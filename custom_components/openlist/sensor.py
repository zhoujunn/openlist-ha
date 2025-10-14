from __future__ import annotations
import logging
from datetime import datetime
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, TASK_TYPES, SENSOR_TYPE_DONE, SENSOR_TYPE_UNDONE, SENSOR_TYPE_FAILED, SENSOR_TYPE_TRACK_DIR

_LOGGER = logging.getLogger(DOMAIN)

async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """从配置项设置传感器实体"""
    _LOGGER.debug("开始设置OpenList传感器")
    try:
        data = hass.data[DOMAIN][entry.entry_id]
        file_coordinator = data["file_coordinator"]
        task_coordinator = data["task_coordinator"]
        track_dirs_coordinators = data.get("track_dirs_coordinators", {})
        track_dirs = data.get("track_dirs", [])
        
        if not file_coordinator or not task_coordinator:
            _LOGGER.error("无法获取协调器实例，传感器设置失败")
            return
        
        # 创建传感器实体列表
        sensors = []
        
        # 原有的文件数量传感器
        sensors.append(OpenListFilesSensor(file_coordinator, entry.title))
        
        # 新增：为每种任务类型创建已完成、未完成和已失败任务传感器
        for task_type, task_name in TASK_TYPES.items():
            sensors.append(OpenListTaskSensor(
                task_coordinator, 
                entry.title, 
                task_type, 
                task_name, 
                SENSOR_TYPE_DONE
            ))
            sensors.append(OpenListTaskSensor(
                task_coordinator,
                entry.title,
                task_type,
                task_name, 
                SENSOR_TYPE_UNDONE
            ))
            sensors.append(OpenListTaskSensor(
                task_coordinator,
                entry.title,
                task_type,
                task_name, 
                SENSOR_TYPE_FAILED
            ))
        
        # 新增：为每个跟踪目录创建文件数量传感器
        for dir_path, coordinator in track_dirs_coordinators.items():
            sensors.append(OpenListTrackDirSensor(
                coordinator,
                entry.title,
                dir_path
            ))
            
        async_add_entities(sensors, update_before_add=True)
        _LOGGER.debug("OpenList传感器设置完成，共创建%d个传感器", len(sensors))
        _LOGGER.debug("跟踪目录传感器: %s", [dir_path for dir_path in track_dirs])
        
    except Exception as err:
        _LOGGER.error("传感器设置过程出错: %s", str(err), exc_info=True)


