"""Shared helpers for Octopus EVSE IOG Manager entities."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def async_apply_enabled_rule(
    hass: HomeAssistant,
    platform: str,
    unique_id: str,
    should_be_enabled: bool,
) -> None:
    """
    Enable or disable an already-registered entity to match a config-driven rule.

    `entity_registry_enabled_default` is only consulted the first time an entity
    is registered, so on its own it cannot re-enable an entity when the config
    later changes — e.g. adding a second vehicle should bring the manual plug
    switch back. This reconciles the registry on every reload instead.

    An explicit user decision to disable an entity is always respected.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is None:
        # Not registered yet — entity_registry_enabled_default covers this case.
        return

    entry = registry.async_get(entity_id)
    if entry is None or entry.disabled_by is er.RegistryEntryDisabler.USER:
        return

    if should_be_enabled and entry.disabled_by is not None:
        registry.async_update_entity(entity_id, disabled_by=None)
    elif not should_be_enabled and entry.disabled_by is None:
        registry.async_update_entity(
            entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
        )


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