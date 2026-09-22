# -*- coding: utf-8 -*-
"""通用小工具：数值钳制、ID 文本解析。"""

import re


def clamp(value, low, high):
    """把 value 转成整数并限制在 [low, high] 区间内，非法值返回 low。"""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def parse_ids(text):
    """把用户输入的 ID 文本按逗号/空格等分隔符切分并去重，保持输入顺序。"""
    tokens = [t for t in re.split(r"[\s,;，；、]+", text or "") if t]
    seen, result = set(), []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
