# -*- coding: utf-8 -*-
# Copyright (C) 2026 WisadelZ
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""签到层：执行每日签到，并把签到日历整理成界面要用的统计。

签到只在账号页主动点击时执行，所以直接用 :func:`core.downloader.run_with_login`
提供的登录客户端（会话内复用同一个已登录客户端，并在登录时锁定可用的接口域名）；
服务端返回的错误原样抛出，由界面按「签到失败」展示。
"""

import re
from datetime import date

from core.downloader import run_with_login

# 签到结果码（与 jmcomic 的 JmDailyCheckinResp 一致）
CODE_SUCCESS = 0              # 签到成功
CODE_ALREADY_CHECKED_IN = 1   # 今天已经签到过

# 签到成功时服务端会返回形如 "Jcoin:40 EXP:40" 的奖励说明
_COIN_RE = re.compile(r"coin\s*[:：]\s*(\d+)", re.I)
_EXP_RE = re.compile(r"exp\s*[:：]\s*(\d+)", re.I)

# 服务端「今天已签过」的提示片段（jmcomic 只认繁体写法，简体会被它当成签到失败）
_ALREADY_SIGNED_HINTS = ("已簽到", "已签到", "簽到過", "签到过", "已完成")


def check_in(conf):
    """执行一次每日签到，返回签到结果字典：

    - ``code``：0 签到成功；1 今天已经签到过
    - ``coin`` / ``exp``：本次签到获得的 J 币与经验（解析不到时为 None）
    - ``msg``：服务端返回的原始提示
    - ``month_days``：当月已签到天数
    - ``streak``：连续签到天数（以最后一次签到那天为终点）
    - ``event``：当前签到活动名
    """
    return run_with_login(conf, _check_in)


def _check_in(client):
    daily = client.get_daily().res_data
    if not isinstance(daily, dict):
        daily = {}
    month_days, streak = _stats(daily.get("record"))
    result = {
        "code": CODE_SUCCESS,
        "coin": None,
        "exp": None,
        "msg": "",
        "month_days": month_days,
        "streak": streak,
        "event": str(daily.get("event_name") or "").strip(),
    }
    if _signed_today(daily.get("record")):
        # 日历上今天已经打过卡，就不再调签到接口：服务端会回「今天已经签到过了」，
        # 而 jmcomic 认不出这个简体写法，会把它当成签到失败抛出来
        result["code"] = CODE_ALREADY_CHECKED_IN
        return result
    try:
        resp = client.daily_checkin(daily_id=daily.get("daily_id"))
    except Exception as exc:
        if not _is_already_signed_msg(str(exc)):
            raise
        result["code"] = CODE_ALREADY_CHECKED_IN
        return result
    result["code"] = resp.code
    result["msg"] = resp.msg
    result["coin"] = _match(_COIN_RE, resp.msg)
    result["exp"] = _match(_EXP_RE, resp.msg)
    return result


def _match(pattern, text):
    found = pattern.search(text or "")
    return int(found.group(1)) if found else None


def _is_already_signed_msg(text):
    return any(hint in text for hint in _ALREADY_SIGNED_HINTS)


def _signed_today(record):
    """签到日历里今天是否已经打过卡（日历按周分组，日期是当月第几天）。"""
    today = str(date.today().day)
    for week in record or []:
        for day in week or []:
            day = day or {}
            if str(day.get("date") or "").strip() == today and day.get("signed"):
                return True
    return False


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
