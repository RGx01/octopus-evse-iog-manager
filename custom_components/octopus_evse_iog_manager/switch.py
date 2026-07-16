"""
Switch platform for Octopus EVSE IOG Manager.

Per vehicle:
  switch.iog_plugged_in_<name> — manual plug override.

Only relevant when the vehicle has no plug sensor configured; if a plug
sensor IS configured it takes precedence and this switch is ignored by the
coordinator (but still shown for visibility). Persists across restarts.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_PLUG_SENSOR,
    CONF_VEHICLES,
    DOMAIN,
    SIGNAL_MANUAL_PLUG_UPDATED,
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

    entities: list[IOGPluggedInSwitch] = []
    for vcfg in vehicles:
        name = vcfg.get(CONF_VEHICLE_NAME, "EV")
        slug = vehicle_slug(name)
        # Needed only when there is more than one vehicle and no plug sensor.
        enabled = not single_vehicle and not vcfg.get(CONF_VEHICLE_PLUG_SENSOR)
        async_apply_enabled_rule(
            hass, "switch", f"{entry.entry_id}_plugged_in_{slug}", enabled
        )
        entities.append(
            IOGPluggedInSwitch(coordinator, vcfg, entry.entry_id, single_vehicle)
        )
    async_add_entities(entities)


class IOGPluggedInSwitch(SwitchEntity, RestoreEntity):
    _attr_icon = "mdi:ev-plug-type2"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OctopusIOGCoordinator,
        vehicle_cfg: dict,
        entry_id: str,
        single_vehicle: bool = False,
    ) -> None:
        self._coordinator = coordinator
        self._vehicle_name = vehicle_cfg.get(CONF_VEHICLE_NAME, "EV")
        self._has_plug_sensor = bool(vehicle_cfg.get(CONF_VEHICLE_PLUG_SENSOR))
        self._single_vehicle = single_vehicle
        self._is_on = False

        slug = vehicle_slug(self._vehicle_name)
        self._attr_unique_id = f"{entry_id}_plugged_in_{slug}"
        self._attr_name = "Manual Plugged In"
        self._attr_device_info = vehicle_device_info(entry_id, self._vehicle_name)

        # Only relevant with 2+ vehicles and no plug sensor. With one vehicle
        # there is nothing to disambiguate (it's treated as always plugged in);
        # with a plug sensor the sensor wins.
        if self._has_plug_sensor or single_vehicle:
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state == "on":
            self._is_on = True
        # Seed the coordinator directly WITHOUT triggering enforcement — during
        # startup each switch loads independently and we don't want a restored
        # ON switch to cascade-off the others before they've even restored.
        self._coordinator.seed_manual_plugged_in(self._vehicle_name, self._is_on)

        # Listen for enforcement events (e.g. another switch turned on, forcing
        # this one off) so our UI state stays in sync.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_MANUAL_PLUG_UPDATED, self._handle_plug_update
            )
        )

    @callback
    def _handle_plug_update(self) -> None:
        """Re-read our state from the coordinator after an enforcement event."""
        new_state = self._coordinator.get_manual_plugged_in(self._vehicle_name)
        if new_state != self._is_on:
            self._is_on = new_state
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._single_vehicle:
            note = (
                "Not needed — only one vehicle is configured, so it is treated as "
                "always plugged in. Add a second vehicle to use this switch."
            )
        elif self._has_plug_sensor:
            note = "Ignored — a plug sensor is configured for this vehicle."
        else:
            note = "Set ON when this vehicle is plugged in (no plug sensor configured)."
        return {"note": note}

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self._coordinator.set_manual_plugged_in(self._vehicle_name, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self._coordinator.set_manual_plugged_in(self._vehicle_name, False)
        self.async_write_ha_state()