"""从甄选层生成可直接灌入 RAG 的语料包（纯本地，不调用任何 API）。

输入: kb_trial/curated_high_quality.json
输出: rag_pack/ 下的 corpus.jsonl / corpus.json / system_prompt.txt / MANIFEST.json

语料正文的组成原则:
- 检索文本(text)只放机制本身: claim + subject + condition，不用 claim 单句，
  因为缺主语的条目单靠 claim 无法被正确解读。
- scope 是元数据而非正文: 它只标注适用范围，混进正文会干扰检索。
- 引文与审核理由不进入检索文本，放在 metadata，供溯源展示而非向量化。
"""
import hashlib
import json
import os
from collections import Counter

SRC = "kb_trial/curated_high_quality.json"
OUT_DIR = "rag_pack"

SCOPE_ZH = {"universal": "通用", "instance": "单次实例", "未标注": "未标注"}
REVIEW_ZH = {"user_verified": "用户确认", "agent_verified": "代理核读"}


def build_text(entry):
    """检索正文: 机制句 + 主语 + 条件。"""
    lines = []
    subject = (entry.get("subject") or "").strip()
    condition = (entry.get("condition") or "").strip()
    if subject and subject != "未标注":
        lines.append(f"涉及对象：{subject}")
    if condition and condition != "未标注":
        lines.append(f"触发条件：{condition}")
    lines.append(f"机制：{entry['claim'].strip()}")
    return "\n".join(lines)


def collect_quotes(entry):
    quotes = []
    for cit in entry.get("citations", []):
        for q in cit.get("quotes", []):
            text = (q.get("text") or "").strip()
            if not text or text in [x["text"] for x in quotes]:
                continue
            quotes.append({
                "text": text,
                "time": q.get("t_line_label"),
                "t_start": q.get("t_start"),
                "transcript_file": cit.get("transcript_file"),
                "window_id": cit.get("window_id"),
                "citation_status": cit.get("status"),
            })
    return quotes


def first_source_url(entry):
    for cit in entry.get("citations", []):
        bv = cit.get("bvid_stem")
        t = None
        for q in cit.get("quotes", []):
            if q.get("t_start") is not None:
                t = int(q["t_start"])
                break
        if bv:
            bv_id = bv.split("_")[0]
            return f"https://bilibili.com/video/{bv_id}" + (f"?t={t}" if t else "")
    return None


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    entries = data["entries"]
    os.makedirs(OUT_DIR, exist_ok=True)

    records = []
    for e in entries:
        ev = e.get("evidence_review", {}) or {}
        rv = e.get("review", {}) or {}
        records.append({
            "id": e["id"],
            "text": build_text(e),
            "metadata": {
                "claim": e["claim"],
                "subject": e.get("subject"),
                "condition": e.get("condition"),
                "category": e.get("category"),
                "scope": e.get("scope"),
                "scope_zh": SCOPE_ZH.get(e.get("scope"), e.get("scope")),
                "source_layer": e.get("source_layer"),
                "track": e.get("track"),
                "review_status": rv.get("status"),
                "review_zh": REVIEW_ZH.get(rv.get("status"), rv.get("status")),
                "evidence_status": ev.get("status"),
                "confidence": ev.get("confidence", "text-source-supported"),
                "recorded_at": next(
                    (c.get("recorded_at") for c in e.get("citations", []) if c.get("recorded_at")),
                    e.get("recorded_ym"),
                ),
                "source_url": first_source_url(e),
                "quotes": collect_quotes(e),
                "caveat": "判定基于转写文本，未核听原片音画、未做游戏内实测；官方字幕本身可能有 ASR 讹写。",
            },
        })

    with open(os.path.join(OUT_DIR, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(os.path.join(OUT_DIR, "corpus.json"), "w", encoding="utf-8") as f:
        json.dump({"schema_version": "rag-corpus-1.0", "count": len(records),
                   "documents": records}, f, ensure_ascii=False, indent=1)

    src_sha = hashlib.sha256(open(SRC, "rb").read()).hexdigest()
    corpus_sha = hashlib.sha256(open(os.path.join(OUT_DIR, "corpus.jsonl"), "rb").read()).hexdigest()

    manifest = {
        "schema_version": "rag-corpus-1.0",
        "document_count": len(records),
        "source_file": SRC,
        "source_sha256": src_sha,
        "corpus_jsonl_sha256": corpus_sha,
        "by_category": dict(Counter(e["category"] for e in entries)),
        "by_source_layer": dict(Counter(e["source_layer"] for e in entries)),
        "by_review_status": dict(Counter(e["review"]["status"] for e in entries)),
        "confidence_ceiling": "text-source-supported",
        "not_verified": "未核听原片音画、未做游戏内实测；不能声称游戏内真值",
        "files": {
            "corpus.jsonl": "检索语料，每行一条文档 id/text/metadata",
            "corpus.json": "同上，单个 JSON 数组（部分平台上传需要）",
            "system_prompt.txt": "问答系统 system prompt，约束引用与不确定性",
            "MANIFEST.json": "本文件，含计数与 sha256",
        },
    }
    with open(os.path.join(OUT_DIR, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(json.dumps({"documents": len(records), "corpus_sha256": corpus_sha,
                      "source_sha256": src_sha}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
