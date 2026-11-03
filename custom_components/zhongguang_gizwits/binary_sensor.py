"""Binary sensors for Zhongguang Gizwits."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZGCoordinator
from .entity import device_info

# (key, name, data 字段, device_class, category)
BINARY = [
    ("compressor_running", "压缩机运行", "compressor_running", BinarySensorDeviceClass.RUNNING, None),
    ("run_request", "压缩机运行位", "run_request", BinarySensorDeviceClass.RUNNING, None),
    ("cloud_online", "云端在线", "online", BinarySensorDeviceClass.CONNECTIVITY, EntityCategory.DIAGNOSTIC),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ZGBinary(coordinator, entry, *b) for b in BINARY)


class ZGBinary(CoordinatorEntity[ZGCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, field, dclass, category) -> None:
        super().__init__(coordinator)
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_class = dclass
        self._attr_entity_category = category
        self._attr_device_info = device_info(coordinator)

    @property
    def available(self) -> bool:
        if self._field == "online":
            return super().available
        return super().available and bool(self.coordinator.data.get("online"))

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get(self._field)
