# web_server.py - Web服务器（修复版 - 确保text_end事件正确发送 + 停止功能）

import asyncio
import json
import os
import sys
import re
from typing import Dict, List, Optional, Callable
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from pathlib import Path
import time
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.web_terminal import WebTerminal
from config import (
    OUTPUT_FORMATS,
    AUTO_FIX_TOOL_CALL,
    AUTO_FIX_MAX_ATTEMPTS,
    MAX_ITERATIONS_PER_TASK,
    MAX_CONSECUTIVE_SAME_TOOL,
    MAX_TOTAL_TOOL_CALLS,
    TOOL_CALL_COOLDOWN
)
from pathlib import Path

# 如果使用了新的配置项，还需要添加：
from config import (
    DEFAULT_CONVERSATIONS_LIMIT, 
    MAX_CONVERSATIONS_LIMIT,
    CONVERSATIONS_DIR,
    DEFAULT_RESPONSE_MAX_TOKENS
)

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'your-secret-key-here'
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局变量
web_terminal = None
project_path = None
terminal_rooms = {}  # 跟踪终端订阅者
stop_flags = {}  # 新增：停止标志字典，按连接ID管理

# 创建调试日志文件
DEBUG_LOG_FILE = "debug_stream.log"

def reset_system_state():
    """完整重置系统状态，确保停止后能正常开始新任务"""
    global web_terminal
    
    if not web_terminal:
        return
    
    try:
        # 1. 重置API客户端状态
        if hasattr(web_terminal, 'api_client') and web_terminal.api_client:
            debug_log("重置API客户端状态")
            web_terminal.api_client.start_new_task()  # 重置思考模式状态
        
        # 2. 重置主终端会话状态
        if hasattr(web_terminal, 'current_session_id'):
            web_terminal.current_session_id += 1  # 开始新会话
            debug_log(f"重置会话ID为: {web_terminal.current_session_id}")
        
        # 3. 清理读取文件跟踪器
        if hasattr(web_terminal, 'read_file_usage_tracker'):
            web_terminal.read_file_usage_tracker.clear()
            debug_log("清理文件读取跟踪器")
        
        # 4. 重置Web特有的状态属性
        web_attrs = ['streamingMessage', 'currentMessageIndex', 'preparingTools', 'activeTools']
        for attr in web_attrs:
            if hasattr(web_terminal, attr):
                if attr in ['streamingMessage']:
                    setattr(web_terminal, attr, False)
                elif attr in ['currentMessageIndex']:
                    setattr(web_terminal, attr, -1)
                elif attr in ['preparingTools', 'activeTools'] and hasattr(getattr(web_terminal, attr), 'clear'):
                    getattr(web_terminal, attr).clear()
        
        debug_log("系统状态重置完成")
        
    except Exception as e:
        debug_log(f"状态重置过程中出现错误: {e}")
        import traceback
        debug_log(f"错误详情: {traceback.format_exc()}")


def debug_log(message):
    """写入调试日志"""
    with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        f.write(f"[{timestamp}] {message}\n")

# 终端广播回调函数
def terminal_broadcast(event_type, data):
    """广播终端事件到所有订阅者"""
    try:
        # 对于token_update事件，发送给所有连接的客户端
        if event_type == 'token_update':
            socketio.emit(event_type, data)  # 全局广播，不限制房间
            debug_log(f"全局广播token更新: {data}")
        else:
            # 其他终端事件发送到终端订阅者房间
            socketio.emit(event_type, data, room='terminal_subscribers')
            
            # 如果是特定会话的事件，也发送到该会话的专属房间
            if 'session' in data:
                session_room = f"terminal_{data['session']}"
                socketio.emit(event_type, data, room=session_room)
        
        debug_log(f"终端广播: {event_type} - {data}")
    except Exception as e:
        debug_log(f"终端广播错误: {e}")

@app.route('/')
def index():
    """主页"""
    return app.send_static_file('index.html')

@app.route('/terminal')
def terminal_page():
    """终端监控页面"""
    return app.send_static_file('terminal.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """提供静态文件"""
    return send_from_directory('static', filename)

@app.route('/api/status')
def get_status():
    """获取系统状态（增强版：包含对话信息）"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    status = web_terminal.get_status()
    
    # 添加终端状态信息
    if web_terminal.terminal_manager:
        terminal_status = web_terminal.terminal_manager.list_terminals()
        status['terminals'] = terminal_status
    
    # 【新增】添加当前对话的详细信息
    if web_terminal.context_manager.current_conversation_id:
        try:
            current_conv_data = web_terminal.context_manager.conversation_manager.load_conversation(
                web_terminal.context_manager.current_conversation_id
            )
            if current_conv_data:
                status['conversation']['title'] = current_conv_data.get('title', '未知对话')
                status['conversation']['created_at'] = current_conv_data.get('created_at')
                status['conversation']['updated_at'] = current_conv_data.get('updated_at')
        except Exception as e:
            print(f"[Status] 获取当前对话信息失败: {e}")
    
    return jsonify(status)

@app.route('/api/files')
def get_files():
    """获取文件树"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    structure = web_terminal.context_manager.get_project_structure()
    return jsonify(structure)

@app.route('/api/focused')
def get_focused_files():
    """获取聚焦文件"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    focused = {}
    for path, content in web_terminal.focused_files.items():
        focused[path] = {
            "content": content,
            "size": len(content),
            "lines": content.count('\n') + 1
        }
    return jsonify(focused)

@app.route('/api/terminals')
def get_terminals():
    """获取终端会话列表"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    if web_terminal.terminal_manager:
        result = web_terminal.terminal_manager.list_terminals()
        return jsonify(result)
    else:
        return jsonify({"sessions": [], "active": None, "total": 0})

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端连接: {request.sid}")
    emit('connected', {'status': 'Connected to server'})
    
    # 清理可能存在的停止标志和状态
    stop_flags.pop(request.sid, None)
    
    # 如果是终端页面的连接，自动加入终端订阅房间
    if request.path == '/socket.io/' and request.referrer and '/terminal' in request.referrer:
        join_room('terminal_subscribers')
        print(f"[WebSocket] {request.sid} 自动加入终端订阅房间")
    
    if web_terminal:
        # 确保系统状态是干净的
        reset_system_state()
        
        emit('system_ready', {
            'project_path': project_path,
            'thinking_mode': web_terminal.get_thinking_mode_status()
        })
        
        # 发送当前终端列表和状态
        if web_terminal.terminal_manager:
            terminals = web_terminal.terminal_manager.get_terminal_list()
            emit('terminal_list_update', {
                'terminals': terminals,
                'active': web_terminal.terminal_manager.active_terminal
            })
            
            # 如果有活动终端，发送其状态
            if web_terminal.terminal_manager.active_terminal:
                for name, terminal in web_terminal.terminal_manager.terminals.items():
                    emit('terminal_started', {
                        'session': name,
                        'working_dir': str(terminal.working_dir),
                        'shell': terminal.shell_command,
                        'time': terminal.start_time.isoformat() if terminal.start_time else None
                    })

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f"[WebSocket] 客户端断开: {request.sid}")
    
    # 清理停止标志
    stop_flags.pop(request.sid, None)
    
    # 从所有房间移除
    leave_room('terminal_subscribers')
    for room in list(terminal_rooms.get(request.sid, [])):
        leave_room(room)
    if request.sid in terminal_rooms:
        del terminal_rooms[request.sid]

@socketio.on('stop_task')
def handle_stop_task():
    """处理停止任务请求"""
    print(f"[停止] 收到停止请求: {request.sid}")
    
    # 检查是否有正在运行的任务
    if request.sid in stop_flags and isinstance(stop_flags[request.sid], dict):
        # 获取任务引用并取消
        task_info = stop_flags[request.sid]
        if 'task' in task_info and not task_info['task'].done():
            debug_log(f"正在取消任务: {request.sid}")
            task_info['task'].cancel()
        
        # 设置停止标志
        task_info['stop'] = True
    else:
        # 如果没有任务引用，使用旧的布尔标志
        stop_flags[request.sid] = True
    
    emit('stop_requested', {
        'message': '停止请求已接收，正在取消任务...'
    })

@socketio.on('terminal_subscribe')
def handle_terminal_subscribe(data):
    """订阅终端事件"""
    session_name = data.get('session')
    subscribe_all = data.get('all', False)
    
    if request.sid not in terminal_rooms:
        terminal_rooms[request.sid] = set()
    
    if subscribe_all:
        # 订阅所有终端事件
        join_room('terminal_subscribers')
        terminal_rooms[request.sid].add('terminal_subscribers')
        print(f"[Terminal] {request.sid} 订阅所有终端事件")
        
        # 发送当前终端状态
        if web_terminal and web_terminal.terminal_manager:
            emit('terminal_subscribed', {
                'type': 'all',
                'terminals': web_terminal.terminal_manager.get_terminal_list()
            })
    elif session_name:
        # 订阅特定终端会话
        room_name = f'terminal_{session_name}'
        join_room(room_name)
        terminal_rooms[request.sid].add(room_name)
        print(f"[Terminal] {request.sid} 订阅终端: {session_name}")
        
        # 发送该终端的当前输出
        if web_terminal and web_terminal.terminal_manager:
            output_result = web_terminal.terminal_manager.get_terminal_output(session_name, 100)
            if output_result['success']:
                emit('terminal_history', {
                    'session': session_name,
                    'output': output_result['output']
                })

@socketio.on('terminal_unsubscribe')
def handle_terminal_unsubscribe(data):
    """取消订阅终端事件"""
    session_name = data.get('session')
    
    if session_name:
        room_name = f'terminal_{session_name}'
        leave_room(room_name)
        if request.sid in terminal_rooms:
            terminal_rooms[request.sid].discard(room_name)
        print(f"[Terminal] {request.sid} 取消订阅终端: {session_name}")

@socketio.on('get_terminal_output')
def handle_get_terminal_output(data):
    """获取终端输出历史"""
    session_name = data.get('session')
    lines = data.get('lines', 50)
    
    if not web_terminal or not web_terminal.terminal_manager:
        emit('error', {'message': 'Terminal system not initialized'})
        return
    
    result = web_terminal.terminal_manager.get_terminal_output(session_name, lines)
    
    if result['success']:
        emit('terminal_output_history', {
            'session': session_name,
            'output': result['output'],
            'is_interactive': result.get('is_interactive', False),
            'last_command': result.get('last_command', '')
        })
    else:
        emit('error', {'message': result['error']})

