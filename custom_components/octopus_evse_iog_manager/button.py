"""
Button platform for Octopus EVSE IOG Manager.

Per vehicle:
  button.iog_recalculate_<name> — trigger a fresh charge target calculation.

For sensor-SoC vehicles this resets to WAITING (stabilisation delay applies).
For manual-SoC vehicles the target is calculated and written immediately.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_VEHICLE_NAME, CONF_VEHICLES, DOMAIN
from .coordinator import OctopusIOGCoordinator
from .entity import vehicle_device_info, vehicle_slug

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OctopusIOGCoordinator = hass.data[DOMAIN][entry.entry_id]
    vehicles = entry.data.get(CONF_VEHICLES, [])

    async_add_entities([
        IOGRecalculateButton(coordinator, vcfg, entry.entry_id)
        for vcfg in vehicles
    ])


class IOGRecalculateButton(ButtonEntity):
    _attr_icon = "mdi:calculator-variant"
    _attr_has_entity_name = True

    def __init__(self, coordinator: OctopusIOGCoordinator, vehicle_cfg: dict, entry_id: str) -> None:
        self._coordinator = coordinator
        self._vehicle_name = vehicle_cfg.get(CONF_VEHICLE_NAME, "EV")
        slug = vehicle_slug(self._vehicle_name)
        self._attr_unique_id = f"{entry_id}_recalculate_{slug}"
        self._attr_name = "Recalculate"
        self._attr_device_info = vehicle_device_info(entry_id, self._vehicle_name)

    async def async_press(self) -> None:
        _LOGGER.info("Recalculate pressed for '%s'", self._vehicle_name)
        self._coordinator.request_recalculate(self._vehicle_name)
