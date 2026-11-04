"""运行模式：制热 / 制冷。"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ZGCoordinator
from .entity import ZGControlEntity

MODE_LABELS = {"heat": "制热", "cool": "制冷"}
LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZGModeSelect(coordinator, entry, "mode", "运行模式")])


class ZGModeSelect(ZGControlEntity, SelectEntity):
    _attr_icon = "mdi:sun-snowflake-variant"
    _attr_options = list(MODE_LABELS.values())

    @property
    def current_option(self) -> str | None:
        return MODE_LABELS.get(self.coordinator.data.get("mode"))

    async def async_select_option(self, option: str) -> None:
        # 只改模式字节，不顺带开机；开关机用「外机开关」
        await self.coordinator.async_set_ctrl(mode=LABEL_TO_MODE[option])
