# -*- coding: utf-8 -*-
"""把父对 b4 批 needs_parent_review 的裁决逐条落进 _b4_dec.jsonl。

改动只有三类，且都只改台账（产物由 _b4_converge_build.py 机械重建）：
  1) 5 条首轮 keep 按父裁决降为 pending，criterion_note 前置「父裁决（parent_ruling）」并保留首轮记录；
  2) qq_wo_b4_206/c02 首轮为缺省 keep、台账无行，按父裁决补录一行 pending；
  3) qq_wo_b4_307/c02 维持 keep，但按父要求补 limitations（走 override.limitations_append）；
     另为维持 keep 的 019/c01、383/c02 记下父裁决，便于事后追溯。

幂等：重复运行结果相同（以键定位，不依赖行序）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "_b4_dec.jsonl")

DOWNGRADES = {
    ("qq_wo_b4_022", "c02"): (
        "subject_unidentified",
        "主体「弧光」在窗内无任何定义（未点全名、未说清是干员还是召唤物），父复核后亦无法确指，"
        "与同词根的「弧光交通厅」（关卡）、「弧光望」无法区分；claim 自带的「弧光（的重构体）」括号即回执自身的存疑标记。",
    ),
    ("qq_wo_b4_322", "c03"): (
        "subject_unidentified",
        "「影」在窗内只有群内昵称（seq15/22），无单位全名或技能名可锚定，kb 实体索引与 qq 别名表均无该项；父复核认定无法锚定，故不再按形式 keep 保留。",
    ),
    ("qq_wo_b4_322", "c04"): (
        "subject_unidentified",
        "与同窗 c03 同一未闭合主体「影」；本条的两个现象（取消再部署时间显示、吞掉边框显示）虽逐字可核，但脱离「影」这一昵称无法确指对象。",
    ),
    ("qq_wo_b4_395", "c02"): (
        "memory_uncertain",
        "承载句发言者本人在窗内自述「不知道，我只是这么一说」（seq66），且对该机制成因与范围的追问在窗内以「不知道」结束（seq63→seq71），"
        "按「猜测不入」降 pending。",
    ),
    ("qq_wo_b4_206", "c02"): (
        "subject_unidentified",
        "父抽查：claim 的主体「刀」在窗内未定义；核心证据 seq21「0.51吗」是疑问句，仅由 seq22 一个「对」字确认，"
        "与本批「把带问号的猜测写成断言」属同型缺陷，按主体不可确指降 pending。",
    ),
}

KEEP_UPHELD = {
    ("qq_wo_b4_019", "c01"): "父裁决：主命题自足，维持 keep（末句「那个飞行兵」未点名只作留注，不降级）。",
    ("qq_wo_b4_383", "c02"): "父裁决：维持 keep，保留 500/1000 数差的 audit_note。",
}

LIMITATIONS_APPEND = {
    ("qq_wo_b4_307", "c02"): [
        "未实战验证：claim 末句的可观测后果（该状态永远被视为有、无法触发箭雨）在窗内无人完成实测——"
        "seq14（载荷句本人）自述「我不确定这个bug是不是真的能触发」、seq16「没验证的东西还是别乱发了」、seq25「那我试试」。"
        "本条按逻辑层保留，可观测层未经游戏内验证。"
    ],
}

NEW_RECORD = {
    ("qq_wo_b4_206", "c02"): {
        "window": "w000410",
        "verdict": "pending",
    },
}


def main():
    rows, order, index = [], [], {}
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            key = (r["workorder"], r["local_id"])
            if key in index:
                raise SystemExit("台账重复键：%s" % (key,))
            index[key] = len(rows)
            order.append(key)
            rows.append(r)
    before = len(rows)

    changed = []
    for key, (code, basis) in DOWNGRADES.items():
        rec = index.get(key)
        if rec is None:
            # 206/c02 首轮为缺省 keep，台账无行：补录一行
            if key not in NEW_RECORD:
                raise SystemExit("台账缺少待降级项：%s" % (key,))
            r = {"workorder": key[0], "window": NEW_RECORD[key]["window"], "local_id": key[1],
                 "verdict": "pending", "reason_code": code,
                 "criterion_note": "父裁决（parent_ruling）降为 pending：%s" % basis,
                 "needs_parent_review": False,
                 "flags": ["question_turned_into_assertion", "subject_referent_unnamed"],
                 "parent_ruling": "pending"}
            index[key] = len(rows)
            order.append(key)
            rows.append(r)
            changed.append("%s/%s 补录 pending(%s)" % (key[0], key[1], code))
            continue
        r = rows[rec]
        was = r["verdict"]
        r["verdict"] = "pending"
        r["reason_code"] = code
        first = r.get("criterion_note") or ""
        if not first.startswith("父裁决（parent_ruling）"):
            r["criterion_note"] = "父裁决（parent_ruling）降为 pending：%s" % basis + \
                ("\n首轮审读记录（%s）：%s" % (was, first) if first else "")
        r["parent_ruling"] = "pending"
        changed.append("%s/%s %s→pending(%s)" % (key[0], key[1], was, code))

    for key, note in KEEP_UPHELD.items():
        rec = index.get(key)
        if rec is None:
            raise SystemExit("台账缺少维持 keep 项：%s" % (key,))
        rows[rec]["parent_ruling"] = "keep"
        if note not in (rows[rec].get("criterion_note") or ""):
            rows[rec]["criterion_note"] = (rows[rec].get("criterion_note") or "") + "\n" + note
        changed.append("%s/%s 维持 keep（父裁决已记）" % (key[0], key[1]))

    for key, lims in LIMITATIONS_APPEND.items():
        rec = index.get(key)
        if rec is None:
            raise SystemExit("台账缺少需补 limitations 项：%s" % (key,))
        ov = rows[rec].setdefault("override", {})
        existing = list(ov.get("limitations_append") or [])
        for l in lims:
            if l not in existing:
                existing.append(l)
        ov["limitations_append"] = existing
        rows[rec]["parent_ruling"] = "keep"
        if "并按要求补 limitations" not in (rows[rec].get("criterion_note") or ""):
            rows[rec]["criterion_note"] = (rows[rec].get("criterion_note") or "") + \
                "\n父裁决：维持 keep，并按要求补 limitations（未实战验证）。"
        changed.append("%s/%s 补 limitations_append" % (key[0], key[1]))

    # 台账行序：原序 + 新增行（新增按 order 追加在末尾）
    out = [json.dumps(rows[i], ensure_ascii=False) for i in range(len(rows))]
    with open(LEDGER, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("台账 %d 行 → %d 行；改动 %d 项：" % (before, len(rows), len(changed)))
    for c in changed:
        print("  -", c)


if __name__ == "__main__":
    main()
