# AI Agent 系统技术文档 v4.0

## 系统概述

这是一个基于 DeepSeek v3.1 的智能自动化操作系统，能够在指定文件夹内执行各种任务。系统采用单终端架构，通过工具调用（Function Calling）实现文件操作、代码执行、网络搜索、网页提取、持久化终端管理等功能。支持命令行（CLI）和Web两种运行模式，并提供实时终端监控界面和优雅停止机制。

## 核心设计理念

1. **对话连续性**：单次程序运行期间保持完整对话历史，包括工具调用结果
2. **智能思考模式**：两种模式平衡效率与深度（快速模式/思考模式）
3. **工具调用循环**：支持多轮工具调用直到任务完成，具备优雅停止功能
4. **文件备注同步**：文件和备注始终保持一一对应
5. **完整上下文传递**：确保API能看到完整的对话流程
6. **持久化终端会话**：保持终端状态，支持交互式程序
7. **智能文件管理**：读取确认机制，聚焦文件管理，精确行编辑

## 系统架构

### 持久化终端子系统
```
持久化终端架构：
┌─────────────────────────────────────┐
│         AI Agent (Python)           │
├─────────────────────────────────────┤
│       TerminalManager               │
│         ├── 管理多个会话            │
│         ├── 会话切换                │
│         └── 资源控制                │
├─────────────────────────────────────┤
│     PersistentTerminal × 3          │
│         ├── subprocess.Popen        │
│         ├── 异步I/O                 │
│         └── 输出缓冲                │
├─────────────────────────────────────┤
│        WebSocket广播                │
│         ├── terminal_output         │
│         ├── terminal_input          │
│         ├── terminal_status         │
│         └── stop_task               │
├─────────────────────────────────────┤
│    Web终端监控器 (xterm.js)         │
│         ├── 实时显示                │
│         ├── 多会话标签              │
│         ├── 命令历史                │
│         └── 停止控制                │
└─────────────────────────────────────┘
```

### 文件管理子系统
```
智能文件管理：
┌─────────────────────────────────────┐
│        文件操作决策层                │
│  ┌─────────────┐  ┌─────────────┐   │
│  │ 读取确认机制 │  │ 聚焦文件管理 │   │
│  └─────────────┘  └─────────────┘   │
├─────────────────────────────────────┤
│        文件操作执行层                │
│  ┌─────────────┐  ┌─────────────┐   │
│  │ 文本匹配修改 │  │ 精确行编辑   │   │
│  └─────────────┘  └─────────────┘   │
├─────────────────────────────────────┤
│        底层文件系统                 │
│         ├── 路径验证                │
│         ├── 权限控制                │
│         └── 原子操作                │
└─────────────────────────────────────┘
```

## 核心功能模块

### 入口文件
- **`main.py`** - 程序入口
  - 初始化系统
  - 选择运行模式（CLI/Web）
  - 选择思考模式（快速/思考）
  - 启动相应终端

### 配置文件
- **`config.py`** - 所有系统配置
  - API密钥（DeepSeek、Tavily）
  - 文件路径限制
  - 超时设置
  - 输出格式定义
  - 终端配置（MAX_TERMINALS = 3，TERMINAL_BUFFER_SIZE = 20000等）

### 核心模块 (`core/`)

#### `main_terminal.py` - 主终端（核心）
- **功能**：处理用户输入、管理对话流程
- **核心特性**：
  - 集成TerminalManager
  - 智能文件读取确认机制
  - 处理所有工具调用（包括行编辑工具）
  - 注入聚焦文件和活动终端内容到上下文
- **关键方法**：
  - `run()` - 主循环，处理用户输入
  - `handle_task()` - 处理任务，调用API
  - `handle_tool_call()` - 执行工具调用（支持优雅停止）
  - `define_tools()` - 定义可用工具（包括行编辑和网页提取）
  - `build_messages()` - 构建消息（高优先级注入聚焦文件）

#### `web_terminal.py` - Web终端
- **功能**：继承MainTerminal，适配Web环境
- **特点**：
  - 禁用print输出（web_mode=True）
  - 提供状态查询接口
  - 支持WebSocket通信和优雅停止
  - 终端事件广播

