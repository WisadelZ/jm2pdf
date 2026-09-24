# -*- coding: utf-8 -*-
"""下载层：把界面配置翻译成 jmcomic 选项，并处理下载产物与邮件推送。"""

import copy
import io
import os
import re
import smtplib
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import jmcomic
import yaml
from PIL import Image

from core import account, pdf_metadata, progress_plugin  # noqa: F401  (导入即注册插件)
from core.config import resolve_path
from utils.helpers import clamp

# 本子网页链接固定使用 18comic.vip：其余镜像域名只支持下载，浏览器直接访问会被拦截
SITE_DOMAIN = "18comic.vip"

# dir_rule 未配置时的兜底规则（与 jmcomic 默认一致：图片存放在 base_dir/<章节名>）
DEFAULT_FILENAME_RULE = "Pname"

# PDF 插件 key：本工具插件会把元数据写进 PDF；img2pdf 为旧配置里的 key，一并识别并替换
PDF_PLUGIN_KEYS = (pdf_metadata.PLUGIN_KEY, "img2pdf")

# 封面缩略图尺寸后缀：与网站搜索列表一致，3:4 竖版
COVER_SIZE = "_3x4"

# 图片 CDN 会拒绝空 User-Agent（返回 403），取图时显式带一个
COVER_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 批量取封面图时的并发线程数
COVER_WORKERS = 8

# 详情页「预览前 5 页」最多取几张
PREVIEW_LIMIT = 5

# 预览图重新编码时的 JPEG 质量（站点图片本身是打乱的，必须重排后重编码）
PREVIEW_QUALITY = 92


def album_url(album_id, domain=SITE_DOMAIN):
    """拼接本子在网站上的链接，便于在界面里跳转查看。"""
    return jmcomic.JmcomicText.format_album_url(str(album_id), domain)


def cover_url(album_id, size=COVER_SIZE):
    """拼接封面图 URL（只拼地址，不下载）。"""
    return jmcomic.JmcomicText.get_album_cover_url(str(album_id), size=size)


def fetch_image_bytes(url):
    """按 URL 取图片字节，供界面控件直接显示（只在内存中，不落盘）；失败返回 None。"""
    if not url:
        return None
    try:
        request = urllib.request.Request(url, headers=COVER_HEADERS)
        with urllib.request.urlopen(request, timeout=15) as resp:
            # 不存在的资源会返回 200 + 空响应，这里按失败处理
            return resp.read() or None
    except Exception:      # 图片只是界面的点缀，任何异常都不应影响主流程
        return None


def fetch_cover(album_id, size=COVER_SIZE):
    """取封面图字节，供界面控件直接显示（只在内存中，不落盘）；失败返回 None。"""
    return fetch_image_bytes(cover_url(album_id, size))


def fetch_covers(items, workers=COVER_WORKERS):
    """并发给条目列表补上封面字节（只在内存中，不落盘）；取不到的项保持 None。"""
    pending = [item for item in items if not item.get("cover")]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        covers = list(pool.map(lambda item: fetch_cover(item["id"]), pending))
    for item, cover in zip(pending, covers):
        item["cover"] = cover


def needs_login_to_view(error):
    """服务端是否明确表示「本子取不到」——这种本子可能只对登录用户可见。

    这是唯一值得用登录态重试的情况；网络抖动等其它错误一律交给用户重试，
    避免无谓地消耗下载额度。
    """
    return isinstance(error, jmcomic.MissingAlbumPhotoException)


def fetch_preview_images(conf, album_id, limit=PREVIEW_LIMIT):
    """取本子第一话的前几页图片，供详情页预览。

    返回 ``[{"data": 图片字节, "size": (宽, 高)}, ...]``；站点上的图片是打乱存放的，
    这里按 jmcomic 的分条规则还原（未打乱的直接用原始字节），全程只在内存中处理。
    单页取不到就跳过，一页都没取到时抛出异常，由调用方提示。

    预览属于取图流程，默认不带登录态，避免白白消耗下载额度；只有服务端明确
    表示本子取不到时，才用登录态再试一次。
    """
    try:
        return _fetch_preview_images(conf, album_id, limit, with_login=False)
    except Exception as exc:
        if not (needs_login_to_view(exc) and account.is_logged_in()):
            raise
    return _fetch_preview_images(conf, album_id, limit, with_login=True)


def _fetch_preview_images(conf, album_id, limit, with_login):
    client = build_option(conf, with_login=with_login).new_jm_client()
    photo = client.get_album_detail(album_id)[0]
    client.check_photo(photo)              # 补全图片 URL 等信息
    pages = []
    error = None
    for index in range(min(limit, len(photo))):
        try:
            pages.append(fetch_page_image(client, photo.getindex(index)))
        except Exception as exc:           # 个别页失败不影响其余几页
            error = exc
    if not pages:
        raise error if error is not None else ValueError("没有取到预览图片")
    return pages


def fetch_page_image(client, detail):
    """取一页图片并解密，返回 ``{"data": 字节, "size": (宽, 高)}``。

    供详情页预览与在线浏览共用；只在内存中处理，不落盘。
    """
    content = client.get_jm_image(detail.download_url).content
    if not content:
        raise ValueError("图片响应为空")
    num = jmcomic.JmImageTool.get_num_by_url(detail.scramble_id, detail.img_url)
    if num == 0:
        # 未打乱的图：原始字节就能直接显示，不必重新编码
        return {"data": content, "size": _image_size(content)}
    image = _decode_image(content, num)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=PREVIEW_QUALITY)
    return {"data": buffer.getvalue(), "size": image.size}


