from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .api import OpenListAPI  # 从当前目录的 api.py 导入
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_TRACK_DIRS

class OpenListFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        errors = {}
        
        if user_input is not None:
            # 验证输入格式
            if not user_input[CONF_HOST].startswith(('http://', 'https://')):
                errors["host"] = "invalid_host"
            elif not user_input[CONF_USERNAME] or not user_input[CONF_PASSWORD]:
                errors["base"] = "empty_credentials"
            else:
                # 尝试登录验证
                session = async_get_clientsession(self.hass)
                api = OpenListAPI(
                    user_input[CONF_HOST], 
                    user_input[CONF_USERNAME], 
                    user_input[CONF_PASSWORD], 
                    session
                )
                try:
                    await api.async_login()
                    
                    # 处理跟踪目录（转换为列表，去空，去重）
                    track_dirs_input = user_input.get(CONF_TRACK_DIRS, "")
                    if track_dirs_input:
                        track_dirs = [dir.strip() for dir in track_dirs_input.split(",") if dir.strip()]
                        user_input[CONF_TRACK_DIRS] = list(set(track_dirs))  # 去重
                    else:
                        user_input[CONF_TRACK_DIRS] = []
                    
                    return self.async_create_entry(
                        title=user_input[CONF_HOST], 
                        data=user_input
                    )
                except Exception as e:
                    errors["base"] = "auth_failed"
                    self._async_abort_entries_match({
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_USERNAME: user_input[CONF_USERNAME]
                    })
        
        # 定义表单结构
        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST) if user_input else "https://"): str,
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME) if user_input else ""): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_TRACK_DIRS, 
                        default=user_input.get(CONF_TRACK_DIRS) if user_input else "",
                        description="可选的跟踪目录列表，用英文逗号分隔"): str,
        })
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "host_desc": "OpenList服务器地址 (例如: https://your-openlist-server.com)",
                "user_desc": "登录用户名", 
                "pass_desc": "登录密码",
                "track_dirs_desc": "要跟踪文件数量的目录路径，多个目录用英文逗号分隔，例如：/downloads,/movies"
            }
        )

    async def async_step_import(self, import_data):
        """支持从configuration.yaml导入配置"""
        return await self.async_step_user(import_data)
