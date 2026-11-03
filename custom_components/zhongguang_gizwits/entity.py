"""Shared helpers for Zhongguang Gizwits entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER


def device_info(coordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.did)},
        name="中广两联供",
        manufacturer=MANUFACTURER,
        model="家用变频两联供",
        sw_version=str(coordinator.attrs.get("Mst_SoftVer") or "") or None,
    )
