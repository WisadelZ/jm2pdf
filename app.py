# -*- coding: utf-8 -*-
"""
Jm2PDF v2.0.0 - 禁漫本子下载工具（Flet UI）

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

Unauthorized modification, distribution of modified versions,
or commercial use is strictly prohibited.
"""

import copy
import logging
import os
import re
import smtplib
import sys
import threading
import traceback

# 以无控制台方式打包时 sys.stdout / sys.stderr 可能为 None，先做兜底
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import yaml
import flet as ft
import jmcomic

APP_NAME = "jm2pdf"
APP_VERSION = "2.0.0"
APP_TITLE = "%s v%s - 本子下载转 PDF" % (APP_NAME, APP_VERSION)
CONF_FILENAME = "conf.yml"

CONF_HEADER = """# Jm2PDF 配置文件
# 界面中的任何修改都会自动同步保存到本文件；也可手动编辑后重启程序生效。
# 相对路径基于程序（exe）所在目录解析。

"""

DEFAULT_CONF_TEXT = """
version: 2.0.0
app:
  download_dir: ./download
  to_pdf: true
  thread_image: 30
  thread_photo: 16
  username: ''
  password: ''
mail:
  enable: false
  server: smtp.qq.com
  port: 465
  sender: ''
  password: ''
  receiver: ''
  subject: downloaded comic
  body: jmcomic download successfully.
option:
  log: true
  download:
    image:
      suffix: .jpg
  dir_rule:
    base_dir: ./download
  plugins:
    after_photo:
      - plugin: img2pdf
        kwargs:
          pdf_dir: ./download
          filename_rule: Pid
"""


# --------------------------------------------------------------------------
# 路径与配置工具
# --------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    return getattr(sys, "_MEIPASS", app_dir())


def conf_path():
    return os.path.join(app_dir(), CONF_FILENAME)


def resolve_path(path):
    path = (path or "").strip()
    if not path:
        path = "download"
    if not os.path.isabs(path):
        path = os.path.join(app_dir(), path)
    return os.path.normpath(path)


def clamp(value, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def parse_ids(text):
    tokens = [t for t in re.split(r"[\s,;，；、]+", text or "") if t]
    seen, result = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _deep_merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def ensure_conf_file():
    path = conf_path()
    if os.path.isfile(path):
        return path
    text = None
    bundled = os.path.join(bundle_dir(), CONF_FILENAME)
    if os.path.isfile(bundled):
        try:
            with open(bundled, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = None
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text else CONF_HEADER + yaml.safe_dump(
                yaml.safe_load(DEFAULT_CONF_TEXT), allow_unicode=True, sort_keys=False))
    except OSError:
        pass
    return path


def load_conf():
    defaults = yaml.safe_load(DEFAULT_CONF_TEXT)
    path = ensure_conf_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return _deep_merge(defaults, data)


def save_conf(conf):
    conf = copy.deepcopy(conf)
    conf["version"] = APP_VERSION
    text = CONF_HEADER + yaml.safe_dump(
        conf, allow_unicode=True, sort_keys=False, default_flow_style=False)
    with open(conf_path(), "w", encoding="utf-8") as f:
        f.write(text)


# --------------------------------------------------------------------------
# jmcomic 选项构建 / 下载结果 / 邮件
# --------------------------------------------------------------------------
def build_option(conf):
    app_conf = conf.get("app") or {}
    download_dir = resolve_path(app_conf.get("download_dir"))
    data = copy.deepcopy(conf.get("option") or {})
    threading_conf = data.setdefault("download", {}).setdefault("threading", {})
    threading_conf["image"] = clamp(app_conf.get("thread_image", 30), 1, 50)
    threading_conf["photo"] = clamp(app_conf.get("thread_photo", 16), 1, 64)
    data.setdefault("dir_rule", {})["base_dir"] = download_dir
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
            if isinstance(item, dict) and item.get("plugin") == "img2pdf":
                item.setdefault("kwargs", {})["pdf_dir"] = download_dir
                break
        else:
            after_photo.append({
                "plugin": "img2pdf",
                "kwargs": {"pdf_dir": download_dir, "filename_rule": "Pid"},
            })
    else:
        plugins["after_photo"] = [
            item for item in after_photo
            if not (isinstance(item, dict) and item.get("plugin") == "img2pdf")
        ]
    return jmcomic.create_option_by_str(yaml.safe_dump(data, allow_unicode=True))


def collect_pdfs(result):
    items = list(result) if hasattr(result, "__iter__") and not isinstance(result, tuple) else [result]
    pdfs = []
    for item in items:
        try:
            pdfs.extend(item.manifest.export_filepath_dict.get("pdf", []))
        except Exception:
            continue
    return [p for p in dict.fromkeys(pdfs) if os.path.isfile(p)]


def send_mail(cfg, files, log):
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
            log("警告：附件 %s 读取失败，已跳过（%s）" % (path, e))
            continue
        part.add_header("Content-Disposition", "attachment",
                        filename=Header(os.path.basename(path), "utf-8").encode())
        encoders.encode_base64(part)
        msg.attach(part)
        log("已添加附件：%s" % os.path.basename(path))
    port = clamp(cfg.get("port", 465), 1, 65535)
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["server"], port, timeout=60)
    else:
        server = smtplib.SMTP(cfg["server"], port, timeout=60)
        server.starttls()
    with server:
        server.login(sender, cfg["password"])
        server.sendmail(sender, receiver, msg.as_string())


