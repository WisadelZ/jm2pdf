# Jm2PDF v2.1.2 - 禁漫本子下载工具 📚

一个开源免费的禁漫（jmcomic）本子下载、搜索和 PDF 合并工具，支持批量操作和邮件推送。

[![License: CC BY-NC-ND 4.0](https://img.shields.io/badge/License-CC%20BY--NC--ND%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2B-green.svg)](https://www.microsoft.com/windows)

## ✨ 特性

- **智能搜索**：输入本子 ID 即可获取详细信息（名称、页数、章节、标签）与封面缩略图，
  并附可点击的网页链接
- **批量下载**：支持逗号/空格分隔的多个 ID，一次下载多个本子
- **自动合并 PDF**：每个章节自动合并为 PDF 文件，可通过「生成 PDF」开关自由关闭；
  PDF 与图片文件夹同名，按名称排序时两者相邻，便于管理
- **PDF 元数据**：生成 PDF 时把漫画资料写进 PDF 文件属性（标题、作者、标签、ID、页数、章节），
  图片文件不做任何处理；旧版本生成的 PDF 没有元数据属正常现象
- **资源管理器**：按漫画归组浏览下载目录，同一本漫画的 PDF 与图片文件夹用折叠菜单归在一起；
  可批量打开或删除（删除为移入回收站，可恢复），选中 PDF 时右侧边栏展示其元数据
- **邮件推送**：可选将生成的 PDF 通过邮件发送（支持 QQ/163 等邮箱）
- **可配置性**：自定义下载目录、并发数、账号密码等设置，界面修改自动同步到 conf.yml
- **配置导入导出**：一键导出当前配置备份，或从文件导入已有配置
- **多语言**：内置简体中文、繁体中文、英文三种界面语言，切换后立即生效
- **主题切换**：支持浅色 / 深色 / 跟随系统三种外观，切换后立即生效
- **帮助页**：展示版本号、作者署名、项目地址、分发协议与免责声明，并附 GitHub Issue 入口
- **开源共享**：CC BY-NC-ND 4.0 许可证，允许非商用分享

## 🚀 快速开始

### 方式一：使用预编译版本（推荐）

1. 访问 [Releases](https://github.com/WisadelZ/jm2pdf/releases) 页面
2. 下载最新的 `jm2pdf-v2.1.2.exe`
3. 双击运行，输入本子 ID 即可开始使用

### 方式二：从源码构建

```bash
# 克隆仓库
git clone https://github.com/WisadelZ/jm2pdf.git
cd jm2pdf

# 安装依赖
python -m pip install -r requirements.txt

# 运行（调试）
python app.py

# 打包成单文件 exe（内部调用 flet pack）
python build.py
```

## 📖 使用说明

### 基本流程

1. **输入本子 ID**：在"本子 ID"框中输入本子编号（如：`1462837`）
2. **选择下载目录**：指定保存位置（默认 `./download`）
3. **生成 PDF 开关**：主界面可直接切换是否合并 PDF
4. **配置选项**（折叠面板，可选展开）：
   - 图片/章节并发数：调整下载速度
   - 账号密码：如需登录（可选）
5. **点击"开始下载"**：等待完成

### 搜索功能

1. 在"搜索 ID"框中输入本子 ID（回车或点击"搜索"）
2. 查看返回的信息（自动换行，无需拖动），末尾附有可点击的网页链接：
   ```
   ID: 567464
   页数: 454 / 章节: 1
   名称: 《明日方舟》官方世界观设定集[大地巡旅]
   标签: 非H, 设定集, 中文
   网页链接 https://18comic.vip/album/567464/
   ```
3. 点击"添加"按钮将其加入下载列表

搜索结果框右侧会同时显示该本子的封面缩略图（3:4）。封面只在内存中展示，不会保存到本地磁盘；
若封面取不到，该处显示一个占位图标，不影响搜索结果与后续操作。

### 邮件推送（可选）

展开"邮件推送"面板：
1. 打开"启用邮件推送"开关
2. 填写 SMTP 服务器信息：
   - 服务器：`smtp.qq.com`（QQ邮箱）或 `smtp.163.com`（163邮箱）
   - 端口：`465`（SSL）或 `25`（非加密）
   - 发件箱：你的邮箱地址
   - 授权码：邮箱的授权码（不是登录密码！）
   - 收件箱：留空则发给自己
3. 下载完成后会自动发送邮件

### 资源管理器

主界面顶栏的「资源管理器」按钮可打开资源管理器页，用于管理下载目录里已下载的内容：

- 同一本漫画的图片文件夹与 PDF 会折叠归在同一项下（点击展开），单独的 PDF 或图片文件夹则单独列出
- 勾选项目左侧的复选框后，底部「打开」可用系统默认方式打开（PDF 用默认阅读器、文件夹用资源管理器），
  「删除」则把所选项目**移入回收站**（可从回收站恢复，删除前会弹确认框）
- 勾选 PDF 时，右侧边栏展示该 PDF 的元数据：标题、本子 ID、作者、标签、页数、章节序号；
  旧版本生成的 PDF 没有元数据，会提示「该 PDF 没有元数据」
- 列表与边栏数据来自实时扫描，点击「刷新」可重新读取

### 帮助

顶栏的「帮助」按钮可打开帮助页，展示版本号、作者署名、项目地址、分发协议与免责声明；
如遇问题或有功能建议，可通过页面下方的链接前往 GitHub 项目主页提交 Issue。

### 设置

主界面左上角的「设置」按钮可打开设置页，包含三个分区：

- **配置管理**：导出当前配置到指定文件备份，或从文件导入已有配置（导入后界面立即刷新）
- **外观设置**：浅色 / 深色 / 跟随系统
- **语言设置**：简体中文 / 繁体中文 / English

外观与语言切换后立即生效，无需重启；下载任务进行中时修改语言会在重启后生效。

## 📁 项目结构

```
jm2pdf/
├── app.py                      # 程序入口（仅创建窗口）
├── build.py                    # flet pack 打包脚本
├── conf.yml                    # 配置模板
├── icon.ico                    # 应用图标
├── requirements.txt            # 依赖清单
├── LICENSE                     # CC BY-NC-ND 4.0 许可证
├── README.md                   # 项目说明
├── CHANGELOG.md                # 更新日志
├── .gitignore                  # Git 忽略规则
├── core/                       # 业务逻辑层（不依赖 Flet）
│   ├── constants.py            # 全局常量与应用元信息
│   ├── config.py               # 路径解析、conf.yml 读写、导入导出
│   ├── downloader.py           # jmcomic 选项构建、PDF 收集、邮件发送
│   ├── library.py              # 下载目录扫描分组、打开、删除到回收站
│   ├── pdf_metadata.py         # PDF 元数据写入插件与读取解析
│   └── logging_bridge.py       # jmcomic 日志转发到界面
├── ui/                         # 界面层
│   ├── app_ui.py               # 协调器：路由、状态、配置持久化、业务调度
│   ├── main_page.py            # 主页（下载、搜索、日志）
│   ├── explorer_page.py        # 资源管理器页（归组管理 + 元数据边栏）
│   ├── settings_page.py        # 设置页（配置管理、外观、语言）
│   └── help_page.py            # 帮助页（版本、署名、协议、免责声明）
└── utils/                      # 通用工具层
    ├── i18n.py                 # 多语言文本表
    └── helpers.py              # 通用辅助函数
```

代码按「业务逻辑 / 界面 / 工具」三层拆分，各层职责单一、互不耦合，新增功能时只需在对应层增加模块。

## ⚙️ 配置说明

首次运行时会自动生成 `conf.yml`，可手动编辑：

```yaml
app:
  download_dir: ./download      # 下载目录
  to_pdf: true                  # 是否合并为 PDF
  thread_image: 30              # 图片并发数
  thread_photo: 16              # 章节并发数
  username: ''                  # 登录账号（可选）
  password: ''                  # 登录密码（可选）
  theme_mode: light             # 界面主题：light / dark / system
  language: zh_cn               # 界面语言：zh_cn / zh_tw / en

mail:
  enable: false                 # 是否启用邮件
  server: smtp.qq.com           # SMTP 服务器
  port: 465                     # 端口
  sender: ''                    # 发件邮箱
  password: ''                  # 授权码
  receiver: ''                  # 收件邮箱（留空=自己）
```

## 🔧 技术栈

- **Python**: 3.12+
- **GUI框架**: Flet（现代化跨平台 UI 框架）
- **核心库**: jmcomic（禁漫客户端）、img2pdf / pikepdf（PDF 合并与元数据）、Pillow（图像处理）
- **打包工具**: flet pack / PyInstaller（单文件 exe）

## 🙏 反馈与建议

欢迎提交 Issue 报告问题或提出建议！

由于本项目采用 CC BY-NC-ND 4.0 许可证（禁止衍生作品），因此不接受 Fork 修改后的 Pull Request。如有功能需求或 Bug，请直接通过 Issue 反馈。

## 📄 许可证

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

## 🙏 致谢

- jmcomic 禁漫客户端库
- Flet 与 Python 社区及所有开源贡献者

---

**注意**：本工具仅用于学习研究，请遵守网站的使用条款，尊重版权和创作者权益。
