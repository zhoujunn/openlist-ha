import asyncio
import time
import logging
from typing import Optional, Dict, Any, List
import aiohttp
import hashlib
from homeassistant.exceptions import HomeAssistantError

# 初始化日志记录器（与集成保持一致）
_LOGGER = logging.getLogger(__name__)

class OpenListAPI:
    def __init__(self, host: str, username: str, password: str, session: aiohttp.ClientSession):
        self._host = host.rstrip("/")  # 确保主机地址末尾无斜杠
        self._username = username
        self._password = password
        self._session = session  # 复用HA的aiohttp会话
        self._token: Optional[str] = None  # 存储认证令牌
        self._token_obtained_at: Optional[float] = None  # 令牌获取时间
        self._token_ttl = 48 * 3600  # 令牌有效期（48小时）
        
        # 定义支持的任务类型
        self._task_types = [
            "upload", 
            "copy", 
            "offline_download", 
            "offline_download_transfer", 
            "decompress", 
            "decompress_upload",
            "move"  # 新增 move 任务类型
        ]

    def _hash_password(self) -> str:
        """密码哈希处理（遵循OpenList/Alist的哈希规则）"""
        combined = f"{self._password}-https://github.com/alist-org/alist"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    async def async_login(self) -> None:
        """登录并获取令牌，输出登录请求的头和体"""
        login_url = f"{self._host}/api/auth/login/hash"
        # 构造登录请求体
        login_body = {
            "username": self._username,
            "password": self._hash_password(),
            "otp_code": ""  # 验证码（默认空）
        }
        # 构造登录请求头（默认JSON格式）
        login_headers = {"Content-Type": "application/json"}

        # 打印登录请求日志（隐藏密码哈希的后半部分，避免敏感信息泄露）
        masked_body = login_body.copy()
        if masked_body.get("password"):
            masked_body["password"] = f"{masked_body['password'][:10]}***"  # 只显示前10位哈希
        _LOGGER.debug(
            "发起登录请求 | URL: %s | 请求头: %s | 请求体: %s",
            login_url, login_headers, masked_body
        )

        try:
            async with self._session.post(
                url=login_url,
                json=login_body,
                headers=login_headers,
                timeout=30  # 30秒超时
            ) as resp:
                # 打印登录响应日志
                resp_headers = dict(resp.headers)  # 转换为字典便于日志输出
                resp_body = await resp.text()
                _LOGGER.debug(
                    "登录响应 | 状态码: %d | 响应头: %s | 响应体: %s",
                    resp.status, resp_headers, resp_body[:500]  # 响应体只显示前500字符
                )

                if resp.status != 200:
                    raise HomeAssistantError(
                        f"登录失败 [状态码: {resp.status}] | 响应: {resp_body[:200]}"
                    )

                # 解析响应体（确保为JSON格式）
                try:
                    resp_json = await resp.json()
                except aiohttp.ContentTypeError:
                    raise HomeAssistantError(f"登录响应不是JSON格式 | 响应: {resp_body[:200]}")

                # 提取令牌
                self._token = resp_json.get("data", {}).get("token")
                if not self._token:
                    raise HomeAssistantError(
                        f"登录响应中无令牌 | 响应数据: {str(resp_json)[:300]}"
                    )

                self._token_obtained_at = time.time()
                _LOGGER.info("登录成功 | 令牌已获取（有效期48小时）")

        except Exception as err:
            _LOGGER.error("登录过程出错: %s", str(err), exc_info=True)
            raise

    def _token_expired_or_stale(self) -> bool:
        """检查令牌是否过期或无效"""
        if not self._token or not self._token_obtained_at:
            _LOGGER.debug("令牌不存在或未记录获取时间 → 令牌无效")
            return True

        # 提前25%时间刷新令牌（避免临近过期时请求失败）
        elapsed_time = time.time() - self._token_obtained_at
        is_expired = elapsed_time > (self._token_ttl * 0.75)
        _LOGGER.debug(
            "令牌状态检查 | 已过时间: %.1f秒 | 过期阈值: %.1f秒 | 是否过期: %s",
            elapsed_time, self._token_ttl * 0.75, is_expired
        )
        return is_expired

    async def _ensure_token(self) -> None:
        """确保令牌有效（过期则重新登录）"""
        if self._token_expired_or_stale():
            _LOGGER.debug("令牌过期或无效 → 触发重新登录")
            await self.async_login()

    async def async_request(
        self, 
        method: str,  # HTTP方法（GET/POST/PUT等）
        path: str,    # API路径（如/api/fs/list）
        **kwargs      # 额外参数（headers/params/json等）
    ) -> Dict[str, Any]:
        """核心HTTP请求方法，输出完整请求头、请求体日志"""
        # 确保令牌有效（请求前检查）
        await self._ensure_token()

        # 1. 构造完整请求URL
        request_url = f"{self._host}{path}"  # 拼接主机和路径

        # 2. 处理请求头（添加认证令牌）
        request_headers = kwargs.pop("headers", {})  # 提取用户传入的头
        # 添加Bearer令牌认证头（覆盖已有的Authorization头）
        request_headers["Authorization"] = f"{self._token}"
        # 默认添加JSON接受头（如果未指定）
        if "Accept" not in request_headers:
            request_headers["Accept"] = "application/json"

        # 3. 提取并处理请求体/参数（用于日志输出，隐藏敏感信息）
        request_params = kwargs.get("params", {})  # URL参数（GET请求常用）
        request_body = kwargs.get("json", {})      # 请求体（POST/PUT常用）
        # 隐藏敏感信息（如路径中的密码，此处仅示例，可根据实际调整）
        masked_params = {k: v for k, v in request_params.items()}
        masked_body = {k: v for k, v in request_body.items()}

        # 4. 打印请求日志（包含方法、URL、头、体）
        _LOGGER.debug(
            "发起API请求 | 方法: %s | URL: %s | 请求头: %s | URL参数: %s | 请求体: %s",
            method.upper(), request_url, request_headers, masked_params, masked_body
        )

        try:
            # 5. 发起HTTP请求
            async with self._session.request(
                method=method.upper(),
                url=request_url,
                headers=request_headers,
                timeout=30,  # 30秒超时（避免长期阻塞）
                **kwargs
            ) as resp:
                # 6. 打印响应日志（状态码、响应头、响应体前500字符）
                resp_headers = dict(resp.headers)
                resp_body_raw = await resp.text()  # 先获取原始文本（便于日志）
                _LOGGER.debug(
                    "API响应接收 | 状态码: %d | 响应头: %s | 响应体: %s",
                    resp.status, resp_headers, resp_body_raw[:500]  # 响应体截断，避免日志过长
                )

                # 7. 处理401令牌失效（重试一次）
                if resp.status == 401:
                    _LOGGER.warning(
                        "API请求401未授权 → 令牌可能已失效，尝试重新登录后重试"
                    )
                    # 清除无效令牌并重新登录
                    self._token = None
                    await self._ensure_token()

                    # 重试请求（使用新令牌）
                    request_headers["Authorization"] = f"{self._token}"
                    _LOGGER.debug(
                        "重试API请求 | 方法: %s | URL: %s | 新请求头: %s",
                        method.upper(), request_url, request_headers
                    )
                    async with self._session.request(
                        method=method.upper(),
                        url=request_url,
                        headers=request_headers,
                        timeout=30,
                        **kwargs
                    ) as retry_resp:
                        retry_resp_body = await retry_resp.text()
                        _LOGGER.debug(
                            "重试响应接收 | 状态码: %d | 响应体: %s",
                            retry_resp.status, retry_resp_body[:500]
                        )
                        # 检查重试结果
                        if retry_resp.status != 200:
                            raise HomeAssistantError(
                                f"重试请求失败 [状态码: {retry_resp.status}] | 响应: {retry_resp_body[:200]}"
                            )
                        # 解析重试响应为JSON
                        try:
                            return await retry_resp.json()
                        except aiohttp.ContentTypeError:
                            raise HomeAssistantError(
                                f"重试响应不是JSON格式 | 响应: {retry_resp_body[:200]}"
                            )

                # 8. 处理非200状态码（非401的其他错误）
                if resp.status != 200:
                    raise HomeAssistantError(
                        f"API请求失败 [状态码: {resp.status}] | 响应: {resp_body_raw[:200]}"
                    )

                # 9. 解析响应为JSON并返回
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    raise HomeAssistantError(
                        f"API响应不是JSON格式 | 响应: {resp_body_raw[:200]}"
                    )

        except Exception as err:
            _LOGGER.error(
                "API请求过程出错 | 方法: %s | URL: %s | 错误: %s",
                method.upper(), request_url, str(err), exc_info=True
            )
            raise

    # ------------------------------
    # 业务方法（复用async_request，自动输出日志）
    # ------------------------------
    async def async_list(
        self, 
        path: str = "/", 
        page: int = 1, 
        per_page: int = 0, 
        refresh: bool = False
    ) -> Dict[str, Any]:
        """获取文件列表（调用async_request，自动输出请求头/体）"""
        return await self.async_request(
            method="POST",
            path="/api/fs/list",
            json={
                "path": path,
                "page": page,
                "per_page": per_page,
                "refresh": refresh
            }
        )

    async def async_mkdir(self, path: str) -> Dict[str, Any]:
        """创建目录（调用async_request，自动输出请求头/体）"""
        if not path:
            raise HomeAssistantError("创建目录失败：路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/mkdir",
            json={"path": path}
        )

    async def async_get_me(self) -> Dict[str, Any]:
        """获取当前用户信息（调用async_request，自动输出请求头/体）"""
        return await self.async_request(
            method="GET",
            path="/api/me"  # 无请求体，仅URL和头
        )

    # ------------------------------
    # 任务管理方法
    # ------------------------------
    
    async def async_get_task_info(self, task_type: str, tid: str = None) -> Dict[str, Any]:
        """获取任务信息（支持tid筛选单个任务）"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        
        params = {}
        if tid:
            params["tid"] = tid
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/info",
            params=params
        )

    async def async_get_task_done(self, task_type: str) -> Dict[str, Any]:
        """获取已完成任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
            
        return await self.async_request(
            method="GET",
            path=f"/api/task/{task_type}/done"
        )

    async def async_get_task_undone(self, task_type: str) -> Dict[str, Any]:
        """获取未完成任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
            
        return await self.async_request(
            method="GET",
            path=f"/api/task/{task_type}/undone"
        )

    async def async_delete_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        """删除单个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("删除任务需要任务ID")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/delete",
            params={"tid": tid}
        )

    async def async_cancel_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        """取消单个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("取消任务需要任务ID")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/cancel",
            params={"tid": tid}
        )

    async def async_clear_done_tasks(self, task_type: str) -> Dict[str, Any]:
        """清除已完成任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/clear_done"
        )

    async def async_clear_succeeded_tasks(self, task_type: str) -> Dict[str, Any]:
        """清除已成功任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/clear_succeeded"
        )

    async def async_retry_task(self, task_type: str, tid: str) -> Dict[str, Any]:
        """重试单个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tid:
            raise HomeAssistantError("重试任务需要任务ID")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/retry",
            params={"tid": tid}
        )

    async def async_retry_failed_tasks(self, task_type: str) -> Dict[str, Any]:
        """重试所有失败任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/retry_failed"
        )

    async def async_delete_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        """删除多个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("删除多个任务需要任务ID列表")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/delete_some",
            json=tids
        )

    async def async_cancel_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        """取消多个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("取消多个任务需要任务ID列表")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/cancel_some",
            json=tids
        )

    async def async_retry_some_tasks(self, task_type: str, tids: List[str]) -> Dict[str, Any]:
        """重试多个任务"""
        if task_type not in self._task_types:
            raise HomeAssistantError(f"不支持的任务类型: {task_type}")
        if not tids or not isinstance(tids, list):
            raise HomeAssistantError("重试多个任务需要任务ID列表")
            
        return await self.async_request(
            method="POST",
            path=f"/api/task/{task_type}/retry_some",
            json=tids
        )
    
    async def async_rename(self, path: str, name: str) -> Dict[str, Any]:
        """重命名文件/文件夹"""
        if not path or not name:
            raise HomeAssistantError("路径和目标文件名不能为空")
        if '/' in name:
            raise HomeAssistantError("目标文件名不支持'/'")
        return await self.async_request(
            method="POST",
            path="/api/fs/rename",
            json={"path": path, "name": name}
        )
    
    async def async_list_files(self, path: str = "/", password: str = "", 
                              page: int = 1, per_page: int = 0, refresh: bool = False) -> Dict[str, Any]:
        """列出文件目录"""
        return await self.async_request(
            method="POST",
            path="/api/fs/list",
            json={
                "path": path,
                "password": password,
                "page": page,
                "per_page": per_page,
                "refresh": refresh
            }
        )
    
    async def async_get_file_info(self, path: str, password: str = "", 
                                page: int = 1, per_page: int = 0, refresh: bool = False) -> Dict[str, Any]:
        """获取文件/目录信息"""
        if not path:
            raise HomeAssistantError("路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/get",
            json={
                "path": path,
                "password": password,
                "page": page,
                "per_page": per_page,
                "refresh": refresh
            }
        )
    
    async def async_search_files(self, parent: str, keywords: str, scope: int, 
                               page: int = 1, per_page: int = 20, password: str = "") -> Dict[str, Any]:
        """搜索文件或文件夹"""
        if not parent or not keywords:
            raise HomeAssistantError("搜索目录和关键词不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/search",
            json={
                "parent": parent,
                "keywords": keywords,
                "scope": scope,
                "page": page,
                "per_page": per_page,
                "password": password
            }
        )
    
    async def async_get_dirs(self, path: str = "/", password: str = "", force_root: bool = False) -> Dict[str, Any]:
        """获取目录列表"""
        return await self.async_request(
            method="POST",
            path="/api/fs/dirs",
            json={
                "path": path,
                "password": password,
                "force_root": force_root
            }
        )
    
    async def async_batch_rename(self, src_dir: str, rename_objects: list) -> Dict[str, Any]:
        """批量重命名"""
        if not src_dir or not rename_objects:
            raise HomeAssistantError("源目录和重命名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/batch_rename",
            json={
                "src_dir": src_dir,
                "rename_objects": rename_objects
            }
        )
    
    async def async_regex_rename(self, src_dir: str, src_name_regex: str, new_name_regex: str) -> Dict[str, Any]:
        """正则重命名"""
        if not src_dir or not src_name_regex or not new_name_regex:
            raise HomeAssistantError("源目录和正则表达式不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/regex_rename",
            json={
                "src_dir": src_dir,
                "src_name_regex": src_name_regex,
                "new_name_regex": new_name_regex
            }
        )
    
    async def async_move_files(self, src_dir: str, dst_dir: str, names: list) -> Dict[str, Any]:
        """移动文件"""
        if not src_dir or not dst_dir or not names:
            raise HomeAssistantError("源目录、目标目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/move",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": names
            }
        )
    
    async def async_recursive_move(self, src_dir: str, dst_dir: str) -> Dict[str, Any]:
        """聚合移动"""
        if not src_dir or not dst_dir:
            raise HomeAssistantError("源目录和目标目录不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/recursive_move",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir
            }
        )
    
    async def async_copy_files(self, src_dir: str, dst_dir: str, names: list) -> Dict[str, Any]:
        """复制文件"""
        if not src_dir or not dst_dir or not names:
            raise HomeAssistantError("源目录、目标目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/copy",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": names
            }
        )
    
    async def async_remove_files(self, dir_path: str, names: list) -> Dict[str, Any]:
        """删除文件或文件夹"""
        if not dir_path or not names:
            raise HomeAssistantError("目录和文件名列表不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/remove",
            json={
                "dir": dir_path,
                "names": names
            }
        )
    
    async def async_remove_empty_dir(self, src_dir: str) -> Dict[str, Any]:
        """删除空文件夹"""
        if not src_dir:
            raise HomeAssistantError("目录不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/remove_empty_directory",
            json={"src_dir": src_dir}
        )
    
    async def async_add_offline_download(self, path: str, urls: list, tool: str, delete_policy: str) -> Dict[str, Any]:
        """添加离线下载"""
        if not path or not urls or not tool or not delete_policy:
            raise HomeAssistantError("路径、URL列表、工具和删除策略不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/add_offline_download",
            json={
                "path": path,
                "urls": urls,
                "tool": tool,
                "delete_policy": delete_policy
            }
        )
    
    async def async_get_archive_meta(self, path: str, password: str = "", 
                                   refresh: bool = False, archive_pass: str = "") -> Dict[str, Any]:
        """获取压缩文件元信息"""
        if not path:
            raise HomeAssistantError("路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/meta",
            json={
                "path": path,
                "password": password,
                "refresh": refresh,
                "archive_pass": archive_pass
            }
        )
    
    async def async_list_archive(self, path: str, inner_path: str, password: str = "", 
                               page: int = 1, per_page: int = 0, refresh: bool = False, 
                               archive_pass: str = "") -> Dict[str, Any]:
        """列出压缩文件目录"""
        if not path or not inner_path:
            raise HomeAssistantError("路径和压缩文件内部路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/list",
            json={
                "path": path,
                "inner_path": inner_path,
                "password": password,
                "page": page,
                "per_page": per_page,
                "refresh": refresh,
                "archive_pass": archive_pass
            }
        )
    
    async def async_decompress_archive(self, src_dir: str, dst_dir: str, name: list, 
                                      inner_path: str, archive_pass: str = "", 
                                      cache_full: bool = True, put_into_new_dir: bool = False) -> Dict[str, Any]:
        """解压压缩文件"""
        if not src_dir or not dst_dir or not name or not inner_path:
            raise HomeAssistantError("源目录、目标目录、文件名和内部路径不能为空")
        return await self.async_request(
            method="POST",
            path="/api/fs/archive/decompress",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "name": name,
                "inner_path": inner_path,
                "archive_pass": archive_pass,
                "cache_full": cache_full,
                "put_into_new_dir": put_into_new_dir
            }
        )