@socketio.on('send_message')
def handle_message(data):
    """处理用户消息"""
    message = data.get('message', '')
    print(f"[WebSocket] 收到消息: {message}")
    debug_log(f"\n{'='*80}\n新任务开始: {message}\n{'='*80}")
    
    if not web_terminal:
        emit('error', {'message': 'System not initialized'})
        return
    
    def send_to_client(event_type, data):
        """发送消息到客户端"""
        socketio.emit(event_type, data)
    
    # 传递客户端ID
    socketio.start_background_task(process_message_task, message, send_to_client, request.sid)

# 在 web_server.py 中添加以下对话管理API接口
# 添加在现有路由之后，@socketio 事件处理之前

# ==========================================
# 对话管理API接口
# ==========================================

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """获取对话列表"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        # 获取查询参数
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # 限制参数范围
        limit = max(1, min(limit, 100))  # 限制在1-100之间
        offset = max(0, offset)
        
        result = web_terminal.get_conversations_list(limit=limit, offset=offset)
        
        if result["success"]:
            return jsonify({
                "success": True,
                "data": result["data"]
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Unknown error"),
                "message": result.get("message", "获取对话列表失败")
            }), 500
            
    except Exception as e:
        print(f"[API] 获取对话列表错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "获取对话列表时发生异常"
        }), 500

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    """创建新对话"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        data = request.get_json() or {}
        thinking_mode = data.get('thinking_mode', web_terminal.thinking_mode)
        
        result = web_terminal.create_new_conversation(thinking_mode=thinking_mode)
        
        if result["success"]:
            # 广播对话列表更新事件
            socketio.emit('conversation_list_update', {
                'action': 'created',
                'conversation_id': result["conversation_id"]
            })
            
            # 广播当前对话切换事件
            socketio.emit('conversation_changed', {
                'conversation_id': result["conversation_id"],
                'title': "新对话"
            })
            
            return jsonify(result), 201
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"[API] 创建对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "创建对话时发生异常"
        }), 500

@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation_info(conversation_id):
    """获取特定对话信息"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        # 通过ConversationManager直接获取对话数据
        conversation_data = web_terminal.context_manager.conversation_manager.load_conversation(conversation_id)
        
        if conversation_data:
            # 提取关键信息，不返回完整消息内容（避免数据量过大）
            info = {
                "id": conversation_data["id"],
                "title": conversation_data["title"],
                "created_at": conversation_data["created_at"],
                "updated_at": conversation_data["updated_at"],
                "metadata": conversation_data["metadata"],
                "messages_count": len(conversation_data.get("messages", []))
            }
            
            return jsonify({
                "success": True,
                "data": info
            })
        else:
            return jsonify({
                "success": False,
                "error": "Conversation not found",
                "message": f"对话 {conversation_id} 不存在"
            }), 404
            
    except Exception as e:
        print(f"[API] 获取对话信息错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "获取对话信息时发生异常"
        }), 500

@app.route('/api/conversations/<conversation_id>/load', methods=['PUT'])
def load_conversation(conversation_id):
    """加载特定对话"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        result = web_terminal.load_conversation(conversation_id)
        
        if result["success"]:
            # 广播对话切换事件
            socketio.emit('conversation_changed', {
                'conversation_id': conversation_id,
                'title': result.get("title", "未知对话"),
                'messages_count': result.get("messages_count", 0)
            })
            
            # 广播系统状态更新（因为当前对话改变了）
            status = web_terminal.get_status()
            socketio.emit('status_update', status)
            
            # 清理和重置相关UI状态
            socketio.emit('conversation_loaded', {
                'conversation_id': conversation_id,
                'clear_ui': True  # 提示前端清理当前UI状态
            })
            
            return jsonify(result)
        else:
            return jsonify(result), 404 if "不存在" in result.get("message", "") else 500
            
    except Exception as e:
        print(f"[API] 加载对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "加载对话时发生异常"
        }), 500

@app.route('/api/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """删除特定对话"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        # 检查是否是当前对话
        is_current = (web_terminal.context_manager.current_conversation_id == conversation_id)
        
        result = web_terminal.delete_conversation(conversation_id)
        
        if result["success"]:
            # 广播对话列表更新事件
            socketio.emit('conversation_list_update', {
                'action': 'deleted',
                'conversation_id': conversation_id
            })
            
            # 如果删除的是当前对话，广播对话清空事件
            if is_current:
                socketio.emit('conversation_changed', {
                    'conversation_id': None,
                    'title': None,
                    'cleared': True
                })
                
                # 更新系统状态
                status = web_terminal.get_status()
                socketio.emit('status_update', status)
            
            return jsonify(result)
        else:
            return jsonify(result), 404 if "不存在" in result.get("message", "") else 500
            
    except Exception as e:
        print(f"[API] 删除对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "删除对话时发生异常"
        }), 500

@app.route('/api/conversations/search', methods=['GET'])
def search_conversations():
    """搜索对话"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        query = request.args.get('q', '').strip()
        limit = request.args.get('limit', 20, type=int)
        
        if not query:
            return jsonify({
                "success": False,
                "error": "Missing query parameter",
                "message": "请提供搜索关键词"
            }), 400
        
        # 限制参数范围
        limit = max(1, min(limit, 50))
        
        result = web_terminal.search_conversations(query, limit)
        
        return jsonify({
            "success": True,
            "data": {
                "results": result["results"],
                "count": result["count"],
                "query": query
            }
        })
            
    except Exception as e:
        print(f"[API] 搜索对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "搜索对话时发生异常"
        }), 500

@app.route('/api/conversations/<conversation_id>/messages', methods=['GET'])
def get_conversation_messages(conversation_id):
    """获取对话的消息历史（可选功能，用于调试或详细查看）"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        # 获取完整对话数据
        conversation_data = web_terminal.context_manager.conversation_manager.load_conversation(conversation_id)
        
        if conversation_data:
            messages = conversation_data.get("messages", [])
            
            # 可选：限制消息数量，避免返回过多数据
            limit = request.args.get('limit', type=int)
            if limit:
                messages = messages[-limit:]  # 获取最后N条消息
            
            return jsonify({
                "success": True,
                "data": {
                    "conversation_id": conversation_id,
                    "messages": messages,
                    "total_count": len(conversation_data.get("messages", []))
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Conversation not found",
                "message": f"对话 {conversation_id} 不存在"
            }), 404
            
    except Exception as e:
        print(f"[API] 获取对话消息错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "获取对话消息时发生异常"
        }), 500


@app.route('/api/conversations/<conversation_id>/compress', methods=['POST'])
def compress_conversation(conversation_id):
    """压缩指定对话的大体积消息，生成压缩版新对话"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503

    try:
        result = web_terminal.context_manager.compress_conversation(conversation_id)

        if not result.get("success"):
            status_code = 404 if "不存在" in result.get("error", "") else 400
            return jsonify(result), status_code

        new_conversation_id = result["compressed_conversation_id"]

        load_result = web_terminal.load_conversation(new_conversation_id)

        if load_result.get("success"):
            socketio.emit('conversation_list_update', {
                'action': 'compressed',
                'conversation_id': new_conversation_id
            })
            socketio.emit('conversation_changed', {
                'conversation_id': new_conversation_id,
                'title': load_result.get('title', '压缩后的对话'),
                'messages_count': load_result.get('messages_count', 0)
            })
            socketio.emit('conversation_loaded', {
                'conversation_id': new_conversation_id,
                'clear_ui': True
            })

        response_payload = {
            "success": True,
            "compressed_conversation_id": new_conversation_id,
            "compressed_types": result.get("compressed_types", []),
            "system_message": result.get("system_message"),
            "load_result": load_result
        }

        return jsonify(response_payload)

    except Exception as e:
        print(f"[API] 压缩对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "压缩对话时发生异常"
        }), 500


@app.route('/api/conversations/<conversation_id>/duplicate', methods=['POST'])
def duplicate_conversation(conversation_id):
    """复制指定对话，生成新的对话副本"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503

    try:
        result = web_terminal.context_manager.duplicate_conversation(conversation_id)

        if not result.get("success"):
            status_code = 404 if "不存在" in result.get("error", "") else 400
            return jsonify(result), status_code

        new_conversation_id = result["duplicate_conversation_id"]
        load_result = web_terminal.load_conversation(new_conversation_id)

        if load_result.get("success"):
            socketio.emit('conversation_list_update', {
                'action': 'duplicated',
                'conversation_id': new_conversation_id
            })
            socketio.emit('conversation_changed', {
                'conversation_id': new_conversation_id,
                'title': load_result.get('title', '复制的对话'),
                'messages_count': load_result.get('messages_count', 0)
            })
            socketio.emit('conversation_loaded', {
                'conversation_id': new_conversation_id,
                'clear_ui': True
            })

        response_payload = {
            "success": True,
            "duplicate_conversation_id": new_conversation_id,
            "load_result": load_result
        }

        return jsonify(response_payload)

    except Exception as e:
        print(f"[API] 复制对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "复制对话时发生异常"
        }), 500

