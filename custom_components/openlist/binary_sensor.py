"""OpenList 二进制传感器。"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TASK_TYPES

_LOGGER = logging.getLogger(DOMAIN)


class _OpenListBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data
        return isinstance(data, dict) and data.get("code") != 401


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    task_coordinator = data["task_coordinator"]
    file_coordinator = data["file_coordinator"]
    device_info = data.get("device_info")

    sensors = [
        OpenListHasFailedTasksSensor(task_coordinator, entry.title),
        OpenListHasRunningTasksSensor(task_coordinator, entry.title),
        OpenListServerOnlineSensor(file_coordinator, entry.title),
    ]

    if device_info:
        for s in sensors:
            s._attr_device_info = device_info

    async_add_entities(sensors, update_before_add=False)
    _LOGGER.debug("OpenList 二进制传感器已创建: %d 个", len(sensors))


class OpenListHasFailedTasksSensor(_OpenListBaseBinarySensor):
    """任一任务类型存在失败任务时为 ON。"""
    _attr_icon = "mdi:alert-circle"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, source_name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = "有失败任务"
        self._attr_unique_id = (
            f"{DOMAIN}_{source_name}_has_failed_tasks"
            .replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
        )

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return False
        total_failed = sum(
            data.get(f"{t}_failed", 0) or 0 for t in TASK_TYPES
        )
        return total_failed > 0

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        details = {}
        for t, name in TASK_TYPES.items():
            count = data.get(f"{t}_failed", 0) or 0
            if count:
                details[name] = count
        return {"失败任务统计": details}


class OpenListHasRunningTasksSensor(_OpenListBaseBinarySensor):
    """任一任务类型有未完成任务时为 ON。"""
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator, source_name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = "有正在运行的任务"
        self._attr_unique_id = (
            f"{DOMAIN}_{source_name}_has_running_tasks"
            .replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
        )

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return False
        total_undone = sum(
            data.get(f"{t}_undone", 0) or 0 for t in TASK_TYPES
        )
        return total_undone > 0

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        details = {}
        for t, name in TASK_TYPES.items():
            count = data.get(f"{t}_undone", 0) or 0
            if count:
                details[name] = count
        return {"运行中任务统计": details}


class OpenListServerOnlineSensor(_OpenListBaseBinarySensor):
    """OpenList 服务器是否可正常访问。"""
    _attr_icon = "mdi:server"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, source_name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = "服务器在线"
        self._attr_unique_id = (
            f"{DOMAIN}_{source_name}_server_online"
            .replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")
        )

    @property
    def is_on(self) -> bool:
        return (
            self.coordinator.last_update_success
            and isinstance(self.coordinator.data, dict)
            and self.coordinator.data.get("code") == 200
        )