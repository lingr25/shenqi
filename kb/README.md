# kb/ — 明日方舟进阶机制统一知识库（draft）

直播轨（神祇读神奇录播）与 QQ 群轨（桃大将军粉丝群讨论）横向合并产物，可直接作为 RAG 语料接入 AI。

## 文件

| 文件 | 内容 |
|---|---|
| `docs.jsonl` | 统一文档层（schema 见 `SCHEMA.md`）：vod_atom / vod_cluster / qq_window / qq_canonical / glossary / qq_atom |
| `entity_index.json` | 统一实体索引 mention → canonical/type（PRTS 主表 + QQ 别名合并，多义保留候选） |
| `entity_suggestions.json` | QQ 俗称待人工确认清单（未入 entity_corrector.py） |
| `cross_links.jsonl` | 跨轨候选链接（确定性打分） |
| `cross_conflicts.jsonl` | 跨轨冲突清单，一律 `vod_wins` |
| `qq_atoms.jsonl` | QQ 窗卡原子化产物 |
| `*_report.md` | 各阶段报告与评测 |

## 使用红线

1. **冲突以录播为准**：`conflict_resolution=vod_wins` 时采用录播命题，群聊被否结论不索引原文。
2. 全部内容为 **draft**，人工审核前不公开发布。
3. QQ 侧已脱敏，禁止任何形式的群友隐私入库。
4. `hypothesis`/`question` 类型是未证实内容，RAG 回答时不得当作定论。
5. 检索建议：BM25/向量分 × `retrieval_boost` × `retrieval_weight`；优先引用 `vod_cluster(agreed)` 与 `qq_canonical`。

## 复现

```bash
python kb_build_docs.py       # A: 统一文档层
python kb_build_entities.py   # B: 实体索引 + 回填
python kb_link_tracks.py      # C: 确定性弱对齐
python kb_llm_align.py        # C+: LLM 仲裁 (需 GROK_API_KEY/GROK_MODEL 环境变量)
python kb_atomize_qq.py       # D+: QQ 窗卡原子化
python kb_pack_qq_atoms.py    # D+: 并入 docs.jsonl
python kb_eval.py             # D: 检索评测
```
