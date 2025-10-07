# core/web_terminal.py - Web终端（集成对话持久化）

import json
from typing import Dict, List, Optional, Callable
from core.main_terminal import MainTerminal
from config import MAX_TERMINALS, TERMINAL_BUFFER_SIZE, TERMINAL_DISPLAY_SIZE
from modules.terminal_manager import TerminalManager

class WebTerminal(MainTerminal):
    """Web版本的终端，继承自MainTerminal，包含对话持久化功能"""
    
    def _ensure_conversation(self):
        """确保有可用的对话ID（Web版本：生成临时ID而不创建实际对话）"""
        if not self.context_manager.current_conversation_id:
            # 生成临时ID，但不保存为对话
            import time
            temp_id = f"temp_{int(time.time() * 1000)}"
            self.context_manager.current_conversation_id = temp_id
            print(f"[WebTerminal] 生成临时对话ID: {temp_id}")
    
    def __init__(
        self, 
        project_path: str, 
        thinking_mode: bool = False,
        message_callback: Optional[Callable] = None
    ):
        # 调用父类初始化（包含对话持久化功能）
        super().__init__(project_path, thinking_mode)
        
        # Web特有属性
        self.message_callback = message_callback
        self.web_mode = True
        
        # 设置API客户端为Web模式（禁用print）
        self.api_client.web_mode = True
        
        # 重新初始化终端管理器
        self.terminal_manager = TerminalManager(
            project_path=project_path,
            max_terminals=MAX_TERMINALS,
            terminal_buffer_size=TERMINAL_BUFFER_SIZE,
            terminal_display_size=TERMINAL_DISPLAY_SIZE,
            broadcast_callback=message_callback
        )
        
        print(f"[WebTerminal] 初始化完成，项目路径: {project_path}")
        print(f"[WebTerminal] 思考模式: {'开启' if thinking_mode else '关闭'}")
        print(f"[WebTerminal] 对话管理已就绪")
        
        # 设置token更新回调
        if message_callback is not None:
            self.context_manager._web_terminal_callback = message_callback
            self.context_manager._focused_files = self.focused_files
            print(f"[WebTerminal] 实时token统计已启用")
        else:
            print(f"[WebTerminal] 警告：message_callback为None，无法启用实时token统计")
    # ===========================================
    # 新增：对话管理相关方法（Web版本）
    # ===========================================
    
    def create_new_conversation(self, thinking_mode: bool = None) -> Dict:
        """
        创建新对话（Web版本）
        
        Args:
            thinking_mode: 思考模式，None则使用当前设置
            
        Returns:
            Dict: 包含新对话信息
        """
        if thinking_mode is None:
            thinking_mode = self.thinking_mode
            
        try:
            conversation_id = self.context_manager.start_new_conversation(
                project_path=self.project_path,
                thinking_mode=thinking_mode
            )
            
            # 重置相关状态
            if self.thinking_mode:
                self.api_client.start_new_task()
            
            self.read_file_usage_tracker.clear()
            self.current_session_id += 1
            
            return {
                "success": True,
                "conversation_id": conversation_id,
                "message": f"已创建新对话: {conversation_id}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"创建新对话失败: {e}"
            }
    
    def load_conversation(self, conversation_id: str) -> Dict:
        """
        加载指定对话（Web版本）
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            Dict: 加载结果
        """
        try:
            success = self.context_manager.load_conversation_by_id(conversation_id)
            if success:
                # 重置相关状态
                if self.thinking_mode:
                    self.api_client.start_new_task()
                
                self.read_file_usage_tracker.clear()
                self.current_session_id += 1
                
                # 获取对话信息
                conversation_data = self.context_manager.conversation_manager.load_conversation(conversation_id)
                
                return {
                    "success": True,
                    "conversation_id": conversation_id,
                    "title": conversation_data.get("title", "未知对话"),
                    "messages_count": len(self.context_manager.conversation_history),
                    "message": f"对话已加载: {conversation_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "对话不存在或加载失败",
                    "message": f"对话加载失败: {conversation_id}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"加载对话异常: {e}"
            }
    
    def get_conversations_list(self, limit: int = 20, offset: int = 0) -> Dict:
        """获取对话列表（Web版本）"""
        try:
            result = self.context_manager.get_conversation_list(limit=limit, offset=offset)
            return {
                "success": True,
                "data": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"获取对话列表失败: {e}"
            }
    
    def delete_conversation(self, conversation_id: str) -> Dict:
        """删除指定对话（Web版本）"""
        try:
            success = self.context_manager.delete_conversation_by_id(conversation_id)
            if success:
                return {
                    "success": True,
                    "message": f"对话已删除: {conversation_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "删除失败",
                    "message": f"对话删除失败: {conversation_id}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"删除对话异常: {e}"
            }
    
    def search_conversations(self, query: str, limit: int = 20) -> Dict:
        """搜索对话（Web版本）"""
        try:
            results = self.context_manager.search_conversations(query, limit)
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"搜索对话失败: {e}"
            }
    
    # ===========================================
    # 修改现有方法，保持兼容性
    # ===========================================
    
    def get_status(self) -> Dict:
        """获取系统状态（Web版本，集成对话信息）"""
        # 获取基础状态
        context_status = self.context_manager.check_context_size()
        memory_stats = self.memory_manager.get_memory_stats()
        structure = self.context_manager.get_project_structure()
        
        # 聚焦文件状态 - 使用与 /api/focused 相同的格式（字典格式）
        focused_files_dict = {}
        for path, content in self.focused_files.items():
            focused_files_dict[path] = {
                "content": content,
                "size": len(content),
                "lines": content.count('\n') + 1
            }
        
        # 终端状态
        terminal_status = None
        if self.terminal_manager:
            terminal_status = self.terminal_manager.list_terminals()
        
        # 新增：对话状态
        conversation_stats = self.context_manager.get_conversation_statistics()
        
        # 构建状态信息
        status = {
            "project_path": self.project_path,
            "thinking_mode": self.thinking_mode,
            "thinking_status": self.get_thinking_mode_status(),
            "context": {
                "usage_percent": context_status['usage_percent'],
                "total_size": context_status['sizes']['total'],
                "conversation_count": len(self.context_manager.conversation_history)
            },
            "focused_files": focused_files_dict,  # 使用字典格式，与 /api/focused 一致
            "focused_files_count": len(self.focused_files),  # 单独提供计数
            "terminals": terminal_status,
            "project": {
                "total_files": structure['total_files'],
                "total_size": structure['total_size']
            },
            "memory": {
                "main": memory_stats['main_memory']['lines'],
                "task": memory_stats['task_memory']['lines']
            },
            # 新增：对话状态
            "conversation": {
                "current_id": self.context_manager.current_conversation_id,
                "total_conversations": conversation_stats.get('total_conversations', 0),
                "total_messages": conversation_stats.get('total_messages', 0),
                "total_tools": conversation_stats.get('total_tools', 0)
            }
        }
        
        return status
    
    def get_thinking_mode_status(self) -> str:
        """获取思考模式状态描述"""
        if not self.thinking_mode:
            return "快速模式"
        else:
            if self.api_client.current_task_first_call:
                return "思考模式（等待新任务）"
            else:
                return "思考模式（任务进行中）"
    
    def get_focused_files_info(self) -> Dict:
        """获取聚焦文件信息（用于WebSocket更新）- 使用与 /api/focused 一致的格式"""
        focused_files_dict = {}
        for path, content in self.focused_files.items():
            focused_files_dict[path] = {
                "content": content,
                "size": len(content),
                "lines": content.count('\n') + 1
            }
        
        return focused_files_dict
    
    def broadcast(self, event_type: str, data: Dict):
        """广播事件到WebSocket"""
        if self.message_callback:
            self.message_callback(event_type, data)
    
    # ===========================================
    # 覆盖父类方法，添加Web特有的广播功能
    # ===========================================
    
    async def handle_tool_call(self, tool_name: str, arguments: Dict) -> str:
        """
        处理工具调用（Web版本）
        覆盖父类方法，添加增强的实时广播功能
        """
        # 立即广播工具执行开始事件（不等待）
        self.broadcast('tool_execution_start', {
            'tool': tool_name,
            'arguments': arguments,
            'status': 'executing',
            'message': f'正在执行 {tool_name}...'
        })
        
        # 对于某些工具，发送更详细的状态
        if tool_name == "create_file":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'creating',
                'detail': f'创建文件: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "read_file":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'reading',
                'detail': f'读取文件: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "confirm_read_or_focus":
            # 新增：确认读取或聚焦工具的广播
            choice = arguments.get("choice", "未知")
            file_path = arguments.get("file_path", "未知路径")
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'confirming',
                'detail': f'确认操作: {choice} - {file_path}'
            })
        elif tool_name == "modify_file":
            operation = arguments.get("operation", "未知操作")
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'modifying',
                'detail': f'修改文件 ({operation}): {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "edit_lines":
            operation = arguments.get("operation", "未知操作")
            start_line = arguments.get("start_line", "?")
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'editing_lines',
                'detail': f'行编辑 ({operation}) 从第{start_line}行: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "delete_file":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'deleting',
                'detail': f'删除文件: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "focus_file":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'focusing',
                'detail': f'聚焦文件: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "unfocus_file":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'unfocusing',
                'detail': f'取消聚焦: {arguments.get("path", "未知路径")}'
            })
        elif tool_name == "web_search":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'searching',
                'detail': f'搜索: {arguments.get("query", "")}'
            })
        elif tool_name == "extract_webpage":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'extracting',
                'detail': f'提取网页: {arguments.get("url", "")}'
            })
        elif tool_name == "run_python":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'running_code',
                'detail': '执行Python代码'
            })
        elif tool_name == "run_command":
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'running_command',
                'detail': f'执行命令: {arguments.get("command", "")}'
            })
        elif tool_name == "terminal_session":
            action = arguments.get("action", "")
            session_name = arguments.get("session_name", "default")
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': f'terminal_{action}',
                'detail': f'终端操作: {action} - {session_name}'
            })
        elif tool_name == "terminal_input":
            command = arguments.get("command", "")
            # 只显示命令的前50个字符避免过长
            display_command = command[:50] + "..." if len(command) > 50 else command
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'sending_input',
                'detail': f'发送终端输入: {display_command}'
            })
        elif tool_name == "sleep":
            seconds = arguments.get("seconds", 1)
            reason = arguments.get("reason", "等待操作完成")
            self.broadcast('tool_status', {
                'tool': tool_name,
                'status': 'waiting',
                'detail': f'等待 {seconds} 秒: {reason}'
            })
        
        # 调用父类的工具处理（包含我们的新逻辑）
        result = await super().handle_tool_call(tool_name, arguments)
        
        # 解析结果并广播工具结束事件
        try:
            result_data = json.loads(result)
            success = result_data.get('success', False)
            
            # 特殊处理某些错误类型
            if not success:
                error_msg = result_data.get('error', '执行失败')
                
                # 检查是否是参数预检查失败
                if '参数过大' in error_msg or '内容过长' in error_msg:
                    self.broadcast('tool_execution_end', {
                        'tool': tool_name,
                        'success': False,
                        'result': result_data,
                        'message': f'{tool_name} 执行失败: 参数过长',
                        'error_type': 'parameter_too_long',
                        'suggestion': result_data.get('suggestion', '建议分块处理')
                    })
                elif 'JSON解析' in error_msg or '参数解析失败' in error_msg:
                    self.broadcast('tool_execution_end', {
                        'tool': tool_name,
                        'success': False,
                        'result': result_data,
                        'message': f'{tool_name} 执行失败: 参数格式错误',
                        'error_type': 'parameter_format_error',
                        'suggestion': result_data.get('suggestion', '请检查参数格式')
                    })
                elif 'requires_confirmation' in result_data:
                    # 特殊处理需要确认的情况（read_file拦截）
                    self.broadcast('tool_execution_end', {
                        'tool': tool_name,
                        'success': False,
                        'result': result_data,
                        'message': f'{tool_name}: 需要用户确认操作方式',
                        'error_type': 'requires_confirmation',
                        'instruction': result_data.get('instruction', '')
                    })
                else:
                    # 一般错误
                    self.broadcast('tool_execution_end', {
                        'tool': tool_name,
                        'success': False,
                        'result': result_data,
                        'message': f'{tool_name} 执行失败: {error_msg}',
                        'error_type': 'general_error'
                    })
            else:
                # 成功的情况
                success_msg = result_data.get('message', f'{tool_name} 执行成功')
                self.broadcast('tool_execution_end', {
                    'tool': tool_name,
                    'success': True,
                    'result': result_data,
                    'message': success_msg
                })
                
        except json.JSONDecodeError:
            # 无法解析JSON结果
            success = False
            result_data = {'output': result, 'raw_result': True}
            self.broadcast('tool_execution_end', {
                'tool': tool_name,
                'success': False,
                'result': result_data,
                'message': f'{tool_name} 返回了非JSON格式结果',
                'error_type': 'invalid_result_format'
            })
        
        # 如果是终端相关操作，广播终端更新
        if tool_name in ['terminal_session', 'terminal_input'] and self.terminal_manager:
            try:
                terminals = self.terminal_manager.get_terminal_list()
                self.broadcast('terminal_list_update', {
                    'terminals': terminals,
                    'active': self.terminal_manager.active_terminal
                })
            except Exception as e:
                logger.error(f"广播终端更新失败: {e}")
        
        # 如果是文件操作，广播文件树更新
        if tool_name in ['create_file', 'delete_file', 'rename_file', 'create_folder', 'confirm_read_or_focus']:
            try:
                structure = self.context_manager.get_project_structure()
                self.broadcast('file_tree_update', structure)
            except Exception as e:
                logger.error(f"广播文件树更新失败: {e}")
        
        
        # 如果是聚焦操作，广播聚焦文件更新
        if tool_name in ['focus_file', 'unfocus_file', 'modify_file', 'edit_lines', 'confirm_read_or_focus']:
            try:
                focused_files_dict = self.get_focused_files_info()
                self.broadcast('focused_files_update', focused_files_dict)
                
                # 聚焦文件变化后，更新token统计
                self.context_manager.safe_broadcast_token_update()
                
            except Exception as e:
                logger.error(f"广播聚焦文件更新失败: {e}")
        
        # 如果是记忆操作，广播记忆状态更新
        if tool_name == 'update_memory':
            try:
                memory_stats = self.memory_manager.get_memory_stats()
                self.broadcast('memory_update', {
                    'main': memory_stats['main_memory']['lines'],
                    'task': memory_stats['task_memory']['lines']
                })
            except Exception as e:
                logger.error(f"广播记忆更新失败: {e}")
        
        return result
    
    def build_context(self) -> Dict:
        """构建上下文（Web版本）"""
        context = super().build_context()
        
        # 添加Web特有的上下文信息
        context['web_mode'] = True
        context['terminal_sessions'] = []
        
        if self.terminal_manager:
            for name, terminal in self.terminal_manager.terminals.items():
                context['terminal_sessions'].append({
                    'name': name,
                    'is_active': name == self.terminal_manager.active_terminal,
                    'is_running': terminal.is_running
                })
        
        # 添加对话信息
        context['conversation_info'] = {
            'current_id': self.context_manager.current_conversation_id,
            'messages_count': len(self.context_manager.conversation_history)
        }
        
        return context
    
    async def confirm_action(self, action: str, arguments: Dict) -> bool:
        """
        确认危险操作（Web版本）
        在Web模式下，我们自动确认或通过WebSocket请求确认
        """
        # 在Web模式下，暂时自动确认
        # 未来可以通过WebSocket向前端请求确认
        print(f"[WebTerminal] 自动确认操作: {action}")
        
        # 广播确认事件，让前端知道正在执行危险操作
        self.broadcast('dangerous_action', {
            'action': action,
            'arguments': arguments,
            'auto_confirmed': True
        })
        
        return True
    
    def __del__(self):
        """析构函数，确保资源释放"""
        try:
            # 保存当前对话
            if hasattr(self, 'context_manager') and self.context_manager:
                if self.context_manager.current_conversation_id:
                    self.context_manager.save_current_conversation()
            
            # 关闭所有终端
            if hasattr(self, 'terminal_manager') and self.terminal_manager:
                self.terminal_manager.close_all()
                
        except Exception as e:
            print(f"[WebTerminal] 资源清理失败: {e}")