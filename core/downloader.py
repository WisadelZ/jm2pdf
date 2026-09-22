# -*- coding: utf-8 -*-
"""下载层：把界面配置翻译成 jmcomic 选项，并处理下载产物与邮件推送。"""

import copy
import os
import re
import smtplib
import urllib.request

import jmcomic
import yaml

from core import pdf_metadata
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


def album_url(album_id, domain=SITE_DOMAIN):
    """拼接本子在网站上的链接，便于在界面里跳转查看。"""
    return jmcomic.JmcomicText.format_album_url(str(album_id), domain)


def cover_url(album_id, size=COVER_SIZE):
    """拼接封面图 URL（只拼地址，不下载）。"""
    return jmcomic.JmcomicText.get_album_cover_url(str(album_id), size=size)


def fetch_cover(album_id, size=COVER_SIZE):
    """取封面图字节，供界面控件直接显示（只在内存中，不落盘）；失败返回 None。"""
    try:
        request = urllib.request.Request(cover_url(album_id, size), headers=COVER_HEADERS)
        with urllib.request.urlopen(request, timeout=15) as resp:
            # 不存在的本子会返回 200 + 空响应，这里按失败处理
            return resp.read() or None
    except Exception:      # 封面只是搜索结果的点缀，任何异常都不应影响搜索本身
        return None


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


def build_option(conf):
    """根据界面配置构建 jmcomic Option。

    app 段的下载目录、并发数、登录信息、是否生成 PDF 会覆盖 option 段中的同名项。
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
    username = (app_conf.get("username") or "").strip()
    password = (app_conf.get("password") or "").strip()
    if username and password:
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
