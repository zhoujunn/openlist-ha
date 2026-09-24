DOMAIN = "openlist"
DEFAULT_NAME = "OpenList"
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TRACK_DIRS = "track_dirs"
CONF_UPDATE_INTERVAL = "update_interval"

# 平台（含 button）
PLATFORMS = ["sensor", "binary_sensor", "button"]   # ← 加 binary_sensor


TASK_TYPES = {
    "upload": "上传",
    "copy": "复制",
    "offline_download": "离线下载",
    "offline_download_transfer": "离线下载转存",
    "decompress": "解压",
    "decompress_upload": "解压转存",
}

# 传感器类型
SENSOR_TYPE_DONE = "done"
SENSOR_TYPE_UNDONE = "undone"
SENSOR_TYPE_FAILED = "failed"
SENSOR_TYPE_TRACK_DIR = "track_dir"
SENSOR_TYPE_PROGRESS = "progress"
SENSOR_TYPE_STORAGE = "storage"

# 需要异步执行、完成后发通知的服务（api 方法名）
ASYNC_FILE_SERVICES = {
    "async_add_offline_download",
    "async_decompress_archive",
    "async_copy_files",
    "async_move_files",
    "async_recursive_move",
    "async_regex_rename",
    "async_batch_rename",
    "async_remove_files",
}

# 事件名
EVENT_TASK_COMPLETED = f"{DOMAIN}_task_completed"

# 设备信息常量
MANUFACTURER = "OpenList"
MODEL = "OpenList Server"

# 令牌刷新阈值（0.5 表示有效期过半即刷新）
TOKEN_REFRESH_THRESHOLD = 0.5

# 令牌默认有效期（秒，48 小时）
TOKEN_TTL_DEFAULT = 48 * 3600