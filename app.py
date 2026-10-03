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
"""Jm2PDF v2.4.3 - 禁漫本子探索、在线浏览与下载工具（Flet UI）

程序入口：仅负责创建窗口并交给 :class:`ui.app_ui.AppUI` 编排。
各功能模块分布如下：

    core/     业务逻辑（常量、配置、下载、元数据、搜索、账号、收藏、签到、下载目录管理、日志桥接）
    ui/       界面层（主页、探索页、本子详情页、账号页、收藏页、资源管理器页、设置页、帮助页、协调器）
    utils/    通用工具（多语言、辅助函数）
"""

import os
import sys

# 便携版 Python 通过 python312._pth 以隔离模式运行，脚本目录不会自动进入
# sys.path，这里显式补充，保证源码运行时能 import core / ui / utils（打包后无副作用）。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 以无控制台方式打包时 sys.stdout / sys.stderr 可能为 None，先做兜底
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import flet as ft

from core.constants import APP_NAME, APP_VERSION  # noqa: F401  (build.py 由此读取版本)
from ui.app_ui import AppUI

__all__ = ["APP_NAME", "APP_VERSION", "main"]


def main(page: ft.Page):
    AppUI(page)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
