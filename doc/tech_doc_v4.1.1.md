# AI Agent 系统技术文档 v4.2

## 版本更新 v4.2

### 新增功能：实时Token统计显示

在v4.1对话持久化功能基础上，新增了完整的Token使用统计和实时显示功能。

## Token统计功能详解

### 核心特性
1. **实时Token计算**：每次API调用时准确计算输入和输出token
2. **累计统计**：长期记录对话的总token消耗
3. **真实成本反映**：基于完整API请求内容计算，包含所有动态内容
4. **WebSocket实时推送**：前端实时显示token使用情况

### Token计算逻辑

#### 输入Token统计
- **计算时机**：用户发送消息后，构建完整API请求时
- **包含内容**：
  - 完整系统提示词（含项目信息、文件树、记忆）
  - 完整对话历史
  - 聚焦文件内容
  - 终端内容
  - 工具定义
- **计算方法**：使用tiktoken的`cl100k_base`编码器

#### 输出Token统计  
- **计算时机**：AI响应完成后，工具执行前
- **包含内容**：
  - AI思考内容（thinking）
  - AI文本回复
  - 工具调用JSON格式
- **排除内容**：工具返回结果（系统生成，非AI输出）

### 数据结构

#### 对话文件中的Token统计
```json
{
  "token_statistics": {
    "total_input_tokens": 15420,
    "total_output_tokens": 8930,
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

#### WebSocket广播数据
```json
{
  "conversation_id": "conv_xxx",
  "cumulative_input_tokens": 15420,
  "cumulative_output_tokens": 8930,  
  "cumulative_total_tokens": 24350,
  "updated_at": "2025-01-15T10:30:00Z"
}
```

### API接口

#### Token统计相关API
```http
GET /api/conversations/{id}/token-statistics
```
返回指定对话的详细token统计信息。

### 实现架构

#### 后端实现
1. **ConversationManager**：
   - `update_token_statistics()` - 更新累计统计
   - `get_token_statistics()` - 获取统计数据
   - `calculate_conversation_tokens()` - 计算当前上下文token

2. **ContextManager**：
   - `calculate_input_tokens()` - 计算输入token
   - `calculate_output_tokens()` - 计算输出token
   - `update_token_statistics()` - 更新并广播统计

3. **WebServer**：
   - 在用户消息后立即计算输入token
   - 在AI响应完成后计算输出token
   - 通过WebSocket实时广播更新

#### 前端显示（待实现）
- 实时显示当前对话的累计token使用
- 显示输入/输出token分布
- 成本预警和趋势分析

### 技术细节

#### Token计算准确性
- 使用与OpenAI兼容的tiktoken编码器
- 计算完整API请求内容，不遗漏任何部分
- 避免重复计算历史内容

#### 性能优化
- 增量统计更新，避免重复计算
- 容错机制，统计失败不影响主功能
- 异步广播，不阻塞主流程

#### 向后兼容
- 老对话文件自动初始化token统计结构
- 数据验证和修复机制
- 渐进式功能增强

### Bug修复记录

#### v4.2修复的关键问题
1. **用户消息重复发送**：修复了`build_messages`中重复添加最新用户消息的bug
2. **Token计算精度**：使用真实API请求内容计算，而非估算
3. **统计时机优化**：避免在多轮工具调用中重复计算输入token

## 使用建议

### 成本控制
- 监控聚焦文件数量，大文件会显著增加token消耗
- 合理使用记忆功能，避免记忆内容过长
- 关注累计token统计，及时了解使用成本

### 性能优化
- 定期清理不必要的对话历史
- 避免同时聚焦多个大文件
- 使用简洁的项目结构描述

## 后续规划

### 前端增强
- 可视化token使用趋势
- 成本预警阈值设置
- 按功能模块的token分解显示

### 多模型支持
- 支持不同模型的token计算（如Qwen分词器）
- 模型特定的token计算优化
- 成本对比分析

---

*v4.2更新：2025年1月 - 完整Token统计功能*