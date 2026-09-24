# -*- coding: utf-8 -*-
"""签到层：执行每日签到，并把签到日历整理成界面要用的统计。

签到只在账号页主动点击时执行，所以直接用带登录态的客户端；服务端返回的错误
原样抛出，由界面按「签到失败」展示。
"""

import re

from core.account import get_credentials
from core.downloader import build_option

# 签到成功时服务端会返回形如 "Jcoin:40 EXP:40" 的奖励说明
_COIN_RE = re.compile(r"coin\s*[:：]\s*(\d+)", re.I)
_EXP_RE = re.compile(r"exp\s*[:：]\s*(\d+)", re.I)


def check_in(conf):
    """执行一次每日签到，返回签到结果字典：

    - ``code``：0 签到成功；1 今天已经签到过
    - ``coin`` / ``exp``：本次签到获得的 J 币与经验（解析不到时为 None）
    - ``msg``：服务端返回的原始提示
    - ``month_days``：当月已签到天数
    - ``streak``：连续签到天数（以最后一次签到那天为终点）
    - ``event``：当前签到活动名
    """
    username, password = get_credentials()
    client = build_option(conf, with_login=False).new_jm_client()
    client.login(username, password)
    resp = client.daily_checkin()
    daily = client.get_daily().res_data or {}
    month_days, streak = _stats(daily.get("record"))
    return {
        "code": resp.code,
        "coin": _match(_COIN_RE, resp.msg),
        "exp": _match(_EXP_RE, resp.msg),
        "msg": resp.msg,
        "month_days": month_days,
        "streak": streak,
        "event": str(daily.get("event_name") or "").strip(),
    }


def _match(pattern, text):
    found = pattern.search(text or "")
    return int(found.group(1)) if found else None


def _stats(record):
    """从签到日历里算出 (当月签到天数, 连续签到天数)。

    日历是按周分组的二维列表，每格是 ``{"date": "07", "signed": bool}``；
    未到来的日期 ``signed`` 为 None，不计入。
    """
    signed_days = []
    for week in record or []:
        for day in week or []:
            date = str((day or {}).get("date") or "").strip()
            if date.isdigit() and day.get("signed"):
                signed_days.append(int(date))
    signed_days.sort()
    streak = 0
    last = None
    for day in reversed(signed_days):          # 以最后一次签到那天为终点往前数
        if last is not None and last - day != 1:
            break
        streak += 1
        last = day
    return len(signed_days), streak
