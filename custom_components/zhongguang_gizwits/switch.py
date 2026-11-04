"""外机开关。原始控制字和云端字段挂在这个实体的属性上，方便继续解码。"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ZGCoordinator
from .entity import ZGControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZGPowerSwitch(coordinator, entry, "power", "外机开关")])


class ZGPowerSwitch(ZGControlEntity, SwitchEntity):
    _attr_icon = "mdi:heat-pump"
    # raw_attrs 每次上报都变，留在属性里便于继续解码，但不进 recorder
    _unrecorded_attributes = frozenset({"raw_attrs"})

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("power")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "ctrl_raw": data.get("ctrl_raw"),
            "slv1_bit_states": data.get("slv1_bit_states"),
            "cloud_updated_at": data.get("updated_at"),
            "raw_attrs": data.get("raw"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_ctrl(power=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_ctrl(power=False)
