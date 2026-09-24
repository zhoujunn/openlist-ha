from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OpenListAPI
from .const import (
    DOMAIN, PLATFORMS, CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_TRACK_DIRS, CONF_UPDATE_INTERVAL, TASK_TYPES,
    ASYNC_FILE_SERVICES, EVENT_TASK_COMPLETED,
    MANUFACTURER, MODEL,
)

_LOGGER = logging.getLogger(DOMAIN)

DEFAULT_FILE_INTERVAL_MIN = 5
DEFAULT_TASK_INTERVAL_MIN = 2
DEFAULT_STORAGE_INTERVAL_MIN = 10


# ---------------------------------------------------------------------------
# 协调器构造
# ---------------------------------------------------------------------------
def _build_file_coordinator(
    hass: HomeAssistant, api: OpenListAPI, interval_min: int
) -> DataUpdateCoordinator:
    async def _update() -> dict:
        resp = await api.async_list(path="/", page=1, per_page=0)
        if not isinstance(resp, dict) or resp.get("code") != 200:
            raise UpdateFailed(f"文件数据格式错误: {str(resp)[:200]}")
        return resp

    return DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"{DOMAIN}_file_coordinator",
        update_method=_update,
        update_interval=timedelta(minutes=interval_min),
    )


def _build_task_coordinator(hass: HomeAssistant, api: OpenListAPI) -> DataUpdateCoordinator:
    """任务协调器，同时负责检测任务完成事件。"""
    prev_done_ids: dict[str, set] = {}
    initialized = False

    async def _update() -> dict:
        nonlocal initialized
        data: dict[str, Any] = {}

        async def _fetch_one(task_type: str) -> None:
            try:
                done_resp = await api.async_get_task_done(task_type)
                done_tasks = (
                    done_resp.get("data", [])
                    if isinstance(done_resp, dict) and done_resp.get("code") == 200
                    else []
                )
                if not isinstance(done_tasks, list):
                    done_tasks = []

                failed = [t for t in done_tasks if isinstance(t, dict) and t.get("state") != 2]

                data[f"{task_type}_done"] = len(done_tasks)
                data[f"{task_type}_done_details"] = done_tasks
                data[f"{task_type}_failed"] = len(failed)
                data[f"{task_type}_failed_details"] = failed

                undone_resp = await api.async_get_task_undone(task_type)
                undone_tasks = (
                    undone_resp.get("data", [])
                    if isinstance(undone_resp, dict) and undone_resp.get("code") == 200
                    else []
                )
                if not isinstance(undone_tasks, list):
                    undone_tasks = []

                data[f"{task_type}_undone"] = len(undone_tasks)
                data[f"{task_type}_undone_details"] = undone_tasks

                # 检测新完成的任务并触发 HA 事件
                curr_ids = {t.get("id") for t in done_tasks if isinstance(t, dict) and t.get("id")}
                if initialized:
                    new_ids = curr_ids - prev_done_ids.get(task_type, set())
                    for tid in new_ids:
                        task = next(
                            (t for t in done_tasks if isinstance(t, dict) and t.get("id") == tid),
                            None,
                        )
                        if not task:
                            continue
                        state = task.get("state")
                        payload = {
                            "task_type": task_type,
                            "task_type_name": TASK_TYPES.get(task_type, task_type),
                            "task_id": tid,
                            "task_name": task.get("name"),
                            "state": state,
                            "success": state == 2,
                            "error": task.get("error", ""),
                            "start_time": task.get("start_time"),
                            "end_time": task.get("end_time"),
                        }
                        _LOGGER.info(
                            "任务完成事件 | 类型=%s | ID=%s | 成功=%s",
                            task_type, tid, state == 2,
                        )
                        hass.bus.async_fire(EVENT_TASK_COMPLETED, payload)
                prev_done_ids[task_type] = curr_ids

            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("获取 %s 任务数据失败: %s", task_type, err)
                data.update({
                    f"{task_type}_done": 0,
                    f"{task_type}_done_details": [],
                    f"{task_type}_undone": 0,
                    f"{task_type}_undone_details": [],
                    f"{task_type}_failed": 0,
                    f"{task_type}_failed_details": [],
                })

        await asyncio.gather(*(_fetch_one(t) for t in TASK_TYPES))
        initialized = True
        return data

    return DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"{DOMAIN}_task_coordinator",
        update_method=_update,
        update_interval=timedelta(minutes=DEFAULT_TASK_INTERVAL_MIN),
    )


