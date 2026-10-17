#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 站录播列表与官方字幕抓取（「神祇读神奇」，UP 主 Lapis___，mid 592610）。

补齐早期一次性交互抓取（all_search_videos.json / subtitles/ / subtitle_inventory.json）
的可复现脚本，输出格式与已有文件逐字段一致，可直接增量并入。纯标准库。

子命令:
  list                    列出 UP 主投稿（关键词「神奇」），与已有清单比对，报告新增 BV
  subtitles BV... | --new 逐分P取 cid → 字幕列表 → 下载，写 subtitles/ 与 subtitle_inventory.json

通用参数:
  --out DIR     输出根目录（默认仓库根）。指向临时目录可做不落仓库的验证。
  --dry-run     只读请求与报告，不写任何数据文件（运行记录也只打印）。
  --sleep SEC   请求间隔（默认 1.5 秒），失败按指数退避重试。

Cookie: 仅从环境变量 BILI_SESSDATA 读取，绝不写盘/打印。未设置时 list 走免登录的
medialist 兜底，字幕通常拿不到 ai-zh（需登录）。
遇到风控码（-352 / -799 / -412 等）立即停止并给出提示，不会反复重试。
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from functools import reduce

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MID = 592610
KEYWORD = "神奇"
SERIES_RE = re.compile(r"【神祇读神奇】|【神奇】")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
RISK_CODES = {-352: "风控校验失败", -799: "请求过于频繁", -412: "请求被拦截", -509: "请求过于频繁"}

EP_NAV = "https://api.bilibili.com/x/web-interface/nav"
EP_ARC = "https://api.bilibili.com/x/space/wbi/arc/search"
EP_MEDIALIST = "https://api.bilibili.com/x/v2/medialist/resource/list"
EP_VIEW = "https://api.bilibili.com/x/web-interface/view"
EP_PLAYER = "https://api.bilibili.com/x/player/wbi/v2"
EP_PAGELIST = "https://api.bilibili.com/x/player/pagelist"

MIXIN_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
             33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
             61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
             36, 20, 34, 44, 52]


class RiskControl(Exception):
    pass


class Client:
    def __init__(self, sleep=1.5, retries=3):
        self.sleep = sleep
        self.retries = retries
        self.sessdata = os.environ.get("BILI_SESSDATA", "").strip()
        self._mixin = None
        self._last = 0.0
        self.endpoints = set()
        self.requests = 0

    def _headers(self, referer="https://www.bilibili.com/"):
        h = {"User-Agent": UA, "Referer": referer}
        if self.sessdata:
            h["Cookie"] = "SESSDATA=" + self.sessdata
        return h

    def _wait(self):
        dt = time.monotonic() - self._last
        if dt < self.sleep:
            time.sleep(self.sleep - dt)
        self._last = time.monotonic()

    def get_raw(self, url, referer="https://www.bilibili.com/"):
        err = None
        for i in range(self.retries):
            self._wait()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers=self._headers(referer))
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 412:
                    raise RiskControl(f"HTTP 412（请求被拦截）: {url.split('?')[0]}")
                err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                err = e
            time.sleep(self.sleep * (2 ** (i + 1)))
        raise RuntimeError(f"请求失败（已重试 {self.retries} 次）: {url.split('?')[0]}: {err}")

    def get_json(self, endpoint, params=None, wbi=False, referer="https://www.bilibili.com/"):
        params = dict(params or {})
        if wbi:
            params = self.sign(params)
        url = endpoint + ("?" + urllib.parse.urlencode(params) if params else "")
        self.endpoints.add(endpoint)
        d = json.loads(self.get_raw(url, referer).decode("utf-8"))
        code = d.get("code", 0)
        if code in RISK_CODES:
            raise RiskControl(f"{endpoint} 返回 code={code}（{RISK_CODES[code]}）：{d.get('message')}")
        if code != 0:
            raise RuntimeError(f"{endpoint} 返回 code={code}: {d.get('message')}")
        return d.get("data")

    # ---- WBI 签名 ----
    def mixin_key(self):
        if self._mixin is None:
            data = self.get_json_nav()
            img = data["wbi_img"]
            raw = (img["img_url"].rsplit("/", 1)[1].split(".")[0]
                   + img["sub_url"].rsplit("/", 1)[1].split(".")[0])
            self._mixin = reduce(lambda s, i: s + raw[i], MIXIN_TAB, "")[:32]
        return self._mixin

    def get_json_nav(self):
        # nav 未登录时 code=-101 但仍返回 wbi_img
        self.endpoints.add(EP_NAV)
        d = json.loads(self.get_raw(EP_NAV).decode("utf-8"))
        return d["data"]

    def is_login(self):
        try:
            return bool(self.get_json_nav().get("isLogin"))
        except Exception:
            return False

    def sign(self, params):
        params = dict(params, wts=int(time.time()))
        q = urllib.parse.urlencode(sorted(
            (k, "".join(c for c in str(v) if c not in "!'()*")) for k, v in params.items()))
        params["w_rid"] = hashlib.md5((q + self.mixin_key()).encode()).hexdigest()
        return params


