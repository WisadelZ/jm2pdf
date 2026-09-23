# 安全策略

本文件说明 Jm2PDF 的安全边界、数据处理方式以及漏洞报告流程。

- 当前版本：v2.3.1（版本号取自 `core/constants.py` 的 `APP_VERSION`）
- 项目地址：https://github.com/WisadelZ/jm2pdf
- 许可证：CC BY-NC-ND 4.0

## 支持的版本

仅对**最新发布版本**提供安全修复。旧版本请先升级到最新版再反馈安全问题。

| 版本 | 是否支持 |
| --- | --- |
| v2.3.1（最新） | ✅ |
| v2.3.0 及更早 | ❌ |

## 报告安全漏洞

请通过 GitHub Issues 反馈：https://github.com/WisadelZ/jm2pdf/issues

- 提交时请说明：影响版本、复现步骤、预期与实际结果、可能的影响范围。
- **请勿在 Issue 中粘贴真实凭据**（账号密码、邮箱授权码、Cookie 等）。如果问题必须依赖敏感信息才能复现，请先只描述问题，等待维护者给出私下的沟通方式。
- 请在修复发布后再公开细节，给维护者留出处理时间。

本项目目前没有独立的安全邮箱，所有安全问题统一走 GitHub Issues。

## 安全边界（威胁模型）

Jm2PDF 是一个**本地桌面工具**，不是服务端程序，也没有网络服务端口：

- 无后端服务、无遥测、无自动更新、无后台常驻进程；不收集、不上传任何用户数据。
- 所有请求都由用户在本机发出，程序的权限等同于运行它的 Windows 账户权限。
- 程序不对下载内容做安全审查，也**不是**内容隔离沙箱：它会把文件写入用户指定的下载目录。

因此，以下内容**不在**本项目的处理范围内：

- 站点本身（18comic 及其镜像）的内容、可用性与安全性；
- 第三方依赖库自身的漏洞（应向上游项目报告，见下文「第三方依赖」）；
- 用户自行修改源码后产生的问题（CC BY-NC-ND 4.0 禁止分发修改版）。

## 凭据与敏感信息

配置文件 `conf.yml` 位于程序（exe）所在目录，以**明文**保存以下信息：

| 字段 | 含义 | 敏感度 |
| --- | --- | --- |
| `app.username` / `app.password` | 站点登录账号（可选） | 高 |
| `mail.password` | 邮箱 SMTP 授权码 | 高 |
| `mail.sender` / `mail.receiver` | 收发件邮箱地址 | 中 |

说明与注意事项：

- 凭据由 [core/downloader.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/downloader.py) 在构建选项时读取，仅用于向站点登录和向用户指定的 SMTP 服务器发信，不会发送到任何第三方。
- 界面上的任何修改都会自动写回 `conf.yml`（见 [core/config.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/config.py)）。文件权限即所在目录的权限，请勿把程序放在共享目录中运行。
- 设置页的**配置导出**会把当前 `conf.yml`（含明文凭据）原样写到用户选择的文件（见 [ui/app_ui.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/ui/app_ui.py)）。导出的备份请妥善保管，不要上传到公开位置。
- **不要把 `conf.yml` 或导出的配置提交到 Git / 网盘 / 公开仓库。** 打开发布包前请确认 `conf.yml` 已还原为默认模板（`app.username`、`app.password`、`mail.password` 均为空）。
- 出于最小化原则，搜索与预览用到的封面、预览图只在内存中处理、不写入磁盘；图片文件本身不做任何改动（不写 EXIF、不重新编码）。

## 网络行为

程序只访问以下目标，全部由本机主动发起：

| 目标 | 用途 | 说明 |
| --- | --- | --- |
| `18comic.vip` 及 jmcomic 内置的镜像域名 | 搜索、本子详情、下载、在线浏览 | 由依赖库 `jmcomic` 负责请求与图片解密 |
| 站点图片 CDN | 获取封面缩略图与页面图片 | 取图时显式带 `User-Agent`（空 UA 会被 CDN 拒绝），见 [core/downloader.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/downloader.py) |
| 用户自行填写的 SMTP 服务器 | 邮件推送 | 端口 465 走 `SMTP_SSL`，其他端口走 `SMTP` + `STARTTLS` |

- 只会把 PDF 附件发到用户填写的收件箱（留空则发给自己），不会向其他地址发送数据。
- 网页链接固定使用 `18comic.vip` 域名，其余镜像只用于下载。
- 除上述目标外，程序不访问任何其他地址。

## 文件与本地数据

- **写入范围**：仅写入用户指定的下载目录（默认 `./download`，相对路径基于程序所在目录解析）以及程序目录下的 `conf.yml`。
- **删除行为**：资源管理器中的「删除」调用 Windows Shell 接口并带上 `FOF_ALLOWUNDO`，即**移入回收站**而非永久删除，可从回收站恢复（见 [core/library.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/library.py)）。
- **打开文件**：「打开」使用系统默认关联程序，请确认本机 PDF 阅读器可信。
- **配置导入**：导入外部配置文件会校验并深度合并后**覆盖写回** `conf.yml`（见 [core/config.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/config.py)），因此不要导入来路不明的配置文件。
- **PDF 元数据**：生成 PDF 时会写入标题、作者、标签、本子 ID / 页数 / 章节等 DocInfo 字段（见 [core/pdf_metadata.py](file:///e:/Trae%20work%20projects/exp1/jm2pdf/core/pdf_metadata.py)）。分享 PDF 前请注意这些信息会随文件一起带出。

## 发布包与供应链

- 请从官方渠道获取程序：Releases 页面 https://github.com/WisadelZ/jm2pdf/releases 。不要从第三方站点下载 `jm2pdf-*.exe`。
- 预编译 exe 由 `build.py` 调用 `flet pack`（PyInstaller）自行打包，**未做代码签名**，Windows 可能提示来源不明；请在确认来源后再运行。
- 依赖清单见 [requirements.txt](file:///e:/Trae%20work%20projects/exp1/jm2pdf/requirements.txt)：`jmcomic`、`pyyaml`、`pillow`、`img2pdf`、`pikepdf`、`flet`。从源码构建时请使用官方 PyPI 源安装，并建议固定依赖版本后自行审计。
- 上游依赖若出现漏洞，请向对应上游项目报告；本项目会通过更新依赖版本跟进。

## 使用建议

- 邮箱只填写**授权码**而非登录密码，并为该邮箱单独开通/更换授权码。
- 不要在下载目录里存放与下载内容无关的敏感文件，避免误删或误分享。
- 定期检查 `conf.yml` 中的凭据；不再使用时清空并更换授权码。
- 使用完毕后如不再需要，删除 `conf.yml` 即可清除本地保存的凭据。

## 免责声明

本工具仅供学习研究使用，请遵守网站的使用条款，尊重版权与创作者权益，请勿用于任何商业用途。
程序按「现状」提供，作者不对使用本工具造成的任何后果负责。
本项目采用 CC BY-NC-ND 4.0 许可证：允许非商用分享，禁止商用，禁止修改后再分发。
