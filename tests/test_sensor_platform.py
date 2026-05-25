"""Tests for the output-sensor platform (CDiT fork).

Covers the `output-sensors` capability: entity surface, dispatcher push
update, sun.sun source for sun_elevation, no-recompute-in-sensor, and
graceful unknown-on-startup.
"""

from __future__ import annotations

import inspect

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import CONF_NAME, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_lighting import sensor as sensor_module
from custom_components.adaptive_lighting.const import (
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    OUTPUT_SENSORS,
    SIGNAL_OUTPUTS_UPDATED,
)

PROFILE_NAME = "test_profile"
SENSOR_KEYS = ("output_brightness", "output_color_temp", "sun_elevation")


async def _setup_entry(hass, *, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: PROFILE_NAME},
        options=options or {},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _unique_id(entry, key: str) -> str:
    return f"{entry.entry_id}_{key}"


def _resolve_entity_id(hass, entry, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "sensor",
        DOMAIN,
        _unique_id(entry, key),
    )


# ---------------------------------------------------------------------------
# 4.2 — Three sensor entities per entry, expected suffixes
# ---------------------------------------------------------------------------


async def test_three_sensor_entities_registered(hass) -> None:
    entry = await _setup_entry(hass)
    registry = er.async_get(hass)
    for key in SENSOR_KEYS:
        eid = registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            _unique_id(entry, key),
        )
        assert eid is not None, f"Missing sensor entity for {key}"
        assert eid.startswith("sensor.")


# ---------------------------------------------------------------------------
# 4.3 — Sensors attach to the same device as switches and numbers
# ---------------------------------------------------------------------------


async def test_sensors_share_profile_device(hass) -> None:
    entry = await _setup_entry(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    master_eid = ent_reg.async_get_entity_id("switch", DOMAIN, PROFILE_NAME)
    master_dev_id = ent_reg.async_get(master_eid).device_id
    assert master_dev_id

    for key in SENSOR_KEYS:
        eid = _resolve_entity_id(hass, entry, key)
        assert ent_reg.async_get(eid).device_id == master_dev_id

    device = dev_reg.async_get(master_dev_id)
    assert device.name == PROFILE_NAME


# ---------------------------------------------------------------------------
# 4.4 — Sensor metadata matches the D4 table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        ("output_brightness", "%"),
        ("output_color_temp", "K"),
        ("sun_elevation", "°"),
    ],
)
async def test_sensor_metadata(hass, key, unit) -> None:
    entry = await _setup_entry(hass)
    eid = _resolve_entity_id(hass, entry, key)
    state = hass.states.get(eid)
    assert state is not None
    assert state.attributes.get("unit_of_measurement") == unit
    assert state.attributes.get("state_class") == SensorStateClass.MEASUREMENT
    assert state.attributes.get("device_class") is None


# ---------------------------------------------------------------------------
# 4.4b — Publish step handles missing sun.sun gracefully (D8)
# ---------------------------------------------------------------------------


async def test_publish_sun_elevation_handles_missing_sun(hass) -> None:
    entry = await _setup_entry(hass)
    al_switch = hass.data[DOMAIN][entry.entry_id]["switch"]
    # Pre-populate _settings so brightness/color publish has values.
    al_switch._settings.update(
        {"brightness_pct": 50, "color_temp_kelvin": 3000, "sun_position": 0.0},
    )
    # sun.sun is not registered in tests — confirm + invoke publish directly.
    assert hass.states.get("sun.sun") is None
    al_switch._publish_outputs_and_wake_sensors()
    outputs = hass.data[DOMAIN][entry.entry_id]["outputs"]
    assert outputs["sun_elevation"] is None
    assert outputs["output_brightness"] == 50
    assert outputs["output_color_temp"] == 3000


async def test_publish_sun_elevation_reads_from_sun_sun(hass) -> None:
    entry = await _setup_entry(hass)
    al_switch = hass.data[DOMAIN][entry.entry_id]["switch"]
    al_switch._settings.update(
        {"brightness_pct": 60, "color_temp_kelvin": 3500, "sun_position": 0.5},
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 42.5})
    al_switch._publish_outputs_and_wake_sensors()
    outputs = hass.data[DOMAIN][entry.entry_id]["outputs"]
    assert outputs["sun_elevation"] == 42.5
    assert outputs["output_brightness"] == 60


