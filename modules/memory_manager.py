# modules/memory_manager.py - 记忆管理模块

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
try:
    from config import MAIN_MEMORY_FILE, TASK_MEMORY_FILE, DATA_DIR, OUTPUT_FORMATS
except ImportError:
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from config import MAIN_MEMORY_FILE, TASK_MEMORY_FILE, DATA_DIR, OUTPUT_FORMATS

class MemoryManager:
    def __init__(self):
        self.main_memory_path = Path(MAIN_MEMORY_FILE)
        self.task_memory_path = Path(TASK_MEMORY_FILE)
        self.ensure_files_exist()
    
    def ensure_files_exist(self):
        """确保记忆文件存在"""
        # 创建数据目录
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # 创建主记忆文件
        if not self.main_memory_path.exists():
            self.create_memory_file(self.main_memory_path, "主记忆文件")
        
        # 创建任务记忆文件
        if not self.task_memory_path.exists():
            self.create_memory_file(self.task_memory_path, "任务记忆文件")
    
    def create_memory_file(self, path: Path, title: str):
        """创建记忆文件"""
        template = f"""# {title}
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 项目信息


## 重要记录


## 经验总结


## 待办事项

"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(template)
        
        print(f"{OUTPUT_FORMATS['memory']} 创建{title}: {path}")
    
    def read_main_memory(self) -> str:
        """读取主记忆"""
        try:
            with open(self.main_memory_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 读取主记忆失败: {e}")
            return ""
    
    def read_task_memory(self) -> str:
        """读取任务记忆"""
        try:
            with open(self.task_memory_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 读取任务记忆失败: {e}")
            return ""
    
    def write_main_memory(self, content: str) -> bool:
        """写入主记忆"""
        try:
            with open(self.main_memory_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{OUTPUT_FORMATS['memory']} 更新主记忆")
            return True
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 写入主记忆失败: {e}")
            return False
    
    def write_task_memory(self, content: str) -> bool:
        """写入任务记忆"""
        try:
            with open(self.task_memory_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{OUTPUT_FORMATS['memory']} 更新任务记忆")
            return True
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 写入任务记忆失败: {e}")
            return False
    
    def append_main_memory(self, content: str, section: str = None) -> bool:
        """追加内容到主记忆"""
        try:
            current = self.read_main_memory()
            
            # 添加时间戳
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if section:
                # 追加到特定部分
                new_entry = f"\n### [{timestamp}] {section}\n{content}\n"
                if f"## {section}" in current:
                    # 在该部分后添加
                    parts = current.split(f"## {section}")
                    if len(parts) > 1:
                        # 找到下一个##的位置
                        next_section = parts[1].find("\n##")
                        if next_section > 0:
                            parts[1] = parts[1][:next_section] + new_entry + parts[1][next_section:]
                        else:
                            parts[1] = parts[1] + new_entry
                        current = f"## {section}".join(parts)
                    else:
                        current += new_entry
                else:
                    # 创建新部分
                    current += f"\n## {section}\n{new_entry}"
            else:
                # 追加到末尾
                current += f"\n### [{timestamp}]\n{content}\n"
            
            return self.write_main_memory(current)
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 追加主记忆失败: {e}")
            return False
    
    def append_task_memory(self, content: str, task_id: str = None) -> bool:
        """追加内容到任务记忆"""
        try:
            current = self.read_task_memory()
            
            # 添加时间戳
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if task_id:
                new_entry = f"\n### 任务 {task_id} - {timestamp}\n{content}\n"
            else:
                new_entry = f"\n### {timestamp}\n{content}\n"
            
            current += new_entry
            
            return self.write_task_memory(current)
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 追加任务记忆失败: {e}")
            return False
    
    def search_memory(self, keyword: str, memory_type: str = "main") -> List[str]:
        """搜索记忆内容"""
        if memory_type == "main":
            content = self.read_main_memory()
        else:
            content = self.read_task_memory()
        
        results = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                # 获取上下文（前后各2行）
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = '\n'.join(lines[start:end])
                results.append(context)
        
        return results
    
    def clear_task_memory(self) -> bool:
        """清空任务记忆"""
        try:
            self.create_memory_file(self.task_memory_path, "任务记忆文件")
            print(f"{OUTPUT_FORMATS['memory']} 清空任务记忆")
            return True
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 清空任务记忆失败: {e}")
            return False
    
    def backup_memory(self, memory_type: str = "main") -> str:
        """备份记忆文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if memory_type == "main":
            source = self.main_memory_path
            backup_name = f"main_memory_backup_{timestamp}.md"
        else:
            source = self.task_memory_path
            backup_name = f"task_memory_backup_{timestamp}.md"
        
        backup_path = Path(DATA_DIR) / "backups" / backup_name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import shutil
            shutil.copy2(source, backup_path)
            print(f"{OUTPUT_FORMATS['success']} 备份成功: {backup_path}")
            return str(backup_path)
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 备份失败: {e}")
            return ""
    
    def restore_memory(self, backup_path: str, memory_type: str = "main") -> bool:
        """恢复记忆文件"""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            print(f"{OUTPUT_FORMATS['error']} 备份文件不存在: {backup_path}")
            return False
        
        if memory_type == "main":
            target = self.main_memory_path
        else:
            target = self.task_memory_path
        
        try:
            import shutil
            # 先备份当前文件
            self.backup_memory(memory_type)
            # 恢复备份
            shutil.copy2(backup_file, target)
            print(f"{OUTPUT_FORMATS['success']} 恢复成功: {target}")
            return True
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 恢复失败: {e}")
            return False
    
    def get_memory_stats(self) -> Dict:
        """获取记忆统计信息"""
        stats = {
            "main_memory": {
                "exists": self.main_memory_path.exists(),
                "size": 0,
                "lines": 0,
                "last_modified": None
            },
            "task_memory": {
                "exists": self.task_memory_path.exists(),
                "size": 0,
                "lines": 0,
                "last_modified": None
            }
        }
        
        # 主记忆统计
        if stats["main_memory"]["exists"]:
            stat = self.main_memory_path.stat()
            content = self.read_main_memory()
            stats["main_memory"]["size"] = stat.st_size
            stats["main_memory"]["lines"] = len(content.split('\n'))
            stats["main_memory"]["last_modified"] = datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat()
        
        # 任务记忆统计
        if stats["task_memory"]["exists"]:
            stat = self.task_memory_path.stat()
            content = self.read_task_memory()
            stats["task_memory"]["size"] = stat.st_size
            stats["task_memory"]["lines"] = len(content.split('\n'))
            stats["task_memory"]["last_modified"] = datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat()
        
        return stats
    
    def merge_memories(self) -> bool:
        """合并任务记忆到主记忆"""
        try:
            task_content = self.read_task_memory()
            
            if not task_content.strip():
                print(f"{OUTPUT_FORMATS['warning']} 任务记忆为空，无需合并")
                return True
            
            # 追加到主记忆
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            merge_content = f"\n## 任务记忆合并 - {timestamp}\n{task_content}\n"
            
            success = self.append_main_memory(merge_content, "历史任务记录")
            
            if success:
                # 清空任务记忆
                self.clear_task_memory()
                print(f"{OUTPUT_FORMATS['success']} 记忆合并完成")
            
            return success
            
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 合并记忆失败: {e}")
            return False
