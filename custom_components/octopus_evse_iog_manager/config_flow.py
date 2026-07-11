"""Config flow for Octopus EVSE IOG Manager."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DRY_RUN,
    CONF_PLUG_STABILISATION_DELAY,
    CONF_REGISTERED_BATTERY_KWH,
    CONF_VEHICLE_MAX_CHARGER_POWER_KW,
    CONF_VEHICLE_BATTERY_KWH,
    CONF_VEHICLE_CHARGING_LOSS_PERCENT,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_PLUG_SENSOR,
    CONF_VEHICLE_RATE_LIMIT_POWER_KW,
    CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT,
    CONF_VEHICLE_SOC_SENSOR,
    CONF_VEHICLES,
    DEFAULT_CHARGING_LOSS_PERCENT,
    DEFAULT_DRY_RUN,
    DEFAULT_PLUG_STABILISATION_DELAY,
    DEFAULT_RATE_LIMIT_POWER_KW,
    DEFAULT_RATE_LIMIT_SOC_PERCENT,
    DEFAULT_REGISTERED_BATTERY_KWH,
    DEFAULT_MAX_CHARGER_POWER_KW,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _build_global_schema(defaults: dict = {}) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_REGISTERED_BATTERY_KWH,
            default=defaults.get(CONF_REGISTERED_BATTERY_KWH, DEFAULT_REGISTERED_BATTERY_KWH),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=200, step=0.5, unit_of_measurement="kWh")
        ),
        vol.Required(
            CONF_PLUG_STABILISATION_DELAY,
            default=defaults.get(CONF_PLUG_STABILISATION_DELAY, DEFAULT_PLUG_STABILISATION_DELAY),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min")
        ),
        vol.Required(
            CONF_DRY_RUN,
            default=defaults.get(CONF_DRY_RUN, DEFAULT_DRY_RUN),
        ): selector.BooleanSelector(),
    })


def _build_vehicle_schema(defaults: dict = {}) -> vol.Schema:
    schema = {
        vol.Required(
            CONF_VEHICLE_NAME,
            default=defaults.get(CONF_VEHICLE_NAME, "My EV"),
        ): selector.TextSelector(),
        vol.Required(
            CONF_VEHICLE_BATTERY_KWH,
            default=defaults.get(CONF_VEHICLE_BATTERY_KWH, 60),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=200, step=0.5, unit_of_measurement="kWh")
        ),
        vol.Required(
            CONF_VEHICLE_MAX_CHARGER_POWER_KW,
            default=defaults.get(CONF_VEHICLE_MAX_CHARGER_POWER_KW, DEFAULT_MAX_CHARGER_POWER_KW),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=50, step=0.1, unit_of_measurement="kW")
        ),
        vol.Required(
            CONF_VEHICLE_CHARGING_LOSS_PERCENT,
            default=defaults.get(CONF_VEHICLE_CHARGING_LOSS_PERCENT, DEFAULT_CHARGING_LOSS_PERCENT),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=30, step=0.5, unit_of_measurement="%")
        ),
        vol.Required(
            CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT,
            default=defaults.get(CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT, DEFAULT_RATE_LIMIT_SOC_PERCENT),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=100, step=1, unit_of_measurement="%")
        ),
        vol.Optional(
            CONF_VEHICLE_RATE_LIMIT_POWER_KW,
            default=defaults.get(CONF_VEHICLE_RATE_LIMIT_POWER_KW, DEFAULT_RATE_LIMIT_POWER_KW),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0.5, max=50, step=0.1, unit_of_measurement="kW")
        ),
    }

    # Optional entity selectors: only attach a default when one actually
    # exists (i.e. editing an existing vehicle). Supplying default="" makes
    # HA validate the empty string as an entity id and reject it, so we must
    # omit the default entirely when the field is meant to be left blank.
    soc_default = defaults.get(CONF_VEHICLE_SOC_SENSOR)
    if soc_default:
        soc_key = vol.Optional(CONF_VEHICLE_SOC_SENSOR, default=soc_default)
    else:
        soc_key = vol.Optional(CONF_VEHICLE_SOC_SENSOR)
    schema[soc_key] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sensor"], device_class="battery")
    )

    plug_default = defaults.get(CONF_VEHICLE_PLUG_SENSOR)
    if plug_default:
        plug_key = vol.Optional(CONF_VEHICLE_PLUG_SENSOR, default=plug_default)
    else:
        plug_key = vol.Optional(CONF_VEHICLE_PLUG_SENSOR)
    schema[plug_key] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean", "switch"])
    )

    return vol.Schema(schema)


class OctopusIOGManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._global_config: dict[str, Any] = {}
        self._vehicles: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self._global_config = user_input
            return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="user",
            data_schema=_build_global_schema(),
        )

    async def async_step_vehicle(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            self._vehicles.append(user_input)
            return await self.async_step_add_another()

        return self.async_show_form(
            step_id="vehicle",
            data_schema=_build_vehicle_schema(),
            description_placeholders={"vehicle_number": str(len(self._vehicles) + 1)},
        )

    async def async_step_add_another(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_vehicle()
            return self._create_entry()

        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema({
                vol.Required("add_another", default=False): selector.BooleanSelector()
            }),
            description_placeholders={"count": str(len(self._vehicles))},
        )

    def _create_entry(self) -> FlowResult:
        return self.async_create_entry(
            title="Octopus EVSE IOG Manager",
            data={**self._global_config, CONF_VEHICLES: self._vehicles},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OctopusIOGManagerOptionsFlow:
        return OctopusIOGManagerOptionsFlow(config_entry)


class OctopusIOGManagerOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._global_config: dict[str, Any] = {}
        self._vehicles: list[dict[str, Any]] = list(config_entry.data.get(CONF_VEHICLES, []))
        self._editing_vehicle_index: int | None = None

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        current = self._config_entry.data
        if user_input is not None:
            self._global_config = user_input
            return await self.async_step_manage_vehicles()

        return self.async_show_form(
            step_id="init",
            data_schema=_build_global_schema(defaults={
                CONF_REGISTERED_BATTERY_KWH: current.get(CONF_REGISTERED_BATTERY_KWH, DEFAULT_REGISTERED_BATTERY_KWH),
                CONF_PLUG_STABILISATION_DELAY: current.get(CONF_PLUG_STABILISATION_DELAY, DEFAULT_PLUG_STABILISATION_DELAY),
                CONF_DRY_RUN: current.get(CONF_DRY_RUN, DEFAULT_DRY_RUN),
            }),
        )

    async def async_step_manage_vehicles(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_vehicle()
            if action == "edit":
                return await self.async_step_select_vehicle_to_edit()
            if action == "remove":
                return await self.async_step_remove_vehicle()
            return self._save()

        names = [v.get(CONF_VEHICLE_NAME, "Vehicle") for v in self._vehicles]
        options = ["add", "done"]
        if names:
            options.insert(1, "edit")
            options.insert(2, "remove")

        return self.async_show_form(
            step_id="manage_vehicles",
            data_schema=vol.Schema({
                vol.Required("action", default="done"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        translation_key="vehicle_action",
                    )
                )
            }),
            description_placeholders={
                "vehicle_list": f"Configured vehicles: {', '.join(names) or 'None'}.",
            },
        )

    async def async_step_select_vehicle_to_edit(self, user_input: dict | None = None) -> FlowResult:
        """Pick which existing vehicle to edit."""
        names = [v.get(CONF_VEHICLE_NAME, "Vehicle") for v in self._vehicles]

        if user_input is not None:
            chosen = user_input.get("vehicle_to_edit")
            # Store the index so a rename during edit doesn't break the match
            self._editing_vehicle_index = names.index(chosen) if chosen in names else None
            return await self.async_step_edit_vehicle()

        return self.async_show_form(
            step_id="select_vehicle_to_edit",
            data_schema=vol.Schema({
                vol.Required("vehicle_to_edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=names)
                )
            }),
        )

    async def async_step_edit_vehicle(self, user_input: dict | None = None) -> FlowResult:
        """Edit an existing vehicle, pre-filled with its current values.

        On upgrade, vehicles saved before new fields existed simply get the
        field defaults here, so opening this form is how a user adds the new
        1.2.0 settings (charging loss, rate-limit knee/power) to an existing car.
        """
        idx = self._editing_vehicle_index
        if idx is None or idx < 0 or idx >= len(self._vehicles):
            return await self.async_step_manage_vehicles()

        existing = self._vehicles[idx]

        if user_input is not None:
            # Replace at the same index, preserving list order and allowing rename
            self._vehicles[idx] = user_input
            return await self.async_step_manage_vehicles()

        return self.async_show_form(
            step_id="edit_vehicle",
            data_schema=_build_vehicle_schema(defaults=existing),
            description_placeholders={"vehicle_name": existing.get(CONF_VEHICLE_NAME, "")},
        )

    async def async_step_vehicle(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            self._vehicles.append(user_input)
            return await self.async_step_manage_vehicles()

        return self.async_show_form(
            step_id="vehicle",
            data_schema=_build_vehicle_schema(),
            description_placeholders={"vehicle_number": str(len(self._vehicles) + 1)},
        )

    async def async_step_remove_vehicle(self, user_input: dict | None = None) -> FlowResult:
        """Select a vehicle to remove via dropdown."""
        names = [v.get(CONF_VEHICLE_NAME, "Vehicle") for v in self._vehicles]

        if user_input is not None:
            name_to_remove = user_input.get("vehicle_to_remove")
            self._vehicles = [
                v for v in self._vehicles if v.get(CONF_VEHICLE_NAME) != name_to_remove
            ]
            _LOGGER.info("Removed vehicle '%s' from config", name_to_remove)
            return await self.async_step_manage_vehicles()

        if not names:
            return await self.async_step_manage_vehicles()

        return self.async_show_form(
            step_id="remove_vehicle",
            data_schema=vol.Schema({
                vol.Required("vehicle_to_remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=names)
                )
            }),
            description_placeholders={
                "note": (
                    "Removing a vehicle deletes its configuration. Its number/button/"
                    "sensor entities will become unavailable until HA is restarted, "
                    "at which point they will be removed entirely. The registered "
                    "battery size (set on the previous screen) is independent of "
                    "which vehicles are configured, so removing a vehicle never "
                    "affects your IOG calculations for the others."
                )
            },
        )

    def _save(self) -> FlowResult:
        new_data = {
            **self._config_entry.data,
            **self._global_config,
            CONF_VEHICLES: self._vehicles,
        }
        self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
        return self.async_create_entry(title="", data={})