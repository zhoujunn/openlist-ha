from __future__ import annotations
import logging
import asyncio
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError

from .api import OpenListAPI
from .const import DOMAIN, PLATFORMS, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_TRACK_DIRS, TASK_TYPES

_LOGGER = logging.getLogger(DOMAIN)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """初始化集成：API + 协调器 + 服务 + 平台"""
    # 1. 初始化API客户端
    session = async_get_clientsession(hass)
    api = OpenListAPI(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session
    )

    # 2. 文件数据协调器
    async def async_update_file_data():
        try:
            resp = await api.async_list(path="/", page=1, per_page=0)
            if not isinstance(resp, dict) or resp.get("code") != 200:
                raise UpdateFailed(f"文件数据格式错误: {str(resp)[:200]}")
            return resp
        except Exception as err:
            raise UpdateFailed(f"文件数据更新失败: {str(err)}")
    
    file_coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="openlist_file_coordinator",
        update_method=async_update_file_data, update_interval=timedelta(minutes=5)
    )

    # 3. 任务数据协调器
    async def async_update_task_data():
        """更新所有任务类型的状态数据"""
        try:
            task_data = {}
            
            # 为每种任务类型获取已完成、未完成和失败任务
            for task_type in TASK_TYPES.keys():
                try:
                    # 获取已完成任务
                    done_resp = await api.async_get_task_done(task_type)
                    if isinstance(done_resp, dict) and done_resp.get("code") == 200:
                        done_tasks = done_resp.get("data", [])
                        task_data[f"{task_type}_done"] = len(done_tasks) if isinstance(done_tasks, list) else 0
                        task_data[f"{task_type}_done_details"] = done_tasks if isinstance(done_tasks, list) else []
                        
                        # 从已完成任务中筛选出失败的任务（状态不为2）
                        failed_tasks = [
                            task for task in done_tasks 
                            if isinstance(task, dict) and task.get("state") != 2
                        ]
                        task_data[f"{task_type}_failed"] = len(failed_tasks)
                        task_data[f"{task_type}_failed_details"] = failed_tasks
                    else:
                        task_data[f"{task_type}_done"] = 0
                        task_data[f"{task_type}_done_details"] = []
                        task_data[f"{task_type}_failed"] = 0
                        task_data[f"{task_type}_failed_details"] = []
                    
                    # 获取未完成任务  
                    undone_resp = await api.async_get_task_undone(task_type)
                    if isinstance(undone_resp, dict) and undone_resp.get("code") == 200:
                        undone_tasks = undone_resp.get("data", [])
                        task_data[f"{task_type}_undone"] = len(undone_tasks) if isinstance(undone_tasks, list) else 0
                        task_data[f"{task_type}_undone_details"] = undone_tasks if isinstance(undone_tasks, list) else []
                    else:
                        task_data[f"{task_type}_undone"] = 0
                        task_data[f"{task_type}_undone_details"] = []
                        
                except Exception as task_err:
                    _LOGGER.warning(f"获取{task_type}任务数据失败: {task_err}")
                    task_data[f"{task_type}_done"] = 0
                    task_data[f"{task_type}_undone"] = 0
                    task_data[f"{task_type}_failed"] = 0
                    task_data[f"{task_type}_done_details"] = []
                    task_data[f"{task_type}_undone_details"] = []
                    task_data[f"{task_type}_failed_details"] = []
            
            return task_data
            
        except Exception as err:
            raise UpdateFailed(f"任务数据更新失败: {str(err)}")
    
    task_coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="openlist_task_coordinator",
        update_method=async_update_task_data, update_interval=timedelta(minutes=2)
    )

    # 4. 跟踪目录协调器 - 修复版本
    track_dirs_coordinators = {}
    track_dirs = entry.data.get(CONF_TRACK_DIRS, [])
    
    if track_dirs:
        _LOGGER.info(f"初始化跟踪目录协调器: {track_dirs}")
        
        for dir_path in track_dirs:
            # 为每个目录创建独立的更新函数
            async def async_update_dir_data(path=dir_path):
                """目录数据更新函数"""
                try:
                    resp = await api.async_list(path=path, page=1, per_page=0)
                    if not isinstance(resp, dict) or resp.get("code") != 200:
                        raise UpdateFailed(f"目录 {path} 数据格式错误: {str(resp)[:200]}")
                    return resp
                except Exception as err:
                    raise UpdateFailed(f"目录 {path} 数据更新失败: {str(err)}")
            
            # 创建协调器
            coordinator = DataUpdateCoordinator(
                hass, 
                _LOGGER, 
                name=f"openlist_track_dir_{dir_path.replace('/', '_').replace(' ', '_')}",
                update_method=async_update_dir_data,  # 直接传递函数引用
                update_interval=timedelta(minutes=5)
            )
            track_dirs_coordinators[dir_path] = coordinator

    # 5. 立即刷新协调器
    refresh_tasks = [
        file_coordinator.async_refresh(),
        task_coordinator.async_refresh()
    ]
    
    # 添加跟踪目录协调器的刷新任务
    for coordinator in track_dirs_coordinators.values():
        refresh_tasks.append(coordinator.async_refresh())
    
    await asyncio.gather(*refresh_tasks, return_exceptions=True)

    # 6. 存储数据到HA
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "file_coordinator": file_coordinator,
        "task_coordinator": task_coordinator,
        "track_dirs_coordinators": track_dirs_coordinators,  # 新增：跟踪目录协调器
        "track_dirs": track_dirs  # 新增：跟踪目录列表
    }

    # ------------------------------
    # 服务处理逻辑（区分任务类和文件类）
    # ------------------------------
    
    # 任务类服务处理函数（需要task_type校验）
    async def _async_handle_task_service(call, service_func, required_args=None):
        required_args = required_args or []
        # 校验必填参数
        for arg in required_args:
            if arg not in call.data:
                err_msg = f"任务服务缺少必填参数: {arg}"
                _LOGGER.error(err_msg)
                raise HomeAssistantError(err_msg)
        
        # 任务类型校验
        task_type = call.data.get("task_type")
        if task_type not in api._task_types:
            err_msg = f"不支持的任务类型: {task_type}（支持: {api._task_types}）"
            _LOGGER.error(err_msg)
            raise HomeAssistantError(err_msg)
        
        # 从 call.data 中移除 task_type，避免重复传递
        service_data = dict(call.data)  # 创建副本
        service_data.pop("task_type", None)  # 移除 task_type
        
        # 调用API
        try:
            _LOGGER.debug(f"调用任务服务: {service_func.__name__}, 任务类型: {task_type}")
            # 将 task_type 作为第一个位置参数传递，其他参数作为关键字参数
            result = await service_func(task_type, **service_data)
            _LOGGER.info(f"任务服务执行成功: {service_func.__name__}, 结果: {str(result)[:200]}")
            return result
        except Exception as err:
            err_msg = f"任务服务执行失败: {str(err)}"
            _LOGGER.error(err_msg, exc_info=True)
            raise HomeAssistantError(err_msg)

    # 文件类服务处理函数（不需要task_type校验）
    async def _async_handle_file_service(call, service_func, required_args=None):
        required_args = required_args or []
        # 仅校验必填参数，不涉及task_type
        for arg in required_args:
            if arg not in call.data:
                err_msg = f"文件服务缺少必填参数: {arg}"
                _LOGGER.error(err_msg)
                raise HomeAssistantError(err_msg)
        
        # 调用API（无需传递task_type）
        try:
            _LOGGER.debug(f"调用文件服务: {service_func.__name__}")
            result = await service_func(** call.data)  # 注意：此处不传递task_type
            _LOGGER.info(f"文件服务执行成功: {service_func.__name__}, 结果: {str(result)[:200]}")
            return result
        except Exception as err:
            err_msg = f"文件服务执行失败: {str(err)}"
            _LOGGER.error(err_msg, exc_info=True)
            raise HomeAssistantError(err_msg)

    # 工厂函数：避免闭包陷阱
    def _create_task_service_handler(func, args):
        async def handler(call):
            return await _async_handle_task_service(call, func, args)
        return handler

    def _create_file_service_handler(func, args):
        async def handler(call):
            return await _async_handle_file_service(call, func, args)
        return handler

    # 任务类服务列表（需要task_type）
    task_services = [
        ("get_task_info", api.async_get_task_info, ["task_type"]),
        ("get_task_done", api.async_get_task_done, ["task_type"]),
        ("get_task_undone", api.async_get_task_undone, ["task_type"]),
        ("delete_task", api.async_delete_task, ["task_type", "tid"]),
        ("cancel_task", api.async_cancel_task, ["task_type", "tid"]),
        ("clear_done_tasks", api.async_clear_done_tasks, ["task_type"]),
        ("clear_succeeded_tasks", api.async_clear_succeeded_tasks, ["task_type"]),
        ("retry_task", api.async_retry_task, ["task_type", "tid"]),
        ("retry_failed_tasks", api.async_retry_failed_tasks, ["task_type"]),
        ("delete_some_tasks", api.async_delete_some_tasks, ["task_type", "tids"]),
        ("cancel_some_tasks", api.async_cancel_some_tasks, ["task_type", "tids"]),
        ("retry_some_tasks", api.async_retry_some_tasks, ["task_type", "tids"]),
    ]

    # 文件类服务列表（不需要task_type）
    file_services = [
        ("mkdir", api.async_mkdir, ["path"]),
        ("rename", api.async_rename, ["path", "name"]),
        ("list_files", api.async_list_files, []),  # 路径有默认值，非必选
        ("get_file_info", api.async_get_file_info, ["path"]),
        ("search_files", api.async_search_files, ["parent", "keywords", "scope"]),
        ("get_dirs", api.async_get_dirs, []),
        ("batch_rename", api.async_batch_rename, ["src_dir", "rename_objects"]),
        ("regex_rename", api.async_regex_rename, ["src_dir", "src_name_regex", "new_name_regex"]),
        ("move_files", api.async_move_files, ["src_dir", "dst_dir", "names"]),
        ("recursive_move", api.async_recursive_move, ["src_dir", "dst_dir"]),
        ("copy_files", api.async_copy_files, ["src_dir", "dst_dir", "names"]),
        ("remove_files", api.async_remove_files, ["dir_path", "names"]),
        ("remove_empty_dir", api.async_remove_empty_dir, ["src_dir"]),
        ("add_offline_download", api.async_add_offline_download, ["path", "urls", "tool", "delete_policy"]),
        ("get_archive_meta", api.async_get_archive_meta, ["path"]),
        ("list_archive", api.async_list_archive, ["path", "inner_path"]),
        ("decompress_archive", api.async_decompress_archive, ["src_dir", "dst_dir", "name", "inner_path"]),
    ]

    # 注册任务类服务
    for service_name, service_func, required_args in task_services:
        hass.services.async_register(
            DOMAIN,
            service_name,
            _create_task_service_handler(service_func, required_args)
        )

    # 注册文件类服务
    for service_name, service_func, required_args in file_services:
        hass.services.async_register(
            DOMAIN,
            service_name,
            _create_file_service_handler(service_func, required_args)
        )

    _LOGGER.debug(f"已注册{len(task_services)}个任务服务和{len(file_services)}个文件服务")

    # 7. 初始化平台（传感器）
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("OpenList集成初始化完成，跟踪目录数量: %d", len(track_dirs))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("OpenList集成卸载完成")
    return unload_ok