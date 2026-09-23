# -*- coding: utf-8 -*-
"""浏览支持：把已下载的 PDF 或图片文件夹统一成「逐页取图」。

PDF 由本工具用 img2pdf 生成，每一页就是原图本身（JPEG 直接以 DCTDecode 内嵌），
所以不需要引入 PDF 渲染引擎，用 pikepdf（已是本项目依赖）取出页面里的图片流即可：

- DCTDecode 的流本身就是 JPEG 字节，直接交给界面显示；
- 其它编码（例如内嵌 PNG 产生的 FlateDecode）用 Pillow 解出像素后重新编码成 PNG。

供资源管理器页的内置浏览功能使用。
"""

import io
import os
import re
import threading

import pikepdf
from PIL import Image

# 可浏览的图片后缀：图片文件夹里只挑这些文件
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

# 未压缩像素只处理 8 位深，其它位深不做转换
_BITS_PER_COMPONENT = 8

# PDF 色彩空间 -> Pillow 像素模式
_COLOR_MODES = {
    "/DeviceGray": "L",
    "/DeviceRGB": "RGB",
    "/DeviceCMYK": "CMYK",
}


class ReaderError(Exception):
    """打不开文件或取不出页面时抛出，由界面提示用户。"""


def is_pdf(path):
    """是否是 PDF 文件。"""
    return os.path.isfile(path) and path.lower().endswith(".pdf")


def list_images(folder):
    """列出文件夹里的图片（按名称中的数字自然排序），没有图片时返回空列表。"""
    if not os.path.isdir(folder):
        return []
    names = [name for name in os.listdir(folder)
             if name.lower().endswith(IMAGE_SUFFIXES)]
    return [os.path.join(folder, name) for name in sorted(names, key=_sort_key)]


def _sort_key(name):
    """名称里的数字段按数值比较：1.jpg 排在 10.jpg 前面。"""
    parts = re.split(r"(\d+)", name.lower())
    return [(0, int(part)) if part.isdigit() else (1, part) for part in parts]


class Reader:
    """一次浏览会话：PDF 与图片文件夹统一成「逐页取图」。

    页面索引从 0 开始。``size(index)`` 给出图片的像素尺寸（竖式滚动定位当前页用），
    ``render(index)`` 返回可以直接交给 ``ft.Image`` 的图片字节。
    pikepdf 的 Pdf 对象不是线程安全的，取页时加锁。
    """

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.kind = "pdf" if is_pdf(path) else "images"
        # PDF 每页没有名字，右下角显示「当前页/总页数」；图片文件夹显示文件名
        self.numbered_pages = self.kind == "pdf"
        self._files = []
        self._pdf = None
        self._sizes = {}
        self._lock = threading.Lock()
        if self.kind == "images":
            self._files = list_images(path)
        else:
            try:
                self._pdf = pikepdf.open(path)
            except Exception as exc:
                raise ReaderError(exc)
        if not self.page_count:
            raise ReaderError("文件里没有可显示的页面")

    @property
    def page_count(self):
        return len(self._files) if self.kind == "images" else len(self._pdf.pages)

    def page_name(self, index):
        """当前页的名称：图片是文件名；PDF 用不到（界面显示页码）。"""
        return os.path.basename(self._files[index]) if self.kind == "images" else self.name

    def size(self, index):
        """该页图片的像素尺寸。"""
        cached = self._sizes.get(index)
        if cached is not None:
            return cached
        if self.kind == "images":
            with Image.open(self._files[index]) as image:
                size = image.size
        else:
            with self._lock:
                obj = self._page_image(index)
                size = (int(obj.get("/Width")), int(obj.get("/Height")))
        self._sizes[index] = size
        return size

    def render(self, index):
        """该页的图片字节（JPEG 或 PNG），可直接作为 ``ft.Image`` 的 src。"""
        if self.kind == "images":
            with open(self._files[index], "rb") as file:
                return file.read()
        with self._lock:
            obj = self._page_image(index)
            if str(obj.get("/Filter")) == "/DCTDecode":
                # 内嵌的 JPEG 原图：直接取原始流，不必重新编码，画质与体积都不变
                return bytes(obj.read_raw_bytes())
            return _encode_png(obj)

    def _page_image(self, index):
        """取出该页里的图片对象（本工具生成的 PDF 每页就是一张整页图）。"""
        try:
            page = self._pdf.pages[index]
            resources = page.get("/Resources")
            xobject = resources.get("/XObject") if resources is not None else None
            if xobject is not None:
                for _, obj in xobject.items():
                    if str(obj.get("/Subtype")) == "/Image":
                        return obj
        except ReaderError:
            raise
        except Exception as exc:
            raise ReaderError(exc)
        raise ReaderError("该页没有可显示的图片")


def _encode_png(obj):
    """非 JPEG 内嵌的图片：解码成像素后重新编码为 PNG。"""
    data = bytes(obj.read_bytes())          # pikepdf 按 Filter 解压
    width, height = int(obj.get("/Width")), int(obj.get("/Height"))
    bits = int(obj.get("/BitsPerComponent", 8))
    mode, palette = _pixel_mode(obj.get("/ColorSpace"))
    if mode is None or bits != _BITS_PER_COMPONENT:
        raise ReaderError("不支持的图片编码，无法显示该页")
    image = Image.frombytes(mode, (width, height), data)
    if palette is not None:
        image.putpalette(palette)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _pixel_mode(space):
    """把 PDF 色彩空间映射成 Pillow 像素模式，返回 ``(模式, 调色板或 None)``。"""
    if isinstance(space, pikepdf.Name):
        return _COLOR_MODES.get(str(space)), None
    if isinstance(space, pikepdf.Array) and len(space) >= 2:
        if str(space[0]) == "/Indexed" and len(space) >= 4:
            return "P", bytes(space[3])      # /Indexed [基础空间 上限 调色板]
        return _pixel_mode(space[1])         # ICCBased 等：按基础空间处理
    return None, None
