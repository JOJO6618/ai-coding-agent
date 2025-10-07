# ========== api_client.py ==========
# utils/api_client.py - DeepSeek API 客户端（支持Web模式）- 简化版

import httpx
import json
import asyncio
from typing import List, Dict, Optional, AsyncGenerator
from config import API_BASE_URL, API_KEY, MODEL_ID, OUTPUT_FORMATS

class DeepSeekClient:
    def __init__(self, thinking_mode: bool = True, web_mode: bool = False):
        self.api_base_url = API_BASE_URL
        self.api_key = API_KEY
        self.model_id = MODEL_ID
        self.thinking_mode = thinking_mode  # True=智能思考模式, False=快速模式
        self.web_mode = web_mode  # Web模式标志，用于禁用print输出
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # 每个任务的独立状态
        self.current_task_first_call = True  # 当前任务是否是第一次调用
        self.current_task_thinking = ""  # 当前任务的思考内容
    
    def _print(self, message: str, end: str = "\n", flush: bool = False):
        """安全的打印函数，在Web模式下不输出"""
        if not self.web_mode:
            print(message, end=end, flush=flush)
    
    def start_new_task(self):
        """开始新任务（重置任务级别的状态）"""
        self.current_task_first_call = True
        self.current_task_thinking = ""
    
    def get_current_thinking_mode(self) -> bool:
        """获取当前应该使用的思考模式"""
        if not self.thinking_mode:
            # 快速模式，始终不使用思考
            return False
        else:
            # 思考模式：当前任务的第一次用思考，后续不用
            return self.current_task_first_call
    
    def _validate_json_string(self, json_str: str) -> tuple:
        """
        验证JSON字符串的完整性
        
        Returns:
            (is_valid: bool, error_message: str, parsed_data: dict or None)
        """
        if not json_str or not json_str.strip():
            return True, "", {}
        
        # 检查基本的JSON结构标记
        stripped = json_str.strip()
        if not stripped.startswith('{') or not stripped.endswith('}'):
            return False, "JSON字符串格式不完整（缺少开始或结束大括号）", None
        
        # 检查引号配对
        in_string = False
        escape_next = False
        quote_count = 0
        
        for char in stripped:
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"':
                quote_count += 1
                in_string = not in_string
        
        if in_string:
            return False, "JSON字符串中存在未闭合的引号", None
        
        # 尝试解析JSON
        try:
            parsed_data = json.loads(stripped)
            return True, "", parsed_data
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {str(e)}", None
    
    def _safe_tool_arguments_parse(self, arguments_str: str, tool_name: str) -> tuple:
        """
        安全地解析工具参数，增强JSON修复能力
        
        Returns:
            (success: bool, arguments: dict, error_message: str)
        """
        if not arguments_str or not arguments_str.strip():
            return True, {}, ""
        
        # 长度检查
        max_length = 999999999  # 50KB限制
        if len(arguments_str) > max_length:
            return False, {}, f"参数过长({len(arguments_str)}字符)，超过{max_length}字符限制"
        
        # 尝试直接解析JSON
        try:
            parsed_data = json.loads(arguments_str)
            return True, parsed_data, ""
        except json.JSONDecodeError as e:
            # JSON解析失败，尝试修复常见问题
            return self._attempt_json_repair(arguments_str, str(e))
    
    def _attempt_json_repair(self, json_str: str, error_msg: str) -> tuple:
        """
        尝试修复常见的JSON格式错误
        
        Returns:
            (success: bool, arguments: dict, error_message: str)
        """
        original = json_str.strip()
        
        # 1. 修复未闭合的字符串（最常见问题）
        if "Unterminated string" in error_msg:
            # 查找最后一个未闭合的引号
            quote_count = 0
            last_quote_pos = -1
            escape_next = False
            
            for i, char in enumerate(original):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    quote_count += 1
                    last_quote_pos = i
            
            # 如果引号数量为奇数，添加闭合引号
            if quote_count % 2 == 1:
                repaired = original + '"'
                # 尝试闭合JSON结构
                if not repaired.rstrip().endswith('}'):
                    repaired = repaired + '}'
                
                try:
                    parsed_data = json.loads(repaired)
                    return True, parsed_data, f"已修复未闭合字符串: 添加了闭合引号和括号"
                except:
                    pass
        
        # 2. 修复未闭合的JSON对象
        if not original.rstrip().endswith('}') and original.lstrip().startswith('{'):
            repaired = original.rstrip() + '}'
            try:
                parsed_data = json.loads(repaired)
                return True, parsed_data, f"已修复未闭合对象: 添加了闭合括号"
            except:
                pass
        
        # 3. 处理截断的JSON（移除不完整的最后一个键值对）
        try:
            # 找到最后一个完整的键值对
            last_comma = original.rfind(',')
            if last_comma > 0:
                truncated = original[:last_comma] + '}'
                parsed_data = json.loads(truncated)
                return True, parsed_data, f"已修复截断JSON: 移除了不完整的最后部分"
        except:
            pass
        
        # 4. 尝试修复转义字符问题
        if '\\' in original:
            try:
                # 简单的转义字符修复
                repaired = original.replace('\\"', '"').replace('\\n', '\\n').replace('\\\\', '\\')
                parsed_data = json.loads(repaired)
                return True, parsed_data, f"已修复转义字符问题"
            except:
                pass
        
        # 所有修复尝试都失败
        preview_length = 200
        preview = original[:preview_length] + "..." if len(original) > preview_length else original
        
        return False, {}, f"JSON解析失败且无法自动修复: {error_msg}\n参数预览: {preview}"
    async def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        stream: bool = True
    ) -> AsyncGenerator[Dict, None]:
        """
        异步调用DeepSeek API
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            stream: 是否流式输出
        
        Yields:
            响应内容块
        """
        # 检查API密钥
        if not self.api_key or self.api_key == "your-deepseek-api-key":
            self._print(f"{OUTPUT_FORMATS['error']} API密钥未配置，请在config.py中设置API_KEY")
            return
        
        # 决定是否使用思考模式
        current_thinking_mode = self.get_current_thinking_mode()
        
        # 如果是思考模式且不是当前任务的第一次，显示提示
        if self.thinking_mode and not self.current_task_first_call:
            self._print(f"{OUTPUT_FORMATS['info']} [任务内快速模式] 使用本次任务的思考继续处理...")
        
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": stream,
            "thinking": {"type": "enabled" if current_thinking_mode else "disabled"}
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            async with httpx.AsyncClient(http2=True, timeout=300) as client:
                if stream:
                    async with client.stream(
                        "POST",
                        f"{self.api_base_url}/chat/completions",
                        json=payload,
                        headers=self.headers
                    ) as response:
                        # 检查响应状态
                        if response.status_code != 200:
                            error_text = await response.aread()
                            self._print(f"{OUTPUT_FORMATS['error']} API请求失败 ({response.status_code}): {error_text}")
                            return
                            
                        async for line in response.aiter_lines():
                            if line.startswith("data:"):
                                json_str = line[5:].strip()
                                if json_str == "[DONE]":
                                    break
                                
                                try:
                                    data = json.loads(json_str)
                                    yield data
                                except json.JSONDecodeError:
                                    continue
                else:
                    response = await client.post(
                        f"{self.api_base_url}/chat/completions",
                        json=payload,
                        headers=self.headers
                    )
                    if response.status_code != 200:
                        error_text = response.text
                        self._print(f"{OUTPUT_FORMATS['error']} API请求失败 ({response.status_code}): {error_text}")
                        return
                    yield response.json()
                    
        except httpx.ConnectError:
            self._print(f"{OUTPUT_FORMATS['error']} 无法连接到API服务器，请检查网络连接")
        except httpx.TimeoutException:
            self._print(f"{OUTPUT_FORMATS['error']} API请求超时")
        except Exception as e:
            self._print(f"{OUTPUT_FORMATS['error']} API调用异常: {e}")
    
    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        tool_handler: callable
    ) -> str:
        """
        带工具调用的对话（支持多轮）
        
        Args:
            messages: 消息列表
            tools: 工具定义
            tool_handler: 工具处理函数
        
        Returns:
            最终回答
        """
        final_response = ""
        max_iterations = 200  # 最大迭代次数
        iteration = 0
        all_tool_results = []  # 记录所有工具调用结果
        
        # 如果是思考模式且不是当前任务的第一次调用，注入本次任务的思考
        # 注意：这里重置的是当前任务的第一次调用标志，确保新用户请求重新思考
        # 只有在同一个任务的多轮迭代中才应该注入
        # 对于新的用户请求，应该重新开始思考，而不是使用之前的思考内容
        # 只有在当前任务有思考内容且不是第一次调用时才注入
        if (self.thinking_mode and 
            not self.current_task_first_call and 
            self.current_task_thinking and
            iteration == 0):  # 只在第一次迭代时注入，避免多次注入
            # 在messages末尾添加一个系统消息，包含本次任务的思考
            thinking_context = f"\n=== 📋 本次任务的思考 ===\n{self.current_task_thinking}\n=== 思考结束 ===\n提示：这是本次任务的初始思考，你可以基于此继续处理。"
            messages.append({
                "role": "system",
                "content": thinking_context
            })
        
        while iteration < max_iterations:
            iteration += 1
            
            # 调用API（始终提供工具定义）
            full_response = ""
            tool_calls = []
            current_thinking = ""
            
            # 状态标志
            in_thinking = False
            thinking_printed = False
            
            # 获取当前是否应该显示思考
            should_show_thinking = self.get_current_thinking_mode()
            
            async for chunk in self.chat(messages, tools, stream=True):
                if "choices" not in chunk:
                    continue
                    
                delta = chunk["choices"][0].get("delta", {})
                
                # 处理思考内容（只在思考模式开启时）
                if "reasoning_content" in delta and should_show_thinking:
                    reasoning_content = delta["reasoning_content"]
                    if reasoning_content:  # 只处理非空内容
                        if not in_thinking:
                            self._print("💭 [正在思考]\n", end="", flush=True)
                            in_thinking = True
                            thinking_printed = True
                        current_thinking += reasoning_content
                        self._print(reasoning_content, end="", flush=True)
                
                # 处理正常内容 - 独立的if，不是elif
                if "content" in delta:
                    content = delta["content"]
                    if content:  # 只处理非空内容
                        # 如果之前在输出思考，先结束思考输出
                        if in_thinking:
                            self._print("\n\n💭 [思考结束]\n\n", end="", flush=True)
                            in_thinking = False
                        full_response += content
                        self._print(content, end="", flush=True)
                
                # 收集工具调用 - 改进的拼接逻辑
                # 收集工具调用 - 修复JSON分片问题
                if "tool_calls" in delta:
                    for tool_call in delta["tool_calls"]:
                        tool_index = tool_call.get("index", 0)
                        
                        # 查找或创建对应索引的工具调用
                        existing_call = None
                        for existing in tool_calls:
                            if existing.get("index") == tool_index:
                                existing_call = existing
                                break
                        
                        if not existing_call and tool_call.get("id"):
                            # 创建新的工具调用
                            new_call = {
                                "id": tool_call.get("id"),
                                "index": tool_index,
                                "type": tool_call.get("type", "function"),
                                "function": {
                                    "name": tool_call.get("function", {}).get("name", ""),
                                    "arguments": ""
                                }
                            }
                            tool_calls.append(new_call)
                            existing_call = new_call
                        
                        # 安全地拼接arguments - 简单字符串拼接，不尝试JSON验证
                        if existing_call and "function" in tool_call and "arguments" in tool_call["function"]:
                            new_args = tool_call["function"]["arguments"]
                            if new_args:  # 只拼接非空内容
                                existing_call["function"]["arguments"] += new_args
            
            self._print()  # 最终换行
            
            # 如果思考还没结束（只调用工具没有文本），手动结束
            if in_thinking:
                self._print("\n💭 [思考结束]\n")
            
            # 在思考模式下，如果是当前任务的第一次调用且有思考内容，保存它
            if self.thinking_mode and self.current_task_first_call and current_thinking:
                self.current_task_thinking = current_thinking
                self.current_task_first_call = False  # 标记当前任务的第一次调用已完成
            
            # 如果没有工具调用，说明完成了
            if not tool_calls:
                if full_response:  # 有正常回复，任务完成
                    final_response = full_response
                    break
                elif iteration == 1:  # 第一次就没有工具调用也没有内容，可能有问题
                    self._print(f"{OUTPUT_FORMATS['warning']} 模型未返回内容")
                    break
            
            # 构建助手消息 - 始终包含所有收集到的内容
            assistant_content_parts = []
            
            # 添加思考内容（如果有）
            if current_thinking:
                assistant_content_parts.append(f"<think>\n{current_thinking}\n</think>")
            
            # 添加正式回复内容（如果有）
            if full_response:
                assistant_content_parts.append(full_response)
            
            # 添加工具调用说明
            if tool_calls:
                tool_names = [tc['function']['name'] for tc in tool_calls]
                assistant_content_parts.append(f"执行工具: {', '.join(tool_names)}")
            
            # 合并所有内容
            assistant_content = "\n".join(assistant_content_parts) if assistant_content_parts else "执行工具调用"
            
            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls
            }
            
            messages.append(assistant_message)
            
            # 执行所有工具调用 - 使用鲁棒的参数解析
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments_str = tool_call["function"]["arguments"]
                
                # 使用改进的参数解析方法，增强JSON修复能力
                success, arguments, error_msg = self._safe_tool_arguments_parse(arguments_str, function_name)
                
                if not success:
                    self._print(f"{OUTPUT_FORMATS['error']} 工具参数解析失败: {error_msg}")
                    self._print(f"  工具名称: {function_name}")
                    self._print(f"  参数长度: {len(arguments_str)} 字符")
                    
                    # 返回详细的错误信息给模型
                    error_response = {
                        "success": False,
                        "error": error_msg,
                        "tool_name": function_name,
                        "arguments_length": len(arguments_str),
                        "suggestion": "请检查参数格式或减少参数长度后重试"
                    }
                    
                    # 如果参数过长，提供分块建议
                    if len(arguments_str) > 10000:
                        error_response["suggestion"] = "参数过长，建议分块处理或使用更简洁的内容"
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": json.dumps(error_response, ensure_ascii=False)
                    })
                    
                    # 记录失败的调用，防止死循环检测失效
                    all_tool_results.append({
                        "tool": function_name,
                        "args": {"parse_error": error_msg, "length": len(arguments_str)},
                        "result": f"参数解析失败: {error_msg}"
                    })
                    continue
                
                self._print(f"\n{OUTPUT_FORMATS['action']} 调用工具: {function_name}")
                
                # 额外的参数长度检查（针对特定工具）
                if function_name == "modify_file" and "content" in arguments:
                    content_length = len(arguments.get("content", ""))
                    if content_length > 9999999999:  # 降低到50KB限制
                        error_msg = f"内容过长({content_length}字符)，超过50KB限制"
                        self._print(f"{OUTPUT_FORMATS['warning']} {error_msg}")
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": function_name,
                            "content": json.dumps({
                                "success": False,
                                "error": error_msg,
                                "suggestion": "请将内容分成多个小块分别修改，或使用replace操作只修改必要部分"
                            }, ensure_ascii=False)
                        })
                        
                        all_tool_results.append({
                            "tool": function_name,
                            "args": arguments,
                            "result": error_msg
                        })
                        continue
                
                tool_result = await tool_handler(function_name, arguments)
                
                # 解析工具结果，提取关键信息
                try:
                    result_data = json.loads(tool_result)
                    # 特殊处理read_file的结果
                    if function_name == "read_file" and result_data.get("success"):
                        file_content = result_data.get("content", "")
                        # 将文件内容作为明确的上下文信息
                        tool_result_msg = f"文件 {result_data.get('path')} 的内容:\n```\n{file_content}\n```\n文件大小: {result_data.get('size')} 字节"
                    else:
                        tool_result_msg = tool_result
                except:
                    tool_result_msg = tool_result
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": tool_result_msg
                })
                
                # 记录工具结果
                all_tool_results.append({
                    "tool": function_name,
                    "args": arguments,
                    "result": tool_result_msg
                })
            
            # 如果连续多次调用同样的工具，可能陷入循环
            if len(all_tool_results) >= 8:
                recent_tools = [r["tool"] for r in all_tool_results[-8:]]
                if len(set(recent_tools)) == 1:  # 最近8次都是同一个工具
                    self._print(f"\n{OUTPUT_FORMATS['warning']} 检测到重复操作，停止执行")
                    break
        
        if iteration >= max_iterations:
            self._print(f"\n{OUTPUT_FORMATS['warning']} 达到最大迭代次数限制")
        
        return final_response
    
    async def simple_chat(self, messages: List[Dict]) -> tuple:
        """
        简单对话（无工具调用）
        
        Args:
            messages: 消息列表
        
        Returns:
            (模型回答, 思考内容)
        """
        full_response = ""
        thinking_content = ""
        in_thinking = False
        
        # 获取当前是否应该显示思考
        should_show_thinking = self.get_current_thinking_mode()
        
        # 如果是思考模式且不是当前任务的第一次调用，注入本次任务的思考
        if self.thinking_mode and not self.current_task_first_call and self.current_task_thinking:
            thinking_context = f"\n=== 📋 本次任务的思考 ===\n{self.current_task_thinking}\n=== 思考结束 ===\n"
            messages.append({
                "role": "system",
                "content": thinking_context
            })
        
        try:
            async for chunk in self.chat(messages, tools=None, stream=True):
                if "choices" not in chunk:
                    continue
                    
                delta = chunk["choices"][0].get("delta", {})
                
                # 处理思考内容
                if "reasoning_content" in delta and should_show_thinking:
                    reasoning_content = delta["reasoning_content"]
                    if reasoning_content:  # 只处理非空内容
                        if not in_thinking:
                            self._print("💭 [正在思考]\n", end="", flush=True)
                            in_thinking = True
                        thinking_content += reasoning_content
                        self._print(reasoning_content, end="", flush=True)
                
                # 处理正常内容 - 独立的if而不是elif
                if "content" in delta:
                    content = delta["content"]
                    if content:  # 只处理非空内容
                        if in_thinking:
                            self._print("\n\n💭 [思考结束]\n\n", end="", flush=True)
                            in_thinking = False
                        full_response += content
                        self._print(content, end="", flush=True)
            
            self._print()  # 最终换行
            
            # 如果思考还没结束（极少情况），手动结束
            if in_thinking:
                self._print("\n💭 [思考结束]\n")
            
            # 在思考模式下，如果是当前任务的第一次调用且有思考内容，保存它
            if self.thinking_mode and self.current_task_first_call and thinking_content:
                self.current_task_thinking = thinking_content
                self.current_task_first_call = False
            
            # 如果没有收到任何响应
            if not full_response and not thinking_content:
                self._print(f"{OUTPUT_FORMATS['error']} API未返回任何内容，请检查API密钥和模型ID")
                return "", ""
                
        except Exception as e:
            self._print(f"{OUTPUT_FORMATS['error']} API调用失败: {e}")
            return "", ""
        
        return full_response, thinking_content