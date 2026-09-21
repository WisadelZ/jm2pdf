# -*- coding: utf-8 -*-
"""jm2pdf 打包脚本：使用 flet pack（封装 PyInstaller）生成单文件 exe。

生成的 exe 以「名称-v版本号」命名，版本号取自 app.py 中的 APP_VERSION。

注意：flet pack 在 -y 模式下会 rmtree 掉 --distpath 指定的目录，
因此 distpath 必须使用独立的 dist 子目录，绝不能指向项目目录本身。
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
PORTABLE_FLET = os.path.join(PROJECT_ROOT, "python", "Scripts", "flet.exe")
DIST_DIR = os.path.join(HERE, "dist")

sys.path.insert(0, HERE)
from app import APP_NAME, APP_VERSION  # noqa: E402

EXE_NAME = "%s-v%s" % (APP_NAME, APP_VERSION)


def find_flet_cli():
    if os.path.isfile(PORTABLE_FLET):
        return PORTABLE_FLET
    found = shutil.which("flet")
    if found:
        return found
    raise SystemExit("未找到 flet CLI，请先执行: pip install flet")


ARGS = [
    find_flet_cli(), "pack", os.path.join(HERE, "app.py"),
    "--name", EXE_NAME,
    "--icon", os.path.join(HERE, "icon.ico"),
    "--distpath", "dist",
    "--add-data", os.path.join(HERE, "conf.yml") + os.pathsep + ".",
    "--product-name", "Jm2PDF",
    "--product-version", APP_VERSION,
    "--file-version", APP_VERSION,
    "--company-name", "WisadelZ",
    "--copyright", "Copyright (c) 2026 WisadelZ, CC BY-NC-ND 4.0",
    "--file-description", "Jm2PDF - comic downloader & PDF merger",
    "-y",
]

if __name__ == "__main__":
    print("Building %s ..." % EXE_NAME)
    ret = subprocess.call(ARGS, cwd=HERE)
    built = os.path.join(DIST_DIR, EXE_NAME + ".exe")
    target = os.path.join(HERE, EXE_NAME + ".exe")
    if ret == 0 and os.path.isfile(built):
        shutil.move(built, target)
        print("OK -> %s (%.1f MB)" % (target, os.path.getsize(target) / 1024 / 1024))
        sys.exit(0)
    print("FAILED: exit=%s built=%s" % (ret, os.path.isfile(built)))
    sys.exit(1)
