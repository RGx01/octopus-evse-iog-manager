"""Shared helpers for Octopus EVSE IOG Manager entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def vehicle_slug(vehicle_name: str) -> str:
    """Return a filesystem/entity-id-safe slug for a vehicle name."""
    return vehicle_name.lower().replace(" ", "_").replace("-", "_")


def vehicle_device_info(entry_id: str, vehicle_name: str) -> DeviceInfo:
    """
    Return DeviceInfo that groups all of a vehicle's entities under a single
    HA device. This gives us the native device page (list of EVs → click →
    grouped entities each with an 'add to dashboard' button) for free.
    """
    slug = vehicle_slug(vehicle_name)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{slug}")},
        name=f"IOG · {vehicle_name}",
        manufacturer="Octopus EVSE IOG Manager",
        model="Managed EV",
    )
