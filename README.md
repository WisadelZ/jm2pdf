# Jm2PDF v1.2.0 - 禁漫本子下载工具 📚

一个开源免费的禁漫（jmcomic）本子下载、搜索和 PDF 合并工具，支持批量操作和邮件推送。

[![License: CC BY-NC-ND 4.0](https://img.shields.io/badge/License-CC%20BY--NC--ND%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2B-green.svg)](https://www.microsoft.com/windows)

## ✨ 特性

- **智能搜索**：输入本子 ID 即可获取详细信息（名称、页数、章节、标签）
- **批量下载**：支持逗号/空格分隔的多个 ID，一次下载多个本子
- **自动合并 PDF**：每个章节自动合并为 PDF 文件
- **邮件推送**：可选将生成的 PDF 通过邮件发送（支持 QQ/163 等邮箱）
- **可配置性**：自定义下载目录、并发数、账号密码等设置
- **开源共享**：CC BY-NC-ND 4.0 许可证，允许非商用分享

## 🚀 快速开始

### 方式一：使用预编译版本（推荐）

1. 访问 [Releases](https://github.com/WisadelZ/jm2pdf/releases) 页面
2. 下载最新的 `Jm2PDF.exe`
3. 双击运行，输入本子 ID 即可开始使用

### 方式二：从源码构建

```bash
# 克隆仓库
git clone https://github.com/WisadelZ/jm2pdf.git
cd jm2pdf

# 安装依赖（使用项目内置的 portable Python）
& "python" -m pip install -r requirements.txt

# 打包成 exe
& "python" build.py
```

## 📖 使用说明

### 基本流程

1. **输入本子 ID**：在"本子ID"框中输入本子编号（如：`1462837`）
2. **选择下载目录**：指定保存位置（默认 `./download`）
3. **配置选项**（可选展开）：
   - 合并为 PDF：勾选后每个章节会生成 PDF
   - 图片/章节并发数：调整下载速度
   - 账号密码：如需登录（可选）
4. **点击"开始下载"**：等待完成

### 搜索功能

1. 在"搜索ID"框中输入本子 ID
2. 点击"搜索"按钮
3. 查看返回的信息：
   ```
   ID: 422866
   页数: 2 / 章节: 1
   名称: [MANA] 神里绫华 1 (原神) [中国语] [无修正]
   标签: cosplay, 原神, 神里绫华
   ```
4. 点击"添加"按钮将其加入下载列表

### 邮件推送（可选）

1. 勾选"启用邮件推送"
2. 填写 SMTP 服务器信息：
   - 服务器：`smtp.qq.com`（QQ邮箱）或 `smtp.163.com`（163邮箱）
   - 端口：`465`（SSL）或 `25`（非加密）
   - 发件箱：你的邮箱地址
   - 授权码：邮箱的授权码（不是登录密码！）
   - 收件箱：留空则发给自己
3. 下载完成后会自动发送邮件

## 📁 项目结构

```
jm2pdf/
├── app.py              # 主程序（含 GUI）
├── build.py            # PyInstaller 打包脚本
├── conf.yml            # 配置模板
├── icon.ico            # 应用图标
├── LICENSE             # 许可证
├── README.md           # 项目说明
└── .gitignore          # Git 忽略规则
```

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
- **GUI框架**: tkinter（标准库，无需额外安装）
- **核心库**: jmcomic（禁漫客户端）、Pillow（图像处理）
- **打包工具**: PyInstaller（单文件 exe）

## 🙏 反馈与建议

欢迎提交 Issue 报告问题或提出建议！

由于本项目采用 CC BY-NC-ND 4.0 许可证（禁止衍生作品），因此不接受 Fork 修改后的 Pull Request。如有功能需求或 Bug，请直接通过 Issue 反馈。

## 📄 许可证

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may not use this work except in compliance with the License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## 🙏 致谢

- jmcomic 禁漫客户端库
- Python 社区及所有开源贡献者

---

**注意**：本工具仅用于学习研究，请遵守网站的使用条款，尊重版权和创作者权益。
