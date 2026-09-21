# -*- coding: utf-8 -*-
"""jm2pdf 打包脚本：使用项目内置的 portable Python + PyInstaller 生成单文件 exe。

生成的 exe 以「名称-v版本号」命名，版本号取自 app.py 中的 APP_VERSION。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
PORTABLE_PY = os.path.join(PROJECT_ROOT, "python")

# 让 PyInstaller 的 tkinter hook 能定位到 portable Python 中的 tcl/tk 数据
os.environ["TCL_LIBRARY"] = os.path.join(PORTABLE_PY, "tcl", "tcl8.6")
os.environ["TK_LIBRARY"] = os.path.join(PORTABLE_PY, "tcl", "tk8.6")

sys.path.insert(0, HERE)
from app import APP_NAME, APP_VERSION  # noqa: E402

import PyInstaller.__main__  # noqa: E402

EXE_NAME = "%s-v%s" % (APP_NAME, APP_VERSION)

ARGS = [
    os.path.join(HERE, "app.py"),
    "--name", EXE_NAME,
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    "-i", "icon.ico",
    "--distpath", HERE,
    "--workpath", os.path.join(HERE, "build"),
    "--specpath", HERE,
    "--add-data", os.path.join(HERE, "conf.yml") + os.pathsep + ".",
    "--add-data", os.path.join(HERE, "icon.png") + os.pathsep + ".",
    # jmcomic 及其依赖链中存在动态导入 / 二进制 / 数据文件，逐项收集
    "--collect-all", "jmcomic",
    "--collect-all", "common",
    "--collect-all", "curl_cffi",
    "--collect-all", "certifi",
    "--collect-all", "img2pdf",
    "--collect-all", "pikepdf",
    # pycryptodome 只需二进制扩展，收集全部子模块会带上庞大的 SelfTest
    "--collect-binaries", "Crypto",
    "--exclude-module", "Crypto.SelfTest",
    # jmcomic 运行时按需（延迟）导入的依赖，静态分析无法发现，需显式声明
    "--hidden-import", "requests",
    "--hidden-import", "typing_extensions",
    "--collect-submodules", "rich",
    "--collect-all", "zhconv",
    # 部分库通过 importlib.metadata 读取版本信息
    "--copy-metadata", "img2pdf",
    "--copy-metadata", "pikepdf",
    "--copy-metadata", "pillow",
    "--copy-metadata", "curl_cffi",
    "--copy-metadata", "certifi",
    "--copy-metadata", "jmcomic",
]

if __name__ == "__main__":
    print("Building %s ..." % EXE_NAME)
    PyInstaller.__main__.run(ARGS)
    exe = os.path.join(HERE, EXE_NAME + ".exe")
    if os.path.isfile(exe):
        print("OK -> %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1024 / 1024))
        sys.exit(0)
    print("FAILED: exe not found")
    sys.exit(1)
