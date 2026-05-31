"""Tests for the runtime range number platform (CDiT fork).

Covers the `runtime-range-controls` capability: entity surface, restore,
no-reload-on-slider write, and the curve-math read path.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from homeassistant.components.number import NumberMode
from homeassistant.const import CONF_NAME
from homeassistant.core import State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.adaptive_lighting.const import (
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONFIG_ENTRY_VERSION,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_COLOR_TEMP,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_COLOR_TEMP,
    DOMAIN,
)

PROFILE_NAME = "test_profile"
FIELD_KEYS = ("min_brightness", "max_brightness", "min_color_temp", "max_color_temp")


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


def _unique_id(entry, field_key: str) -> str:
    return f"{entry.entry_id}_{field_key}"


def _resolve_entity_id(hass, entry, field_key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "number",
        DOMAIN,
        _unique_id(entry, field_key),
    )


# ---------------------------------------------------------------------------
# 7.2 — Four entities per entry, expected suffixes
# ---------------------------------------------------------------------------


async def test_four_range_entities_registered(hass) -> None:
    entry = await _setup_entry(hass)
    registry = er.async_get(hass)
    for field_key in FIELD_KEYS:
        eid = registry.async_get_entity_id(
            "number",
            DOMAIN,
            _unique_id(entry, field_key),
        )
        assert eid is not None, f"Missing number entity for {field_key}"
        assert eid.startswith("number.")


# ---------------------------------------------------------------------------
# 7.3 — Same device as the profile's switches
# ---------------------------------------------------------------------------


async def test_number_entities_share_switch_device(hass) -> None:
    entry = await _setup_entry(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    # The master switch uses the profile name as unique_id.
    master_eid = ent_reg.async_get_entity_id("switch", DOMAIN, PROFILE_NAME)
    assert master_eid is not None
    master_dev_id = ent_reg.async_get(master_eid).device_id
    assert master_dev_id

    for field_key in FIELD_KEYS:
        eid = _resolve_entity_id(hass, entry, field_key)
        assert ent_reg.async_get(eid).device_id == master_dev_id

    device = dev_reg.async_get(master_dev_id)
    assert device.name == PROFILE_NAME  # D11: profile name, no integration prefix


# ---------------------------------------------------------------------------
# 7.4 — Selector attributes match D6 table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_key,expected",
    [
        ("min_brightness", {"min": 1.0, "max": 100.0, "step": 1, "unit": "%"}),
        ("max_brightness", {"min": 1.0, "max": 100.0, "step": 1, "unit": "%"}),
        ("min_color_temp", {"min": 1000.0, "max": 10000.0, "step": 100, "unit": "K"}),
        ("max_color_temp", {"min": 1000.0, "max": 10000.0, "step": 100, "unit": "K"}),
    ],
)
async def test_number_entity_attributes(hass, field_key, expected) -> None:
    entry = await _setup_entry(hass)
    eid = _resolve_entity_id(hass, entry, field_key)
    state = hass.states.get(eid)
    assert state is not None
    attrs = state.attributes
    assert attrs["min"] == expected["min"]
    assert attrs["max"] == expected["max"]
    assert attrs["step"] == expected["step"]
    assert attrs["unit_of_measurement"] == expected["unit"]
    assert attrs["mode"] == NumberMode.SLIDER


# ---------------------------------------------------------------------------
# 7.4b — Fresh profile (only a name) seeds sensible DEFAULT_*, not native_min
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_key", "expected_default"),
    [
        ("min_brightness", DEFAULT_MIN_BRIGHTNESS),
        ("max_brightness", DEFAULT_MAX_BRIGHTNESS),
        ("min_color_temp", DEFAULT_MIN_COLOR_TEMP),
        ("max_color_temp", DEFAULT_MAX_COLOR_TEMP),
    ],
)
async def test_new_profile_seeds_sensible_defaults(
    hass,
    field_key,
    expected_default,
) -> None:
    """A profile created with only a name must come up at DEFAULT_*.

    Regression: the seed previously fell back to the slider's native_min,
    so a brand-new group ran at max_brightness=1% and a collapsed
    1000-1000K color-temp range until the options dialog was saved once.
    """
    entry = await _setup_entry(hass)  # data={name}, options={}
    eid = _resolve_entity_id(hass, entry, field_key)
    state = hass.states.get(eid)
    assert state is not None
    assert float(state.state) == float(expected_default)


# ---------------------------------------------------------------------------
# 7.5 — async_set_native_value does NOT write to entry.options
# ---------------------------------------------------------------------------


async def test_slider_set_does_not_update_entry_options(hass) -> None:
    entry = await _setup_entry(hass)
    eid = _resolve_entity_id(hass, entry, "min_brightness")
    snapshot_options = dict(entry.options)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": eid, "value": 42},
        blocking=True,
    )
    assert dict(entry.options) == snapshot_options
    assert float(hass.states.get(eid).state) == 42.0


# ---------------------------------------------------------------------------
# 7.6 — slider change does not invoke unload/setup
# ---------------------------------------------------------------------------


async def test_slider_change_no_reload(hass) -> None:
    entry = await _setup_entry(hass)
    eid = _resolve_entity_id(hass, entry, "max_brightness")
    with (
        patch(
            "custom_components.adaptive_lighting.async_setup_entry",
        ) as setup_spy,
        patch(
            "custom_components.adaptive_lighting.async_unload_entry",
        ) as unload_spy,
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": eid, "value": 70},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert setup_spy.call_count == 0
    assert unload_spy.call_count == 0


# ---------------------------------------------------------------------------
# 7.7 — RestoreNumber: restored state wins on a plain restart
# ---------------------------------------------------------------------------


async def test_restore_state_survives_restart(hass) -> None:
    """The entity restores its last value when entry was NOT modified since."""
    # Build an entry whose modified_at is in the deep past so the restored
    # state (which we prime fresh) is treated as newer.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: PROFILE_NAME},
        options={CONF_MIN_BRIGHTNESS: 5},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)

    # Force modified_at into the past so the restored state's last_updated
    # (which will be "now" when the cache is primed) is treated as fresher.
    object.__setattr__(
        entry,
        "modified_at",
        datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc),
    )

    # Prime the restore cache with a saved native_value of 30.
    fake_state = State("number.test_profile_min_brightness", "30")
    fake_extra = {
        "native_value": 30.0,
        "native_unit_of_measurement": "%",
    }
    mock_restore_cache_with_extra_data(hass, [(fake_state, fake_extra)])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    eid = _resolve_entity_id(hass, entry, "min_brightness")
    state = hass.states.get(eid)
    assert state is not None
    assert float(state.state) == 30.0  # restored, not the options default of 5


# ---------------------------------------------------------------------------
# 7.8 — Options-flow save with new range value propagates to the entity
# ---------------------------------------------------------------------------


async def test_options_save_overrides_slider(hass) -> None:
    """A just-saved options value beats the prior slider position after reload."""
    entry = await _setup_entry(
        hass,
        options={
            CONF_MAX_BRIGHTNESS: 100,
            CONF_MIN_BRIGHTNESS: 5,
            "min_color_temp": 2200,
            "max_color_temp": 5500,
            "lights": [],
            "sunrise_entity": "sensor.sun_next_rising",
            "sunset_entity": "sensor.sun_next_setting",
        },
    )
    eid = _resolve_entity_id(hass, entry, "min_brightness")
    # Move the slider to 30
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": eid, "value": 30},
        blocking=True,
    )
    assert float(hass.states.get(eid).state) == 30.0

    # Save new options that set min_brightness to 55.
    new_options = dict(entry.options)
    new_options[CONF_MIN_BRIGHTNESS] = 55
    hass.config_entries.async_update_entry(entry, options=new_options)
    await hass.async_block_till_done()
    # Reload so the entity is recreated; OptionsFlowWithReload would do
    # this implicitly on a real options-flow save.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    eid_after = _resolve_entity_id(hass, entry, "min_brightness")
    state_after = hass.states.get(eid_after)
    assert state_after is not None
    assert float(state_after.state) == 55.0  # just-saved options wins


# ---------------------------------------------------------------------------
# 7.9 — Options flow open seeds the four range fields from entity state
# ---------------------------------------------------------------------------


async def test_options_flow_seeds_from_entity_state(hass) -> None:
    entry = await _setup_entry(hass, options={CONF_MAX_BRIGHTNESS: 100})
    eid = _resolve_entity_id(hass, entry, "max_brightness")
    # Move the slider to 80
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": eid, "value": 80},
        blocking=True,
    )
    # Open the options flow
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    schema = result["data_schema"].schema
    # Find the daytime_curve section and walk its inner schema to find max_brightness default
    daytime = next(sub for k, sub in schema.items() if str(k) == "daytime_curve")
    inner = daytime.schema.schema
    max_b_default = next(k.default() for k in inner if str(k) == CONF_MAX_BRIGHTNESS)
    assert max_b_default == 80  # entity wins over options


# ---------------------------------------------------------------------------
# 7.10 — Options flow open falls back to entry.options when entity unavailable
# ---------------------------------------------------------------------------


async def test_options_flow_fallback_when_entity_unavailable(hass) -> None:
    entry = await _setup_entry(hass, options={CONF_MIN_COLOR_TEMP: 2500})
    eid = _resolve_entity_id(hass, entry, "min_color_temp")
    # Manually wipe the state so it looks unavailable
    hass.states.async_remove(eid)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    daytime = next(sub for k, sub in schema.items() if str(k) == "daytime_curve")
    inner = daytime.schema.schema
    default = next(k.default() for k in inner if str(k) == CONF_MIN_COLOR_TEMP)
    assert default == 2500  # falls back to options


# ---------------------------------------------------------------------------
# 7.11 — Curve math reads runtime values from the number entities
# ---------------------------------------------------------------------------


async def test_curve_math_reads_runtime_range(hass) -> None:
    """When the slider differs from entry.options, the curve uses the slider."""
    entry = await _setup_entry(
        hass,
        options={CONF_MAX_BRIGHTNESS: 100, CONF_MIN_BRIGHTNESS: 5},
    )
    eid = _resolve_entity_id(hass, entry, "max_brightness")
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": eid, "value": 70},
        blocking=True,
    )

    # Grab the master switch and read its live SunLightSettings via property.
    al_data = hass.data[DOMAIN][entry.entry_id]
    al_switch = al_data["switch"]
    settings = al_switch.sun_light_settings
    assert settings.max_brightness == 70  # slider, not options' 100
    assert settings.min_brightness == 5  # entity value (initialized from options)


# ---------------------------------------------------------------------------
# 7.12 — Curve math falls back to options when entity unavailable
# ---------------------------------------------------------------------------


async def test_curve_math_falls_back_on_unavailable(hass, caplog) -> None:
    entry = await _setup_entry(
        hass,
        options={CONF_MAX_BRIGHTNESS: 88, CONF_MIN_BRIGHTNESS: 5},
    )
    eid = _resolve_entity_id(hass, entry, "max_brightness")
    # Wipe the state so the read sees `None`
    hass.states.async_remove(eid)

    al_data = hass.data[DOMAIN][entry.entry_id]
    al_switch = al_data["switch"]

    import logging

    caplog.set_level(logging.DEBUG)
    settings = al_switch.sun_light_settings
    assert settings.max_brightness == 88  # fell back to options
    # DEBUG log mentions the missing entity
    assert "max_brightness" in caplog.text
