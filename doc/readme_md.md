# AI Agent 系统

一个基于 DeepSeek v3.1 的智能自动化操作系统，可以在指定文件夹内执行各种任务。

## 功能特性

### 核心功能
- 📁 **文件操作**: 创建、删除、修改、读取文件和文件夹
- 🔍 **网络搜索**: 通过 Tavily API 搜索网络信息
- 💻 **代码执行**: 运行 Python 代码和脚本
- ⚡ **终端操作**: 执行终端命令
- 📝 **记忆管理**: 维护主记忆和任务记忆

### 架构特点
- **双终端模式**: 主终端对话 + 子终端执行
- **思考模式**: 支持开启/关闭 AI 思考过程显示
- **模块化设计**: 各功能模块独立，易于扩展
- **安全机制**: 路径验证、命令过滤、操作确认

## 安装步骤

### 1. 环境要求
- Python 3.8+
- macOS 或 Windows

### 2. 创建项目结构
```bash
cd /Users/jojo/Desktop
# 运行提供的创建命令
```

### 3. 安装依赖
```bash
cd agent
pip install httpx
```

### 4. 配置 API 密钥
编辑 `config.py` 文件，替换以下内容：
```python
API_KEY = "your-deepseek-api-key"  # 火山引擎 DeepSeek API 密钥
TAVILY_API_KEY = "your-tavily-api-key"  # Tavily 搜索 API 密钥（可选）
```

## 使用方法

### 启动系统
```bash
python main.py
```

### 系统命令
- `/help` - 显示帮助信息
- `/exit` - 退出系统
- `/status` - 显示系统状态
- `/memory` - 管理记忆文件
- `/clear` - 清屏
- `/history` - 显示对话历史
- `/files` - 显示项目文件
- `/mode` - 切换思考模式

### 任务示例

#### 创建文件
```
创建一个名为 hello.py 的 Python 文件，内容是打印 Hello World
```

#### 搜索信息
```
搜索比亚迪仰望系列车型的信息
```

#### 运行代码
```
运行 hello.py 文件
```

#### 文件操作
```
在项目中创建一个 docs