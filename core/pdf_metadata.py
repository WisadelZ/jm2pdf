# -*- coding: utf-8 -*-
"""PDF 元数据：生成 PDF 时把本子资料写进 DocInfo，并提供读回解析。

本模块只处理 PDF 文件，图片文件不做任何改动（不写 EXIF、不写侧车文件、不重新编码）。
模块导入时会向 jmcomic 注册插件，因此必须早于 ``create_option_by_str`` 被导入
（由 ``core.downloader`` 顶部触发）。
"""

import os

import jmcomic
import pikepdf

from core.constants import APP_VERSION

# 插件 key：conf.yml 中 after_photo 的 plugin 项填这个值
PLUGIN_KEY = "jm2pdf_meta_pdf"

# Keywords 里的三段前缀
_KEY_ID = "id"
_KEY_PAGES = "pages"
_KEY_CHAPTER = "chapter"


def build_docinfo(album, photo):
    """把 JmAlbumDetail / JmPhotoDetail 映射为 PDF DocInfo 字段。"""
    docinfo = {
        "title": album.name,
        "author": ", ".join(album.authors or []),
        "creator": "jm2pdf v%s" % APP_VERSION,
        # keywords 必须是 list，且元素内不能有逗号：img2pdf 内部用逗号拼接
        "keywords": [
            "%s:%s" % (_KEY_ID, album.album_id),
            "%s:%d" % (_KEY_PAGES, len(photo)),
            "%s:%d" % (_KEY_CHAPTER, photo.album_index),
        ],
    }
    tags = [str(tag) for tag in (album.tags or [])]
    if tags:
        # tags 为空时整项不传，img2pdf 会跳过 Subject 字段
        docinfo["subject"] = ", ".join(tags)
    return docinfo


def apply_docinfo(pdf_path, docinfo):
    """原地补写 DocInfo（补写后 PDF 页数与体积不变）。"""
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        for key, value in docinfo.items():
            pdf.docinfo["/" + key.capitalize()] = (
                value if isinstance(value, str) else ",".join(value))
        pdf.save(pdf_path)


def read_metadata(pdf_path):
    """读回 PDF 里的漫画元数据，返回界面需要的字段字典。

    如果 PDF 里没有任何本工具写入的元数据则返回 None（例如旧版本生成的 PDF）。
    文件损坏、被加密无法读取等情况会抛出异常，由调用方处理。
    """
    with pikepdf.open(pdf_path) as pdf:
        docinfo = {str(key): value for key, value in dict(pdf.docinfo).items()}
        page_count = len(pdf.pages)

    title = _text(docinfo.get("/Title"))
    author = _text(docinfo.get("/Author"))
    tags = _text(docinfo.get("/Subject"))
    fields = _parse_keywords(_text(docinfo.get("/Keywords")))
    if not any((title, author, tags, fields)):
        return None
    return {
        "title": title,
        "author": author,
        "tags": tags,
        "album_id": fields.get(_KEY_ID, ""),
        "chapter": fields.get(_KEY_CHAPTER, ""),
        # 元数据里没有 pages 时退回 PDF 的实际页数
        "pages": fields.get(_KEY_PAGES) or str(page_count),
    }


def _text(value):
    """把 DocInfo 里的值统一转成去空白的字符串。"""
    return str(value).strip() if value is not None else ""


def _parse_keywords(keywords):
    """解析 ``id:1,pages:2,chapter:3`` 形式的关键字。"""
    fields = {}
    for part in keywords.split(","):
        key, sep, value = part.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


class MetaImg2pdfPlugin(jmcomic.Img2pdfPlugin):
    """继承官方 img2pdf 插件：先正常生成 PDF，再原地补写本子元数据。"""

    plugin_key = PLUGIN_KEY
    plugin_dependencies = ("img2pdf",)

    def invoke(self, photo=None, album=None, downloader=None, pdf_dir=None,
               filename_rule="Pid", dir_rule=None, **kwargs):
        super().invoke(photo=photo, album=album, downloader=downloader, pdf_dir=pdf_dir,
                       filename_rule=filename_rule, dir_rule=dir_rule, **kwargs)

        # 本插件只用于 after_photo；album 模式下 photo 为 None，不做处理
        if photo is None:
            return
        try:
            # 与父类 invoke 用的是同一套参数，算出的路径完全一致
            pdf_path = self.decide_filepath(album, photo, filename_rule, "pdf", pdf_dir, dir_rule)
            if os.path.isfile(pdf_path):
                apply_docinfo(pdf_path, build_docinfo(photo.from_album, photo))
        except Exception as exc:      # 元数据写入失败不能影响下载主流程
            self.log("写入 PDF 元数据失败：%s" % exc, "error")


jmcomic.JmModuleConfig.register_plugin(MetaImg2pdfPlugin)
