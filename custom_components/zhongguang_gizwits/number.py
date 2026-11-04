"""目标出水温度（制热 / 制冷各一个）。

这台外机的设定值是「出水温度」，不是室温，所以不用 climate（空调式温控盘），
而是像线控器一样，制热、制冷两个设定值分开、随时可改，与当前模式无关。
"""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SETPOINT_RANGE, SETPOINT_STEP
from .coordinator import ZGCoordinator
from .entity import ZGControlEntity

# (key, 名称, 模式, 图标)
SETPOINTS = [
    ("heat_target", "制热出水温度", "heat", "mdi:water-thermometer"),
    ("cool_target", "制冷出水温度", "cool", "mdi:snowflake-thermometer"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ZGSetpoint(coordinator, entry, *s) for s in SETPOINTS)


class ZGSetpoint(ZGControlEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = SETPOINT_STEP
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, key, name, mode, icon) -> None:
        super().__init__(coordinator, entry, key, name)
        self._key = key
        self._sp_mode = mode
        self._attr_icon = icon
        self._attr_native_min_value, self._attr_native_max_value = SETPOINT_RANGE[mode]

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {"active": self.coordinator.data.get("mode") == self._sp_mode}
        if self._sp_mode == "cool":
            # Ctrl_Set 字节 4–5 是制冷设定值，这一点是推断的（还没实写验证过）
            attrs["note"] = "制冷设定值的字节位置是推断的，入夏切制冷时再确认"
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_ctrl(**{self._key: value})
