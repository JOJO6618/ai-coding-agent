# modules/terminal_ops.py - 终端操作模块（修复Python命令检测）

import os
import sys
import asyncio
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple
from config import (
    CODE_EXECUTION_TIMEOUT,
    TERMINAL_COMMAND_TIMEOUT,
    FORBIDDEN_COMMANDS,
    OUTPUT_FORMATS
)

class TerminalOperator:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.process = None
        # 自动检测Python命令
        self.python_cmd = self._detect_python_command()
        print(f"{OUTPUT_FORMATS['info']} 检测到Python命令: {self.python_cmd}")
    
    def _detect_python_command(self) -> str:
        """
        自动检测可用的Python命令
        
        Returns:
            可用的Python命令（python、python3、py）
        """
        # 按优先级尝试不同的Python命令
        commands_to_try = []
        
        if sys.platform == "win32":
            # Windows优先顺序
            commands_to_try = ["python", "py", "python3"]
        else:
            # Unix-like系统优先顺序
            commands_to_try = ["python3", "python"]
        
        # 检测哪个命令可用
        for cmd in commands_to_try:
            if shutil.which(cmd):
                try:
                    # 验证是否真的可以运行
                    result = subprocess.run(
                        [cmd, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        # 检查版本是否为Python 3
                        output = result.stdout + result.stderr
                        if "Python 3" in output or "Python 2" not in output:
                            return cmd
                except:
                    continue
        
        # 如果都没找到，根据平台返回默认值
        return "python" if sys.platform == "win32" else "python3"
        
    def _validate_command(self, command: str) -> Tuple[bool, str]:
        """验证命令安全性"""
        # 检查禁止的命令
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden in command.lower():
                return False, f"禁止执行的命令: {forbidden}"
        
        # 检查危险的命令模式
        dangerous_patterns = [
            "sudo",
            "chmod 777",
            "rm -rf",
            "> /dev/",
            "fork bomb"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in command.lower():
                return False, f"检测到危险命令模式: {pattern}"
        
        return True, ""
    
    async def run_command(
        self,
        command: str,
        working_dir: str = None,
        timeout: int = None
    ) -> Dict:
        """
        执行终端命令
        
        Args:
            command: 要执行的命令
            working_dir: 工作目录
            timeout: 超时时间（秒）
        
        Returns:
            执行结果字典
        """
        # 替换命令中的python3为实际可用的命令
        if "python3" in command and self.python_cmd != "python3":
            command = command.replace("python3", self.python_cmd)
        elif "python" in command and "python3" not in command and self.python_cmd == "python3":
            # 如果命令中有python（但不是python3），而系统使用python3
            command = command.replace("python", self.python_cmd)
        
        # 验证命令
        valid, error = self._validate_command(command)
        if not valid:
            return {
                "success": False,
                "error": error,
                "output": "",
                "return_code": -1
            }
        
        # 设置工作目录
        if working_dir:
            work_path = (self.project_path / working_dir).resolve()
            # 确保工作目录在项目内
            try:
                work_path.relative_to(self.project_path)
            except ValueError:
                return {
                    "success": False,
                    "error": "工作目录必须在项目文件夹内",
                    "output": "",
                    "return_code": -1
                }
        else:
            work_path = self.project_path
        
        timeout = timeout or TERMINAL_COMMAND_TIMEOUT
        
        print(f"{OUTPUT_FORMATS['terminal']} 执行命令: {command}")
        print(f"{OUTPUT_FORMATS['info']} 工作目录: {work_path}")
        
        try:
            # 创建进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_path),
                shell=True
            )
            
            # 等待执行完成
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"命令执行超时 ({timeout}秒)",
                    "output": "",
                    "return_code": -1
                }
            
            # 解码输出
            stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            output = stdout_text
            if stderr_text:
                output += f"\n[错误输出]\n{stderr_text}"
            
            success = process.returncode == 0
            
            if success:
                print(f"{OUTPUT_FORMATS['success']} 命令执行成功")
            else:
                print(f"{OUTPUT_FORMATS['error']} 命令执行失败 (返回码: {process.returncode})")
            
            return {
                "success": success,
                "output": output,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "return_code": process.returncode,
                "command": command
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"执行失败: {str(e)}",
                "output": "",
                "return_code": -1
            }
    
    async def run_python_code(
        self,
        code: str,
        timeout: int = None
    ) -> Dict:
        """
        执行Python代码
        
        Args:
            code: Python代码
            timeout: 超时时间（秒）
        
        Returns:
            执行结果字典
        """
        timeout = timeout or CODE_EXECUTION_TIMEOUT
        
        # 创建临时Python文件
        temp_file = self.project_path / ".temp_code.py"
        
        try:
            # 写入代码
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            print(f"{OUTPUT_FORMATS['code']} 执行Python代码")
            
            # 使用检测到的Python命令执行文件
            result = await self.run_command(
                f'{self.python_cmd} "{temp_file}"',
                timeout=timeout
            )
            
            # 添加代码到结果
            result["code"] = code
            
            return result
            
        finally:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
    
    async def run_python_file(
        self,
        file_path: str,
        args: str = "",
        timeout: int = None
    ) -> Dict:
        """
        执行Python文件
        
        Args:
            file_path: Python文件路径
            args: 命令行参数
            timeout: 超时时间（秒）
        
        Returns:
            执行结果字典
        """
        # 构建完整路径
        full_path = (self.project_path / file_path).resolve()
        
        # 验证文件存在
        if not full_path.exists():
            return {
                "success": False,
                "error": "文件不存在",
                "output": "",
                "return_code": -1
            }
        
        # 验证是Python文件
        if not full_path.suffix == '.py':
            return {
                "success": False,
                "error": "不是Python文件",
                "output": "",
                "return_code": -1
            }
        
        # 验证文件在项目内
        try:
            full_path.relative_to(self.project_path)
        except ValueError:
            return {
                "success": False,
                "error": "文件必须在项目文件夹内",
                "output": "",
                "return_code": -1
            }
        
        print(f"{OUTPUT_FORMATS['code']} 执行Python文件: {file_path}")
        
        # 使用检测到的Python命令构建命令
        command = f'{self.python_cmd} "{full_path}"'
        if args:
            command += f" {args}"
        
        # 执行命令
        return await self.run_command(command, timeout=timeout)
    
    async def install_package(self, package: str) -> Dict:
        """
        安装Python包
        
        Args:
            package: 包名
        
        Returns:
            安装结果
        """
        print(f"{OUTPUT_FORMATS['terminal']} 安装包: {package}")
        
        # 使用检测到的Python命令安装
        command = f'{self.python_cmd} -m pip install {package}'
        
        result = await self.run_command(command, timeout=120)
        
        if result["success"]:
            print(f"{OUTPUT_FORMATS['success']} 包安装成功: {package}")
        else:
            print(f"{OUTPUT_FORMATS['error']} 包安装失败: {package}")
        
        return result
    
    async def check_environment(self) -> Dict:
        """检查Python环境"""
        print(f"{OUTPUT_FORMATS['info']} 检查Python环境...")
        
        env_info = {
            "python_command": self.python_cmd,
            "python_version": "",
            "pip_version": "",
            "installed_packages": [],
            "working_directory": str(self.project_path)
        }
        
        # 获取Python版本
        version_result = await self.run_command(
            f'{self.python_cmd} --version',
            timeout=5
        )
        if version_result["success"]:
            env_info["python_version"] = version_result["output"].strip()
        
        # 获取pip版本
        pip_result = await self.run_command(
            f'{self.python_cmd} -m pip --version',
            timeout=5
        )
        if pip_result["success"]:
            env_info["pip_version"] = pip_result["output"].strip()
        
        # 获取已安装的包
        packages_result = await self.run_command(
            f'{self.python_cmd} -m pip list --format=json',
            timeout=10
        )
        if packages_result["success"]:
            try:
                import json
                packages = json.loads(packages_result["output"])
                env_info["installed_packages"] = [
                    f"{p['name']}=={p['version']}" for p in packages
                ]
            except:
                pass
        
        return {
            "success": True,
            "environment": env_info
        }
    
    def kill_process(self):
        """终止当前运行的进程"""
        if self.process and self.process.returncode is None:
            self.process.kill()
            print(f"{OUTPUT_FORMATS['warning']} 进程已终止")