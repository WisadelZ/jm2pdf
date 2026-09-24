# -*- coding: utf-8 -*-
"""账号层：登录信息的本地加密存储与运行时凭据。

登录信息（账号 / 密码 / 昵称 / 头像地址）统一加密后写入程序同级目录下的
单个文件（account.dat），磁盘上与 conf.yml 里都不出现任何明文；密钥由内置
常量结合本机标识派生，文件拷到其它机器上无法解密。
"""

import getpass
import hashlib
import json
import os
import platform

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from core.config import app_dir

ACCOUNT_FILENAME = "account.dat"

# 文件头：标记加密格式与版本，解密前先校验
_MAGIC = b"JM2PDF-ACCOUNT-V1"
# 内置主密钥：与机器标识一起参与密钥派生，本身不出现在磁盘上
_APP_SECRET = "jm2pdf::account::v1::3f9a1c7e5b2d48a6"
# 密钥派生与分组加密参数
_KDF_ROUNDS = 200_000
_SALT_SIZE = 16
_NONCE_SIZE = 12
_TAG_SIZE = 16
_KEY_SIZE = 32

# 运行时凭据：只在内存里，供下载层登录使用
_credentials = {"username": "", "password": ""}


def account_path():
    """账号文件路径：与 conf.yml 同级（打包后为 exe 所在目录）。"""
    return os.path.join(app_dir(), ACCOUNT_FILENAME)


def _machine_factor():
    """机器标识：让加密文件绑定本机，换机器或换用户后无法解密。"""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    raw = "|".join((platform.node(), user, platform.machine(), platform.system()))
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _derive_key(salt):
    material = _APP_SECRET.encode("utf-8") + _machine_factor()
    return hashlib.pbkdf2_hmac("sha256", material, salt, _KDF_ROUNDS, dklen=_KEY_SIZE)


def _encrypt(payload):
    """明文 JSON -> 文件头 + 盐 + 随机数 + 认证标签 + 密文。"""
    salt = get_random_bytes(_SALT_SIZE)
    cipher = AES.new(_derive_key(salt), AES.MODE_GCM, nonce=get_random_bytes(_NONCE_SIZE))
    ciphertext, tag = cipher.encrypt_and_digest(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return _MAGIC + salt + cipher.nonce + tag + ciphertext


def _decrypt(raw):
    """还原 _encrypt 的产物；密钥不符或内容被改动时抛异常。"""
    offset = len(_MAGIC) + _SALT_SIZE + _NONCE_SIZE
    salt = raw[len(_MAGIC):len(_MAGIC) + _SALT_SIZE]
    nonce = raw[len(_MAGIC) + _SALT_SIZE:offset]
    tag = raw[offset:offset + _TAG_SIZE]
    cipher = AES.new(_derive_key(salt), AES.MODE_GCM, nonce=nonce)
    return json.loads(cipher.decrypt_and_verify(raw[offset + _TAG_SIZE:], tag).decode("utf-8"))


def load_account():
    """读取并解密账号信息；文件不存在、损坏或来自其它机器时返回 None。"""
    try:
        with open(account_path(), "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if not raw.startswith(_MAGIC):
        return None
    try:
        data = _decrypt(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_account(data):
    """加密写入账号信息，并同步运行时凭据。"""
    with open(account_path(), "wb") as f:
        f.write(_encrypt(data))
    set_credentials(data.get("username"), data.get("password"))


def delete_account():
    """退出登录：删掉整个账号文件并清空运行时凭据。"""
    try:
        os.remove(account_path())
    except FileNotFoundError:
        pass
    set_credentials("", "")


def set_credentials(username, password):
    _credentials["username"] = (username or "").strip()
    _credentials["password"] = password or ""


def get_credentials():
    """下载层登录用的 (账号, 密码)；未登录时均为空串。"""
    return _credentials["username"], _credentials["password"]


def is_logged_in():
    """是否已有可用的登录凭据（用于「必要时才用登录态」的判断）。"""
    username, password = get_credentials()
    return bool(username and password)
