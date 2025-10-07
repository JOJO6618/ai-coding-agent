# core/main_terminal.py - 主终端（集成对话持久化）

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from config import (
    OUTPUT_FORMATS, DATA_DIR, PROMPTS_DIR, NEED_CONFIRMATION,
    MAX_TERMINALS, TERMINAL_BUFFER_SIZE, TERMINAL_DISPLAY_SIZE
)
from modules.file_manager import FileManager
from modules.search_engine import SearchEngine
from modules.terminal_ops import TerminalOperator
from modules.memory_manager import MemoryManager
from modules.terminal_manager import TerminalManager
from modules.webpage_extractor import extract_webpage_content
from utils.api_client import DeepSeekClient
from utils.context_manager import ContextManager
from utils.logger import setup_logger

logger = setup_logger(__name__)
# 临时禁用长度检查
DISABLE_LENGTH_CHECK = True
class MainTerminal:
    def __init__(self, project_path: str, thinking_mode: bool = False):
        self.project_path = project_path
        self.thinking_mode = thinking_mode  # False=快速模式, True=思考模式
        
        # 初始化组件
        self.api_client = DeepSeekClient(thinking_mode=thinking_mode)
        self.context_manager = ContextManager(project_path)
        self.memory_manager = MemoryManager()
        self.file_manager = FileManager(project_path)
        self.search_engine = SearchEngine()
        self.terminal_ops = TerminalOperator(project_path)
        
        # 新增：终端管理器
        self.terminal_manager = TerminalManager(
            project_path=project_path,
            max_terminals=MAX_TERMINALS,
            terminal_buffer_size=TERMINAL_BUFFER_SIZE,
            terminal_display_size=TERMINAL_DISPLAY_SIZE,
            broadcast_callback=None  # CLI模式不需要广播
        )
        
        # 聚焦文件管理
        self.focused_files = {}  # {path: content} 存储聚焦的文件内容
        
        # 新增：阅读工具使用跟踪
        self.read_file_usage_tracker = {}  # {file_path: first_read_session_id} 跟踪文件的首次读取
        self.current_session_id = 0  # 用于标识不同的任务会话
        
        # 新增：自动开始新对话
        self._ensure_conversation()
        
        # 命令映射
        self.commands = {
            "help": self.show_help,
            "exit": self.exit_system,
            "status": self.show_status,
            "memory": self.manage_memory,
            "clear": self.clear_conversation,
            "history": self.show_history,
            "files": self.show_files,
            "mode": self.toggle_mode,
            "focused": self.show_focused_files,
            "terminals": self.show_terminals,
            # 新增：对话管理命令
            "conversations": self.show_conversations,
            "load": self.load_conversation_command,
            "new": self.new_conversation_command,
            "save": self.save_conversation_command
        }
        #self.context_manager._web_terminal_callback = message_callback
        #self.context_manager._focused_files = self.focused_files  # 引用传递
    
    
    async def run(self):
        """运行主终端循环"""
        print(f"\n{OUTPUT_FORMATS['info']} 主终端已启动")
        print(f"{OUTPUT_FORMATS['info']} 当前对话: {self.context_manager.current_conversation_id}")
        
        while True:
            try:
                # 获取用户输入（使用人的表情）
                user_input = input("\n👤 > ").strip()
                
                if not user_input:
                    continue
                
                # 处理命令（命令不记录到对话历史）
                if user_input.startswith('/'):
                    await self.handle_command(user_input[1:])
                elif user_input.lower() in ['exit', 'quit', 'q']:
                    # 用户可能忘记加斜杠
                    print(f"{OUTPUT_FORMATS['info']} 提示: 使用 /exit 退出系统")
                    continue
                elif user_input.lower() == 'help':
                    print(f"{OUTPUT_FORMATS['info']} 提示: 使用 /help 查看帮助")
                    continue
                else:
                    # 确保有活动对话
                    self._ensure_conversation()
                    
                    # 只有非命令的输入才记录到对话历史
                    self.context_manager.add_conversation("user", user_input)
                    
                    # 新增：开始新的任务会话
                    self.current_session_id += 1
                    
                    # AI回复前空一行，并显示机器人图标
                    print("\n🤖 >", end=" ")
                    await self.handle_task(user_input)
                    # 回复后自动空一行（在handle_task完成后）
                
            except KeyboardInterrupt:
                print(f"\n{OUTPUT_FORMATS['warning']} 使用 /exit 退出系统")
                continue
            except Exception as e:
                logger.error(f"主终端错误: {e}", exc_info=True)
                print(f"{OUTPUT_FORMATS['error']} 发生错误: {e}")
                # 错误后仍然尝试自动保存
                try:
                    self.context_manager.auto_save_conversation()
                except:
                    pass
    
    async def handle_command(self, command: str):
        """处理系统命令"""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in self.commands:
            await self.commands[cmd](args)
        else:
            print(f"{OUTPUT_FORMATS['error']} 未知命令: {cmd}")
            await self.show_help()
    
    async def handle_task(self, user_input: str):
        """处理用户任务（完全修复版：彻底解决对话记录重复问题）"""
        try:
            # 如果是思考模式，每个新任务重置状态
            # 注意：这里重置的是当前任务的第一次调用标志，确保新用户请求重新思考
            if self.thinking_mode:
                self.api_client.start_new_task()
            
            # 新增：开始新的任务会话
            self.current_session_id += 1
            
            # 构建上下文
            context = self.build_context()
            
            # 构建消息
            messages = self.build_messages(context, user_input)
            
            # 定义可用工具
            tools = self.define_tools()
            
            # 用于收集本次任务的所有信息（关键：不立即保存到对话历史）
            collected_tool_calls = []
            collected_tool_results = []
            final_response = ""
            final_thinking = ""
            
            # 工具处理器：只执行工具，收集信息，绝不保存到对话历史
            async def tool_handler(tool_name: str, arguments: Dict) -> str:
                # 执行工具调用
                result = await self.handle_tool_call(tool_name, arguments)
                
                # 生成工具调用ID
                tool_call_id = f"call_{datetime.now().timestamp()}_{tool_name}"
                
                # 收集工具调用信息（不保存）
                tool_call_info = {
                    "id": tool_call_id,
                    "type": "function", 
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False)
                    }
                }
                collected_tool_calls.append(tool_call_info)
                
                # 处理工具结果用于保存
                try:
                    result_data = json.loads(result)
                    if tool_name == "read_file" and result_data.get("success"):
                        file_content = result_data.get("content", "")
                        tool_result_content = f"文件内容:\n```\n{file_content}\n```\n大小: {result_data.get('size')} 字节"
                    else:
                        tool_result_content = result
                except:
                    tool_result_content = result
                
                # 收集工具结果（不保存）
                collected_tool_results.append({
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": tool_result_content
                })
                
                return result
            
            # 调用带工具的API（模型自己决定是否使用工具）
            response = await self.api_client.chat_with_tools(
                messages=messages,
                tools=tools,
                tool_handler=tool_handler
            )
            
            # 保存响应内容
            final_response = response
            
            # 获取思考内容（如果有的话）
            if self.api_client.current_task_thinking:
                final_thinking = self.api_client.current_task_thinking
            
            # ===== 统一保存到对话历史（关键修复） =====
            
            # 1. 构建完整的assistant消息内容
            assistant_content_parts = []
            
            # 添加思考内容
            if final_thinking:
                assistant_content_parts.append(f"<think>\n{final_thinking}\n</think>")
            
            # 添加回复内容
            if final_response:
                assistant_content_parts.append(final_response)
            
            # 合并内容
            assistant_content = "\n".join(assistant_content_parts) if assistant_content_parts else "已完成操作。"
            
            # 2. 保存assistant消息（包含tool_calls但不包含结果）
            self.context_manager.add_conversation(
                "assistant",
                assistant_content,
                collected_tool_calls if collected_tool_calls else None
            )
            
            # 3. 保存独立的tool消息
            for tool_result in collected_tool_results:
                self.context_manager.add_conversation(
                    "tool",
                    tool_result["content"],
                    tool_call_id=tool_result["tool_call_id"],
                    name=tool_result["name"]
                )
            
            # 4. 在终端显示执行信息（不保存到历史）
            if collected_tool_calls:
                tool_names = [tc['function']['name'] for tc in collected_tool_calls]
                
                for tool_name in tool_names:
                    if tool_name == "create_file":
                        print(f"{OUTPUT_FORMATS['file']} 创建文件")
                    elif tool_name == "read_file":
                        print(f"{OUTPUT_FORMATS['file']} 读取文件")
                    elif tool_name == "modify_file":
                        print(f"{OUTPUT_FORMATS['file']} 修改文件")
                    elif tool_name == "delete_file":
                        print(f"{OUTPUT_FORMATS['file']} 删除文件")
                    elif tool_name == "terminal_session":
                        print(f"{OUTPUT_FORMATS['session']} 终端会话操作")
                    elif tool_name == "terminal_input":
                        print(f"{OUTPUT_FORMATS['terminal']} 执行终端命令")
                    elif tool_name == "web_search":
                        print(f"{OUTPUT_FORMATS['search']} 网络搜索")
                    elif tool_name == "run_python":
                        print(f"{OUTPUT_FORMATS['code']} 执行Python代码")
                    elif tool_name == "run_command":
                        print(f"{OUTPUT_FORMATS['terminal']} 执行系统命令")
                    elif tool_name == "update_memory":
                        print(f"{OUTPUT_FORMATS['memory']} 更新记忆")
                    elif tool_name == "focus_file":
                        print(f"🔍 聚焦文件")
                    elif tool_name == "unfocus_file":
                        print(f"❌ 取消聚焦")
                    elif tool_name == "confirm_read_or_focus":
                        print(f"📋 确认读取方式")
                    elif tool_name == "sleep":
                        print(f"{OUTPUT_FORMATS['info']} 等待操作")
                    else:
                        print(f"{OUTPUT_FORMATS['action']} 执行: {tool_name}")
                
                if len(tool_names) > 1:
                    print(f"{OUTPUT_FORMATS['info']} 共执行 {len(tool_names)} 个操作")
                    
        except Exception as e:
            logger.error(f"任务处理错误: {e}", exc_info=True)
            print(f"{OUTPUT_FORMATS['error']} 任务处理失败: {e}")
            # 错误时也尝试自动保存
            try:
                self.context_manager.auto_save_conversation()
            except:
                pass
    async def show_conversations(self, args: str = ""):
        """显示对话列表"""
        try:
            limit = 10  # 默认显示最近10个对话
            if args:
                try:
                    limit = int(args)
                    limit = max(1, min(limit, 50))  # 限制在1-50之间
                except ValueError:
                    print(f"{OUTPUT_FORMATS['warning']} 无效数量，使用默认值10")
                    limit = 10
            
            conversations = self.context_manager.get_conversation_list(limit=limit)
            
            if not conversations["conversations"]:
                print(f"{OUTPUT_FORMATS['info']} 暂无对话记录")
                return
            
            print(f"\n📚 最近 {len(conversations['conversations'])} 个对话:")
            print("="*70)
            
            for i, conv in enumerate(conversations["conversations"], 1):
                # 状态图标
                status_icon = "🟢" if conv["status"] == "active" else "📦" if conv["status"] == "archived" else "❌"
                
                # 当前对话标记
                current_mark = " [当前]" if conv["id"] == self.context_manager.current_conversation_id else ""
                
                # 思考模式标记
                mode_mark = "💭" if conv["thinking_mode"] else "⚡"
                
                print(f"{i:2d}. {status_icon} {conv['id'][:16]}...{current_mark}")
                print(f"    {mode_mark} {conv['title'][:50]}{'...' if len(conv['title']) > 50 else ''}")
                print(f"    📅 {conv['updated_at'][:19]} | 💬 {conv['total_messages']} 条消息 | 🔧 {conv['total_tools']} 个工具")
                print(f"    📁 {conv['project_path']}")
                print()
            
            print(f"总计: {conversations['total']} 个对话")
            if conversations["has_more"]:
                print(f"使用 /conversations {limit + 10} 查看更多")
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 获取对话列表失败: {e}")
    
    async def load_conversation_command(self, args: str):
        """加载指定对话"""
        if not args:
            print(f"{OUTPUT_FORMATS['error']} 请指定对话ID")
            print("使用方法: /load <对话ID>")
            await self.show_conversations("5")  # 显示最近5个对话作为提示
            return
        
        conversation_id = args.strip()
        
        try:
            success = self.context_manager.load_conversation_by_id(conversation_id)
            if success:
                print(f"{OUTPUT_FORMATS['success']} 对话已加载: {conversation_id}")
                print(f"{OUTPUT_FORMATS['info']} 消息数量: {len(self.context_manager.conversation_history)}")
                
                # 如果是思考模式，重置状态（下次任务会重新思考）
                if self.thinking_mode:
                    self.api_client.start_new_task()
                
                # 重置读取工具跟踪
                self.read_file_usage_tracker.clear()
                self.current_session_id += 1
                
            else:
                print(f"{OUTPUT_FORMATS['error']} 对话加载失败")
                
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 加载对话异常: {e}")
    
    async def new_conversation_command(self, args: str = ""):
        """创建新对话"""
        try:
            conversation_id = self.context_manager.start_new_conversation(
                project_path=self.project_path,
                thinking_mode=self.thinking_mode
            )
            
            print(f"{OUTPUT_FORMATS['success']} 已创建新对话: {conversation_id}")
            
            # 重置相关状态
            if self.thinking_mode:
                self.api_client.start_new_task()
            
            self.read_file_usage_tracker.clear()
            self.current_session_id += 1
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 创建新对话失败: {e}")
    
    async def save_conversation_command(self, args: str = ""):
        """手动保存当前对话"""
        try:
            success = self.context_manager.save_current_conversation()
            if success:
                print(f"{OUTPUT_FORMATS['success']} 对话已保存")
            else:
                print(f"{OUTPUT_FORMATS['error']} 对话保存失败")
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 保存对话异常: {e}")
    
    # ===== 修改现有命令，集成对话管理 =====
    
    async def clear_conversation(self, args: str = ""):
        """清除对话记录（修改版：创建新对话而不是清空）"""
        if input("确认创建新对话? 当前对话将被保存 (y/n): ").lower() == 'y':
            try:
                # 保存当前对话
                if self.context_manager.current_conversation_id:
                    self.context_manager.save_current_conversation()
                
                # 创建新对话
                await self.new_conversation_command()
                
                print(f"{OUTPUT_FORMATS['success']} 已开始新对话")
                
            except Exception as e:
                print(f"{OUTPUT_FORMATS['error']} 创建新对话失败: {e}")
    
    async def show_status(self, args: str = ""):
        """显示系统状态"""
        # 上下文状态
        context_status = self.context_manager.check_context_size()
        
        # 记忆状态
        memory_stats = self.memory_manager.get_memory_stats()
        
        # 文件结构
        structure = self.context_manager.get_project_structure()
        
        # 聚焦文件状态
        focused_size = sum(len(content) for content in self.focused_files.values())
        
        # 终端会话状态
        terminal_status = self.terminal_manager.list_terminals()
        
        # 思考模式状态
        thinking_status = '思考模式' if self.thinking_mode else '快速模式'
        if self.thinking_mode:
            thinking_status += f" ({'等待新任务' if self.api_client.current_task_first_call else '任务进行中'})"
        
        # 新增：阅读工具使用统计
        read_files_count = len(self.read_file_usage_tracker)
        
        # 新增：对话统计
        conversation_stats = self.context_manager.get_conversation_statistics()
        
        status_text = f"""
📊 系统状态:
  项目路径: {self.project_path}
  运行模式: {thinking_status}
  当前对话: {self.context_manager.current_conversation_id or '无'}
  
  上下文使用: {context_status['usage_percent']:.1f}%
  当前消息: {len(self.context_manager.conversation_history)} 条
  聚焦文件: {len(self.focused_files)}/3 个 ({focused_size/1024:.1f}KB)
  终端会话: {terminal_status['total']}/{terminal_status['max_allowed']} 个
  已读文件: {read_files_count} 个 (本次会话ID: {self.current_session_id})
  
  项目文件: {structure['total_files']} 个
  项目大小: {structure['total_size'] / 1024 / 1024:.2f} MB
  
  对话总数: {conversation_stats.get('total_conversations', 0)} 个
  历史消息: {conversation_stats.get('total_messages', 0)} 条
  工具调用: {conversation_stats.get('total_tools', 0)} 次
  
  主记忆: {memory_stats['main_memory']['lines']} 行
  任务记忆: {memory_stats['task_memory']['lines']} 行
"""
        print(status_text)
    
    async def save_state(self):
        """保存状态"""
        try:
            # 保存对话历史（使用新的持久化系统）
            self.context_manager.save_current_conversation()
            
            # 保存文件备注
            self.context_manager.save_annotations()
            
            print(f"{OUTPUT_FORMATS['success']} 状态已保存")
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 状态保存失败: {e}")
    
    async def show_help(self, args: str = ""):
        """显示帮助信息"""
        # 根据当前模式显示不同的帮助信息
        mode_info = ""
        if self.thinking_mode:
            mode_info = "\n💡 思考模式:\n  - 每个新任务首次调用深度思考\n  - 同一任务后续调用快速响应\n  - 每个新任务都会重新思考"
        else:
            mode_info = "\n⚡ 快速模式:\n  - 不进行思考，直接响应\n  - 适合简单任务和快速交互"
        
        help_text = f"""
📚 可用命令:
  /help         - 显示此帮助信息
  /exit         - 退出系统
  /status       - 显示系统状态
  /memory       - 管理记忆
  /clear        - 创建新对话
  /history      - 显示对话历史
  /files        - 显示项目文件
  /focused      - 显示聚焦文件
  /terminals    - 显示终端会话
  /mode         - 切换运行模式
  
🗂️ 对话管理:
  /conversations [数量]  - 显示对话列表
  /load <对话ID>        - 加载指定对话
  /new                  - 创建新对话
  /save                 - 手动保存当前对话
  
💡 使用提示:
  - 直接输入任务描述，系统会自动判断是否需要执行
  - 使用 Ctrl+C 可以中断当前操作
  - 重要操作会要求确认
  - 所有对话都会自动保存，不用担心丢失
  
🔍 文件聚焦功能:
  - 系统可以聚焦最多3个文件，实现"边看边改"
  - 聚焦的文件内容会持续显示在上下文中
  - 适合需要频繁查看和修改的文件
  
📺 持久化终端:
  - 可以打开最多3个终端会话
  - 终端保持运行状态，支持交互式程序
  - 使用 terminal_session 和 terminal_input 工具控制{mode_info}
"""
        print(help_text)
    
    # ===== 保持原有的其他方法不变，只需要小修改 =====
    
    def define_tools(self) -> List[Dict]:
        """定义可用工具（添加确认工具）"""
        return [
                {
                "type": "function",
                "function": {
                    "name": "sleep",
                    "description": "等待指定的秒数。用于等待长时间操作完成，如安装包、编译、服务启动等。当终端或进程需要时间完成操作时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "seconds": {
                                "type": "number",
                                "description": "等待的秒数，可以是小数（如2.5秒）。建议范围：0.5-30秒"
                            },
                            "reason": {
                                "type": "string",
                                "description": "等待的原因说明（可选）"
                            }
                        },
                        "required": ["seconds"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_file",
                    "description": "创建新文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"},
                            "content": {"type": "string", "description": "文件内容"},
                            "file_type": {"type": "string", "enum": ["txt", "py", "md"], "description": "文件类型"},
                            "annotation": {"type": "string", "description": "文件备注"}
                        },
                        "required": ["path", "file_type", "annotation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文件内容。注意：此工具会触发智能建议，系统建议使用聚焦功能来代替频繁读取，文件内容超过10000字符将被拒绝，请使用run_command限制字符数返回。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "confirm_read_or_focus",
                    "description": "确认是使用读取还是聚焦功能来查看文件。当系统建议选择查看方式时使用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "要操作的文件路径"},
                            "choice": {
                                "type": "string", 
                                "enum": ["read", "focus"],
                                "description": "选择操作类型：read-一次性读取，focus-持续聚焦"
                            },
                            "reason": {"type": "string", "description": "选择原因（可选）"}
                        },
                        "required": ["file_path", "choice"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "description": "删除文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rename_file",
                    "description": "重命名文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "old_path": {"type": "string", "description": "原文件路径"},
                            "new_path": {"type": "string", "description": "新文件路径"}
                        },
                        "required": ["old_path", "new_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "modify_file",
                    "description": "修改文件内容。对于空文件，可以省略old_text参数或提供空字符串，这是修改聚焦文件的首选方法，优先使用内容替换而非行号编辑。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"},
                            "operation": {
                                "type": "string", 
                                "enum": ["append", "replace", "clear"], 
                                "description": "操作类型：append-追加内容，replace-替换文本（空文件可省略old_text），clear-清空文件"
                            },
                            "content": {
                                "type": "string", 
                                "description": "新内容（append和replace时必需）"
                            },
                            "old_text": {
                                "type": "string", 
                                "description": "要替换的旧内容（replace非空文件时必需，空文件可省略或传空字符串）"
                            }
                        },
                        "required": ["path", "operation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_lines",
                    "description": "基于行号精确编辑文件，仅在modify_file失败时使用。使用前**必须先用grep -n定位精确行号**，严格禁止瞎猜行号。对于聚焦文件，这是modify_file的备选方案。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"},
                            "operation": {
                                "type": "string",
                                "enum": ["replace_lines", "insert_at", "delete_lines"],
                                "description": "操作类型：replace_lines-替换指定行范围，insert_at-在指定行插入内容，delete_lines-删除指定行范围"
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "起始行号（从1开始计数）"
                            },
                            "end_line": {
                                "type": "integer", 
                                "description": "结束行号（replace_lines和delete_lines的范围操作时需要，可以等于start_line表示单行）"
                            },
                            "content": {
                                "type": "string",
                                "description": "新内容（replace_lines和insert_at时必需）"
                            }
                        },
                        "required": ["path", "operation", "start_line"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_folder",
                    "description": "创建文件夹",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件夹路径"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "focus_file",
                    "description": "聚焦文件，将完整文件内容持续显示在上下文中，内容100%可见。聚焦后禁止使用任何内容查看命令。适合需要频繁查看和修改的文件。文件内容超过10000字符将被拒绝，请使用run_command限制字符数返回。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "unfocus_file",
                    "description": "取消聚焦文件，从上下文中移除",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "terminal_session",
                    "description": "管理持久化终端会话。可以打开、关闭、列出或切换终端会话。终端会保持运行状态，适合运行交互式程序。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string", 
                                "enum": ["open", "close", "list", "switch"],
                                "description": "操作类型：open-打开新终端，close-关闭终端，list-列出所有终端，switch-切换活动终端"
                            },
                            "session_name": {
                                "type": "string",
                                "description": "终端会话名称（open、close、switch时需要）"
                            },
                            "working_dir": {
                                "type": "string",
                                "description": "工作目录，相对于项目路径（open时可选）"
                            }
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "terminal_input",
                    "description": "向活动终端发送命令或输入。终端会保持状态，可以运行交互式程序。禁止在已经有程序正在运行的终端中输入新指令，必须在新终端中输入。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "要执行的命令或发送的输入"
                            },
                            "session_name": {
                                "type": "string",
                                "description": "目标终端会话名称（可选，默认使用活动终端）"
                            },
                            "wait_for_output": {
                                "type": "boolean",
                                "description": "是否等待输出（默认true）"
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索网络信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜索查询"},
                            "max_results": {"type": "integer", "description": "最大结果数"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_webpage",
                    "description": "提取指定网页的完整内容进行详细分析。补充web_search功能，获取网页的具体内容而不仅仅是摘要。网页内容超过80000字符将被拒绝，请不要提取过长的网页。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "要提取内容的网页URL"}
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": "执行Python代码（一次性执行，不保持状态）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python代码"}
                        },
                        "required": ["code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "执行终端命令（一次性执行，不保持状态）。对已聚焦文件：允许使用 grep -n 定位行号，禁止使用内容查看命令（grep不带-n、cat、head、tail等）。命令输出超过10000字符将被拒绝，请使用限制字符数的获取内容方式，根据程度选择10k以内的数。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "终端命令"}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_memory",
                    "description": "更新记忆文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "memory_type": {"type": "string", "enum": ["main", "task"], "description": "记忆类型"},
                            "content": {"type": "string", "description": "要添加的内容"},
                            "operation": {"type": "string", "enum": ["append", "replace"], "description": "操作类型"}
                        },
                        "required": ["memory_type", "content", "operation"]
                    }
                }
            }
        ]
    
    async def handle_tool_call(self, tool_name: str, arguments: Dict) -> str:
        """处理工具调用（添加参数预检查和改进错误处理）"""
        # 导入字符限制配置
        from config import (
            MAX_READ_FILE_CHARS, MAX_FOCUS_FILE_CHARS, 
            MAX_RUN_COMMAND_CHARS, MAX_EXTRACT_WEBPAGE_CHARS
        )
        
        # 检查是否需要确认
        if tool_name in NEED_CONFIRMATION:
            if not await self.confirm_action(tool_name, arguments):
                return json.dumps({"success": False, "error": "用户取消操作"})
        
        # === 新增：预检查参数大小和格式 ===
        try:
            # 检查参数总大小
            arguments_str = json.dumps(arguments, ensure_ascii=False)
            if len(arguments_str) > 50000:  # 50KB限制
                return json.dumps({
                    "success": False,
                    "error": f"参数过大({len(arguments_str)}字符)，超过50KB限制",
                    "suggestion": "请分块处理或减少参数内容"
                }, ensure_ascii=False)
            
            # 针对特定工具的内容检查
            if tool_name in ["modify_file", "create_file"] and "content" in arguments:
                content = arguments.get("content", "")
                if not DISABLE_LENGTH_CHECK and len(content) > 9999999999:  # 30KB内容限制
                    return json.dumps({
                        "success": False,
                        "error": f"文件内容过长({len(content)}字符)，建议分块处理",
                        "suggestion": "请将大文件内容分成多个操作，或使用edit_lines工具进行部分修改"
                    }, ensure_ascii=False)
                
                # 检查内容中的特殊字符
                if '\\' in content and content.count('\\') > len(content) / 10:
                    print(f"{OUTPUT_FORMATS['warning']} 检测到大量转义字符，可能存在格式问题")
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"参数预检查失败: {str(e)}"
            }, ensure_ascii=False)
        
        try:
            # ===== 新增：阅读工具拦截逻辑 =====
            if tool_name == "read_file":
                file_path = arguments.get("path", "")
                
                # 检查是否是本次会话首次读取此文件
                if file_path not in self.read_file_usage_tracker:
                    # 记录首次读取
                    self.read_file_usage_tracker[file_path] = self.current_session_id
                    
                    # 返回选择提示，要求AI使用confirm_read_or_focus工具
                    return json.dumps({
                        "success": False,
                        "requires_confirmation": True,
                        "message": "阅读工具只能用于阅读小文件、临时文件、不重要的文件。如果要查看核心文件、需要多次修改的文件、重要的文件，请使用聚焦功能。请确认使用阅读还是聚焦？",
                        "instruction": f"请使用 confirm_read_or_focus 工具来选择操作方式，文件路径: {file_path}",
                        "file_path": file_path
                    })
                
                # 如果不是首次读取，检查是否是同一会话
                elif self.read_file_usage_tracker[file_path] != self.current_session_id:
                    # 新会话首次读取已读过的文件，也需要确认
                    self.read_file_usage_tracker[file_path] = self.current_session_id
                    
                    return json.dumps({
                        "success": False,
                        "requires_confirmation": True,
                        "message": f"检测到要重复读取文件 {file_path}。建议使用聚焦功能以避免频繁读取。请确认使用阅读还是聚焦？",
                        "instruction": f"请使用 confirm_read_or_focus 工具来选择操作方式，文件路径: {file_path}",
                        "file_path": file_path
                    })
            
            # ===== 新增：处理确认选择工具 =====
            elif tool_name == "confirm_read_or_focus":
                file_path = arguments.get("file_path", "")
                choice = arguments.get("choice", "")
                reason = arguments.get("reason", "")
                
                if not file_path or not choice:
                    return json.dumps({
                        "success": False,
                        "error": "缺少必要参数：file_path 或 choice"
                    })
                
                if choice == "read":
                    # 执行读取操作
                    print(f"{OUTPUT_FORMATS['info']} 用户选择：一次性读取文件 {file_path}")
                    if reason:
                        print(f"{OUTPUT_FORMATS['info']} 选择原因: {reason}")
                    
                    # 直接调用读取文件
                    result = self.file_manager.read_file(file_path)
                    
                    # ✅ 先检查是否读取成功
                    if not result["success"]:
                        return json.dumps({
                            "success": False,
                            "error": f"读取文件失败: {result.get('error', '未知错误')}"
                        })
                    
                    # 读取成功，继续处理
                    file_content = result["content"]
                    char_count = len(file_content)
                    
                    # 字符数检查
                    if char_count > MAX_READ_FILE_CHARS:
                        return json.dumps({
                            "success": False,
                            "error": f"文件过大，有{char_count}字符，请使用run_command限制字符数返回",
                            "char_count": char_count,
                            "limit": MAX_READ_FILE_CHARS
                        })
                    
                    # 加载到上下文管理器
                    self.context_manager.load_file(result["path"])
                    print(f"{OUTPUT_FORMATS['info']} 文件已加载到上下文: {result['path']}")
                    
                    # ✅ 返回完整内容
                    return json.dumps({
                        "success": True,
                        "action": "read",
                        "message": f"已使用读取方式查看文件: {file_path}",
                        "content": file_content,  # ← 关键：包含完整内容
                        "file_size": len(file_content),
                        "char_count": char_count
                    })
                elif choice == "focus":
                    # 执行聚焦操作
                    print(f"{OUTPUT_FORMATS['info']} 用户选择：聚焦文件 {file_path}")
                    if reason:
                        print(f"{OUTPUT_FORMATS['info']} 选择原因: {reason}")
                    
                    # 检查是否已经聚焦
                    if file_path in self.focused_files:
                        return json.dumps({
                            "success": False,
                            "error": f"文件已经处于聚焦状态: {file_path}"
                        })
                    
                    # 检查聚焦文件数量限制
                    if len(self.focused_files) >= 3:
                        return json.dumps({
                            "success": False,
                            "error": f"已达到最大聚焦文件数量(3个)，当前聚焦: {list(self.focused_files.keys())}",
                            "suggestion": "请先使用 unfocus_file 取消部分文件的聚焦"
                        })
                    
                    # 读取文件内容并聚焦
                    read_result = self.file_manager.read_file(file_path)
                    if read_result["success"]:
                        # 字符数检查
                        char_count = len(read_result["content"])
                        if char_count > MAX_FOCUS_FILE_CHARS:
                            return json.dumps({
                                "success": False,
                                "error": f"文件过大，有{char_count}字符，请使用run_command限制字符数返回",
                                "char_count": char_count,
                                "limit": MAX_FOCUS_FILE_CHARS
                            })
                        
                        self.focused_files[file_path] = read_result["content"]
                        result = {
                            "success": True,
                            "action": "focus",
                            "message": f"文件已聚焦: {file_path}",
                            "focused_files": list(self.focused_files.keys()),
                            "file_size": len(read_result["content"])
                        }
                        print(f"🔍 文件已聚焦: {file_path} ({len(read_result['content'])} 字节)")
                    else:
                        result = {
                            "success": False,
                            "action": "focus",
                            "error": f"读取文件失败: {read_result.get('error', '未知错误')}"
                        }
                    
                    return json.dumps(result)
                
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"无效的选择: {choice}，只能选择 'read' 或 'focus'"
                    })
            
            # ===== 以下是原有的工具处理逻辑 =====
            
            # 终端会话管理工具
            elif tool_name == "terminal_session":
                action = arguments["action"]
                
                if action == "open":
                    result = self.terminal_manager.open_terminal(
                        session_name=arguments.get("session_name", "default"),
                        working_dir=arguments.get("working_dir"),
                        make_active=True
                    )
                    if result["success"]:
                        print(f"{OUTPUT_FORMATS['session']} 终端会话已打开: {arguments.get('session_name', 'default')}")
                        
                elif action == "close":
                    result = self.terminal_manager.close_terminal(
                        session_name=arguments.get("session_name", "default")
                    )
                    if result["success"]:
                        print(f"{OUTPUT_FORMATS['session']} 终端会话已关闭: {arguments.get('session_name', 'default')}")
                        
                elif action == "list":
                    result = self.terminal_manager.list_terminals()
                    
                elif action == "switch":
                    result = self.terminal_manager.switch_terminal(
                        session_name=arguments.get("session_name", "default")
                    )
                    if result["success"]:
                        print(f"{OUTPUT_FORMATS['session']} 切换到终端: {arguments.get('session_name', 'default')}")
                        
                else:
                    result = {"success": False, "error": f"未知操作: {action}"}
                    
            # 终端输入工具
            elif tool_name == "terminal_input":
                result = self.terminal_manager.send_to_terminal(
                    command=arguments["command"],
                    session_name=arguments.get("session_name"),
                    wait_for_output=arguments.get("wait_for_output", True)
                )
                if result["success"]:
                    print(f"{OUTPUT_FORMATS['terminal']} 执行命令: {arguments['command']}")
                    
            # sleep工具
            elif tool_name == "sleep":
                seconds = arguments.get("seconds", 1)
                reason = arguments.get("reason", "等待操作完成")
                
                # 限制最大等待时间
                max_sleep = 60  # 最多等待60秒
                if seconds > max_sleep:
                    result = {
                        "success": False,
                        "error": f"等待时间过长，最多允许 {max_sleep} 秒",
                        "suggestion": f"建议分多次等待或减少等待时间"
                    }
                else:
                    # 确保秒数为正数
                    if seconds <= 0:
                        result = {
                            "success": False,
                            "error": "等待时间必须大于0"
                        }
                    else:
                        print(f"{OUTPUT_FORMATS['info']} 等待 {seconds} 秒: {reason}")
                        
                        # 执行等待
                        import asyncio
                        await asyncio.sleep(seconds)
                        
                        result = {
                            "success": True,
                            "message": f"已等待 {seconds} 秒",
                            "reason": reason,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        print(f"{OUTPUT_FORMATS['success']} 等待完成")
                    
            elif tool_name == "create_file":
                result = self.file_manager.create_file(
                    path=arguments["path"],
                    content=arguments.get("content", ""),
                    file_type=arguments["file_type"]
                )
                # 添加备注
                if result["success"] and arguments.get("annotation"):
                    self.context_manager.update_annotation(
                        result["path"],
                        arguments["annotation"]
                    )
            
            # 注意：原始的read_file处理已经移到上面的拦截逻辑中
            elif tool_name == "read_file":
                result = self.file_manager.read_file(arguments["path"])
                if result["success"]:
                    # 字符数检查
                    char_count = len(result["content"])
                    if char_count > MAX_READ_FILE_CHARS:
                        return json.dumps({...})
                    
                    # ✅ 先保存文件内容
                    file_content = result["content"]
                    
                    # 加载到上下文管理器
                    self.context_manager.load_file(result["path"])
                    print(f"{OUTPUT_FORMATS['info']} 文件已加载到上下文: {result['path']}")
                    
                    # ✅ 关键：返回时必须包含content字段
                    result = {
                        "success": True,
                        "message": f"已读取文件: {arguments['path']}",
                        "content": file_content,  # ← 必须加这个！
                        "file_size": len(file_content),
                        "char_count": char_count
                    }
            elif tool_name == "delete_file":
                result = self.file_manager.delete_file(arguments["path"])
                # 如果删除成功，同时删除备注和聚焦
                if result.get("success") and result.get("action") == "deleted":
                    deleted_path = result.get("path")
                    # 删除备注
                    if deleted_path in self.context_manager.file_annotations:
                        del self.context_manager.file_annotations[deleted_path]
                        self.context_manager.save_annotations()
                        print(f"🧹 已删除文件备注: {deleted_path}")
                    # 删除聚焦
                    if deleted_path in self.focused_files:
                        del self.focused_files[deleted_path]
                        print(f"🔍 已取消文件聚焦: {deleted_path}")
                
            elif tool_name == "rename_file":
                result = self.file_manager.rename_file(
                    arguments["old_path"],
                    arguments["new_path"]
                )
                # 如果重命名成功，更新备注和聚焦的key
                if result.get("success") and result.get("action") == "renamed":
                    old_path = result.get("old_path")
                    new_path = result.get("new_path")
                    # 更新备注
                    if old_path in self.context_manager.file_annotations:
                        annotation = self.context_manager.file_annotations[old_path]
                        del self.context_manager.file_annotations[old_path]
                        self.context_manager.file_annotations[new_path] = annotation
                        self.context_manager.save_annotations()
                        print(f"📝 已更新文件备注: {old_path} -> {new_path}")
                    # 更新聚焦
                    if old_path in self.focused_files:
                        content = self.focused_files[old_path]
                        del self.focused_files[old_path]
                        self.focused_files[new_path] = content
                        print(f"🔍 已更新文件聚焦: {old_path} -> {new_path}")
                
            elif tool_name == "modify_file":
                operation = arguments.get("operation")
                path = arguments.get("path")
                
                if not operation:
                    result = {"success": False, "error": "缺少必要参数: operation"}
                elif not path:
                    result = {"success": False, "error": "缺少必要参数: path"}
                elif operation == "append":
                    content = arguments.get("content")
                    if content is None:
                        result = {"success": False, "error": "append操作需要提供content参数"}
                    else:
                        result = self.file_manager.append_file(path, content)
                elif operation == "replace":
                    content = arguments.get("content")
                    old_text = arguments.get("old_text", "")
                    if content is None:
                        result = {"success": False, "error": "replace操作需要提供content参数"}
                    else:
                        result = self.file_manager.replace_in_file(path, old_text, content)
                elif operation == "clear":
                    result = self.file_manager.clear_file(path)
                else:
                    result = {"success": False, "error": f"未知的操作类型: {operation}"}
                
                # 如果修改成功且文件在聚焦列表中，更新聚焦内容
                if result.get("success") and path in self.focused_files:
                    # 重新读取文件内容
                    read_result = self.file_manager.read_file(path)
                    if read_result["success"]:
                        self.focused_files[path] = read_result["content"]
                        print(f"🔍 已更新聚焦文件内容: {path}")
                        
            elif tool_name == "edit_lines":
                operation = arguments.get("operation")
                path = arguments.get("path")
                start_line = arguments.get("start_line")
                
                if not operation:
                    result = {"success": False, "error": "缺少必要参数: operation"}
                elif not path:
                    result = {"success": False, "error": "缺少必要参数: path"}
                elif start_line is None:
                    result = {"success": False, "error": "缺少必要参数: start_line"}
                elif operation == "replace_lines":
                    content = arguments.get("content")
                    end_line = arguments.get("end_line", start_line)  # 默认为单行替换
                    if content is None:
                        result = {"success": False, "error": "replace_lines操作需要提供content参数"}
                    else:
                        result = self.file_manager.edit_lines_range(path, start_line, end_line, content, "replace")
                elif operation == "insert_at":
                    content = arguments.get("content")
                    if content is None:
                        result = {"success": False, "error": "insert_at操作需要提供content参数"}
                    else:
                        result = self.file_manager.edit_lines_range(path, start_line, start_line, content, "insert")
                elif operation == "delete_lines":
                    end_line = arguments.get("end_line", start_line)  # 默认为单行删除
                    result = self.file_manager.edit_lines_range(path, start_line, end_line, "", "delete")
                else:
                    result = {"success": False, "error": f"未知的操作类型: {operation}"}
                
                # 如果修改成功且文件在聚焦列表中，更新聚焦内容
                if result.get("success") and path in self.focused_files:
                    # 重新读取文件内容
                    read_result = self.file_manager.read_file(path)
                    if read_result["success"]:
                        self.focused_files[path] = read_result["content"]
                        print(f"🔍 已更新聚焦文件内容: {path}")
                    
            elif tool_name == "create_folder":
                result = self.file_manager.create_folder(arguments["path"])
            
            elif tool_name == "focus_file":
                path = arguments["path"]
                # 检查是否已经聚焦
                if path in self.focused_files:
                    result = {"success": False, "error": f"文件已经处于聚焦状态: {path}"}
                else:
                    # 检查聚焦文件数量限制
                    if len(self.focused_files) >= 3:
                        result = {
                            "success": False, 
                            "error": f"已达到最大聚焦文件数量(3个)，当前聚焦: {list(self.focused_files.keys())}",
                            "suggestion": "请先使用 unfocus_file 取消部分文件的聚焦"
                        }
                    else:
                        # 读取文件内容
                        read_result = self.file_manager.read_file(path)
                        if read_result["success"]:
                            # 字符数检查
                            char_count = len(read_result["content"])
                            if char_count > MAX_FOCUS_FILE_CHARS:
                                result = {
                                    "success": False,
                                    "error": f"文件过大，有{char_count}字符，请使用run_command限制字符数返回",
                                    "char_count": char_count,
                                    "limit": MAX_FOCUS_FILE_CHARS
                                }
                            else:
                                self.focused_files[path] = read_result["content"]
                                result = {
                                    "success": True, 
                                    "message": f"文件已聚焦: {path}",
                                    "focused_files": list(self.focused_files.keys()),
                                    "file_size": len(read_result["content"])
                                }
                                print(f"🔍 文件已聚焦: {path} ({len(read_result['content'])} 字节)")
                        else:
                            result = read_result
            
            elif tool_name == "unfocus_file":
                path = arguments["path"]
                if path in self.focused_files:
                    del self.focused_files[path]
                    result = {
                        "success": True, 
                        "message": f"已取消文件聚焦: {path}",
                        "remaining_focused": list(self.focused_files.keys())
                    }
                    print(f"✖️ 已取消文件聚焦: {path}")
                else:
                    result = {"success": False, "error": f"文件未处于聚焦状态: {path}"}
                
            elif tool_name == "web_search":
                summary = await self.search_engine.search_with_summary(
                    arguments["query"],
                    arguments.get("max_results")
                )
                result = {"success": True, "summary": summary}
                
            elif tool_name == "extract_webpage":
                url = arguments["url"]
                try:
                    # 从config获取API密钥
                    from config import TAVILY_API_KEY
                    full_content, _ = await extract_webpage_content(
                        urls=url, 
                        api_key=TAVILY_API_KEY,
                        extract_depth="basic",
                        max_urls=1
                    )
                    
                    # 字符数检查
                    char_count = len(full_content)
                    if char_count > MAX_EXTRACT_WEBPAGE_CHARS:
                        result = {
                            "success": False,
                            "error": f"网页提取返回了过长的{char_count}字符，请不要提取这个网页",
                            "char_count": char_count,
                            "limit": MAX_EXTRACT_WEBPAGE_CHARS,
                            "url": url
                        }
                    else:
                        result = {
                            "success": True,
                            "url": url,
                            "content": full_content
                        }
                except Exception as e:
                    result = {
                        "success": False,
                        "error": f"网页提取失败: {str(e)}",
                        "url": url
                    }
                    
            elif tool_name == "run_python":
                result = await self.terminal_ops.run_python_code(arguments["code"])
                
            elif tool_name == "run_command":
                result = await self.terminal_ops.run_command(arguments["command"])
                
                # 字符数检查
                if result.get("success") and "output" in result:
                    char_count = len(result["output"])
                    if char_count > MAX_RUN_COMMAND_CHARS:
                        result = {
                            "success": False,
                            "error": f"结果内容过大，有{char_count}字符，请使用限制字符数的获取内容方式，根据程度选择10k以内的数",
                            "char_count": char_count,
                            "limit": MAX_RUN_COMMAND_CHARS,
                            "command": arguments["command"]
                        }
                
            elif tool_name == "update_memory":
                memory_type = arguments["memory_type"]
                content = arguments["content"]
                operation = arguments["operation"]
                
                if memory_type == "main":
                    if operation == "append":
                        success = self.memory_manager.append_main_memory(content)
                    else:
                        success = self.memory_manager.write_main_memory(content)
                else:
                    if operation == "append":
                        success = self.memory_manager.append_task_memory(content)
                    else:
                        success = self.memory_manager.write_task_memory(content)
                
                result = {"success": success}
            
            else:
                result = {"success": False, "error": f"未知工具: {tool_name}"}
                
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name} - {e}")
            result = {"success": False, "error": f"工具执行异常: {str(e)}"}
    
        return json.dumps(result, ensure_ascii=False)
    
    async def confirm_action(self, action: str, arguments: Dict) -> bool:
        """确认危险操作"""
        print(f"\n{OUTPUT_FORMATS['confirm']} 需要确认的操作:")
        print(f"  操作: {action}")
        print(f"  参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")
        
        response = input("\n是否继续? (y/n): ").strip().lower()
        return response == 'y'
    
    def build_context(self) -> Dict:
        """构建主终端上下文"""
        # 读取记忆
        memory = self.memory_manager.read_main_memory()
        
        # 构建上下文
        return self.context_manager.build_main_context(memory)
    
    def build_messages(self, context: Dict, user_input: str) -> List[Dict]:
        """构建消息列表（添加终端内容注入）"""
        # 加载系统提示
        system_prompt = self.load_prompt("main_system")
        
        # 格式化系统提示
        system_prompt = system_prompt.format(
            project_path=self.project_path,
            file_tree=context["project_info"]["file_tree"],
            memory=context["memory"],
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加对话历史（保留完整结构，包括tool_calls和tool消息）
        for conv in context["conversation"]:
            if conv["role"] == "assistant":
                # Assistant消息可能包含工具调用
                message = {
                    "role": conv["role"],
                    "content": conv["content"]
                }
                # 如果有工具调用信息，添加到消息中
                if "tool_calls" in conv and conv["tool_calls"]:
                    message["tool_calls"] = conv["tool_calls"]
                messages.append(message)
                
            elif conv["role"] == "tool":
                # Tool消息需要保留完整结构
                message = {
                    "role": "tool",
                    "content": conv["content"],
                    "tool_call_id": conv.get("tool_call_id", ""),
                    "name": conv.get("name", "")
                }
                messages.append(message)
                
            else:
                # User消息
                messages.append({
                    "role": conv["role"],
                    "content": conv["content"]
                })
        
        # 当前用户输入已经在conversation中了，不需要重复添加
        
        # 在最后注入聚焦文件内容作为系统消息
        if self.focused_files:
            focused_content = "\n\n=== 🔍 正在聚焦的文件 ===\n"
            focused_content += f"(共 {len(self.focused_files)} 个文件处于聚焦状态)\n"
            
            for path, content in self.focused_files.items():
                size_kb = len(content) / 1024
                focused_content += f"\n--- 文件: {path} ({size_kb:.1f}KB) ---\n"
                focused_content += f"```\n{content}\n```\n"
            
            focused_content += "\n=== 聚焦文件结束 ===\n"
            focused_content += "提示：以上文件正在被聚焦，你可以直接看到完整内容并进行修改，禁止再次读取。"
            
            messages.append({
                "role": "system",
                "content": focused_content
            })
    
        
        # 最后添加终端内容（如果需要）
        terminal_content = self.terminal_manager.get_active_terminal_content()
        if terminal_content:
            messages.append({
                "role": "system",
                "content": terminal_content
            })
        
        return messages
    
    def load_prompt(self, name: str) -> str:
        """加载提示模板"""
        prompt_file = Path(PROMPTS_DIR) / f"{name}.txt"
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        return "你是一个AI助手。"
    
    async def show_focused_files(self, args: str = ""):
        """显示当前聚焦的文件"""
        if not self.focused_files:
            print(f"{OUTPUT_FORMATS['info']} 当前没有聚焦的文件")
        else:
            print(f"\n🔍 聚焦文件列表 ({len(self.focused_files)}/3):")
            print("="*50)
            for path, content in self.focused_files.items():
                size_kb = len(content) / 1024
                lines = content.count('\n') + 1
                print(f"  📄 {path}")
                print(f"     大小: {size_kb:.1f}KB | 行数: {lines}")
            print("="*50)
    
    async def show_terminals(self, args: str = ""):
        """显示终端会话列表"""
        result = self.terminal_manager.list_terminals()
        
        if result["total"] == 0:
            print(f"{OUTPUT_FORMATS['info']} 当前没有活动的终端会话")
        else:
            print(f"\n📺 终端会话列表 ({result['total']}/{result['max_allowed']}):")
            print("="*50)
            for session in result["sessions"]:
                status_icon = "🟢" if session["is_running"] else "🔴"
                active_mark = " [活动]" if session["is_active"] else ""
                print(f"  {status_icon} {session['session_name']}{active_mark}")
                print(f"     工作目录: {session['working_dir']}")
                print(f"     Shell: {session['shell']}")
                print(f"     运行时间: {session['uptime_seconds']:.1f}秒")
                if session["is_interactive"]:
                    print(f"     ⚠️ 等待输入")
            print("="*50)
    
    async def exit_system(self, args: str = ""):
        """退出系统"""
        print(f"{OUTPUT_FORMATS['info']} 正在退出...")
        
        # 关闭所有终端会话
        self.terminal_manager.close_all()
        
        # 保存状态
        await self.save_state()
        
        exit(0)
    
    async def manage_memory(self, args: str = ""):
        """管理记忆"""
        if not args:
            print("""
🧠 记忆管理:
  /memory show [main|task]  - 显示记忆内容
  /memory edit [main|task]  - 编辑记忆
  /memory clear task        - 清空任务记忆
  /memory merge             - 合并任务记忆到主记忆
  /memory backup [main|task]- 备份记忆
""")
            return
        
        parts = args.split()
        action = parts[0] if parts else ""
        target = parts[1] if len(parts) > 1 else "main"
        
        if action == "show":
            if target == "main":
                content = self.memory_manager.read_main_memory()
            else:
                content = self.memory_manager.read_task_memory()
            print(f"\n{'='*50}")
            print(content)
            print('='*50)
        
        elif action == "clear" and target == "task":
            if input("确认清空任务记忆? (y/n): ").lower() == 'y':
                self.memory_manager.clear_task_memory()
        
        elif action == "merge":
            self.memory_manager.merge_memories()
        
        elif action == "backup":
            path = self.memory_manager.backup_memory(target)
            if path:
                print(f"备份保存到: {path}")
    
    async def show_history(self, args: str = ""):
        """显示对话历史"""
        history = self.context_manager.conversation_history[-2000:]  # 最近2000条
        
        print("\n📜 对话历史:")
        print("="*50)
        for conv in history:
            timestamp = conv.get("timestamp", "")
            if conv["role"] == "user":
                role = "👤 用户"
            elif conv["role"] == "assistant":
                role = "🤖 助手"
            elif conv["role"] == "tool":
                role = f"🔧 工具[{conv.get('name', 'unknown')}]"
            else:
                role = conv["role"]
                
            content = conv["content"][:100] + "..." if len(conv["content"]) > 100 else conv["content"]
            print(f"\n[{timestamp[:19]}] {role}:")
            print(content)
            
            # 如果是助手消息且有工具调用，显示工具信息
            if conv["role"] == "assistant" and "tool_calls" in conv and conv["tool_calls"]:
                tools = [tc["function"]["name"] for tc in conv["tool_calls"]]
                print(f"  🔗 调用工具: {', '.join(tools)}")
        print("="*50)
    
    async def show_files(self, args: str = ""):
        """显示项目文件"""
        structure = self.context_manager.get_project_structure()
        print(f"\n📁 项目文件结构:")
        print(self.context_manager._build_file_tree(structure))
        print(f"\n总计: {structure['total_files']} 个文件, {structure['total_size'] / 1024 / 1024:.2f} MB")
    
    async def toggle_mode(self, args: str = ""):
        """切换运行模式（简化版）"""
        if self.thinking_mode:
            # 当前是思考模式，切换到快速模式
            self.thinking_mode = False
            self.api_client.thinking_mode = False
            print(f"{OUTPUT_FORMATS['info']} 已切换到: 快速模式（不思考）")
        else:
            # 当前是快速模式，切换到思考模式
            self.thinking_mode = True
            self.api_client.thinking_mode = True
            self.api_client.start_new_task()
            print(f"{OUTPUT_FORMATS['info']} 已切换到: 思考模式（智能思考）")