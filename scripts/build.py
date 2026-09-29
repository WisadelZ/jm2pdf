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
"""jm2pdf 打包脚本：使用 flet pack（封装 PyInstaller）生成单文件 exe。

脚本位于 scripts/ 目录，项目根目录（app.py、core/、ui/、utils/ 所在处）为其上一级。

生成的 exe 以「名称-v版本号」命名，版本号取自 core/constants.py 的 APP_VERSION。

app.py 只是入口，业务与界面代码拆分在 core、ui、utils 三个源码包中；
PyInstaller 会依据 app.py 的 import 关系自动收集这些模块，无需额外 --add-data ——
首次运行用的配置模板由 core/config.py 的 DEFAULT_CONF_TEXT 在运行时直接生成。

注意：flet pack 在 -y 模式下会 rmtree 掉 --distpath 指定的目录，
因此 distpath 必须使用独立的 dist 子目录，绝不能指向项目目录本身。
"""

import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
PORTABLE_FLET = os.path.join(WORKSPACE_ROOT, "python", "Scripts", "flet.exe")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")

sys.path.insert(0, PROJECT_ROOT)
from core.constants import APP_NAME, APP_VERSION  # noqa: E402

EXE_NAME = "%s-v%s" % (APP_NAME, APP_VERSION)


def find_flet_cli():
    if os.path.isfile(PORTABLE_FLET):
        return PORTABLE_FLET
    found = shutil.which("flet")
    if found:
        return found
    raise SystemExit("未找到 flet CLI，请先执行: pip install flet")


ARGS = [
    find_flet_cli(), "pack", os.path.join(PROJECT_ROOT, "app.py"),
    "--name", EXE_NAME,
    "--icon", os.path.join(PROJECT_ROOT, "assets", "icon.ico"),
    "--distpath", DIST_DIR,
    "--product-name", "Jm2PDF",
    "--product-version", APP_VERSION,
    "--file-version", APP_VERSION,
    "--company-name", "WisadelZ",
    "--copyright", "Copyright (C) 2026 WisadelZ, GPL-3.0-or-later",
    "--file-description", "Jm2PDF - comic downloader & PDF merger",
    "-y",
]

if __name__ == "__main__":
    print("Building %s ..." % EXE_NAME)
    ret = subprocess.call(ARGS, cwd=PROJECT_ROOT)
    built = os.path.join(DIST_DIR, EXE_NAME + ".exe")
    target = os.path.join(PROJECT_ROOT, EXE_NAME + ".exe")
    if ret == 0 and os.path.isfile(built):
        shutil.move(built, target)
        print("OK -> %s (%.1f MB)" % (target, os.path.getsize(target) / 1024 / 1024))
        sys.exit(0)
    print("FAILED: exit=%s built=%s" % (ret, os.path.isfile(built)))
    sys.exit(1)