def _build_track_dir_coordinator(
    hass: HomeAssistant, api: OpenListAPI, dir_path: str, interval_min: int,
) -> DataUpdateCoordinator:
    async def _update() -> dict:
        resp = await api.async_list(path=dir_path, page=1, per_page=0)
        if not isinstance(resp, dict) or resp.get("code") != 200:
            raise UpdateFailed(f"目录 {dir_path} 数据格式错误: {str(resp)[:200]}")
        return resp

    safe_name = dir_path.replace("/", "_").replace(" ", "_").strip("_") or "root"
    return DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"{DOMAIN}_track_dir_{safe_name}",
        update_method=_update,
        update_interval=timedelta(minutes=interval_min),
    )


def _build_storage_coordinator(hass: HomeAssistant, api: OpenListAPI) -> DataUpdateCoordinator:
    """存储状态协调器（兼容 data 为列表或 data.content 为列表两种格式）。"""

    def _extract_storages(payload: Any) -> tuple[list, str | None]:
        """从不同响应格式中提取存储列表。"""
        if not isinstance(payload, dict):
            return [], f"payload 非 dict: {type(payload).__name__}"

        data = payload.get("data")
        if data is None:
            return [], "缺少 data 字段"

        # 格式 1：data 直接是列表
        if isinstance(data, list):
            return data, None

        # 格式 2：data.content 是列表（OpenList 实际格式）
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, list):
                return content, None
            return [], f"data.content 非列表: {type(content).__name__}"

        return [], f"data 类型异常: {type(data).__name__}"

    async def _update() -> dict:
        try:
            resp = await api.async_get_storages()
            if isinstance(resp, dict) and resp.get("code") == 200:
                storages, err = _extract_storages(resp)
                if err:
                    _LOGGER.warning("存储协调器：%s | 原始响应: %s", err, str(resp)[:300])
                    return {"code": 200, "data": [], "error": err}

                _LOGGER.info("存储协调器：成功获取 %d 个存储挂载点", len(storages))
                return {"code": 200, "data": storages}

            _LOGGER.warning("存储协调器：响应异常 %s", str(resp)[:200])
            return {
                "code": 200, "data": [],
                "error": f"响应异常: {str(resp)[:200]}",
            }

        except Exception as err:  # noqa: BLE001
            _LOGGER.error("存储协调器：请求失败 %s", err, exc_info=True)
            return {
                "code": 200, "data": [],
                "error": f"{type(err).__name__}: {str(err)[:200]}",
            }

    return DataUpdateCoordinator(
        hass, _LOGGER,
        name=f"{DOMAIN}_storage_coordinator",
        update_method=_update,
        update_interval=timedelta(minutes=DEFAULT_STORAGE_INTERVAL_MIN),
    )


# ---------------------------------------------------------------------------
# 服务调用处理
# ---------------------------------------------------------------------------
def _check_required_args(call: ServiceCall, required: Iterable[str], kind: str) -> None:
    for arg in required:
        if arg not in call.data:
            raise HomeAssistantError(f"{kind}服务缺少必填参数: {arg}")


