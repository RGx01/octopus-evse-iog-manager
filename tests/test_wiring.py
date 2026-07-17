"""
Static wiring checks for the integration's Home Assistant surface.

These exist because the unit tests deliberately avoid importing Home Assistant
(see conftest.py), which leaves coordinator.py and __init__.py — where the code
actually gets wired together — with no coverage at all. Two releases shipped
broken through exactly that gap:

  * 1.4.2: __init__.py called OctopusIOGCoordinator(hass, entry.data) while the
    constructor had gained a third required argument, entry_id. Valid Python;
    TypeError at setup.
  * 1.4.3: _vehicle_calc and _manual_calc_requested were accidentally moved out
    of __init__ into another method, so they were never initialised. Valid
    Python; AttributeError on the first update.

Neither is a logic error, so no amount of testing calculations.py would have
caught them. Both are visible in the AST without importing anything, so these
checks need no Home Assistant install and run in milliseconds.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "octopus_evse_iog_manager"
)

# Attributes provided by DataUpdateCoordinator / the HA base classes rather than
# by our own __init__. Reading these is legitimate.
_INHERITED = {
    "hass",
    "data",
    "logger",
    "name",
    "config_entry",
    "update_interval",
    "last_update_success",
    "always_update",
}


def _parse(filename: str) -> ast.Module:
    path = _COMPONENT / filename
    assert path.is_file(), f"expected component file at {path}"
    return ast.parse(path.read_text(), filename=str(path))


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _find_function(node: ast.ClassDef | ast.Module, name: str):
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
            return child
    raise AssertionError(f"function {name} not found")


def _assigned_attrs(func) -> set[str]:
    """self.X = ... targets within a function."""
    found = set()
    for node in ast.walk(func):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for t in targets:
            if (
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
            ):
                found.add(t.attr)
    return found


class TestCoordinatorAttributesInitialised:
    """Regression guard for the 1.4.3 AttributeError."""

    def test_every_attribute_read_is_initialised_in_init(self):
        cls = _find_class(_parse("coordinator.py"), "OctopusIOGCoordinator")
        init = _find_function(cls, "__init__")

        assigned = _assigned_attrs(init)
        methods = {
            m.name
            for m in cls.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        read: dict[str, int] = {}
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if method.name == "__init__":
                continue
            for node in ast.walk(method):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and isinstance(node.ctx, ast.Load)
                ):
                    read.setdefault(node.attr, node.lineno)

        missing = {
            attr: line
            for attr, line in read.items()
            if attr.startswith("_")
            and attr not in assigned
            and attr not in methods
            and attr not in _INHERITED
        }

        assert not missing, (
            "attributes are read but never initialised in __init__ "
            "(this is the 1.4.3 bug): "
            + ", ".join(f"self.{a} (read at line {l})" for a, l in sorted(missing.items()))
        )

    def test_no_attribute_is_introduced_outside_init(self):
        """
        Every attribute assigned anywhere in the class must also be assigned in
        __init__. An attribute that only ever gets assigned in some other method
        is the exact shape of the 1.4.3 bug: it looks initialised, but only if
        that method happens to run first.
        """
        cls = _find_class(_parse("coordinator.py"), "OctopusIOGCoordinator")
        init = _find_function(cls, "__init__")
        in_init = _assigned_attrs(init)

        class_level = {
            t.id
            for node in cls.body
            if isinstance(node, ast.Assign)
            for t in node.targets
            if isinstance(t, ast.Name)
        }

        offenders: dict[str, str] = {}
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if method.name == "__init__":
                continue
            for attr in _assigned_attrs(method):
                if attr.startswith("_") and attr not in in_init and attr not in class_level:
                    offenders.setdefault(attr, method.name)

        assert not offenders, (
            "attributes are only ever assigned outside __init__: "
            + ", ".join(f"self.{a} (in {m})" for a, m in sorted(offenders.items()))
        )


class TestCoordinatorConstructedCorrectly:
    """Regression guard for the 1.4.2 TypeError."""

    def test_call_site_matches_constructor_signature(self):
        init_fn = _find_function(
            _find_class(_parse("coordinator.py"), "OctopusIOGCoordinator"), "__init__"
        )
        params = [a.arg for a in init_fn.args.args if a.arg != "self"]
        n_defaults = len(init_fn.args.defaults)
        required = params[: len(params) - n_defaults] if n_defaults else params

        setup = _find_function(_parse("__init__.py"), "async_setup_entry")
        calls = [
            node
            for node in ast.walk(setup)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "OctopusIOGCoordinator"
        ]
        assert calls, "async_setup_entry never constructs OctopusIOGCoordinator"

        for call in calls:
            supplied = len(call.args) + len(call.keywords)
            assert supplied >= len(required), (
                f"OctopusIOGCoordinator(...) at __init__.py line {call.lineno} passes "
                f"{supplied} argument(s), but the constructor requires "
                f"{len(required)}: {', '.join(required)}. This is the 1.4.2 bug."
            )
            assert supplied <= len(params), (
                f"OctopusIOGCoordinator(...) at __init__.py line {call.lineno} passes "
                f"{supplied} argument(s); the constructor accepts at most {len(params)}."
            )


class TestSessionStateWiring:
    """
    Guards Rule 5 of the 1.4.1 design: restore before the first refresh.

    If async_load_session_state() runs after async_config_entry_first_refresh(),
    the first poll starts from IDLE and re-writes the charge target for a car
    that is already sorted — silently defeating the whole point of persisting
    the session. Nothing would error; it would just quietly misbehave.
    """

    def test_session_restored_before_first_refresh(self):
        setup = _find_function(_parse("__init__.py"), "async_setup_entry")

        order: list[tuple[int, str]] = []
        for node in ast.walk(setup):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in (
                    "async_load_session_state",
                    "async_config_entry_first_refresh",
                ):
                    order.append((node.lineno, node.func.attr))
        order.sort()
        names = [n for _, n in order]

        assert "async_load_session_state" in names, (
            "async_setup_entry never calls async_load_session_state() — persisted "
            "session state is loaded nowhere, so every restart re-writes the target"
        )
        assert "async_config_entry_first_refresh" in names
        assert names.index("async_load_session_state") < names.index(
            "async_config_entry_first_refresh"
        ), (
            "async_load_session_state() must be called BEFORE "
            "async_config_entry_first_refresh(), otherwise the first poll runs "
            "against un-restored state and re-writes the charge target"
        )

    def test_pending_save_is_flushed_on_unload(self):
        unload = _find_function(_parse("__init__.py"), "async_unload_entry")
        called = {
            node.func.attr
            for node in ast.walk(unload)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "async_save_session_state_now" in called, (
            "async_unload_entry must flush the debounced session save, or a "
            "pending write from the old coordinator can land after the new one "
            "and clobber newer state"
        )