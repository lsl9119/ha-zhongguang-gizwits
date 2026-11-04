"""Setup for Zhongguang Gizwits integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import ZGCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _remove_legacy_climate(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """v0.5.0 起不再提供 climate（空调式温控盘不适合设定水温），清掉旧注册项。"""
    reg = er.async_get(hass)
    entity_id = reg.async_get_entity_id("climate", DOMAIN, f"{entry.entry_id}_climate")
    if entity_id:
        _LOGGER.info("移除旧的 climate 实体 %s，改用 number/select/switch", entity_id)
        reg.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _remove_legacy_climate(hass, entry)
    coordinator = ZGCoordinator(hass, dict(entry.data), entry.entry_id, entry)
    await coordinator.async_load_stored()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
