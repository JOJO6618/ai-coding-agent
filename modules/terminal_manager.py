# modules/terminal_manager.py - 终端会话管理器

import json
from typing import Dict, List, Optional, Callable
from pathlib import Path
from datetime import datetime
from config import (
    OUTPUT_FORMATS,
    MAX_TERMINALS,           # 添加这个
    TERMINAL_BUFFER_SIZE,    # 添加这个
    TERMINAL_DISPLAY_SIZE    # 添加这个
)

from modules.persistent_terminal import PersistentTerminal
from utils.terminal_factory import TerminalFactory

class TerminalManager:
    """管理多个终端会话"""
    
    def __init__(
        self,
        project_path: str,
        max_terminals: int = None,
        terminal_buffer_size: int = None,
        terminal_display_size: int = None,
        broadcast_callback: Callable = None
    ):
        self.max_terminals = max_terminals or MAX_TERMINALS
        self.terminal_buffer_size = terminal_buffer_size or TERMINAL_BUFFER_SIZE
        self.terminal_display_size = terminal_display_size or TERMINAL_DISPLAY_SIZE
        """
        初始化终端管理器
        
        Args:
            project_path: 项目路径
            max_terminals: 最大终端数量
            terminal_buffer_size: 每个终端的缓冲区大小
            terminal_display_size: 显示大小限制
            broadcast_callback: WebSocket广播回调
        """
        self.project_path = Path(project_path)
        self.max_terminals = max_terminals
        self.terminal_buffer_size = terminal_buffer_size
        self.terminal_display_size = terminal_display_size
        self.broadcast = broadcast_callback
        
        # 终端会话字典
        self.terminals: Dict[str, PersistentTerminal] = {}
        
        # 当前活动终端
        self.active_terminal: Optional[str] = None
        
        # 终端工厂（跨平台支持）
        self.factory = TerminalFactory()
    
    def open_terminal(
        self,
        session_name: str,
        working_dir: str = None,
        make_active: bool = True
    ) -> Dict:
        """
        打开新终端会话
        
        Args:
            session_name: 会话名称
            working_dir: 工作目录（相对于项目路径）
            make_active: 是否设为活动终端
            
        Returns:
            操作结果
        """
        # 检查是否已存在
        if session_name in self.terminals:
            return {
                "success": False,
                "error": f"终端会话 '{session_name}' 已存在",
                "existing_sessions": list(self.terminals.keys())
            }
        
        # 检查数量限制
        if len(self.terminals) >= self.max_terminals:
            return {
                "success": False,
                "error": f"已达到最大终端数量限制 ({self.max_terminals})",
                "existing_sessions": list(self.terminals.keys()),
                "suggestion": "请先关闭一个终端会话"
            }
        
        # 确定工作目录
        if working_dir:
            work_path = self.project_path / working_dir
            if not work_path.exists():
                work_path.mkdir(parents=True, exist_ok=True)
        else:
            work_path = self.project_path
        
        # 获取合适的shell命令
        shell_command = self.factory.get_shell_command()
        
        # 创建终端实例
        terminal = PersistentTerminal(
            session_name=session_name,
            working_dir=str(work_path),
            shell_command=shell_command,
            broadcast_callback=self.broadcast,
            max_buffer_size=self.terminal_buffer_size,
            display_size=self.terminal_display_size
        )
        
        # 启动终端
        if not terminal.start():
            return {
                "success": False,
                "error": "终端启动失败",
                "session": session_name
            }
        
        # 保存终端实例
        self.terminals[session_name] = terminal
        
        # 设为活动终端
        if make_active:
            self.active_terminal = session_name
        
        print(f"{OUTPUT_FORMATS['success']} 终端会话已打开: {session_name}")
        
        # 广播终端列表更新
        if self.broadcast:
            self.broadcast('terminal_list_update', {
                'terminals': self.get_terminal_list(),
                'active': self.active_terminal
            })
        
        return {
            "success": True,
            "session": session_name,
            "working_dir": str(work_path),
            "shell": shell_command,
            "is_active": make_active,
            "total_sessions": len(self.terminals)
        }
    
    def close_terminal(self, session_name: str) -> Dict:
        """
        关闭终端会话
        
        Args:
            session_name: 会话名称
            
        Returns:
            操作结果
        """
        if session_name not in self.terminals:
            return {
                "success": False,
                "error": f"终端会话 '{session_name}' 不存在",
                "existing_sessions": list(self.terminals.keys())
            }
        
        # 获取终端实例
        terminal = self.terminals[session_name]
        
        # 关闭终端
        terminal.close()
        
        # 从字典中移除
        del self.terminals[session_name]
        
        # 如果是活动终端，切换到另一个
        if self.active_terminal == session_name:
            if self.terminals:
                self.active_terminal = list(self.terminals.keys())[0]
            else:
                self.active_terminal = None
        
        print(f"{OUTPUT_FORMATS['info']} 终端会话已关闭: {session_name}")
        
        # 广播终端列表更新
        if self.broadcast:
            self.broadcast('terminal_list_update', {
                'terminals': self.get_terminal_list(),
                'active': self.active_terminal
            })
        
        return {
            "success": True,
            "session": session_name,
            "remaining_sessions": list(self.terminals.keys()),
            "new_active": self.active_terminal
        }
    
    def switch_terminal(self, session_name: str) -> Dict:
        """
        切换活动终端
        
        Args:
            session_name: 会话名称
            
        Returns:
            操作结果
        """
        if session_name not in self.terminals:
            return {
                "success": False,
                "error": f"终端会话 '{session_name}' 不存在",
                "existing_sessions": list(self.terminals.keys())
            }
        
        previous_active = self.active_terminal
        self.active_terminal = session_name
        
        print(f"{OUTPUT_FORMATS['info']} 切换到终端: {session_name}")
        
        # 广播切换事件
        if self.broadcast:
            self.broadcast('terminal_switched', {
                'previous': previous_active,
                'current': session_name
            })
        
        return {
            "success": True,
            "previous": previous_active,
            "current": session_name,
            "status": self.terminals[session_name].get_status()
        }
    
    def list_terminals(self) -> Dict:
        """
        列出所有终端会话
        
        Returns:
            终端列表
        """
        sessions = []
        for name, terminal in self.terminals.items():
            status = terminal.get_status()
            status['is_active'] = (name == self.active_terminal)
            sessions.append(status)
        
        return {
            "success": True,
            "sessions": sessions,
            "active": self.active_terminal,
            "total": len(self.terminals),
            "max_allowed": self.max_terminals
        }
    
    def send_to_terminal(
        self,
        command: str,
        session_name: str = None,
        wait_for_output: bool = True
    ) -> Dict:
        """
        向终端发送命令
        
        Args:
            command: 要执行的命令
            session_name: 目标终端（None则使用活动终端）
            wait_for_output: 是否等待输出
            
        Returns:
            执行结果
        """
        # 确定目标终端
        target_session = session_name or self.active_terminal
        
        if not target_session:
            return {
                "success": False,
                "error": "没有活动终端会话",
                "suggestion": "请先使用 terminal_session 打开一个终端"
            }
        
        if target_session not in self.terminals:
            return {
                "success": False,
                "error": f"终端会话 '{target_session}' 不存在",
                "existing_sessions": list(self.terminals.keys())
            }
        
        # 发送命令
        terminal = self.terminals[target_session]
        result = terminal.send_command(command, wait_for_output)
        
        return result
    
    def get_terminal_output(
        self,
        session_name: str = None,
        last_n_lines: int = 50
    ) -> Dict:
        """
        获取终端输出
        
        Args:
            session_name: 终端名称（None则使用活动终端）
            last_n_lines: 获取最后N行
            
        Returns:
            输出内容
        """
        target_session = session_name or self.active_terminal
        
        if not target_session:
            return {
                "success": False,
                "error": "没有活动终端会话"
            }
        
        if target_session not in self.terminals:
            return {
                "success": False,
                "error": f"终端会话 '{target_session}' 不存在"
            }
        
        terminal = self.terminals[target_session]
        output = terminal.get_output(last_n_lines)
        
        return {
            "success": True,
            "session": target_session,
            "output": output,
            "is_interactive": terminal.is_interactive,
            "last_command": terminal.last_command
        }
    
    def get_active_terminal_content(self) -> Optional[str]:
        """
        获取活动终端内容（用于注入到上下文）
        
        Returns:
            格式化的终端内容，如果没有活动终端则返回None
        """
        if not self.active_terminal or self.active_terminal not in self.terminals:
            return None
        
        terminal = self.terminals[self.active_terminal]
        status = terminal.get_status()
        output = terminal.get_display_output()
        
        # 获取最近的命令历史
        recent_commands = terminal.command_history[-5:] if terminal.command_history else []
        command_history = "\n".join([f"> {cmd['command']}" for cmd in recent_commands])
        
        # 格式化内容
        content = f"""=== 📺 活动终端: {self.active_terminal} ===
工作目录: {status['working_dir']}
状态: {'运行中' if status['is_running'] else '已停止'}
Shell: {status['shell']}
运行时间: {status['uptime_seconds']:.1f}秒
缓冲区大小: {status['buffer_size']} 字节
"""
        
        if status['truncated_lines'] > 0:
            content += f"已截断: 前{status['truncated_lines']}行\n"
        
        if recent_commands:
            content += f"\n--- 最近命令历史 ---\n{command_history}\n"
        
        if status['is_interactive']:
            content += f"\n⚠️ 终端正在等待输入（最后命令: {status['last_command']}）\n"
        
        content += f"\n--- 终端输出 (最后50行) ---\n{output}\n"
        content += "=== 终端结束 ==="
        
        return content
    
    def get_terminal_list(self) -> List[Dict]:
        """获取终端列表（简化版）"""
        return [
            {
                "name": name,
                "is_active": name == self.active_terminal,
                "is_running": terminal.is_running,
                "working_dir": str(terminal.working_dir)
            }
            for name, terminal in self.terminals.items()
        ]
    
    def close_all(self):
        """关闭所有终端会话"""
        print(f"{OUTPUT_FORMATS['info']} 关闭所有终端会话...")
        
        for session_name in list(self.terminals.keys()):
            self.close_terminal(session_name)
        
        self.active_terminal = None
        print(f"{OUTPUT_FORMATS['success']} 所有终端会话已关闭")
    
    def __del__(self):
        """析构函数，确保所有终端被关闭"""
        self.close_all()