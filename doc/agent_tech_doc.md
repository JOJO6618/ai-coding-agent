# AI Agent 系统技术文档

## 系统概述

这是一个基于 DeepSeek v3.1 的智能自动化操作系统，能够在指定文件夹内执行各种任务。系统采用单终端架构，通过工具调用（Function Calling）实现文件操作、代码执行、网络搜索等功能。

## 核心设计理念

1. **对话连续性**：单次程序运行期间保持完整对话历史
2. **思考过程隔离**：历史对话不包含思考，当前回答包含所有思考
3. **工具调用循环**：支持无限次工具调用直到任务完成
4. **文件备注同步**：文件和备注始终保持一一对应

## 文件结构和功能

### 入口文件
- **`main.py`** - 程序入口
  - 初始化系统
  - 设置项目路径
  - 选择思考模式
  - 启动主终端

### 配置文件
- **`config.py`** - 所有系统配置
  - API密钥（DeepSeek、Tavily）
  - 文件路径限制
  - 超时设置
  - 输出格式定义

### 核心模块 (`core/`)

#### `main_terminal.py` - 主终端（最重要）
- **功能**：处理用户输入、管理对话流程
- **关键方法**：
  - `run()` - 主循环，处理用户输入
  - `handle_task()` - 处理任务，调用API
  - `handle_tool_call()` - 执行工具调用
  - `define_tools()` - 定义可用工具
  - `build_messages()` - 构建包含历史的消息列表

#### `task_executor.py` - 任务执行器（已废弃）
- 原双终端架构的遗留，现在未使用

### 工具模块 (`modules/`)

#### `file_manager.py` - 文件操作
- **功能**：所有文件和文件夹操作
- **关键方法**：
  - `create_file()` - 创建文件
  - `delete_file()` - 删除文件（返回action标记）
  - `rename_file()` - 重命名（返回新旧路径）
  - `read_file()` - 读取文件内容
  - `modify_file()` - 修改文件（追加/替换/清空）

#### `search_engine.py` - 网络搜索
- **功能**：Tavily API搜索
- **关键方法**：
  - `search()` - 执行搜索
  - `search_with_summary()` - 搜索并格式化（避免重复调用）

#### `terminal_ops.py` - 终端操作
- **功能**：执行Python代码和终端命令
- **关键方法**：
  - `run_python_code()` - 执行Python代码
  - `run_command()` - 执行终端命令
- **注意**：所有Python命令使用`python3`

#### `memory_manager.py` - 记忆管理
- **功能**：管理主记忆和任务记忆
- **记忆文件用途**：长期知识存储，不是对话记录

### 工具模块 (`utils/`)

#### `api_client.py` - API客户端（核心）
- **功能**：与DeepSeek API通信
- **关键方法**：
  - `chat_with_tools()` - 带工具调用的对话（支持多轮）
  - `simple_chat()` - 简单对话（无工具）
- **重要逻辑**：
  - 流式输出处理
  - 思考内容显示（💭标记）
  - 工具调用循环（最多20次）
  - 上下文传递（使用`<think>`标签）

#### `context_manager.py` - 上下文管理
- **功能**：管理对话历史和文件备注
- **关键方法**：
  - `get_project_structure()` - 获取文件结构（自动清理无效备注）
  - `add_conversation()` - 添加对话记录
  - `update_annotation()` - 更新文件备注
- **备注同步**：每次构建上下文时清理不存在文件的备注

#### `logger.py` - 日志系统
- 记录错误和操作日志

### 提示模板 (`prompts/`)
- **`main_system.txt`** - 唯一使用的系统提示
- 其他文件未使用（可删除）

## 文件协作关系

### 对话流程
```
用户输入(main_terminal) 
→ 构建消息(包含历史+系统提示) 
→ API调用(api_client) 
→ 工具执行(main_terminal.handle_tool_call) 
→ 具体操作(file_manager/search_engine等) 
→ 返回结果 
→ 继续或结束
```

### 上下文流转
```
1. main_terminal 从 context_manager 获取对话历史
2. 添加当前用户输入到历史
3. 发送给 api_client（包含完整历史）
4. 保存AI回复到历史（不含思考）
5. 下次对话时包含所有历史
```

### 文件备注同步
```
1. 创建文件 → main_terminal 添加备注
2. 删除文件 → main_terminal 删除备注
3. 重命名文件 → main_terminal 更新备注key
4. 手动删除文件 → context_manager 自动清理
```

## 常见修改场景

### 修改API行为
- **文件**：`utils/api_client.py`
- **位置**：`chat_with_tools()` 方法
- **注意**：处理思考内容的显示和传递

### 添加新工具
1. **定义工具**：`main_terminal.py` 的 `define_tools()`
2. **处理调用**：`main_terminal.py` 的 `handle_tool_call()`
3. **实现功能**：对应的 `modules/` 文件

### 修改思考显示
- **文件**：`utils/api_client.py`
- **位置**：搜索 `💭 [正在思考]` 和 `💭 [思考结束]`
- **注意**：有多处需要同时修改

### 修改对话历史逻辑
- **文件**：`main_terminal.py` 和 `context_manager.py`
- **关键**：`add_conversation()` 和 `build_messages()`

### 修改文件操作权限
- **文件**：`config.py` 的 `FORBIDDEN_PATHS`
- **验证**：`file_manager.py` 的 `_validate_path()`

### 修改命令系统
- **文件**：`main_terminal.py`
- **位置**：`commands` 字典和对应方法
- **注意**：命令不应记录到对话历史

## 关键设计决策

### 为什么使用单终端架构？
- 原设计是双终端（主终端+任务执行器）
- 现简化为单终端，所有功能在主终端完成
- `task_executor.py` 已废弃但保留

### 思考内容如何处理？
- **显示**：使用 `💭` 标记，用户可见
- **传递**：当前回答中用 `<think>` 标签包裹
- **历史**：不保存到对话历史，避免污染

### 工具调用如何结束？
- 模型不再调用工具且返回文本时结束
- 最多20次迭代防止无限循环
- 连续8次相同工具会触发警告

### 文件备注如何保持同步？
- 程序操作：立即更新备注
- 手动操作：下次构建上下文时清理
- 备注key = 相对路径

## 调试技巧

### 查看完整上下文
在 `main_terminal.py` 的 `build_messages()` 后添加：
```python
print(json.dumps(messages, ensure_ascii=False, indent=2))
```

### 追踪工具调用
在 `api_client.py` 的工具执行部分添加日志

### 检查思考内容
搜索 `current_thinking` 变量查看思考内容处理

## 注意事项

1. **不要混淆记忆文件和对话历史**
   - 记忆文件：长期知识
   - 对话历史：当前会话

2. **流式输出的复杂性**
   - 思考和内容可能交错
   - 需要正确管理 `in_thinking` 状态

3. **工具结果格式化**
   - `read_file` 需要特殊处理
   - 搜索结果需要格式化为摘要

4. **Python命令**
   - 所有地方使用 `python3` 而非 `python`

5. **上下文长度**
   - DeepSeek支持128K但要注意效率
   - 文件内容会占用大量token

这个系统的核心在于正确管理对话历史和工具调用循环，理解这两点就能理解整个系统。