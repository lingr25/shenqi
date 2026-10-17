# pipeline/

## fetch_bili.py：录播列表与官方字幕抓取

替代早期一次性交互抓取，产出与仓库已有文件逐字段一致：

| 产物 | 格式 |
|---|---|
| `all_search_videos.json` | `{total_count, keyword: "神奇", mid: 592610, videos: [...]}`，`videos` 为 `x/space/wbi/arc/search` 原始字段，新→旧 |
| `subtitles/{BV}_p{page}_{cid}.json` | `{bvid, title, page, part, cid, lan, body: [{from,to,sid,location,content,music}]}` |
| `subtitle_inventory.json` | `[{bvid,title,total_duration,pubdate,pages:[{page,cid,part,duration,has_subtitle[,sub_type,sub_file,items_count,total_chars]}]}]`，新→旧 |

全部 `indent=2`、`ensure_ascii=False`、LF、无末尾换行，纯标准库。

```bash
export BILI_SESSDATA=...            # 只从环境变量读取，绝不写盘/打印
python pipeline/fetch_bili.py --dry-run list              # 报告新增 BV（只读）
python pipeline/fetch_bili.py list --write                # 并入 all_search_videos.json
python pipeline/fetch_bili.py subtitles --new             # 新增 BV 的字幕 + 更新 inventory
python pipeline/fetch_bili.py subtitles BV17rp16HECP      # 指定 BV
python pipeline/fetch_bili.py --out /tmp/x subtitles --new  # 写到临时目录做验证
```

- **列表**：UP 主 Lapis___（mid 592610）是多位主播共用的录播号，按关键词「神奇」走 WBI 签名的 `arc/search`；被风控（-352/-799/HTTP 412）时退回免登录 `medialist`，按发布时间翻到"已覆盖最新一期 − 7 天"并按标题 `【神祇读神奇】|【神奇】` 过滤。
- **分P**：`x/web-interface/view`；被 412 拦截时退回 `x/player/pagelist` + 列表元数据（标题、发布时间）。
- **字幕**：`x/player/wbi/v2`（ai-zh 需登录）。无字幕的分P记 `has_subtitle: false`，留待 ASR。
- **礼貌**：默认请求间隔 1.5s（`--sleep`），网络错误指数退避重试 3 次；接口返回风控码立即停止，不重试轰炸。
- **运行记录**：每次运行写 `runs/<YYYYMMDD>_fetch/manifest.json`（时间、参数、端点、请求数、新增 BV、产物 sha256）；`--dry-run` 只打印。仓库外的 `--out` 记为 `<external>`。
