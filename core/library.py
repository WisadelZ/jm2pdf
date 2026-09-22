# -*- coding: utf-8 -*-
"""下载目录管理：扫描分组、系统打开、删除到回收站。

供资源管理器页使用。扫描只遍历下载目录的第一层：本子 PDF 与其图片文件夹
都直接位于该层下（由 ``dir_rule`` 决定）。
"""

import ctypes
import os
from ctypes import wintypes

PDF_SUFFIX = ".pdf"

# SHFileOperationW 的常量
_FO_DELETE = 3
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040          # 关键：移入回收站而不是直接删除
_FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    """Windows Shell 文件操作结构体（仅用到删除相关字段）。"""

    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def scan_library(base_dir):
    """扫描下载目录，把同名的 PDF 与图片文件夹归为同一本漫画。

    返回列表，每项形如 ``{"name": 名称, "pdf": PDF 绝对路径或空串,
    "folder": 图片文件夹绝对路径或空串}``，按名称不区分大小写排序。
    """
    entries = {}
    if not os.path.isdir(base_dir):
        return []
    for item in os.scandir(base_dir):
        name = None
        if item.is_dir():
            name = item.name
        elif item.is_file() and item.name.lower().endswith(PDF_SUFFIX):
            name = item.name[: -len(PDF_SUFFIX)]
        if name is None:
            continue
        entry = entries.setdefault(name, {"name": name, "pdf": "", "folder": ""})
        entry["folder" if item.is_dir() else "pdf"] = item.path
    return sorted(entries.values(), key=lambda entry: entry["name"].lower())


def open_path(path):
    """用系统默认方式打开文件或文件夹（文件夹会打开资源管理器）。"""
    os.startfile(path)


def delete_to_recycle_bin(paths):
    """把文件 / 文件夹移入回收站，可从回收站恢复。

    删除失败时抛出 OSError，由调用方提示用户。
    """
    targets = [os.path.abspath(path) for path in paths]
    if not targets:
        return
    # pFrom 要求多个路径以 \0 分隔、整体再以 \0\0 结尾
    operation = _SHFILEOPSTRUCTW()
    operation.wFunc = _FO_DELETE
    operation.pFrom = "\0".join(targets) + "\0\0"
    operation.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError("系统删除接口返回错误码 %d" % result)
    if operation.fAnyOperationsAborted:
        raise OSError("删除操作被中断")
