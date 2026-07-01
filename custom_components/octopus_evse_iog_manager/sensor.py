"""Sensor platform for Octopus EVSE IOG Manager."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    entities: list[SensorEntity] = []

    # Global sensors
    entities.append(IOGTargetSensor(coordinator, entry.entry_id))
    entities.append(IOGStatusSensor(coordinator, entry.entry_id))

    # Per-vehicle sensors
    for vcfg in vehicles:
        name = vcfg.get(CONF_VEHICLE_NAME, "EV")
        entities.append(IOGSessionStateSensor(coordinator, entry.entry_id, name))
        entities.append(IOGWaitTimerSensor(coordinator, entry.entry_id, name))
        entities.append(IOGVehicleSocSensor(coordinator, entry.entry_id, name))
        entities.append(IOGEnergyRequiredSensor(coordinator, entry.entry_id, name))
        entities.append(IOGWouldBeTargetSensor(coordinator, entry.entry_id, name))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class IOGBaseSensor(CoordinatorEntity[OctopusIOGCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None


# ---------------------------------------------------------------------------
# Global sensors
# ---------------------------------------------------------------------------

class IOGTargetSensor(IOGBaseSensor):
    """The charge target % that was (or would be) written to Octopus."""

    _attr_icon = "mdi:battery-charging"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_calculated_target"
        self._attr_name = "IOG Calculated Charge Target"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("target_percent") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        active = data.get("active_vehicle") or {}
        calc = data.get("calculation") or {}
        return {
            "active_vehicle": active.get("name"),
            "current_soc_percent": active.get("current_soc"),
            "desired_soc_percent": active.get("desired_soc"),
            "vehicle_battery_kwh": active.get("battery_kwh"),
            "registered_battery_kwh": data.get("registered_battery_kwh"),
            "charging_loss_percent": active.get("charging_loss"),
            "net_energy_kwh": calc.get("net_kwh"),
            "gross_energy_kwh": calc.get("gross_kwh"),
            "loss_kwh": calc.get("loss_kwh"),
            "soc_delta_percent": calc.get("soc_delta_percent"),
            "dry_run": data.get("dry_run"),
            "status": data.get("reason"),
        }


class IOGStatusSensor(IOGBaseSensor):
    """Overall integration status."""

    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_status"
        self._attr_name = "IOG Manager Status"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("reason") if self.coordinator.data else None


# ---------------------------------------------------------------------------
# Per-vehicle sensors
# ---------------------------------------------------------------------------

class IOGVehicleBaseSensor(IOGBaseSensor):
    def __init__(
        self,
        coordinator: OctopusIOGCoordinator,
        entry_id: str,
        vehicle_name: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._vehicle_name = vehicle_name
        self._slug = vehicle_slug(vehicle_name)
        self._attr_device_info = vehicle_device_info(entry_id, vehicle_name)

    def _vehicle_summary(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        for v in data.get("vehicle_summaries", []):
            if v["name"] == self._vehicle_name:
                return v
        return None


class IOGSessionStateSensor(IOGVehicleBaseSensor):
    """Session state machine state: idle / waiting / target_set."""

    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str, vehicle_name: str) -> None:
        super().__init__(coordinator, entry_id, vehicle_name)
        self._attr_unique_id = f"{entry_id}_session_state_{self._slug}"
        self._attr_name = "Session State"

    @property
    def native_value(self) -> str | None:
        v = self._vehicle_summary()
        return v.get("session_state") if v else None


class IOGWaitTimerSensor(IOGVehicleBaseSensor):
    """Seconds remaining in stabilisation wait period."""

    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str, vehicle_name: str) -> None:
        super().__init__(coordinator, entry_id, vehicle_name)
        self._attr_unique_id = f"{entry_id}_wait_timer_{self._slug}"
        self._attr_name = "Wait Timer"

    @property
    def native_value(self) -> int | None:
        v = self._vehicle_summary()
        return v.get("remaining_wait_seconds") if v else None


class IOGVehicleSocSensor(IOGVehicleBaseSensor):
    """Current SoC as read by the integration for a vehicle."""

    _attr_icon = "mdi:battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.BATTERY

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str, vehicle_name: str) -> None:
        super().__init__(coordinator, entry_id, vehicle_name)
        self._attr_unique_id = f"{entry_id}_soc_{self._slug}"
        self._attr_name = "SoC"

    @property
    def native_value(self) -> float | None:
        v = self._vehicle_summary()
        return v.get("current_soc") if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self._vehicle_summary()
        if not v:
            return {}
        return {
            "source": v.get("soc_source"),
            "has_soc_sensor": v.get("has_soc_sensor"),
        }


class IOGEnergyRequiredSensor(IOGVehicleBaseSensor):
    """Estimated gross grid energy required to reach this vehicle's desired SoC."""

    _attr_icon = "mdi:lightning-bolt"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.ENERGY

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str, vehicle_name: str) -> None:
        super().__init__(coordinator, entry_id, vehicle_name)
        self._attr_unique_id = f"{entry_id}_energy_required_{self._slug}"
        self._attr_name = "Energy Required"

    @property
    def native_value(self) -> float | None:
        v = self._vehicle_summary()
        if not v:
            return None
        calc = v.get("calculation") or {}
        return calc.get("gross_kwh")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self._vehicle_summary()
        if not v:
            return {}
        calc = v.get("calculation") or {}
        return {
            "net_kwh": calc.get("net_kwh"),
            "loss_kwh": calc.get("loss_kwh"),
            "soc_delta_percent": calc.get("soc_delta_percent"),
        }


class IOGWouldBeTargetSensor(IOGVehicleBaseSensor):
    """
    The Intelligent Charge Target % that would be set for this vehicle.

    Continuously updated when the vehicle has a SoC sensor; updated on
    Recalculate button press for manual-SoC vehicles. This is informational —
    it shows what the integration *would* write, independent of whether the
    vehicle is plugged in or dry-run is active.
    """

    _attr_icon = "mdi:target"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: OctopusIOGCoordinator, entry_id: str, vehicle_name: str) -> None:
        super().__init__(coordinator, entry_id, vehicle_name)
        self._attr_unique_id = f"{entry_id}_would_be_target_{self._slug}"
        self._attr_name = "Would-be Charge Target"

    @property
    def native_value(self) -> int | None:
        v = self._vehicle_summary()
        return v.get("would_be_target") if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self._vehicle_summary()
        if not v:
            return {}
        return {
            "soc_source": v.get("soc_source"),
            "current_soc_percent": v.get("current_soc"),
            "desired_soc_percent": v.get("desired_soc"),
            "registered_battery_kwh": (self.coordinator.data or {}).get("registered_battery_kwh"),
            "note": "What would be written to Octopus. Actual write only happens when plugged in and dry run is off.",
        }