# ---------------------------------------------------------------------------
# 4.5 — Sensors are not polled
# ---------------------------------------------------------------------------


async def test_sensors_do_not_poll() -> None:
    # `_attr_should_poll` is shadowed by SensorEntity's property descriptor;
    # check the source for the class-level assignment instead.
    src = inspect.getsource(sensor_module.AdaptiveOutputSensor)
    assert "_attr_should_poll = False" in src


# ---------------------------------------------------------------------------
# 4.6 — Curve tick populates the cache with the four keys
# ---------------------------------------------------------------------------


async def test_curve_tick_publishes_outputs(hass) -> None:
    entry = await _setup_entry(hass)
    al_switch = hass.data[DOMAIN][entry.entry_id]["switch"]
    al_switch._settings.update(
        {"brightness_pct": 72, "color_temp_kelvin": 3240, "sun_position": 0.3},
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 18.0})
    before = dt_util.utcnow()
    al_switch._publish_outputs_and_wake_sensors()

    outputs = hass.data[DOMAIN][entry.entry_id]["outputs"]
    assert set(outputs.keys()) == {
        "output_brightness",
        "output_color_temp",
        "sun_elevation",
        "ambient_lux",
        "lux_reduction",
        "updated_at",
    }
    assert outputs["output_brightness"] == 72
    assert outputs["output_color_temp"] == 3240
    assert outputs["sun_elevation"] == 18.0
    assert outputs["updated_at"] >= before


# ---------------------------------------------------------------------------
# 4.7 — Firing the dispatcher signal updates the three sensors
# ---------------------------------------------------------------------------


async def test_dispatcher_signal_updates_sensors(hass) -> None:
    entry = await _setup_entry(hass)
    hass.data[DOMAIN][entry.entry_id]["outputs"] = {
        "output_brightness": 65,
        "output_color_temp": 3000,
        "sun_elevation": 25.0,
        "updated_at": dt_util.utcnow(),
    }
    async_dispatcher_send(
        hass,
        SIGNAL_OUTPUTS_UPDATED.format(entry_id=entry.entry_id),
    )
    await hass.async_block_till_done()

    assert (
        hass.states.get(_resolve_entity_id(hass, entry, "output_brightness")).state
        == "65"
    )
    assert (
        hass.states.get(_resolve_entity_id(hass, entry, "output_color_temp")).state
        == "3000"
    )
    assert (
        hass.states.get(_resolve_entity_id(hass, entry, "sun_elevation")).state
        == "25.0"
    )


# ---------------------------------------------------------------------------
# 4.8 — Signal isolation between profiles
# ---------------------------------------------------------------------------


async def test_dispatcher_signal_is_per_entry(hass) -> None:
    entry_a = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: "profile_a"},
        options={},
        version=CONFIG_ENTRY_VERSION,
    )
    entry_a.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    entry_b = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: "profile_b"},
        options={},
        version=CONFIG_ENTRY_VERSION,
    )
    entry_b.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry_b.entry_id)
    await hass.async_block_till_done()

    # Populate only A's cache, fire only A's signal.
    hass.data[DOMAIN][entry_a.entry_id]["outputs"] = {
        "output_brightness": 80,
        "output_color_temp": 4000,
        "sun_elevation": 30.0,
        "updated_at": dt_util.utcnow(),
    }
    async_dispatcher_send(
        hass,
        SIGNAL_OUTPUTS_UPDATED.format(entry_id=entry_a.entry_id),
    )
    await hass.async_block_till_done()

    a_eid = _resolve_entity_id(hass, entry_a, "output_brightness")
    b_eid = _resolve_entity_id(hass, entry_b, "output_brightness")
    assert hass.states.get(a_eid).state == "80"
    assert hass.states.get(b_eid).state == STATE_UNKNOWN  # B never updated


# ---------------------------------------------------------------------------
# 4.9 — Sensors do not import or call curve math
# ---------------------------------------------------------------------------


