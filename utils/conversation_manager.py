# utils/conversation_manager.py - 对话持久化管理器（集成Token统计）

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from config import DATA_DIR
import tiktoken

@dataclass
class ConversationMetadata:
    """对话元数据"""
    id: str
    title: str
    created_at: str
    updated_at: str
    project_path: str
    thinking_mode: bool
    total_messages: int
    total_tools: int
    status: str = "active"  # active, archived, error

class ConversationManager:
    """对话持久化管理器"""
    
    def __init__(self):
        self.conversations_dir = Path(DATA_DIR) / "conversations"
        self.index_file = self.conversations_dir / "index.json"
        self.current_conversation_id: Optional[str] = None
        self._ensure_directories()
        self._load_index()
        
        # 初始化tiktoken编码器
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            print(f"⚠️ tiktoken初始化失败: {e}")
            self.encoding = None
    
    def _ensure_directories(self):
        """确保必要的目录存在"""
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        
        # 如果索引文件不存在，创建空索引
        if not self.index_file.exists():
            self._save_index({})
    
    def _load_index(self) -> Dict:
        """加载对话索引"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
            return {}
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️ 加载对话索引失败，将重新创建: {e}")
            return {}
    
    def _save_index(self, index: Dict):
        """保存对话索引"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⌘ 保存对话索引失败: {e}")
    
    def _generate_conversation_id(self) -> str:
        """生成唯一的对话ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 添加毫秒确保唯一性
        ms = int(time.time() * 1000) % 1000
        return f"conv_{timestamp}_{ms:03d}"
    
    def _get_conversation_file_path(self, conversation_id: str) -> Path:
        """获取对话文件路径"""
        return self.conversations_dir / f"{conversation_id}.json"
    
    def _extract_title_from_messages(self, messages: List[Dict]) -> str:
        """从消息中提取标题"""
        # 找到第一个用户消息作为标题
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "").strip()
                if content:
                    # 取前50个字符作为标题
                    title = content[:50]
                    if len(content) > 50:
                        title += "..."
                    return title
        return "新对话"
    
    def _count_tools_in_messages(self, messages: List[Dict]) -> int:
        """统计消息中的工具调用数量"""
        tool_count = 0
        for msg in messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                tool_calls = msg.get("tool_calls", [])
                tool_count += len(tool_calls) if isinstance(tool_calls, list) else 0
            elif msg.get("role") == "tool":
                tool_count += 1
        return tool_count
    
    def _initialize_token_statistics(self) -> Dict:
        """初始化Token统计结构"""
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "updated_at": datetime.now().isoformat()
        }
    
    def _validate_token_statistics(self, data: Dict) -> Dict:
        """验证并修复Token统计数据"""
        token_stats = data.get("token_statistics", {})
        
        # 确保必要字段存在
        if "total_input_tokens" not in token_stats:
            token_stats["total_input_tokens"] = 0
        if "total_output_tokens" not in token_stats:
            token_stats["total_output_tokens"] = 0
        if "updated_at" not in token_stats:
            token_stats["updated_at"] = datetime.now().isoformat()
        
        # 确保数值类型正确
        try:
            token_stats["total_input_tokens"] = int(token_stats["total_input_tokens"])
            token_stats["total_output_tokens"] = int(token_stats["total_output_tokens"])
        except (ValueError, TypeError):
            print("⚠️ Token统计数据损坏，重置为0")
            token_stats["total_input_tokens"] = 0
            token_stats["total_output_tokens"] = 0
        
        data["token_statistics"] = token_stats
        return data
    
    def create_conversation(
        self, 
        project_path: str, 
        thinking_mode: bool = False,
        initial_messages: List[Dict] = None
    ) -> str:
        """
        创建新对话
        
        Args:
            project_path: 项目路径
            thinking_mode: 思考模式
            initial_messages: 初始消息列表
        
        Returns:
            conversation_id: 对话ID
        """
        conversation_id = self._generate_conversation_id()
        messages = initial_messages or []
        
        # 创建对话数据
        conversation_data = {
            "id": conversation_id,
            "title": self._extract_title_from_messages(messages),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": messages,
            "metadata": {
                "project_path": project_path,
                "thinking_mode": thinking_mode,
                "total_messages": len(messages),
                "total_tools": self._count_tools_in_messages(messages),
                "status": "active"
            },
            "token_statistics": self._initialize_token_statistics()  # 新增
        }
        
        # 保存对话文件
        self._save_conversation_file(conversation_id, conversation_data)
        
        # 更新索引
        self._update_index(conversation_id, conversation_data)
        
        self.current_conversation_id = conversation_id
        print(f"📝 创建新对话: {conversation_id} - {conversation_data['title']}")
        
        return conversation_id
    
    def _save_conversation_file(self, conversation_id: str, data: Dict):
        """保存对话文件"""
        try:
            # 确保Token统计数据有效
            data = self._validate_token_statistics(data)
            
            file_path = self._get_conversation_file_path(conversation_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⌘ 保存对话文件失败 {conversation_id}: {e}")
    
    def _update_index(self, conversation_id: str, conversation_data: Dict):
        """更新对话索引"""
        try:
            index = self._load_index()
            
            # 创建元数据
            metadata = ConversationMetadata(
                id=conversation_id,
                title=conversation_data["title"],
                created_at=conversation_data["created_at"],
                updated_at=conversation_data["updated_at"],
                project_path=conversation_data["metadata"]["project_path"],
                thinking_mode=conversation_data["metadata"]["thinking_mode"],
                total_messages=conversation_data["metadata"]["total_messages"],
                total_tools=conversation_data["metadata"]["total_tools"],
                status=conversation_data["metadata"].get("status", "active")
            )
            
            # 添加到索引
            index[conversation_id] = {
                "title": metadata.title,
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
                "project_path": metadata.project_path,
                "thinking_mode": metadata.thinking_mode,
                "total_messages": metadata.total_messages,
                "total_tools": metadata.total_tools,
                "status": metadata.status
            }
            
            self._save_index(index)
        except Exception as e:
            print(f"⌘ 更新对话索引失败: {e}")
    
    def save_conversation(
        self, 
        conversation_id: str, 
        messages: List[Dict],
        project_path: str = None,
        thinking_mode: bool = None
    ) -> bool:
        """
        保存对话（更新现有对话）
        
        Args:
            conversation_id: 对话ID
            messages: 消息列表
            project_path: 项目路径
            thinking_mode: 思考模式
        
        Returns:
            bool: 保存是否成功
        """
        try:
            # 加载现有对话数据
            existing_data = self.load_conversation(conversation_id)
            if not existing_data:
                print(f"⚠️ 对话 {conversation_id} 不存在，无法更新")
                return False
            
            # 更新数据
            existing_data["messages"] = messages
            existing_data["updated_at"] = datetime.now().isoformat()
            
            # 更新标题（如果消息发生变化）
            new_title = self._extract_title_from_messages(messages)
            if new_title != "新对话":
                existing_data["title"] = new_title
            
            # 更新元数据
            if project_path is not None:
                existing_data["metadata"]["project_path"] = project_path
            if thinking_mode is not None:
                existing_data["metadata"]["thinking_mode"] = thinking_mode
            
            existing_data["metadata"]["total_messages"] = len(messages)
            existing_data["metadata"]["total_tools"] = self._count_tools_in_messages(messages)
            
            # 确保Token统计结构存在（向后兼容）
            if "token_statistics" not in existing_data:
                existing_data["token_statistics"] = self._initialize_token_statistics()
            else:
                existing_data["token_statistics"]["updated_at"] = datetime.now().isoformat()
            
            # 保存文件
            self._save_conversation_file(conversation_id, existing_data)
            
            # 更新索引
            self._update_index(conversation_id, existing_data)
            
            return True
        except Exception as e:
            print(f"⌘ 保存对话失败 {conversation_id}: {e}")
            return False
    
    def load_conversation(self, conversation_id: str) -> Optional[Dict]:
        """
        加载对话数据
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            Dict: 对话数据，如果不存在返回None
        """
        try:
            file_path = self._get_conversation_file_path(conversation_id)
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return None
                
                data = json.loads(content)
                
                # 向后兼容：确保Token统计结构存在
                if "token_statistics" not in data:
                    data["token_statistics"] = self._initialize_token_statistics()
                    # 自动保存修复后的数据
                    self._save_conversation_file(conversation_id, data)
                    print(f"🔧 为对话 {conversation_id} 添加Token统计结构")
                else:
                    # 验证现有Token统计数据
                    data = self._validate_token_statistics(data)
                
                return data
        except (json.JSONDecodeError, Exception) as e:
            print(f"⌘ 加载对话失败 {conversation_id}: {e}")
            return None
    
    def update_token_statistics(self, conversation_id: str, input_tokens: int, output_tokens: int) -> bool:
        """
        更新对话的Token统计
        
        Args:
            conversation_id: 对话ID
            input_tokens: 输入Token数量
            output_tokens: 输出Token数量
        
        Returns:
            bool: 更新是否成功
        """
        try:
            conversation_data = self.load_conversation(conversation_id)
            if not conversation_data:
                print(f"⚠️ 无法找到对话 {conversation_id}，跳过Token统计")
                return False
            
            # 确保Token统计结构存在
            if "token_statistics" not in conversation_data:
                conversation_data["token_statistics"] = self._initialize_token_statistics()
            
            # 更新统计数据
            token_stats = conversation_data["token_statistics"]
            token_stats["total_input_tokens"] = token_stats.get("total_input_tokens", 0) + input_tokens
            token_stats["total_output_tokens"] = token_stats.get("total_output_tokens", 0) + output_tokens
            token_stats["updated_at"] = datetime.now().isoformat()
            
            # 保存更新
            self._save_conversation_file(conversation_id, conversation_data)
            
            print(f"📊 Token统计已更新: +{input_tokens}输入, +{output_tokens}输出 "
                  f"(总计: {token_stats['total_input_tokens']}输入, {token_stats['total_output_tokens']}输出)")
            
            return True
        except Exception as e:
            print(f"⌘ 更新Token统计失败 {conversation_id}: {e}")
            return False
    
    def get_token_statistics(self, conversation_id: str) -> Optional[Dict]:
        """
        获取对话的Token统计
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            Dict: Token统计数据
        """
        try:
            conversation_data = self.load_conversation(conversation_id)
            if not conversation_data:
                return None
            
            token_stats = conversation_data.get("token_statistics", {})
            
            # 确保基本字段存在
            result = {
                "total_input_tokens": token_stats.get("total_input_tokens", 0),
                "total_output_tokens": token_stats.get("total_output_tokens", 0),
                "total_tokens": token_stats.get("total_input_tokens", 0) + token_stats.get("total_output_tokens", 0),
                "updated_at": token_stats.get("updated_at"),
                "conversation_id": conversation_id
            }
            
            return result
        except Exception as e:
            print(f"⌘ 获取Token统计失败 {conversation_id}: {e}")
            return None
    
    def get_conversation_list(self, limit: int = 50, offset: int = 0) -> Dict:
        """
        获取对话列表
        
        Args:
            limit: 限制数量
            offset: 偏移量
        
        Returns:
            Dict: 包含对话列表和统计信息
        """
        try:
            index = self._load_index()
            
            # 按更新时间倒序排列
            sorted_conversations = sorted(
                index.items(),
                key=lambda x: x[1].get("updated_at", ""),
                reverse=True
            )
            
            # 分页
            total = len(sorted_conversations)
            conversations = sorted_conversations[offset:offset+limit]
            
            # 格式化结果
            result = []
            for conv_id, metadata in conversations:
                result.append({
                    "id": conv_id,
                    "title": metadata.get("title", "未命名对话"),
                    "created_at": metadata.get("created_at"),
                    "updated_at": metadata.get("updated_at"),
                    "project_path": metadata.get("project_path"),
                    "thinking_mode": metadata.get("thinking_mode", False),
                    "total_messages": metadata.get("total_messages", 0),
                    "total_tools": metadata.get("total_tools", 0),
                    "status": metadata.get("status", "active")
                })
            
            return {
                "conversations": result,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total
            }
        except Exception as e:
            print(f"⌘ 获取对话列表失败: {e}")
            return {
                "conversations": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False
            }
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除对话
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            bool: 删除是否成功
        """
        try:
            # 删除对话文件
            file_path = self._get_conversation_file_path(conversation_id)
            if file_path.exists():
                file_path.unlink()
            
            # 从索引中删除
            index = self._load_index()
            if conversation_id in index:
                del index[conversation_id]
                self._save_index(index)
            
            # 如果删除的是当前对话，清除当前对话ID
            if self.current_conversation_id == conversation_id:
                self.current_conversation_id = None
            
            print(f"🗑️ 已删除对话: {conversation_id}")
            return True
        except Exception as e:
            print(f"⌘ 删除对话失败 {conversation_id}: {e}")
            return False
    
    def archive_conversation(self, conversation_id: str) -> bool:
        """
        归档对话（标记为已归档，不删除）
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            bool: 归档是否成功
        """
        try:
            # 更新对话状态
            conversation_data = self.load_conversation(conversation_id)
            if not conversation_data:
                return False
            
            conversation_data["metadata"]["status"] = "archived"
            conversation_data["updated_at"] = datetime.now().isoformat()
            
            # 保存更新
            self._save_conversation_file(conversation_id, conversation_data)
            self._update_index(conversation_id, conversation_data)
            
            print(f"📦 已归档对话: {conversation_id}")
            return True
        except Exception as e:
            print(f"⌘ 归档对话失败 {conversation_id}: {e}")
            return False
    
    def search_conversations(self, query: str, limit: int = 20) -> List[Dict]:
        """
        搜索对话
        
        Args:
            query: 搜索关键词
            limit: 限制数量
        
        Returns:
            List[Dict]: 匹配的对话列表
        """
        try:
            index = self._load_index()
            results = []
            
            query_lower = query.lower()
            
            for conv_id, metadata in index.items():
                # 搜索标题
                title = metadata.get("title", "").lower()
                if query_lower in title:
                    score = 100  # 标题匹配权重最高
                    results.append((score, {
                        "id": conv_id,
                        "title": metadata.get("title"),
                        "created_at": metadata.get("created_at"),
                        "updated_at": metadata.get("updated_at"),
                        "project_path": metadata.get("project_path"),
                        "match_type": "title"
                    }))
                    continue
                
                # 搜索项目路径
                project_path = metadata.get("project_path", "").lower()
                if query_lower in project_path:
                    results.append((50, {
                        "id": conv_id,
                        "title": metadata.get("title"),
                        "created_at": metadata.get("created_at"),
                        "updated_at": metadata.get("updated_at"),
                        "project_path": metadata.get("project_path"),
                        "match_type": "project_path"
                    }))
            
            # 按分数排序
            results.sort(key=lambda x: x[0], reverse=True)
            
            # 返回前N个结果
            return [result[1] for result in results[:limit]]
        except Exception as e:
            print(f"⌘ 搜索对话失败: {e}")
            return []
    
    def cleanup_old_conversations(self, days: int = 30) -> int:
        """
        清理旧对话（可选功能）
        
        Args:
            days: 保留天数
        
        Returns:
            int: 清理的对话数量
        """
        try:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat()
            
            index = self._load_index()
            to_delete = []
            
            for conv_id, metadata in index.items():
                updated_at = metadata.get("updated_at", "")
                if updated_at < cutoff_iso and metadata.get("status") != "archived":
                    to_delete.append(conv_id)
            
            deleted_count = 0
            for conv_id in to_delete:
                if self.delete_conversation(conv_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"🧹 清理了 {deleted_count} 个旧对话")
            
            return deleted_count
        except Exception as e:
            print(f"⌘ 清理旧对话失败: {e}")
            return 0
    
    def get_statistics(self) -> Dict:
        """
        获取对话统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            index = self._load_index()
            
            total_conversations = len(index)
            total_messages = sum(meta.get("total_messages", 0) for meta in index.values())
            total_tools = sum(meta.get("total_tools", 0) for meta in index.values())
            
            # 按状态分类
            status_count = {}
            for metadata in index.values():
                status = metadata.get("status", "active")
                status_count[status] = status_count.get(status, 0) + 1
            
            # 按思考模式分类
            thinking_mode_count = {
                "thinking": sum(1 for meta in index.values() if meta.get("thinking_mode")),
                "fast": sum(1 for meta in index.values() if not meta.get("thinking_mode"))
            }
            
            # 新增：Token统计汇总
            total_input_tokens = 0
            total_output_tokens = 0
            token_stats_count = 0
            
            for conv_id in index.keys():
                token_stats = self.get_token_statistics(conv_id)
                if token_stats:
                    total_input_tokens += token_stats.get("total_input_tokens", 0)
                    total_output_tokens += token_stats.get("total_output_tokens", 0)
                    token_stats_count += 1
            
            return {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "total_tools": total_tools,
                "status_distribution": status_count,
                "thinking_mode_distribution": thinking_mode_count,
                "token_statistics": {
                    "total_input_tokens": total_input_tokens,
                    "total_output_tokens": total_output_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens,
                    "conversations_with_stats": token_stats_count
                }
            }
        except Exception as e:
            print(f"⌘ 获取统计信息失败: {e}")
            return {}
    
    def get_current_conversation_id(self) -> Optional[str]:
        """获取当前对话ID"""
        return self.current_conversation_id
    
    def set_current_conversation_id(self, conversation_id: str):
        """设置当前对话ID"""
        self.current_conversation_id = conversation_id
    
    def calculate_conversation_tokens(self, conversation_id: str, context_manager=None, focused_files=None, terminal_content="") -> dict:
        """计算对话的真实API token消耗"""
        try:
            if not context_manager:
                return {"total_tokens": 0}
            
            conversation_data = self.load_conversation(conversation_id)
            if not conversation_data:
                return {"total_tokens": 0}
            
            # 构建context和messages...
            context = context_manager.build_main_context(memory_content="")
            messages = context_manager.build_messages(context, "")
            
            # 计算消息token
            message_tokens = context_manager.calculate_input_tokens(messages, [])
            
            # 硬编码添加工具定义token
            tools_tokens = 2400  # 基于你的日志
            
            total_tokens = message_tokens + tools_tokens
            
            return {"total_tokens": total_tokens}
            
        except Exception as e:
            print(f"计算token失败: {e}")
            return {"total_tokens": 0}
    def _get_tools_definition(self, context_manager):
        """获取工具定义"""
        try:
            # 需要找到工具定义的来源，通常在 main_terminal 中
            # 你需要找到 main_terminal 的引用或者 define_tools 方法
            
            # 方法1: 如果 context_manager 有 main_terminal 引用
            if hasattr(context_manager, 'main_terminal') and context_manager.main_terminal:
                return context_manager.main_terminal.define_tools()
            
            # 方法2: 如果有其他方式获取工具定义
            # 你需要去找一下在哪里调用了 calculate_input_tokens，看看 tools 参数是怎么传的
            
            return []
        except Exception as e:
            print(f"获取工具定义失败: {e}")
            return []