# ---------------------------------------------------------------- 文件工具
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj, dry):
    """与已有数据文件一致：indent=2、ensure_ascii=False、LF、无末尾换行。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if dry:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def paths(out):
    return {"search": os.path.join(out, "all_search_videos.json"),
            "inventory": os.path.join(out, "subtitle_inventory.json"),
            "subs": os.path.join(out, "subtitles")}


def existing_bvids(out):
    """已覆盖 BV：优先读 --out 下文件，缺失时回退仓库根（便于临时目录验证）。"""
    seen = set()
    for base in dict.fromkeys([out, ROOT]):
        p = paths(base)
        seen |= {v["bvid"] for v in load_json(p["search"], {}).get("videos", [])}
        seen |= {v["bvid"] for v in load_json(p["inventory"], [])}
        if seen:
            break
    return seen


# ---------------------------------------------------------------- list
STOP_AFTER_SEEN = 8  # 连续遇到这么多已覆盖 BV 才停（接口顺序与发布时间并非严格单调）


def fetch_list(cli, stop_at=None):
    """返回投稿记录（arc/search 原始字段，接口顺序）。
    stop_at: 已覆盖 BV 集合；连续 STOP_AFTER_SEEN 个已覆盖即停（增量），已覆盖条目不返回。"""
    out, pn, run = [], 1, 0
    try:
        while True:
            d = cli.get_json(EP_ARC, {"mid": MID, "ps": 50, "pn": pn, "keyword": KEYWORD,
                                      "order": "pubdate", "tid": 0},
                             wbi=True, referer=f"https://space.bilibili.com/{MID}/video")
            vl = (d.get("list") or {}).get("vlist") or []
            for v in vl:
                if stop_at and v["bvid"] in stop_at:
                    run += 1
                    if run >= STOP_AFTER_SEEN:
                        return out, "arc_search"
                    continue
                run = 0
                out.append(v)
            total = (d.get("page") or {}).get("count", 0)
            if not vl or pn * 50 >= total:
                return out, "arc_search"
            pn += 1
    except RiskControl as e:
        print(f"[warn] arc/search 被风控：{e}；改用免登录 medialist 兜底", file=sys.stderr)
    return fetch_list_medialist(cli, stop_at), "medialist"


def fetch_list_medialist(cli, stop_at=None, max_pages=150):
    """免登录兜底。注意 Lapis___ 是多位主播的录播号，medialist 不能按关键词过滤，
    每页 20 条里多为其他主播；因此按发布时间翻到「已覆盖最新一期 - 7 天」为止
    （stop_at 为空即全量时翻到 max_pages），再在本地按标题过滤系列。"""
    cutoff = None
    if stop_at:
        known = [v for v in load_json(paths(ROOT)["search"], {}).get("videos", [])
                 if v["bvid"] in stop_at]
        if known:
            cutoff = max(v["created"] for v in known) - 7 * 86400
    out, oid = [], ""
    for _ in range(max_pages):
        d = cli.get_json(EP_MEDIALIST, {"type": 1, "biz_id": MID, "ps": 20, "oid": oid,
                                        "otype": 2, "direction": "false", "desc": "true",
                                        "sort_field": 1, "tid": 0, "with_current": "false"})
        items = d.get("media_list") or []
        for m in items:
            title = m.get("title", "")
            if (stop_at and m["bv_id"] in stop_at) or not SERIES_RE.search(title):
                continue
            # 字段名对齐 arc/search 的常用子集
            out.append({"title": title, "author": (m.get("upper") or {}).get("name", ""),
                        "mid": MID, "created": m.get("pubtime"), "aid": m.get("id"),
                        "bvid": m["bv_id"], "pic": m.get("cover", ""),
                        "description": m.get("intro", ""), "length":
                        "%d:%02d" % divmod(m.get("duration", 0), 60),
                        "dur_sec": m.get("duration", 0)})
        if not d.get("has_more") or not items:
            break
        if cutoff and items[-1].get("pubtime", 0) < cutoff:
            break
        oid = items[-1]["id"]
    return out


def cmd_list(cli, args):
    seen = existing_bvids(args.out)
    new, source = fetch_list(cli, stop_at=None if args.full else seen)
    new = [v for v in new if v["bvid"] not in seen and KEYWORD in v.get("title", "")]
    print(f"来源: {source}；已覆盖 {len(seen)} 个 BV；新增 {len(new)} 个")
    for v in new:
        day = _dt.datetime.fromtimestamp(v["created"], _dt.timezone(_dt.timedelta(hours=8)))
        print(f"  {v['bvid']}  {day:%Y-%m-%d}  {v.get('length', '')}  {v['title']}")
    written = {}
    if args.write and new:
        p = paths(args.out)
        base = load_json(p["search"], None) or load_json(paths(ROOT)["search"], {})
        base = dict(base) if base else {"total_count": 0, "keyword": KEYWORD, "mid": MID, "videos": []}
        base["videos"] = new + [v for v in base["videos"] if v["bvid"] not in {n["bvid"] for n in new}]
        base["total_count"] = len(base["videos"])
        written[p["search"]] = dump_json(p["search"], base, args.dry_run)
    return {"source": source, "covered": len(seen), "new": [v["bvid"] for v in new],
            "videos": new}, written


# ---------------------------------------------------------------- subtitles
def fetch_video(cli, bvid, meta=None):
    """view 取标题/发布时间/分P；view 被 412 拦截时退回 pagelist + 列表元数据。"""
    try:
        d = cli.get_json(EP_VIEW, {"bvid": bvid})
        return {"bvid": d["bvid"], "title": d["title"], "total_duration": d["duration"],
                "pubdate": d["pubdate"],
                "pages": [{"page": p["page"], "cid": p["cid"], "part": p["part"],
                           "duration": p["duration"]} for p in d["pages"]]}
    except RiskControl as e:
        if callable(meta):
            meta = meta()
        if not meta:
            raise
        print(f"[warn] view 被拦截（{e}），改用 pagelist + 列表元数据", file=sys.stderr)
    pl = cli.get_json(EP_PAGELIST, {"bvid": bvid}) or []
    pages = [{"page": p["page"], "cid": p["cid"], "part": p["part"],
              "duration": p["duration"]} for p in pl]
    return {"bvid": bvid, "title": meta["title"],
            "total_duration": sum(p["duration"] for p in pages),
            "pubdate": meta["created"], "pages": pages}


def fetch_page_subtitle(cli, bvid, cid):
    d = cli.get_json(EP_PLAYER, {"bvid": bvid, "cid": cid}, wbi=True,
                     referer=f"https://www.bilibili.com/video/{bvid}")
    subs = ((d or {}).get("subtitle") or {}).get("subtitles") or []
    pick = next((s for s in subs if s.get("lan") == "ai-zh"), None) or \
        next((s for s in subs if s.get("lan", "").startswith("zh")), None)
    if not pick or not pick.get("subtitle_url"):
        return None, None
    url = pick["subtitle_url"]
    url = "https:" + url if url.startswith("//") else url
    cli.endpoints.add("aisubtitle.hdslb.com (subtitle_url)")
    body = json.loads(cli.get_raw(url).decode("utf-8")).get("body") or []
    return pick["lan"], body


def lookup_meta(cli, bvid, cache):
    """view 不可用时补标题/发布时间：先查已有清单，再翻一次完整投稿列表（结果缓存）。"""
    for v in load_json(paths(ROOT)["search"], {}).get("videos", []):
        cache.setdefault(v["bvid"], v)
    if bvid not in cache and not cache.get("__listed__"):
        cache["__listed__"] = True
        for v in fetch_list(cli, stop_at=existing_bvids(ROOT))[0]:
            cache.setdefault(v["bvid"], v)
    return cache.get(bvid)


def cmd_subtitles(cli, args):
    if not cli.sessdata:
        print("[warn] 未设置 BILI_SESSDATA：ai-zh 字幕通常需要登录，结果可能全为无字幕", file=sys.stderr)
    bvids, meta = list(args.bvids), {}
    if args.new:
        res, _ = cmd_list(cli, argparse.Namespace(out=args.out, full=False, write=False,
                                                  dry_run=True))
        bvids += [b for b in res["new"] if b not in bvids]
        meta = {v["bvid"]: v for v in res["videos"]}
    p = paths(args.out)
    inv = load_json(p["inventory"], None)
    if inv is None:
        inv = load_json(paths(ROOT)["inventory"], []) if args.out == ROOT else []
    written, entries = {}, []
    for bvid in bvids:
        v = fetch_video(cli, bvid, meta.get(bvid) or (lambda b=bvid: lookup_meta(cli, b, meta)))
        for pg in v["pages"]:
            lan, body = fetch_page_subtitle(cli, bvid, pg["cid"])
            if body:
                fn = f"{bvid}_p{pg['page']}_{pg['cid']}.json"
                doc = {"bvid": bvid, "title": v["title"], "page": pg["page"], "part": pg["part"],
                       "cid": pg["cid"], "lan": lan,
                       "body": [{k: b.get(k) for k in ("from", "to", "sid", "location",
                                                        "content", "music")} for b in body]}
                written[os.path.join(p["subs"], fn)] = dump_json(
                    os.path.join(p["subs"], fn), doc, args.dry_run)
                pg.update(has_subtitle=True, sub_type=lan, sub_file=fn, items_count=len(body),
                          total_chars=sum(len(b.get("content", "")) for b in body))
            else:
                pg["has_subtitle"] = False
            print(f"  {bvid} P{pg['page']} cid={pg['cid']} {pg['duration']}s "
                  f"{'字幕 ' + lan + ' ' + str(pg.get('items_count')) + ' 条' if body else '无字幕（待 ASR）'}")
        entries.append(v)
    # 新条目置前（与已有文件「新→旧」一致），同 BV 覆盖
    done = {e["bvid"] for e in entries}
    inv = entries + [e for e in inv if e["bvid"] not in done]
    written[p["inventory"]] = dump_json(p["inventory"], inv, args.dry_run)
    return {"bvids": bvids, "videos": entries}, written


# ---------------------------------------------------------------- main
def _rel_out(path):
    """仓库内写相对路径；仓库外只记 <external>，避免把本机路径写进记录。"""
    rel = os.path.relpath(path, ROOT)
    return "<external>" if rel.startswith("..") else rel.replace(os.sep, "/")


def write_manifest(args, cli, result, written, started):
    now = _dt.datetime.now().astimezone()
    rec = {"tool": "pipeline/fetch_bili.py", "command": args.cmd,
           "started_at": started.isoformat(timespec="seconds"),
           "finished_at": now.isoformat(timespec="seconds"),
           "args": {k: (_rel_out(v) if k == "out" else v)
                    for k, v in vars(args).items()},
           "logged_in": bool(cli.sessdata), "endpoints": sorted(cli.endpoints),
           "requests": cli.requests,
           "result": {k: v for k, v in result.items() if k != "videos"},
           "outputs": {os.path.relpath(k, args.out).replace(os.sep, "/"): v
                       for k, v in sorted(written.items())}}
    if args.dry_run:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return
    path = os.path.join(args.out, "runs", f"{started:%Y%m%d}_fetch", "manifest.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    print(f"运行记录: {os.path.relpath(path, args.out)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=ROOT, help="输出根目录（默认仓库根）")
    ap.add_argument("--dry-run", action="store_true", help="不写数据文件")
    ap.add_argument("--sleep", type=float, default=1.5, help="请求间隔秒数")
    sp = ap.add_subparsers(dest="cmd", required=True)
    pl = sp.add_parser("list", help="列出新增录播")
    pl.add_argument("--full", action="store_true", help="翻完全部分页（默认遇到已覆盖 BV 即停）")
    pl.add_argument("--write", action="store_true", help="把新增条目并入 all_search_videos.json")
    ps = sp.add_parser("subtitles", help="下载字幕并更新 subtitle_inventory.json")
    ps.add_argument("bvids", nargs="*")
    ps.add_argument("--new", action="store_true", help="处理 list 报告的全部新增 BV")
    args = ap.parse_args(argv)
    args.out = os.path.abspath(args.out)
    if args.cmd == "subtitles" and not (args.bvids or args.new):
        ap.error("subtitles 需要 BV 号或 --new")
    cli = Client(sleep=args.sleep)
    started = _dt.datetime.now().astimezone()
    try:
        result, written = (cmd_list if args.cmd == "list" else cmd_subtitles)(cli, args)
    except RiskControl as e:
        print(f"[stop] 触发风控，已停止：{e}\n  建议：稍后重试、加大 --sleep、确认 BILI_SESSDATA 有效。",
              file=sys.stderr)
        return 2
    write_manifest(args, cli, result, written, started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