### 工具模块 (`modules/`)

#### `file_manager.py` - 文件操作
- **功能**：所有文件和文件夹操作，包括精确行编辑
- **关键方法**：
  - `create_file()` - 创建文件
  - `delete_file()` - 删除文件
  - `rename_file()` - 重命名
  - `read_file()` - 读取文件内容
  - `modify_file()` - 修改文件（文本匹配）
  - `edit_lines_range()` - 基于行号的精确编辑（新增）

#### `persistent_terminal.py` - 持久化终端
- **功能**：管理单个终端会话的生命周期
- **关键特性**：
  - 使用subprocess.Popen创建后台进程
  - 异步读取输出，避免阻塞
  - 智能缓冲管理（20KB缓冲，5KB显示）
  - 检测交互式输入状态
  - WebSocket广播支持
- **关键方法**：
  - `start()` - 启动终端进程
  - `send_command()` - 发送命令
  - `get_output()` - 获取输出
  - `close()` - 关闭终端

#### `terminal_manager.py` - 终端管理器
- **功能**：管理多个终端会话
- **关键特性**：
  - 最多3个并发会话
  - 活动终端切换
  - 会话生命周期管理
  - 终端内容格式化注入
- **关键方法**：
  - `open_terminal()` - 打开新会话
  - `close_terminal()` - 关闭会话
  - `switch_terminal()` - 切换活动终端
  - `send_to_terminal()` - 发送命令
  - `get_active_terminal_content()` - 获取格式化内容

#### `search_engine.py` - 网络搜索
- **功能**：Tavily API搜索
- **关键方法**：
  - `search()` - 执行搜索
  - `search_with_summary()` - 搜索并格式化

#### `webpage_extractor.py` - 网页内容提取（新增）
- **功能**：提取指定网页的完整内容进行深度分析
- **关键特性**：
  - 基于Tavily API的网页内容提取
  - 完善的错误处理（超时、API错误等）
  - 格式化输出，便于AI分析
- **关键方法**：
  - `tavily_extract()` - 核心API调用
  - `format_extract_results()` - 格式化结果
  - `extract_webpage_content()` - 主接口函数

#### `terminal_ops.py` - 一次性终端操作
- **功能**：执行Python代码和终端命令（一次性）
- **关键方法**：
  - `run_python_code()` - 执行Python代码
  - `run_command()` - 执行终端命令

#### `memory_manager.py` - 记忆管理
- **功能**：管理主记忆和任务记忆
- **用途**：长期知识存储

### 工具模块 (`utils/`)

#### `api_client.py` - API客户端（核心）
- **功能**：与DeepSeek API通信
- **关键方法**：
  - `chat_with_tools()` - 带工具调用的对话
  - `simple_chat()` - 简单对话
  - `get_current_thinking_mode()` - 获取思考模式

#### `terminal_factory.py` - 终端工厂
- **功能**：跨平台终端支持
- **支持的Shell**：
  - Windows: cmd.exe、PowerShell、Git Bash、WSL
  - macOS: zsh、bash、sh
  - Linux: bash、zsh、sh、fish
- **关键方法**：
  - `get_shell_command()` - 获取合适的shell
  - `get_system_info()` - 获取系统信息

#### `context_manager.py` - 上下文管理
- **功能**：管理对话历史和文件备注
- **关键特性**：
  - 优化的文件树显示（真正的树形结构）
  - 完善的消息格式处理
- **关键方法**：
  - `get_project_structure()` - 获取文件结构
  - `add_conversation()` - 添加对话记录
  - `add_tool_result()` - 添加工具结果
  - `update_annotation()` - 更新文件备注
  - `_build_file_tree()` - 构建树形文件结构

#### `logger.py` - 日志系统
- 记录错误和操作日志

### Web服务 (`web_server.py`)
- **功能**：提供Web界面服务
- **核心特性**：
  - `/terminal` 路由 - 终端监控页面
  - 终端WebSocket事件处理
  - 终端广播机制
  - 优雅停止功能支持
