# modules/file_manager.py - 文件管理模块（添加行编辑功能）

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
try:
    from config import MAX_FILE_SIZE, FORBIDDEN_PATHS, FORBIDDEN_ROOT_PATHS, OUTPUT_FORMATS
except ImportError:  # 兼容全局环境中存在同名包的情况
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from config import MAX_FILE_SIZE, FORBIDDEN_PATHS, FORBIDDEN_ROOT_PATHS, OUTPUT_FORMATS
# 临时禁用长度检查
DISABLE_LENGTH_CHECK = True
class FileManager:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        
    def _validate_path(self, path: str) -> Tuple[bool, str, Path]:
        """
        验证路径安全性
        
        Returns:
            (是否有效, 错误信息, 完整路径)
        """
        # 不允许绝对路径（除非是在项目内的绝对路径）
        if path.startswith('/') or path.startswith('\\') or (len(path) > 1 and path[1] == ':'):
            # 如果是绝对路径，检查是否指向项目内
            try:
                test_path = Path(path).resolve()
                test_path.relative_to(self.project_path)
                # 如果成功，说明绝对路径在项目内，转换为相对路径
                path = str(test_path.relative_to(self.project_path))
            except ValueError:
                return False, "路径必须在项目文件夹内", None
        
        # 检查是否包含向上遍历
        if ".." in path:
            return False, "不允许使用../向上遍历", None
        
        # 构建完整路径
        full_path = (self.project_path / path).resolve()
        
        # 检查是否在项目目录内
        try:
            full_path.relative_to(self.project_path)
        except ValueError:
            return False, "路径必须在项目文件夹内", None
        
        # 检查禁止的路径
        path_str = str(full_path)
        
        for forbidden_root in FORBIDDEN_ROOT_PATHS:
            if path_str == forbidden_root:
                return False, f"禁止访问根目录: {forbidden_root}", None
        
        for forbidden in FORBIDDEN_PATHS:
            if path_str.startswith(forbidden + os.sep) or path_str == forbidden:
                return False, f"禁止访问系统目录: {forbidden}", None
        
        return True, "", full_path
    
    def create_file(self, path: str, content: str = "", file_type: str = "txt") -> Dict:
        """创建文件"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        # 添加文件扩展名
        if not full_path.suffix:
            full_path = full_path.with_suffix(f".{file_type}")
        
        try:
            # 创建父目录
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 固定创建空文件，忽略传入内容
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write("")
            
            relative_path = str(full_path.relative_to(self.project_path))
            print(f"{OUTPUT_FORMATS['file']} 创建文件: {relative_path}")
            
            return {
                "success": True,
                "path": relative_path,
                "size": 0
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_file(self, path: str) -> Dict:
        """删除文件"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件不存在"}
        
        if not full_path.is_file():
            return {"success": False, "error": "不是文件"}
        
        try:
            relative_path = str(full_path.relative_to(self.project_path))
            full_path.unlink()
            print(f"{OUTPUT_FORMATS['file']} 删除文件: {relative_path}")
            
            # 删除文件备注（如果存在）
            # 这需要通过context_manager处理，但file_manager没有直接访问权限
            # 所以返回相对路径，让调用者处理备注删除
            
            return {
                "success": True,
                "path": relative_path,
                "action": "deleted"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def rename_file(self, old_path: str, new_path: str) -> Dict:
        """重命名文件"""
        valid_old, error_old, full_old_path = self._validate_path(old_path)
        if not valid_old:
            return {"success": False, "error": error_old}
        
        valid_new, error_new, full_new_path = self._validate_path(new_path)
        if not valid_new:
            return {"success": False, "error": error_new}
        
        if not full_old_path.exists():
            return {"success": False, "error": "原文件不存在"}
        
        if full_new_path.exists():
            return {"success": False, "error": "目标文件已存在"}
        
        try:
            full_old_path.rename(full_new_path)
            
            old_relative = str(full_old_path.relative_to(self.project_path))
            new_relative = str(full_new_path.relative_to(self.project_path))
            print(f"{OUTPUT_FORMATS['file']} 重命名: {old_relative} -> {new_relative}")
            
            return {
                "success": True,
                "old_path": old_relative,
                "new_path": new_relative,
                "action": "renamed"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_folder(self, path: str) -> Dict:
        """创建文件夹"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if full_path.exists():
            return {"success": False, "error": "文件夹已存在"}
        
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            relative_path = str(full_path.relative_to(self.project_path))
            print(f"{OUTPUT_FORMATS['file']} 创建文件夹: {relative_path}")
            
            return {"success": True, "path": relative_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_folder(self, path: str) -> Dict:
        """删除文件夹"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件夹不存在"}
        
        if not full_path.is_dir():
            return {"success": False, "error": "不是文件夹"}
        
        try:
            shutil.rmtree(full_path)
            relative_path = str(full_path.relative_to(self.project_path))
            print(f"{OUTPUT_FORMATS['file']} 删除文件夹: {relative_path}")
            
            return {"success": True, "path": relative_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def read_file(self, path: str) -> Dict:
        """读取文件内容"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件不存在"}
        
        if not full_path.is_file():
            return {"success": False, "error": "不是文件"}
        
        # 检查文件大小
        file_size = full_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            return {
                "success": False,
                "error": f"文件太大 ({file_size / 1024 / 1024:.2f}MB > {MAX_FILE_SIZE / 1024 / 1024}MB)"
            }
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            relative_path = str(full_path.relative_to(self.project_path))
            return {
                "success": True,
                "path": relative_path,
                "content": content,
                "size": file_size
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def write_file(self, path: str, content: str, mode: str = "w") -> Dict:
        """
        写入文件
        
        Args:
            path: 文件路径
            content: 内容
            mode: 写入模式 - "w"(覆盖), "a"(追加)
        """
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        # === 新增：内容预处理和验证 ===
        if content:
            # 长度检查
            if not DISABLE_LENGTH_CHECK and len(content) > 9999999999:  # 100KB限制
                return {
                    "success": False,
                    "error": f"内容过长({len(content)}字符)，超过100KB限制",
                    "suggestion": "请分块处理或使用部分修改方式"
                }
            
            # 检查潜在的JSON格式问题
            if content.count('"') % 2 != 0:
                print(f"{OUTPUT_FORMATS['warning']} 检测到奇数个引号，可能存在格式问题")
            
            # 检查大量转义字符
            if content.count('\\') > len(content) / 20:
                print(f"{OUTPUT_FORMATS['warning']} 检测到大量转义字符，建议检查内容格式")
        
        try:
            # 创建父目录
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            relative_path = str(full_path.relative_to(self.project_path))
            action = "覆盖" if mode == "w" else "追加"
            print(f"{OUTPUT_FORMATS['file']} {action}文件: {relative_path}")
            
            return {
                "success": True,
                "path": relative_path,
                "size": len(content),
                "mode": mode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        
    def append_file(self, path: str, content: str) -> Dict:
        """追加内容到文件"""
        return self.write_file(path, content, mode="a")
    
    def apply_modify_blocks(self, path: str, blocks: List[Dict]) -> Dict:
        """
        应用批量替换块
        
        Args:
            path: 目标文件路径
            blocks: [{"index": int, "old": str, "new": str}]
        """
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件不存在"}
        
        if not full_path.is_file():
            return {"success": False, "error": "不是文件"}
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}
        
        current_content = original_content
        results: List[Dict] = []
        completed_indices: List[int] = []
        failed_details: List[Dict] = []
        write_error = None
        
        for block in blocks:
            index = block.get("index")
            old_text = block.get("old", "")
            new_text = block.get("new", "")
            
            block_result = {
                "index": index,
                "status": "pending",
                "removed_lines": 0,
                "added_lines": 0,
                "reason": None
            }
            
            if old_text is None or new_text is None:
                block_result["status"] = "error"
                block_result["reason"] = "缺少 OLD 或 NEW 内容"
                failed_details.append({"index": index, "reason": "缺少 OLD/NEW 标记"})
                results.append(block_result)
                continue
            
            # 统一换行符，避免 CRLF 与 LF 不一致导致匹配失败
            old_text = old_text.replace('\r\n', '\n')
            new_text = new_text.replace('\r\n', '\n')
            
            if not old_text:
                block_result["status"] = "error"
                block_result["reason"] = "OLD 内容不能为空"
                failed_details.append({"index": index, "reason": "OLD 内容为空"})
                results.append(block_result)
                continue
            
            position = current_content.find(old_text)
            if position == -1:
                block_result["status"] = "not_found"
                block_result["reason"] = "未找到匹配的原文，请确认是否完全复制"
                failed_details.append({"index": index, "reason": "未找到匹配的原文"})
                results.append(block_result)
                continue
            
            current_content = (
                current_content[:position] +
                new_text +
                current_content[position + len(old_text):]
            )
            
            removed_lines = old_text.count('\n')
            added_lines = new_text.count('\n')
            if old_text and not old_text.endswith('\n'):
                removed_lines += 1
            if new_text and not new_text.endswith('\n'):
                added_lines += 1
            
            block_result.update({
                "status": "success",
                "removed_lines": removed_lines if old_text else 0,
                "added_lines": added_lines if new_text else 0
            })
            completed_indices.append(index)
            results.append(block_result)
        
        write_performed = False
        if completed_indices:
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(current_content)
                write_performed = True
            except Exception as e:
                write_error = f"写入文件失败: {e}"
                # 写入失败时恢复原始内容
                try:
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(original_content)
                except Exception:
                    pass
        
        success = bool(completed_indices) and not failed_details and write_error is None
        
        return {
            "success": success,
            "completed": completed_indices,
            "failed": failed_details,
            "results": results,
            "write_performed": write_performed,
            "error": write_error
        }
    
    def replace_in_file(self, path: str, old_text: str, new_text: str) -> Dict:
        """替换文件中的内容"""
        # 先读取文件
        result = self.read_file(path)
        if not result["success"]:
            return result
        
        content = result["content"]
        
        # === 新增：替换操作的安全检查 ===
        if old_text and len(old_text) > 9999999999:
            return {
                "success": False,
                "error": "要替换的文本过长，可能导致性能问题",
                "suggestion": "请拆分内容或使用 modify_file 提交结构化补丁"
            }
        
        if new_text and len(new_text) > 9999999999:
            return {
                "success": False,
                "error": "替换的新文本过长，建议分块处理",
                "suggestion": "请将大内容分成多个小的替换操作"
            }
        
        # 检查是否包含要替换的内容
        if old_text and old_text not in content:
            return {"success": False, "error": "未找到要替换的内容"}
        
        # 替换内容
        if old_text:
            new_content = content.replace(old_text, new_text)
            count = content.count(old_text)
        else:
            # 空文件直接写入新内容
            new_content = new_text
            count = 1
        
        # 写回文件
        result = self.write_file(path, new_content)
        if result["success"]:
            result["replacements"] = count
            print(f"{OUTPUT_FORMATS['file']} 替换了 {count} 处内容")
        
        return result
    
    def clear_file(self, path: str) -> Dict:
        """清空文件内容"""
        return self.write_file(path, "", mode="w")
    
    def edit_lines_range(self, path: str, start_line: int, end_line: int, content: str, operation: str) -> Dict:
        """
        基于行号编辑文件
        
        Args:
            path: 文件路径
            start_line: 起始行号（从1开始）
            end_line: 结束行号（从1开始，包含）
            content: 新内容
            operation: 操作类型 - "replace", "insert", "delete"
        """
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件不存在"}
        
        if not full_path.is_file():
            return {"success": False, "error": "不是文件"}
        
        # 验证行号
        if start_line < 1:
            return {"success": False, "error": "行号必须从1开始"}
        
        if end_line < start_line:
            return {"success": False, "error": "结束行号不能小于起始行号"}
        
        try:
            # 读取文件内容
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # 检查行号范围
            if start_line > total_lines:
                if operation == "insert":
                    # 插入操作允许在文件末尾后插入
                    lines.extend([''] * (start_line - total_lines - 1))
                    lines.append(content if content.endswith('\n') else content + '\n')
                else:
                    return {"success": False, "error": f"起始行号 {start_line} 超出文件范围 (共 {total_lines} 行)"}
            elif end_line > total_lines:
                return {"success": False, "error": f"结束行号 {end_line} 超出文件范围 (共 {total_lines} 行)"}
            else:
                # 执行操作（转换为0基索引）
                start_idx = start_line - 1
                end_idx = end_line
                
                if operation == "replace":
                    # 替换指定行范围
                    new_lines = content.split('\n') if '\n' in content else [content]
                    # 确保每行都有换行符，除了最后一行需要检查原文件格式
                    formatted_lines = []
                    for i, line in enumerate(new_lines):
                        if i < len(new_lines) - 1 or (end_idx < len(lines) and lines[end_idx - 1].endswith('\n')):
                            formatted_lines.append(line + '\n' if not line.endswith('\n') else line)
                        else:
                            formatted_lines.append(line)
                    
                    lines[start_idx:end_idx] = formatted_lines
                    affected_lines = end_line - start_line + 1
                    
                elif operation == "insert":
                    # 在指定行前插入内容
                    new_lines = content.split('\n') if '\n' in content else [content]
                    formatted_lines = [line + '\n' if not line.endswith('\n') else line for line in new_lines]
                    lines[start_idx:start_idx] = formatted_lines
                    affected_lines = len(formatted_lines)
                    
                elif operation == "delete":
                    # 删除指定行范围
                    affected_lines = end_line - start_line + 1
                    del lines[start_idx:end_idx]
                    
                else:
                    return {"success": False, "error": f"未知的操作类型: {operation}"}
            
            # 写回文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            relative_path = str(full_path.relative_to(self.project_path))
            
            # 生成操作描述
            if operation == "replace":
                operation_desc = f"替换第 {start_line}-{end_line} 行"
            elif operation == "insert":
                operation_desc = f"在第 {start_line} 行前插入"
            elif operation == "delete":
                operation_desc = f"删除第 {start_line}-{end_line} 行"
            
            print(f"{OUTPUT_FORMATS['file']} {operation_desc}: {relative_path}")
            
            return {
                "success": True,
                "path": relative_path,
                "operation": operation,
                "start_line": start_line,
                "end_line": end_line,
                "affected_lines": affected_lines,
                "total_lines_after": len(lines),
                "description": operation_desc
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_files(self, path: str = "") -> Dict:
        """列出目录内容"""
        if path:
            valid, error, full_path = self._validate_path(path)
            if not valid:
                return {"success": False, "error": error}
        else:
            full_path = self.project_path
        
        if not full_path.exists():
            return {"success": False, "error": "目录不存在"}
        
        if not full_path.is_dir():
            return {"success": False, "error": "不是目录"}
        
        try:
            files = []
            folders = []
            
            for item in full_path.iterdir():
                if item.name.startswith('.'):
                    continue
                
                relative_path = str(item.relative_to(self.project_path))
                
                if item.is_file():
                    files.append({
                        "name": item.name,
                        "path": relative_path,
                        "size": item.stat().st_size,
                        "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                    })
                elif item.is_dir():
                    folders.append({
                        "name": item.name,
                        "path": relative_path
                    })
            
            return {
                "success": True,
                "path": str(full_path.relative_to(self.project_path)) if path else ".",
                "files": sorted(files, key=lambda x: x["name"]),
                "folders": sorted(folders, key=lambda x: x["name"])
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_file_info(self, path: str) -> Dict:
        """获取文件信息"""
        valid, error, full_path = self._validate_path(path)
        if not valid:
            return {"success": False, "error": error}
        
        if not full_path.exists():
            return {"success": False, "error": "文件不存在"}
        
        try:
            stat = full_path.stat()
            relative_path = str(full_path.relative_to(self.project_path))
            
            return {
                "success": True,
                "path": relative_path,
                "name": full_path.name,
                "type": "file" if full_path.is_file() else "folder",
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "extension": full_path.suffix if full_path.is_file() else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