async def _send_notification(hass: HomeAssistant, title: str, message: str) -> None:
    try:
        await hass.services.async_call(
            "persistent_notification", "create",
            {"title": title, "message": message},
            blocking=False,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("发送持久通知失败: %s", err)


async def _handle_task_service(
    call: ServiceCall,
    service_func: Callable,
    required_args: list[str],
    task_types: list[str],
) -> Any:
    _check_required_args(call, required_args, "任务")

    task_type = call.data.get("task_type")
    if task_type not in task_types:
        raise HomeAssistantError(
            f"不支持的任务类型: {task_type}（支持: {task_types}）"
        )

    service_data = {k: v for k, v in call.data.items() if k != "task_type"}
    try:
        result = await service_func(task_type, **service_data)
        _LOGGER.debug("任务服务 %s 执行成功", service_func.__name__)
        return result
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("任务服务 %s 失败: %s", service_func.__name__, err, exc_info=True)
        raise HomeAssistantError(f"任务服务执行失败: {err}") from err


async def _handle_file_service(
    call: ServiceCall,
    service_func: Callable,
    required_args: list[str],
) -> Any:
    _check_required_args(call, required_args, "文件")
    try:
        result = await service_func(**call.data)
        _LOGGER.debug("文件服务 %s 执行成功", service_func.__name__)

        if service_func.__name__ in ASYNC_FILE_SERVICES:
            if isinstance(result, dict) and result.get("code") == 200:
                friendly = {
                    "async_add_offline_download": "离线下载任务",
                    "async_decompress_archive": "解压任务",
                    "async_copy_files": "复制任务",
                    "async_move_files": "移动任务",
                    "async_recursive_move": "聚合移动任务",
                    "async_regex_rename": "正则重命名任务",
                    "async_batch_rename": "批量重命名任务",
                    "async_remove_files": "删除任务",
                }.get(service_func.__name__, service_func.__name__)

                await _send_notification(
                    call.hass,
                    "OpenList 任务已提交",
                    f"**{friendly}** 已成功提交，请通过对应的任务传感器查看进度。",
                )
        return result
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("文件服务 %s 失败: %s", service_func.__name__, err, exc_info=True)
        raise HomeAssistantError(f"文件服务执行失败: {err}") from err


def _make_task_handler(func: Callable, args: list[str], task_types: list[str]) -> Callable:
    async def _handler(call: ServiceCall) -> Any:
        return await _handle_task_service(call, func, args, task_types)
    return _handler


def _make_file_handler(func: Callable, args: list[str]) -> Callable:
    async def _handler(call: ServiceCall) -> Any:
        return await _handle_file_service(call, func, args)
    return _handler


# ---------------------------------------------------------------------------
# 服务注册表
# ---------------------------------------------------------------------------
TASK_SERVICES: list[tuple[str, str, list[str]]] = [
    ("get_task_info",            "async_get_task_info",            ["task_type"]),
    ("get_task_done",            "async_get_task_done",            ["task_type"]),
    ("get_task_undone",          "async_get_task_undone",          ["task_type"]),
    ("delete_task",              "async_delete_task",              ["task_type", "tid"]),
    ("cancel_task",              "async_cancel_task",              ["task_type", "tid"]),
    ("clear_done_tasks",         "async_clear_done_tasks",         ["task_type"]),
    ("clear_succeeded_tasks",    "async_clear_succeeded_tasks",    ["task_type"]),
    ("retry_task",               "async_retry_task",               ["task_type", "tid"]),
    ("retry_failed_tasks",       "async_retry_failed_tasks",       ["task_type"]),
    ("delete_some_tasks",        "async_delete_some_tasks",        ["task_type", "tids"]),
    ("cancel_some_tasks",        "async_cancel_some_tasks",        ["task_type", "tids"]),
    ("retry_some_tasks",         "async_retry_some_tasks",         ["task_type", "tids"]),
]

FILE_SERVICES: list[tuple[str, str, list[str]]] = [
    ("mkdir",                "async_mkdir",                ["path"]),
    ("rename",               "async_rename",               ["path", "name"]),
    ("list_files",           "async_list_files",           []),
    ("get_file_info",        "async_get_file_info",        ["path"]),
    ("search_files",         "async_search_files",         ["parent", "keywords", "scope"]),
    ("get_dirs",             "async_get_dirs",             []),
    ("batch_rename",         "async_batch_rename",         ["src_dir", "rename_objects"]),
    ("regex_rename",         "async_regex_rename",         ["src_dir", "src_name_regex", "new_name_regex"]),
    ("move_files",           "async_move_files",           ["src_dir", "dst_dir", "names"]),
    ("recursive_move",       "async_recursive_move",       ["src_dir", "dst_dir"]),
    ("copy_files",           "async_copy_files",           ["src_dir", "dst_dir", "names"]),
    ("remove_files",         "async_remove_files",         ["dir_path", "names"]),
    ("remove_empty_dir",     "async_remove_empty_dir",     ["src_dir"]),
    ("add_offline_download", "async_add_offline_download", ["path", "urls", "tool", "delete_policy"]),
    ("get_archive_meta",     "async_get_archive_meta",     ["path"]),
    ("list_archive",         "async_list_archive",         ["path", "inner_path"]),
    ("decompress_archive",   "async_decompress_archive",   ["src_dir", "dst_dir", "name", "inner_path"]),
]


def _register_services(hass: HomeAssistant, api: OpenListAPI, entry: ConfigEntry) -> None:
    for service_name, method_name, required in TASK_SERVICES:
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
        hass.services.async_register(
            DOMAIN, service_name,
            _make_task_handler(getattr(api, method_name), required, api._task_types),
        )

    for service_name, method_name, required in FILE_SERVICES:
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
        hass.services.async_register(
            DOMAIN, service_name,
            _make_file_handler(getattr(api, method_name), required),
        )

    def _unregister() -> None:
        for name, _, _ in (*TASK_SERVICES, *FILE_SERVICES):
            if hass.services.has_service(DOMAIN, name):
                hass.services.async_remove(DOMAIN, name)

    entry.async_on_unload(_unregister)


# ---------------------------------------------------------------------------
# Options 更新监听
# ---------------------------------------------------------------------------
async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = OpenListAPI(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session,
    )

    # 首次登录
    await api.async_login()

    # 读取 Options 中的轮询间隔
    interval_min = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_FILE_INTERVAL_MIN))

    file_coordinator = _build_file_coordinator(hass, api, interval_min)
    task_coordinator = _build_task_coordinator(hass, api)
    storage_coordinator = _build_storage_coordinator(hass, api)

    track_dirs: list[str] = entry.data.get(CONF_TRACK_DIRS, []) or []
    track_dirs_coordinators = {
        path: _build_track_dir_coordinator(hass, api, path, interval_min)
        for path in track_dirs
    }

    # 首次刷新（并发）
    await asyncio.gather(
        file_coordinator.async_refresh(),
        task_coordinator.async_refresh(),
        storage_coordinator.async_refresh(),
        *(c.async_refresh() for c in track_dirs_coordinators.values()),
        return_exceptions=True,
    )

    # 尝试获取 OpenList 版本号
    sw_version: str | None = None
    try:
        settings = await api.async_get_public_settings()
        if isinstance(settings, dict) and settings.get("code") == 200:
            data = settings.get("data", {})
            if isinstance(data, dict):
                sw_version = data.get("version")
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("读取 OpenList 版本号失败: %s", err)

    # 构造共享 DeviceInfo
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL,
        configuration_url=entry.data.get(CONF_HOST),
        sw_version=sw_version,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "file_coordinator": file_coordinator,
        "task_coordinator": task_coordinator,
        "storage_coordinator": storage_coordinator,
        "track_dirs_coordinators": track_dirs_coordinators,
        "track_dirs": track_dirs,
        "device_info": device_info,
    }

    _register_services(hass, api, entry)

    # Options 变化时自动重载
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(
        "OpenList 集成初始化完成 | 跟踪目录: %d | 轮询: %d 分钟 | 版本: %s",
        len(track_dirs), interval_min, sw_version or "未知",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
        _LOGGER.info("OpenList 集成卸载完成")
    return unload_ok