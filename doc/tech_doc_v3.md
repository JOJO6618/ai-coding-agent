# AI Agent 系统技术文档 v3.0

## 系统概述

这是一个基于 DeepSeek v3.1 的智能自动化操作系统，能够在指定文件夹内执行各种任务。系统采用单终端架构，通过工具调用（Function Calling）实现文件操作、代码执行、网络搜索、**持久化终端管理**等功能。支持命令行（CLI）和Web两种运行模式，并提供**实时终端监控界面**。

## 核心设计理念

1. **对话连续性**：单次程序运行期间保持完整对话历史，包括工具调用结果
2. **思考模式优化**：两种模式平衡效率与深度（快速模式/思考模式）
3. **工具调用循环**：支持多轮工具调用直到任务完成
4. **文件备注同步**：文件和备注始终保持一一对应
5. **完整上下文传递**：确保API能看到完整的对话流程
6. **持久化终端会话**：保持终端状态，支持交互式程序

## 架构更新（v3.0）

### 新增：持久化终端子系统

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
│         └── terminal_status         │
├─────────────────────────────────────┤
│    Web终端监控器 (xterm.js)         │
│         ├── 实时显示                │
│         ├── 多会话标签              │
│         └── 命令历史                │
└─────────────────────────────────────┘
```

## 运行模式

### 快速模式
- 不进行深度思考，直接响应
- 适合简单任务和快速交互
- 响应速度快，token消耗少

### 思考模式（智能思考）
- 每个新任务首次调用进行深度思考
- 同一任务的后续调用使用快速响应
- 思考内容会注入到后续对话中保持连贯性
- 平衡了深度理解和响应效率

## 文件结构和功能

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
  - **终端配置**（新增）：
    - MAX_TERMINALS = 3
    - TERMINAL_BUFFER_SIZE = 20000
    - TERMINAL_DISPLAY_SIZE = 5000
    - TERMINAL_TIMEOUT = 300

### 核心模块 (`core/`)

#### `main_terminal.py` - 主终端（核心）
- **功能**：处理用户输入、管理对话流程
- **新增功能**：
  - 集成TerminalManager
  - 处理terminal_session和terminal_input工具
  - 注入活动终端内容到上下文
- **关键方法**：
  - `run()` - 主循环，处理用户输入
  - `handle_task()` - 处理任务，调用API
  - `handle_tool_call()` - 执行工具调用（包括终端工具）
  - `define_tools()` - 定义可用工具（包括终端工具）
  - `build_messages()` - 构建消息（注入终端内容）

#### `web_terminal.py` - Web终端
- **功能**：继承MainTerminal，适配Web环境
- **特点**：
  - 禁用print输出（web_mode=True）
  - 提供状态查询接口
  - 支持WebSocket通信
  - 终端事件广播

#### `task_executor.py` - 任务执行器（已废弃）
- 原双终端架构的遗留，现在未使用

### 工具模块 (`modules/`)

#### `file_manager.py` - 文件操作
- **功能**：所有文件和文件夹操作
- **关键方法**：
  - `create_file()` - 创建文件
  - `delete_file()` - 删除文件
  - `rename_file()` - 重命名
  - `read_file()` - 读取文件内容
  - `modify_file()` - 修改文件

#### `persistent_terminal.py` - 持久化终端（新增）
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

#### `terminal_manager.py` - 终端管理器（新增）
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

#### `terminal_ops.py` - 一次性终端操作
- **功能**：执行Python代码和终端命令（一次性）
- **关键方法**：
  - `run_python_code()` - 执行Python代码
  - `run_command()` - 执行终端命令
- **注意**：与持久化终端互补，用于快速一次性操作

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

#### `terminal_factory.py` - 终端工厂（新增）
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
- **关键方法**：
  - `get_project_structure()` - 获取文件结构
  - `add_conversation()` - 添加对话记录
  - `add_tool_result()` - 添加工具结果
  - `update_annotation()` - 更新文件备注

#### `logger.py` - 日志系统
- 记录错误和操作日志

### Web服务 (`web_server.py`)
- **功能**：提供Web界面服务
- **新增功能**：
  - `/terminal` 路由 - 终端监控页面
  - 终端WebSocket事件处理
  - 终端广播机制
- **特点**：
  - Flask + SocketIO实现
  - 实时流式输出
  - 文件树动态更新

### 终端监控页面 (`static/terminal.html`)（新增）
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

### 提示模板 (`prompts/`)
- **`main_system.txt`** - 主系统提示（已更新）
  - 包含持久化终端使用策略
  - 终端管理最佳实践

## 新增工具定义

### terminal_session
```python
{
    "name": "terminal_session",
    "description": "管理持久化终端会话",
    "parameters": {
        "action": ["open", "close", "list", "switch"],
        "session_name": "终端会话名称",
        "working_dir": "工作目录（可选）"
    }
}
```

### terminal_input
```python
{
    "name": "terminal_input",
    "description": "向活动终端发送命令或输入",
    "parameters": {
        "command": "要执行的命令",
        "session_name": "目标终端（可选）",
        "wait_for_output": "是否等待输出"
    }
}
```

## 文件协作关系

### 对话流程（修复版）
```
用户输入(main_terminal) 
→ 构建消息(包含完整历史+系统提示+聚焦文件+活动终端) 
→ API调用(api_client) 
→ 工具执行(main_terminal.handle_tool_call) 
→ 保存工具结果到历史
→ 具体操作(file_manager/terminal_manager等) 
→ WebSocket广播(如果是Web模式)
→ 返回结果 
→ 继续或结束
```

### 终端事件流
```
AI决定使用终端
→ terminal_session(open) 
→ TerminalManager.open_terminal()
→ PersistentTerminal.start()
→ subprocess.Popen创建进程
→ 广播terminal_started事件
→ terminal_input(command)
→ 进程stdin写入
→ 异步读取stdout
→ 广播terminal_output事件
→ Web终端实时显示
```

## 关键技术细节

### 持久化终端实现
1. **进程管理**：subprocess.Popen创建长期运行进程
2. **异步I/O**：单独线程读取输出，避免阻塞
3. **缓冲管理**：20KB总缓冲，5KB显示窗口
4. **交互检测**：识别等待输入的提示符
5. **广播机制**：通过WebSocket实时推送

### 终端与一次性命令的选择
- **持久化终端**：交互式程序、长时间运行、需要状态
- **一次性命令**：快速查询、独立任务、简单操作

### 文件聚焦机制
- 最多同时聚焦3个文件
- 聚焦文件内容持续注入上下文
- 文件修改自动更新聚焦内容
- 删除/重命名自动处理聚焦状态

### 上下文大小管理
- 自动检查上下文使用率
- 聚焦文件单独注入（系统消息）
- 活动终端内容注入（系统消息）
- 对话历史保留最近记录

## 使用场景示例

### 交互式Python调试
```python
# 1. 打开Python REPL
terminal_session(action="open", session_name="python_debug")
terminal_input(command="python3")

