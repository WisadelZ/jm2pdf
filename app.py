# -*- coding: utf-8 -*-
"""Jm2PDF v2.1.1 - 禁漫本子下载工具（Flet UI）

程序入口：仅负责创建窗口并交给 :class:`ui.app_ui.AppUI` 编排。
各功能模块分布如下：

    core/     业务逻辑（常量、配置、下载、元数据、下载目录管理、日志桥接）
    ui/       界面层（主页、资源管理器页、设置页、帮助页、协调器）
    utils/    通用工具（多语言、辅助函数）

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

Unauthorized modification, distribution of modified versions,
or commercial use is strictly prohibited.
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
