import asyncio
import time
import logging
import hashlib
from typing import Optional, Dict, Any, List

import aiohttp
from homeassistant.exceptions import HomeAssistantError

from .const import TOKEN_REFRESH_THRESHOLD, TOKEN_TTL_DEFAULT

_LOGGER = logging.getLogger(__name__)


class OpenListAPI:
    def __init__(self, host: str, username: str, password: str, session: aiohttp.ClientSession):
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._token: Optional[str] = None
        self._token_obtained_at: Optional[float] = None
        self._token_ttl = TOKEN_TTL_DEFAULT
        self._login_lock = asyncio.Lock()

        self._task_types = [
            "upload",
            "copy",
            "offline_download",
            "offline_download_transfer",
            "decompress",
            "decompress_upload",
            "move",              # ← 新增
        ]

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------
    def _hash_password(self) -> str:
        """密码哈希（Alist/OpenList 规则）"""
        combined = f"{self._password}-https://github.com/alist-org/alist"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    async def async_login(self) -> None:
        """使用哈希密码登录并获取令牌"""
        login_url = f"{self._host}/api/auth/login/hash"
        login_body = {
            "username": self._username,
            "password": self._hash_password(),
            "otp_code": "",
        }
        login_headers = {"Content-Type": "application/json"}

        masked = login_body.copy()
        if masked.get("password"):
            masked["password"] = f"{masked['password'][:10]}***"
        _LOGGER.debug(
            "发起登录请求 | URL: %s | 请求头: %s | 请求体: %s",
            login_url, login_headers, masked,
        )

        try:
            async with self._session.post(
                url=login_url,
                json=login_body,
                headers=login_headers,
                timeout=30,
            ) as resp:
                resp_body = await resp.text()
                _LOGGER.debug(
                    "登录响应 | 状态码: %d | 响应体: %s",
                    resp.status, resp_body[:500],
                )

                if resp.status != 200:
                    raise HomeAssistantError(
                        f"登录失败 [状态码: {resp.status}] | 响应: {resp_body[:200]}"
                    )

                try:
                    resp_json = await resp.json()
                except aiohttp.ContentTypeError:
                    raise HomeAssistantError(
                        f"登录响应不是 JSON 格式 | 响应: {resp_body[:200]}"
                    )

                self._token = resp_json.get("data", {}).get("token")
                if not self._token:
                    raise HomeAssistantError(
                        f"登录响应中无令牌 | 响应数据: {str(resp_json)[:300]}"
                    )

                self._token_obtained_at = time.time()
                _LOGGER.info("OpenList 登录成功（令牌有效期 48 小时）")

        except Exception as err:
            _LOGGER.error("登录过程出错: %s", err, exc_info=True)
            raise

    async def async_refresh_token(self) -> None:
        """刷新令牌（不重新登录，延长有效期）"""
        if not self._token:
            await self.async_login()
            return

        try:
            _LOGGER.debug("尝试刷新令牌（剩余有效期: %.0f 秒）",
                          self._token_remaining())
            resp = await self.async_request(
                method="POST",
                path="/api/auth/refresh_token",
                json={"token": self._token},
            )
            new_token = (
                resp.get("data", {}).get("token")
                if isinstance(resp, dict)
                else None
            )
            if new_token:
                self._token = new_token
                self._token_obtained_at = time.time()
                _LOGGER.info("令牌已自动刷新（新有效期 48 小时）")
            else:
                _LOGGER.warning(
                    "令牌刷新响应中未包含新令牌: %s", str(resp)[:200]
                )
        except Exception as err:
            _LOGGER.warning("令牌刷新失败，将尝试重新登录: %s", err)
            # 降级为重新登录
            self._token = None
            await self.async_login()

    def _token_remaining(self) -> float:
        """返回令牌剩余有效秒数（未登录返回 0）"""
        if not self._token or not self._token_obtained_at:
            return 0
        return max(0, self._token_ttl - (time.time() - self._token_obtained_at))

    def _token_expired_or_stale(self) -> bool:
        if not self._token or not self._token_obtained_at:
            return True
        elapsed = time.time() - self._token_obtained_at
        is_expired = elapsed > (self._token_ttl * 0.75)
        _LOGGER.debug(
            "令牌状态检查 | 已用: %.1f秒 | 剩余: %.1f秒 | 过期: %s",
            elapsed, self._token_remaining(), is_expired,
        )
        return is_expired

    async def _ensure_token(self) -> None:
        """确保令牌有效（支持自动刷新 + 并发保护）"""
        # 情况 1：完全没有令牌 → 登录
        if not self._token or not self._token_obtained_at:
            async with self._login_lock:
                if not self._token:
                    await self.async_login()
            return

        # 情况 2：令牌已过刷新阈值 → 尝试刷新（或降级登录）
        elapsed = time.time() - self._token_obtained_at
        if elapsed > self._token_ttl * TOKEN_REFRESH_THRESHOLD:
            async with self._login_lock:
                # 双重检查，避免在获取锁的过程中已被其他协程刷新
                elapsed = time.time() - (self._token_obtained_at or 0)
                if elapsed > self._token_ttl * TOKEN_REFRESH_THRESHOLD:
                    await self.async_refresh_token()

    # ------------------------------------------------------------------
    # 核心请求
    # ------------------------------------------------------------------
    async def async_request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """核心 HTTP 请求方法"""
        if not path.startswith("/api/"):
            raise HomeAssistantError(f"API 路径必须以 /api/ 开头: {path}")

        await self._ensure_token()

        request_url = f"{self._host}{path}"
        request_headers = kwargs.pop("headers", {})
        request_headers["Authorization"] = f"{self._token}"
        if "Accept" not in request_headers:
            request_headers["Accept"] = "application/json"

        # 显式提取参数，便于 401 重试时复用
        request_params = kwargs.pop("params", None)
        request_json = kwargs.pop("json", None)

        def _send(token: str):
            return self._session.request(
                method=method.upper(),
                url=request_url,
                headers={**request_headers, "Authorization": token},
                params=request_params,
                json=request_json,
                timeout=30,
                **kwargs,
            )

        _LOGGER.debug(
            "API 请求 | %s %s | headers=%s | params=%s | json=%s",
            method.upper(), request_url, request_headers,
            request_params, request_json,
        )

        try:
            async with _send(self._token) as resp:
                resp_body_raw = await resp.text()
                _LOGGER.debug(
                    "API 响应 | 状态码: %d | 响应体: %s",
                    resp.status, resp_body_raw[:500],
                )

                # 401 重试一次
                if resp.status == 401:
                    _LOGGER.warning("API 401 未授权，令牌失效，重新登录后重试")
                    async with self._login_lock:
                        self._token = None
                        await self.async_login()

                    async with _send(self._token) as retry_resp:
                        retry_body = await retry_resp.text()
                        _LOGGER.debug(
                            "重试响应 | 状态码: %d | 响应体: %s",
                            retry_resp.status, retry_body[:500],
                        )
                        if retry_resp.status != 200:
                            raise HomeAssistantError(
                                f"重试请求失败 [状态码: {retry_resp.status}] | 响应: {retry_body[:200]}"
                            )
                        try:
                            return await retry_resp.json()
                        except aiohttp.ContentTypeError:
                            raise HomeAssistantError(
                                f"重试响应不是 JSON 格式 | 响应: {retry_body[:200]}"
                            )

                if resp.status != 200:
                    raise HomeAssistantError(
                        f"API 请求失败 [状态码: {resp.status}] | 响应: {resp_body_raw[:200]}"
                    )

                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    raise HomeAssistantError(
                        f"API 响应不是 JSON 格式 | 响应: {resp_body_raw[:200]}"
                    )

        except Exception as err:
            _LOGGER.error(
                "API 请求出错 | %s %s | 错误: %s",
                method.upper(), request_url, err, exc_info=True,
            )
            raise

    # ------------------------------------------------------------------
    # 文件系统接口
    # ------------------------------------------------------------------
    async def async_list(
        self,
        path: str = "/",
        page: int = 1,
        per_page: int = 0,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        return await self.async_request(
            method="POST",
            path="/api/fs/list",
            json={
                "path": path,
                "page": page,
                "per_page": per_page,
                "refresh": refresh,
            },
        )

    async def async_mkdir(self, path: str) -> Dict[str, Any]:
        if not path:
            raise HomeAssistantError("创建目录失败：路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/mkdir",
            json={"path": path},
        )

    async def async_get_me(self) -> Dict[str, Any]:
        return await self.async_request(method="GET", path="/api/me")

    async def async_get_public_settings(self) -> Dict[str, Any]:
        """获取公开设置（含版本号等）"""
        return await self.async_request(method="GET", path="/api/public/settings")

    # ------------------------------------------------------------------
    # 目录树接口
    # ------------------------------------------------------------------
    async def async_get_tree(
        self,
        path: str = "/",
        password: str = "",
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """获取指定路径的完整目录树（递归）"""
        if not path:
            raise HomeAssistantError("获取目录树需要指定路径")
        return await self.async_request(
            method="POST",
            path="/api/fs/tree",
            json={
                "path": path,
                "password": password,
                "refresh": refresh,
            },
        )

    # ------------------------------------------------------------------
    # 任务管理接口
    # ------------------------------------------------------------------
    async def async_get_task_info(self, task_type: str, tid: str = None) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        params = {}
        if tid:
            params["tid"] = tid
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/info",
            params=params,
        )

    async def async_get_task_done(self, task_type: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        return await self.async_request(
            method="GET", path=f"/api/task/{task_type}/done",
        )

    async def async_get_task_undone(self, task_type: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        return await self.async_request(
            method="GET", path=f"/api/task/{task_type}/undone",
        )

    async def async_delete_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("删除任务需要任务ID")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/delete",
            params={"tid": tid},
        )

    async def async_cancel_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("取消任务需要任务ID")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/cancel",
            params={"tid": tid},
        )

    async def async_clear_done_tasks(self, task_type: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        return await self.async_request(
            method="POST", path=f"/api/task/{task_type}/clear_done",
        )

    async def async_clear_succeeded_tasks(self, task_type: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        return await self.async_request(
            method="POST", path=f"/api/task/{task_type}/clear_succeeded",
        )

    async def async_retry_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("重试任务需要任务ID")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/retry",
            params={"tid": tid},
        )

    async def async_retry_failed_tasks(self, task_type: str) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        return await self.async_request(
            method="POST", path=f"/api/task/{task_type}/retry_failed",
        )

    async def async_delete_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("删除多个任务需要任务ID列表")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/delete_some",
            json=tids,
        )

    async def async_cancel_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("取消多个任务需要任务ID列表")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/cancel_some",
            json=tids,
        )

    async def async_retry_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("重试多个任务需要任务ID列表")
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/retry_some",
            json=tids,
        )

    # ------------------------------------------------------------------
    # 其它文件操作接口
    # ------------------------------------------------------------------
    async def async_rename(self, path: str, name: str) -> Dict[str, Any]:
        if not path or not name:
            raise HomeAssistantError("路径和目标文件名不能为空")
        if "/" in name:
            raise HomeAssistantError("目标文件名不支持'/'")
        return await self.async_request(
            method="POST",
            path="/api/fs/rename",
            json={"path": path, "name": name},
        )

    async def async_list_files(
        self, path: str = "/", password: str = "",
        page: int = 1, per_page: int = 0, refresh: bool = False,
    ) -> Dict[str, Any]:
        return await self.async_request(
            method="POST",
            path="/api/fs/list",
            json={
                "path": path, "password": password,
                "page": page, "per_page": per_page, "refresh": refresh,
            },
        )

    async def async_get_file_info(
        self, path: str, password: str = "",
        page: int = 1, per_page: int = 0, refresh: bool = False,
    ) -> Dict[str, Any]:
        if not path:
            raise HomeAssistantError("路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/get",
            json={
                "path": path, "password": password,
                "page": page, "per_page": per_page, "refresh": refresh,
            },
        )

    async def async_search_files(
        self, parent: str, keywords: str, scope: int,
        page: int = 1, per_page: int = 20, password: str = "",
    ) -> Dict[str, Any]:
        if not parent or not keywords:
            raise HomeAssistantError("搜索目录和关键词不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/search",
            json={
                "parent": parent, "keywords": keywords, "scope": scope,
                "page": page, "per_page": per_page, "password": password,
            },
        )

    async def async_get_dirs(
        self, path: str = "/", password: str = "", force_root: bool = False,
    ) -> Dict[str, Any]:
        return await self.async_request(
            method="POST",
            path="/api/fs/dirs",
            json={"path": path, "password": password, "force_root": force_root},
        )

    async def async_batch_rename(self, src_dir: str, rename_objects: list) -> Dict[str, Any]:
        if not src_dir or not rename_objects:
            raise HomeAssistantError("源目录和重命名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/batch_rename",
            json={"src_dir": src_dir, "rename_objects": rename_objects},
        )

    async def async_regex_rename(
        self, src_dir: str, src_name_regex: str, new_name_regex: str,
    ) -> Dict[str, Any]:
        if not src_dir or not src_name_regex or not new_name_regex:
            raise HomeAssistantError("源目录和正则表达式不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/regex_rename",
            json={
                "src_dir": src_dir,
                "src_name_regex": src_name_regex,
                "new_name_regex": new_name_regex,
            },
        )

    async def async_move_files(self, src_dir: str, dst_dir: str, names: list) -> Dict[str, Any]:
        if not src_dir or not dst_dir or not names:
            raise HomeAssistantError("源目录、目标目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/move",
            json={"src_dir": src_dir, "dst_dir": dst_dir, "names": names},
        )

    async def async_recursive_move(self, src_dir: str, dst_dir: str) -> Dict[str, Any]:
        if not src_dir or not dst_dir:
            raise HomeAssistantError("源目录和目标目录不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/recursive_move",
            json={"src_dir": src_dir, "dst_dir": dst_dir},
        )

    async def async_copy_files(self, src_dir: str, dst_dir: str, names: list) -> Dict[str, Any]:
        if not src_dir or not dst_dir or not names:
            raise HomeAssistantError("源目录、目标目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/copy",
            json={"src_dir": src_dir, "dst_dir": dst_dir, "names": names},
        )

    async def async_remove_files(self, dir_path: str, names: list) -> Dict[str, Any]:
        if not dir_path or not names:
            raise HomeAssistantError("目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/remove",
            json={"dir": dir_path, "names": names},
        )

    async def async_remove_empty_dir(self, src_dir: str) -> Dict[str, Any]:
        if not src_dir:
            raise HomeAssistantError("目录不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/remove_empty_directory",
            json={"src_dir": src_dir},
        )

    async def async_add_offline_download(
        self, path: str, urls: list, tool: str, delete_policy: str,
    ) -> Dict[str, Any]:
        if not path or not urls or not tool or not delete_policy:
            raise HomeAssistantError("路径、URL列表、工具和删除策略不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/add_offline_download",
            json={
                "path": path, "urls": urls,
                "tool": tool, "delete_policy": delete_policy,
            },
        )

    async def async_get_archive_meta(
        self, path: str, password: str = "",
        refresh: bool = False, archive_pass: str = "",
    ) -> Dict[str, Any]:
        if not path:
            raise HomeAssistantError("路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/meta",
            json={
                "path": path, "password": password,
                "refresh": refresh, "archive_pass": archive_pass,
            },
        )

    async def async_list_archive(
        self, path: str, inner_path: str, password: str = "",
        page: int = 1, per_page: int = 0, refresh: bool = False,
        archive_pass: str = "",
    ) -> Dict[str, Any]:
        if not path or not inner_path:
            raise HomeAssistantError("路径和压缩文件内部路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/list",
            json={
                "path": path, "inner_path": inner_path, "password": password,
                "page": page, "per_page": per_page, "refresh": refresh,
                "archive_pass": archive_pass,
            },
        )

    async def async_decompress_archive(
        self, src_dir: str, dst_dir: str, name: list, inner_path: str,
        archive_pass: str = "", cache_full: bool = True, put_into_new_dir: bool = False,
    ) -> Dict[str, Any]:
        if not src_dir or not dst_dir or not name or not inner_path:
            raise HomeAssistantError("源目录、目标目录、文件名和内部路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/decompress",
            json={
                "src_dir": src_dir, "dst_dir": dst_dir, "name": name,
                "inner_path": inner_path, "archive_pass": archive_pass,
                "cache_full": cache_full, "put_into_new_dir": put_into_new_dir,
            },
        )

    # ------------------------------------------------------------------
    # 存储管理接口
    # ------------------------------------------------------------------
    async def async_get_storages(self) -> Dict[str, Any]:
        """获取所有存储挂载信息"""
        return await self.async_request(
            method="GET",
            path="/api/admin/storage/list",
        )