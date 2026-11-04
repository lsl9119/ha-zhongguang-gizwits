"""Data coordinator for Zhongguang Gizwits."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE,
    BYTE_TO_HVAC_MODE,
    COMPRESSOR_FREQ_KEY,
    DISCHARGE_SUPERHEAT_KEY,
    PANEL_ROOM_KEY,
    CONF_ACCOUNT,
    CONF_APP_ID,
    CONF_DID,
    CONF_ENCRYPTED,
    CONF_PASSWORD,
    CONF_PRODUCT_KEY,
    CONF_TOKEN,
    CTRL_TEMPLATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXV_KEYS,
    GIZ_AUTH_ERROR_CODES,
    HVAC_MODE_TO_BYTE,
    MST_TEMP_KEYS,
    OUTES_API,
    OUTES_BAD_CREDENTIAL_CODES,
    OUTES_LOGIN_PATH,
    RELOGIN_COOLDOWN,
    RAW_ATTR_SKIP,
    RUN_REQUEST_BYTE,
    RUN_REQUEST_MASK,
    VERIFIED_PRODUCT_KEYS,
    SETPOINT_OFFSET,
    SETPOINT_RANGE,
    SLV1_KEYS,
)

_LOGGER = logging.getLogger(__name__)


def get_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """HA 共享会话，放宽密码套件以兼容机智云的 AES128-SHA（证书照常校验）。"""
    try:
        from homeassistant.util.ssl import SSLCipherList

        return async_get_clientsession(hass, ssl_cipher=SSLCipherList.INSECURE)
    except (ImportError, TypeError):  # 老版本 HA 没有 ssl_cipher 参数
        return async_get_clientsession(hass)


class GizwitsAuthError(Exception):
    """Token 失效。"""


class OutesBadCredentials(Exception):
    """中广登录网关明确拒绝了账号/密码（不可重试）。"""


class OutesLoginError(Exception):
    """登录网关的其他失败（网络、未知业务码），可稍后重试。"""


def normalize_account(raw: str) -> str:
    """手机号统一成 +86XXXXXXXXXXX（App 实际发送的格式）。"""
    s = re.sub(r"[\s-]", "", raw or "")
    if re.fullmatch(r"1\d{10}", s):
        return "+86" + s
    if re.fullmatch(r"861\d{10}", s):
        return "+" + s
    return s


async def outes_login(
    session: aiohttp.ClientSession,
    app_id: str,
    account: str,
    password: str,
    encrypted: bool = False,
) -> str:
    """中广 App 的密码登录，返回机智云 user token。

    encrypted=False：明文手机号+密码（与 ha-bestway 对同款网关的用法一致）；
    encrypted=True：原样提交 App 抓包里已加密的 account/password 十六进制串。
    """
    data: dict[str, Any] = {"account": account, "password": password, "lang": "zh"}
    if encrypted:
        data["encrypt"] = True
    payload = {"appKey": app_id, "data": data, "version": "1.0"}
    headers = {
        "Content-Type": "application/json",
        "X-Gizwits-Application-Id": app_id,
        "version": "1.0",
    }
    try:
        async with session.post(
            f"{OUTES_API}{OUTES_LOGIN_PATH}",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            text = await resp.text()
            status = resp.status
    except (aiohttp.ClientError, TimeoutError) as err:
        raise OutesLoginError(f"连接中广登录服务器失败: {err!r}") from err
    try:
        body = json.loads(text) if text else {}
    except ValueError:
        body = {}
    code = str(body.get("code", "")) if isinstance(body, dict) else ""
    msg = body.get("message") if isinstance(body, dict) else None
    if code in OUTES_BAD_CREDENTIAL_CODES:
        raise OutesBadCredentials(f"{code} {msg}")
    data_out = body.get("data") if isinstance(body, dict) else None
    token = data_out.get("userToken") if isinstance(data_out, dict) else None
    if status != 200 or code != "200" or not token:
        raise OutesLoginError(f"登录失败 HTTP {status} code={code or '?'} {msg or text[:120]}")
    return str(token)


async def giz_request(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> Any:
    """发请求并把机智云的错误码翻译成异常。"""
    async with session.request(
        method,
        f"{API_BASE}{path}",
        headers=headers,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=20),
    ) as resp:
        text = await resp.text()
        try:
            body = json.loads(text) if text else {}
        except ValueError:
            body = {}
        if resp.status == 200:
            return body
        code = body.get("error_code") if isinstance(body, dict) else None
        if resp.status in (401, 403) or code in GIZ_AUTH_ERROR_CODES:
            raise GizwitsAuthError(f"HTTP {resp.status} error_code={code}")
        raise aiohttp.ClientResponseError(
            resp.request_info,
            resp.history,
            status=resp.status,
            message=f"error_code={code} {text[:200]}",
        )


def _i16(h: str, signed: bool = True) -> list[int]:
    b = bytes.fromhex(h)
    return [int.from_bytes(b[i:i + 2], "big", signed=signed) for i in range(0, len(b) - 1, 2)]


class ZGCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the Gizwits cloud and merge incremental attribute reports."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_data: dict[str, Any],
        entry_id: str = "",
        entry: ConfigEntry | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.app_id: str = entry_data[CONF_APP_ID]
        self.token: str = entry_data[CONF_TOKEN]
        self.did: str = entry_data[CONF_DID]
        self.product_key: str = entry_data.get(CONF_PRODUCT_KEY, "")
        self.entry = entry
        self.account: str = entry_data.get(CONF_ACCOUNT, "")
        self.password: str = entry_data.get(CONF_PASSWORD, "")
        self.encrypted: bool = bool(entry_data.get(CONF_ENCRYPTED, False))
        self._login_lock = asyncio.Lock()
        self._last_login: float = 0.0
        self.last_login_ok: float | None = None
        self.attrs: dict[str, Any] = {}
        self.online: bool = True
        self._ctrl_hex: str = CTRL_TEMPLATE
        self._ctrl_known = False   # 读到/恢复过设备真实 Ctrl_Set 之前不允许控制
        self._warned_pk = False
        self._poll_count = 0
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry_id or 'default'}")
        self.restored = False

    async def async_load_stored(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        if data.get("attrs"):
            self.attrs.update(data["attrs"])
        if data.get("ctrl_hex"):
            self._ctrl_hex = data["ctrl_hex"]
            self._ctrl_known = True
        self.restored = True
        _LOGGER.debug("已恢复缓存状态: %s", self._ctrl_hex)

    def _data_to_save(self) -> dict[str, Any]:
        return {"attrs": self.attrs, "ctrl_hex": self._ctrl_hex}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Gizwits-Application-Id": self.app_id,
            "X-Gizwits-User-token": self.token,
            "Content-Type": "application/json",
        }

    async def _async_relogin(self, failed_token: str) -> None:
        """token 失效后用保存的账号密码重新登录一次。

        - 加锁：轮询与控制同时撞上 9004 时只登录一次；拿锁后发现 token 已被别人换过就直接返回。
        - 账号/密码错误 → GizwitsAuthError（上层转 reauth），绝不重试，避免锁号。
        - 网络等临时失败 → OutesLoginError；冷却期内不再登录。
        """
        if not (self.account and self.password):
            raise GizwitsAuthError("未保存账号密码，无法自动续期")
        async with self._login_lock:
            if self.token != failed_token:
                return
            now = time.monotonic()
            if self._last_login and now - self._last_login < RELOGIN_COOLDOWN:
                raise OutesLoginError("自动登录冷却中")
            self._last_login = now
            try:
                token = await outes_login(
                    get_session(self.hass),
                    self.app_id,
                    self.account,
                    self.password,
                    self.encrypted,
                )
            except OutesBadCredentials as err:
                raise GizwitsAuthError(f"中广账号或密码被拒绝（{err}）") from err
            self.last_login_ok = time.time()
            if token == self.token:
                # 网关返回同一个 token 却被机智云拒绝 → 再登也没用
                raise GizwitsAuthError("重新登录拿到的仍是失效的 token")
            _LOGGER.info("机智云 token 已通过中广账号自动续期")
            self.token = token
            if self.entry is not None:
                self.hass.config_entries.async_update_entry(
                    self.entry, data={**self.entry.data, CONF_TOKEN: token}
                )

    async def _giz(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        """机智云请求；9004 时自动登录一次并重试。异常：GizwitsAuthError / OutesLoginError / 网络错误。"""
        session = get_session(self.hass)
        used = self.token
        try:
            return await giz_request(session, method, path, self._headers, payload)
        except GizwitsAuthError:
            await self._async_relogin(used)
        return await giz_request(session, method, path, self._headers, payload)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            body = await self._giz("GET", f"/app/devdata/{self.did}/latest")
        except GizwitsAuthError as err:
            raise ConfigEntryAuthFailed(
                f"机智云 token 失效（{err}），请在集成页面重新验证（手机号+密码）"
            ) from err
        except OutesLoginError as err:
            raise UpdateFailed(f"token 失效且自动登录暂未成功: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"连接机智云失败: {err!r}") from err

        new_attrs = body.get("attr") or {}
        if new_attrs:
            self.attrs.update(new_attrs)
        if "Ctrl_Set" in new_attrs:
            self._ctrl_hex = new_attrs["Ctrl_Set"]
            self._ctrl_known = True
        if new_attrs:
            self._store.async_delay_save(self._data_to_save, 30)

        # online 状态查询频率低一些（约 1 分钟一次）
        self._poll_count += 1
        if self._poll_count % 6 == 1:
            try:
                dev = await self._giz("GET", f"/app/devices/{self.did}")
                self.online = bool(dev.get("is_online"))
                pk = dev.get("product_key") or self.product_key
                if pk and pk not in VERIFIED_PRODUCT_KEYS and not self._warned_pk:
                    self._warned_pk = True
                    _LOGGER.warning(
                        "product_key %s 未经面板对照验证，传感器含义可能不对；"
                        "欢迎把实体的 raw_attrs 和线控器读数提交到 issue", pk
                    )
            except GizwitsAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (aiohttp.ClientError, TimeoutError, OutesLoginError):
                pass

        data = self._parse()
        data["updated_at"] = body.get("updated_at")
        return data

    def _parse(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "online": self.online,
            "updated_at": None,
            "sensors": {},
            "raw": {k: v for k, v in self.attrs.items() if k not in RAW_ATTR_SKIP},
        }

        def fill(field: str, keys: list) -> None:
            hexval = self.attrs.get(field)
            if not hexval:
                return
            try:
                vals = _i16(hexval)
            except ValueError:
                _LOGGER.warning("无法解析 %s: %s", field, hexval)
                return
            for idx, (key, name, scale, *_rest) in enumerate(keys):
                if idx < len(vals):
                    data["sensors"][key] = {
                        "name": name,
                        "value": round(vals[idx] * scale, 1),
                    }

        fill("Mst_Temp", MST_TEMP_KEYS)
        fill("Slv1_Sensor", SLV1_KEYS)

        exv = self.attrs.get("Slv1_C1_ExvSteb")
        if exv:
            try:
                vals = _i16(exv)
                for key, name, idx in EXV_KEYS:
                    if idx < len(vals):
                        data["sensors"][key] = {"name": name, "value": vals[idx]}
            except ValueError:
                pass

        sens = data["sensors"]
        if "slv1_discharge" in sens and "slv1_s12" in sens:
            sens[DISCHARGE_SUPERHEAT_KEY] = {
                "name": "排气过热度",
                "value": round(sens["slv1_discharge"]["value"] - sens["slv1_s12"]["value"], 1),
            }
        rsl = self.attrs.get("Reserve_ReadSLow")
        if rsl and len(rsl) >= 4:
            try:
                sens[PANEL_ROOM_KEY] = {
                    "name": "线控器室内温度",
                    "value": round(int.from_bytes(bytes.fromhex(rsl[:4]), "big", signed=True) / 10, 1),
                }
            except ValueError:
                pass

        freq = data["sensors"].get(COMPRESSOR_FREQ_KEY, {}).get("value")
        data["compressor_running"] = None if freq is None else freq > 0

        bits = self.attrs.get("Slv1_C1_Bit_States")
        data["run_request"] = None
        if bits:
            try:
                b = bytes.fromhex(bits)
                if len(b) > RUN_REQUEST_BYTE:
                    data["run_request"] = bool(b[RUN_REQUEST_BYTE] & RUN_REQUEST_MASK)
            except ValueError:
                pass
            data["slv1_bit_states"] = bits

        ctrl = self.attrs.get("Ctrl_Set", self._ctrl_hex)
        try:
            raw = bytes.fromhex(ctrl)
            if len(raw) >= 8:
                data["power"] = raw[0] == 0x05
                data["mode"] = BYTE_TO_HVAC_MODE.get(raw[3])
                data["heat_target"] = int.from_bytes(raw[6:8], "big") / 10
                data["cool_target"] = int.from_bytes(raw[4:6], "big") / 10
                data["target_temp"] = (
                    data["cool_target"] if data["mode"] == "cool" else data["heat_target"]
                )
                data["ctrl_raw"] = ctrl
        except ValueError:
            _LOGGER.warning("无法解析 Ctrl_Set: %s", ctrl)

        return data

    async def async_set_ctrl(
        self,
        *,
        power: bool | None = None,
        mode: str | None = None,
        target_temp: float | None = None,
        heat_target: float | None = None,
        cool_target: float | None = None,
    ) -> None:
        """改 Ctrl_Set 里的指定字段后整体下发。

        heat_target / cool_target 直接写各自的字节，与当前模式无关；
        target_temp 写「当前（或本次设定的）模式」对应的那个设定值。
        """
        if not self._ctrl_known:
            raise HomeAssistantError("还没从云端读到设备当前的控制字（Ctrl_Set），为避免覆盖设备设置暂不下发，请稍后再试")
        raw = bytearray.fromhex(self._ctrl_hex)
        if len(raw) < 16:
            raise HomeAssistantError(f"Ctrl_Set 长度异常（{self._ctrl_hex}），不下发")

        if power is not None:
            raw[0] = 0x05 if power else 0x04
        if mode is not None:
            raw[3] = HVAC_MODE_TO_BYTE[mode]
        setpoints: dict[str, float] = {}
        if target_temp is not None:
            setpoints[BYTE_TO_HVAC_MODE.get(raw[3], "heat")] = target_temp
        if heat_target is not None:
            setpoints["heat"] = heat_target
        if cool_target is not None:
            setpoints["cool"] = cool_target
        for sp_mode, temp in setpoints.items():
            lo, hi = SETPOINT_RANGE[sp_mode]
            if not lo <= float(temp) <= hi:
                raise ServiceValidationError(
                    f"{'制热' if sp_mode == 'heat' else '制冷'}目标出水温度需在 {lo:g}–{hi:g} °C 之间，收到 {temp}"
                )
            off = SETPOINT_OFFSET[sp_mode]
            raw[off:off + 2] = int(round(float(temp) * 10)).to_bytes(2, "big")

        payload = {"attrs": {"Ctrl_Set": raw.hex()}}
        try:
            await self._giz("POST", f"/app/control/{self.did}", payload)
        except GizwitsAuthError as err:
            self.hass.async_create_task(self.async_request_refresh())
            raise HomeAssistantError("机智云 token 失效且无法自动续期，控制未下发") from err
        except OutesLoginError as err:
            raise HomeAssistantError(f"token 失效，自动登录未成功，控制未下发: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"控制下发失败: {err!r}") from err

        _LOGGER.info("下发 Ctrl_Set %s → %s", self._ctrl_hex, raw.hex())
        self._ctrl_hex = raw.hex()
        self.attrs["Ctrl_Set"] = raw.hex()
        self._store.async_delay_save(self._data_to_save, 5)
        data = self._parse()
        data["updated_at"] = (self.data or {}).get("updated_at")   # 云端上报时间不因本地下发而清空
        self.async_set_updated_data(data)
