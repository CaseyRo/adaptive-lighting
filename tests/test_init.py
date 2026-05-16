"""Tests for the CDiT Adaptive Lighting integration setup.

Covers spec R8 (strict version-break) and R9 (sleep-switch tombstone).
"""

from __future__ import annotations

import logging

import pytest
from custom_components.adaptive_lighting.const import (
    CONFIG_ENTRY_VERSION,
    DEFAULT_NAME,
    DOMAIN,
    UNDO_UPDATE_LISTENER,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry


# ---------------------------------------------------------------------------
# R8 — strict version break
# ---------------------------------------------------------------------------


async def test_successful_setup_on_current_version(hass) -> None:
    """R8: an entry created on the current major succeeds and runs no
    tombstone log line."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.LOADED
    assert UNDO_UPDATE_LISTENER in hass.data[DOMAIN][entry.entry_id]


async def test_stale_version_raises_config_entry_error(hass, caplog) -> None:
    """R8: an entry created on the previous major fails with our
    ConfigEntryError, leaving the entry in the MIGRATION_ERROR state.
    HA routes version mismatches through `async_migrate_entry`."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION - 1,
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.MIGRATION_ERROR
    # The full captured log (which includes the exception traceback) should
    # carry our friendly "delete and recreate" message so the user sees it.
    text = caplog.text.lower()
    assert "delete" in text and "recreate" in text


async def test_unload_entry(hass) -> None:
    """A current-version entry can be unloaded cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert DOMAIN not in hass.data


# ---------------------------------------------------------------------------
# R9 — sleep-switch tombstone cleanup
# ---------------------------------------------------------------------------


async def test_orphan_sleep_entity_is_removed_on_setup(hass, caplog) -> None:
    """R9: a leftover sleep_mode switch owned by this entry is removed and
    one INFO log line is emitted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)

    # Seed the registry with an orphan sleep-mode entity owned by this entry.
    registry = er.async_get(hass)
    orphan = registry.async_get_or_create(
        domain="switch",
        platform=DOMAIN,
        unique_id=f"{DEFAULT_NAME}_sleep_mode",
        config_entry=entry,
    )

    with caplog.at_level(logging.INFO):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert registry.async_get(orphan.entity_id) is None, (
        "Orphan sleep entity should have been removed."
    )
    # One INFO log line naming the entity ID.
    assert any(
        orphan.entity_id in record.message
        for record in caplog.records
        if record.levelno == logging.INFO
    )


async def test_tombstone_helper_is_idempotent(hass, caplog) -> None:
    """R9: a second setup with no orphans finds nothing and emits no log line."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)

    # First setup: no orphans seeded, no log line.
    with caplog.at_level(logging.INFO):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert not any(
        "sleep_mode" in record.message.lower()
        for record in caplog.records
        if record.levelno == logging.INFO
    )


async def test_tombstone_skips_foreign_entities(hass, caplog) -> None:
    """R9 + D12: an entity matching the name pattern but owned by another
    config entry is not removed."""
    our_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
        version=CONFIG_ENTRY_VERSION,
    )
    our_entry.add_to_hass(hass)

    # Different config entry, different domain, but a name that ends in
    # _sleep_mode — should NOT be touched.
    foreign_entry = MockConfigEntry(
        domain="other_integration",
        data={},
    )
    foreign_entry.add_to_hass(hass)

    registry = er.async_get(hass)
    foreign_entity = registry.async_get_or_create(
        domain="switch",
        platform="other_integration",
        unique_id=f"unrelated_{DEFAULT_NAME}_sleep_mode",
        config_entry=foreign_entry,
    )

    assert await hass.config_entries.async_setup(our_entry.entry_id)

    assert registry.async_get(foreign_entity.entity_id) is not None, (
        "Foreign-owned entity matching name pattern must not be removed."
    )
