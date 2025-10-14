DOMAIN = "openlist"
DEFAULT_NAME = "OpenList"
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TRACK_DIRS = "track_dirs"  # 新增：跟踪目录配置
PLATFORMS = ["sensor"]

# 任务类型常量
TASK_TYPES = {
    "upload": "上传",
    "copy": "复制", 
    "offline_download": "离线下载",
    "offline_download_transfer": "离线下载转存",
    "decompress": "解压",
    "decompress_upload": "解压转存",
    "move": "移动"# 新增 move 任务类型
}

# 传感器类型
SENSOR_TYPE_DONE = "done"
SENSOR_TYPE_UNDONE = "undone"
SENSOR_TYPE_FAILED = "failed"  # 新增：已失败任务传感器类型
SENSOR_TYPE_TRACK_DIR = "track_dir"  # 新增：跟踪目录传感器类型