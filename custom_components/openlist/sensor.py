from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, TASK_TYPES,
    SENSOR_TYPE_DONE, SENSOR_TYPE_UNDONE, SENSOR_TYPE_FAILED,
)

_LOGGER = logging.getLogger(DOMAIN)


# ---------------------------------------------------------------------------
# 通用基类
# ---------------------------------------------------------------------------
class _OpenListBaseSensor(CoordinatorEntity, Entity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._last_updated: float | None = None

    def _handle_coordinator_update(self) -> None:
        self._last_updated = datetime.now().timestamp()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data
        return isinstance(data, dict) and data.get("code") != 401

    def _format_timestamp(self, ts: float | None) -> str:
        if ts is None:
            return "从未更新"
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:  # noqa: BLE001
            return str(ts)

    @staticmethod
    def _safety_key(s: str) -> str:
        return s.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# 根目录文件数传感器
# ---------------------------------------------------------------------------
class OpenListFilesSensor(_OpenListBaseSensor):
    _attr_icon = "mdi:folder-file"

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = "根目录文件数"
        self._attr_unique_id = self._safety_key(f"{DOMAIN}_{name}_root_files")

    def _get_content(self) -> list | None:
        data = self.coordinator.data
        if not isinstance(data, dict) or data.get("code") == 401:
            return None
        api_data = data.get("data")
        if not isinstance(api_data, dict):
            return None
        content = api_data.get("content", [])
        return content if isinstance(content, list) else []

    @property
    def state(self) -> int:
        content = self._get_content()
        return len(content) if content is not None else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        content = self._get_content()
        if content is None:
            return {"状态": "数据无效",
                    "最后更新时间": self._format_timestamp(self._last_updated)}
        file_names = [i.get("name") for i in content if isinstance(i, dict) and "name" in i]
        modified = [i.get("modified") for i in content
                    if isinstance(i, dict) and i.get("modified")]
        return {
            "文件列表": file_names[:50],
            "文件总数": len(content),
            "最新修改时间": max(modified) if modified else None,
            "最后更新时间": self._format_timestamp(self._last_updated),
        }


# ---------------------------------------------------------------------------
# 任务数量传感器
# ---------------------------------------------------------------------------
class OpenListTaskSensor(_OpenListBaseSensor):

    def __init__(self, coordinator, source_name: str, task_type: str,
                 task_name: str, sensor_type: str) -> None:
        super().__init__(coordinator)
        self._task_type = task_type
        self._task_name = task_name
        self._sensor_type = sensor_type

        if sensor_type == SENSOR_TYPE_DONE:
            self._attr_name = f"{task_name} 已完成任务"
            self._state_key = f"{task_type}_done"
            self._details_key = f"{task_type}_done_details"
            self._attr_icon = "mdi:check-circle-outline"
        elif sensor_type == SENSOR_TYPE_UNDONE:
            self._attr_name = f"{task_name} 未完成任务"
            self._state_key = f"{task_type}_undone"
            self._details_key = f"{task_type}_undone_details"
            self._attr_icon = "mdi:progress-clock"
        else:
            self._attr_name = f"{task_name} 已失败任务"
            self._state_key = f"{task_type}_failed"
            self._details_key = f"{task_type}_failed_details"
            self._attr_icon = "mdi:alert-circle-outline"

        self._attr_unique_id = self._safety_key(
            f"{DOMAIN}_{source_name}_{task_type}_{sensor_type}"
        )

    @property
    def state(self) -> int:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return 0

        if self._sensor_type == SENSOR_TYPE_DONE:
            total = data.get(f"{self._task_type}_done", 0)
            failed = data.get(f"{self._task_type}_failed", 0)
            if not isinstance(total, int) or not isinstance(failed, int):
                return 0
            return max(0, total - failed)

        val = data.get(self._state_key, 0)
        return val if isinstance(val, int) else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return {"任务类型": self._task_type, "任务名称": self._task_name,
                    "最后更新时间": self._format_timestamp(self._last_updated)}

        details = data.get(self._details_key, [])
        filtered: list[dict] = []
        if isinstance(details, list):
            if self._sensor_type == SENSOR_TYPE_FAILED:
                filtered = [t for t in details if isinstance(t, dict)]
            elif self._sensor_type == SENSOR_TYPE_DONE:
                filtered = [t for t in details if isinstance(t, dict) and t.get("state") == 2]
            else:
                filtered = [t for t in details if isinstance(t, dict) and t.get("state") == 1]

        task_list = [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "progress": f"{t.get('progress', 0):.1f}%",
                "state": t.get("state"),
                "start_time": t.get("start_time"),
                "end_time": t.get("end_time"),
                "error": t.get("error", ""),
            }
            for t in filtered[:10]
        ]

        return {
            "任务类型": self._task_type,
            "任务名称": self._task_name,
            "传感器类型": self._sensor_type,
            "任务列表": task_list,
            "任务数量": len(filtered),
            "最后更新时间": self._format_timestamp(self._last_updated),
        }


