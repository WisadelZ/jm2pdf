# -*- coding: utf-8 -*-
"""在线浏览：把站点上的本子按「逐页取图」暴露出来，接口与 :class:`core.reader.Reader` 一致。

浏览层（``ui.reader_view``）只依赖 ``page_count`` / ``numbered_pages`` / ``name`` /
``page_name`` / ``size`` / ``render`` 这几项，因此在线本子与本地文件可以共用同一套界面：
横竖式切换、左右翻页、分段加载、相邻页预取全部直接复用。

页面按需取：只有浏览到某页时才请求该页图片并解密，取到的尺寸会缓存下来。
"""

import threading

from core import account
from core.downloader import build_option, fetch_page_image, needs_login_to_view

# 还没取到的页按这个尺寸给个占位比例（竖式列宽、横式等比缩放都靠它先排出布局）
DEFAULT_PAGE_SIZE = (1000, 1414)


class OnlineAlbumError(Exception):
    """打不开本子或定位不到页面时抛出，由界面提示用户。"""


def _open(conf, album_id, with_login):
    """建客户端并取本子详情；打不开时抛 OnlineAlbumError。"""
    client = build_option(conf, with_login=with_login).new_jm_client()
    try:
        album = client.get_album_detail(album_id)
    except Exception as exc:
        raise OnlineAlbumError(exc)
    return client, album


class OnlineAlbum:
    """在线本子：按全局页号（跨章节连续编号）逐页取图。"""

    kind = "images"
    numbered_pages = True          # 右下角显示「当前页/总页数」而不是图片名

    def __init__(self, conf, album_id):
        try:
            # 浏览也属于取图流程，默认不带登录态，避免白白消耗下载额度
            self._client, self._album = _open(conf, album_id, with_login=False)
        except OnlineAlbumError as exc:
            cause = exc.args[0] if exc.args else None
            # 只有服务端明确表示本子取不到时才用登录态重试，其余错误直接报错
            if not (needs_login_to_view(cause) and account.is_logged_in()):
                raise
            self._client, self._album = _open(conf, album_id, with_login=True)
        self.album_id = str(album_id)
        self.name = self._album.name
        self.page_count = int(self._album.page_count or 0)
        if not self.page_count:
            raise OnlineAlbumError("这个本子没有可浏览的页面")
        self._lock = threading.Lock()
        self._chapters = {}        # 章节序号 -> JmPhotoDetail（已补全图片 URL）
        self._pages = {}           # 全局页号 -> (章节序号, 章节内页号)
        self._sizes = {}           # 全局页号 -> (宽, 高)

    def page_name(self, index):
        return self.name

    def size(self, index):
        """该页图片的像素尺寸；还没取到该页时先返回占位尺寸。"""
        return self._sizes.get(index, DEFAULT_PAGE_SIZE)

    def render(self, index):
        """取该页图片字节（已解密），只在内存中处理。"""
        chapter, local = self._locate(index)
        page = fetch_page_image(self._client, self._chapter(chapter).getindex(local))
        self._sizes[index] = page["size"]
        return page["data"]

    # ------------------------------------------------------------------
    # 章节 / 页码定位
    # ------------------------------------------------------------------
    def _chapter(self, index):
        """取某一章的详情（含图片 URL）并缓存。

        本子详情里只有章节列表，图片 URL 与各章页数都要再取一次章节详情才有。
        """
        with self._lock:
            chapter = self._chapters.get(index)
        if chapter is None:
            try:
                chapter = self._album[index]
                self._client.check_photo(chapter)
            except Exception as exc:
                raise OnlineAlbumError(exc)
            with self._lock:
                self._chapters[index] = chapter
        return chapter

    def _locate(self, index):
        """把全局页号定位成 (章节序号, 章节内页号)。

        章节详情有缓存，遍历只是累加各章页数，代价很小。
        """
        if not 0 <= index < self.page_count:
            raise OnlineAlbumError("页号超出范围")
        with self._lock:
            known = self._pages.get(index)
        if known is not None:
            return known
        offset = 0
        for chapter in range(len(self._album)):
            count = len(self._chapter(chapter))
            if index < offset + count:
                found = (chapter, index - offset)
                with self._lock:
                    self._pages[index] = found
                return found
            offset += count
        raise OnlineAlbumError("页号超出范围")
