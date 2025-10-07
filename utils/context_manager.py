# utils/context_manager.py - 上下文管理器（集成对话持久化和Token统计）

import os
import json
import tiktoken
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from config import MAX_CONTEXT_SIZE, DATA_DIR, PROMPTS_DIR
from utils.conversation_manager import ConversationManager

class ContextManager:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.temp_files = {}  # 临时加载的文件内容
        self.file_annotations = {}  # 文件备注
        self.conversation_history = []  # 当前对话历史（内存中）
        
        # 新增：对话持久化管理器
        self.conversation_manager = ConversationManager()
        self.current_conversation_id: Optional[str] = None
        self.auto_save_enabled = True
        
        # 新增：Token计算相关
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            print(f"⚠️ tiktoken初始化失败: {e}")
            self.encoding = None
        
        # 用于接收Web终端的回调函数
        self._web_terminal_callback = None
        self._focused_files = {}
        
        self.load_annotations()
    
    def set_web_terminal_callback(self, callback):
        """设置Web终端回调函数，用于广播事件"""
        self._web_terminal_callback = callback
    
    def set_focused_files(self, focused_files: Dict):
        """设置聚焦文件信息，用于token计算"""
        self._focused_files = focused_files
    
    def load_annotations(self):
        """加载文件备注"""
        annotations_file = Path(DATA_DIR) / "file_annotations.json"
        if annotations_file.exists():
            try:
                with open(annotations_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        self.file_annotations = json.loads(content)
                    else:
                        self.file_annotations = {}
            except (json.JSONDecodeError, KeyError):
                print(f"⚠️ [警告] 文件备注格式错误，将重新初始化")
                self.file_annotations = {}
                self.save_annotations()
    
    def save_annotations(self):
        """保存文件备注"""
        annotations_file = Path(DATA_DIR) / "file_annotations.json"
        with open(annotations_file, 'w', encoding='utf-8') as f:
            json.dump(self.file_annotations, f, ensure_ascii=False, indent=2)
    
    # ===========================================
    # 新增：Token统计相关方法
    # ===========================================
    
    def calculate_input_tokens(self, messages: List[Dict], tools: List[Dict] = None) -> int:
        if not self.encoding:
            return 0
        
        try:
            total_tokens = 0
            
            print(f"[Debug] 开始计算输入token，messages数量: {len(messages)}")
            
            # 详细分析每条消息
            for i, message in enumerate(messages):
                content = message.get("content", "")
                role = message.get("role", "unknown")
                if content:
                    msg_tokens = len(self.encoding.encode(content))
                    total_tokens += msg_tokens
                    print(f"[Debug] 消息 {i+1} ({role}): {msg_tokens} tokens - {content[:50]}...")
            
            print(f"[Debug] 消息总token: {total_tokens}")
            
            # 工具定义
            if tools:
                tools_str = json.dumps(tools, ensure_ascii=False)
                tools_tokens = len(self.encoding.encode(tools_str))
                total_tokens += tools_tokens
                print(f"[Debug] 工具定义token: {tools_tokens}")
            
            print(f"[Debug] 最终输入token: {total_tokens}")
            return total_tokens
        except Exception as e:
            print(f"计算输入token失败: {e}")
            return 0
    
    def calculate_output_tokens(self, ai_content: str) -> int:
        """
        计算AI输出的token数量
        
        Args:
            ai_content: AI输出的完整内容（包括thinking、文本、工具调用）
        
        Returns:
            int: 输出token数量
        """
        if not self.encoding or not ai_content:
            return 0
        
        try:
            return len(self.encoding.encode(ai_content))
        except Exception as e:
            print(f"计算输出token失败: {e}")
            return 0
    
    def update_token_statistics(self, input_tokens: int, output_tokens: int) -> bool:
        """
        更新当前对话的token统计
        
        Args:
            input_tokens: 输入token数量
            output_tokens: 输出token数量
        
        Returns:
            bool: 更新是否成功
        """
        if not self.current_conversation_id:
            print("⚠️ 没有当前对话ID，跳过token统计更新")
            return False
        
        try:
            success = self.conversation_manager.update_token_statistics(
                self.current_conversation_id,
                input_tokens,
                output_tokens
            )
            
            if success:
                # 广播token更新事件
                self.safe_broadcast_token_update()
            
            return success
        except Exception as e:
            print(f"更新token统计失败: {e}")
            return False
    
    def get_conversation_token_statistics(self, conversation_id: str = None) -> Optional[Dict]:
        """
        获取指定对话的token统计
        
        Args:
            conversation_id: 对话ID，默认为当前对话
        
        Returns:
            Dict: Token统计信息
        """
        target_id = conversation_id or self.current_conversation_id
        if not target_id:
            return None
        
        return self.conversation_manager.get_token_statistics(target_id)
    
    # ===========================================
    # 新增：对话持久化相关方法
    # ===========================================
    
    def start_new_conversation(self, project_path: str = None, thinking_mode: bool = False) -> str:
        """
        开始新对话
        
        Args:
            project_path: 项目路径，默认使用当前项目路径
            thinking_mode: 思考模式
        
        Returns:
            str: 新对话ID
        """
        if project_path is None:
            project_path = str(self.project_path)
        
        # 保存当前对话（如果有的话）
        if self.current_conversation_id and self.conversation_history:
            self.save_current_conversation()
        
        # 创建新对话
        conversation_id = self.conversation_manager.create_conversation(
            project_path=project_path,
            thinking_mode=thinking_mode,
            initial_messages=[]
        )
        
        # 重置当前状态
        self.current_conversation_id = conversation_id
        self.conversation_history = []
        
        print(f"📝 开始新对话: {conversation_id}")
        return conversation_id
    
    def load_conversation_by_id(self, conversation_id: str) -> bool:
        """
        加载指定对话
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            bool: 加载是否成功
        """
        # 先保存当前对话
        if self.current_conversation_id and self.conversation_history:
            self.save_current_conversation()
        
        # 加载指定对话
        conversation_data = self.conversation_manager.load_conversation(conversation_id)
        if not conversation_data:
            print(f"⌘ 对话 {conversation_id} 不存在")
            return False
        
        # 更新当前状态
        self.current_conversation_id = conversation_id
        self.conversation_history = conversation_data.get("messages", [])
        
        # 更新项目路径（如果对话中有的话）
        metadata = conversation_data.get("metadata", {})
        if "project_path" in metadata:
            self.project_path = Path(metadata["project_path"])
        
        print(f"📖 加载对话: {conversation_id} - {conversation_data.get('title', '未知标题')}")
        print(f"📊 包含 {len(self.conversation_history)} 条消息")
        
        return True
    
    def save_current_conversation(self) -> bool:
        """
        保存当前对话
        
        Returns:
            bool: 保存是否成功
        """
        if not self.current_conversation_id:
            print("⚠️ 没有当前对话ID，无法保存")
            return False
        
        if not self.auto_save_enabled:
            return False
        
        try:
            success = self.conversation_manager.save_conversation(
                conversation_id=self.current_conversation_id,
                messages=self.conversation_history,
                project_path=str(self.project_path)
            )
            
            if success:
                print(f"💾 对话已自动保存: {self.current_conversation_id}")
            else:
                print(f"⌘ 对话保存失败: {self.current_conversation_id}")
            
            return success
        except Exception as e:
            print(f"⌘ 保存对话异常: {e}")
            return False
    
    def auto_save_conversation(self):
        """自动保存对话（静默模式，减少日志输出）"""
        if self.auto_save_enabled and self.current_conversation_id and self.conversation_history:
            try:
                self.conversation_manager.save_conversation(
                    conversation_id=self.current_conversation_id,
                    messages=self.conversation_history,
                    project_path=str(self.project_path)
                )
                # 静默保存，不输出日志
            except Exception as e:
                print(f"⌘ 自动保存异常: {e}")
    
    def get_conversation_list(self, limit: int = 50, offset: int = 0) -> Dict:
        """获取对话列表"""
        return self.conversation_manager.get_conversation_list(limit=limit, offset=offset)
    
    def delete_conversation_by_id(self, conversation_id: str) -> bool:
        """删除指定对话"""
        # 如果是当前对话，清理状态
        if self.current_conversation_id == conversation_id:
            self.current_conversation_id = None
            self.conversation_history = []
        
        return self.conversation_manager.delete_conversation(conversation_id)
    
    def search_conversations(self, query: str, limit: int = 20) -> List[Dict]:
        """搜索对话"""
        return self.conversation_manager.search_conversations(query, limit)
    
    def get_conversation_statistics(self) -> Dict:
        """获取对话统计"""
        return self.conversation_manager.get_statistics()
    
    # ===========================================
    # 修改现有方法，集成自动保存和Token统计
    # ===========================================
    
    def safe_broadcast_token_update(self):
        """安全的token更新广播（只广播累计统计，不重新计算）"""
        try:
            print(f"[Debug] 尝试广播token更新")
            
            # 检查是否有回调函数
            if not hasattr(self, '_web_terminal_callback'):
                print(f"[Debug] 没有_web_terminal_callback属性")
                return
                
            if not self._web_terminal_callback:
                print(f"[Debug] _web_terminal_callback为None")
                return
            
            if not self.current_conversation_id:
                print(f"[Debug] 没有当前对话ID")
                return
                
            print(f"[Debug] 广播token统计，对话ID: {self.current_conversation_id}")
            
            # 只获取已有的累计token统计，不重新计算
            cumulative_stats = self.get_conversation_token_statistics()
            
            # 准备广播数据
            broadcast_data = {
                'conversation_id': self.current_conversation_id,
                'cumulative_input_tokens': cumulative_stats.get("total_input_tokens", 0) if cumulative_stats else 0,
                'cumulative_output_tokens': cumulative_stats.get("total_output_tokens", 0) if cumulative_stats else 0,
                'cumulative_total_tokens': cumulative_stats.get("total_tokens", 0) if cumulative_stats else 0,
                'updated_at': datetime.now().isoformat()
            }
            
            print(f"[Debug] Token统计: 累计输入={broadcast_data['cumulative_input_tokens']}, 累计输出={broadcast_data['cumulative_output_tokens']}")
            
            # 广播到前端
            self._web_terminal_callback('token_update', broadcast_data)
            
            print(f"[Debug] token更新已广播")
            
        except Exception as e:
            print(f"[Debug] 广播token更新失败: {e}")
            import traceback
            traceback.print_exc()
    
    def add_conversation(self, role: str, content: str, tool_calls: Optional[List[Dict]] = None, tool_call_id: Optional[str] = None, name: Optional[str] = None):
        """添加对话记录（改进版：集成自动保存 + 智能token统计）"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        # 如果是assistant消息且有工具调用，保存完整格式
        if role == "assistant" and tool_calls:
            # 确保工具调用格式完整
            formatted_tool_calls = []
            for tc in tool_calls:
                # 如果是简化格式，补全它
                if "function" in tc and not tc.get("id"):
                    formatted_tc = {
                        "id": f"call_{datetime.now().timestamp()}_{tc['function'].get('name', 'unknown')}",
                        "type": "function",
                        "function": tc["function"]
                    }
                else:
                    formatted_tc = tc
                formatted_tool_calls.append(formatted_tc)
            message["tool_calls"] = formatted_tool_calls
        
        # 如果是tool消息，保存必要信息
        if role == "tool":
            if tool_call_id:
                message["tool_call_id"] = tool_call_id
            if name:
                message["name"] = name
        
        self.conversation_history.append(message)
        
        # 自动保存
        self.auto_save_conversation()
        
        # 特殊处理：如果是用户消息，需要计算并更新输入token
        if role == "user":
            self._handle_user_message_token_update()
        else:
            # 其他消息只需要广播现有统计
            print(f"[Debug] 添加{role}消息后广播token更新")
            self.safe_broadcast_token_update()
    
    def _handle_user_message_token_update(self):
        """处理用户消息的token更新（计算输入token并更新统计）"""
        try:
            print(f"[Debug] 用户发送消息，开始计算输入token")
            
            # 需要访问web_terminal来构建完整的messages
            # 这里有个问题：add_conversation是在用户消息添加后调用的
            # 但我们需要构建包含这条消息的完整context来计算输入token
            
            # 临时解决方案：延迟计算，让web_server负责在构建messages后计算输入token
            # 这里只广播现有统计
            print(f"[Debug] 用户消息添加完成，广播现有token统计")
            self.safe_broadcast_token_update()
            
        except Exception as e:
            print(f"[Debug] 处理用户消息token更新失败: {e}")
            # 失败时仍然广播现有统计
            self.safe_broadcast_token_update()
    
    def add_tool_result(self, tool_call_id: str, function_name: str, result: str):
        """添加工具调用结果（保留方法以兼容）"""
        self.add_conversation(
            role="tool",
            content=result,
            tool_call_id=tool_call_id,
            name=function_name
        )
    
    # ===========================================
    # 废弃旧的保存/加载方法，保持兼容性
    # ===========================================
    
    def save_conversation(self):
        """保存对话历史（废弃，使用新的持久化系统）"""
        print("⚠️ save_conversation() 已废弃，使用新的持久化系统")
        return self.save_current_conversation()
    
    def load_conversation(self):
        """加载对话历史（废弃，使用新的持久化系统）"""
        print("⚠️ load_conversation() 已废弃，使用 load_conversation_by_id()")
        # 兼容性：尝试加载最近的对话
        conversations = self.get_conversation_list(limit=1)
        if conversations["conversations"]:
            latest_conv = conversations["conversations"][0]
            return self.load_conversation_by_id(latest_conv["id"])
        return False
    
    # ===========================================
    # 保持原有的其他方法不变
    # ===========================================
    
    def get_project_structure(self) -> Dict:
        """获取项目文件结构"""
        structure = {
            "path": str(self.project_path),
            "files": [],
            "folders": [],
            "total_files": 0,
            "total_size": 0,
            "tree": {}  # 新增：树形结构数据
        }
        
        # 记录实际存在的文件
        existing_files = set()
        
        def scan_directory(path: Path, level: int = 0, max_level: int = 5, parent_tree: Dict = None):
            if level > max_level:
                return
            
            if parent_tree is None:
                parent_tree = structure["tree"]
            
            try:
                # 获取目录内容并排序（文件夹在前，文件在后）
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for item in items:
                    if item.name.startswith('.'):
                        continue
                    
                    relative_path = str(item.relative_to(self.project_path))
                    
                    if item.is_file():
                        existing_files.add(relative_path)  # 记录存在的文件
                        file_info = {
                            "name": item.name,
                            "path": relative_path,
                            "size": item.stat().st_size,
                            "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                            "annotation": self.file_annotations.get(relative_path, "")
                        }
                        structure["files"].append(file_info)
                        structure["total_files"] += 1
                        structure["total_size"] += file_info["size"]
                        
                        # 添加到树形结构
                        parent_tree[item.name] = {
                            "type": "file",
                            "path": relative_path,
                            "size": file_info["size"],
                            "annotation": file_info["annotation"]
                        }
                    
                    elif item.is_dir():
                        folder_info = {
                            "name": item.name,
                            "path": relative_path
                        }
                        structure["folders"].append(folder_info)
                        
                        # 创建文件夹节点
                        parent_tree[item.name] = {
                            "type": "folder",
                            "path": relative_path,
                            "children": {}
                        }
                        
                        # 递归扫描子目录
                        scan_directory(item, level + 1, max_level, parent_tree[item.name]["children"])
            except PermissionError:
                pass
        
        scan_directory(self.project_path)
        
        # 清理不存在文件的备注
        invalid_annotations = []
        for annotation_path in self.file_annotations.keys():
            if annotation_path not in existing_files:
                invalid_annotations.append(annotation_path)
        
        if invalid_annotations:
            for path in invalid_annotations:
                del self.file_annotations[path]
                print(f"🧹 清理无效备注: {path}")
            self.save_annotations()
        
        return structure
    
    def load_file(self, file_path: str) -> bool:
        """加载文件到临时上下文"""
        full_path = self.project_path / file_path
        
        if not full_path.exists():
            return False
        
        if not full_path.is_file():
            return False
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.temp_files[file_path] = content
                return True
        except Exception:
            return False
    
    def unload_file(self, file_path: str) -> bool:
        """从临时上下文移除文件"""
        if file_path in self.temp_files:
            del self.temp_files[file_path]
            return True
        return False
    
    def update_annotation(self, file_path: str, annotation: str):
        """更新文件备注"""
        self.file_annotations[file_path] = annotation
        self.save_annotations()
    
    def load_prompt(self, prompt_name: str) -> str:
        """加载prompt模板"""
        prompt_file = Path(PROMPTS_DIR) / f"{prompt_name}.txt"
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    
    def build_main_context(self, memory_content: str) -> Dict:
        """构建主终端上下文"""
        structure = self.get_project_structure()
        
        context = {
            "project_info": {
                "path": str(self.project_path),
                "file_tree": self._build_file_tree(structure),
                "file_annotations": self.file_annotations,
                "statistics": {
                    "total_files": structure["total_files"],
                    "total_size": f"{structure['total_size'] / 1024 / 1024:.2f}MB"
                }
            },
            "memory": memory_content,
            "conversation": self.conversation_history
        }
        
        return context
    
    def build_task_context(
        self,
        task_info: Dict,
        main_memory: str,
        task_memory: str,
        execution_results: List[Dict] = None
    ) -> Dict:
        """构建子任务上下文"""
        structure = self.get_project_structure()
        
        context = {
            "task_info": task_info,
            "project_info": {
                "path": str(self.project_path),
                "file_tree": self._build_file_tree(structure),
                "file_annotations": self.file_annotations
            },
            "memory": {
                "main_memory": main_memory,
                "task_memory": task_memory
            },
            "temp_files": self.temp_files,
            "execution_results": execution_results or [],
            "conversation": {
                "main": self.conversation_history[-10:],  # 最近10条主对话
                "sub": []  # 子任务对话
            }
        }
        
        return context
    
    def _build_file_tree(self, structure: Dict) -> str:
        """构建文件树字符串（修复版：正确显示树形结构）"""
        if not structure.get("tree"):
            return f"📁 {structure['path']}/\n(空项目)"
        
        lines = []
        project_name = Path(structure['path']).name
        lines.append(f"📁 {project_name}/")
        
        def build_tree_recursive(tree_dict: Dict, prefix: str = ""):
            """递归构建树形结构"""
            if not tree_dict:
                return
                
            # 将项目按类型和名称排序：文件夹在前，文件在后，同类型按名称排序
            items = list(tree_dict.items())
            folders = [(name, info) for name, info in items if info["type"] == "folder"]
            files = [(name, info) for name, info in items if info["type"] == "file"]
            
            # 排序
            folders.sort(key=lambda x: x[0].lower())
            files.sort(key=lambda x: x[0].lower())
            
            # 合并列表
            sorted_items = folders + files
            
            for i, (name, info) in enumerate(sorted_items):
                is_last = (i == len(sorted_items) - 1)
                
                # 选择连接符
                if is_last:
                    current_connector = "└── "
                    next_prefix = prefix + "    "
                else:
                    current_connector = "├── "
                    next_prefix = prefix + "│   "
                
                if info["type"] == "folder":
                    # 文件夹
                    lines.append(f"{prefix}{current_connector}📁 {name}/")
                    
                    # 递归处理子项目
                    if info.get("children"):
                        build_tree_recursive(info["children"], next_prefix)
                else:
                    # 文件
                    icon = self._get_file_icon(name)
                    size_info = self._format_file_size(info['size'])
                    
                    # 构建文件行
                    file_line = f"{prefix}{current_connector}{icon} {name}"
                    
                    # 添加大小信息（简化版）
                    if info['size'] > 1024:  # 只显示大于1KB的文件大小
                        file_line += f" {size_info}"
                    
                    # 添加备注
                    if info.get('annotation'):
                        file_line += f" # {info['annotation']}"
                    
                    lines.append(file_line)
        
        # 构建树形结构
        build_tree_recursive(structure["tree"])
        
        # 添加统计信息
        lines.append("")
        lines.append(f"📊 统计: {structure['total_files']} 个文件, {structure['total_size']/1024/1024:.2f}MB")
        
        return "\n".join(lines)
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"({size_bytes}B)"
        elif size_bytes < 1024 * 1024:
            return f"({size_bytes/1024:.1f}KB)"
        else:
            return f"({size_bytes/1024/1024:.1f}MB)"
    
    def _get_file_icon(self, filename: str) -> str:
        """根据文件类型返回合适的图标"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        icon_map = {
            'py': '🐍',      # Python
            'js': '📜',      # JavaScript
            'ts': '📘',      # TypeScript
            'jsx': '⚛️',     # React JSX
            'tsx': '⚛️',     # React TSX
            'java': '☕',    # Java
            'cpp': '⚙️',     # C++
            'c': '⚙️',       # C
            'h': '📎',       # Header files
            'cs': '💷',      # C#
            'go': '🐹',      # Go
            'rs': '🦀',      # Rust
            'rb': '💎',      # Ruby
            'php': '🐘',     # PHP
            'swift': '🦉',   # Swift
            'kt': '🟣',      # Kotlin
            'md': '📝',      # Markdown
            'txt': '📄',     # Text
            'json': '📊',    # JSON
            'yaml': '📋',    # YAML
            'yml': '📋',     # YAML
            'toml': '📋',    # TOML
            'xml': '📰',     # XML
            'html': '🌐',    # HTML
            'css': '🎨',     # CSS
            'scss': '🎨',    # SCSS
            'less': '🎨',    # LESS
            'sql': '🗃️',     # SQL
            'db': '🗄️',      # Database
            'sh': '💻',      # Shell script
            'bash': '💻',    # Bash script
            'bat': '💻',     # Batch file
            'ps1': '💻',     # PowerShell
            'env': '🔧',     # Environment
            'gitignore': '🚫', # Gitignore
            'dockerfile': '🐳', # Docker
            'png': '🖼️',     # Image
            'jpg': '🖼️',     # Image
            'jpeg': '🖼️',    # Image
            'gif': '🖼️',     # Image
            'svg': '🖼️',     # Image
            'ico': '🖼️',     # Icon
            'mp4': '🎬',     # Video
            'mp3': '🎵',     # Audio
            'wav': '🎵',     # Audio
            'pdf': '📕',     # PDF
            'doc': '📘',     # Word
            'docx': '📘',    # Word
            'xls': '📗',     # Excel
            'xlsx': '📗',    # Excel
            'ppt': '📙',     # PowerPoint
            'pptx': '📙',    # PowerPoint
            'zip': '📦',     # Archive
            'rar': '📦',     # Archive
            'tar': '📦',     # Archive
            'gz': '📦',      # Archive
            'log': '📋',     # Log file
            'lock': '🔒',    # Lock file
        }
        
        return icon_map.get(ext, '📄')  # 默认文件图标
    
    def check_context_size(self) -> Dict:
        """检查上下文大小"""
        sizes = {
            "temp_files": sum(len(content) for content in self.temp_files.values()),
            "conversation": sum(len(json.dumps(msg, ensure_ascii=False)) for msg in self.conversation_history),
            "total": 0
        }
        sizes["total"] = sum(sizes.values())
        
        return {
            "sizes": sizes,
            "is_overflow": sizes["total"] > MAX_CONTEXT_SIZE,
            "usage_percent": (sizes["total"] / MAX_CONTEXT_SIZE) * 100
        }
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
        
        # 添加对话历史
        for conv in context["conversation"]:
            if conv["role"] == "assistant":
                message = {
                    "role": conv["role"],
                    "content": conv["content"]
                }
                if "tool_calls" in conv and conv["tool_calls"]:
                    message["tool_calls"] = conv["tool_calls"]
                messages.append(message)
            elif conv["role"] == "tool":
                message = {
                    "role": "tool",
                    "content": conv["content"],
                    "tool_call_id": conv.get("tool_call_id", ""),
                    "name": conv.get("name", "")
                }
                messages.append(message)
            else:
                messages.append({
                    "role": conv["role"],
                    "content": conv["content"]
                })
        
        # 添加聚焦文件内容
        if self._focused_files:
            focused_content = "\n\n=== 🔍 正在聚焦的文件 ===\n"
            focused_content += f"(共 {len(self._focused_files)} 个文件处于聚焦状态)\n"
            
            for path, content in self._focused_files.items():
                size_kb = len(content) / 1024
                focused_content += f"\n--- 文件: {path} ({size_kb:.1f}KB) ---\n"
                focused_content += f"```\n{content}\n```\n"
            
            focused_content += "\n=== 聚焦文件结束 ===\n"
            messages.append({
                "role": "system",
                "content": focused_content
            })
        
        # 添加终端内容（如果有的话）
        # 这里需要从参数传入或获取
        
        return messages