class OpenListFilesSensor(CoordinatorEntity, Entity):
    """OpenList根目录文件数量传感器（原有传感器）"""
    
    def __init__(self, coordinator, name: str):
        super().__init__(coordinator)
        self._source_name = name
        self._attr_name = f"根目录文件数"
        self._attr_unique_id = f"{DOMAIN}_{name}_root_files".replace(
            ":", "_"
        ).replace("/", "_").replace(".", "_").replace("-", "_")
        # 自定义最后更新时间戳
        self._last_updated: float | None = None
        
        _LOGGER.debug(
            "初始化文件传感器: 名称=%s | 唯一ID=%s",
            self._attr_name, self._attr_unique_id
        )

    async def async_added_to_hass(self) -> None:
        """当传感器添加到HA时调用，注册更新回调"""
        await super().async_added_to_hass()
        # 监听协调器更新，记录自定义时间戳
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """协调器数据更新时调用，更新自定义时间戳"""
        self._last_updated = datetime.now().timestamp()
        self.async_write_ha_state()

    @property
    def state(self):
        """返回传感器状态（文件数量）"""
        try:
            data = self.coordinator.data
            _LOGGER.debug(f"文件传感器原始数据: {str(data)[:500]}")

            if isinstance(data, dict) and data.get("code") == 401:
                _LOGGER.warning(f"认证失败: {data.get('message')}")
                return -1

            if not isinstance(data, dict):
                _LOGGER.warning(f"数据格式错误，预期dict，实际{type(data).__name__}")
                return 0

            api_data = data.get("data")
            if api_data is None:
                _LOGGER.warning("缺少'data'字段")
                return 0

            if not isinstance(api_data, dict):
                _LOGGER.warning(f"'data'不是字典，实际{type(api_data).__name__}")
                return 0

            content = api_data.get("content", [])
            if not isinstance(content, list):
                content = []

            return len(content)

        except Exception as err:
            _LOGGER.error(f"计算文件状态出错: {err}", exc_info=True)
            return 0

    @property
    def extra_state_attributes(self):
        """返回额外状态属性"""
        try:
            data = self.coordinator.data
            _LOGGER.debug(f"提取文件属性数据: {str(data)[:500]}")

            if not isinstance(data, dict):
                return {
                    "状态": "数据无效",
                    "错误详情": f"预期dict，实际{type(data).__name__}",
                    "最后更新时间": self._format_timestamp(self._last_updated)
                }

            if data.get("code") == 401:
                return {
                    "状态": "认证失败",
                    "错误详情": data.get("message", "未知错误"),
                    "最后更新时间": self._format_timestamp(self._last_updated)
                }

            api_data = data.get("data")
            if api_data is None:
                return {
                    "状态": "数据不完整",
                    "错误详情": "缺少'data'字段",
                    "最后更新时间": self._format_timestamp(self._last_updated)
                }

            if not isinstance(api_data, dict):
                return {
                    "状态": "数据格式错误",
                    "错误详情": f"'data'不是字典，实际{type(api_data).__name__}",
                    "最后更新时间": self._format_timestamp(self._last_updated)
                }

            content = api_data.get("content", [])
            if not isinstance(content, list):
                content = []

            file_names = [
                item.get("name") 
                for item in content
                if isinstance(item, dict) and "name" in item
            ]

            modified_times = [
                item.get("modified") 
                for item in content 
                if isinstance(item, dict) and "modified" in item and item["modified"]
            ]
            latest_modified = max(modified_times) if modified_times else None

            return {
                "文件列表": file_names,
                "文件总数": len(content),
                "最新修改时间": latest_modified,
                "更新状态": "成功" if self.coordinator.last_update_success else "失败",
                "最后更新时间": self._format_timestamp(self._last_updated),
                "传感器可用": self.available
            }

        except Exception as err:
            _LOGGER.error(f"获取文件属性出错: {err}", exc_info=True)
            return {
                "状态": "获取属性失败",
                "错误信息": str(err),
                "最后更新时间": self._format_timestamp(self._last_updated)
            }

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success 
            and isinstance(self.coordinator.data, dict)
            and self.coordinator.data.get("code") != 401
        )

    @property
    def icon(self) -> str:
        return "mdi:folder-file"

    @property
    def should_poll(self) -> bool:
        return False

    def _format_timestamp(self, timestamp: float | None) -> str | None:
        """格式化自定义时间戳"""
        if timestamp is None:
            return "从未更新"
        try:
            local_time = datetime.fromtimestamp(timestamp)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as err:
            _LOGGER.error(f"格式化时间失败: {err}")
            return str(timestamp)


