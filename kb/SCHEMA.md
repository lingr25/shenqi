# kb/ 统一知识库 schema (阶段A)

`kb/docs.jsonl` 每行一条统一文档，字段：

| 字段 | 说明 |
|---|---|
| `id` | 主键：`vod_atom:{atom_id}` / `vod_cluster:{cluster_id}` / `window:{w...}` / `canonical:{c...}` / `glossary:{term}` |
| `doc_type` | `vod_atom` / `vod_cluster` / `qq_window` / `qq_canonical` / `glossary` |
| `track` | `vod_official` / `vod_cloud` / `qq` |
| `status` | `draft` / `canonical_draft` / `duplicate` / `superseded`（全部 draft 层） |
| `issue_status` | `agreed` / `conflict` / `open` / `n/a`（仅 vod 侧有议题态） |
| `novelty` | `vod_only` / `group_only` / `also_in_vod` / `conflict` / `unknown` |
| `conflict_resolution` | `vod_wins` / `open` / `n/a`；**冲突一律以录播为准** |
| `text` | 检索主文本 |
| `category` | 直播自由类名或 8 桶 / QQ 10 类 |
| `applies_to` / `conditions` / `scope` | 适用对象 / 前提条件 / general 或 instance |
| `claim_type` | 直播原子六值（conclusion/correction/derivation/observation/hypothesis/question），QQ 侧为 null |
| `entities` | `[{mention, canonical, type}]`，阶段B 统一索引回填 |
| `evidence` | `{kind: video_quote, clips:[{t_start,t_end,quote}]}` 或 `{kind: qq_span, window_id, ...}` |
| `source` | `{bvid_stem, recorded_at, speaker, credibility}` 或 `{window_id, as_of, origin, credibility}` |
| `retrieval_weight` | 直播类型分权（conclusion/correction=1.0 … question=0.1），其余 1.0 |
| `retrieval_boost` | qq_canonical 1.5 / glossary 1.3 / vod_cluster agreed 1.3, conflict 1.4, open 1.0 |
| `links` | `{cluster_ids, canonical_ids, linked_doc_ids, counterpart_ids, member_atom_ids}` |
| `game_version` | 版本，当前全 null |

红线：冲突裁决 `vod_wins`；QQ 隐私已脱敏，禁止写入 QQ 号；本层为 draft，人工审核前不公开发布。