@app.route('/api/conversations/statistics', methods=['GET'])
def get_conversations_statistics():
    """获取对话统计信息"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        stats = web_terminal.context_manager.get_conversation_statistics()
        
        return jsonify({
            "success": True,
            "data": stats
        })
            
    except Exception as e:
        print(f"[API] 获取对话统计错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "获取对话统计时发生异常"
        }), 500

@app.route('/api/conversations/current', methods=['GET'])
def get_current_conversation():
    """获取当前对话信息"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    current_id = web_terminal.context_manager.current_conversation_id
    
    # 如果是临时ID，返回空的对话信息
    if not current_id or current_id.startswith('temp_'):
        return jsonify({
            "success": True,
            "data": {
                "id": current_id,
                "title": "新对话",
                "messages_count": 0,
                "is_temporary": True
            }
        })
    
    # 如果是真实的对话ID，查找对话数据
    try:
        conversation_data = web_terminal.context_manager.conversation_manager.load_conversation(current_id)
        if conversation_data:
            return jsonify({
                "success": True,
                "data": {
                    "id": current_id,
                    "title": conversation_data.get("title", "未知对话"),
                    "messages_count": len(conversation_data.get("messages", [])),
                    "is_temporary": False
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "对话不存在"
            }), 404
            
    except Exception as e:
        print(f"[API] 获取当前对话错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
def process_message_task(message, sender, client_sid):
    """在后台处理消息任务"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 创建可取消的任务
        task = loop.create_task(handle_task_with_sender(message, sender, client_sid))
        
        # 存储任务引用，以便取消
        if client_sid not in stop_flags:
            stop_flags[client_sid] = {'stop': False, 'task': task}
        else:
            stop_flags[client_sid]['task'] = task
        
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            debug_log(f"任务 {client_sid} 被成功取消")
            sender('task_stopped', {
                'message': '任务已停止',
                'reason': 'user_requested'
            })
            reset_system_state()
        
        loop.close()
    except Exception as e:
        # 【新增】错误时确保对话状态不丢失
        try:
            if web_terminal and web_terminal.context_manager:
                # 尝试保存当前对话状态
                web_terminal.context_manager.auto_save_conversation()
                debug_log("错误恢复：对话状态已保存")
        except Exception as save_error:
            debug_log(f"错误恢复：保存对话状态失败: {save_error}")
        
    # 修改为：
    except Exception as e:
        # 【新增】错误时确保对话状态不丢失
        try:
            if web_terminal and web_terminal.context_manager:
                # 尝试保存当前对话状态
                web_terminal.context_manager.auto_save_conversation()
                debug_log("错误恢复：对话状态已保存")
        except Exception as save_error:
            debug_log(f"错误恢复：保存对话状态失败: {save_error}")
        
        # 原有的错误处理逻辑
        print(f"[Task] 错误: {e}")
        debug_log(f"任务处理错误: {e}")
        import traceback
        traceback.print_exc()
        sender('error', {'message': str(e)})

    finally:
        # 清理任务引用
        if client_sid in stop_flags and isinstance(stop_flags[client_sid], dict):
            stop_flags.pop(client_sid, None)

def detect_malformed_tool_call(text):
    """检测文本中是否包含格式错误的工具调用"""
    # 检测多种可能的工具调用格式
    patterns = [
        r'执行工具[:：]\s*\w+<.*?tool.*?sep.*?>',  # 执行工具: xxx<｜tool▼sep｜>
        r'<\|?tool[_▼]?call[_▼]?start\|?>',  # <｜tool_call_start｜>
        r'```tool[_\s]?call',  # ```tool_call 或 ```tool call
        r'{\s*"tool":\s*"[^"]+",\s*"arguments"',  # JSON格式的工具调用
        r'function_calls?:\s*\[?\s*{',  # function_call: [{
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    # 检测特定的工具名称后跟JSON
    tool_names = ['create_file', 'read_file', 'modify_file', 'delete_file', 
                  'append_to_file', 'terminal_session', 'terminal_input', 'web_search', 
                  'extract_webpage', 'save_webpage',
                  'run_python', 'run_command', 'focus_file', 'unfocus_file', 'sleep']
    for tool in tool_names:
        if tool in text and '{' in text:
            # 可能是工具调用但格式错误
            return True
            
    return False

async def handle_task_with_sender(message, sender, client_sid):
    """处理任务并发送消息 - 集成token统计版本"""
    
    # 如果是思考模式，重置状态
    if web_terminal.thinking_mode:
        web_terminal.api_client.start_new_task()
    
    # 添加到对话历史
    web_terminal.context_manager.add_conversation("user", message)
    
    # === 移除：不在这里计算输入token，改为在每次API调用前计算 ===
    
    # 构建上下文和消息（用于API调用）
    context = web_terminal.build_context()
    messages = web_terminal.build_messages(context, message)
    tools = web_terminal.define_tools()
    
    # 开始新的AI消息
    sender('ai_message_start', {})
    
    # 增量保存相关变量
    has_saved_thinking = False  # 是否已保存思考内容
    accumulated_response = ""   # 累积的响应内容
    is_first_iteration = True   # 是否是第一次迭代
    
    # 统计和限制变量
    total_iterations = 0
    total_tool_calls = 0
    consecutive_same_tool = defaultdict(int)
    last_tool_name = ""
    auto_fix_attempts = 0
    last_tool_call_time = 0
    
    # 设置最大迭代次数
    max_iterations = MAX_ITERATIONS_PER_TASK
    
    pending_append = None  # {"path": str, "tool_call_id": str, "buffer": str, ...}
    append_probe_buffer = ""
    pending_modify = None  # {"path": str, "tool_call_id": str, "buffer": str, ...}
    modify_probe_buffer = ""
    
    async def finalize_pending_append(response_text: str, stream_completed: bool, finish_reason: str = None) -> Dict:
        """在流式输出结束后处理追加写入"""
        nonlocal pending_append, append_probe_buffer
        
        result = {
            "handled": False,
            "success": False,
            "summary": None,
            "summary_message": None,
            "tool_content": None,
            "tool_call_id": None,
            "path": None,
            "forced": False,
            "error": None,
            "assistant_content": response_text,
            "lines": 0,
            "bytes": 0,
            "finish_reason": finish_reason,
            "appended_content": "",
            "assistant_metadata": None
        }
        
        if not pending_append:
            return result
        
        state = pending_append
        path = state.get("path")
        tool_call_id = state.get("tool_call_id")
        buffer = state.get("buffer", "")
        start_marker = state.get("start_marker")
        end_marker = state.get("end_marker")
        start_idx = state.get("content_start")
        end_idx = state.get("end_index")
        
        display_id = state.get("display_id")
        
        result.update({
            "handled": True,
            "path": path,
            "tool_call_id": tool_call_id,
            "display_id": display_id
        })
        
        if path is None or tool_call_id is None:
            error_msg = "append_to_file 状态不完整，缺少路径或ID。"
            debug_log(error_msg)
            result["error"] = error_msg
            result["tool_content"] = json.dumps({
                "success": False,
                "error": error_msg
            }, ensure_ascii=False)
            pending_append = None
            return result
        
        if start_idx is None:
            error_msg = f"未检测到格式正确的开始标识 {start_marker}。"
            debug_log(error_msg)
            result["error"] = error_msg
            result["tool_content"] = json.dumps({
                "success": False,
                "path": path,
                "error": error_msg
            }, ensure_ascii=False)
            pending_append = None
            return result
        
        forced = False
        if end_idx is None:
            forced = True
            # 查找下一个<<<，否则使用整个缓冲结尾
            remaining = buffer[start_idx:]
            next_marker = remaining.find("<<<", len(end_marker))
            if next_marker != -1:
                end_idx = start_idx + next_marker
            else:
                end_idx = len(buffer)
        
        content = buffer[start_idx:end_idx]
        if content.startswith('\n'):
            content = content[1:]
        
        if not content:
            error_msg = "未检测到需要追加的内容，请严格按照<<<APPEND:path>>>...<<<END_APPEND>>>格式输出。"
            debug_log(error_msg)
            result["error"] = error_msg
            result["forced"] = forced
            result["tool_content"] = json.dumps({
                "success": False,
                "path": path,
                "error": error_msg
            }, ensure_ascii=False)
            pending_append = None
            return result
        
        assistant_message_lines = []
        if start_marker:
            assistant_message_lines.append(start_marker)
        assistant_message_lines.append(content)
        if not forced and end_marker:
            assistant_message_lines.append(end_marker)
        assistant_message_text = "\n".join(assistant_message_lines)
        result["assistant_content"] = assistant_message_text
        assistant_metadata = {
            "append_payload": {
                "path": path,
                "tool_call_id": tool_call_id,
                "forced": forced,
                "has_end_marker": not forced
            }
        }
        result["assistant_metadata"] = assistant_metadata
        
        write_result = web_terminal.file_manager.append_file(path, content)
        if write_result.get("success"):
            bytes_written = len(content.encode('utf-8'))
            line_count = content.count('\n')
            if content and not content.endswith('\n'):
                line_count += 1
            
            summary = f"已向 {path} 追加 {line_count} 行（{bytes_written} 字节）"
            if forced:
                summary += "。未检测到 <<<END_APPEND>>> 标记，系统已在流结束处完成写入。如内容未完成，请重新调用 append_to_file 并按标准格式补充；如已完成，可继续后续步骤。"
            
            result.update({
                "success": True,
                "summary": summary,
                "summary_message": summary,
                "forced": forced,
                "lines": line_count,
                "bytes": bytes_written,
                "appended_content": content,
                "tool_content": json.dumps({
                    "success": True,
                    "path": path,
                    "lines": line_count,
                    "bytes": bytes_written,
                    "forced": forced,
                    "message": summary,
                    "finish_reason": finish_reason
                }, ensure_ascii=False)
            })
            
            assistant_meta_payload = result["assistant_metadata"]["append_payload"]
            assistant_meta_payload["lines"] = line_count
            assistant_meta_payload["bytes"] = bytes_written
            assistant_meta_payload["success"] = True
            
            summary_payload = {
                "success": True,
                "path": path,
                "lines": line_count,
                "bytes": bytes_written,
                "forced": forced,
                "message": summary
            }
            
            if display_id:
                sender('update_action', {
                    'id': display_id,
                    'status': 'completed',
                    'result': summary_payload,
                    'preparing_id': tool_call_id,
                    'message': summary
                })
            
            # 更新聚焦文件内容
            if path in web_terminal.focused_files:
                refreshed = web_terminal.file_manager.read_file(path)
                if refreshed.get("success"):
                    web_terminal.focused_files[path] = refreshed["content"]
                    debug_log(f"聚焦文件已刷新: {path}")
            
            debug_log(f"追加写入完成: {summary}")
        else:
            error_msg = write_result.get("error", "追加写入失败")
            result.update({
                "error": error_msg,
                "summary_message": error_msg,
                "forced": forced,
                "appended_content": content,
                "tool_content": json.dumps({
                    "success": False,
                    "path": path,
                    "error": error_msg,
                    "finish_reason": finish_reason
                }, ensure_ascii=False)
            })
            debug_log(f"追加写入失败: {error_msg}")
            
            if result["assistant_metadata"]:
                assistant_meta_payload = result["assistant_metadata"]["append_payload"]
                assistant_meta_payload["lines"] = content.count('\n') + (0 if content.endswith('\n') or not content else 1)
                assistant_meta_payload["bytes"] = len(content.encode('utf-8'))
                assistant_meta_payload["success"] = False
            
            failure_payload = {
                "success": False,
                "path": path,
                "error": error_msg,
                "forced": forced
            }
            
            if display_id:
                sender('update_action', {
                    'id': display_id,
                    'status': 'completed',
                    'result': failure_payload,
                    'preparing_id': tool_call_id,
                    'message': error_msg
                })
        
        pending_append = None
        append_probe_buffer = ""
        if hasattr(web_terminal, "pending_append_request"):
            web_terminal.pending_append_request = None
        return result
    
    async def finalize_pending_modify(response_text: str, stream_completed: bool, finish_reason: str = None) -> Dict:
        """在流式输出结束后处理修改写入"""
        nonlocal pending_modify, modify_probe_buffer
        
        result = {
            "handled": False,
            "success": False,
            "path": None,
            "tool_call_id": None,
            "display_id": None,
            "total_blocks": 0,
            "completed_blocks": [],
            "failed_blocks": [],
            "forced": False,
            "details": [],
            "error": None,
            "assistant_content": response_text,
            "assistant_metadata": None,
            "tool_content": None,
            "summary_message": None,
            "finish_reason": finish_reason
        }
        
        if not pending_modify:
            return result
        
        state = pending_modify
        path = state.get("path")
        tool_call_id = state.get("tool_call_id")
        display_id = state.get("display_id")
        start_marker = state.get("start_marker")
        end_marker = state.get("end_marker")
        buffer = state.get("buffer", "")
        raw_buffer = state.get("raw_buffer", "")
        end_index = state.get("end_index")
        
        result.update({
            "handled": True,
            "path": path,
            "tool_call_id": tool_call_id,
            "display_id": display_id
        })
        
        if not state.get("start_seen"):
            error_msg = "未检测到格式正确的 <<<MODIFY:path>>> 标记。"
            debug_log(error_msg)
            result["error"] = error_msg
            result["summary_message"] = error_msg
            result["tool_content"] = json.dumps({
                "success": False,
                "path": path,
                "error": error_msg,
                "finish_reason": finish_reason
            }, ensure_ascii=False)
            if hasattr(web_terminal, "pending_modify_request"):
                web_terminal.pending_modify_request = None
            pending_modify = None
            modify_probe_buffer = ""
            return result
        
        forced = end_index is None
        apply_text = buffer if forced else buffer[:end_index]
        raw_content = raw_buffer if forced else raw_buffer[:len(start_marker) + end_index + len(end_marker)]
        if raw_content:
            result["assistant_content"] = raw_content
        
        blocks_info = []
        block_reports = {}
        detected_indices = set()
        block_pattern = re.compile(r"\[replace:(\d+)\](.*?)\[/replace\]", re.DOTALL)
        
        def extract_segment(body: str, tag: str):
            marker = f"<<{tag}>>"
            end_tag = "<<END>>"
            start_pos = body.find(marker)
            if start_pos == -1:
                return None, f"缺少 {marker}"
            start_pos += len(marker)
            if body[start_pos:start_pos+2] == "\r\n":
                start_pos += 2
            elif body[start_pos:start_pos+1] == "\n":
                start_pos += 1
            end_pos = body.find(end_tag, start_pos)
            if end_pos == -1:
                return None, f"缺少 {end_tag}"
            segment = body[start_pos:end_pos]
            return segment, None
        
        for match in block_pattern.finditer(apply_text):
            try:
                index = int(match.group(1))
            except ValueError:
                continue
            body = match.group(2)
            if index in detected_indices:
                continue
            detected_indices.add(index)
            block_reports[index] = {
                "index": index,
                "status": "pending",
                "reason": None,
                "removed_lines": 0,
                "added_lines": 0
            }
            old_content, old_error = extract_segment(body, "OLD")
            new_content, new_error = extract_segment(body, "NEW")
            if old_error or new_error:
                reason = old_error or new_error
                block_reports[index]["status"] = "failed"
                block_reports[index]["reason"] = reason
            blocks_info.append({
                "index": index,
                "old": old_content,
                "new": new_content,
                "error": old_error or new_error
            })
        
        total_blocks = len(blocks_info)
        result["total_blocks"] = total_blocks
        if forced:
            debug_log("未检测到 <<<END_MODIFY>>>，将在流结束处执行已识别的修改块。")
            result["forced"] = True
        
        blocks_to_apply = [
            {"index": block["index"], "old": block["old"], "new": block["new"]}
            for block in blocks_info
            if block["error"] is None and block["old"] is not None and block["new"] is not None
        ]
        
        # 记录格式残缺的块
        for block in blocks_info:
            if block["error"]:
                idx = block["index"]
                block_reports[idx]["status"] = "failed"
                block_reports[idx]["reason"] = block["error"]
        
        apply_result = {}
        if blocks_to_apply:
            apply_result = web_terminal.file_manager.apply_modify_blocks(path, blocks_to_apply)
        else:
            apply_result = {"success": False, "completed": [], "failed": [], "results": [], "write_performed": False, "error": None}
        
        block_result_map = {item["index"]: item for item in apply_result.get("results", [])}
        
        for block in blocks_info:
            idx = block["index"]
            report = block_reports.get(idx)
            if report is None:
                continue
            if report["status"] == "failed":
                continue
            block_apply = block_result_map.get(idx)
            if not block_apply:
                report["status"] = "failed"
                report["reason"] = "未执行，可能未找到匹配原文"
                continue
            status = block_apply.get("status")
            report["removed_lines"] = block_apply.get("removed_lines", 0)
            report["added_lines"] = block_apply.get("added_lines", 0)
            if status == "success":
                report["status"] = "completed"
            elif status == "not_found":
                report["status"] = "failed"
                report["reason"] = block_apply.get("reason") or "未找到匹配的原文"
            else:
                report["status"] = "failed"
                report["reason"] = block_apply.get("reason") or "替换失败"
        
        completed_blocks = sorted([idx for idx, rep in block_reports.items() if rep["status"] == "completed"])
        failed_blocks = sorted([idx for idx, rep in block_reports.items() if rep["status"] != "completed"])
        
        result["completed_blocks"] = completed_blocks
        result["failed_blocks"] = failed_blocks
        result["details"] = sorted(block_reports.values(), key=lambda x: x["index"])
        
        summary_parts = []
        if total_blocks == 0:
            summary_parts.append("未检测到有效的修改块，未执行任何修改。")
        else:
            if not completed_blocks and failed_blocks:
                summary_parts.append(f"共检测到 {total_blocks} 个修改块，全部未执行。")
            elif completed_blocks and not failed_blocks:
                summary_parts.append(f"共 {total_blocks} 个修改块全部完成。")
            else:
                summary_parts.append(
                    f"共检测到 {total_blocks} 个修改块，其中成功 {len(completed_blocks)} 个，失败 {len(failed_blocks)} 个。"
                )
        if forced:
            summary_parts.append("未检测到 <<<END_MODIFY>>> 标记，系统已在流结束处执行补丁。")
        if apply_result.get("error"):
            summary_parts.append(apply_result["error"])
        
        summary_message = " ".join(summary_parts).strip()
        result["summary_message"] = summary_message
        result["success"] = bool(completed_blocks) and not failed_blocks and apply_result.get("error") is None
        
        tool_payload = {
            "success": result["success"],
            "path": path,
            "total_blocks": total_blocks,
            "completed": completed_blocks,
            "failed": [
                {
                    "index": rep["index"],
                    "reason": rep.get("reason")
                }
                for rep in result["details"] if rep["status"] != "completed"
            ],
            "forced": forced,
            "message": summary_message,
            "finish_reason": finish_reason,
            "details": result["details"]
        }
        if apply_result.get("error"):
            tool_payload["error"] = apply_result["error"]
        
        result["tool_content"] = json.dumps(tool_payload, ensure_ascii=False)
        result["assistant_metadata"] = {
            "modify_payload": {
                "path": path,
                "total_blocks": total_blocks,
                "completed": completed_blocks,
                "failed": failed_blocks,
                "forced": forced,
                "details": result["details"]
            }
        }
        
        if display_id:
            sender('update_action', {
                'id': display_id,
                'status': 'completed' if result["success"] else 'failed',
                'result': tool_payload,
                'preparing_id': tool_call_id,
                'message': summary_message
            })
        
        if path in web_terminal.focused_files and tool_payload.get("success"):
            refreshed = web_terminal.file_manager.read_file(path)
            if refreshed.get("success"):
                web_terminal.focused_files[path] = refreshed["content"]
                debug_log(f"聚焦文件已刷新: {path}")
        
        pending_modify = None
        modify_probe_buffer = ""
        if hasattr(web_terminal, "pending_modify_request"):
            web_terminal.pending_modify_request = None
        return result
    
    for iteration in range(max_iterations):
        total_iterations += 1
        debug_log(f"\n--- 迭代 {iteration + 1}/{max_iterations} 开始 ---")
        
        # 检查是否超过总工具调用限制
        if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
            debug_log(f"已达到最大工具调用次数限制 ({MAX_TOTAL_TOOL_CALLS})")
            sender('system_message', {
                'content': f'⚠️ 已达到最大工具调用次数限制 ({MAX_TOTAL_TOOL_CALLS})，任务结束。'
            })
            break
        
        # === 修改：每次API调用前都计算输入token ===
        try:
            input_tokens = web_terminal.context_manager.calculate_input_tokens(messages, tools)
            debug_log(f"第{iteration + 1}次API调用输入token: {input_tokens}")
            
            # 更新输入token统计
            web_terminal.context_manager.update_token_statistics(input_tokens, 0)
        except Exception as e:
            debug_log(f"输入token统计失败: {e}")
        
        full_response = ""
        tool_calls = []
        current_thinking = ""
        detected_tools = {}
        
        # 状态标志
        in_thinking = False
        thinking_started = False
        thinking_ended = False
        text_started = False
        text_has_content = False
        text_streaming = False
        
        # 计数器
        chunk_count = 0
        reasoning_chunks = 0
        content_chunks = 0
        tool_chunks = 0
        append_break_triggered = False
        append_result = {"handled": False}
        modify_break_triggered = False
        modify_result = {"handled": False}
        last_finish_reason = None
        
        # 获取是否显示思考
        should_show_thinking = web_terminal.api_client.get_current_thinking_mode()
        debug_log(f"思考模式: {should_show_thinking}")
        
        print(f"[API] 第{iteration + 1}次调用 (总工具调用: {total_tool_calls}/{MAX_TOTAL_TOOL_CALLS})")
        
        # 收集流式响应
        async for chunk in web_terminal.api_client.chat(messages, tools, stream=True):
            chunk_count += 1
            
            # 检查停止标志
            client_stop_info = stop_flags.get(client_sid)
            if client_stop_info:
                stop_requested = client_stop_info.get('stop', False) if isinstance(client_stop_info, dict) else client_stop_info
                if stop_requested:
                    debug_log(f"检测到停止请求，中断流处理")
                    if pending_append:
                        append_result = await finalize_pending_append(full_response, False, finish_reason="user_stop")
                        break
                    if pending_modify:
                        modify_result = await finalize_pending_modify(full_response, False, finish_reason="user_stop")
                        break
            
            if "choices" not in chunk:
                debug_log(f"Chunk {chunk_count}: 无choices字段")
                continue
                
            choice = chunk["choices"][0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                last_finish_reason = finish_reason
            
            # 处理思考内容
            if "reasoning_content" in delta:
                reasoning_content = delta["reasoning_content"]
                if reasoning_content:
                    reasoning_chunks += 1
                    debug_log(f"  思考内容 #{reasoning_chunks}: {len(reasoning_content)} 字符")
                    
                    if should_show_thinking:
                        if not thinking_started:
                            in_thinking = True
                            thinking_started = True
                            sender('thinking_start', {})
                            await asyncio.sleep(0.05)
                        
                        current_thinking += reasoning_content
                        sender('thinking_chunk', {'content': reasoning_content})
            
            # 处理正常内容
            if "content" in delta:
                content = delta["content"]
                if content:
                    content_chunks += 1
                    debug_log(f"  正式内容 #{content_chunks}: {repr(content[:100] if content else 'None')}")
                    
                    # 通过文本内容提前检测工具调用意图
                    if not detected_tools:
                        # 检测常见的工具调用模式
                        tool_patterns = [
                            (r'(创建|新建|生成).*(文件|file)', 'create_file'),
                            (r'(读取|查看|打开).*(文件|file)', 'read_file'),
                            (r'(修改|编辑|更新).*(文件|file)', 'modify_file'),
                            (r'(删除|移除).*(文件|file)', 'delete_file'),
                            (r'(搜索|查找|search)', 'web_search'),
                            (r'(执行|运行).*(Python|python|代码)', 'run_python'),
                            (r'(执行|运行).*(命令|command)', 'run_command'),
                            (r'(等待|sleep|延迟)', 'sleep'),
                            (r'(聚焦|focus).*(文件|file)', 'focus_file'),
                            (r'(终端|terminal|会话|session)', 'terminal_session'),
                        ]
                        
                        for pattern, tool_name in tool_patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                early_tool_id = f"early_{tool_name}_{time.time()}"
                                if early_tool_id not in detected_tools:
                                    sender('tool_hint', {
                                        'id': early_tool_id,
                                        'name': tool_name,
                                        'message': f'检测到可能需要调用 {tool_name}...',
                                        'confidence': 'low'
                                    })
                                    detected_tools[early_tool_id] = tool_name
                                    debug_log(f"    ⚡ 提前检测到工具意图: {tool_name}")
                                    break
                    
                    if in_thinking and not thinking_ended:
                        in_thinking = False
                        thinking_ended = True
                        sender('thinking_end', {'full_content': current_thinking})
                        await asyncio.sleep(0.1)
                        
                        # ===== 增量保存：保存思考内容 =====
                        if current_thinking and not has_saved_thinking and is_first_iteration:
                            thinking_content = f"<think>\n{current_thinking}\n</think>"
                            web_terminal.context_manager.add_conversation("assistant", thinking_content)
                            has_saved_thinking = True
                            debug_log(f"💾 增量保存：思考内容 ({len(current_thinking)} 字符)")
                    
                    if pending_modify:
                        if not pending_modify.get("start_seen"):
                            probe_buffer = pending_modify.get("probe_buffer", "") + content
                            if len(probe_buffer) > 10000:
                                probe_buffer = probe_buffer[-10000:]
                            marker = pending_modify.get("start_marker")
                            marker_index = probe_buffer.find(marker)
                            if marker_index == -1:
                                pending_modify["probe_buffer"] = probe_buffer
                                continue
                            after_marker = marker_index + len(marker)
                            remainder = probe_buffer[after_marker:]
                            pending_modify["buffer"] = remainder
                            pending_modify["raw_buffer"] = marker + remainder
                            pending_modify["start_seen"] = True
                            pending_modify["detected_blocks"] = set()
                            pending_modify["probe_buffer"] = ""
                            if pending_modify.get("display_id"):
                                sender('update_action', {
                                    'id': pending_modify["display_id"],
                                    'status': 'running',
                                    'preparing_id': pending_modify.get("tool_call_id"),
                                    'message': f"正在修改 {pending_modify['path']}..."
                                })
                        else:
                            pending_modify["buffer"] += content
                            pending_modify["raw_buffer"] += content
                        
                        if pending_modify.get("start_seen"):
                            block_text = pending_modify["buffer"]
                            for match in re.finditer(r"\[replace:(\d+)\]", block_text):
                                try:
                                    block_index = int(match.group(1))
                                except ValueError:
                                    continue
                                detected_blocks = pending_modify.setdefault("detected_blocks", set())
                                if block_index not in detected_blocks:
                                    detected_blocks.add(block_index)
                                    if pending_modify.get("display_id"):
                                        sender('update_action', {
                                            'id': pending_modify["display_id"],
                                            'status': 'running',
                                            'preparing_id': pending_modify.get("tool_call_id"),
                                            'message': f"正在对 {pending_modify['path']} 进行第 {block_index} 处修改..."
                                        })
                        
                        if pending_modify.get("start_seen"):
                            end_pos = pending_modify["buffer"].find(pending_modify["end_marker"])
                            if end_pos != -1:
                                pending_modify["end_index"] = end_pos
                                modify_break_triggered = True
                                debug_log("检测到<<<END_MODIFY>>>，即将终止流式输出并应用修改")
                                break
                        continue
                    else:
                        modify_probe_buffer += content
                        if len(modify_probe_buffer) > 10000:
                            modify_probe_buffer = modify_probe_buffer[-10000:]
                        
                        marker_match = re.search(r"<<<MODIFY:\s*([\s\S]*?)>>>", modify_probe_buffer)
                        if marker_match:
                            detected_raw_path = marker_match.group(1)
                            detected_path = detected_raw_path.strip()
                            marker_full = marker_match.group(0)
                            after_marker_index = modify_probe_buffer.find(marker_full) + len(marker_full)
                            remainder = modify_probe_buffer[after_marker_index:]
                            modify_probe_buffer = ""
                            
                            if not detected_path:
                                debug_log("检测到 MODIFY 起始标记但路径为空，忽略。")
                                continue
                            
                            pending_modify = {
                                "path": detected_path,
                                "tool_call_id": None,
                                "buffer": remainder,
                                "raw_buffer": marker_full + remainder,
                                "start_marker": marker_full,
                                "end_marker": "<<<END_MODIFY>>>",
                                "start_seen": True,
                                "end_index": None,
                                "display_id": None,
                                "detected_blocks": set()
                            }
                            if hasattr(web_terminal, "pending_modify_request"):
                                web_terminal.pending_modify_request = {"path": detected_path}
                            debug_log(f"直接检测到modify起始标记，构建修改缓冲: {detected_path}")
                            
                            end_pos = pending_modify["buffer"].find(pending_modify["end_marker"])
                            if end_pos != -1:
                                pending_modify["end_index"] = end_pos
                                modify_break_triggered = True
                                debug_log("检测到<<<END_MODIFY>>>，即将终止流式输出并应用修改")
                                break
                            continue
                    
                    if pending_append:
                        pending_append["buffer"] += content
                        
                        if pending_append.get("content_start") is None:
                            marker_index = pending_append["buffer"].find(pending_append["start_marker"])
                            if marker_index != -1:
                                pending_append["content_start"] = marker_index + len(pending_append["start_marker"])
                                debug_log(f"检测到追加起始标识: {pending_append['start_marker']}")
                        
                        if pending_append.get("content_start") is not None:
                            end_index = pending_append["buffer"].find(
                                pending_append["end_marker"],
                                pending_append["content_start"]
                            )
                            if end_index != -1:
                                pending_append["end_index"] = end_index
                                append_break_triggered = True
                                debug_log("检测到<<<END_APPEND>>>，即将终止流式输出并写入文件")
                                break
                        
                        # 继续累积追加内容
                        continue
                    else:
                        append_probe_buffer += content
                        # 限制缓冲区大小防止过长
                        if len(append_probe_buffer) > 10000:
                            append_probe_buffer = append_probe_buffer[-10000:]

                        marker_match = re.search(r"<<<APPEND:\s*([\s\S]*?)>>>", append_probe_buffer)
                        if marker_match:
                            detected_raw_path = marker_match.group(1)
                            detected_path = detected_raw_path.strip()
                            if not detected_path:
                                append_probe_buffer = append_probe_buffer[marker_match.end():]
                                continue
                            marker_full = marker_match.group(0)
                            after_marker_index = append_probe_buffer.find(marker_full) + len(marker_full)
                            remainder = append_probe_buffer[after_marker_index:]
                            append_probe_buffer = ""
                            pending_append = {
                                "path": detected_path,
                                "tool_call_id": None,
                                "buffer": remainder,
                                "start_marker": marker_full,
                                "end_marker": "<<<END_APPEND>>>",
                                "content_start": 0,
                                "end_index": None,
                                "display_id": None
                            }
                            if hasattr(web_terminal, "pending_append_request"):
                                web_terminal.pending_append_request = {"path": detected_path}
                            debug_log(f"直接检测到append起始标记，构建追加缓冲: {detected_path}")
                            # 检查是否立即包含结束标记
                            if pending_append["buffer"]:
                                end_index = pending_append["buffer"].find(pending_append["end_marker"], pending_append["content_start"])
                                if end_index != -1:
                                    pending_append["end_index"] = end_index
                                    append_break_triggered = True
                                    debug_log("检测到<<<END_APPEND>>>，即将终止流式输出并写入文件")
                                    break
                            continue
                    
                    if not text_started:
                        text_started = True
                        text_streaming = True
                        sender('text_start', {})
                        await asyncio.sleep(0.05)
                    
                    if not pending_append:
                        full_response += content
                        accumulated_response += content
                        text_has_content = True
                        sender('text_chunk', {'content': content})
            
            # 收集工具调用 - 实时发送准备状态
            if "tool_calls" in delta:
                tool_chunks += 1
                for tc in delta["tool_calls"]:
                    found = False
                    for existing in tool_calls:
                        if existing.get("index") == tc.get("index"):
                            if "function" in tc and "arguments" in tc["function"]:
                                existing["function"]["arguments"] += tc["function"]["arguments"]
                            found = True
                            break
                    
                    if not found and tc.get("id"):
                        tool_id = tc["id"]
                        tool_name = tc.get("function", {}).get("name", "")
                        
                        # 新工具检测到，立即发送准备事件
                        if tool_id not in detected_tools and tool_name:
                            detected_tools[tool_id] = tool_name
                            
                            # 立即发送工具准备中事件
                            sender('tool_preparing', {
                                'id': tool_id,
                                'name': tool_name,
                                'message': f'准备调用 {tool_name}...'
                            })
                            debug_log(f"    发送工具准备事件: {tool_name}")
                            await asyncio.sleep(0.1)
                        
                        tool_calls.append({
                            "id": tool_id,
                            "index": tc.get("index"),
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tc.get("function", {}).get("arguments", "")
                            }
                        })
                        debug_log(f"    新工具: {tool_name}")
        
        # 检查是否被停止
        client_stop_info = stop_flags.get(client_sid)
        if client_stop_info:
            stop_requested = client_stop_info.get('stop', False) if isinstance(client_stop_info, dict) else client_stop_info
            if stop_requested:
                debug_log("任务在流处理完成后检测到停止状态")
                return
        
        # === API响应完成后只计算输出token ===
        try:
            # 计算AI输出的token（包括thinking、文本内容、工具调用）
            ai_output_content = ""
            if current_thinking:
                ai_output_content += f"<think>\n{current_thinking}\n</think>\n"
            if full_response:
                ai_output_content += full_response
            if tool_calls:
                ai_output_content += json.dumps(tool_calls, ensure_ascii=False)
            
            if ai_output_content.strip():
                output_tokens = web_terminal.context_manager.calculate_output_tokens(ai_output_content)
                debug_log(f"第{iteration + 1}次API调用输出token: {output_tokens}")
                
                # 只更新输出token统计
                web_terminal.context_manager.update_token_statistics(0, output_tokens)
            else:
                debug_log("没有AI输出内容，跳过输出token统计")
        except Exception as e:
            debug_log(f"输出token统计失败: {e}")
        
        # 流结束后的处理
        debug_log(f"\n流结束统计:")
        debug_log(f"  总chunks: {chunk_count}")
        debug_log(f"  思考chunks: {reasoning_chunks}")
        debug_log(f"  内容chunks: {content_chunks}")
        debug_log(f"  工具chunks: {tool_chunks}")
        debug_log(f"  收集到的思考: {len(current_thinking)} 字符")
        debug_log(f"  收集到的正文: {len(full_response)} 字符")
        debug_log(f"  收集到的工具: {len(tool_calls)} 个")
        
        if not append_result["handled"] and pending_append:
            append_result = await finalize_pending_append(full_response, True, finish_reason=last_finish_reason)
        if not modify_result["handled"] and pending_modify:
            modify_result = await finalize_pending_modify(full_response, True, finish_reason=last_finish_reason)
        
        # 结束未完成的流
        if in_thinking and not thinking_ended:
            sender('thinking_end', {'full_content': current_thinking})
            await asyncio.sleep(0.1)
            
            # 保存思考内容
            if current_thinking and not has_saved_thinking and is_first_iteration:
                thinking_content = f"<think>\n{current_thinking}\n</think>"
                web_terminal.context_manager.add_conversation("assistant", thinking_content)
                has_saved_thinking = True
                debug_log(f"💾 增量保存：延迟思考内容 ({len(current_thinking)} 字符)")
        
        # 确保text_end事件被发送
        if text_started and text_has_content and not append_result["handled"] and not modify_result["handled"]:
            debug_log(f"发送text_end事件，完整内容长度: {len(full_response)}")
            sender('text_end', {'full_content': full_response})
            await asyncio.sleep(0.1)
            text_streaming = False
            
            # ===== 增量保存：保存当前轮次的文本内容 =====
            if full_response.strip():
                web_terminal.context_manager.add_conversation("assistant", full_response)
                debug_log(f"💾 增量保存：文本内容 ({len(full_response)} 字符)")
        
        if append_result["handled"]:
            append_metadata = append_result.get("assistant_metadata")
            append_content_text = append_result.get("assistant_content")
            if append_content_text:
                web_terminal.context_manager.add_conversation(
                    "assistant",
                    append_content_text,
                    metadata=append_metadata
                )
                debug_log("💾 增量保存：追加正文快照")
                
                payload_info = append_metadata.get("append_payload") if append_metadata else {}
                sender('append_payload', {
                    'path': payload_info.get("path") or append_result.get("path"),
                    'forced': payload_info.get("forced", False),
                    'lines': payload_info.get("lines"),
                    'bytes': payload_info.get("bytes"),
                    'tool_call_id': payload_info.get("tool_call_id") or append_result.get("tool_call_id"),
                    'success': payload_info.get("success", append_result.get("success", False))
                })
            
            if append_result["tool_content"]:
                tool_call_id = append_result.get("tool_call_id") or f"append_{int(time.time() * 1000)}"
                web_terminal.context_manager.add_conversation(
                    "tool",
                    append_result["tool_content"],
                    tool_call_id=tool_call_id,
                    name="append_to_file"
                )
                append_result["tool_call_id"] = tool_call_id
                debug_log("💾 增量保存：append_to_file 工具结果")
            
            finish_reason = append_result.get("finish_reason")
            path_for_prompt = append_result.get("path")
            need_follow_prompt = (
                finish_reason == "length" or
                append_result.get("forced") or
                not append_result.get("success")
            )

            if need_follow_prompt and path_for_prompt:
                prompt_lines = [
                    f"当前必须先完成对 {path_for_prompt} 的写入任务。"
                ]
                if finish_reason == "length":
                    prompt_lines.append(
                        "上一次输出已达到系统的单次输出上限，已有内容已写入文件。"
                    )
                if append_result.get("forced"):
                    prompt_lines.append(
                        "刚才的输出缺少 <<<END_APPEND>>> 标记，系统已在流结束处写入。"
                    )
                if not append_result.get("success"):
                    prompt_lines.append("系统未检测到合法的追加标识。")
                prompt_lines.append("请按以下格式继续输出（标记需独立成行）：")
                prompt_lines.append(f"<<<APPEND:{path_for_prompt}>>>")
                prompt_lines.append("...填写剩余正文，如内容已完成可留空...")
                prompt_lines.append("<<<END_APPEND>>>")
                prompt_lines.append("完成追加之前禁止执行其他操作或再次调用 append_to_file。")
                follow_prompt = "\n".join(prompt_lines)
                messages.append({
                    "role": "system",
                    "content": follow_prompt
                })
                web_terminal.context_manager.add_conversation("system", follow_prompt)
                debug_log("已注入追加任务提示")

            if not append_result.get("success"):
                sender('system_message', {
                    'content': f'⚠️ 追加写入失败：{append_result.get("error")}'
                })
            
            # 重置文本流状态，避免后续错误处理
            text_streaming = False
            text_started = False
            text_has_content = False
            full_response = ""
        
        if modify_result["handled"]:
            modify_metadata = modify_result.get("assistant_metadata")
            modify_content_text = modify_result.get("assistant_content")
            if modify_content_text:
                web_terminal.context_manager.add_conversation(
                    "assistant",
                    modify_content_text,
                    metadata=modify_metadata
                )
                debug_log("💾 增量保存：修改正文快照")
                
                payload_info = modify_metadata.get("modify_payload") if modify_metadata else {}
                sender('modify_payload', {
                    'path': payload_info.get("path") or modify_result.get("path"),
                    'total': payload_info.get("total_blocks") or modify_result.get("total_blocks"),
                    'completed': payload_info.get("completed") or modify_result.get("completed_blocks"),
                    'failed': payload_info.get("failed") or modify_result.get("failed_blocks"),
                    'forced': payload_info.get("forced", modify_result.get("forced", False)),
                    'success': modify_result.get("success", False)
                })
            
            if modify_result["tool_content"]:
                tool_call_id = modify_result.get("tool_call_id") or f"modify_{int(time.time() * 1000)}"
                web_terminal.context_manager.add_conversation(
                    "tool",
                    modify_result["tool_content"],
                    tool_call_id=tool_call_id,
                    name="modify_file"
                )
                modify_result["tool_call_id"] = tool_call_id
                debug_log("💾 增量保存：modify_file 工具结果")
            
            path_for_prompt = modify_result.get("path")
            failed_blocks = modify_result.get("failed_blocks") or []
            need_follow_prompt = modify_result.get("forced") or bool(failed_blocks)
            
            if need_follow_prompt and path_for_prompt:
                prompt_lines = [
                    f"当前必须先完成对 {path_for_prompt} 的修改任务。"
                ]
                if modify_result.get("forced"):
                    prompt_lines.append(
                        "刚才的输出缺少 <<<END_MODIFY>>> 标记，系统已在流结束处执行已识别的补丁。"
                    )
                if failed_blocks:
                    failed_text = "、".join(str(idx) for idx in failed_blocks)
                    prompt_lines.append(f"以下修改未完成：第 {failed_text} 处。")
                prompt_lines.append("请重新输出完整补丁（标记独立成行，且 OLD/NEW 必须逐字匹配原代码，包含所有缩进和换行）：")
                prompt_lines.append(f"<<<MODIFY:{path_for_prompt}>>>")
                prompt_lines.append("[replace:序号]")
                prompt_lines.append("<<OLD>>")
                prompt_lines.append("...原文（必须逐字匹配，包含全部缩进、空格和换行）...")
                prompt_lines.append("<<END>>")
                prompt_lines.append("<<NEW>>")
                prompt_lines.append("...新内容，可留空表示清空，注意保持结构完整...")
                prompt_lines.append("<<END>>")
                prompt_lines.append("[/replace]")
                prompt_lines.append("<<<END_MODIFY>>>")
                follow_prompt = "\n".join(prompt_lines)
                messages.append({
                    "role": "system",
                    "content": follow_prompt
                })
                web_terminal.context_manager.add_conversation("system", follow_prompt)
                debug_log("已注入修改任务提示")

            if not modify_result.get("success"):
                error_message = modify_result.get("summary_message") or modify_result.get("error") or "修改操作未成功，请根据提示重新执行。"
                sender('system_message', {
                    'content': f'⚠️ 修改操作存在未完成的内容：{error_message}'
                })
            
            text_streaming = False
            text_started = False
            text_has_content = False
            full_response = ""
        
        # 保存思考内容（如果这是第一次迭代且有思考）
        if web_terminal.thinking_mode and web_terminal.api_client.current_task_first_call and current_thinking:
            web_terminal.api_client.current_task_thinking = current_thinking
            web_terminal.api_client.current_task_first_call = False
        
        # 检测是否有格式错误的工具调用
        if not tool_calls and full_response and AUTO_FIX_TOOL_CALL and not append_result["handled"] and not modify_result["handled"]:
            if detect_malformed_tool_call(full_response):
                auto_fix_attempts += 1
                
                if auto_fix_attempts <= AUTO_FIX_MAX_ATTEMPTS:
                    debug_log(f"检测到格式错误的工具调用，尝试自动修复 (尝试 {auto_fix_attempts}/{AUTO_FIX_MAX_ATTEMPTS})")
                    
                    fix_message = "你使用了错误的格式输出工具调用。请使用正确的工具调用格式而不是直接输出JSON。根据当前进度继续执行任务。"
                    
                    sender('system_message', {
                        'content': f'⚠️ 自动修复: {fix_message}'
                    })
                    
                    messages.append({
                        "role": "user",
                        "content": fix_message
                    })
                    
                    await asyncio.sleep(1)
                    continue
                else:
                    debug_log(f"自动修复尝试已达上限 ({AUTO_FIX_MAX_ATTEMPTS})")
                    sender('system_message', {
                        'content': f'⌘ 工具调用格式错误，自动修复失败。请手动检查并重试。'
                    })
                    break
        
        # 构建助手消息（用于API继续对话）
        assistant_content_parts = []
        
        if current_thinking:
            assistant_content_parts.append(f"<think>\n{current_thinking}\n</think>")
        
        if full_response:
            assistant_content_parts.append(full_response)
        elif append_result["handled"] and append_result["assistant_content"]:
            assistant_content_parts.append(append_result["assistant_content"])
        elif modify_result["handled"] and modify_result.get("assistant_content"):
            assistant_content_parts.append(modify_result["assistant_content"])
        
        assistant_content = "\n".join(assistant_content_parts) if assistant_content_parts else ""
        
        # 添加到消息历史（用于API继续对话，不保存到文件）
        assistant_message = {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls
        }
        
        messages.append(assistant_message)
        
        if append_result["handled"] and append_result.get("tool_content"):
            tool_call_id = append_result.get("tool_call_id") or f"append_{int(time.time() * 1000)}"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": "append_to_file",
                "content": append_result["tool_content"]
            })
            debug_log("已将 append_to_file 工具结果追加到对话上下文")
        if modify_result["handled"] and modify_result.get("tool_content"):
            tool_call_id = modify_result.get("tool_call_id") or f"modify_{int(time.time() * 1000)}"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": "modify_file",
                "content": modify_result["tool_content"]
            })
            debug_log("已将 modify_file 工具结果追加到对话上下文")
        
        force_continue = append_result["handled"] or modify_result["handled"]
        if force_continue:
            if append_result["handled"]:
                debug_log("append_to_file 已处理，继续下一轮以让模型返回确认回复")
            elif modify_result["handled"]:
                debug_log("modify_file 已处理，继续下一轮以让模型返回确认回复")
            else:
                debug_log("补丁处理完成，继续下一轮以获取模型回复")
            continue

        if not tool_calls:
            debug_log("没有工具调用，结束迭代")
            break
        
        # 检查连续相同工具调用
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            
            if tool_name == last_tool_name:
                consecutive_same_tool[tool_name] += 1
                
                if consecutive_same_tool[tool_name] >= MAX_CONSECUTIVE_SAME_TOOL:
                    debug_log(f"警告: 连续调用相同工具 {tool_name} 已达 {MAX_CONSECUTIVE_SAME_TOOL} 次")
                    sender('system_message', {
                        'content': f'⚠️ 检测到重复调用 {tool_name} 工具 {MAX_CONSECUTIVE_SAME_TOOL} 次，可能存在循环。'
                    })
                    
                    if consecutive_same_tool[tool_name] >= MAX_CONSECUTIVE_SAME_TOOL + 2:
                        debug_log(f"终止: 工具 {tool_name} 调用次数过多")
                        sender('system_message', {
                            'content': f'⌘ 工具 {tool_name} 重复调用过多，任务终止。'
                        })
                        break
            else:
                consecutive_same_tool.clear()
                consecutive_same_tool[tool_name] = 1
            
            last_tool_name = tool_name
        
        # ===== 增量保存：保存工具调用信息 =====
        if tool_calls:
            # 保存assistant消息（只包含工具调用信息，内容为空）
            web_terminal.context_manager.add_conversation(
                "assistant",
                "",  # 空内容，只记录工具调用
                tool_calls
            )
            debug_log(f"💾 增量保存：工具调用信息 ({len(tool_calls)} 个工具)")
        
        # 更新统计
        total_tool_calls += len(tool_calls)
        
        # 执行每个工具
        for tool_call in tool_calls:
            # 检查停止标志
            client_stop_info = stop_flags.get(client_sid)
            if client_stop_info:
                stop_requested = client_stop_info.get('stop', False) if isinstance(client_stop_info, dict) else client_stop_info
                if stop_requested:
                    debug_log("在工具调用过程中检测到停止状态") 
                    return
            
            # 工具调用间隔控制
            current_time = time.time()
            if last_tool_call_time > 0:
                elapsed = current_time - last_tool_call_time
                if elapsed < TOOL_CALL_COOLDOWN:
                    await asyncio.sleep(TOOL_CALL_COOLDOWN - elapsed)
            last_tool_call_time = time.time()
            
            function_name = tool_call["function"]["name"]
            arguments_str = tool_call["function"]["arguments"]
            tool_call_id = tool_call["id"]
            

            debug_log(f"准备解析JSON，工具: {function_name}, 参数长度: {len(arguments_str)}")
            debug_log(f"JSON参数前200字符: {arguments_str[:200]}")
            debug_log(f"JSON参数后200字符: {arguments_str[-200:]}")
            
            # 使用改进的参数解析方法
            if hasattr(web_terminal, 'api_client') and hasattr(web_terminal.api_client, '_safe_tool_arguments_parse'):
                success, arguments, error_msg = web_terminal.api_client._safe_tool_arguments_parse(arguments_str, function_name)
                if not success:
                    debug_log(f"安全解析失败: {error_msg}")
                    sender('error', {'message': f'工具参数解析失败: {error_msg}'})
                    continue
                debug_log(f"使用安全解析成功，参数键: {list(arguments.keys())}")
            else:
                # 回退到带有基本修复逻辑的解析
                try:
                    arguments = json.loads(arguments_str) if arguments_str.strip() else {}
                    debug_log(f"直接JSON解析成功，参数键: {list(arguments.keys())}")
                except json.JSONDecodeError as e:
                    debug_log(f"原始JSON解析失败: {e}")
                    # 尝试基本的JSON修复
                    repaired_str = arguments_str.strip()
                    repair_attempts = []
                    
                    # 修复1: 未闭合字符串
                    if repaired_str.count('"') % 2 == 1:
                        repaired_str += '"'
                        repair_attempts.append("添加闭合引号")
                    
                    # 修复2: 未闭合JSON对象
                    if repaired_str.startswith('{') and not repaired_str.rstrip().endswith('}'):
                        repaired_str = repaired_str.rstrip() + '}'
                        repair_attempts.append("添加闭合括号")
                    
                    # 修复3: 截断的JSON（移除不完整的最后一个键值对）
                    if not repair_attempts:  # 如果前面的修复都没用上
                        last_comma = repaired_str.rfind(',')
                        if last_comma > 0:
                            repaired_str = repaired_str[:last_comma] + '}'
                            repair_attempts.append("移除不完整的键值对")
                    
                    # 尝试解析修复后的JSON
                    try:
                        arguments = json.loads(repaired_str)
                        debug_log(f"JSON修复成功: {', '.join(repair_attempts)}")
                        debug_log(f"修复后参数键: {list(arguments.keys())}")
                    except json.JSONDecodeError as repair_error:
                        debug_log(f"JSON修复也失败: {repair_error}")
                        debug_log(f"修复尝试: {repair_attempts}")
                        debug_log(f"修复后内容前100字符: {repaired_str[:100]}")
                        sender('error', {'message': f'工具参数解析失败: {e}'})
                        continue            
            
            debug_log(f"执行工具: {function_name} (ID: {tool_call_id})")
            
            # 发送工具开始事件
            tool_display_id = f"tool_{iteration}_{function_name}_{time.time()}"
            
            sender('tool_start', {
                'id': tool_display_id,
                'name': function_name,
                'arguments': arguments,
                'preparing_id': tool_call_id
            })
            
            await asyncio.sleep(0.3)
            start_time = time.time()
            
            # 执行工具
            tool_result = await web_terminal.handle_tool_call(function_name, arguments)
            debug_log(f"工具结果: {tool_result[:200]}...")
            
            execution_time = time.time() - start_time
            if execution_time < 1.5:
                await asyncio.sleep(1.5 - execution_time)
            
            # 更新工具状态
            try:
                result_data = json.loads(tool_result)
            except:
                result_data = {'output': tool_result}
            
            action_status = 'completed'
            action_message = None
            awaiting_flag = False
            
            if function_name == "append_to_file":
                if result_data.get("success") and result_data.get("awaiting_content"):
                    append_path = result_data.get("path") or arguments.get("path")
                    pending_append = {
                        "path": append_path,
                        "tool_call_id": tool_call_id,
                        "buffer": "",
                        "start_marker": f"<<<APPEND:{append_path}>>>",
                        "end_marker": "<<<END_APPEND>>>",
                        "content_start": None,
                        "end_index": None,
                        "display_id": tool_display_id
                    }
                    append_probe_buffer = ""
                    awaiting_flag = True
                    action_status = 'running'
                    action_message = f"正在向 {append_path} 追加内容..."
                    text_started = False
                    text_streaming = False
                    text_has_content = False
                    debug_log(f"append_to_file 等待输出: {append_path}")
                else:
                    debug_log("append_to_file 返回完成状态")
            elif function_name == "modify_file":
                if result_data.get("success") and result_data.get("awaiting_content"):
                    modify_path = result_data.get("path") or arguments.get("path")
                    pending_modify = {
                        "path": modify_path,
                        "tool_call_id": tool_call_id,
                        "buffer": "",
                        "raw_buffer": "",
                        "start_marker": f"<<<MODIFY:{modify_path}>>>",
                        "end_marker": "<<<END_MODIFY>>>",
                        "start_seen": False,
                        "end_index": None,
                        "display_id": tool_display_id,
                        "detected_blocks": set(),
                        "probe_buffer": ""
                    }
                    modify_probe_buffer = ""
                    if hasattr(web_terminal, "pending_modify_request"):
                        web_terminal.pending_modify_request = {"path": modify_path}
                    awaiting_flag = True
                    action_status = 'running'
                    action_message = f"正在修改 {modify_path}..."
                    text_started = False
                    text_streaming = False
                    text_has_content = False
                    debug_log(f"modify_file 等待输出: {modify_path}")
                else:
                    debug_log("modify_file 返回完成状态")
            
            update_payload = {
                'id': tool_display_id,
                'status': action_status,
                'result': result_data,
                'preparing_id': tool_call_id
            }
            if action_message:
                update_payload['message'] = action_message
            if awaiting_flag:
                update_payload['awaiting_content'] = True
            
            sender('update_action', update_payload)
            
            # 更新UI状态
            if function_name in ['focus_file', 'unfocus_file', 'modify_file', 'confirm_read_or_focus']:
                sender('focused_files_update', web_terminal.get_focused_files_info())
            
            if function_name in ['create_file', 'delete_file', 'rename_file', 'create_folder']:
                structure = web_terminal.context_manager.get_project_structure()
                sender('file_tree_update', structure)
            
            # ===== 增量保存：立即保存工具结果 =====
            try:
                result_data = json.loads(tool_result)
                if function_name == "read_file" and result_data.get("success"):
                    file_content = result_data.get("content", "")
                    tool_result_content = f"文件内容:\n```\n{file_content}\n```\n大小: {result_data.get('size')} 字节"
                else:
                    tool_result_content = tool_result
            except:
                tool_result_content = tool_result
            
            # 立即保存工具结果
            web_terminal.context_manager.add_conversation(
                "tool",
                tool_result_content,
                tool_call_id=tool_call_id,
                name=function_name
            )
            debug_log(f"💾 增量保存：工具结果 {function_name}")
            
            # 添加到消息历史（用于API继续对话）
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": function_name,
                "content": tool_result_content
            })
            
            await asyncio.sleep(0.2)
        
        # 标记不再是第一次迭代
        is_first_iteration = False
    
    # 最终统计
    debug_log(f"\n{'='*40}")
    debug_log(f"任务完成统计:")
    debug_log(f"  总迭代次数: {total_iterations}")
    debug_log(f"  总工具调用: {total_tool_calls}")
    debug_log(f"  自动修复尝试: {auto_fix_attempts}")
    debug_log(f"  累积响应: {len(accumulated_response)} 字符")
    debug_log(f"{'='*40}\n")
    
    # 发送完成事件
    sender('task_complete', {
        'total_iterations': total_iterations,
        'total_tool_calls': total_tool_calls,
        'auto_fix_attempts': auto_fix_attempts
    })
    
@socketio.on('send_command')
def handle_command(data):
    """处理系统命令"""
    command = data.get('command', '')
    
    if not web_terminal:
        emit('error', {'message': 'System not initialized'})
        return
    
    if command.startswith('/'):
        command = command[1:]
    
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()
    
    if cmd == "clear":
        web_terminal.context_manager.conversation_history.clear()
        if web_terminal.thinking_mode:
            web_terminal.api_client.start_new_task()
        emit('command_result', {
            'command': cmd,
            'success': True,
            'message': '对话已清除'
        })
    elif cmd == "status":
        status = web_terminal.get_status()
        # 添加终端状态
        if web_terminal.terminal_manager:
            terminal_status = web_terminal.terminal_manager.list_terminals()
            status['terminals'] = terminal_status
        emit('command_result', {
            'command': cmd,
            'success': True,
            'data': status
        })
    elif cmd == "terminals":
        # 列出终端会话
        if web_terminal.terminal_manager:
            result = web_terminal.terminal_manager.list_terminals()
            emit('command_result', {
                'command': cmd,
                'success': True,
                'data': result
            })
        else:
            emit('command_result', {
                'command': cmd,
                'success': False,
                'message': '终端系统未初始化'
            })
    else:
        emit('command_result', {
            'command': cmd,
            'success': False,
            'message': f'未知命令: {cmd}'
        })

@app.route('/api/conversations/<conversation_id>/token-statistics', methods=['GET'])
def get_conversation_token_statistics(conversation_id):
    """获取特定对话的token统计"""
    if not web_terminal:
        return jsonify({"error": "System not initialized"}), 503
    
    try:
        stats = web_terminal.context_manager.get_conversation_token_statistics(conversation_id)
        
        if stats:
            return jsonify({
                "success": True,
                "data": stats
            })
        else:
            return jsonify({
                "success": False,
                "error": "Conversation not found",
                "message": f"对话 {conversation_id} 不存在"
            }), 404
            
    except Exception as e:
        print(f"[API] 获取token统计错误: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "获取token统计时发生异常"
        }), 500


@app.route('/api/conversations/<conversation_id>/tokens', methods=['GET'])
def get_conversation_tokens(conversation_id):
    """获取对话的当前完整上下文token数（包含所有动态内容）"""
    try:
        # 获取当前聚焦文件状态
        focused_files = web_terminal.get_focused_files_info()
        
        # 获取当前终端内容
        terminal_content = ""
        if web_terminal.terminal_manager:
            terminal_content = web_terminal.terminal_manager.get_active_terminal_content()
        
        # 计算完整token
        tokens = web_terminal.context_manager.conversation_manager.calculate_conversation_tokens(
            conversation_id=conversation_id,
            context_manager=web_terminal.context_manager,
            focused_files=focused_files,
            terminal_content=terminal_content
        )
        
        return jsonify({
            "success": True,
            "data": tokens
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

def initialize_system(path: str, thinking_mode: bool = False):
    """初始化系统"""
    global web_terminal, project_path
    
    # 清空或创建调试日志
    with open(DEBUG_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"调试日志开始 - {datetime.now()}\n")
        f.write(f"项目路径: {path}\n")
        f.write(f"思考模式: {'思考模式' if thinking_mode else '快速模式'}\n")
        f.write(f"自动修复: {'开启' if AUTO_FIX_TOOL_CALL else '关闭'}\n")
        f.write(f"最大迭代: {MAX_ITERATIONS_PER_TASK}\n")
        f.write(f"最大工具调用: {MAX_TOTAL_TOOL_CALLS}\n")
        f.write("="*80 + "\n")
    
    print(f"[Init] 初始化Web系统...")
    print(f"[Init] 项目路径: {path}")
    print(f"[Init] 运行模式: {'思考模式（首次思考，后续快速）' if thinking_mode else '快速模式（无思考）'}")
    print(f"[Init] 自动修复: {'开启' if AUTO_FIX_TOOL_CALL else '关闭'}")
    print(f"[Init] 调试日志: {DEBUG_LOG_FILE}")
    
    project_path = path
    
    try:
        from config import CONVERSATIONS_DIR
        conversations_dir = Path(CONVERSATIONS_DIR)
        conversations_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Init] 对话存储目录: {conversations_dir}")
        
        # 创建WebTerminal
        web_terminal = WebTerminal(
            project_path=path,
            thinking_mode=thinking_mode,
            message_callback=terminal_broadcast
        )
        
        # 设置终端管理器的广播回调
        if web_terminal.terminal_manager:
            web_terminal.terminal_manager.broadcast = terminal_broadcast
            print(f"[Init] 终端管理器已配置，支持{web_terminal.terminal_manager.max_terminals}个会话")
        
        print(f"[Init] WebTerminal创建成功")
    except Exception as e:
        print(f"[Init] WebTerminal创建失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"{OUTPUT_FORMATS['success']} Web系统初始化完成")
    print(f"{OUTPUT_FORMATS['info']} 项目路径: {path}")
    print(f"{OUTPUT_FORMATS['info']} 访问 http://localhost:8091 开始使用")
    print(f"{OUTPUT_FORMATS['info']} 访问 http://localhost:8091/terminal 查看终端")
    print(f"{OUTPUT_FORMATS['info']} 调试日志文件: {DEBUG_LOG_FILE}")

def run_server(path: str, thinking_mode: bool = False, port: int = 8091):
    """运行Web服务器"""
    initialize_system(path, thinking_mode)
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
