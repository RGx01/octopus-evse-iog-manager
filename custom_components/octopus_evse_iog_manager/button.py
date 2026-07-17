"""
Button platform for Octopus EVSE IOG Manager.

Per vehicle:
  button.iog_recalculate_<name> — trigger a fresh charge target calculation.

Only available for vehicles without a SoC sensor: those with a sensor recompute
continuously, so there is nothing to trigger manually.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_PLUG_SENSOR,
    CONF_VEHICLE_SOC_SENSOR,
    CONF_VEHICLES,
    DOMAIN,
)
from .coordinator import OctopusIOGCoordinator
from .entity import async_apply_enabled_rule, vehicle_device_info, vehicle_slug

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OctopusIOGCoordinator = hass.data[DOMAIN][entry.entry_id]
    vehicles = entry.data.get(CONF_VEHICLES, [])
    single_vehicle = len(vehicles) <= 1

    entities: list[IOGRecalculateButton] = []
    for vcfg in vehicles:
        name = vcfg.get(CONF_VEHICLE_NAME, "EV")
        slug = vehicle_slug(name)
        # A lone vehicle with no plug sensor is treated as always connected, so
        # no plug event will ever trigger a write — the button is then the only
        # trigger, regardless of whether a SoC sensor exists.
        always_plugged_in = single_vehicle and not vcfg.get(CONF_VEHICLE_PLUG_SENSOR)
        enabled = always_plugged_in or not vcfg.get(CONF_VEHICLE_SOC_SENSOR)
        async_apply_enabled_rule(
            hass, "button", f"{entry.entry_id}_recalculate_{slug}", enabled
        )
        entities.append(
            IOGRecalculateButton(coordinator, vcfg, entry.entry_id, always_plugged_in)
        )
    async_add_entities(entities)


class IOGRecalculateButton(ButtonEntity):
    """
    Trigger a fresh charge target calculation.

    Available whenever there is no automatic trigger for a write:
      - the vehicle has no SoC sensor (you enter the SoC, then press this), or
      - the vehicle is treated as always plugged in (single vehicle, no plug
        sensor), so no plug event will ever occur to trigger one.

    Otherwise a plug event drives the write and there is nothing to trigger, so
    the button is marked unavailable.
    """

    _attr_icon = "mdi:calculator-variant"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OctopusIOGCoordinator,
        vehicle_cfg: dict,
        entry_id: str,
        always_plugged_in: bool = False,
    ) -> None:
        self._coordinator = coordinator
        self._vehicle_name = vehicle_cfg.get(CONF_VEHICLE_NAME, "EV")
        self._has_soc_sensor = bool(vehicle_cfg.get(CONF_VEHICLE_SOC_SENSOR))
        self._always_plugged_in = always_plugged_in
        slug = vehicle_slug(self._vehicle_name)
        self._attr_unique_id = f"{entry_id}_recalculate_{slug}"
        self._attr_name = "Recalculate"
        self._attr_device_info = vehicle_device_info(entry_id, self._vehicle_name)

        if self._has_soc_sensor and not always_plugged_in:
            self._attr_entity_registry_enabled_default = False

    async def async_press(self) -> None:
        _LOGGER.info("Recalculate pressed for '%s'", self._vehicle_name)
        self._coordinator.request_recalculate(self._vehicle_name)