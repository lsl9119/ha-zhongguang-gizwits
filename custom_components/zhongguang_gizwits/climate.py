"""Climate platform for Zhongguang Gizwits.

这台两联供的设定值是「目标水温」，不是室温：current_temperature 用主机出水温度，
hvac_action 用压缩机频率（>0 即在制热/制冷）。
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SETPOINT_RANGE
from .coordinator import ZGCoordinator
from .entity import device_info

HVAC_TO_HA = {"cool": HVACMode.COOL, "heat": HVACMode.HEAT}
HA_TO_HVAC = {v: k for k, v in HVAC_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZGClimate(coordinator, entry)])


class ZGClimate(CoordinatorEntity[ZGCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    # raw_attrs 每次上报都变，留在属性里便于继续解码，但不进 recorder
    _unrecorded_attributes = frozenset({"raw_attrs"})

    def __init__(self, coordinator: ZGCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = device_info(coordinator)

    @property
    def _mode_key(self) -> str:
        return self.coordinator.data.get("mode") or "heat"

    @property
    def min_temp(self) -> float:
        return SETPOINT_RANGE[self._mode_key][0]

    @property
    def max_temp(self) -> float:
        return SETPOINT_RANGE[self._mode_key][1]

    @property
    def current_temperature(self) -> float | None:
        sensors = self.coordinator.data.get("sensors", {})
        for key in ("outlet_water_temp", "slv1_outlet_water"):
            if key in sensors:
                return sensors[key]["value"]
        return None

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.get("target_temp")

    @property
    def hvac_mode(self) -> HVACMode | None:
        data = self.coordinator.data
        if not data.get("power"):
            return HVACMode.OFF
        mode = data.get("mode")
        return HVAC_TO_HA.get(mode) if mode else None

    @property
    def hvac_action(self) -> HVACAction | None:
        data = self.coordinator.data
        if not data.get("power"):
            return HVACAction.OFF
        running = data.get("compressor_running")
        if running is None:
            return None
        if not running:
            return HVACAction.IDLE
        return HVACAction.COOLING if data.get("mode") == "cool" else HVACAction.HEATING

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data.get("online"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "heat_target": data.get("heat_target"),
            "cool_target": data.get("cool_target"),
            "ctrl_raw": data.get("ctrl_raw"),
            "slv1_bit_states": data.get("slv1_bit_states"),
            "cloud_updated_at": data.get("updated_at"),
            "raw_attrs": data.get("raw"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_ctrl(power=False)
            return
        mode = HA_TO_HVAC.get(hvac_mode)
        if mode is None:
            return
        await self.coordinator.async_set_ctrl(power=True, mode=mode)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_ctrl(power=True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_ctrl(power=False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        hvac_mode = kwargs.get("hvac_mode")
        temp = kwargs.get(ATTR_TEMPERATURE)
        mode = self._mode_key
        if hvac_mode is not None and hvac_mode != HVACMode.OFF:
            mode = HA_TO_HVAC.get(hvac_mode, mode)
        if temp is not None:
            lo, hi = SETPOINT_RANGE[mode]
            if not lo <= float(temp) <= hi:
                raise ServiceValidationError(
                    f"{mode} 目标水温需在 {lo}–{hi}°C 之间，收到 {temp}"
                )
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_ctrl(power=False)
            return
        # 模式与温度合成一次下发，避免两次写 Ctrl_Set 之间被云端回显覆盖
        await self.coordinator.async_set_ctrl(
            power=True if hvac_mode is not None else None,
            mode=mode if hvac_mode is not None else None,
            target_temp=float(temp) if temp is not None else None,
        )