class OpenListTaskSensor(CoordinatorEntity, Entity):
    """OpenList任务数量传感器"""
    
    def __init__(self, coordinator, source_name: str, task_type: str, task_name: str, sensor_type: str):
        super().__init__(coordinator)
        self._source_name = source_name
        self._task_type = task_type
        self._task_name = task_name
        self._sensor_type = sensor_type
        
        # 设置传感器属性
        if sensor_type == SENSOR_TYPE_DONE:
            self._attr_name = f"{task_name} 已完成任务"
            self._state_key = f"{task_type}_done"
            self._details_key = f"{task_type}_done_details"
            self._failed_key = f"{task_type}_failed"  # 用于计算实际完成数量
            self._target_state = 2  # 已完成任务的状态为2
        elif sensor_type == SENSOR_TYPE_UNDONE:
            self._attr_name = f"{task_name} 未完成任务" 
            self._state_key = f"{task_type}_undone"
            self._details_key = f"{task_type}_undone_details"
            self._target_state = 1  # 未完成任务的状态为1
        else:  # SENSOR_TYPE_FAILED
            self._attr_name = f"{task_name} 已失败任务"
            self._state_key = f"{task_type}_failed"
            self._details_key = f"{task_type}_failed_details"
            self._target_state = None  # 失败任务没有固定状态值，通过其他方式筛选
            
        self._attr_unique_id = f"{DOMAIN}_{source_name}_{task_type}_{sensor_type}".replace(
            ":", "_"
        ).replace("/", "_").replace(".", "_").replace("-", "_")
        
        # 自定义最后更新时间戳
        self._last_updated: float | None = None
        
        _LOGGER.debug(
            "初始化任务传感器: 名称=%s | 唯一ID=%s | 任务类型=%s | 传感器类型=%s | 目标状态=%s",
            self._attr_name, self._attr_unique_id, task_type, sensor_type, self._target_state
        )

    async def async_added_to_hass(self) -> None:
        """当传感器添加到HA时调用，注册更新回调"""
        await super().async_added_to_hass()
        # 监听协调器更新，记录自定义时间戳
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """协调器数据更新时调用，更新自定义时间戳"""
        self._last_updated = datetime.now().timestamp()
        self.async_write_ha_state()

    @property
    def state(self):
        """返回传感器状态（任务数量）"""
        try:
            data = self.coordinator.data
            
            if not isinstance(data, dict):
                _LOGGER.warning(f"任务数据格式错误，预期dict，实际{type(data).__name__}")
                return 0
            
            if self._sensor_type == SENSOR_TYPE_DONE:
                # 已完成任务数量 = 总完成数 - 失败数
                total_done = data.get(self._state_key, 0)
                failed_count = data.get(self._failed_key, 0)
                actual_done = total_done - failed_count
                
                if not isinstance(total_done, int) or not isinstance(failed_count, int):
                    _LOGGER.warning(f"任务数量不是整数: 总完成={total_done}, 失败={failed_count}")
                    return 0
                    
                return max(0, actual_done)  # 确保不会出现负数
            else:
                count = data.get(self._state_key, 0)
                if not isinstance(count, int):
                    _LOGGER.warning(f"任务数量不是整数: {count}")
                    return 0
                    
                return count

        except Exception as err:
            _LOGGER.error(f"计算任务状态出错: {err}", exc_info=True)
            return 0

    @property
    def extra_state_attributes(self):
        """返回额外状态属性 - 只显示当前任务类型的信息，并过滤状态"""
        try:
            data = self.coordinator.data
            
            if not isinstance(data, dict):
                return {
                    "状态": "数据无效",
                    "错误详情": f"预期dict，实际{type(data).__name__}",
                    "最后更新时间": self._format_timestamp(self._last_updated),
                    "任务类型": self._task_type,
                    "任务名称": self._task_name,
                    "传感器类型": self._get_sensor_type_name()
                }

            # 计算当前任务类型的统计信息
            total_done = data.get(f"{self._task_type}_done", 0)
            failed_count = data.get(f"{self._task_type}_failed", 0)
            actual_done = max(0, total_done - failed_count)  # 实际完成数
            undone_count = data.get(f"{self._task_type}_undone", 0)
            
            task_stats = {
                "实际完成": actual_done,
                "已失败": failed_count,
                "未完成": undone_count,
                "总计": actual_done + failed_count + undone_count,
                "原始完成总数": total_done  # 新增：显示原始完成总数（包含失败）
            }

            # 获取当前任务类型的详细信息
            task_details = []
            details_data = data.get(self._details_key, [])
            
            if isinstance(details_data, list):
                if self._sensor_type == SENSOR_TYPE_FAILED:
                    # 对于失败任务，直接使用已筛选好的数据
                    filtered_tasks = details_data
                elif self._sensor_type == SENSOR_TYPE_DONE:
                    # 对于已完成任务，只显示状态为2的成功任务
                    filtered_tasks = [
                        task for task in details_data 
                        if isinstance(task, dict) and task.get("state") == 2
                    ]
                else:  # SENSOR_TYPE_UNDONE
                    # 对于未完成任务，过滤状态为1的任务
                    filtered_tasks = [
                        task for task in details_data 
                        if isinstance(task, dict) and task.get("state") == 1
                    ]
                
                task_details = [
                    {
                        "id": task.get("id"),
                        "name": task.get("name"),
                        "progress": f"{task.get('progress', 0):.1f}%",
                        "status": task.get("status"),
                        "state": task.get("state"),  # 显示状态值
                        "start_time": task.get("start_time"),
                        "end_time": task.get("end_time") if self._sensor_type in [SENSOR_TYPE_DONE, SENSOR_TYPE_FAILED] else None,
                        "total_bytes": task.get("total_bytes"),
                        "error": task.get("error", "")
                    } for task in filtered_tasks[:20]  # 显示前20个任务，避免属性过大
                ]

            return {
                "任务类型": self._task_type,
                "任务名称": self._task_name,
                "传感器类型": self._get_sensor_type_name(),
                "目标状态": self._target_state,  # 显示过滤的状态
                "任务统计": task_stats,
                "任务列表": task_details,
                "更新状态": "成功" if self.coordinator.last_update_success else "失败",
                "最后更新时间": self._format_timestamp(self._last_updated),
                "传感器可用": self.available
            }

        except Exception as err:
            _LOGGER.error(f"获取任务属性出错: {err}", exc_info=True)
            return {
                "状态": "获取属性失败",
                "错误信息": str(err),
                "最后更新时间": self._format_timestamp(self._last_updated),
                "任务类型": self._task_type,
                "任务名称": self._task_name,
                "传感器类型": self._get_sensor_type_name()
            }

    def _get_sensor_type_name(self):
        """获取传感器类型名称"""
        if self._sensor_type == SENSOR_TYPE_DONE:
            return "已完成"
        elif self._sensor_type == SENSOR_TYPE_UNDONE:
            return "未完成"
        else:  # SENSOR_TYPE_FAILED
            return "已失败"

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success 
            and isinstance(self.coordinator.data, dict)
        )

    @property
    def icon(self) -> str:
        if self._sensor_type == SENSOR_TYPE_DONE:
            return "mdi:check-circle-outline"
        elif self._sensor_type == SENSOR_TYPE_UNDONE:
            return "mdi:progress-clock"
        else:  # SENSOR_TYPE_FAILED
            return "mdi:alert-circle-outline"

    @property
    def should_poll(self) -> bool:
        return False

    def _format_timestamp(self, timestamp: float | None) -> str | None:
        """格式化自定义时间戳"""
        if timestamp is None:
            return "从未更新"
        try:
            local_time = datetime.fromtimestamp(timestamp)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as err:
            _LOGGER.error(f"格式化时间失败: {err}")
            return str(timestamp)


