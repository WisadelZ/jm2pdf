# -*- coding: utf-8 -*-
"""探索层：按关键词搜索本子（作品 / 作者 / 标签 / 角色）。

搜索走 jmcomic 的站内搜索接口，库每页最多返回 80 条
（``JmModuleConfig.PAGE_SIZE_SEARCH``），界面自行切分为 20 条一页。
列表项只带 id / name / author / description / category，
页数、章节数、标签等信息需要再调 ``get_album_detail`` 获取。
"""

from core.downloader import build_option

# 搜索方式 -> jmcomic 客户端方法名
SEARCH_MODES = {
    "work": "search_work",        # 作品
    "author": "search_author",    # 作者
    "tag": "search_tag",          # 标签
    "actor": "search_actor",      # 角色
}

DEFAULT_MODE = "work"

# 库每页返回的条数（与 JmModuleConfig.PAGE_SIZE_SEARCH 一致）
LIB_PAGE_SIZE = 80


def new_client(conf):
    """按当前配置创建一个 jmcomic 客户端，可重复使用（内部自带 cookies 与域名缓存）。"""
    return build_option(conf).new_jm_client()


def search(client, mode, keyword, page=1):
    """按指定方式搜索一页，返回 JmSearchPage。

    关键词支持站内语法：``+词`` 必须包含、``-词`` 必须排除。
    搜索纯数字车号时，jmcomic 会自动返回单本结果。
    """
    method = getattr(client, SEARCH_MODES.get(mode, SEARCH_MODES[DEFAULT_MODE]))
    return method(keyword, page)


def to_items(page):
    """把 JmSearchPage 转成界面用的条目列表（不含封面，封面按需另取）。"""
    items = []
    for album_id, info in page.content:
        items.append({
            "id": str(album_id),
            "name": info.get("name") or "",
            "author": info.get("author") or "",
            "cover": None,
        })
    return items
