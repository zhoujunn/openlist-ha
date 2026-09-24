"""OpenList 按钮实体。"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TASK_TYPES

_LOGGER = logging.getLogger(DOMAIN)


def _safety_key(s: str) -> str:
    return s.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    device_info = data.get("device_info")

    buttons: list[ButtonEntity] = []
    for task_type, task_name in TASK_TYPES.items():
        buttons.append(OpenListRetryFailedButton(api, entry.title, task_type, task_name))
        buttons.append(OpenListClearDoneButton(api, entry.title, task_type, task_name))

    if device_info:
        for b in buttons:
            b._attr_device_info = device_info

    async_add_entities(buttons, update_before_add=False)
    _LOGGER.debug("OpenList 按钮已创建: %d 个", len(buttons))


class _OpenListBaseButton(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, api, source_name: str, task_type: str, task_name: str) -> None:
        self._api = api
        self._task_type = task_type
        self._task_name = task_name

    async def _send_notification(self, message: str) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": "OpenList 按钮操作", "message": message},
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("发送按钮通知失败: %s", err)


class OpenListRetryFailedButton(_OpenListBaseButton):
    _attr_icon = "mdi:restart-alert"

    def __init__(self, api, source_name: str, task_type: str, task_name: str) -> None:
        super().__init__(api, source_name, task_type, task_name)
        self._attr_name = f"{task_name} 重试失败任务"
        self._attr_unique_id = _safety_key(
            f"{DOMAIN}_{source_name}_{task_type}_retry_failed_button"
        )

    async def async_press(self) -> None:
        _LOGGER.info("按钮触发: 重试 %s 失败任务", self._task_name)
        try:
            result = await self._api.async_retry_failed_tasks(self._task_type)
            if isinstance(result, dict) and result.get("code") == 200:
                await self._send_notification(
                    f"**{self._task_name}** 失败任务已提交重试。"
                )
            else:
                _LOGGER.warning("重试失败任务返回异常: %s", str(result)[:200])
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("重试 %s 失败任务出错: %s", self._task_name, err, exc_info=True)


class OpenListClearDoneButton(_OpenListBaseButton):
    _attr_icon = "mdi:broom"

    def __init__(self, api, source_name: str, task_type: str, task_name: str) -> None:
        super().__init__(api, source_name, task_type, task_name)
        self._attr_name = f"{task_name} 清除已完成任务"
        self._attr_unique_id = _safety_key(
            f"{DOMAIN}_{source_name}_{task_type}_clear_done_button"
        )

    async def async_press(self) -> None:
        _LOGGER.info("按钮触发: 清除 %s 已完成任务", self._task_name)
        try:
            result = await self._api.async_clear_done_tasks(self._task_type)
            if isinstance(result, dict) and result.get("code") == 200:
                await self._send_notification(
                    f"**{self._task_name}** 已完成任务已清除。"
                )
            else:
                _LOGGER.warning("清除已完成任务返回异常: %s", str(result)[:200])
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("清除 %s 已完成任务出错: %s", self._task_name, err, exc_info=True)