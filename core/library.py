# -*- coding: utf-8 -*-
"""下载目录管理：扫描分组、搜索过滤、排序、系统打开、删除到回收站。

供资源管理器页使用。扫描只遍历下载目录的第一层：本子 PDF 与其图片文件夹
都直接位于该层下（由 ``dir_rule`` 决定）。

过滤与排序都在扫描结果上做纯内存运算，不重新读盘；只有按作者 / 标签 /
本子 ID 搜索或按页数排序时才需要读 PDF 元数据（由界面按需触发并缓存，
见 :func:`read_pdf_info`）。
"""

import ctypes
import os
from ctypes import wintypes

from core import pdf_metadata

PDF_SUFFIX = ".pdf"

# 搜索方式：名称按文件 / 文件夹名匹配，其余四种按 PDF 元数据匹配
SEARCH_MODES = ("all", "name", "author", "tag", "id")
DEFAULT_SEARCH_MODE = "all"

# 需要读 PDF 元数据的搜索方式（只有「名称」不需要）
_META_MODES = ("all", "author", "tag", "id")

# 排序字段与各自的默认方向（名称升序，其余降序更符合直觉）
SORT_KEYS = ("name", "time", "size", "pages")
DEFAULT_SORT_KEY = "name"
SORT_DESC_DEFAULT = {"name": False, "time": True, "size": True, "pages": True}

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


def _folder_size(path):
    """统计文件夹第一层内所有文件的大小合计（不递归，避免大目录扫描过慢）。"""
    total = 0
    try:
        with os.scandir(path) as children:
            for child in children:
                try:
                    if child.is_file():
                        total += child.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def scan_library(base_dir):
    """扫描下载目录，把同名的 PDF 与图片文件夹归为同一本漫画。

    返回列表，每项形如 ``{"name": 名称, "pdf": PDF 绝对路径或空串,
    "folder": 图片文件夹绝对路径或空串, "size": 占用字节数,
    "mtime": 最近修改时间}``，按名称不区分大小写排序。
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
        entry = entries.setdefault(
            name, {"name": name, "pdf": "", "folder": "", "size": 0, "mtime": 0.0})
        if item.is_dir():
            entry["folder"] = item.path
            entry["size"] += _folder_size(item.path)
        else:
            entry["pdf"] = item.path
            try:
                entry["size"] += item.stat().st_size
            except OSError:
                pass
        try:
            entry["mtime"] = max(entry["mtime"], item.stat().st_mtime)
        except OSError:
            pass
    return sorted(entries.values(), key=lambda entry: entry["name"].lower())


def mode_needs_metadata(mode):
    """该搜索方式是否需要 PDF 元数据（不需要时界面省掉一次读盘）。"""
    return mode in _META_MODES


def read_pdf_info(pdf_path):
    """读取一个 PDF 里的漫画资料，供搜索与排序使用；读不到返回 None。

    返回 ``{"title", "author", "tags", "album_id", "pages"}``，其中 pages 为
    int 或 None（旧版本生成的 PDF 没有元数据、文件损坏等都会走到 None）。
    """
    if not pdf_path:
        return None
    try:
        meta = pdf_metadata.read_metadata(pdf_path)
    except Exception:      # 读元数据只是锦上添花，任何异常都不应影响列表展示
        return None
    if not meta:
        return None
    pages = str(meta.get("pages") or "").strip()
    return {
        "title": meta.get("title") or "",
        "author": meta.get("author") or "",
        "tags": meta.get("tags") or "",
        "album_id": meta.get("album_id") or "",
        "pages": int(pages) if pages.isdigit() else None,
    }


def _matches(entry, text, mode, info):
    """判断一条扫描结果是否命中关键词；text 已转为小写。"""
    name = (entry.get("name") or "").casefold()
    if mode == "name":
        return text in name
    meta = info.get(entry.get("pdf") or "") or {}
    fields = {
        "title": (meta.get("title") or "").casefold(),
        "author": (meta.get("author") or "").casefold(),
        "tags": (meta.get("tags") or "").casefold(),
        "album_id": (meta.get("album_id") or "").casefold(),
    }
    if mode == "author":
        return text in fields["author"]
    if mode == "tag":
        return text in fields["tags"]
    if mode == "id":
        return text in fields["album_id"]
    # 全部：名称 + 元数据各项，任一命中即可
    return any(text in value for value in [name] + list(fields.values()))


def filter_entries(entries, keyword, mode=DEFAULT_SEARCH_MODE, info=None):
    """按关键词与搜索方式过滤扫描结果；info 为 ``{PDF 路径: read_pdf_info 结果}``。"""
    text = (keyword or "").strip().casefold()
    if not text:
        return list(entries)
    info = info or {}
    return [entry for entry in entries if _matches(entry, text, mode, info)]


def sort_entries(entries, key=DEFAULT_SORT_KEY, desc=None, info=None):
    """在内存里排序扫描结果；页数取不到（非 PDF / 无元数据）的排到末尾。

    ``desc`` 为 None 时按该字段的默认方向排（见 :data:`SORT_DESC_DEFAULT`）。
    """
    if key not in SORT_KEYS:
        key = DEFAULT_SORT_KEY
    if desc is None:
        desc = SORT_DESC_DEFAULT[key]
    if key == "name":
        return sorted(entries, key=lambda entry: entry["name"].casefold(), reverse=desc)
    if key in ("time", "size"):
        return sorted(entries, key=lambda entry: entry.get(key) or 0, reverse=desc)
    # 页数：先把取不到页数的挑出来，避免它们按 0 混进正常排序里
    info = info or {}

    def pages_of(entry):
        pages = (info.get(entry.get("pdf") or "") or {}).get("pages")
        return pages if isinstance(pages, int) else None

    known = sorted((e for e in entries if pages_of(e) is not None),
                   key=pages_of, reverse=desc)
    return known + [e for e in entries if pages_of(e) is None]


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
