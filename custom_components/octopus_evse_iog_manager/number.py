"""
Number platform for Octopus EVSE IOG Manager.

Per vehicle:
  number.iog_desired_soc_<name>  — desired charge target %
  number.iog_manual_soc_<name>   — "EV SoC at Plug in"; used only when the
                                   vehicle has no SoC sensor (unavailable if it
                                   does, since the sensor always wins)

Both persist across restarts via RestoreEntity and are grouped under the
vehicle's device.
"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_SOC_SENSOR,
    CONF_VEHICLES,
    DEFAULT_DESIRED_SOC_PERCENT,
    DEFAULT_MANUAL_SOC_PERCENT,
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

    entities: list[NumberEntity] = []
    for vcfg in vehicles:
        name = vcfg.get(CONF_VEHICLE_NAME, "EV")
        has_soc_sensor = bool(vcfg.get(CONF_VEHICLE_SOC_SENSOR))
        slug = vehicle_slug(name)
        # Redundant when a SoC sensor is configured — the sensor always wins.
        async_apply_enabled_rule(
            hass, "number", f"{entry.entry_id}_manual_soc_{slug}", not has_soc_sensor
        )
        entities.append(IOGDesiredSocNumber(coordinator, name, entry.entry_id))
        entities.append(
            IOGManualSocNumber(coordinator, name, entry.entry_id, has_soc_sensor)
        )
    async_add_entities(entities)


class _IOGNumberBase(NumberEntity, RestoreEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = True

    def __init__(self, coordinator, vehicle_name, entry_id, default):
        self._coordinator = coordinator
        self._vehicle_name = vehicle_name
        self._value = default
        self._default = default
        self._attr_device_info = vehicle_device_info(entry_id, vehicle_name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", None):
            try:
                self._value = float(last.state)
            except (ValueError, TypeError):
                pass
        self._push_to_coordinator(self._value)

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self._push_to_coordinator(value)
        self.async_write_ha_state()

    def _push_to_coordinator(self, value: float) -> None:
        raise NotImplementedError


class IOGDesiredSocNumber(_IOGNumberBase):
    _attr_icon = "mdi:battery-charging-high"

    def __init__(self, coordinator, vehicle_name, entry_id):
        super().__init__(coordinator, vehicle_name, entry_id, DEFAULT_DESIRED_SOC_PERCENT)
        self._attr_native_min_value = 10
        slug = vehicle_slug(vehicle_name)
        self._attr_unique_id = f"{entry_id}_desired_soc_{slug}"
        self._attr_name = "Desired SoC"

    def _push_to_coordinator(self, value: float) -> None:
        self._coordinator.set_desired_soc(self._vehicle_name, value)


class IOGManualSocNumber(_IOGNumberBase):
    """
    The SoC to use for this vehicle when it is plugged in.

    Only relevant for vehicles without a SoC sensor — where a sensor is
    configured it always wins, so this entity is marked unavailable to make it
    clear it has no effect.
    """

    _attr_icon = "mdi:battery-unknown"

    def __init__(self, coordinator, vehicle_name, entry_id, has_soc_sensor: bool = False):
        super().__init__(coordinator, vehicle_name, entry_id, DEFAULT_MANUAL_SOC_PERCENT)
        self._has_soc_sensor = has_soc_sensor
        slug = vehicle_slug(vehicle_name)
        self._attr_unique_id = f"{entry_id}_manual_soc_{slug}"
        self._attr_name = "EV SoC at Plug in"

        if has_soc_sensor:
            self._attr_entity_registry_enabled_default = False

    def _push_to_coordinator(self, value: float) -> None:
        self._coordinator.set_manual_soc(self._vehicle_name, value)