"""Shared helpers for Zhongguang Gizwits entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER


def device_info(coordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.did)},
        name="中广两联供",
        manufacturer=MANUFACTURER,
        model="家用变频两联供",
        sw_version=str(coordinator.attrs.get("Mst_SoftVer") or "") or None,
    )


class ZGControlEntity(CoordinatorEntity):
    """控制类实体（开关 / 模式 / 设定水温）的公共部分：设备离线时不可用。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data.get("online"))
