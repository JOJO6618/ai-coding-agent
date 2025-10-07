# AI Agent 系统

一个基于开源大语言模型（DeepSeek、Qwen、Kimi 等）的智能编程助手，支持文件操作、代码执行和持久化终端管理。主要通过 Web 界面交互，参考了 Claude、ChatGPT 等成熟产品的架构设计。

> ⚠️ **项目状态**：这是一个个人学习项目，代码主要由 AI 辅助编写。目前功能基本可用，但代码结构有待优化（存在一定的"屎山代码"趋势）。欢迎贡献和建议！

## ✨ 核心特性

### 🌐 Web 界面
- 类似 ChatGPT 的对话交互界面
- 实时显示 AI 思考过程（支持双模式切换）
- 文件树可视化，项目结构一目了然
- 完整的对话历史管理和持久化

### 📁 智能文件管理
- **聚焦文件机制**：最多 3 个文件同时聚焦，内容实时可见
- 文件创建、读取、修改、删除
- 基于内容匹配和精确行号的双重编辑模式
- 自动同步文件备注

### 🖥️ 持久化终端
- 支持最多 3 个并发终端会话
- 终端进程持续运行，支持交互式程序（如开发服务器、Python REPL）
- 会话切换和管理
- 实时终端监控界面（基于 xterm.js）

### 💭 双模式思考
- **快速模式**：直接响应，适合简单任务
- **思考模式**：首次深度思考，后续快速执行

### 💾 对话持久化（v4.1）
- 所有对话自动保存到本地 JSON 文件
- 支持加载历史对话，恢复完整上下文
- 对话列表管理、搜索和删除

### 🔍 其他功能
- 网络搜索（基于 Tavily API）
- 网页内容提取
- 记忆管理（长期知识存储）

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名

# 安装依赖
pip install -r requirements.txt
```

### 配置

在 `config.py` 中配置 API 密钥：

```python
# API配置（选择你使用的模型服务）
API_BASE_URL = "https://api.deepseek.com"  # 或其他兼容 OpenAI API 的服务
API_KEY = "your-api-key-here"
MODEL_ID = "deepseek-chat"

# Tavily搜索配置（可选）
TAVILY_API_KEY = "your-tavily-api-key"  # 用于网络搜索功能
```

### 启动

```bash
# 启动系统
python main.py

# 选择运行模式
# 1. 命令行模式（CLI）
# 2. Web界面模式（推荐）

# 选择思考模式
# 1. 快速模式
# 2. 思考模式
```

Web 界面默认地址：`http://localhost:8091`

## 🛠️ 技术栈

- **后端**：Python 3.8+
- **Web 框架**：Flask + Flask-SocketIO
- **前端**：原生 JavaScript + HTML/CSS
- **终端模拟**：xterm.js
- **大语言模型**：支持 DeepSeek、Qwen、Kimi 等（兼容 OpenAI API）
- **搜索引擎**：Tavily API

## 📂 项目结构

```
.
├── main.py                 # 程序入口
├── config.py              # 配置文件
├── web_server.py          # Web 服务器
├── core/                  # 核心模块
│   ├── main_terminal.py   # 主终端逻辑
│   └── web_terminal.py    # Web 终端适配
├── modules/               # 功能模块
│   ├── file_manager.py    # 文件操作
│   ├── terminal_manager.py # 终端管理
│   ├── conversation_manager.py # 对话持久化
│   └── ...
├── utils/                 # 工具模块
│   ├── api_client.py      # API 客户端
│   ├── context_manager.py # 上下文管理
│   └── ...
├── static/                # 前端资源
│   ├── index.html         # 主界面
│   ├── terminal.html      # 终端监控
│   ├── app.js             # 前端逻辑
│   └── style.css          # 样式
└── prompts/               # 系统提示词
```

## 📖 使用示例

### Web 开发场景

```
用户：帮我创建一个 Flask 网站，包含首页和关于页面

AI：
1. 创建项目结构（src/、templates/、static/）
2. 聚焦核心文件（app.py、index.html）
3. 开启开发服务器终端
4. 在新终端中测试 API
5. 边开发边调试
```

### Python 数据处理

```
用户：帮我分析这个 CSV 文件的数据

AI：
1. 聚焦数据处理脚本
2. 开启 Python REPL 终端
3. 逐步加载、处理、验证数据
4. 将验证通过的代码写入脚本
```

## ⚠️ 已知问题

- [ ] 代码结构需要重构，存在一定的耦合
- [ ] 错误处理不够完善
- [ ] 部分功能在特定场景下可能不稳定
- [ ] Windows 路径处理偶尔会出现问题
- [ ] 大文件操作性能有待优化

## 🎯 项目定位

这是一个**学习和实验性质**的项目，主要目标是：

- 探索 AI Agent 的实现方式
- 学习持久化终端管理技术
- 实践完整的 Web 应用开发
- **不是**生产级别的工具（请勿在重要项目中直接使用）

## 🙏 致谢

本项目参考了以下优秀项目的设计理念：

- [Claude](https://claude.ai) - 对话交互和思考模式设计，聚焦文件参考了artifact功能
- [ChatGPT](https://chat.openai.com) - 对话管理和界面设计

特别感谢 AI 辅助编程工具（Claude、ChatGPT、DeepSeek 等）在开发过程中提供的帮助。

## 🤝 贡献指南

欢迎任何形式的贡献！

- 🐛 **Bug 报告**：在 Issues 中详细描述问题
- 💡 **功能建议**：提出你的想法和需求
- 🔧 **代码贡献**：提交 Pull Request（代码质量可能不高，欢迎重构）
- 📝 **文档改进**：完善 README 和注释

### 代码说明

- 大部分代码由 AI 辅助生成，可能存在冗余和不规范之处
- 欢迎进行代码审查和重构
- 提 PR 前请确保基本功能可用

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 📮 联系方式

- **Issues**：[项目 Issues 页面](https://github.com/你的用户名/你的仓库名/issues)
- **讨论**：[Discussions](https://github.com/你的用户名/你的仓库名/discussions)

---

⭐ 如果这个项目对你有帮助，欢迎给个 Star！

💬 有任何问题或建议，欢迎提 Issue 讨论！
