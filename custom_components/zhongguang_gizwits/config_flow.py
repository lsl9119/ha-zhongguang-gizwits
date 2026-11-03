"""Config flow for Zhongguang Gizwits.

三种登录方式（新建、重新验证、重新配置都可选）：
- password  ：手机号 + 密码，走中广 App 的登录网关拿 token；保存账号密码，token 失效时自动续期（推荐）
- encrypted ：粘贴 App 抓包里登录请求的 JSON 体（已加密的 account/password），同样能自动续期
- token     ：老办法，直接填抓包得到的 X-Gizwits-User-token（失效后只能手动再换）
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

import aiohttp
import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_ACCOUNT,
    CONF_APP_ID,
    CONF_DID,
    CONF_ENCRYPTED,
    CONF_PASSWORD,
    CONF_PRODUCT_KEY,
    CONF_TOKEN,
    DEFAULT_APP_ID,
    DOMAIN,
)
from .coordinator import (
    GizwitsAuthError,
    OutesBadCredentials,
    OutesLoginError,
    get_session,
    giz_request,
    normalize_account,
    outes_login,
)

_LOGGER = logging.getLogger(__name__)

CONF_LOGIN_BODY = "login_body"
LOGIN_METHODS = ["password", "encrypted", "token"]


def _headers(app_id: str, token: str) -> dict[str, str]:
    return {"X-Gizwits-Application-Id": app_id, "X-Gizwits-User-token": token}


def _parse_login_body(text: str) -> tuple[str, str]:
    """从抓包的登录请求体里取出加密后的 account/password。"""
    obj = json.loads(text)
    data = obj.get("data", obj) if isinstance(obj, dict) else {}
    if isinstance(data, str):
        data = json.loads(data)
    account, password = data.get("account"), data.get("password")
    if not (isinstance(account, str) and isinstance(password, str) and account and password):
        raise ValueError("缺少 data.account / data.password")
    return account, password


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._entry: config_entries.ConfigEntry | None = None
        self._pending: dict[str, Any] = {}
        self._devices: list[dict[str, Any]] = []

    # ------------------------------------------------------------ 入口

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=LOGIN_METHODS)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        self._entry = self._get_reauth_entry()
        return self.async_show_menu(step_id="reauth_confirm", menu_options=LOGIN_METHODS)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._entry = self._get_reconfigure_entry()
        return self.async_show_menu(step_id="reconfigure", menu_options=LOGIN_METHODS)

    # ------------------------------------------------------------ 校验

    async def _check_device(self, app_id: str, token: str, did: str) -> dict[str, Any]:
        return await giz_request(
            get_session(self.hass), "GET", f"/app/devices/{did}", _headers(app_id, token)
        )

    async def _list_devices(self, app_id: str, token: str) -> list[dict[str, Any]]:
        body = await giz_request(
            get_session(self.hass), "GET", "/app/bindings?limit=50&skip=0", _headers(app_id, token)
        )
        return [d for d in (body.get("devices") or []) if d.get("did")]

    async def _login(
        self, app_id: str, account: str, password: str, encrypted: bool
    ) -> tuple[str | None, dict[str, str], str]:
        try:
            token = await outes_login(get_session(self.hass), app_id, account, password, encrypted)
            return token, {}, ""
        except OutesBadCredentials as err:
            return None, {"base": "bad_credentials"}, str(err)
        except OutesLoginError as err:
            return None, {"base": "cannot_connect"}, str(err)[:300]
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Unexpected login error")
            return None, {"base": "unknown"}, repr(err)[:300]

    async def _finish(
        self, app_id: str, token: str, extra: dict[str, Any]
    ) -> tuple[config_entries.ConfigFlowResult | None, dict[str, str], str]:
        """已拿到 token：已有条目 → 校验同一台设备后更新；新建 → 列设备。"""
        try:
            if self._entry is not None:
                did = self._entry.data[CONF_DID]
                await self._check_device(app_id, token, did)
                data = {
                    k: v
                    for k, v in self._entry.data.items()
                    if k not in (CONF_ACCOUNT, CONF_PASSWORD, CONF_ENCRYPTED)
                }
                data.update({CONF_APP_ID: app_id, CONF_TOKEN: token, **extra})
                return self.async_update_reload_and_abort(self._entry, data=data), {}, ""
            self._devices = await self._list_devices(app_id, token)
        except GizwitsAuthError as err:
            return None, {"base": "invalid_auth"}, str(err)
        except (aiohttp.ClientError, TimeoutError) as err:
            return None, {"base": "cannot_connect"}, repr(err)[:300]
        if not self._devices:
            return None, {"base": "no_devices"}, "该账号下没有绑定设备"
        self._pending = {CONF_APP_ID: app_id, CONF_TOKEN: token, **extra}
        if len(self._devices) == 1:
            return await self._create(self._devices[0]), {}, ""
        return await self.async_step_pick_device(), {}, ""

    async def _create(self, dev: dict[str, Any]) -> config_entries.ConfigFlowResult:
        await self.async_set_unique_id(dev["did"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=dev.get("dev_alias") or dev.get("product_name") or "中广两联供",
            data={
                **self._pending,
                CONF_DID: dev["did"],
                CONF_PRODUCT_KEY: dev.get("product_key", ""),
            },
        )

    def _placeholders(self, err: str) -> dict[str, str]:
        return {
            "did": self._entry.data[CONF_DID] if self._entry else "（新建）",
            "error": err or "none",
        }

    def _default_app_id(self) -> str:
        return self._entry.data.get(CONF_APP_ID, DEFAULT_APP_ID) if self._entry else DEFAULT_APP_ID

    # ------------------------------------------------------------ 三种方式

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        err = ""
        if user_input is not None:
            app_id = user_input.get(CONF_APP_ID) or DEFAULT_APP_ID
            account = normalize_account(user_input[CONF_ACCOUNT])
            password = user_input[CONF_PASSWORD]
            token, errors, err = await self._login(app_id, account, password, False)
            if token:
                result, errors, err = await self._finish(
                    app_id,
                    token,
                    {CONF_ACCOUNT: account, CONF_PASSWORD: password, CONF_ENCRYPTED: False},
                )
                if result:
                    return result
        default_account = ""
        if self._entry and not self._entry.data.get(CONF_ENCRYPTED):
            default_account = self._entry.data.get(CONF_ACCOUNT, "")
        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT, default=default_account): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_APP_ID, default=self._default_app_id()): str,
            }
        )
        return self.async_show_form(
            step_id="password",
            data_schema=schema,
            errors=errors,
            description_placeholders=self._placeholders(err),
        )

    async def async_step_encrypted(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        err = ""
        if user_input is not None:
            app_id = user_input.get(CONF_APP_ID) or DEFAULT_APP_ID
            try:
                account, password = _parse_login_body(user_input[CONF_LOGIN_BODY])
            except (ValueError, AttributeError, TypeError) as e:
                errors, err = {"base": "bad_body"}, str(e)
            else:
                token, errors, err = await self._login(app_id, account, password, True)
                if token:
                    result, errors, err = await self._finish(
                        app_id,
                        token,
                        {CONF_ACCOUNT: account, CONF_PASSWORD: password, CONF_ENCRYPTED: True},
                    )
                    if result:
                        return result
        schema = vol.Schema(
            {
                vol.Required(CONF_LOGIN_BODY): str,
                vol.Optional(CONF_APP_ID, default=self._default_app_id()): str,
            }
        )
        return self.async_show_form(
            step_id="encrypted",
            data_schema=schema,
            errors=errors,
            description_placeholders=self._placeholders(err),
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        err = ""
        if user_input is not None:
            app_id = user_input.get(CONF_APP_ID) or DEFAULT_APP_ID
            token = user_input[CONF_TOKEN].strip()
            if self._entry is None:
                did = user_input[CONF_DID].strip()
                try:
                    dev = await self._check_device(app_id, token, did)
                except GizwitsAuthError as e:
                    errors, err = {"base": "invalid_auth"}, str(e)
                except (aiohttp.ClientError, TimeoutError) as e:
                    errors, err = {"base": "cannot_connect"}, repr(e)[:300]
                else:
                    self._pending = {CONF_APP_ID: app_id, CONF_TOKEN: token}
                    return await self._create(
                        {
                            "did": did,
                            "product_key": user_input.get(CONF_PRODUCT_KEY)
                            or dev.get("product_key", ""),
                            "product_name": dev.get("product_name"),
                        }
                    )
            else:
                result, errors, err = await self._finish(app_id, token, {})
                if result:
                    return result
        fields: dict[Any, Any] = {vol.Required(CONF_TOKEN): str}
        if self._entry is None:
            fields[vol.Required(CONF_DID)] = str
            fields[vol.Optional(CONF_PRODUCT_KEY, default="")] = str
        fields[vol.Optional(CONF_APP_ID, default=self._default_app_id())] = str
        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders=self._placeholders(err),
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            dev = next(d for d in self._devices if d["did"] == user_input[CONF_DID])
            return await self._create(dev)
        options = {
            d["did"]: f'{d.get("dev_alias") or d.get("product_name") or "设备"} ({d["did"]})'
            for d in self._devices
        }
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required(CONF_DID): vol.In(options)}),
        )