# --------------------------------------------------------------------------
# 日志桥接
# --------------------------------------------------------------------------
class _UiLogHandler(logging.Handler):
    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def emit(self, record):
        try:
            self._sink(self.format(record))
        except Exception:
            pass


# --------------------------------------------------------------------------
# 主界面
# --------------------------------------------------------------------------
class Jm2PdfUI:
    SAVE_DELAY = 0.5
    COLOR_OK = "#27ae60"
    COLOR_ERR = "#c0392b"
    COLOR_IDLE = "#666666"

    def __init__(self, page: ft.Page):
        self.page = page
        self.conf = load_conf()
        self.running = False
        self.searching = False
        self.searched_id = ""
        self._save_timer = None

        page.title = APP_TITLE
        page.window.width = 660
        page.window.height = 700
        page.window.min_width = 540
        page.window.min_height = 520
        page.window.resizable = True
        page.padding = 12
        page.theme_mode = ft.ThemeMode.LIGHT

        app_conf = self.conf["app"]
        mail_conf = self.conf["mail"]

        # ---- 下载任务 ----
        self.ids_field = ft.TextField(
            label="本子 ID", hint_text="多个 ID 用逗号或空格分隔", expand=True)
        self.btn_clear_ids = ft.Button("清空", on_click=self._on_clear_ids)

        self.dir_field = ft.TextField(
            label="下载目录", expand=True,
            value=str(app_conf.get("download_dir") or "./download"),
            on_change=self._on_conf_change)
        self.btn_browse = ft.Button("浏览", on_click=self._on_browse)

        # ---- 搜索 ----
        self.search_field = ft.TextField(
            label="搜索 ID", expand=True, on_submit=lambda e: self.do_search())
        self.btn_search = ft.Button("搜索", on_click=lambda e: self.do_search())

        self.result_text = ft.Text("", selectable=True, size=12)
        self.result_box = ft.Container(
            content=ft.ListView(controls=[self.result_text], padding=6, expand=True),
            border=ft.Border.all(1, "#cccccc"), border_radius=6,
            bgcolor="#fafafa", height=96, expand=True, padding=2)
        self.btn_add = ft.Button("添加", on_click=lambda e: self.add_searched(), disabled=True)

        # ---- 操作行：PDF 开关 + 开始下载 + 状态 + 进度 ----
        self.to_pdf_switch = ft.Switch(
            label="生成 PDF", value=bool(app_conf.get("to_pdf", True)),
            on_change=self._on_conf_change)
        self.btn_start = ft.Button("开始下载", on_click=lambda e: self.start())
        self.status_text = ft.Text("就绪", size=12, color=self.COLOR_IDLE, expand=True)
        self.progress = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=3)

        # ---- 下载选项（折叠）----
        self.thread_image_field = ft.TextField(
            label="图片并发", width=100,
            value=str(clamp(app_conf.get("thread_image", 30), 1, 50)),
            on_change=self._on_conf_change)
        self.thread_photo_field = ft.TextField(
            label="章节并发", width=100,
            value=str(clamp(app_conf.get("thread_photo", 16), 1, 64)),
            on_change=self._on_conf_change)
        self.username_field = ft.TextField(
            label="账号（可选）", expand=True, value=app_conf.get("username") or "",
            on_change=self._on_conf_change)
        self.password_field = ft.TextField(
            label="密码", expand=True, password=True,
            value=app_conf.get("password") or "", on_change=self._on_conf_change)

        opt_tile = ft.ExpansionTile(
            title=ft.Text("下载选项"),
            controls=[ft.Column([
                ft.Row([self.thread_image_field, self.thread_photo_field], spacing=16),
                ft.Row([self.username_field, self.password_field], spacing=16),
            ], spacing=14)],
            controls_padding=ft.Padding.only(left=8, right=8, top=14, bottom=8),
        )

        # ---- 邮件推送（折叠）----
        self.mail_enable_switch = ft.Switch(
            label="启用邮件推送", value=bool(mail_conf.get("enable", False)),
            on_change=self._on_conf_change)
        self.mail_server_field = ft.TextField(
            label="服务器", expand=True, value=mail_conf.get("server") or "smtp.qq.com",
            on_change=self._on_conf_change)
        self.mail_port_field = ft.TextField(
            label="端口", width=80, value=str(mail_conf.get("port", 465)),
            on_change=self._on_conf_change)
        self.mail_sender_field = ft.TextField(
            label="发件邮箱", expand=True, value=mail_conf.get("sender") or "",
            on_change=self._on_conf_change)
        self.mail_password_field = ft.TextField(
            label="授权码", expand=True, password=True,
            value=mail_conf.get("password") or "", on_change=self._on_conf_change)
        self.mail_receiver_field = ft.TextField(
            label="收件邮箱（留空则发给自己）", expand=True,
            value=mail_conf.get("receiver") or "", on_change=self._on_conf_change)
        self.mail_subject_field = ft.TextField(
            label="邮件标题", expand=True, value=mail_conf.get("subject") or "",
            on_change=self._on_conf_change)
        self.mail_body_field = ft.TextField(
            label="邮件正文", expand=True, value=mail_conf.get("body") or "",
            on_change=self._on_conf_change)

        mail_tile = ft.ExpansionTile(
            title=ft.Text("邮件推送"),
            controls=[ft.Column([
                self.mail_enable_switch,
                ft.Row([self.mail_server_field, self.mail_port_field], spacing=10),
                ft.Row([self.mail_sender_field, self.mail_password_field], spacing=10),
                self.mail_receiver_field,
                self.mail_subject_field,
                self.mail_body_field,
            ], spacing=14)],
            controls_padding=ft.Padding.only(left=8, right=8, top=14, bottom=8),
        )

        # ---- 日志 ----
        self.log_list = ft.ListView(expand=True, auto_scroll=True, padding=6, spacing=2)
        self.log_box = ft.Container(
            content=self.log_list, border=ft.Border.all(1, "#333333"),
            border_radius=6, bgcolor="#1e1e1e", height=200, padding=2)

        # ---- 目录选择器（Flet 1.0 中 FilePicker 为 service，需注册到 page.services）----
        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        # 表单区可滚动：展开折叠面板时内容超出窗口高度时出现右侧滚动条，
        # 无需手动拉高窗口；spacing 加大避免输入框标签与上一个输入框贴在一起
        form_col = ft.Column([
            ft.Row([self.ids_field, self.btn_clear_ids], spacing=8),
            ft.Row([self.dir_field, self.btn_browse], spacing=8),
            ft.Row([self.search_field, self.btn_search], spacing=8),
            ft.Row([self.result_box, self.btn_add], spacing=8),
            ft.Row([self.to_pdf_switch, self.btn_start, self.status_text, self.progress],
                   spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            opt_tile,
            mail_tile,
        ], scroll=ft.ScrollMode.AUTO, spacing=18, expand=True)

        page.add(ft.Column([form_col, self.log_box], expand=True, spacing=10))

        handler = _UiLogHandler(self.append_log)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger = logging.getLogger("jmcomic")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    # ------------------------------ 工具 ------------------------------
    def _update(self):
        try:
            self.page.update()
        except Exception:
            pass

    def _set_status(self, text, color=None):
        self.status_text.value = text
        self.status_text.color = color or self.COLOR_IDLE
        self._update()

    @staticmethod
    def _field_int(field, default):
        try:
            return int(str(field.value).strip())
        except (TypeError, ValueError):
            return default

    def append_log(self, message):
        try:
            self.log_list.controls.append(
                ft.Text(message, size=11, color="#dcdcdc", selectable=True))
            if len(self.log_list.controls) > 500:
                del self.log_list.controls[0:len(self.log_list.controls) - 500]
            self._update()
        except Exception:
            pass

    # ------------------------------ 配置同步 ------------------------------
    def _on_conf_change(self, e=None):
        self._sync_conf_from_ui()
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self.SAVE_DELAY, self._flush_conf)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _sync_conf_from_ui(self):
        self.conf["app"] = {
            "download_dir": (self.dir_field.value or "").strip() or "./download",
            "to_pdf": bool(self.to_pdf_switch.value),
            "thread_image": self._field_int(self.thread_image_field, 30),
            "thread_photo": self._field_int(self.thread_photo_field, 16),
            "username": self.username_field.value or "",
            "password": self.password_field.value or "",
        }
        self.conf["mail"] = {
            "enable": bool(self.mail_enable_switch.value),
            "server": (self.mail_server_field.value or "").strip() or "smtp.qq.com",
            "port": self._field_int(self.mail_port_field, 465),
            "sender": (self.mail_sender_field.value or "").strip(),
            "password": self.mail_password_field.value or "",
            "receiver": (self.mail_receiver_field.value or "").strip(),
            "subject": self.mail_subject_field.value or "",
            "body": self.mail_body_field.value or "",
        }

    def _flush_conf(self):
        self._save_timer = None
        try:
            save_conf(self.conf)
        except OSError as exc:
            self._set_status("配置保存失败：%s" % exc, self.COLOR_ERR)

    # ------------------------------ 交互 ------------------------------
    def _on_clear_ids(self, e):
        self.ids_field.value = ""
        self._update()

    async def _on_browse(self, e):
        # Flet 1.0: get_directory_path 为异步方法，直接返回所选路径
        path = await self.picker.get_directory_path(dialog_title="选择下载目录")
        if path:
            self.dir_field.value = os.path.normpath(path)
            self._on_conf_change()

    # ------------------------------ 搜索 ------------------------------
    def do_search(self):
        if self.searching:
            return
        aid = (self.search_field.value or "").strip()
        if not aid:
            self._set_status("请先在搜索框中输入本子 ID", self.COLOR_ERR)
            return
        self.searching = True
        self.btn_search.disabled = True
        self.btn_add.disabled = True
        self.result_text.value = ""
        self.searched_id = ""
        self._set_status("搜索中...")
        self.page.run_thread(self._search_worker, aid)

    def _search_worker(self, aid):
        try:
            self._sync_conf_from_ui()
            option = build_option(self.conf)
            client = option.new_jm_client()
            detail = client.get_album_detail(aid)
            tags = ""
            try:
                tag_list = getattr(detail, "tags", None) or []
                if isinstance(tag_list, dict):
                    flat = []
                    for v in tag_list.values():
                        flat.extend(v if isinstance(v, list) else [v])
                    tag_list = flat
                tags = ", ".join(str(t) for t in list(tag_list)[:10])
                if len(tag_list) > 10:
                    tags += " ..."
            except Exception:
                tags = ""
            text = "ID: %s\n页数: %s / 章节: %d\n名称: %s" % (
                detail.id, detail.page_count, len(detail), detail.title)
            if tags:
                text += "\n标签: %s" % tags
            ok, searched = True, str(detail.id)
        except Exception as exc:
            text, ok, searched = "搜索失败：%s" % exc, False, ""
        self.searching = False
        self.btn_search.disabled = False
        self.btn_add.disabled = not ok
        self.result_text.value = text
        self.searched_id = searched
        self._set_status("搜索完成" if ok else "搜索失败",
                         self.COLOR_OK if ok else self.COLOR_ERR)
        self.append_log("搜索结果：%s" % text.replace("\n", " | "))

    def add_searched(self):
        aid = self.searched_id
        if not aid:
            self._set_status("没有可添加的搜索结果，请先搜索", self.COLOR_ERR)
            return
        ids = parse_ids(self.ids_field.value)
        if aid in ids:
            self._set_status("ID %s 已在列表中" % aid)
            return
        ids.append(aid)
        self.ids_field.value = ", ".join(ids)
        self._set_status("已添加 %s 到下载列表" % aid, self.COLOR_OK)

    # ------------------------------ 下载 ------------------------------
    def start(self):
        if self.running:
            return
        ids = parse_ids(self.ids_field.value)
        if not ids:
            self._set_status("请先输入至少一个本子 ID", self.COLOR_ERR)
            return
        self._sync_conf_from_ui()
        conf = copy.deepcopy(self.conf)
        mail_conf = conf["mail"]
        if mail_conf.get("enable") and not (mail_conf.get("sender") and mail_conf.get("password")):
            self._set_status("已启用邮件推送：请填写发件邮箱与授权码", self.COLOR_ERR)
            return
        try:
            save_conf(self.conf)
        except OSError:
            pass
        download_dir = resolve_path(conf["app"].get("download_dir"))
        self.running = True
        self.btn_start.disabled = True
        self.progress.visible = True
        self._set_status("下载中...")
        self.page.run_thread(self._run_task, ids, download_dir, conf)

    def _run_task(self, ids, download_dir, conf):
        try:
            os.makedirs(download_dir, exist_ok=True)
            option = build_option(conf)
            self.append_log("开始下载 %d 个本子：%s" % (len(ids), ", ".join(ids)))
            self.append_log("下载目录：%s" % download_dir)
            result = jmcomic.download_album(ids, option)
            failed = getattr(result, "failed", {}) or {}
            pdfs = collect_pdfs(result)
            for jmid, err in failed.items():
                self.append_log("下载失败 [%s]：%s" % (jmid, err))
            if conf["app"].get("to_pdf", True):
                if pdfs:
                    self.append_log("共生成 %d 个 PDF：" % len(pdfs))
                    for p in pdfs:
                        self.append_log("  %s" % p)
                else:
                    self.append_log("未生成任何 PDF 文件")
            else:
                self.append_log("已按设置跳过 PDF 合并")
            mail_conf = conf["mail"]
            if mail_conf.get("enable"):
                if pdfs:
                    self.append_log("正在发送邮件...")
                    try:
                        send_mail(mail_conf, pdfs, self.append_log)
                        self.append_log("邮件发送成功！")
                    except Exception as exc:
                        self.append_log("邮件发送失败：%s" % exc)
                else:
                    self.append_log("没有可发送的 PDF，跳过邮件推送")
            ok = not failed
            summary = "完成：%d 个本子，%d 个 PDF" % (len(ids) - len(failed), len(pdfs))
            self._finish(ok, summary if ok else "完成（含失败项），详见日志")
        except Exception:
            self.append_log("发生错误：\n%s" % traceback.format_exc())
            self._finish(False, "出错，详见日志")

    def _finish(self, ok, status):
        self.running = False
        self.btn_start.disabled = False
        self.progress.visible = False
        self._set_status(status, self.COLOR_OK if ok else self.COLOR_ERR)


def main(page: ft.Page):
    Jm2PdfUI(page)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
