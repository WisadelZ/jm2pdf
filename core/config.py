# -*- coding: utf-8 -*-
"""配置层：路径解析、conf.yml 的读取 / 保存 / 导入 / 导出。

本模块不依赖 UI 框架，可单独测试。
"""

import copy
import os
import sys

import yaml

CONF_FILENAME = "conf.yml"

CONF_HEADER = """# Jm2PDF 配置文件
# 界面中的任何修改都会自动同步保存到本文件；也可手动编辑后重启程序生效。
# 相对路径基于程序（exe）所在目录解析。

"""

# 程序内兜底默认配置：磁盘配置缺失字段时以此补齐
DEFAULT_CONF_TEXT = """
version: 2.2.0
app:
  download_dir: ./download
  to_pdf: true
  thread_image: 30
  thread_photo: 16
  username: ''
  password: ''
  theme_mode: light
  language: zh_cn
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
      - plugin: jm2pdf_meta_pdf
        kwargs:
          pdf_dir: ./download
          filename_rule: Pname
"""

# 界面支持的取值
THEME_MODES = ("light", "dark", "system")

# core/config.py -> 项目根目录（源码运行时 app.py 所在目录）
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_SOURCE_ROOT = os.path.dirname(_PACKAGE_DIR)


def app_dir():
    """程序数据目录：打包后为 exe 所在目录，源码运行时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _SOURCE_ROOT


def bundle_dir():
    """打包资源目录（onefile 模式下为解压临时目录）。"""
    return getattr(sys, "_MEIPASS", app_dir())


def conf_path():
    return os.path.join(app_dir(), CONF_FILENAME)


def resolve_path(path):
    """把配置中的相对路径解析为基于程序目录的绝对路径。"""
    path = (path or "").strip()
    if not path:
        path = "download"
    if not os.path.isabs(path):
        path = os.path.join(app_dir(), path)
    return os.path.normpath(path)


def _deep_merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _dump_conf(conf):
    return CONF_HEADER + yaml.safe_dump(
        conf, allow_unicode=True, sort_keys=False, default_flow_style=False)


def ensure_conf_file():
    """确保 conf.yml 存在；首次运行时从打包资源或默认模板生成。"""
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
            f.write(text if text else _dump_conf(yaml.safe_load(DEFAULT_CONF_TEXT)))
    except OSError:
        pass
    return path


def load_conf():
    """读取配置并与默认值深度合并，保证调用方拿到的字段完整。"""
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
    """写回 conf.yml，并始终把 version 更新为当前程序版本。"""
    from core.constants import APP_VERSION

    data = copy.deepcopy(conf)
    data["version"] = APP_VERSION
    with open(conf_path(), "w", encoding="utf-8") as f:
        f.write(_dump_conf(data))


def export_conf(conf, target_path):
    """把当前配置写到用户指定的文件（用于备份 / 迁移）。"""
    from core.constants import APP_VERSION

    data = copy.deepcopy(conf)
    data["version"] = APP_VERSION
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(_dump_conf(data))


def read_conf_file(source_path):
    """读取并校验一个外部配置文件，返回补齐默认值后的配置字典。

    校验失败时抛出 ValueError。
    """
    with open(source_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or not data:
        raise ValueError("invalid or empty config file")
    defaults = yaml.safe_load(DEFAULT_CONF_TEXT)
    return _deep_merge(defaults, data)