# ---------------------------------------------------------------------------
# 进度百分比传感器
# ---------------------------------------------------------------------------
class OpenListTaskProgressSensor(_OpenListBaseSensor):
    _attr_icon = "mdi:progress-check"
    _attr_unit_of_measurement = "%"

    def __init__(self, coordinator, source_name: str, task_type: str, task_name: str) -> None:
        super().__init__(coordinator)
        self._task_type = task_type
        self._task_name = task_name
        self._attr_name = f"{task_name} 已完成进度"
        self._attr_unique_id = self._safety_key(
            f"{DOMAIN}_{source_name}_{task_type}_progress"
        )

    def _calc(self) -> tuple[float, dict[str, int]]:
        data = self.coordinator.data or {}
        if not isinstance(data, dict):
            return 0.0, {"实际完成": 0, "已失败": 0, "未完成": 0, "总计": 0}
        total = data.get(f"{self._task_type}_done", 0) or 0
        failed = data.get(f"{self._task_type}_failed", 0) or 0
        undone = data.get(f"{self._task_type}_undone", 0) or 0
        done = max(0, total - failed)
        grand = done + failed + undone
        pct = round(done / grand * 100, 1) if grand else 0.0
        return pct, {"实际完成": done, "已失败": failed, "未完成": undone, "总计": grand}

    @property
    def state(self) -> float:
        return self._calc()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pct, stats = self._calc()
        stats["进度百分比"] = f"{pct:.1f}%"
        return {
            "任务类型": self._task_type,
            "任务名称": self._task_name,
            "任务统计": stats,
            "最后更新时间": self._format_timestamp(self._last_updated),
        }


# ---------------------------------------------------------------------------
# 跟踪目录传感器
# ---------------------------------------------------------------------------
class OpenListTrackDirSensor(_OpenListBaseSensor):
    _attr_icon = "mdi:folder-search"

    def __init__(self, coordinator, source_name: str, dir_path: str) -> None:
        super().__init__(coordinator)
        self._dir_path = dir_path
        self._attr_name = f"目录文件数: {dir_path}"
        self._attr_unique_id = self._safety_key(
            f"{DOMAIN}_{source_name}_track_dir_{dir_path}"
        )

    def _get_content(self) -> list | None:
        data = self.coordinator.data
        if not isinstance(data, dict) or data.get("code") == 401:
            return None
        api_data = data.get("data")
        if not isinstance(api_data, dict):
            return None
        content = api_data.get("content", [])
        return content if isinstance(content, list) else []

    @property
    def state(self) -> int:
        content = self._get_content()
        return len(content) if content is not None else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        content = self._get_content()
        if content is None:
            return {"目录路径": self._dir_path,
                    "最后更新时间": self._format_timestamp(self._last_updated)}
        file_names = [i.get("name") for i in content if isinstance(i, dict) and "name" in i]
        modified = [i.get("modified") for i in content
                    if isinstance(i, dict) and i.get("modified")]
        return {
            "目录路径": self._dir_path,
            "文件列表": file_names[:50],
            "文件总数": len(content),
            "最新修改时间": max(modified) if modified else None,
            "最后更新时间": self._format_timestamp(self._last_updated),
        }