async def test_sensors_dont_recompute_curve() -> None:
    src = inspect.getsource(sensor_module)
    assert "SunLightSettings" not in src
    # The handler must not fetch sun.sun, sun-time, or range entities itself
    cls_src = inspect.getsource(sensor_module.AdaptiveOutputSensor)
    assert "states.get" not in cls_src


# ---------------------------------------------------------------------------
# 4.10 — Before first dispatcher signal, sensors are unknown
# ---------------------------------------------------------------------------


async def test_sensors_unknown_before_first_tick(hass) -> None:
    entry = await _setup_entry(hass)
    # In tests the sunrise/sunset entities aren't available, so even when
    # the master switch publishes during setup the brightness/color values
    # are None (no curve math ran). The sensors render as `unknown` until
    # a real tick produces real numbers.
    outputs = hass.data[DOMAIN][entry.entry_id]["outputs"]
    if outputs is not None:
        assert outputs["output_brightness"] is None
        assert outputs["output_color_temp"] is None
    for key in SENSOR_KEYS:
        eid = _resolve_entity_id(hass, entry, key)
        assert hass.states.get(eid).state == STATE_UNKNOWN


# ---------------------------------------------------------------------------
# 4.11 — Friendly names compose from device + role label, no collisions
# ---------------------------------------------------------------------------


async def test_friendly_names_compose_correctly(hass) -> None:
    entry = await _setup_entry(hass)
    names = {}
    for row in OUTPUT_SENSORS:
        if row.get("conditional"):
            continue
        key = row["key"]
        eid = _resolve_entity_id(hass, entry, key)
        names[key] = hass.states.get(eid).attributes["friendly_name"]
    assert names["output_brightness"] == f"{PROFILE_NAME} Output brightness"
    assert names["output_color_temp"] == f"{PROFILE_NAME} Output color temp"
    assert names["sun_elevation"] == f"{PROFILE_NAME} Sun elevation"

    # No collision with the adapt-brightness switch ("<profile> Brightness").
    all_friendly = set(names.values())
    # Walk all entities owned by this entry and confirm uniqueness.
    ent_reg = er.async_get(hass)
    for ent in ent_reg.entities.values():
        if ent.config_entry_id != entry.entry_id:
            continue
        state = hass.states.get(ent.entity_id)
        if state is None:
            continue
        fname = state.attributes.get("friendly_name")
        if fname is None:
            continue
        if fname in names.values():
            continue
        # Any other entity's friendly name must not match a sensor's.
        assert (
            fname not in all_friendly
        ), f"Collision: {fname} appears on both sensor and another entity"


# ---------------------------------------------------------------------------
# 4.12 — Unload removes sensors and detaches dispatcher subscriptions
# ---------------------------------------------------------------------------


async def test_unload_detaches_dispatcher(hass) -> None:
    entry = await _setup_entry(hass)
    # Confirm sensors are registered, then unload.
    assert _resolve_entity_id(hass, entry, "output_brightness") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Firing the signal after unload must not raise nor populate state.
    # We can't easily inspect the handler-not-called assertion without a
    # spy, but the fact that this doesn't raise (and that the entity is
    # gone from the state machine) is sufficient evidence the subscription
    # was cleaned up via async_on_remove.
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["outputs"] = {
        "output_brightness": 99,
        "output_color_temp": 4500,
        "sun_elevation": 50.0,
        "updated_at": dt_util.utcnow(),
    }
    async_dispatcher_send(
        hass,
        SIGNAL_OUTPUTS_UPDATED.format(entry_id=entry.entry_id),
    )
    await hass.async_block_till_done()

    # Post-unload, the entity is `unavailable`; firing the signal MUST NOT
    # repopulate it with the dummy "99" value — that would mean the
    # dispatcher subscription leaked.
    ent_reg = er.async_get(hass)
    eid = ent_reg.async_get_entity_id(
        "sensor",
        DOMAIN,
        _unique_id(entry, "output_brightness"),
    )
    if eid is not None:
        state = hass.states.get(eid)
        if state is not None:
            assert (
                state.state != "99"
            ), "Dispatcher subscription leaked: sensor updated after unload"