def _decode_image(content, num):
    """按 jmcomic 的分条规则把打乱的图片还原（与 JmImageTool.decode_and_save 一致）。"""
    source = jmcomic.JmImageTool.open_image(content)
    width, height = source.size
    target = Image.new("RGB", (width, height))
    over = height % num
    for i in range(num):
        move = height // num
        y_src = height - (move * (i + 1)) - over
        y_dst = move * i
        if i == 0:
            move += over
        else:
            y_dst += over
        target.paste(source.crop((0, y_src, width, y_src + move)),
                     (0, y_dst, width, y_dst + move))
    return target


def _image_size(content):
    """读出图片像素尺寸；读不出来时给一个竖版的兜底尺寸。"""
    try:
        return jmcomic.JmImageTool.open_image(content).size
    except Exception:
        return (1000, 1400)


def pdf_filename_rule(dir_rule_dsl):
    """由下载目录规则推导 PDF 文件名规则，取目录规则的最后一段。

    dir_rule 的最后一段就是图片文件夹的名字，PDF 用同一规则命名后，
    按名称排序时 PDF 与其图片文件夹会紧挨在一起。
    """
    segments = [seg.strip() for seg in re.split(r"[/_]", (dir_rule_dsl or "").strip())]
    segments = [seg for seg in segments if seg]
    if not segments or segments[-1] == "Bd":
        return DEFAULT_FILENAME_RULE
    return segments[-1]


def build_option(conf, with_login=True, progress=False):
    """根据界面配置构建 jmcomic Option。

    app 段的下载目录、并发数、是否生成 PDF 会覆盖 option 段中的同名项；
    登录信息由 :mod:`core.account` 加密保存，``with_login=True`` 时取运行时凭据
    注入登录插件（读元数据、收藏等需要身份的场景）。

    ``with_login=False`` 用于取图流程（下载 / 预览 / 在线浏览）：站点会按登录
    身份统计下载额度，因此这些流程默认不带登录态，只有本子确实需要登录时才改用它。

    ``progress=True`` 时额外注入 :mod:`core.progress_plugin` 的进度插件
    （任务队列用它统计每个任务的页数进度）。
    """
    app_conf = conf.get("app") or {}
    download_dir = resolve_path(app_conf.get("download_dir"))
    data = copy.deepcopy(conf.get("option") or {})

    threading_conf = data.setdefault("download", {}).setdefault("threading", {})
    threading_conf["image"] = clamp(app_conf.get("thread_image", 30), 1, 50)
    threading_conf["photo"] = clamp(app_conf.get("thread_photo", 16), 1, 64)

    dir_rule = data.setdefault("dir_rule", {})
    dir_rule["base_dir"] = download_dir
    # PDF 文件名跟随图片文件夹名（取 dir_rule 最后一段），便于按名称归在一起
    filename_rule = pdf_filename_rule(dir_rule.get("rule"))

    plugins = data.setdefault("plugins", {})
    if progress:
        for group, key in progress_plugin.PLUGIN_KEYS.items():
            plugins.setdefault(group, []).append({"plugin": key, "kwargs": {}})
    username, password = account.get_credentials()
    if with_login and username and password:
        plugins.setdefault("after_init", []).insert(0, {
            "plugin": "login",
            "kwargs": {"username": username, "password": password},
        })

    after_photo = plugins.setdefault("after_photo", [])
    if app_conf.get("to_pdf", True):
        for item in after_photo:
            if isinstance(item, dict) and item.get("plugin") in PDF_PLUGIN_KEYS:
                # 旧配置里的 img2pdf 一并改写成带元数据的插件
                item["plugin"] = pdf_metadata.PLUGIN_KEY
                kwargs = item.setdefault("kwargs", {})
                kwargs["pdf_dir"] = download_dir
                kwargs["filename_rule"] = filename_rule
                break
        else:
            after_photo.append({
                "plugin": pdf_metadata.PLUGIN_KEY,
                "kwargs": {"pdf_dir": download_dir, "filename_rule": filename_rule},
            })
    else:
        plugins["after_photo"] = [
            item for item in after_photo
            if not (isinstance(item, dict) and item.get("plugin") in PDF_PLUGIN_KEYS)
        ]
    return jmcomic.create_option_by_str(yaml.safe_dump(data, allow_unicode=True))


def collect_pdfs(result):
    """从下载结果中收集实际存在的 PDF 路径（去重）。"""
    items = list(result) if hasattr(result, "__iter__") and not isinstance(result, tuple) else [result]
    pdfs = []
    for item in items:
        try:
            pdfs.extend(item.manifest.export_filepath_dict.get("pdf", []))
        except Exception:
            continue
    return [p for p in dict.fromkeys(pdfs) if os.path.isfile(p)]


def send_mail(cfg, files, log, t):
    """把指定文件作为附件发送邮件；log 为日志回调，t 为多语言取值函数。"""
    from email import encoders
    from email.header import Header
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender = cfg["sender"]
    receiver = cfg.get("receiver") or sender
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = Header(cfg.get("subject") or "downloaded comic", "utf-8")
    msg.attach(MIMEText(cfg.get("body") or "jmcomic download successfully.", "plain", "utf-8"))

    for path in files:
        try:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
        except OSError as e:
            log(t("log_attach_failed", path=path, error=e))
            continue
        part.add_header("Content-Disposition", "attachment",
                        filename=Header(os.path.basename(path), "utf-8").encode())
        encoders.encode_base64(part)
        msg.attach(part)
        log(t("log_attach_added", name=os.path.basename(path)))

    port = clamp(cfg.get("port", 465), 1, 65535)
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["server"], port, timeout=60)
    else:
        server = smtplib.SMTP(cfg["server"], port, timeout=60)
        server.starttls()
    with server:
        server.login(sender, cfg["password"])
        server.sendmail(sender, receiver, msg.as_string())