class OpenListTrackDirSensor(CoordinatorEntity, Entity):
    """OpenList跟踪目录文件数量传感器"""
    
    def __init__(self, coordinator, source_name: str, dir_path: str):
        super().__init__(coordinator)
        self._source_name = source_name
        self._dir_path = dir_path
        
        # 设置传感器属性
        self._attr_name = f"目录文件数: {dir_path}"
        self._attr_unique_id = f"{DOMAIN}_{source_name}_track_dir_{dir_path.replace('/', '_')}".replace(
            ":", "_"
        ).replace(".", "_").replace("-", "_")
        
        # 自定义最后更新时间戳
        self._last_updated: float | None = None
        
        _LOGGER.debug(
            "初始化跟踪目录传感器: 名称=%s | 唯一ID=%s | 目录路径=%s",
            self._attr_name, self._attr_unique_id, dir_path
        )

    async def async_added_to_hass(self) -> None:
        """当传感器添加到HA时调用，注册更新回调"""
        await super().async_added_to_hass()
        # 监听协调器更新，记录自定义时间戳
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """协调器数据更新时调用，更新自定义时间戳"""
        self._last_updated = datetime.now().timestamp()
        self.async_write_ha_state()

    @property
    def state(self):
        """返回传感器状态（文件数量）"""
        try:
            data = self.coordinator.data
            _LOGGER.debug(f"跟踪目录传感器原始数据 [目录: {self._dir_path}]: {str(data)[:500]}")

            if isinstance(data, dict) and data.get("code") == 401:
                _LOGGER.warning(f"认证失败 [目录: {self._dir_path}]: {data.get('message')}")
                return -1

            if not isinstance(data, dict):
                _LOGGER.warning(f"数据格式错误 [目录: {self._dir_path}]，预期dict，实际{type(data).__name__}")
                return 0

            api_data = data.get("data")
            if api_data is None:
                _LOGGER.warning(f"缺少'data'字段 [目录: {self._dir_path}]")
                return 0

            if not isinstance(api_data, dict):
                _LOGGER.warning(f"'data'不是字典 [目录: {self._dir_path}]，实际{type(api_data).__name__}")
                return 0

            content = api_data.get("content", [])
            if not isinstance(content, list):
                content = []

            return len(content)

        except Exception as err:
            _LOGGER.error(f"计算跟踪目录状态出错 [目录: {self._dir_path}]: {err}", exc_info=True)
            return 0

    @property
    def extra_state_attributes(self):
        """返回额外状态属性"""
        try:
            data = self.coordinator.data
            _LOGGER.debug(f"提取跟踪目录属性数据 [目录: {self._dir_path}]: {str(data)[:500]}")

            if not isinstance(data, dict):
                return {
                    "状态": "数据无效",
                    "错误详情": f"预期dict，实际{type(data).__name__}",
                    "最后更新时间": self._format_timestamp(self._last_updated),
                    "目录路径": self._dir_path
                }

            if data.get("code") == 401:
                return {
                    "状态": "认证失败",
                    "错误详情": data.get("message", "未知错误"),
                    "最后更新时间": self._format_timestamp(self._last_updated),
                    "目录路径": self._dir_path
                }

            api_data = data.get("data")
            if api_data is None:
                return {
                    "状态": "数据不完整",
                    "错误详情": "缺少'data'字段",
                    "最后更新时间": self._format_timestamp(self._last_updated),
                    "目录路径": self._dir_path
                }

            if not isinstance(api_data, dict):
                return {
                    "状态": "数据格式错误",
                    "错误详情": f"'data'不是字典，实际{type(api_data).__name__}",
                    "最后更新时间": self._format_timestamp(self._last_updated),
                    "目录路径": self._dir_path
                }

            content = api_data.get("content", [])
            if not isinstance(content, list):
                content = []

            file_names = [
                item.get("name") 
                for item in content
                if isinstance(item, dict) and "name" in item
            ]

            modified_times = [
                item.get("modified") 
                for item in content 
                if isinstance(item, dict) and "modified" in item and item["modified"]
            ]
            latest_modified = max(modified_times) if modified_times else None

            return {
                "目录路径": self._dir_path,
                "文件列表": file_names,
                "文件总数": len(content),
                "最新修改时间": latest_modified,
                "更新状态": "成功" if self.coordinator.last_update_success else "失败",
                "最后更新时间": self._format_timestamp(self._last_updated),
                "传感器可用": self.available
            }

        except Exception as err:
            _LOGGER.error(f"获取跟踪目录属性出错 [目录: {self._dir_path}]: {err}", exc_info=True)
            return {
                "状态": "获取属性失败",
                "错误信息": str(err),
                "最后更新时间": self._format_timestamp(self._last_updated),
                "目录路径": self._dir_path
            }

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success 
            and isinstance(self.coordinator.data, dict)
            and self.coordinator.data.get("code") != 401
        )

    @property
    def icon(self) -> str:
        return "mdi:folder-search"

    @property
    def should_poll(self) -> bool:
        return False

    def _format_timestamp(self, timestamp: float | None) -> str | None:
        """格式化自定义时间戳"""
        if timestamp is None:
            return "从未更新"
        try:
            local_time = datetime.fromtimestamp(timestamp)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as err:
            _LOGGER.error(f"格式化时间失败: {err}")
            return str(timestamp)