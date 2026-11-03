"""Diagnostics (敏感字段已脱敏)，提 issue 时可附上。"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNT, CONF_DID, CONF_PASSWORD, CONF_TOKEN, DOMAIN

TO_REDACT = {CONF_TOKEN, CONF_PASSWORD, CONF_ACCOUNT, CONF_DID, "mac", "sno", "imsi", "uid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "product_key": coordinator.product_key,
        "online": coordinator.online,
        "ctrl_known": coordinator._ctrl_known,
        "attrs": coordinator.attrs,
        "parsed": coordinator.data,
    }
