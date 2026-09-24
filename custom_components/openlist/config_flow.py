from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OpenListAPI
from .const import (
    DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_TRACK_DIRS, CONF_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _parse_track_dirs(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        items = [x.strip() for x in str(raw).split(",") if x.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


class OpenListFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            username = (user_input.get(CONF_USERNAME) or "").strip()
            password = user_input.get(CONF_PASSWORD, "")

            if not host.startswith(("http://", "https://")):
                errors["host"] = "invalid_host"
            elif not username or not password:
                errors["base"] = "empty_credentials"

            if not errors:
                await self.async_set_unique_id(f"{host}_{username}")
                self._abort_if_unique_id_configured()

                session = async_get_clientsession(self.hass)
                api = OpenListAPI(host, username, password, session)
                try:
                    await api.async_login()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("OpenList 登录失败: %s", err)
                    errors["base"] = "auth_failed"
                else:
                    user_input[CONF_HOST] = host
                    user_input[CONF_USERNAME] = username
                    user_input[CONF_TRACK_DIRS] = _parse_track_dirs(
                        user_input.get(CONF_TRACK_DIRS)
                    )
                    return self.async_create_entry(title=host, data=user_input)

        default_host = (user_input or {}).get(CONF_HOST, "https://")
        default_user = (user_input or {}).get(CONF_USERNAME, "")
        default_dirs = (user_input or {}).get(CONF_TRACK_DIRS, "")

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=default_host): str,
            vol.Required(CONF_USERNAME, default=default_user): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_TRACK_DIRS, default=default_dirs): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors,
        )

    async def async_step_import(self, import_data):
        return await self.async_step_user(import_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OpenListOptionsFlowHandler(config_entry)


class OpenListOptionsFlowHandler(config_entries.OptionsFlow):
    """允许用户运行时修改跟踪目录和轮询间隔。"""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        current_dirs = self._entry.options.get(
            CONF_TRACK_DIRS, self._entry.data.get(CONF_TRACK_DIRS, [])
        )
        if isinstance(current_dirs, list):
            current_dirs_str = ", ".join(current_dirs)
        else:
            current_dirs_str = str(current_dirs or "")

        current_interval = self._entry.options.get(CONF_UPDATE_INTERVAL, 5)

        if user_input is not None:
            new_dirs = _parse_track_dirs(user_input.get(CONF_TRACK_DIRS, ""))
            new_interval = int(user_input.get(CONF_UPDATE_INTERVAL, 5))
            return self.async_create_entry(
                title="",
                data={
                    CONF_TRACK_DIRS: new_dirs,
                    CONF_UPDATE_INTERVAL: new_interval,
                },
            )

        schema = vol.Schema({
            vol.Optional(
                CONF_TRACK_DIRS, default=current_dirs_str,
            ): str,
            vol.Optional(
                CONF_UPDATE_INTERVAL, default=current_interval,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)