# 2. 导入模块并调试
terminal_input(command="import sys")
terminal_input(command="sys.path")
terminal_input(command="from my_module import my_function")
terminal_input(command="result = my_function(test_data)")
terminal_input(command="print(result)")

# 3. 退出REPL
terminal_input(command="exit()")
terminal_session(action="close", session_name="python_debug")
```

### 运行开发服务器
```python
# 1. 启动服务器
terminal_session(action="open", session_name="dev_server", working_dir="project")
terminal_input(command="npm run dev")

# 2. 在另一个终端测试
terminal_session(action="open", session_name="test")
terminal_input(command="curl http://localhost:3000/api/health")

# 3. 停止服务器
terminal_input(command="^C", session_name="dev_server")
```

### 数据库交互
```python
# 1. 打开数据库客户端
terminal_session(action="open", session_name="db")
terminal_input(command="psql -U user -d database")

# 2. 执行查询
terminal_input(command="SELECT * FROM users LIMIT 10;")
terminal_input(command="\\d+ users")

# 3. 退出
terminal_input(command="\\q")
```

## 系统限制

1. **工具调用次数**：单任务最多20次迭代
2. **聚焦文件数量**：最多3个
3. **终端会话数量**：最多3个并发会话
4. **终端缓冲区**：每个终端20KB缓冲
5. **连续相同工具**：8次触发警告
6. **上下文长度**：受DeepSeek API限制

## 监控和调试

### Web终端监控器
- 访问地址：`http://localhost:8091/terminal`
- 功能：
  - 实时查看所有终端操作
  - AI命令显示为绿色
  - 支持多会话切换
  - 显示命令历史和统计

### 调试日志
- `debug_stream.log` - WebSocket事件日志
- `logs/` - 系统操作日志
- 浏览器Console - 前端调试信息

## 版本更新说明

### v3.0 主要新增功能
1. **持久化终端系统**：支持交互式程序和长时间运行任务
2. **终端监控界面**：实时查看AI的终端操作
3. **跨平台支持**：自动选择合适的shell
4. **终端管理器**：多会话管理和切换
5. **WebSocket广播**：实时事件推送

### v2.0 主要改进
1. **修复工具调用中断**：确保工具结果保存到历史
2. **简化思考模式**：从三种模式简化为两种
3. **完善消息流**：支持完整的对话流程
4. **优化Web体验**：改进流式输出和状态更新

### 从 v2.x 升级注意事项
1. 新增配置项需要更新 `config.py`
2. 需要安装新的依赖文件
3. Web界面新增终端监控页面
4. 系统提示词已更新，包含终端使用策略

## 最佳实践

1. **选择合适的工具**
   - 简单命令用 `run_command`
   - 交互程序用终端会话
   - 文件操作合理使用聚焦

2. **管理终端会话**
   - 命名要有意义
   - 及时关闭不用的会话
   - 切换前确认目标会话

3. **监控系统状态**
   - 定期使用 `/status` 查看
   - 注意上下文使用率
   - 关注终端会话数量

4. **处理长任务**
   - 使用持久化终端
   - 适时清理对话历史
   - 合理使用记忆系统

## 故障排除

### 终端无响应
- 发送 Ctrl+C（输入 `^C`）
- 检查是否在等待输入
- 必要时关闭重开会话

### 显示异常
- 刷新浏览器页面
- 清除浏览器缓存
- 检查终端编码设置

### WebSocket连接失败
- 确认服务器正在运行
- 检查防火墙设置
- 查看debug_stream.log

这个系统的核心优势在于完整的对话管理、智能的思考模式切换、以及强大的持久化终端支持，使AI能够像真正的开发者一样进行交互式编程和调试。