- **特点**：
  - Flask + SocketIO实现
  - 实时流式输出
  - 文件树动态更新
  - 停止标志管理

### 终端监控页面 (`static/terminal.html`)
- **功能**：实时显示AI的终端操作
- **技术栈**：
  - xterm.js - 专业终端模拟器
  - WebSocket - 实时通信
  - 响应式设计
- **特性**：
  - 多会话标签切换
  - 命令历史追踪
  - ANSI颜色支持
  - 统计信息显示

## 工具定义与使用策略

### 文件管理工具

#### 智能读取策略
- **read_file** - 触发确认机制，系统询问是读取还是聚焦
- **confirm_read_or_focus** - 确认工具，AI明确选择读取或聚焦方式
- **focus_file** / **unfocus_file** - 聚焦文件管理

#### 文件编辑工具
- **modify_file** - 基于文本匹配的修改（append、replace、clear）
- **edit_lines** - 基于行号的精确编辑（新增）
  - `replace_lines` - 替换指定行范围
  - `insert_at` - 在指定行前插入内容
  - `delete_lines` - 删除指定行范围

### 终端管理工具

#### 持久化终端
- **terminal_session** - 管理终端会话生命周期
  - `open` - 打开新终端会话
  - `close` - 关闭终端会话
  - `list` - 列出所有会话
  - `switch` - 切换活动终端
- **terminal_input** - 向活动终端发送命令或输入

#### 一次性操作
- **run_command** - 执行系统命令（一次性）
- **run_python** - 执行Python代码（一次性）

### 网络信息获取工具

#### 搜索与提取
- **web_search** - 搜索网络信息（主要方案）
- **extract_webpage** - 提取指定网页完整内容（辅助方案）
  - 仅在搜索结果不足时使用
  - 会显著增加上下文使用量

### 辅助工具
- **sleep** - 等待指定时间，用于长时间操作后的等待
- **update_memory** - 更新系统记忆

## 文件操作失败处理策略

### 标准处理流程
1. **命令行搜索定位**：使用grep查找目标内容和行号
2. **获取精确上下文**：分析实际文件格式、缩进、拼写
3. **选择修改策略**：
   - 优先：使用精确内容重新调用modify_file
   - 备选：使用edit_lines进行基于行号的修改
   - 分解：将大修改拆分为小修改

### edit_lines使用模式
```bash
# 典型工作流
1. run_command("grep -n '函数名' file.py")  # 定位行号
2. edit_lines(path="file.py", operation="replace_lines", 
              start_line=15, end_line=18, content="新代码")
```

## 上下文注入机制

### 信息优先级（从高到低）
1. **系统提示**：基础指令和规则
2. **聚焦文件内容**：当前正在处理的核心文件（高优先级注入）
3. **活动终端状态**：当前终端的输出和状态信息
4. **对话历史**：之前的交互记录

### 聚焦文件管理
- **高优先级注入**：聚焦文件内容在系统提示后立即显示
- **实时更新**：文件修改后内容自动更新
- **容量限制**：最多3个文件同时聚焦
- **智能选择**：通过确认机制引导AI选择读取或聚焦

## 开发工作流程

### 项目开发标准流程
1. **需求分析**：理解用户意图，制定实现计划
2. **环境准备**：创建文件结构，开启终端会话
3. **核心文件聚焦**：聚焦主要开发文件
4. **增量开发**：逐步实现，在终端中测试
5. **持续调试**：利用交互式终端解决问题
6. **优雅停止**：支持任务中途停止
7. **清理总结**：关闭会话，取消聚焦，整理成果

### Web项目开发示例
```python
# 1. 创建项目结构
create_folder("src")
create_folder("static") 
create_folder("templates")

# 2. 聚焦核心文件
focus_file("src/app.py")
focus_file("templates/index.html")
focus_file("static/style.css")

# 3. 开启开发环境
terminal_session(action="open", session_name="dev_server", working_dir="src")
terminal_input(command="python -m venv venv")
terminal_input(command="source venv/bin/activate")
terminal_input(command="pip install flask")

# 4. 启动开发服务器
terminal_input(command="python app.py")
sleep(3, "等待服务器启动")

# 5. 开启测试终端
terminal_session(action="open", session_name="test")
terminal_input(command="curl http://localhost:5000")
```

