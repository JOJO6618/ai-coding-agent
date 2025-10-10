// static/app-enhanced.js - 修复版，正确实现Token实时更新

// 等待所有资源加载完成
window.onload = function() {
    
    // 检查必要的库是否加载
    if (typeof Vue === 'undefined') {
        console.error('错误：Vue.js 未加载');
        document.body.innerHTML = '<h1 style="color:red;">Vue.js 加载失败，请刷新页面</h1>';
        return;
    }
    
    if (typeof io === 'undefined') {
        console.error('错误：Socket.IO 未加载');
        document.body.innerHTML = '<h1 style="color:red;">Socket.IO 加载失败，请刷新页面</h1>';
        return;
    }
    
    console.log('所有依赖加载成功，初始化Vue应用...');
    
    const { createApp } = Vue;
    
    const app = createApp({
        data() {
            return {
                // 连接状态
                isConnected: false,
                socket: null,
                
                // 系统信息
                projectPath: '',
                thinkingMode: '未知',
                
                // 消息相关
                messages: [],
                inputMessage: '',
                
                // 当前消息索引
                currentMessageIndex: -1,
                streamingMessage: false,
                
                // 停止功能状态
                stopRequested: false,
                
                // 文件相关
                fileTree: [],
                focusedFiles: {},
                expandedFolders: {},

                // 展开状态管理
                expandedBlocks: new Set(),
                
                // 滚动控制
                userScrolling: false,
                autoScrollEnabled: true,
                
                // 面板宽度控制
                leftWidth: 280,
                rightWidth: 420,
                isResizing: false,
                resizingPanel: null,
                minPanelWidth: 200,
                maxPanelWidth: 600,
                
                // 工具状态跟踪
                preparingTools: new Map(),
                activeTools: new Map(),
                
                // ==========================================
                // 对话管理相关状态
                // ==========================================
                
                // 对话历史侧边栏
                sidebarCollapsed: true,  // 默认收起对话侧边栏
                conversations: [],
                conversationsLoading: false,
                hasMoreConversations: false,
                loadingMoreConversations: false,
                currentConversationId: null,
                currentConversationTitle: '当前对话',
                
                // 搜索功能
                searchQuery: '',
                searchTimer: null,
                
                // 分页
                conversationsOffset: 0,
                conversationsLimit: 20,
                
                // ==========================================
                // Token统计相关状态（修复版）
                // ==========================================
                
                // 当前上下文Token（动态计算，包含完整prompt）
                currentContextTokens: 0,
                
                // 累计Token统计（从对话文件和WebSocket获取）
                currentConversationTokens: {
                    // 累计统计字段
                    cumulative_input_tokens: 0,
                    cumulative_output_tokens: 0,
                    cumulative_total_tokens: 0
                    
                },
                // Token面板折叠状态
                tokenPanelCollapsed: false,

                // 对话压缩状态
                compressing: false,

                // 设置菜单状态
                settingsOpen: false
            }
        },
        
        mounted() {
            console.log('Vue应用已挂载');
            this.initSocket();
            this.initScrollListener();
            
            // 延迟加载初始数据
            setTimeout(() => {
                this.loadInitialData();
            }, 500);
            
            document.addEventListener('click', this.handleClickOutsideSettings);
        },

        beforeUnmount() {
            document.removeEventListener('click', this.handleClickOutsideSettings);
        },
        
        methods: {
            initScrollListener() {
                const messagesArea = this.$refs.messagesArea;
                if (!messagesArea) {
                    console.warn('消息区域未找到');
                    return;
                }
                
                let isProgrammaticScroll = false;
                const bottomThreshold = 12;
                
                this._setScrollingFlag = (flag) => {
                    isProgrammaticScroll = !!flag;
                };
                
                messagesArea.addEventListener('scroll', () => {
                    if (isProgrammaticScroll) {
                        return;
                    }
                    
                    const scrollTop = messagesArea.scrollTop;
                    const scrollHeight = messagesArea.scrollHeight;
                    const clientHeight = messagesArea.clientHeight;
                    const isAtBottom = scrollHeight - scrollTop - clientHeight < bottomThreshold;
                    
                    if (isAtBottom) {
                        this.userScrolling = false;
                        this.autoScrollEnabled = true;
                    } else {
                        this.userScrolling = true;
                        this.autoScrollEnabled = false;
                    }
                });
            },
            
            initSocket() {
                try {
                    console.log('初始化WebSocket连接...');
                    
                    this.socket = io('/', {
                        transports: ['websocket', 'polling']
                    });
                    
                    // 连接事件
                    this.socket.on('connect', () => {
                        this.isConnected = true;
                        console.log('WebSocket已连接');
                        // 连接时重置所有状态
                        this.resetAllStates();
                    });
                    
                    this.socket.on('disconnect', () => {
                        this.isConnected = false;
                        console.log('WebSocket已断开');
                        // 断线时也重置状态，防止状态混乱
                        this.resetAllStates();
                    });
                    
                    this.socket.on('connect_error', (error) => {
                        console.error('WebSocket连接错误:', error.message);
                    });
                    
                    // ==========================================
                    // Token统计WebSocket事件处理（修复版）
                    // ==========================================
                    
                    this.socket.on('token_update', (data) => {
                        console.log('收到token更新事件:', data);
                        
                        // 只处理当前对话的token更新
                        if (data.conversation_id === this.currentConversationId) {
                            // 更新累计统计（使用后端提供的准确字段名）
                            this.currentConversationTokens.cumulative_input_tokens = data.cumulative_input_tokens || 0;
                            this.currentConversationTokens.cumulative_output_tokens = data.cumulative_output_tokens || 0;
                            this.currentConversationTokens.cumulative_total_tokens = data.cumulative_total_tokens || 0;
                            
                            console.log(`累计Token统计更新: 输入=${data.cumulative_input_tokens}, 输出=${data.cumulative_output_tokens}, 总计=${data.cumulative_total_tokens}`);
                            
                            // 同时更新当前上下文Token（关键修复）
                            this.updateCurrentContextTokens();
                            
                            this.$forceUpdate();
                        }
                    });
                    
                    // 系统就绪
                    this.socket.on('system_ready', (data) => {
                        this.projectPath = data.project_path || '';
                        this.thinkingMode = data.thinking_mode || '未知';
                        console.log('系统就绪:', data);
                        
                        // 系统就绪后立即加载对话列表
                        this.loadConversationsList();
                    });
                    
                    // ==========================================
                    // 对话管理相关Socket事件
                    // ==========================================
                    
                    // 监听对话变更事件
                    this.socket.on('conversation_changed', (data) => {
                        console.log('对话已切换:', data);
                        this.currentConversationId = data.conversation_id;
                        this.currentConversationTitle = data.title || '';
                        
                        if (data.cleared) {
                            // 对话被清空
                            this.messages = [];
                            this.currentConversationId = null;
                            this.currentConversationTitle = '';
                            // 重置Token统计
                            this.resetTokenStatistics();
                        }
                        
                        // 刷新对话列表
                        this.loadConversationsList();
                    });
                    
                    // 监听对话加载事件
                    this.socket.on('conversation_loaded', (data) => {
                        console.log('对话已加载:', data);
                        if (data.clear_ui) {
                            // 清理当前UI状态，准备显示历史内容
                            this.resetAllStates();
                        }
                        
                        // 延迟获取并显示历史对话内容
                        setTimeout(() => {
                            this.fetchAndDisplayHistory();
                        }, 300);
                        
                        // 延迟获取Token统计（累计+当前上下文）
                        setTimeout(() => {
                            this.fetchConversationTokenStatistics();
                            this.updateCurrentContextTokens();
                        }, 500);
                    });
                    
                    // 监听对话列表更新事件
                    this.socket.on('conversation_list_update', (data) => {
                        console.log('对话列表已更新:', data);
                        // 刷新对话列表
                        this.loadConversationsList();
                    });
                    
                    // 监听状态更新事件
                    this.socket.on('status_update', (status) => {
                        // 更新系统状态信息
                        if (status.conversation && status.conversation.current_id) {
                            this.currentConversationId = status.conversation.current_id;
                        }
                    });
                    
                    // AI消息开始
                    this.socket.on('ai_message_start', () => {
                        console.log('AI消息开始');
                        const newMessage = {
                            role: 'assistant',
                            actions: [],
                            streamingThinking: '',
                            streamingText: '',
                            currentStreamingType: null
                        };
                        this.messages.push(newMessage);
                        this.currentMessageIndex = this.messages.length - 1;
                        this.streamingMessage = true;
                        this.stopRequested = false;
                        this.autoScrollEnabled = true;
                        this.scrollToBottom();
                    });
                    
                    // 思考流开始
                    this.socket.on('thinking_start', () => {
                        console.log('思考开始');
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            msg.streamingThinking = '';
                            msg.currentStreamingType = 'thinking';
                            
                            const action = {
                                id: Date.now() + Math.random(),
                                type: 'thinking',
                                content: '',
                                streaming: true,
                                timestamp: Date.now()
                            };
                            msg.actions.push(action);
                            
                            const blockId = `${this.currentMessageIndex}-thinking-${msg.actions.length - 1}`;
                            this.expandedBlocks.add(blockId);
                            this.$forceUpdate();
                        }
                    });
                    
                    // 思考内容块
                    this.socket.on('thinking_chunk', (data) => {
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            msg.streamingThinking += data.content;
                            
                            const lastAction = msg.actions[msg.actions.length - 1];
                            if (lastAction && lastAction.type === 'thinking') {
                                lastAction.content += data.content;
                            }
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                        }
                    });
                    
                    // 思考结束
                    this.socket.on('thinking_end', (data) => {
                        console.log('思考结束');
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            const lastAction = msg.actions[msg.actions.length - 1];
                            if (lastAction && lastAction.type === 'thinking') {
                                lastAction.streaming = false;
                                lastAction.content = data.full_content;
                            }
                            msg.streamingThinking = '';
                            msg.currentStreamingType = null;
                            this.$forceUpdate();
                        }
                    });
                    
                    // 文本流开始
                    this.socket.on('text_start', () => {
                        console.log('文本开始');
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            msg.streamingText = '';
                            msg.currentStreamingType = 'text';
                            
                            const action = {
                                id: Date.now() + Math.random(),
                                type: 'text',
                                content: '',
                                streaming: true,
                                timestamp: Date.now()
                            };
                            msg.actions.push(action);
                            this.$forceUpdate();
                        }
                    });
                    
                    // 文本内容块
                    this.socket.on('text_chunk', (data) => {
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            msg.streamingText += data.content;
                            
                            const lastAction = msg.actions[msg.actions.length - 1];
                            if (lastAction && lastAction.type === 'text') {
                                lastAction.content += data.content;
                            }
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                            
                            // 实时渲染LaTeX
                            this.renderLatexInRealtime();
                        }
                    });
                    
                    // 文本结束
                    this.socket.on('text_end', (data) => {
                        console.log('文本结束');
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            
                            // 查找当前流式文本的action
                            for (let i = msg.actions.length - 1; i >= 0; i--) {
                                const action = msg.actions[i];
                                if (action.type === 'text' && action.streaming) {
                                    action.streaming = false;
                                    action.content = data.full_content;
                                    console.log('文本action已更新为完成状态');
                                    break;
                                }
                            }
                            
                            msg.streamingText = '';
                            msg.currentStreamingType = null;
                            this.$forceUpdate();
                        }
                    });
                    
                    // 工具提示事件（可选）
                    this.socket.on('tool_hint', (data) => {
                        console.log('工具提示:', data.name);
                        // 可以在这里添加提示UI
                    });
                    
                    // 工具准备中事件 - 实时显示
                    this.socket.on('tool_preparing', (data) => {
                        console.log('工具准备中:', data.name);
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            
                            // 添加准备中的工具到Map
                            this.preparingTools.set(data.id, {
                                name: data.name,
                                message: data.message || `准备调用 ${data.name}...`
                            });
                            
                            // 创建一个准备状态的action
                            const action = {
                                id: data.id,
                                type: 'tool',
                                tool: {
                                    id: data.id,
                                    name: data.name,
                                    arguments: {},
                                    status: 'preparing',
                                    result: null,
                                    message: data.message || `准备调用 ${data.name}...`
                                },
                                timestamp: Date.now()
                            };
                            
                            msg.actions.push(action);
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                        }
                    });
                    
                    // 工具状态更新事件 - 实时显示详细状态
                    this.socket.on('tool_status', (data) => {
                        console.log('工具状态:', data);
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            
                            // 查找对应的工具action并更新状态
                            for (let action of msg.actions) {
                                if (action.type === 'tool' && action.tool.name === data.tool) {
                                    action.tool.statusDetail = data.detail;
                                    action.tool.statusType = data.status;
                                    this.$forceUpdate();
                                    break;
                                }
                            }
                        }
                    });
                    
                    // 工具开始（从准备转为执行）
                    this.socket.on('tool_start', (data) => {
                        console.log('工具开始执行:', data.name);
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            
                            // 如果有准备中的ID，更新对应的action
                            if (data.preparing_id && this.preparingTools.has(data.preparing_id)) {
                                // 查找并更新准备中的工具
                                for (let action of msg.actions) {
                                    if (action.id === data.preparing_id && action.type === 'tool') {
                                        action.tool.status = 'running';
                                        action.tool.arguments = data.arguments;
                                        action.tool.message = null; // 清除自定义消息
                                        action.tool.executionId = data.id;  // 保存执行ID
                                        this.$forceUpdate();
                                        break;
                                    }
                                }
                                this.preparingTools.delete(data.preparing_id);
                            } else {
                                // 如果没有准备事件，创建新的action
                                const action = {
                                    id: data.id,
                                    type: 'tool',
                                    tool: {
                                        id: data.id,
                                        name: data.name,
                                        arguments: data.arguments,
                                        status: 'running',
                                        result: null
                                    },
                                    timestamp: Date.now()
                                };
                                msg.actions.push(action);
                                this.$forceUpdate();
                            }
                            
                            this.conditionalScrollToBottom();
                        }
                    });
                    
                    // 更新action（工具完成）
                    this.socket.on('update_action', (data) => {
                        console.log('更新action:', data.id, 'status:', data.status);
                        if (this.currentMessageIndex >= 0) {
                            const message = this.messages[this.currentMessageIndex];
                            
                            // 查找并更新工具状态
                            for (let action of message.actions) {
                                if (action.type === 'tool') {
                                    // 检查执行ID或准备ID
                                    const matchByExecution = action.tool.executionId === data.id;
                                    const matchByToolId = action.tool.id === data.id;
                                    const matchByPreparingId = action.id === data.preparing_id;
                                    if (matchByExecution || matchByToolId || matchByPreparingId) {
                                        if (data.status) {
                                            action.tool.status = data.status;
                                        }
                                        if (data.result !== undefined) {
                                            action.tool.result = data.result;
                                        }
                                        if (data.message !== undefined) {
                                            action.tool.message = data.message;
                                        }
                                        if (data.awaiting_content) {
                                            action.tool.awaiting_content = true;
                                        } else if (data.status === 'completed') {
                                            action.tool.awaiting_content = false;
                                        }
                                        console.log(`工具 ${action.tool.name} 状态更新为: ${data.status}`);
                                        this.$forceUpdate();
                                        this.conditionalScrollToBottom();
                                        break;
                                    }
                                }
                            }
                        }
                        
                        // 关键修复：每个工具完成后都更新当前上下文Token
                    if (data.status === 'completed') {
                        setTimeout(() => {
                            this.updateCurrentContextTokens();
                        }, 500);
                    }
                });
                    
                    this.socket.on('append_payload', (data) => {
                        console.log('收到append_payload事件:', data);
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            const action = {
                                id: `append-payload-${Date.now()}-${Math.random()}`,
                                type: 'append_payload',
                                append: {
                                    path: data.path || '未知文件',
                                    forced: !!data.forced,
                                    success: data.success === undefined ? true : !!data.success,
                                    lines: data.lines ?? null,
                                    bytes: data.bytes ?? null
                                },
                                timestamp: Date.now()
                            };
                            msg.actions.push(action);
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                        }
                    });
                    
                    this.socket.on('modify_payload', (data) => {
                        console.log('收到modify_payload事件:', data);
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            const action = {
                                id: `modify-payload-${Date.now()}-${Math.random()}`,
                                type: 'modify_payload',
                                modify: {
                                    path: data.path || '未知文件',
                                    total: data.total ?? null,
                                    completed: data.completed || [],
                                    failed: data.failed || [],
                                    forced: !!data.forced
                                },
                                timestamp: Date.now()
                            };
                            msg.actions.push(action);
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                        }
                    });
                    
                    // 停止请求确认
                    this.socket.on('stop_requested', (data) => {
                        console.log('停止请求已接收:', data.message);
                        // 可以显示提示信息
                    });
                    
                    // 任务停止
                    this.socket.on('task_stopped', (data) => {
                        console.log('任务已停止:', data.message);
                        this.resetAllStates();
                    });
                    
                    // 任务完成（重点：更新Token统计）
                    this.socket.on('task_complete', (data) => {
                        console.log('任务完成', data);
                        this.resetAllStates();
                        
                        // 任务完成后立即更新Token统计（关键修复）
                        if (this.currentConversationId) {
                            this.updateCurrentContextTokens();
                            this.fetchConversationTokenStatistics(); 
                        }
                    });
                    
                    // 聚焦文件更新
                    this.socket.on('focused_files_update', (data) => {
                        this.focusedFiles = data || {};
                        // 聚焦文件变化时更新当前上下文Token（关键修复）
                        if (this.currentConversationId) {
                            setTimeout(() => {
                                this.updateCurrentContextTokens();
                            }, 500);
                        }
                    });
                    
                    // 文件树更新
                    this.socket.on('file_tree_update', (data) => {
                        this.updateFileTree(data);
                        // 文件树变化时也可能影响上下文
                        if (this.currentConversationId) {
                            setTimeout(() => {
                                this.updateCurrentContextTokens();
                            }, 500);
                        }
                    });
                    
                    // 系统消息
                    this.socket.on('system_message', (data) => {
                        if (this.currentMessageIndex >= 0) {
                            const msg = this.messages[this.currentMessageIndex];
                            const action = {
                                id: `system-${Date.now()}-${Math.random()}`,
                                type: 'system',
                                content: data.content,
                                timestamp: Date.now()
                            };
                            msg.actions.push(action);
                            this.$forceUpdate();
                            this.conditionalScrollToBottom();
                        } else {
                            this.addSystemMessage(data.content);
                        }
                    });
                    
                    // 错误处理
                    this.socket.on('error', (data) => {
                        this.addSystemMessage(`错误: ${data.message}`);
                        // 发生错误时也重置状态，防止卡在错误状态
                        this.resetAllStates();
                    });
                    
                    // 命令结果
                    this.socket.on('command_result', (data) => {
                        if (data.command === 'clear' && data.success) {
                            this.messages = [];
                            this.currentMessageIndex = -1;
                            this.expandedBlocks.clear();
                            // 清除对话时重置Token统计
                            this.resetTokenStatistics();
                        } else if (data.command === 'status' && data.success) {
                            this.addSystemMessage(`系统状态:\n${JSON.stringify(data.data, null, 2)}`);
                        } else if (!data.success) {
                            this.addSystemMessage(`命令失败: ${data.message}`);
                        }
                    });
                    
                } catch (error) {
                    console.error('Socket初始化失败:', error);
                }
            },
            
            // 完整重置所有状态
            resetAllStates() {
                console.log('重置所有前端状态');
                
                // 重置消息和流状态
                this.streamingMessage = false;
                this.currentMessageIndex = -1;
                this.stopRequested = false;
                
                // 清理工具状态
                this.preparingTools.clear();
                this.activeTools.clear();
                
                // ✨ 新增：将所有未完成的工具标记为已完成
                this.messages.forEach(msg => {
                    if (msg.role === 'assistant' && msg.actions) {
                        msg.actions.forEach(action => {
                            if (action.type === 'tool' && 
                                (action.tool.status === 'preparing' || action.tool.status === 'running')) {
                                action.tool.status = 'completed';
                            }
                        });
                    }
                });
                
                // 重置滚动状态
                this.userScrolling = false;
                this.autoScrollEnabled = true;
                
                // 清理Markdown缓存
                if (this.markdownCache) {
                    this.markdownCache.clear();
                }
                
                // 强制更新视图
                this.$forceUpdate();
                
                this.settingsOpen = false;
                
                console.log('前端状态重置完成');
            },
            
            // 重置Token统计
            resetTokenStatistics() {
                this.currentContextTokens = 0;
                this.currentConversationTokens = {
                    cumulative_input_tokens: 0,
                    cumulative_output_tokens: 0,
                    cumulative_total_tokens: 0
                };
            },
            
            async loadInitialData() {
                try {
                    console.log('加载初始数据...');
                    
                    const filesResponse = await fetch('/api/files');
                    const filesData = await filesResponse.json();
                    this.updateFileTree(filesData);
                    
                    const focusedResponse = await fetch('/api/focused');
                    const focusedData = await focusedResponse.json();
                    this.focusedFiles = focusedData || {};
                    
                    const statusResponse = await fetch('/api/status');
                    const statusData = await statusResponse.json();
                    this.projectPath = statusData.project_path || '';
                    this.thinkingMode = statusData.thinking_mode || '未知';
                    
                    // 获取当前对话信息
                    if (statusData.conversation && statusData.conversation.current_id) {
                        this.currentConversationId = statusData.conversation.current_id;
                        // 如果有当前对话，尝试获取标题和Token统计
                        try {
                            const convResponse = await fetch(`/api/conversations/current`);
                            const convData = await convResponse.json();
                            if (convData.success && convData.data) {
                                this.currentConversationTitle = convData.data.title;
                            }
                            
                            // 获取当前对话的Token统计
                            this.fetchConversationTokenStatistics();
                            this.updateCurrentContextTokens();
                        } catch (e) {
                            console.warn('获取当前对话标题失败:', e);
                        }
                    }
                    
                    console.log('初始数据加载完成');
                } catch (error) {
                    console.error('加载初始数据失败:', error);
                }
            },
            
            // ==========================================
            // Token统计相关方法（完全修复版）
            // ==========================================
            
            async updateCurrentContextTokens() {
                // 获取当前上下文Token数（动态计算，包含完整prompt构建）
                if (!this.currentConversationId) {
                    this.currentContextTokens = 0;
                    return;
                }
                
                try {
                    console.log(`正在更新当前上下文Token: ${this.currentConversationId}`);
                    
                    // 关键修复：使用正确的动态API，包含文件结构+记忆+聚焦文件+终端内容+工具定义
                    const response = await fetch(`/api/conversations/${this.currentConversationId}/tokens`);
                    const data = await response.json();
                    
                    if (data.success && data.data) {
                        this.currentContextTokens = data.data.total_tokens || 0;
                        console.log(`当前上下文Token更新: ${this.currentContextTokens}`);
                        this.$forceUpdate();
                    } else {
                        console.warn('获取当前上下文Token失败:', data.error);
                        this.currentContextTokens = 0;
                    }
                } catch (error) {
                    console.warn('获取当前上下文Token异常:', error);
                    this.currentContextTokens = 0;
                }
            },
            
            async fetchConversationTokenStatistics() {
                // 获取对话累计Token统计（加载对话时、任务完成后调用）
                if (!this.currentConversationId) {
                    this.resetTokenStatistics();
                    return;
                }
                
                try {
                    const response = await fetch(`/api/conversations/${this.currentConversationId}/token-statistics`);
                    const data = await response.json();
                    
                    if (data.success && data.data) {
                        // 更新累计统计
                        this.currentConversationTokens.cumulative_input_tokens = data.data.total_input_tokens || 0;
                        this.currentConversationTokens.cumulative_output_tokens = data.data.total_output_tokens || 0;
                        this.currentConversationTokens.cumulative_total_tokens = data.data.total_tokens || 0;
                        
                        console.log(`累计Token统计: 输入=${data.data.total_input_tokens}, 输出=${data.data.total_output_tokens}, 总计=${data.data.total_tokens}`);
                        this.$forceUpdate();
                    } else {
                        console.warn('获取Token统计失败:', data.error);
                        // 保持当前统计，不重置
                    }
                } catch (error) {
                    console.warn('获取Token统计异常:', error);
                    // 保持当前统计，不重置
                }
            },
            
            // Token面板折叠/展开切换
            toggleTokenPanel() {
                this.tokenPanelCollapsed = !this.tokenPanelCollapsed;
            },
            
            // ==========================================
            // 对话管理核心功能
            // ==========================================
            
            async loadConversationsList() {
                this.conversationsLoading = true;
                try {
                    const response = await fetch(`/api/conversations?limit=${this.conversationsLimit}&offset=${this.conversationsOffset}`);
                    const data = await response.json();
                    
                    if (data.success) {
                        if (this.conversationsOffset === 0) {
                            this.conversations = data.data.conversations;
                        } else {
                            this.conversations.push(...data.data.conversations);
                        }
                        this.hasMoreConversations = data.data.has_more;
                        console.log(`已加载 ${this.conversations.length} 个对话`);

                        if (this.conversationsOffset === 0 && !this.currentConversationId && this.conversations.length > 0) {
                            const latestConversation = this.conversations[0];
                            if (latestConversation && latestConversation.id) {
                                await this.loadConversation(latestConversation.id);
                            }
                        }
                    } else {
                        console.error('加载对话列表失败:', data.error);
                    }
                } catch (error) {
                    console.error('加载对话列表异常:', error);
                } finally {
                    this.conversationsLoading = false;
                }
            },
            
            async loadMoreConversations() {
                if (this.loadingMoreConversations || !this.hasMoreConversations) return;
                
                this.loadingMoreConversations = true;
                this.conversationsOffset += this.conversationsLimit;
                await this.loadConversationsList();
                this.loadingMoreConversations = false;
            },
            
            async loadConversation(conversationId) {
                console.log('加载对话:', conversationId);
                
                if (conversationId === this.currentConversationId) {
                    console.log('已是当前对话，跳过加载');
                    return;
                }
                
                try {
                    // 1. 调用加载API
                    const response = await fetch(`/api/conversations/${conversationId}/load`, {
                        method: 'PUT'
                    });
                    const result = await response.json();
                    
                    if (result.success) {
                        console.log('对话加载API成功:', result);
                        
                        // 2. 更新当前对话信息
                        this.currentConversationId = conversationId;
                        this.currentConversationTitle = result.title;
                        
                        // 3. 重置UI状态
                        this.resetAllStates();
                        
                        // 4. 延迟获取并显示历史对话内容（关键功能）
                        setTimeout(() => {
                            this.fetchAndDisplayHistory();
                        }, 300);
                        
                        // 5. 获取Token统计（重点：加载历史累计统计+当前上下文）
                        setTimeout(() => {
                            this.fetchConversationTokenStatistics();
                            this.updateCurrentContextTokens();
                        }, 500);
                        
                    } else {
                        console.error('对话加载失败:', result.message);
                        alert(`加载对话失败: ${result.message}`);
                    }
                } catch (error) {
                    console.error('加载对话异常:', error);
                    alert(`加载对话异常: ${error.message}`);
                }
            },
            
            // ==========================================
            // 关键功能：获取并显示历史对话内容
            // ==========================================
            async fetchAndDisplayHistory() {
                console.log('开始获取历史对话内容...');
                
                if (!this.currentConversationId) {
                    console.log('没有当前对话ID，跳过历史加载');
                    return;
                }
                
                try {
                    // 使用专门的API获取对话消息历史
                    const messagesResponse = await fetch(`/api/conversations/${this.currentConversationId}/messages`);
                    
                    if (!messagesResponse.ok) {
                        console.warn('无法获取消息历史，尝试备用方法');
                        // 备用方案：通过状态API获取
                        const statusResponse = await fetch('/api/status');
                        const status = await statusResponse.json();
                        console.log('系统状态:', status);
                        
                        // 如果状态中有对话历史字段
                        if (status.conversation_history && Array.isArray(status.conversation_history)) {
                            this.renderHistoryMessages(status.conversation_history);
                            return;
                        }
                        
                        console.log('备用方案也无法获取历史消息');
                        return;
                    }
                    
                    const messagesData = await messagesResponse.json();
                    console.log('获取到消息数据:', messagesData);
                    
                    if (messagesData.success && messagesData.data && messagesData.data.messages) {
                        const messages = messagesData.data.messages;
                        console.log(`发现 ${messages.length} 条历史消息`);
                        
                        if (messages.length > 0) {
                            // 清空当前显示的消息
                            this.messages = [];
                            
                            // 渲染历史消息 - 这是关键功能
                            this.renderHistoryMessages(messages);
                            
                            // 滚动到底部
                            this.$nextTick(() => {
                                this.scrollToBottom();
                            });
                            
                            console.log('历史对话内容显示完成');
                        } else {
                            console.log('对话存在但没有历史消息');
                            this.messages = [];
                        }
                    } else {
                        console.log('消息数据格式不正确:', messagesData);
                        this.messages = [];
                    }
                    
                } catch (error) {
                    console.error('获取历史对话失败:', error);
                    console.log('尝试不显示错误弹窗，仅在控制台记录');
                    // 不显示alert，避免打断用户体验
                    this.messages = [];
                }
            },
            
            // ==========================================
            // 关键功能：渲染历史消息
            // ==========================================
            renderHistoryMessages(historyMessages) {
                console.log('开始渲染历史消息...', historyMessages);
                console.log('历史消息数量:', historyMessages.length);
                
                if (!Array.isArray(historyMessages)) {
                    console.error('历史消息不是数组格式');
                    return;
                }
                
                let currentAssistantMessage = null;
                
                historyMessages.forEach((message, index) => {
                    console.log(`处理消息 ${index + 1}/${historyMessages.length}:`, message.role, message);
                    
                    if (message.role === 'user') {
                        // 用户消息 - 先结束之前的assistant消息
                        if (currentAssistantMessage && currentAssistantMessage.actions.length > 0) {
                            this.messages.push(currentAssistantMessage);
                            currentAssistantMessage = null;
                        }
                        
                        this.messages.push({
                            role: 'user',
                            content: message.content || ''
                        });
                        console.log('添加用户消息:', message.content?.substring(0, 50) + '...');
                        
                    } else if (message.role === 'assistant') {
                        // AI消息 - 如果没有当前assistant消息，创建一个
                        if (!currentAssistantMessage) {
                            currentAssistantMessage = {
                                role: 'assistant',
                                actions: [],
                                streamingThinking: '',
                                streamingText: '',
                                currentStreamingType: null
                            };
                        }
                        
                        // 处理思考内容 - 支持多种格式
                        const content = message.content || '';
                        const thinkPatterns = [
                            /<think>([\s\S]*?)<\/think>/g,
                            /<thinking>([\s\S]*?)<\/thinking>/g
                        ];
                        
                        let allThinkingContent = '';
                        for (const pattern of thinkPatterns) {
                            let match;
                            while ((match = pattern.exec(content)) !== null) {
                                allThinkingContent += match[1].trim() + '\n';
                            }
                        }
                        
                        if (allThinkingContent) {
                            currentAssistantMessage.actions.push({
                                id: `history-think-${Date.now()}-${Math.random()}`,
                                type: 'thinking',
                                content: allThinkingContent.trim(),
                                streaming: false,
                                timestamp: Date.now()
                            });
                            console.log('添加思考内容:', allThinkingContent.substring(0, 50) + '...');
                        }
                        
                        // 处理普通文本内容（移除思考标签后的内容）
                        const metadata = message.metadata || {};
                        const appendPayloadMeta = metadata.append_payload;
                        const modifyPayloadMeta = metadata.modify_payload;
                        
                        let textContent = content
                            .replace(/<think>[\s\S]*?<\/think>/g, '')
                            .replace(/<thinking>[\s\S]*?<\/thinking>/g, '')
                            .trim();
                            
                        if (appendPayloadMeta) {
                            currentAssistantMessage.actions.push({
                                id: `history-append-payload-${Date.now()}-${Math.random()}`,
                                type: 'append_payload',
                                append: {
                                    path: appendPayloadMeta.path || '未知文件',
                                    forced: !!appendPayloadMeta.forced,
                                    success: appendPayloadMeta.success === undefined ? true : !!appendPayloadMeta.success,
                                    lines: appendPayloadMeta.lines ?? null,
                                    bytes: appendPayloadMeta.bytes ?? null
                                },
                                timestamp: Date.now()
                            });
                            console.log('添加append占位信息:', appendPayloadMeta.path);
                        } else if (modifyPayloadMeta) {
                            currentAssistantMessage.actions.push({
                                id: `history-modify-payload-${Date.now()}-${Math.random()}`,
                                type: 'modify_payload',
                                modify: {
                                    path: modifyPayloadMeta.path || '未知文件',
                                    total: modifyPayloadMeta.total_blocks ?? null,
                                    completed: modifyPayloadMeta.completed || [],
                                    failed: modifyPayloadMeta.failed || [],
                                    forced: !!modifyPayloadMeta.forced,
                                    details: modifyPayloadMeta.details || []
                                },
                                timestamp: Date.now()
                            });
                            console.log('添加modify占位信息:', modifyPayloadMeta.path);
                        }
                        
                        if (textContent && !appendPayloadMeta && !modifyPayloadMeta) {
                            currentAssistantMessage.actions.push({
                                id: `history-text-${Date.now()}-${Math.random()}`,
                                type: 'text',
                                content: textContent,
                                streaming: false,
                                timestamp: Date.now()
                            });
                            console.log('添加文本内容:', textContent.substring(0, 50) + '...');
                        }
                        
                        // 处理工具调用
                        if (message.tool_calls && Array.isArray(message.tool_calls)) {
                            message.tool_calls.forEach((toolCall, tcIndex) => {
                                let arguments_obj = {};
                                try {
                                    arguments_obj = typeof toolCall.function.arguments === 'string' 
                                        ? JSON.parse(toolCall.function.arguments || '{}')
                                        : (toolCall.function.arguments || {});
                                } catch (e) {
                                    console.warn('解析工具参数失败:', e);
                                    arguments_obj = {};
                                }
                                
                                currentAssistantMessage.actions.push({
                                    id: `history-tool-${toolCall.id || Date.now()}-${tcIndex}`,
                                    type: 'tool',
                                    tool: {
                                        id: toolCall.id,
                                        name: toolCall.function.name,
                                        arguments: arguments_obj,
                                        status: 'preparing',
                                        result: null
                                    },
                                    timestamp: Date.now()
                                });
                                console.log('添加工具调用:', toolCall.function.name);
                            });
                        }
                        
                    } else if (message.role === 'tool') {
                        // 工具结果 - 更新当前assistant消息中对应的工具
                        if (currentAssistantMessage) {
                            // 查找对应的工具action - 使用更灵活的匹配
                            let toolAction = null;
                            
                            // 优先按tool_call_id匹配
                            if (message.tool_call_id) {
                                toolAction = currentAssistantMessage.actions.find(action => 
                                    action.type === 'tool' && 
                                    action.tool.id === message.tool_call_id
                                );
                            }
                            
                            // 如果找不到，按name匹配最后一个同名工具
                            if (!toolAction && message.name) {
                                const sameNameTools = currentAssistantMessage.actions.filter(action => 
                                    action.type === 'tool' && 
                                    action.tool.name === message.name
                                );
                                toolAction = sameNameTools[sameNameTools.length - 1]; // 取最后一个
                            }
                            
                            if (toolAction) {
                                // 解析工具结果
                                let result;
                                try {
                                    // 尝试解析为JSON
                                    result = JSON.parse(message.content);
                                } catch (e) {
                                    // 如果不是JSON，就作为纯文本
                                    result = { 
                                        output: message.content,
                                        success: true
                                    };
                                }
                                
                                toolAction.tool.status = 'completed';
                                toolAction.tool.result = result;
                                if (message.name === 'append_to_file' && result && result.message) {
                                    toolAction.tool.message = result.message;
                                }
                                console.log(`更新工具结果: ${message.name} -> ${message.content?.substring(0, 50)}...`);
                                
                                if (message.name === 'append_to_file' && result && typeof result === 'object') {
                                    const appendSummary = {
                                        path: result.path || '未知文件',
                                        success: result.success !== false,
                                        summary: result.message || (result.success === false ? '追加失败' : '追加完成'),
                                        lines: result.lines || 0,
                                        bytes: result.bytes || 0,
                                        forced: !!result.forced
                                    };
                                    currentAssistantMessage.actions.push({
                                        id: `history-append-${Date.now()}-${Math.random()}`,
                                        type: 'append',
                                        append: appendSummary,
                                        timestamp: Date.now()
                                    });
                                }
                            } else {
                                console.warn('找不到对应的工具调用:', message.name, message.tool_call_id);
                            }
                        }
                        
                    } else {
                        // 其他类型消息（如system）- 先结束当前assistant消息
                        if (currentAssistantMessage && currentAssistantMessage.actions.length > 0) {
                            this.messages.push(currentAssistantMessage);
                            currentAssistantMessage = null;
                        }
                        
                        console.log('处理其他类型消息:', message.role);
                        this.messages.push({
                            role: message.role,
                            content: message.content || ''
                        });
                    }
                });
                
                // 处理最后一个assistant消息
                if (currentAssistantMessage && currentAssistantMessage.actions.length > 0) {
                    this.messages.push(currentAssistantMessage);
                }
                
                console.log(`历史消息渲染完成，共 ${this.messages.length} 条消息`);
                
                // 强制更新视图
                this.$forceUpdate();
                
                // 确保滚动到底部
                this.$nextTick(() => {
                    this.scrollToBottom();
                });
            },
            
            async createNewConversation() {
                console.log('创建新对话...');
                
                try {
                    const response = await fetch('/api/conversations', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            thinking_mode: this.thinkingMode !== '快速模式'
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        console.log('新对话创建成功:', result.conversation_id);
                        
                        // 清空当前消息
                        this.messages = [];
                        this.currentConversationId = result.conversation_id;
                        this.currentConversationTitle = '新对话';
                        
                        // 重置Token统计
                        this.resetTokenStatistics();
                        
                        // 重置状态
                        this.resetAllStates();
                        
                        // 刷新对话列表
                        this.conversationsOffset = 0;
                        await this.loadConversationsList();
                        
                    } else {
                        console.error('创建对话失败:', result.message);
                        alert(`创建对话失败: ${result.message}`);
                    }
                } catch (error) {
                    console.error('创建对话异常:', error);
                    alert(`创建对话异常: ${error.message}`);
                }
            },
            
            async deleteConversation(conversationId) {
                if (!confirm('确定要删除这个对话吗？删除后无法恢复。')) {
                    return;
                }
                
                console.log('删除对话:', conversationId);
                
                try {
                    const response = await fetch(`/api/conversations/${conversationId}`, {
                        method: 'DELETE'
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        console.log('对话删除成功');
                        
                        // 如果删除的是当前对话，清空界面
                        if (conversationId === this.currentConversationId) {
                            this.messages = [];
                            this.currentConversationId = null;
                            this.currentConversationTitle = '';
                            this.resetAllStates();
                            this.resetTokenStatistics();
                        }
                        
                        // 刷新对话列表
                        this.conversationsOffset = 0;
                        await this.loadConversationsList();
                        
                    } else {
                        console.error('删除对话失败:', result.message);
                        alert(`删除对话失败: ${result.message}`);
                    }
                } catch (error) {
                    console.error('删除对话异常:', error);
                    alert(`删除对话异常: ${error.message}`);
                }
            },

            async duplicateConversation(conversationId) {
                console.log('复制对话:', conversationId);
                try {
                    const response = await fetch(`/api/conversations/${conversationId}/duplicate`, {
                        method: 'POST'
                    });

                    const result = await response.json();

                    if (response.ok && result.success) {
                        const newId = result.duplicate_conversation_id;
                        if (newId) {
                            this.currentConversationId = newId;
                        }

                        this.conversationsOffset = 0;
                        await this.loadConversationsList();
                    } else {
                        const message = result.message || result.error || '复制失败';
                        alert(`复制失败: ${message}`);
                    }
                } catch (error) {
                    console.error('复制对话异常:', error);
                    alert(`复制对话异常: ${error.message}`);
                }
            },
            
            searchConversations() {
                // 简单的搜索功能，实际实现可以调用搜索API
                if (this.searchTimer) {
                    clearTimeout(this.searchTimer);
                }
                
                this.searchTimer = setTimeout(() => {
                    if (this.searchQuery.trim()) {
                        console.log('搜索对话:', this.searchQuery);
                        // TODO: 实现搜索API调用
                        // this.searchConversationsAPI(this.searchQuery);
                    } else {
                        // 清空搜索，重新加载全部对话
                        this.conversationsOffset = 0;
                        this.loadConversationsList();
                    }
                }, 300);
            },
            
            toggleSidebar() {
                this.sidebarCollapsed = !this.sidebarCollapsed;
            },
            
            formatTime(timeString) {
                if (!timeString) return '';
                
                const date = new Date(timeString);
                const now = new Date();
                const diffMs = now - date;
                const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
                const diffDays = Math.floor(diffHours / 24);
                
                if (diffHours < 1) {
                    return '刚刚';
                } else if (diffHours < 24) {
                    return `${diffHours}小时前`;
                } else if (diffDays < 7) {
                    return `${diffDays}天前`;
                } else {
                    return date.toLocaleDateString('zh-CN', { 
                        month: 'short', 
                        day: 'numeric' 
                    });
                }
            },
            
            // ==========================================
            // 原有功能保持不变
            // ==========================================
            
            updateFileTree(structure) {
                const treeDictionary = structure && structure.tree ? structure.tree : {};

                const buildNodes = (treeMap) => {
                    if (!treeMap) {
                        return [];
                    }

                    const entries = Object.keys(treeMap).map((name) => {
                        const node = treeMap[name] || {};
                        if (node.type === 'folder') {
                            return {
                                type: 'folder',
                                name,
                                path: node.path || name,
                                children: buildNodes(node.children)
                            };
                        }
                        return {
                            type: 'file',
                            name,
                            path: node.path || name,
                            annotation: node.annotation || ''
                        };
                    });

                    entries.sort((a, b) => {
                        if (a.type !== b.type) {
                            return a.type === 'folder' ? -1 : 1;
                        }
                        return a.name.localeCompare(b.name, 'zh-CN');
                    });

                    return entries;
                };

                const nodes = buildNodes(treeDictionary);

                const expanded = { ...this.expandedFolders };
                const validFolderPaths = new Set();

                const ensureExpansion = (list, depth = 0) => {
                    list.forEach((item) => {
                        if (item.type === 'folder') {
                            validFolderPaths.add(item.path);
                            if (expanded[item.path] === undefined) {
                                expanded[item.path] = false;
                            }
                            ensureExpansion(item.children || [], depth + 1);
                        }
                    });
                };

                ensureExpansion(nodes);

                Object.keys(expanded).forEach((path) => {
                    if (!validFolderPaths.has(path)) {
                        delete expanded[path];
                    }
                });

                this.expandedFolders = expanded;
                this.fileTree = nodes;
            },

            toggleFolder(path) {
                if (!path) {
                    return;
                }
                const current = !!this.expandedFolders[path];
                this.expandedFolders = {
                    ...this.expandedFolders,
                    [path]: !current
                };
            },
            
            handleSendOrStop() {
                if (this.streamingMessage) {
                    this.stopTask();
                } else {
                    this.sendMessage();
                }
            },

            sendMessage() {
                if (this.streamingMessage || !this.isConnected) {
                    return;
                }

                if (!this.inputMessage.trim()) {
                    return;
                }
                
                const message = this.inputMessage;
                
                if (message.startsWith('/')) {
                    this.socket.emit('send_command', { command: message });
                    this.inputMessage = '';
                    this.settingsOpen = false;
                    return;
                }
                
                this.messages.push({
                    role: 'user',
                    content: message
                });
                
                this.currentMessageIndex = -1;
                this.socket.emit('send_message', { message: message });
                this.inputMessage = '';
                this.autoScrollEnabled = true;
                this.scrollToBottom();
                this.settingsOpen = false;
                
                // 发送消息后延迟更新当前上下文Token（关键修复：恢复原逻辑）
                setTimeout(() => {
                    if (this.currentConversationId) {
                        this.updateCurrentContextTokens();
                    }
                }, 1000);
            },
            
            // 新增：停止任务方法
            stopTask() {
                if (this.streamingMessage && !this.stopRequested) {
                    this.socket.emit('stop_task');
                    this.stopRequested = true;
                    console.log('发送停止请求');
                }
                this.settingsOpen = false;
            },
            
            clearChat() {
                if (confirm('确定要清除所有对话记录吗？')) {
                    this.socket.emit('send_command', { command: '/clear' });
                }
                this.settingsOpen = false;
            },

            async compressConversation() {
                if (!this.currentConversationId) {
                    alert('当前没有可压缩的对话。');
                    return;
                }

                if (this.compressing) {
                    return;
                }

                const confirmed = confirm('确定要压缩当前对话记录吗？压缩后会生成新的对话副本。');
                if (!confirmed) {
                    return;
                }

                this.settingsOpen = false;
                this.compressing = true;

                try {
                    const response = await fetch(`/api/conversations/${this.currentConversationId}/compress`, {
                        method: 'POST'
                    });

                    const result = await response.json();

                    if (response.ok && result.success) {
                        const newId = result.compressed_conversation_id;
                        if (newId) {
                            this.currentConversationId = newId;
                        }
                        console.log('对话压缩完成:', result);
                    } else {
                        const message = result.message || result.error || '压缩失败';
                        alert(`压缩失败: ${message}`);
                    }
                } catch (error) {
                    console.error('压缩对话异常:', error);
                    alert(`压缩对话异常: ${error.message}`);
                } finally {
                    this.compressing = false;
                }
            },

            toggleSettings() {
                if (!this.isConnected) {
                    return;
                }
                this.settingsOpen = !this.settingsOpen;
            },

            handleClickOutsideSettings(event) {
                if (!this.settingsOpen) {
                    return;
                }
                const dropdown = this.$refs.settingsDropdown;
                if (dropdown && !dropdown.contains(event.target)) {
                    this.settingsOpen = false;
                }
            },
            
            addSystemMessage(content) {
                this.messages.push({
                    role: 'system',
                    content: content
                });
                this.conditionalScrollToBottom();
            },
            
            toggleBlock(id) {
                if (this.expandedBlocks.has(id)) {
                    this.expandedBlocks.delete(id);
                } else {
                    this.expandedBlocks.add(id);
                }
                this.$forceUpdate();
            },
            
            // 修复：工具相关方法 - 接收tool对象而不是name
            getToolIcon(tool) {
                const toolName = typeof tool === 'string' ? tool : tool.name;
                const icons = {
                    'create_file': '📄',
                    'sleep': '⏱️',
                    'read_file': '📖',
                    'delete_file': '🗑️',
                    'rename_file': '✏️',
                    'modify_file': '✏️',
                    'append_to_file': '✏️',
                    'create_folder': '📁',
                    'focus_file': '👁️',
                    'unfocus_file': '👁️',
                    'web_search': '🔍',
                    'extract_webpage': '🌐',
                    'save_webpage': '💾',
                    'run_python': '🐍',
                    'run_command': '$',
                    'update_memory': '🧠',
                    'terminal_session': '💻',
                    'terminal_input': '⌨️'
                };
                return icons[toolName] || '⚙️';
            },
            
            getToolAnimationClass(tool) {
                // 根据工具状态返回不同的动画类
                if (tool.status === 'hinted') {
                    return 'hint-animation pulse-slow';
                } else if (tool.status === 'preparing') {
                    return 'preparing-animation';
                } else if (tool.status === 'running') {
                    const animations = {
                        'create_file': 'file-animation',
                        'read_file': 'read-animation',
                        'delete_file': 'file-animation',
                        'rename_file': 'file-animation',
                        'modify_file': 'file-animation',
                        'append_to_file': 'file-animation',
                        'create_folder': 'file-animation',
                        'focus_file': 'focus-animation',
                        'unfocus_file': 'focus-animation',
                        'web_search': 'search-animation',
                        'extract_webpage': 'search-animation',
                        'save_webpage': 'file-animation',
                        'run_python': 'code-animation',
                        'run_command': 'terminal-animation',
                        'update_memory': 'memory-animation',
                        'sleep': 'wait-animation',
                        'terminal_session': 'terminal-animation',
                        'terminal_input': 'terminal-animation'
                    };
                    return animations[tool.name] || 'default-animation';
                }
                return '';
            },
            
            // 修复：获取工具状态文本
            getToolStatusText(tool) {
                // 优先使用自定义消息
                if (tool.message) {
                    return tool.message;
                }
                
                if (tool.status === 'hinted') {
                    return `可能需要 ${tool.name}...`;
                } else if (tool.status === 'preparing') {
                    return `准备调用 ${tool.name}...`;
                } else if (tool.status === 'running') {
                    const texts = {
                        'create_file': '正在创建文件...',
                        'read_file': '正在读取文件...',
                        'sleep': '正在等待...',
                        'delete_file': '正在删除文件...',
                        'rename_file': '正在重命名文件...',
                        'modify_file': '正在修改文件...',
                        'append_to_file': '正在追加文件...',
                        'create_folder': '正在创建文件夹...',
                        'focus_file': '正在聚焦文件...',
                        'unfocus_file': '正在取消聚焦...',
                        'web_search': '正在搜索网络...',
                        'extract_webpage': '正在提取网页...',
                        'save_webpage': '正在保存网页...',
                        'run_python': '正在执行Python代码...',
                        'run_command': '正在执行命令...',
                        'update_memory': '正在更新记忆...',
                        'terminal_session': '正在管理终端会话...',
                        'terminal_input': '正在发送终端输入...'
                    };
                    return texts[tool.name] || '正在执行...';
                } else if (tool.status === 'completed') {
                    // 修复：完成状态的文本
                    const texts = {
                        'create_file': '文件创建成功',
                        'read_file': '文件读取完成',
                        'delete_file': '文件删除成功',
                        'sleep': '等待完成',
                        'rename_file': '文件重命名成功',
                        'modify_file': '文件修改成功',
                        'append_to_file': '文件追加完成',
                        'create_folder': '文件夹创建成功',
                        'focus_file': '文件聚焦成功',
                        'unfocus_file': '取消聚焦成功',
                        'web_search': '搜索完成',
                        'extract_webpage': '网页提取完成',
                        'save_webpage': '网页保存完成（纯文本）',
                        'run_python': '代码执行完成',
                        'run_command': '命令执行完成',
                        'update_memory': '记忆更新成功',
                        'terminal_session': '终端操作完成',
                        'terminal_input': '终端输入完成'
                    };
                    return texts[tool.name] || '执行完成';
                } else {
                    // 其他状态
                    return `${tool.name} - ${tool.status}`;
                }
            },
            
            getToolDescription(tool) {
                // 如果有状态详情，优先显示
                if (tool.statusDetail) {
                    return tool.statusDetail;
                }
                
                if (tool.result && typeof tool.result === 'object') {
                    if (tool.result.path) {
                        return tool.result.path.split('/').pop();
                    }
                }
                
                if (tool.arguments) {
                    if (tool.arguments.path) {
                        return tool.arguments.path.split('/').pop();
                    }
                    if (tool.arguments.target_path) {
                        return tool.arguments.target_path.split('/').pop();
                    }
                    if (tool.arguments.query) {
                        return `"${tool.arguments.query}"`;
                    }
                    if (tool.arguments.command) {
                        return tool.arguments.command;
                    }
                    if (tool.arguments.seconds) {
                        return `${tool.arguments.seconds} 秒`;
                    }
                }
                return '';
            },
            
            renderMarkdown(text, isStreaming = false) {
                if (!text) return '';
                
                if (typeof marked === 'undefined') {
                    return text;
                }
                
                marked.setOptions({
                    breaks: true,
                    gfm: true,
                    sanitize: false
                });
                
                if (!isStreaming) {
                    if (!this.markdownCache) {
                        this.markdownCache = new Map();
                    }
                    
                    const cacheKey = `${text.length}_${text.substring(0, 100)}`;
                    
                    if (this.markdownCache.has(cacheKey)) {
                        return this.markdownCache.get(cacheKey);
                    }
                }
                
                let html = marked.parse(text);
                html = this.wrapCodeBlocks(html, isStreaming);
                
                if (!isStreaming && text.length < 10000) {
                    if (!this.markdownCache) {
                        this.markdownCache = new Map();
                    }
                    this.markdownCache.set(`${text.length}_${text.substring(0, 100)}`, html);
                    if (this.markdownCache.size > 20) {
                        const firstKey = this.markdownCache.keys().next().value;
                        this.markdownCache.delete(firstKey);
                    }
                }
                
                // 只在非流式状态处理（流式状态由renderLatexInRealtime处理）
                if (!isStreaming) {
                    setTimeout(() => {
                        // 代码高亮
                        if (typeof Prism !== 'undefined') {
                            const codeBlocks = document.querySelectorAll('.code-block-wrapper pre code:not([data-highlighted])');
                            codeBlocks.forEach(block => {
                                try {
                                    Prism.highlightElement(block);
                                    block.setAttribute('data-highlighted', 'true');
                                } catch (e) {
                                    console.warn('代码高亮失败:', e);
                                }
                            });
                        }
                        
                        // LaTeX最终渲染
                        if (typeof renderMathInElement !== 'undefined') {
                            const elements = document.querySelectorAll('.text-output .text-content:not(.streaming-text)');
                            elements.forEach(element => {
                                if (element.hasAttribute('data-math-rendered')) return;
                                
                                try {
                                    renderMathInElement(element, {
                                        delimiters: [
                                            {left: '$$', right: '$$', display: true},
                                            {left: '$', right: '$', display: false},
                                            {left: '\\[', right: '\\]', display: true},
                                            {left: '\\(', right: '\\)', display: false}
                                        ],
                                        throwOnError: false,
                                        trust: true
                                    });
                                    element.setAttribute('data-math-rendered', 'true');
                                } catch (e) {
                                    console.warn('LaTeX渲染失败:', e);
                                }
                            });
                        }
                    }, 100);
                }
                
                return html;
            },
            // 实时LaTeX渲染（用于流式输出）
            renderLatexInRealtime() {
                if (typeof renderMathInElement === 'undefined') {
                    return;
                }
                
                // 使用requestAnimationFrame优化性能
                if (this._latexRenderTimer) {
                    cancelAnimationFrame(this._latexRenderTimer);
                }
                
                this._latexRenderTimer = requestAnimationFrame(() => {
                    const elements = document.querySelectorAll('.text-output .streaming-text');
                    elements.forEach(element => {
                        try {
                            renderMathInElement(element, {
                                delimiters: [
                                    {left: '$$', right: '$$', display: true},
                                    {left: '$', right: '$', display: false},
                                    {left: '\\[', right: '\\]', display: true},
                                    {left: '\\(', right: '\\)', display: false}
                                ],
                                throwOnError: false,
                                trust: true
                            });
                        } catch (e) {
                            // 忽略错误，继续渲染
                        }
                    });
                });
            },
            // 用字符串替换包装代码块
            // 用字符串替换包装代码块 - 添加streaming参数
            wrapCodeBlocks(html, isStreaming = false) {
                // 如果是流式输出，不包装代码块，保持原样
                if (isStreaming) {
                    return html;
                }
                
                let counter = 0;
                
                // 匹配 <pre><code ...>...</code></pre>
                return html.replace(/<pre><code([^>]*)>([\s\S]*?)<\/code><\/pre>/g, (match, attributes, content) => {
                    // 提取语言
                    const langMatch = attributes.match(/class="[^"]*language-(\w+)/);
                    const language = langMatch ? langMatch[1] : 'text';
                    
                    // 生成唯一ID
                    const blockId = `code-${Date.now()}-${counter++}`;
                    
                    // 转义引号用于data属性
                    const escapedContent = content
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;');
                    
                    // 构建新的HTML，保持code元素原样
                    return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-language">${language}</span>
                    <button class="copy-code-btn" data-code="${blockId}" title="复制代码">📋</button>
                </div>
                <pre><code${attributes} data-code-id="${blockId}" data-original-code="${escapedContent}">${content}</code></pre>
            </div>`;
                });
            },
            
            getLanguageClass(path) {
                const ext = path.split('.').pop().toLowerCase();
                const langMap = {
                    'py': 'language-python',
                    'js': 'language-javascript',
                    'html': 'language-html',
                    'css': 'language-css',
                    'json': 'language-json',
                    'md': 'language-markdown',
                    'txt': 'language-plain'
                };
                return langMap[ext] || 'language-plain';
            },
            
            scrollToBottom() {
                setTimeout(() => {
                    const messagesArea = this.$refs.messagesArea;
                    if (messagesArea) {
                        // 标记为程序触发的滚动
                        if (this._setScrollingFlag) {
                            this._setScrollingFlag(true);
                        }
                        
                        messagesArea.scrollTop = messagesArea.scrollHeight;
                        
                        // 滚动完成后重置标记
                        setTimeout(() => {
                            if (this._setScrollingFlag) {
                                this._setScrollingFlag(false);
                            }
                        }, 100);
                    }
                }, 50);
            },
            
            conditionalScrollToBottom() {
                // 严格检查：只在明确允许时才滚动
                if (this.autoScrollEnabled === true && this.userScrolling === false) {
                    this.scrollToBottom();
                }
            },
            
            toggleScrollLock() {
                const currentlyLocked = this.autoScrollEnabled && !this.userScrolling;
                if (currentlyLocked) {
                    this.autoScrollEnabled = false;
                    this.userScrolling = true;
                } else {
                    this.autoScrollEnabled = true;
                    this.userScrolling = false;
                    this.scrollToBottom();
                }
            },
            
            // 面板调整方法
            startResize(panel, event) {
                this.isResizing = true;
                this.resizingPanel = panel;
                document.addEventListener('mousemove', this.handleResize);
                document.addEventListener('mouseup', this.stopResize);
                document.body.style.userSelect = 'none';
                document.body.style.cursor = 'col-resize';
                event.preventDefault();
            },
            
            handleResize(event) {
                if (!this.isResizing) return;
                
                const containerWidth = document.querySelector('.main-container').offsetWidth;
                
                if (this.resizingPanel === 'left') {
                    let newWidth = event.clientX - (this.sidebarCollapsed ? 60 : 300);
                    newWidth = Math.max(this.minPanelWidth, Math.min(newWidth, this.maxPanelWidth));
                    this.leftWidth = newWidth;
                } else if (this.resizingPanel === 'right') {
                    let newWidth = containerWidth - event.clientX;
                    newWidth = Math.max(this.minPanelWidth, Math.min(newWidth, this.maxPanelWidth));
                    this.rightWidth = newWidth;
                } else if (this.resizingPanel === 'conversation') {
                    // 对话侧边栏宽度调整
                    let newWidth = event.clientX;
                    newWidth = Math.max(200, Math.min(newWidth, 400));
                    // 这里可以动态调整对话侧边栏宽度，暂时不实现
                }
            },
            
            stopResize() {
                this.isResizing = false;
                this.resizingPanel = null;
                document.removeEventListener('mousemove', this.handleResize);
                document.removeEventListener('mouseup', this.stopResize);
                document.body.style.userSelect = '';
                document.body.style.cursor = '';
            },

            // 格式化token显示（修复NaN问题）
            formatTokenCount(tokens) {
                // 确保tokens是数字，防止NaN
                const num = Number(tokens) || 0;
                if (num < 1000) {
                    return num.toString();
                } else if (num < 1000000) {
                    return (num / 1000).toFixed(1) + 'K';
                } else {
                    return (num / 1000000).toFixed(1) + 'M';
                }
            }
        }
    });
    
    app.component('file-node', {
        name: 'FileNode',
        props: {
            node: {
                type: Object,
                required: true
            },
            level: {
                type: Number,
                default: 0
            },
            expandedFolders: {
                type: Object,
                required: true
            }
        },
        emits: ['toggle-folder'],
        computed: {
            isExpanded() {
                if (this.node.type !== 'folder') {
                    return false;
                }
                const value = this.expandedFolders[this.node.path];
                return value === undefined ? true : value;
            },
            folderPadding() {
                return {
                    paddingLeft: `${12 + this.level * 16}px`
                };
            },
            filePadding() {
                return {
                    paddingLeft: `${40 + this.level * 16}px`
                };
            }
        },
        methods: {
            toggle() {
                if (this.node.type === 'folder') {
                    this.$emit('toggle-folder', this.node.path);
                }
            }
        },
        template: `
            <div class="file-node-wrapper">
                <div v-if="node.type === 'folder'" class="file-node folder-node">
                    <button class="folder-header" type="button" :style="folderPadding" @click="toggle">
                        <span class="folder-arrow">{{ isExpanded ? '▾' : '▸' }}</span>
                        <span class="folder-icon">{{ isExpanded ? '📂' : '📁' }}</span>
                        <span class="folder-name">{{ node.name }}</span>
                    </button>
                    <div v-show="isExpanded" class="folder-children">
                        <file-node
                            v-for="child in node.children"
                            :key="child.path"
                            :node="child"
                            :level="level + 1"
                            :expanded-folders="expandedFolders"
                            @toggle-folder="$emit('toggle-folder', $event)"
                        ></file-node>
                    </div>
                </div>
                <div v-else class="file-node file-leaf" :style="filePadding">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ node.name }}</span>
                    <span v-if="node.annotation" class="annotation">{{ node.annotation }}</span>
                </div>
            </div>
        `
    });

    app.mount('#app');
    console.log('Vue应用初始化完成');
    
};
