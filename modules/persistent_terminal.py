# modules/persistent_terminal.py - 持久化终端实例（修复版）

import asyncio
import subprocess
import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List
from datetime import datetime
import threading
import queue
try:
    from config import OUTPUT_FORMATS
except ImportError:
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from config import OUTPUT_FORMATS

class PersistentTerminal:
    """单个持久化终端实例"""
    
    def __init__(
        self,
        session_name: str,
        working_dir: str = None,
        shell_command: str = None,
        broadcast_callback: Callable = None,
        max_buffer_size: int = 20000,
        display_size: int = 5000
    ):
        """
        初始化持久化终端
        
        Args:
            session_name: 会话名称
            working_dir: 工作目录
            shell_command: shell命令（None则自动选择）
            broadcast_callback: 广播回调函数（用于WebSocket）
            max_buffer_size: 最大缓冲区大小
            display_size: 显示大小限制
        """
        self.session_name = session_name
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.shell_command = shell_command
        self.broadcast = broadcast_callback
        self.max_buffer_size = max_buffer_size
        self.display_size = display_size
        
        # 进程相关
        self.process = None
        self.is_running = False
        self.start_time = None
        
        # 输出缓冲
        self.output_buffer = []
        self.command_history = []
        self.total_output_size = 0
        self.truncated_lines = 0
        
        # 线程和队列
        self.output_queue = queue.Queue()
        self.reader_thread = None
        self.is_reading = False
        
        # 状态标志
        self.is_interactive = False  # 是否在等待输入
        self.last_command = ""
        self.last_activity = time.time()
        
        # 系统特定设置
        self.is_windows = sys.platform == "win32"
    
    def start(self) -> bool:
        """启动终端进程（统一处理编码）"""
        if self.is_running:
            return False
        
        try:
            # 确定使用的shell
            if self.is_windows:
                # Windows下使用CMD
                self.shell_command = self.shell_command or "cmd.exe"
            else:
                # Unix系统
                self.shell_command = self.shell_command or os.environ.get('SHELL', '/bin/bash')
            
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            if self.is_windows:
                # Windows特殊设置
                env['CHCP'] = '65001'  # UTF-8代码页
                
                # Windows统一不使用text模式，手动处理编码
                self.process = subprocess.Popen(
                    self.shell_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(self.working_dir),
                    shell=False,
                    bufsize=0,  # 无缓冲
                    env=env
                )
            else:
                # Unix系统
                env['TERM'] = 'xterm-256color'
                env['LANG'] = 'en_US.UTF-8'
                env['LC_ALL'] = 'en_US.UTF-8'
                
                # Unix也不使用text模式，统一处理
                self.process = subprocess.Popen(
                    self.shell_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(self.working_dir),
                    shell=False,
                    bufsize=0,
                    env=env
                )
            
            self.is_running = True
            self.start_time = datetime.now()
            
            # 启动输出读取线程
            self.is_reading = True
            self.reader_thread = threading.Thread(target=self._read_output)
            self.reader_thread.daemon = True
            self.reader_thread.start()
            
            # 如果是Windows，设置代码页
            if self.is_windows:
                time.sleep(0.5)  # 等待终端初始化
                self.send_command("chcp 65001", wait_for_output=False)
                time.sleep(0.5)
                # 清屏以去除代码页设置的输出
                self.send_command("cls", wait_for_output=False)
                time.sleep(0.3)
                self.output_buffer.clear()  # 清除初始化输出
                self.total_output_size = 0
            
            # 广播终端启动事件
            if self.broadcast:
                self.broadcast('terminal_started', {
                    'session': self.session_name,
                    'working_dir': str(self.working_dir),
                    'shell': self.shell_command,
                    'time': self.start_time.isoformat()
                })
            
            print(f"{OUTPUT_FORMATS['success']} 终端会话启动: {self.session_name}")
            return True
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 终端启动失败: {e}")
            self.is_running = False
            return False
    
    def _read_output(self):
        """后台线程：持续读取输出（修复版，正确处理编码）"""
        while self.is_reading and self.process:
            try:
                # 始终读取字节（因为我们没有使用text=True）
                line_bytes = self.process.stdout.readline()
                
                if line_bytes:
                    # 解码字节到字符串
                    line = self._decode_output(line_bytes)
                    
                    # 处理输出
                    self.output_queue.put(line)
                    self._process_output(line)
                    
                elif self.process.poll() is not None:
                    # 进程已结束
                    self.is_running = False
                    break
                else:
                    # 没有输出，短暂休眠
                    time.sleep(0.01)
                    
            except Exception as e:
                # 不要因为单个错误而停止
                print(f"[Terminal] 读取输出警告: {e}")
                time.sleep(0.01)
                continue
    
    def _decode_output(self, data):
        """安全地解码输出"""
        # 如果已经是字符串，直接返回
        if isinstance(data, str):
            return data
        
        # 如果是字节，尝试解码
        if isinstance(data, bytes):
            # Windows系统尝试的编码顺序
            if self.is_windows:
                encodings = ['utf-8', 'gbk', 'gb2312', 'cp936', 'latin-1']
            else:
                encodings = ['utf-8', 'latin-1']
            
            for encoding in encodings:
                try:
                    return data.decode(encoding)
                except (UnicodeDecodeError, AttributeError):
                    continue
            
            # 如果所有编码都失败，使用替换模式
            return data.decode('utf-8', errors='replace')
        
        # 其他类型，转换为字符串
        return str(data)
    
    def _process_output(self, output: str):
        """处理输出行"""
        # 添加到缓冲区
        self.output_buffer.append(output)
        self.total_output_size += len(output)
        
        # 检查是否需要截断
        if self.total_output_size > self.max_buffer_size:
            self._truncate_buffer()
        
        # 更新活动时间
        self.last_activity = time.time()
        
        # 检测交互式提示
        self._detect_interactive_prompt(output)
        
        # 广播输出
        if self.broadcast:
            self.broadcast('terminal_output', {
                'session': self.session_name,
                'data': output,
                'timestamp': time.time()
            })
    
    def _truncate_buffer(self):
        """截断缓冲区以保持在限制内"""
        # 保留最后的N个字符
        while self.total_output_size > self.max_buffer_size and self.output_buffer:
            removed = self.output_buffer.pop(0)
            self.total_output_size -= len(removed)
            self.truncated_lines += 1
    
    def _detect_interactive_prompt(self, output: str):
        """检测是否在等待交互输入"""
        # 常见的交互提示模式
        interactive_patterns = [
            "? ",  # 问题提示
            ": ",  # 输入提示
            "> ",  # 命令提示
            "$ ",  # shell提示
            "# ",  # root提示
            ">>> ",  # Python提示
            "... ",  # Python续行
            "(y/n)",  # 确认提示
            "[Y/n]",  # 确认提示
            "Password:",  # 密码提示
            "password:",  # 密码提示
            "Enter",  # 输入提示
            "选择",  # 中文选择
            "请输入",  # 中文输入
        ]
        
        output_lower = output.lower().strip()
        for pattern in interactive_patterns:
            if pattern.lower() in output_lower:
                self.is_interactive = True
                return
        
        # 如果输出以常见提示符结尾且没有换行，也认为是交互式
        if output and not output.endswith('\n'):
            last_chars = output.strip()[-3:]
            if last_chars in ['> ', '$ ', '# ', ': ']:
                self.is_interactive = True
    
    def send_command(self, command: str, wait_for_output: bool = True) -> Dict:
        """发送命令到终端（统一编码处理）"""
        if not self.is_running or not self.process:
            return {
                "success": False,
                "error": "终端未运行",
                "session": self.session_name
            }
        
        try:
            # 记录命令
            self.command_history.append({
                "command": command,
                "timestamp": datetime.now().isoformat()
            })
            self.last_command = command
            self.is_interactive = False
            
            # 广播输入事件
            if self.broadcast:
                self.broadcast('terminal_input', {
                    'session': self.session_name,
                    'data': command + '\n',
                    'timestamp': time.time()
                })
            
            # 确保命令有换行符
            if not command.endswith('\n'):
                command += '\n'
            
            # 发送命令（统一使用UTF-8编码）
            try:
                # 首先尝试UTF-8
                command_bytes = command.encode('utf-8')
            except UnicodeEncodeError:
                # 如果UTF-8失败，Windows系统尝试GBK
                if self.is_windows:
                    command_bytes = command.encode('gbk', errors='replace')
                else:
                    command_bytes = command.encode('utf-8', errors='replace')
            
            self.process.stdin.write(command_bytes)
            self.process.stdin.flush()
            
            # 如果需要等待输出
            if wait_for_output:
                output = self._wait_for_output(timeout=5)
                return {
                    "success": True,
                    "session": self.session_name,
                    "command": command.strip(),
                    "output": output
                }
            else:
                return {
                    "success": True,
                    "session": self.session_name,
                    "command": command.strip(),
                    "output": "命令已发送"
                }
                
        except Exception as e:
            error_msg = f"发送命令失败: {str(e)}"
            print(f"{OUTPUT_FORMATS['error']} {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "session": self.session_name
            }
    
    def _wait_for_output(self, timeout: float = 5) -> str:
        """等待并收集输出"""
        collected_output = []
        start_time = time.time()
        last_output_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 非阻塞获取
                output = self.output_queue.get_nowait()
                collected_output.append(output)
                last_output_time = time.time()
            except queue.Empty:
                # 如果超过0.5秒没有新输出，认为命令执行完成
                if time.time() - last_output_time > 0.5 and collected_output:
                    break
                time.sleep(0.01)
        
        return ''.join(collected_output)
    
    def get_output(self, last_n_lines: int = 50) -> str:
        """
        获取终端输出
        
        Args:
            last_n_lines: 获取最后N行
            
        Returns:
            输出内容
        """
        if last_n_lines <= 0:
            return ''.join(self.output_buffer)
        
        # 获取最后N行
        lines = []
        for line in reversed(self.output_buffer):
            lines.insert(0, line)
            if len(lines) >= last_n_lines:
                break
        
        return ''.join(lines)
    
    def get_display_output(self) -> str:
        """获取用于显示的输出（截断到display_size）"""
        output = self.get_output()
        if len(output) > self.display_size:
            # 保留最后的display_size字符
            output = output[-self.display_size:]
            output = f"[输出已截断，显示最后{self.display_size}字符]\n{output}"
        return output
    
    def get_status(self) -> Dict:
        """获取终端状态"""
        return {
            "session_name": self.session_name,
            "is_running": self.is_running,
            "working_dir": str(self.working_dir),
            "shell": self.shell_command,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "is_interactive": self.is_interactive,
            "last_command": self.last_command,
            "command_count": len(self.command_history),
            "buffer_size": self.total_output_size,
            "truncated_lines": self.truncated_lines,
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        }
    
    def close(self) -> bool:
        """关闭终端"""
        if not self.is_running:
            return False
        
        try:
            # 停止读取线程
            self.is_reading = False
            
            # 发送退出命令
            if self.process and self.process.poll() is None:
                exit_cmd = "exit\n"
                try:
                    self.process.stdin.write(exit_cmd.encode('utf-8'))
                    self.process.stdin.flush()
                except:
                    pass
                
                # 等待进程结束
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    self.process.terminate()
                    time.sleep(0.5)
                    if self.process.poll() is None:
                        self.process.kill()
            
            self.is_running = False
            
            # 等待读取线程结束
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=1)
            
            # 广播终端关闭事件
            if self.broadcast:
                self.broadcast('terminal_closed', {
                    'session': self.session_name,
                    'time': datetime.now().isoformat()
                })
            
            print(f"{OUTPUT_FORMATS['info']} 终端会话关闭: {self.session_name}")
            return True
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 关闭终端失败: {e}")
            return False
    
    def __del__(self):
        """析构函数，确保进程被关闭"""
        if hasattr(self, 'is_running') and self.is_running:
            self.close()