# ---------------------------------------------------------------------------
# 存储状态传感器
# ---------------------------------------------------------------------------
class OpenListStorageSensor(_OpenListBaseSensor):
    """监控单个存储挂载点的在线/离线状态。"""

    _attr_icon = "mdi:harddisk"

    def __init__(self, coordinator, source_name: str, storage: dict) -> None:
        super().__init__(coordinator)
        self._storage_id = storage.get("id")
        self._mount_path = storage.get("mount_path") or "/"
        self._driver = storage.get("driver", "unknown")

        self._attr_name = f"存储状态: {self._mount_path}"
        self._attr_unique_id = self._safety_key(
            f"{DOMAIN}_{source_name}_storage_{self._mount_path}"
        )

    def _find_storage(self) -> dict | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        storages = data.get("data", [])
        if not isinstance(storages, list):
            return None
        for s in storages:
            if isinstance(s, dict) and s.get("id") == self._storage_id:
                return s
        return None

    @property
    def state(self) -> str:
        s = self._find_storage()
        if not s:
            return "unknown"
        status = (s.get("status") or "").lower()
        return "online" if status in ("work", "working", "ok") else "offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._find_storage() or {}
        return {
            "挂载路径": self._mount_path,
            "驱动类型": s.get("driver", self._driver),
            "状态": s.get("status"),
            "禁用": s.get("disabled", False),
            "排序": s.get("order"),
            "最后更新时间": self._format_timestamp(self._last_updated),
        }


# ---------------------------------------------------------------------------
# 存储数量汇总传感器
# ---------------------------------------------------------------------------
class OpenListStorageCountSensor(_OpenListBaseSensor):
    """始终创建的诊断传感器，显示存储挂载点数量。"""
    _attr_icon = "mdi:database"

    def __init__(self, coordinator, source_name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = "存储数量"
        self._attr_unique_id = self._safety_key(
            f"{DOMAIN}_{source_name}_storage_count"
        )

    @property
    def state(self) -> int:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return 0
        storages = data.get("data", [])
        return len(storages) if isinstance(storages, list) else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "最后更新时间": self._format_timestamp(self._last_updated),
            "更新状态": "成功" if self.coordinator.last_update_success else "失败",
        }
        data = self.coordinator.data
        if isinstance(data, dict):
            err = data.get("error")
            if err:
                attrs["错误"] = err
            storages = data.get("data", [])
            if isinstance(storages, list):
                attrs["存储列表"] = [
                    {
                        "id": s.get("id"),
                        "mount_path": s.get("mount_path"),
                        "driver": s.get("driver"),
                        "status": s.get("status"),
                    }
                    for s in storages[:20]
                    if isinstance(s, dict)
                ]
        return attrs


# ---------------------------------------------------------------------------
# 平台入口
# ---------------------------------------------------------------------------
async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    file_coordinator = data["file_coordinator"]
    task_coordinator = data["task_coordinator"]
    storage_coordinator = data.get("storage_coordinator")
    track_dirs_coordinators = data.get("track_dirs_coordinators", {})
    device_info = data.get("device_info")

    sensors: list[Entity] = [OpenListFilesSensor(file_coordinator, entry.title)]

    for task_type, task_name in TASK_TYPES.items():
        for sensor_type in (SENSOR_TYPE_DONE, SENSOR_TYPE_UNDONE, SENSOR_TYPE_FAILED):
            sensors.append(OpenListTaskSensor(
                task_coordinator, entry.title, task_type, task_name, sensor_type,
            ))
        sensors.append(OpenListTaskProgressSensor(
            task_coordinator, entry.title, task_type, task_name,
        ))

    for dir_path, coordinator in track_dirs_coordinators.items():
        sensors.append(OpenListTrackDirSensor(coordinator, entry.title, dir_path))

    # 存储传感器
    if storage_coordinator is not None:
        sensors.append(OpenListStorageCountSensor(storage_coordinator, entry.title))

        if isinstance(storage_coordinator.data, dict):
            storages = storage_coordinator.data.get("data", [])
            if isinstance(storages, list) and storages:
                for storage in storages:
                    if isinstance(storage, dict) and storage.get("id") is not None:
                        sensors.append(OpenListStorageSensor(
                            storage_coordinator, entry.title, storage,
                        ))
                _LOGGER.info("已创建 %d 个存储状态传感器", len(storages))
            else:
                err = storage_coordinator.data.get("error", "未知")
                _LOGGER.warning("未创建存储传感器：%s", err)

    # 挂载设备信息
    if device_info:
        for s in sensors:
            s._attr_device_info = device_info

    async_add_entities(sensors, update_before_add=False)
    _LOGGER.debug("OpenList 传感器已创建: %d 个", len(sensors))