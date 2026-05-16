"""Adaptive Lighting integration in Home Assistant (CDiT fork)."""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_SOURCE
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .const import (
    _DOMAIN_SCHEMA,  # pyright: ignore[reportPrivateUsage]
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_NAME,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    UNDO_UPDATE_LISTENER,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]

# unique_id suffix(es) that this fork no longer creates. Any entity in the
# registry whose unique_id ends with one of these strings AND that is owned
# by an Adaptive Lighting config entry is a leftover from upstream and is
# removed on first setup (spec R9, design D12).
_REMOVED_UNIQUE_ID_SUFFIXES = ("_sleep_mode",)


def _all_unique_names(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate that all entities have a unique profile name."""
    hosts = [device[CONF_NAME] for device in value]
    schema = vol.Schema(vol.Unique())
    schema(hosts)
    return value


CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [_DOMAIN_SCHEMA], _all_unique_names)},
    extra=vol.ALLOW_EXTRA,
)


async def reload_configuration_yaml(event: Event) -> None:
    """Reload configuration.yaml."""
    hass: HomeAssistant | None = event.data.get("hass")
    if hass is not None:
        await hass.services.async_call("homeassistant", "check_config", {})
    else:
        _LOGGER.error("HomeAssistant instance not found in event data.")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Import integration from config."""
    if DOMAIN in config:
        for entry in config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={CONF_SOURCE: SOURCE_IMPORT},
                    data=entry,
                ),
            )
    return True


def _remove_orphan_sleep_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Remove sleep-mode switch entities left behind by upstream AL.

    Idempotent: subsequent runs find nothing and emit no log lines. Only
    removes entities whose config_entry_id matches the current entry, so
    foreign entities matching the name pattern are not touched.
    Spec R9, design D12.
    """
    registry = er.async_get(hass)
    entries_to_remove = [
        entry.entity_id
        for entry in registry.entities.values()
        if entry.config_entry_id == config_entry.entry_id
        and any(
            entry.unique_id.endswith(suffix)
            for suffix in _REMOVED_UNIQUE_ID_SUFFIXES
        )
    ]
    for entity_id in entries_to_remove:
        _LOGGER.info(
            "Removing orphan entity %s left behind by upstream Adaptive Lighting "
            "(sleep mode is not supported in the CDiT fork).",
            entity_id,
        )
        registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the component."""
    # Spec R8 + design D4: reject entries from older, incompatible versions
    # with a clear "recreate this entry" message rather than silently migrating.
    if config_entry.version < CONFIG_ENTRY_VERSION:
        msg = (
            f"Adaptive Lighting v{CONFIG_ENTRY_VERSION} (CDiT fork) is incompatible "
            f"with the existing config entry (version {config_entry.version}). "
            "Delete and recreate the entry from Settings → Devices & Services."
        )
        raise ConfigEntryError(msg)

    _remove_orphan_sleep_entities(hass, config_entry)

    data = hass.data.setdefault(DOMAIN, {})

    # Reload YAML configs on `hass.config.entry_updated` (covers `quick reload`
    # and explicit `hass.reload_config_entry` calls).
    hass.bus.async_listen("hass.config.entry_updated", reload_configuration_yaml)

    undo_listener = config_entry.add_update_listener(async_update_options)
    data[config_entry.entry_id] = {UNDO_UPDATE_LISTENER: undo_listener}
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(
        config_entry,
        "switch",
    )
    data = hass.data[DOMAIN]
    data[config_entry.entry_id][UNDO_UPDATE_LISTENER]()
    if unload_ok:
        data.pop(config_entry.entry_id)

    if len(data) == 1 and ATTR_ADAPTIVE_LIGHTING_MANAGER in data:
        # no more config_entries
        manager = data.pop(ATTR_ADAPTIVE_LIGHTING_MANAGER)
        manager.disable()

    if not data:
        hass.data.pop(DOMAIN)

    return unload_ok
