# config.py - 系统配置文件（添加了终端配置）

# API配置
API_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
API_KEY = "请替换为你的API密钥"
MODEL_ID = "kimi-k2-250905"  # 模型ID

# 如需通过环境变量覆盖以下配置，可取消注释
# import os
# API_BASE_URL = os.getenv("API_BASE_URL", API_BASE_URL)
# API_KEY = os.getenv("API_KEY", API_KEY)
# MODEL_ID = os.getenv("MODEL_ID", MODEL_ID)

#API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
#API_KEY = "<YOUR_DASHSCOPE_API_KEY>"
#MODEL_ID = "qwen3-max"  # 模型ID

# Tavily搜索配置
TAVILY_API_KEY = "请替换为你的TavilyAPI密钥"

# 如需通过环境变量覆盖，请取消注释
# TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", TAVILY_API_KEY)

# 系统配置
DEFAULT_PROJECT_PATH = "./project"  # 默认项目文件夹
MAX_CONTEXT_SIZE = 100000  # 最大上下文字符数（约100K）
MAX_FILE_SIZE = 10 * 1024 * 1024  # 最大文件大小 10MB
MAX_OPEN_FILES = 20  # 最多同时打开的文件数

# 执行配置
CODE_EXECUTION_TIMEOUT = 60  # 代码执行超时（秒）
TERMINAL_COMMAND_TIMEOUT = 30  # 终端命令超时（秒）
SEARCH_MAX_RESULTS = 10  # 搜索最大结果数

# 持久化终端配置（新增）
MAX_TERMINALS = 3  # 最大同时开启的终端数量
TERMINAL_BUFFER_SIZE =100000  # 每个终端的最大缓冲区大小（字符）
TERMINAL_DISPLAY_SIZE = 50000  # 终端显示大小限制（字符）
TERMINAL_TIMEOUT = 300  # 终端空闲超时（秒）
TERMINAL_OUTPUT_WAIT = 5  # 等待终端输出的默认时间（秒）

# 在 config.py 中添加以下配置项

# 自动修复配置
AUTO_FIX_TOOL_CALL = False  # 是否自动修复工具调用格式错误
AUTO_FIX_MAX_ATTEMPTS = 3  # 最大自动修复尝试次数

# 工具调用安全限制
MAX_ITERATIONS_PER_TASK = 100# 单个任务最大迭代次数
MAX_CONSECUTIVE_SAME_TOOL = 50  # 连续相同工具调用的最大次数
MAX_TOTAL_TOOL_CALLS = 100  #单个任务最大工具调用总数
TOOL_CALL_COOLDOWN = 0.5  # 工具调用之间的最小间隔（秒）

# 文件路径
PROMPTS_DIR = "./prompts"
DATA_DIR = "./data"
LOGS_DIR = "./logs"

# 记忆文件
MAIN_MEMORY_FILE = f"{DATA_DIR}/memory.md"
TASK_MEMORY_FILE = f"{DATA_DIR}/task_memory.md"
CONVERSATION_HISTORY_FILE = f"{DATA_DIR}/conversation_history.json"

# 日志配置
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 安全配置
FORBIDDEN_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "format",
    "shutdown",
    "reboot",
    "kill -9",
    "dd if=",
]

FORBIDDEN_PATHS = [
    "/System",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/var",
    "/tmp",
    "/Applications",
    "/Library",
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData"
]

# 这些是绝对不允许的根路径
FORBIDDEN_ROOT_PATHS = [
    "/",
    "C:\\",
    "~"
]

# 确认操作列表
NEED_CONFIRMATION = [
    "delete_file",
    "delete_folder",
    "clear_file",
    "execute_terminal",
    "batch_delete"
]

# 输出格式
OUTPUT_FORMATS = {
    "thinking": "💭 [思考]",
    "action": "🔧 [执行]",
    "file": "📁 [文件]",
    "search": "🔍 [搜索]",
    "code": "💻 [代码]",
    "terminal": "⚡ [终端]",
    "memory": "📝 [记忆]",
    "success": "✅ [成功]",
    "error": "❌ [错误]",
    "warning": "⚠️  [警告]",
    "confirm": "❓ [确认]",
    "info": "ℹ️  [信息]",
    "session": "📺 [会话]"  # 新增：终端会话标记
}
# 在 config.py 文件末尾添加以下对话持久化相关配置

# ==========================================
# 对话持久化配置（新增）
# ==========================================

# 对话存储配置
CONVERSATIONS_DIR = f"{DATA_DIR}/conversations"  # 对话存储目录
CONVERSATION_INDEX_FILE = "index.json"  # 对话索引文件名
CONVERSATION_FILE_PREFIX = "conv_"  # 对话文件前缀

# 对话管理配置
DEFAULT_CONVERSATIONS_LIMIT = 20  # API默认返回的对话数量
MAX_CONVERSATIONS_LIMIT = 100  # API允许的最大对话数量限制
CONVERSATION_TITLE_MAX_LENGTH = 100  # 对话标题最大长度
CONVERSATION_SEARCH_MAX_RESULTS = 50  # 搜索结果最大数量

# 对话清理策略配置
CONVERSATION_AUTO_CLEANUP_ENABLED = False  # 是否启用自动清理旧对话
CONVERSATION_RETENTION_DAYS = 30  # 对话保留天数（如果启用自动清理）
CONVERSATION_MAX_TOTAL = 1000  # 最大对话总数（超过时清理最旧的）

# 对话备份配置
CONVERSATION_BACKUP_ENABLED = True  # 是否启用对话备份
CONVERSATION_BACKUP_INTERVAL_HOURS = 24  # 备份间隔（小时）
CONVERSATION_BACKUP_MAX_COUNT = 7  # 最多保留多少个备份文件

# 对话安全配置
CONVERSATION_MAX_MESSAGE_SIZE = 50000  # 单条消息最大字符数
CONVERSATION_MAX_MESSAGES_PER_CONVERSATION = 10000  # 每个对话最大消息数
CONVERSATION_EXPORT_MAX_SIZE = 10 * 1024 * 1024  # 导出文件最大大小（10MB）

# 对话性能配置
CONVERSATION_LAZY_LOADING = True  # 是否启用懒加载（只加载对话元数据，不加载完整消息）
CONVERSATION_CACHE_SIZE = 50  # 内存中缓存的对话数量
CONVERSATION_INDEX_UPDATE_BATCH_SIZE = 100  # 批量更新索引的大小

# 工具输出字符数限制
MAX_READ_FILE_CHARS = 30000      # read_file工具限制
MAX_FOCUS_FILE_CHARS = 30000     # focus_file工具限制  
MAX_RUN_COMMAND_CHARS = 10000    # run_command工具限制
MAX_EXTRACT_WEBPAGE_CHARS = 80000 # extract_webpage工具限制

# 模型调用相关
DEFAULT_RESPONSE_MAX_TOKENS = 16384  # 每次API响应的默认最大tokens，可在此调整
