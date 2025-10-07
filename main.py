#!/usr/bin/env python3
# main.py - 主程序入口（修复路径引号和中文支持问题）

import asyncio
import os
import sys
from pathlib import Path
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import *
from core.main_terminal import MainTerminal
from utils.logger import setup_logger

logger = setup_logger(__name__)

class AgentSystem:
    def __init__(self):
        self.project_path = None
        self.thinking_mode = False  # False=快速模式, True=思考模式
        self.web_mode = False  # Web模式标志
        self.main_terminal = None
        
    async def initialize(self):
        """初始化系统"""
        print("\n" + "="*50)
        print("🤖 AI Agent 系统启动")
        print("="*50)
        
        # 1. 获取项目路径
        await self.setup_project_path()
        
        # 2. 选择运行模式（CLI或Web）
        await self.setup_run_mode()
        
        if not self.web_mode:
            # CLI模式：继续原有流程
            # 3. 选择思考模式
            await self.setup_thinking_mode()
            
            # 4. 初始化系统
            await self.init_system()
            
            # 5. 创建主终端
            self.main_terminal = MainTerminal(
                project_path=self.project_path,
                thinking_mode=self.thinking_mode
            )
            
            print(f"\n{OUTPUT_FORMATS['success']} 系统初始化完成")
            print(f"{OUTPUT_FORMATS['info']} 项目路径: {self.project_path}")
            print(f"{OUTPUT_FORMATS['info']} 运行模式: {'思考模式（智能）' if self.thinking_mode else '快速模式（无思考）'}")
            
            print("\n" + "="*50)
            print("输入 'exit' 退出，'help' 查看帮助，'/clear' 清除对话")
            print("="*50 + "\n")
        else:
            # Web模式：启动Web服务器
            # 3. 选择思考模式
            await self.setup_thinking_mode()
            
            # 4. 初始化系统
            await self.init_system()
            
            # 5. 启动Web服务器
            await self.start_web_server()
    
    def clean_path_input(self, path_str: str) -> str:
        """清理路径输入，去除引号和多余空格"""
        if not path_str:
            return path_str
            
        # 保存原始输入用于调试
        original = path_str
        
        # 去除首尾空格
        path_str = path_str.strip()
        
        # 去除各种引号（包括中文引号）
        quote_pairs = [
            ('"', '"'),   # 英文双引号
            ("'", "'"),   # 英文单引号
            ('"', '"'),   # 中文双引号
            (''', '''),   # 中文单引号
            ('`', '`'),   # 反引号
            ('「', '」'), # 日文引号
            ('『', '』'), # 日文引号
        ]
        
        for start_quote, end_quote in quote_pairs:
            if path_str.startswith(start_quote) and path_str.endswith(end_quote):
                path_str = path_str[len(start_quote):-len(end_quote)]
                break
        
        # 处理只有一边引号的情况
        single_quotes = ['"', "'", '"', '"', ''', ''', '`', '「', '」', '『', '』']
        for quote in single_quotes:
            if path_str.startswith(quote):
                path_str = path_str[len(quote):]
            if path_str.endswith(quote):
                path_str = path_str[:-len(quote)]
        
        # 再次去除空格
        path_str = path_str.strip()
        
        # 调试输出
        if path_str != original.strip():
            print(f"{OUTPUT_FORMATS['info']} 路径已清理: {original.strip()} -> {path_str}")
        
        return path_str
    
    async def setup_project_path(self):
        """设置项目路径"""
        while True:
            # 使用更安全的输入方式
            print("\n📂 请输入项目文件夹路径")
            print("   提示: 可以直接粘贴路径，无需加引号")
            print("   示例: C:\\Users\\username\\Desktop\\project")
            print("   或者: /home/username/project")
            path_input = input("   路径 (直接回车使用默认 ./project): ")
            
            # 处理原始输入（不使用.strip()以保留用户输入的准确性）
            if not path_input or path_input.isspace():
                path_input = DEFAULT_PROJECT_PATH
                print(f"{OUTPUT_FORMATS['info']} 使用默认路径: {path_input}")
            else:
                # 清理输入的路径（去除引号）
                path_input = self.clean_path_input(path_input)
            
            # 展开用户路径（处理 ~ 等）
            try:
                path_input = os.path.expanduser(path_input)
            except Exception as e:
                print(f"{OUTPUT_FORMATS['error']} 路径展开失败: {e}")
                continue
            
            # 尝试解析路径
            try:
                # 对于Windows路径，确保正确处理
                if sys.platform == "win32":
                    # Windows路径特殊处理
                    # 规范化路径分隔符
                    path_input = path_input.replace('/', '\\')
                    # 处理UNC路径
                    if not path_input.startswith('\\\\'):
                        path_input = os.path.normpath(path_input)
                
                project_path = Path(path_input).resolve()
                
            except Exception as e:
                print(f"{OUTPUT_FORMATS['error']} 路径解析错误: {e}")
                print(f"{OUTPUT_FORMATS['info']} 原始输入: {repr(path_input)}")
                print(f"{OUTPUT_FORMATS['info']} 请检查路径格式是否正确")
                continue
            
            # 输出解析后的路径供用户确认
            print(f"{OUTPUT_FORMATS['info']} 解析后的路径: {project_path}")
            
            # 检查路径是否安全
            if self.is_unsafe_path(str(project_path)):
                print(f"{OUTPUT_FORMATS['error']} 不允许操作系统目录或根目录")
                continue
                
            # 创建目录（如果不存在）
            if not project_path.exists():
                # 询问是否创建
                create_confirm = input(f"   文件夹不存在，是否创建? (y/n): ").strip().lower()
                if create_confirm != 'y':
                    continue
                    
                try:
                    project_path.mkdir(parents=True, exist_ok=True)
                    print(f"{OUTPUT_FORMATS['success']} 创建项目文件夹: {project_path}")
                except Exception as e:
                    print(f"{OUTPUT_FORMATS['error']} 无法创建文件夹: {e}")
                    print(f"{OUTPUT_FORMATS['info']} 可能的原因:")
                    print("   1. 权限不足")
                    print("   2. 路径包含非法字符")
                    print("   3. 磁盘空间不足")
                    continue
            elif not project_path.is_dir():
                print(f"{OUTPUT_FORMATS['error']} 指定的路径是文件而不是文件夹: {project_path}")
                continue
            
            # 检查权限
            if not os.access(project_path, os.R_OK):
                print(f"{OUTPUT_FORMATS['error']} 没有读取权限: {project_path}")
                continue
            if not os.access(project_path, os.W_OK):
                print(f"{OUTPUT_FORMATS['warning']} 没有写入权限: {project_path}")
                read_only_confirm = input("   是否以只读模式继续? (y/n): ").strip().lower()
                if read_only_confirm != 'y':
                    continue
                    
            self.project_path = str(project_path)
            print(f"{OUTPUT_FORMATS['success']} 已选择项目路径: {self.project_path}")
            
            # 最终确认
            final_confirm = input("   确认使用此路径? (y/n，直接回车确认): ").strip().lower()
            if final_confirm == '' or final_confirm == 'y':
                break
    
    async def setup_run_mode(self):
        """选择运行模式"""
        print("\n🖥️  选择运行模式:")
        print("  1. 命令行模式 (CLI)")
        print("  2. Web界面模式 (推荐)")
        
        mode_input = input("\n请选择 (1/2，直接回车选择2): ").strip()
        
        self.web_mode = mode_input != "1"
    
    async def setup_thinking_mode(self):
        """选择思考模式"""
        print("\n🤔 选择运行模式:")
        print("  1. 快速模式（不思考）")
        print("  2. 思考模式（智能思考）")
        
        mode_input = input("\n请选择 (1/2，直接回车选择2): ").strip()
        
        if mode_input == "1":
            self.thinking_mode = False
        else:
            self.thinking_mode = True
    
    async def init_system(self):
        """初始化系统文件"""
        # 确保数据目录存在
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
        os.makedirs(f"{LOGS_DIR}/tasks", exist_ok=True)
        os.makedirs(f"{LOGS_DIR}/errors", exist_ok=True)
        
        # 初始化记忆文件
        if not os.path.exists(MAIN_MEMORY_FILE):
            with open(MAIN_MEMORY_FILE, 'w', encoding='utf-8') as f:
                f.write(f"# 主记忆文件\n\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if not os.path.exists(TASK_MEMORY_FILE):
            with open(TASK_MEMORY_FILE, 'w', encoding='utf-8') as f:
                f.write(f"# 任务记忆文件\n\n")
        
        # 初始化或修复对话历史
        conversation_file = Path(CONVERSATION_HISTORY_FILE)
        if conversation_file.exists():
            try:
                with open(conversation_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        json.loads(content)
                    else:
                        raise json.JSONDecodeError("Empty file", "", 0)
            except (json.JSONDecodeError, KeyError):
                print(f"{OUTPUT_FORMATS['warning']} 修复对话历史文件...")
                with open(conversation_file, 'w', encoding='utf-8') as f:
                    json.dump({"conversations": []}, f, ensure_ascii=False, indent=2)
        else:
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump({"conversations": []}, f, ensure_ascii=False, indent=2)
    
    async def start_web_server(self):
        """启动Web服务器"""
        try:
            # 检查是否安装了必要的包
            import flask
            import flask_socketio
            import flask_cors
        except ImportError:
            print(f"{OUTPUT_FORMATS['error']} 缺少Web依赖包，请安装：")
            print("pip install flask flask-socketio flask-cors")
            sys.exit(1)
        
        # 导入Web服务器
        from web_server import run_server
        
        print(f"\n{OUTPUT_FORMATS['success']} 正在启动Web服务器...")
        print(f"{OUTPUT_FORMATS['info']} 项目路径: {self.project_path}")
        
        # 询问端口
        port_input = input("\n请输入端口号 (直接回车使用默认8091): ").strip()
        port = int(port_input) if port_input.isdigit() else 8091
        
        # 运行服务器（这会阻塞）
        run_server(
            path=self.project_path,
            thinking_mode=self.thinking_mode,
            port=port
        )
    
    def is_unsafe_path(self, path: str) -> bool:
        """检查路径是否安全"""
        resolved_path = str(Path(path).resolve())
        
        # 检查是否是根路径
        for forbidden_root in FORBIDDEN_ROOT_PATHS:
            expanded = os.path.expanduser(forbidden_root)
            if resolved_path == expanded or resolved_path == forbidden_root:
                return True
        
        # 检查是否在系统目录
        for forbidden in FORBIDDEN_PATHS:
            if resolved_path.startswith(forbidden + os.sep) or resolved_path == forbidden:
                return True
        
        # 检查是否包含向上遍历
        if ".." in path:
            return True
        
        return False
    
    async def run(self):
        """运行主循环"""
        await self.initialize()
        
        if not self.web_mode:
            # CLI模式
            try:
                await self.main_terminal.run()
            except KeyboardInterrupt:
                print(f"\n{OUTPUT_FORMATS['info']} 收到中断信号")
            except Exception as e:
                logger.error(f"系统错误: {e}", exc_info=True)
                print(f"{OUTPUT_FORMATS['error']} 系统错误: {e}")
            finally:
                await self.cleanup()
        # Web模式在start_web_server中运行，不会到达这里
    
    async def cleanup(self):
        """清理资源"""
        print(f"\n{OUTPUT_FORMATS['info']} 正在保存状态...")
        
        if self.main_terminal:
            await self.main_terminal.save_state()
        
        print(f"{OUTPUT_FORMATS['success']} 系统已安全退出")
        print("\n👋 再见！\n")

async def main():
    """主函数"""
    system = AgentSystem()
    await system.run()

if __name__ == "__main__":
    try:
        # 设置控制台编码为UTF-8（Windows中文路径支持）


        if sys.platform == "win32":
            import locale
            # 尝试设置为UTF-8
            try:
                os.system("chcp 65001 > nul")  # 设置控制台代码页为UTF-8
            except:
                pass
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 再见！")
        sys.exit(0)
    except Exception as e:
        print(f"\n{OUTPUT_FORMATS['error']} 程序异常退出: {e}")
        sys.exit(1)