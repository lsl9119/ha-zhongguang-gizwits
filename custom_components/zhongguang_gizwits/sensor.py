"""Sensor platform for Zhongguang Gizwits."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DISCHARGE_SUPERHEAT_KEY,
    DOMAIN,
    EXV_KEYS,
    MST_TEMP_KEYS,
    PANEL_ROOM_KEY,
    SLV1_KEYS,
)
from .coordinator import ZGCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        ZGSensor(coordinator, entry, key, name, kind, enabled)
        for key, name, _scale, kind, enabled in MST_TEMP_KEYS + SLV1_KEYS
    ]
    entities += [
        ZGSensor(coordinator, entry, key, name, "raw", True)
        for key, name, _idx in EXV_KEYS
    ]
    entities += [
        ZGSensor(coordinator, entry, DISCHARGE_SUPERHEAT_KEY, "排气过热度", "delta", True),
        ZGSensor(coordinator, entry, PANEL_ROOM_KEY, "线控器室内温度", "temp", True),
    ]
    async_add_entities(entities)


class ZGSensor(CoordinatorEntity[ZGCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ZGCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        kind: str,
        enabled: bool,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator)
        self._attr_entity_registry_enabled_default = enabled
        if kind == "temp":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif kind == "delta":
            self._attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
            self._attr_icon = "mdi:thermometer-plus"
        elif kind == "pressure":
            self._attr_device_class = SensorDeviceClass.PRESSURE
            self._attr_native_unit_of_measurement = UnitOfPressure.BAR
            self._attr_suggested_display_precision = 1
        elif kind == "freq":
            self._attr_device_class = SensorDeviceClass.FREQUENCY
            self._attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
        elif kind == "volt":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        else:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data.get("online"))

    @property
    def native_value(self) -> float | None:
        item = self.coordinator.data.get("sensors", {}).get(self._key)
        return item["value"] if item else None