### 调试工作流程
```python
# 1. 重现问题
run_command("python main.py")  # 查看错误

# 2. 如果修改失败，使用搜索定位
run_command("grep -n 'error_function' main.py")

# 3. 使用行编辑精确修改
edit_lines(path="main.py", operation="replace_lines", 
           start_line=25, content="def fixed_function():")

# 4. 交互式调试
terminal_session(action="open", session_name="debug")
terminal_input(command="python")
terminal_input(command="import main")
terminal_input(command="main.test_function()")
```

## 优雅停止机制

### 停止原理
- **非强制中断**：等待当前操作完成后停止
- **状态清理**：停止后清理所有相关状态
- **连接管理**：按客户端连接ID管理停止标志

### 停止时机
- 每次工具调用完成后检查
- 主循环迭代结束时检查
- 不在工具执行过程中中断

### 前端交互
- 停止按钮状态管理（"停止" → "停止中..." → 恢复）
- WebSocket事件：`stop_task`, `stop_requested`, `task_stopped`

## 系统限制与配置

### 资源限制
- **终端会话**：最多3个并发会话
- **聚焦文件**：最多3个文件
- **终端缓冲**：每个终端20KB缓冲，5KB显示窗口
- **工具调用**：单任务最多20次迭代
- **连续相同工具**：8次触发警告

### 文件安全
- **路径验证**：禁止访问项目外目录
- **大小限制**：文件大小限制防止内存溢出
- **权限控制**：禁止访问系统敏感目录

## 监控和调试

### Web监控界面
- **主界面**：`http://localhost:8091` - 主要交互界面
- **终端监控**：`http://localhost:8091/terminal` - 实时终端监控
- **功能特性**：
  - 实时显示AI的所有操作
  - 多会话切换和管理
  - 停止控制和状态监控

### 调试工具
- **日志文件**：
  - `debug_stream.log` - WebSocket事件日志
  - `logs/` - 系统操作日志
- **浏览器调试**：Console显示前端调试信息
- **状态命令**：`/status` 查看系统完整状态

## 最佳实践

### 文件操作最佳实践
1. **明确目的**：根据用途选择读取或聚焦
2. **失败恢复**：modify_file失败时使用grep + edit_lines
3. **资源管理**：及时取消不需要的聚焦
4. **增量修改**：大修改分解为小步骤

### 终端使用最佳实践
1. **命名规范**：使用有意义的会话名称
2. **状态管理**：定期检查会话状态
3. **资源清理**：任务完成后关闭无用会话
4. **等待策略**：适时使用sleep等待操作完成

### 网络信息获取最佳实践
1. **优先搜索**：首先使用web_search获取信息
2. **谨慎提取**：仅在必要时使用extract_webpage
3. **成本意识**：注意网页提取对上下文的影响

### 开发工作流最佳实践
1. **计划优先**：开始前制定清晰的实现计划
2. **增量开发**：小步骤，频繁测试
3. **状态感知**：了解当前聚焦文件和终端状态
4. **优雅停止**：需要时使用停止功能
5. **清理总结**：完成后清理资源，提供总结

## 故障排除

### 常见问题及解决方案
1. **文件修改失败**：使用grep定位 + edit_lines修改
2. **终端无响应**：发送Ctrl+C或重启会话
3. **上下文溢出**：取消不必要的聚焦，清理对话历史
4. **停止功能异常**：检查WebSocket连接，重新加载页面
5. **网页提取失败**：检查API密钥配置和网络连接

### 性能优化建议
1. **合理使用聚焦**：只聚焦真正需要的核心文件
2. **及时清理**：定期清理对话历史和无用会话
3. **避免重复操作**：使用状态查询避免重复工具调用
4. **监控资源**：通过`/status`命令监控系统状态

这个系统的核心优势在于完整的对话管理、智能的文件操作策略、强大的持久化终端支持、以及优雅的停止机制，使AI能够像真正的开发者一样进行复杂的项目开发和调试工作。