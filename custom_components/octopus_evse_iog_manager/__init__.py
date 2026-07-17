"""Octopus EVSE IOG Manager — Home Assistant Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .const import CONF_VEHICLE_NAME, CONF_VEHICLES, DOMAIN, SERVICE_RECALCULATE
from .coordinator import STORAGE_VERSION, OctopusIOGCoordinator
from .entity import vehicle_slug

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "number", "button", "switch"]


def _cleanup_orphaned_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Remove devices for vehicles no longer in the config.

    Each vehicle's device uses identifier (DOMAIN, f"{entry_id}_{slug}").
    Any device for this entry whose identifier isn't in the current vehicle
    list is orphaned and deleted, so it disappears from the UI rather than
    lingering as 'unavailable'.
    """
    device_registry = dr.async_get(hass)
    valid_identifiers = {
        f"{entry.entry_id}_{vehicle_slug(v.get(CONF_VEHICLE_NAME, 'EV'))}"
        for v in entry.data.get(CONF_VEHICLES, [])
    }

    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier not in valid_identifiers:
                _LOGGER.info("Removing orphaned vehicle device: %s", device.name)
                device_registry.async_remove_device(device.id)
                break


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = OctopusIOGCoordinator(hass, entry.data, entry.entry_id)
    # Restore the saved session state BEFORE the first refresh, otherwise the
    # first poll starts from IDLE and re-writes the charge target for a car
    # that is already plugged in and already sorted.
    await coordinator.async_load_session_state()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Clean up devices for any vehicles removed since last setup
    _cleanup_orphaned_devices(hass, entry)

    async def handle_recalculate(call: ServiceCall) -> None:
        """Force recalculation for all vehicles currently in TARGET_SET."""
        _LOGGER.debug("Global recalculate service called")
        coordinator.request_recalculate()

    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE, handle_recalculate)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Reload the entry when its config changes.

    A full reload is required (rather than just refreshing the coordinator)
    because adding or removing a vehicle changes which entities should exist.
    Reloading tears down all platforms and recreates them from the updated
    vehicle list, so removed vehicles' entities are properly cleaned up.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator is not None:
            # Flush any debounced session save now. A reload builds a fresh
            # coordinator, and a pending delayed write from the old one could
            # otherwise land after it and clobber newer state.
            await coordinator.async_save_session_state_now()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Discard the persisted session state when the integration is removed."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.sessions").async_remove()