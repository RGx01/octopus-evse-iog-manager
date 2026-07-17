"""
Update coordinator for Octopus EVSE IOG Manager.

State machine per vehicle:
  IDLE       → plug detected → WAITING (stabilisation delay)
  WAITING    → delay elapsed + SoC valid → TARGET_SET (write once)
  TARGET_SET → unplugged → IDLE
  TARGET_SET → recalculate button → WAITING (re-triggers flow)

The session state is persisted, so a restart, upgrade or config reload restores
TARGET_SET rather than re-running the write for a car that is already sorted.

Manual SoC bypass:
  When a vehicle's SoC is provided manually (no sensor configured), pressing
  recalculate skips the stabilisation delay and writes immediately.

SoC resolution:
  sensor value if configured AND available; None if configured but unavailable
  (never substitutes a fallback); manual number only when no sensor is set.

Plug resolution (tri-state):
  True / False from the plug sensor, or None when it is unavailable or
  unrecognised. None means "unknown" and holds the current state — it is never
  treated as unplugged, so a sensor dropout can't reset a session.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .calculations import (
    calculate_charging_time,
    calculate_iog_target_percent,
    calculate_required_energy,
    resolve_plug_state,
    select_active_vehicle,
)
from .const import (
    CONF_CHARGING_LOSS_PERCENT,
    CONF_DRY_RUN,
    CONF_PLUG_STABILISATION_DELAY,
    CONF_REGISTERED_BATTERY_KWH,
    CONF_VEHICLE_BATTERY_KWH,
    CONF_VEHICLE_CHARGING_LOSS_PERCENT,
    CONF_VEHICLE_MAX_CHARGER_POWER_KW,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_PLUG_SENSOR,
    CONF_VEHICLE_RATE_LIMIT_POWER_KW,
    CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT,
    CONF_VEHICLE_SOC_SENSOR,
    CONF_VEHICLES,
    DEFAULT_CHARGING_LOSS_PERCENT,
    DEFAULT_DESIRED_SOC_PERCENT,
    DEFAULT_DRY_RUN,
    DEFAULT_MANUAL_SOC_PERCENT,
    DEFAULT_MAX_CHARGER_POWER_KW,
    DEFAULT_PLUG_STABILISATION_DELAY,
    DEFAULT_RATE_LIMIT_POWER_KW,
    DEFAULT_RATE_LIMIT_SOC_PERCENT,
    DEFAULT_REGISTERED_BATTERY_KWH,
    DOMAIN,
    IOG_TARGET_ENTITY_PREFIX,
    IOG_TARGET_ENTITY_SUFFIX,
    IOG_TARGET_SOC_ENTITY,
    SCAN_INTERVAL_SECONDS,
    SIGNAL_MANUAL_PLUG_UPDATED,
    STATE_IDLE,
    STATE_TARGET_SET,
    STATE_WAITING,
)

_LOGGER = logging.getLogger(__name__)

# Session state persistence
STORAGE_VERSION = 1
SESSION_SAVE_DELAY_SECONDS = 5


def _safe_float(value: Any, fallback: float | None = None) -> float | None:
    if value in (None, "unknown", "unavailable", ""):
        return fallback
    try:
        return float(value)
    except (ValueError, TypeError):
        return fallback


class OctopusIOGCoordinator(DataUpdateCoordinator):
    """Coordinator implementing the plug-in state machine."""

    def __init__(self, hass: HomeAssistant, config_data: dict, entry_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self._config = config_data
        self._entry_id = entry_id

        # Session state survives restarts, upgrades and config reloads so that a
        # car already in TARGET_SET does not get its target rewritten.
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.sessions"
        )

        # State machine — keyed by vehicle name
        self._vehicle_states: dict[str, dict] = {}

        # Tracks when each vehicle was first seen plugged in, for
        # most-recent-wins conflict resolution across sensors
        self._plug_seen_at: dict = {}

        names = [v.get(CONF_VEHICLE_NAME, "EV") for v in config_data.get(CONF_VEHICLES, [])]

        # User-settable values, seeded with defaults then overwritten by entities
        self._desired_soc: dict[str, float] = {n: DEFAULT_DESIRED_SOC_PERCENT for n in names}
        self._manual_soc: dict[str, float] = {n: DEFAULT_MANUAL_SOC_PERCENT for n in names}
        self._manual_plugged_in: dict[str, bool] = {n: False for n in names}

        # Last results — persisted across ticks so sensors stay populated
        self._last_calculated_target: int | None = None
        self._last_calculation: dict | None = None
        self._last_active_vehicle: dict | None = None
        self._last_written_target: dict[str, int] = {}

        # Cached BCD Octopus target entity id (discovered by pattern match)
        self._resolved_target_entity: str | None = None

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    async def async_load_session_state(self) -> None:
        """
        Restore per-vehicle session state saved before the last shutdown.

        Without this, every restart, upgrade or config reload starts from IDLE
        and re-writes the charge target for a car that is already plugged in and
        already sorted. Called once during setup, before the first refresh.
        """
        try:
            data = await self._store.async_load()
        except Exception:  # pragma: no cover - corrupt store shouldn't block setup
            _LOGGER.warning("Could not read saved session state — starting fresh", exc_info=True)
            return

        if not data:
            _LOGGER.debug("No saved session state — starting fresh")
            return

        for name, vs in (data.get("vehicles") or {}).items():
            detected_raw = vs.get("plug_detected_at")
            detected = dt_util.parse_datetime(detected_raw) if detected_raw else None
            self._vehicle_states[name] = {
                "state": vs.get("state", STATE_IDLE),
                "plug_detected_at": detected,
            }
            written = vs.get("last_written_target")
            if written is not None:
                self._last_written_target[name] = written
            _LOGGER.debug(
                "Restored '%s': state=%s last_written=%s",
                name, vs.get("state"), written,
            )

    @callback
    def _session_payload(self) -> dict:
        """Build the JSON-serialisable session snapshot for the store."""
        vehicles = {}
        for name, vs in self._vehicle_states.items():
            detected = vs.get("plug_detected_at")
            vehicles[name] = {
                "state": vs.get("state", STATE_IDLE),
                "plug_detected_at": detected.isoformat() if detected else None,
                "last_written_target": self._last_written_target.get(name),
            }
        return {"vehicles": vehicles}

    @callback
    def _schedule_session_save(self) -> None:
        """Queue a debounced save — state changes are infrequent but bursty."""
        self._store.async_delay_save(self._session_payload, SESSION_SAVE_DELAY_SECONDS)

    async def async_save_session_state_now(self) -> None:
        """Write the session snapshot immediately (used on unload/reload)."""
        try:
            await self._store.async_save(self._session_payload())
        except Exception:  # pragma: no cover - never block teardown
            _LOGGER.warning("Could not save session state", exc_info=True)

        # Per-vehicle computed results { name: {"target": int, "calc": dict} }
        # Continuously refreshed for sensor-SoC vehicles; refreshed on button
        # press for manual-SoC vehicles.
        self._vehicle_calc: dict[str, dict] = {}

        # Set of vehicle names for which a manual recalculation has been
        # requested (via the recalculate button on a manual-SoC vehicle).
        self._manual_calc_requested: set[str] = set()

    # ------------------------------------------------------------------
    # Public API used by number/switch/button entities
    # ------------------------------------------------------------------

    def get_desired_soc(self, vehicle_name: str) -> float:
        return self._desired_soc.get(vehicle_name, DEFAULT_DESIRED_SOC_PERCENT)

    def set_desired_soc(self, vehicle_name: str, value: float) -> None:
        self._desired_soc[vehicle_name] = value
        _LOGGER.debug("Desired SoC for '%s' set to %.0f%%", vehicle_name, value)

    def get_manual_soc(self, vehicle_name: str) -> float:
        return self._manual_soc.get(vehicle_name, DEFAULT_MANUAL_SOC_PERCENT)

    def set_manual_soc(self, vehicle_name: str, value: float) -> None:
        self._manual_soc[vehicle_name] = value
        _LOGGER.debug("Manual SoC for '%s' set to %.0f%%", vehicle_name, value)

    def get_manual_plugged_in(self, vehicle_name: str) -> bool:
        return self._manual_plugged_in.get(vehicle_name, False)

    def seed_manual_plugged_in(self, vehicle_name: str, value: bool) -> None:
        """
        Seed a manual plug state at startup WITHOUT triggering the
        one-at-a-time cascade.

        If a restored ON state would result in two vehicles being ON at once,
        keep only the first and drop the rest — a stale restored state
        shouldn't silently win over an already-restored one. Enforcement
        proper only happens on live user interaction via set_manual_plugged_in.
        """
        if value and any(self._manual_plugged_in.values()):
            already_on = next(
                (n for n, on in self._manual_plugged_in.items() if on), None
            )
            _LOGGER.warning(
                "Restored '%s' as plugged in, but '%s' is already on. Keeping "
                "'%s' — only one vehicle can be plugged in at a time.",
                vehicle_name, already_on, already_on,
            )
            self._manual_plugged_in[vehicle_name] = False
        else:
            self._manual_plugged_in[vehicle_name] = value

    def set_manual_plugged_in(self, vehicle_name: str, value: bool) -> None:
        """
        Set a vehicle's manual plugged-in state.

        Enforces one-at-a-time: turning a switch ON turns every other manual
        switch OFF (radio-button behaviour), since a single EVSE can only have
        one vehicle plugged in. Switch entities listen for the dispatched
        signal to update their own UI state.
        """
        if value:
            for other in self._manual_plugged_in:
                self._manual_plugged_in[other] = (other == vehicle_name)
            _LOGGER.debug(
                "Manual plugged-in set to '%s' (all others forced off)", vehicle_name
            )
        else:
            self._manual_plugged_in[vehicle_name] = False
            _LOGGER.debug("Manual plugged-in for '%s' set to False", vehicle_name)

        # Tell switch entities to re-read their state from the coordinator
        async_dispatcher_send(self.hass, SIGNAL_MANUAL_PLUG_UPDATED)
        self.hass.async_create_task(self.async_request_refresh())

    def get_session_state(self, vehicle_name: str) -> str:
        return self._vehicle_states.get(vehicle_name, {}).get("state", STATE_IDLE)

    def _vehicle_config(self, vehicle_name: str) -> dict | None:
        for vcfg in self._config.get(CONF_VEHICLES, []):
            if vcfg.get(CONF_VEHICLE_NAME) == vehicle_name:
                return vcfg
        return None

    def request_recalculate(self, vehicle_name: str | None = None) -> None:
        """
        Trigger a recalculation.

        Always recomputes the would-be Intelligent Charge Target and energy
        figures for the vehicle, regardless of plug state — pressing the button
        updates the informational sensors even when nothing is plugged in.

        For the *actual write* to Octopus, the state machine still gates on
        plug state, stabilisation delay and dry-run. Manual-SoC vehicles skip
        the stabilisation delay; sensor-SoC vehicles reset to WAITING so the
        sensor value can settle first.
        """
        targets = [vehicle_name] if vehicle_name else list(self._manual_soc.keys())
        for name in targets:
            # Flag a manual recalculation so the would-be sensors refresh even
            # for manual-SoC vehicles (which otherwise don't recompute per-poll).
            self._manual_calc_requested.add(name)

            uses_manual = self._soc_is_manual(name)
            if uses_manual:
                _LOGGER.info("Recalculate (manual SoC) for '%s' — immediate", name)
                self._vehicle_states[name] = {
                    "state": STATE_WAITING,
                    "plug_detected_at": dt_util.utcnow() - timedelta(days=1),  # force delay elapsed
                }
            else:
                _LOGGER.info("Recalculate (sensor SoC) for '%s' — resetting to WAITING", name)
                self._vehicle_states[name] = {
                    "state": STATE_WAITING,
                    "plug_detected_at": dt_util.utcnow(),
                }
        self.hass.async_create_task(self.async_request_refresh())

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _soc_is_manual(self, vehicle_name: str) -> bool:
        """
        True if this vehicle's SoC comes from manual entry — i.e. no SoC sensor
        is configured.

        This is deliberately config-based, not based on whether the sensor
        happens to be available right now. A vehicle with a configured-but-
        currently-unavailable sensor is NOT a manual vehicle: its SoC resolves
        to None and we wait for a real reading rather than writing a target from
        a manual number the user may never have set.
        """
        vcfg = self._vehicle_config(vehicle_name)
        if not vcfg:
            return True
        return not vcfg.get(CONF_VEHICLE_SOC_SENSOR)

    def _resolve_soc(self, vehicle_name: str) -> tuple[float | None, str]:
        """
        Return (soc, source) where source is 'sensor', 'sensor_unavailable' or
        'manual'.

        If a SoC sensor is configured but currently unavailable we return None
        rather than substituting the manual value. Silently falling back means a
        sensor dropout can produce a charge target computed from a number the
        user never entered — callers must refuse to write on None.
        """
        vcfg = self._vehicle_config(vehicle_name)
        soc_entity = vcfg.get(CONF_VEHICLE_SOC_SENSOR) if vcfg else None
        if soc_entity:
            sensor_soc = _safe_float(self._get_state(soc_entity))
            if sensor_soc is not None:
                return sensor_soc, "sensor"
            return None, "sensor_unavailable"
        return self._manual_soc.get(vehicle_name, DEFAULT_MANUAL_SOC_PERCENT), "manual"

    def _resolve_plugged_in(self, vehicle_name: str) -> bool | None:
        """
        Return True / False / None, where None means *unknown*.

        Plug sensor if configured; otherwise a lone vehicle is treated as always
        connected (nothing to disambiguate against), else the manual switch.
        Unknown only ever comes from an unavailable or unrecognised sensor, and
        holds the current state rather than resetting the session.
        """
        vcfg = self._vehicle_config(vehicle_name)
        plug_entity = vcfg.get(CONF_VEHICLE_PLUG_SENSOR) if vcfg else None
        if plug_entity:
            return resolve_plug_state(self._get_state(plug_entity))
        if len(self._config.get(CONF_VEHICLES, [])) <= 1:
            return True
        return self._manual_plugged_in.get(vehicle_name, False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stabilisation_delay_minutes(self) -> int:
        return int(self._config.get(
            CONF_PLUG_STABILISATION_DELAY, DEFAULT_PLUG_STABILISATION_DELAY
        ))

    def _registered_battery_kwh(self) -> float:
        return float(
            self._config.get(CONF_REGISTERED_BATTERY_KWH, DEFAULT_REGISTERED_BATTERY_KWH)
        )

    def _get_state(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    def _enforce_single_plugged_in(self, vehicles: list[dict]) -> str | None:
        """
        Enforce the physical reality that only one vehicle can be plugged into
        a single EVSE at a time.

        Manual switches already self-enforce via set_manual_plugged_in (radio
        button). This handles the sensor case: if more than one vehicle reads
        as plugged in, keep only the most-recently-detected one and force the
        rest to plugged_in=False for this tick.

        "Most recent" uses each vehicle's first-seen-plugged-in timestamp,
        tracked in self._plug_seen_at. Returns the name of the dropped
        vehicle(s) as a status hint, or None if no conflict.
        """
        now = dt_util.utcnow()

        # Maintain first-seen timestamps
        currently_plugged = [v["name"] for v in vehicles if v["plugged_in"] is True]
        for name in list(self._plug_seen_at.keys()):
            if name not in currently_plugged:
                self._plug_seen_at.pop(name, None)
        for name in currently_plugged:
            self._plug_seen_at.setdefault(name, now)

        if len(currently_plugged) <= 1:
            return None

        # Conflict — pick the most recently plugged in (largest timestamp)
        winner = max(currently_plugged, key=lambda n: self._plug_seen_at.get(n, now))
        dropped = [n for n in currently_plugged if n != winner]

        _LOGGER.warning(
            "Multiple vehicles report plugged in (%s). Keeping most recent '%s', "
            "ignoring: %s. Only one vehicle can use the EVSE at a time.",
            ", ".join(currently_plugged), winner, ", ".join(dropped),
        )

        for v in vehicles:
            if v["name"] in dropped:
                v["plugged_in"] = False

        return winner

    def _build_vehicle_list(self) -> list[dict]:
        result = []
        for vcfg in self._config.get(CONF_VEHICLES, []):
            name = vcfg.get(CONF_VEHICLE_NAME, "EV")
            current_soc, soc_source = self._resolve_soc(name)
            plugged_in = self._resolve_plugged_in(name)

            # Per-vehicle charging loss (moved from global in 1.2.0). Fall back
            # to the old global value if present, then the default, so existing
            # configs keep working until re-saved.
            charging_loss = float(
                vcfg.get(
                    CONF_VEHICLE_CHARGING_LOSS_PERCENT,
                    self._config.get(CONF_CHARGING_LOSS_PERCENT, DEFAULT_CHARGING_LOSS_PERCENT),
                )
            )
            rate_limit_soc = float(
                vcfg.get(CONF_VEHICLE_RATE_LIMIT_SOC_PERCENT, DEFAULT_RATE_LIMIT_SOC_PERCENT)
            )
            rate_limit_power = float(
                vcfg.get(CONF_VEHICLE_RATE_LIMIT_POWER_KW, DEFAULT_RATE_LIMIT_POWER_KW)
            )
            # Per-vehicle charger power (moved from global). Fall back to the old
            # global key, then the default, so pre-1.2.0-final configs still work.
            charger_power = float(
                vcfg.get(
                    CONF_VEHICLE_MAX_CHARGER_POWER_KW,
                    self._config.get("typical_max_charger_power_kw", DEFAULT_MAX_CHARGER_POWER_KW),
                )
            )

            result.append({
                "name": name,
                "battery_kwh": float(vcfg.get(CONF_VEHICLE_BATTERY_KWH, 60)),
                "current_soc": current_soc,
                "soc_source": soc_source,
                "plugged_in": plugged_in,
                "desired_soc": self._desired_soc.get(name, DEFAULT_DESIRED_SOC_PERCENT),
                "charging_loss": charging_loss,
                "rate_limit_soc": rate_limit_soc,
                "rate_limit_power": rate_limit_power,
                "charger_power": charger_power,
                "has_soc_sensor": bool(vcfg.get(CONF_VEHICLE_SOC_SENSOR)),
                "has_plug_sensor": bool(vcfg.get(CONF_VEHICLE_PLUG_SENSOR)),
            })
        return result

    def _tick_state_machine(self, vehicles: list[dict]) -> dict | None:
        delay = timedelta(minutes=self._stabilisation_delay_minutes())
        now = dt_util.utcnow()
        vehicle_to_action = None

        for v in vehicles:
            name = v["name"]
            plugged_in = v["plugged_in"]
            vs = self._vehicle_states.setdefault(
                name, {"state": STATE_IDLE, "plug_detected_at": None}
            )
            current_state = vs["state"]

            if plugged_in is None:
                # Unknown (sensor unavailable/unrecognised). Hold whatever state
                # we're in — treating this as an unplug would reset the session
                # and re-write the target when the sensor comes back.
                _LOGGER.debug(
                    "'%s' plug state unknown — holding %s", name, current_state
                )
                continue

            if not plugged_in:
                if current_state != STATE_IDLE:
                    _LOGGER.info("'%s' unplugged — resetting to IDLE", name)
                    self._vehicle_states[name] = {"state": STATE_IDLE, "plug_detected_at": None}
                    self._last_calculated_target = None
                    self._last_calculation = None
                    self._last_active_vehicle = None
                    self._last_written_target.pop(name, None)
                    self._schedule_session_save()
                continue

            if current_state == STATE_IDLE:
                _LOGGER.info(
                    "'%s' plugged in — entering WAITING (%d min delay)",
                    name, self._stabilisation_delay_minutes(),
                )
                self._vehicle_states[name] = {"state": STATE_WAITING, "plug_detected_at": now}
                self._schedule_session_save()

            elif current_state == STATE_WAITING:
                detected_at = vs.get("plug_detected_at") or now
                if (now - detected_at) >= delay:
                    if v["current_soc"] is None:
                        _LOGGER.warning(
                            "'%s' delay elapsed but SoC unavailable (%s) — staying WAITING, "
                            "not writing a target from stale data",
                            name, v["soc_source"],
                        )
                    else:
                        _LOGGER.info(
                            "'%s' ready (SoC=%.0f%% via %s, desired=%.0f%%) — writing target",
                            name, v["current_soc"], v["soc_source"], v["desired_soc"],
                        )
                        self._vehicle_states[name]["state"] = STATE_TARGET_SET
                        self._schedule_session_save()
                        vehicle_to_action = v

            elif current_state == STATE_TARGET_SET:
                _LOGGER.debug("'%s' target already set — no action", name)

        return vehicle_to_action

    def _resolve_iog_target_entity(self) -> str | None:
        """
        Find the BottlecapDave Octopus intelligent charge target entity.

        Its real entity_id contains an account-specific segment, e.g.
        `number.octopus_energy_00000000_..._intelligent_charge_target`, so we
        match on prefix + suffix rather than a fixed name. The exact legacy
        name is accepted too. The result is cached once found.

        Returns the entity_id, or None if no match currently exists.
        """
        # Return cached match if it still exists
        if self._resolved_target_entity is not None:
            if self.hass.states.get(self._resolved_target_entity) is not None:
                return self._resolved_target_entity
            # Cached entity vanished (integration reload etc.) — re-resolve
            self._resolved_target_entity = None

        matches = [
            state.entity_id
            for state in self.hass.states.async_all("number")
            if state.entity_id.startswith(IOG_TARGET_ENTITY_PREFIX)
            and state.entity_id.endswith(IOG_TARGET_ENTITY_SUFFIX)
        ]

        if not matches:
            # Fall back to the exact legacy name if present
            if self.hass.states.get(IOG_TARGET_SOC_ENTITY) is not None:
                self._resolved_target_entity = IOG_TARGET_SOC_ENTITY
                return IOG_TARGET_SOC_ENTITY
            return None

        if len(matches) > 1:
            _LOGGER.warning(
                "Multiple Octopus intelligent charge target entities found (%s). "
                "Using the first: '%s'. If this is wrong, you likely have more "
                "than one Octopus account configured.",
                ", ".join(matches), matches[0],
            )

        self._resolved_target_entity = matches[0]
        _LOGGER.debug("Resolved IOG target entity: %s", matches[0])
        return matches[0]

    async def _async_write_iog_target(
        self, vehicle_name: str, target_percent: int, dry_run: bool
    ) -> None:
        target_entity = self._resolve_iog_target_entity()

        if dry_run:
            _LOGGER.info(
                "[DRY RUN] Would set %s to %d%% for '%s'",
                target_entity or "(target entity not found)", target_percent, vehicle_name,
            )
            self._last_written_target[vehicle_name] = target_percent
            self._schedule_session_save()
            return

        if target_percent == self._last_written_target.get(vehicle_name):
            return

        if target_entity is None:
            _LOGGER.warning(
                "No Octopus intelligent charge target entity found "
                "(looked for %s*%s). Is the Octopus Energy integration installed "
                "and on an Intelligent Go tariff?",
                IOG_TARGET_ENTITY_PREFIX, IOG_TARGET_ENTITY_SUFFIX,
            )
            return

        _LOGGER.info("Setting %s to %d%% for '%s'", target_entity, target_percent, vehicle_name)
        await self.hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: target_entity, "value": target_percent},
            blocking=True,
        )
        self._last_written_target[vehicle_name] = target_percent
        self._schedule_session_save()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # ------------------------------------------------------------------

    def _compute_vehicle_targets(self, vehicles: list[dict], registered_kwh: float) -> None:
        """
        Compute the would-be Intelligent Charge Target and energy figures for
        each vehicle, caching results in self._vehicle_calc.

        Recompute policy:
          - sensor SoC available → recompute every poll (continuous)
          - manual SoC           → recompute only when a manual recalc was
                                    requested (button press); otherwise keep
                                    the last cached value.
        Requires a valid current_soc; if unavailable, the cache is left as-is.
        """
        for v in vehicles:
            name = v["name"]
            if v["current_soc"] is None:
                continue

            is_manual = v["soc_source"] == "manual"
            manual_requested = name in self._manual_calc_requested

            if is_manual and not manual_requested and name in self._vehicle_calc:
                # Manual SoC, no fresh request, already have a value — keep it
                continue

            target = calculate_iog_target_percent(
                current_soc_percent=v["current_soc"],
                desired_soc_percent=v["desired_soc"],
                vehicle_battery_kwh=v["battery_kwh"],
                registered_battery_kwh=registered_kwh,
            )
            calc = calculate_required_energy(
                battery_kwh=v["battery_kwh"],
                current_soc_percent=v["current_soc"],
                desired_soc_percent=v["desired_soc"],
                charging_loss_percent=v["charging_loss"],
            )
            charge_time = calculate_charging_time(
                battery_kwh=v["battery_kwh"],
                current_soc_percent=v["current_soc"],
                desired_soc_percent=v["desired_soc"],
                charger_power_kw=v["charger_power"],
                charging_loss_percent=v["charging_loss"],
                rate_limit_soc_percent=v["rate_limit_soc"],
                rate_limit_power_kw=v["rate_limit_power"],
            )
            self._vehicle_calc[name] = {
                "target": target,
                "calc": calc,
                "charge_time": charge_time,
                "soc_used": v["current_soc"],
                "soc_source": v["soc_source"],
            }

        # Clear one-shot manual requests now they've been serviced
        self._manual_calc_requested.clear()

    async def _async_update_data(self) -> dict:
        try:
            dry_run = bool(self._config.get(CONF_DRY_RUN, DEFAULT_DRY_RUN))
            registered_kwh = self._registered_battery_kwh()
            vehicles = self._build_vehicle_list()

            # Enforce single-vehicle-at-a-time before the state machine runs
            self._enforce_single_plugged_in(vehicles)

            # Compute would-be target + energy for every vehicle (continuous for
            # sensor SoC, on-request for manual SoC). This runs regardless of
            # plug state so the informational sensors are always populated.
            self._compute_vehicle_targets(vehicles, registered_kwh)

            vehicle_to_action = self._tick_state_machine(vehicles)

            now = dt_util.utcnow()
            delay = timedelta(minutes=self._stabilisation_delay_minutes())
            vehicle_summaries = []
            for v in vehicles:
                name = v["name"]
                session_state = self._vehicle_states.get(name, {}).get("state", STATE_IDLE)
                detected_at = self._vehicle_states.get(name, {}).get("plug_detected_at")
                remaining_seconds = None
                if session_state == STATE_WAITING and detected_at:
                    remaining = delay - (now - detected_at)
                    remaining_seconds = max(0, int(remaining.total_seconds()))

                calc_cache = self._vehicle_calc.get(name, {})
                vehicle_summaries.append({
                    **v,
                    "session_state": session_state,
                    "remaining_wait_seconds": remaining_seconds,
                    "would_be_target": calc_cache.get("target"),
                    "calculation": calc_cache.get("calc"),
                    "charge_time": calc_cache.get("charge_time"),
                })

            # Write to Octopus only when the state machine says a plugged-in
            # vehicle has reached TARGET_SET. Uses the already-computed cache.
            if vehicle_to_action is not None:
                active = vehicle_to_action
                cache = self._vehicle_calc.get(active["name"], {})
                target_percent = cache.get("target")
                calc_details = cache.get("calc")
                if target_percent is not None:
                    await self._async_write_iog_target(
                        active["name"], target_percent, dry_run=dry_run
                    )
                    self._last_calculated_target = target_percent
                    self._last_calculation = calc_details
                    self._last_active_vehicle = active

            # `plugged_in` is tri-state — treat unknown as not-plugged for this
            # summary only; it must never drive the state machine.
            any_plugged_in = any(v["plugged_in"] is True for v in vehicles)
            if not any_plugged_in:
                reason = "no_vehicle_plugged_in"
            elif vehicle_to_action is not None:
                reason = "dry_run" if dry_run else "ok"
            else:
                active_summary = next((v for v in vehicle_summaries if v["plugged_in"] is True), None)
                reason = active_summary.get("session_state", "idle") if active_summary else "idle"

            return {
                "active_vehicle": self._last_active_vehicle,
                "vehicle_summaries": vehicle_summaries,
                "target_percent": self._last_calculated_target,
                "calculation": self._last_calculation,
                "dry_run": dry_run,
                "registered_battery_kwh": registered_kwh,
                "reason": reason,
            }

        except Exception as err:
            raise UpdateFailed(f"Error updating Octopus EVSE IOG Manager: {err}") from err