# modules/search_engine.py - 网络搜索模块

import httpx
import json
from typing import Dict, List, Optional
from datetime import datetime
try:
    from config import TAVILY_API_KEY, SEARCH_MAX_RESULTS, OUTPUT_FORMATS
except ImportError:
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from config import TAVILY_API_KEY, SEARCH_MAX_RESULTS, OUTPUT_FORMATS

class SearchEngine:
    def __init__(self):
        self.api_key = TAVILY_API_KEY
        self.api_url = "https://api.tavily.com/search"
        
    async def search(self, query: str, max_results: int = None) -> Dict:
        """
        执行网络搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
        
        Returns:
            搜索结果字典
        """
        if not self.api_key or self.api_key == "your-tavily-api-key":
            return {
                "success": False,
                "error": "Tavily API密钥未配置",
                "results": []
            }
        
        max_results = max_results or SEARCH_MAX_RESULTS
        
        print(f"{OUTPUT_FORMATS['search']} 搜索: {query}")
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.api_url,
                    json={
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": max_results,
                        "include_answer": True,
                        "include_images": False,
                        "include_raw_content": False
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"API请求失败: {response.status_code}",
                        "results": []
                    }
                
                data = response.json()
                
                # 格式化结果
                formatted_results = self._format_results(data)
                
                print(f"{OUTPUT_FORMATS['success']} 搜索完成，找到 {len(formatted_results['results'])} 条结果")
                
                return formatted_results
                
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "搜索超时",
                "results": []
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}",
                "results": []
            }
    
    def _format_results(self, raw_data: Dict) -> Dict:
        """格式化搜索结果"""
        formatted = {
            "success": True,
            "query": raw_data.get("query", ""),
            "answer": raw_data.get("answer", ""),
            "results": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # 处理每个搜索结果
        for idx, result in enumerate(raw_data.get("results", []), 1):
            formatted_result = {
                "index": idx,
                "title": result.get("title", "无标题"),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "score": result.get("score", 0),
                "published_date": result.get("published_date", "")
            }
            formatted["results"].append(formatted_result)
        
        return formatted
    
    async def search_with_summary(self, query: str, max_results: int = None) -> str:
        """
        搜索并返回格式化的摘要
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
        
        Returns:
            格式化的搜索摘要字符串
        """
        results = await self.search(query, max_results)
        
        if not results["success"]:
            return f"搜索失败: {results['error']}"
        
        # 构建摘要
        summary_lines = [
            f"🔍 搜索查询: {query}",
            f"📅 搜索时间: {results['timestamp']}",
            ""
        ]
        
        # 添加AI答案（如果有）
        if results.get("answer"):
            summary_lines.extend([
                "📝 AI摘要:",
                results["answer"],
                "",
                "---",
                ""
            ])
        
        # 添加搜索结果
        if results["results"]:
            summary_lines.append("📊 搜索结果:")
            
            for result in results["results"]:
                summary_lines.extend([
                    f"\n{result['index']}. {result['title']}",
                    f"   🔗 {result['url']}",
                    f"   📄 {result['content'][:200]}..." if len(result['content']) > 200 else f"   📄 {result['content']}",
                ])
                
                if result.get("published_date"):
                    summary_lines.append(f"   📅 发布时间: {result['published_date']}")
        else:
            summary_lines.append("未找到相关结果")
        
        return "\n".join(summary_lines)
    
    async def quick_answer(self, query: str) -> str:
        """
        快速获取答案（只返回AI摘要）
        
        Args:
            query: 查询问题
        
        Returns:
            AI答案或错误信息
        """
        results = await self.search(query, max_results=5)
        
        if not results["success"]:
            return f"搜索失败: {results['error']}"
        
        if results.get("answer"):
            return results["answer"]
        
        # 如果没有AI答案，返回第一个结果的摘要
        if results["results"]:
            first_result = results["results"][0]
            return f"{first_result['title']}\n{first_result['content'][:300]}..."
        
        return "未找到相关信息"
    
    def save_results(self, results: Dict, filename: str = None) -> str:
        """
        保存搜索结果到文件
        
        Args:
            results: 搜索结果
            filename: 文件名（可选）
        
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"search_{timestamp}.json"
        
        file_path = f"./data/searches/{filename}"
        
        # 确保目录存在
        import os
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 保存结果
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"{OUTPUT_FORMATS['file']} 搜索结果已保存到: {file_path}")
        
        return file_path
    
    def load_results(self, filename: str) -> Optional[Dict]:
        """
        加载之前的搜索结果
        
        Args:
            filename: 文件名
        
        Returns:
            搜索结果字典或None
        """
        file_path = f"./data/searches/{filename}"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"{OUTPUT_FORMATS['error']} 文件不存在: {file_path}")
            return None
        except Exception as e:
            print(f"{OUTPUT_FORMATS['error']} 加载失败: {e}")
            return None
