"""OpenList 诊断信息导出。"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN, CONF_HOST, CONF_USERNAME, CONF_TRACK_DIRS, CONF_UPDATE_INTERVAL,
    TASK_TYPES,
)

_LOGGER = logging.getLogger(DOMAIN)


def _coordinator_summary(coordinator) -> dict[str, Any]:
    if coordinator is None:
        return {"存在": False}
    data = coordinator.data
    summary: dict[str, Any] = {
        "存在": True,
        "名称": coordinator.name,
        "最后更新成功": coordinator.last_update_success,
        "最后更新时间": datetime.now().isoformat() if coordinator.last_update_success else None,
        "数据类型": type(data).__name__ if data is not None else "None",
    }
    if isinstance(data, dict):
        summary["响应码"] = data.get("code")
        inner = data.get("data")
        if isinstance(inner, list):
            summary["记录数"] = len(inner)
        elif isinstance(inner, dict):
            summary["字段"] = sorted(inner.keys())[:20]
    return summary


def _token_status(api) -> dict[str, Any]:
    """返回令牌状态信息。"""
    if api is None:
        return {"存在": False}

    token = getattr(api, "_token", None)
    obtained_at = getattr(api, "_token_obtained_at", None)
    ttl = getattr(api, "_token_ttl", 0)

    if not token or not obtained_at:
        return {
            "存在": True,
            "已登录": False,
            "令牌获取时间": None,
            "令牌剩余有效期(秒)": 0,
            "令牌剩余有效期(小时)": 0.0,
        }

    elapsed = time.time() - obtained_at
    remaining = max(0, ttl - elapsed)

    return {
        "存在": True,
        "已登录": True,
        "令牌获取时间": datetime.fromtimestamp(obtained_at).isoformat(),
        "令牌已用时间(秒)": round(elapsed, 1),
        "令牌剩余有效期(秒)": round(remaining, 1),
        "令牌剩余有效期(小时)": round(remaining / 3600, 2),
        "令牌总有效期(小时)": round(ttl / 3600, 2),
        "已过刷新阈值": elapsed > ttl * 0.5,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry,
) -> dict[str, Any]:
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})

    diagnostics: dict[str, Any] = {
        "集成": {"版本": "1.2.1", "域名": DOMAIN},
        "配置": {
            "标题": entry.title,
            "主机": entry.data.get(CONF_HOST),
            "用户名": entry.data.get(CONF_USERNAME),
            "跟踪目录": entry.data.get(CONF_TRACK_DIRS, []),
            "轮询间隔(分钟)": entry.options.get(CONF_UPDATE_INTERVAL, "默认(5)"),
            "Options": dict(entry.options),
        },
        "任务类型": list(TASK_TYPES.keys()),
        "协调器": {
            "文件": _coordinator_summary(entry_data.get("file_coordinator")),
            "任务": _coordinator_summary(entry_data.get("task_coordinator")),
            "存储": _coordinator_summary(entry_data.get("storage_coordinator")),
            "跟踪目录数量": len(entry_data.get("track_dirs_coordinators", {})),
            "跟踪目录列表": list(entry_data.get("track_dirs_coordinators", {}).keys()),
        },
        "API 状态": _token_status(entry_data.get("api")),
    }

    track_summaries = {}
    for path, coord in entry_data.get("track_dirs_coordinators", {}).items():
        track_summaries[path] = _coordinator_summary(coord)
    diagnostics["跟踪目录协调器"] = track_summaries

    return diagnostics