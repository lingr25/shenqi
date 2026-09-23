# -*- coding: utf-8 -*-
"""本地私有身份配置加载器（公开仓库不含任何真实 QQ 号）。

真实号码写在 qq_info/identities.json —— 该目录已被 .gitignore 忽略，
仅存在于本地归档机。文件格式：

    {
      "host_qq":     "主播QQ",
      "expert_qq":   "专家QQ",
      "bot_qqs":     ["bot1", "bot2", ...],
      "xiaoxiao_qq": "小晓bot QQ"
    }

文件缺失或字段缺失时一律回退为空字符串/空元组：脚本仍可正常 import
与运行，只是身份匹配永不命中（等价于"不标记任何人"）。
"""
import json
import os

_IDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'qq_info', 'identities.json')


def _load() -> dict:
    try:
        with open(_IDS_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


_IDS = _load()
HOST_QQ = str(_IDS.get('host_qq', '') or '')
EXPERT_QQ = str(_IDS.get('expert_qq', '') or '')
BOT_QQS = tuple(str(q) for q in _IDS.get('bot_qqs', ()) if q)
XIAOXIAO_QQ = str(_IDS.get('xiaoxiao_qq', '') or '')
