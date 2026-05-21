"""Number platform for the Adaptive Lighting integration (CDiT fork).

Each config entry exposes four live-tunable sliders that own the runtime
values the curve math reads on every tick:

- ``number.<profile>_min_brightness``
- ``number.<profile>_max_brightness``
- ``number.<profile>_min_color_temp``
- ``number.<profile>_max_color_temp``

The entities extend ``RestoreNumber`` so values survive HA restarts without
a separate ``Store`` helper. Slider changes do NOT write back to
``entry.options`` (no integration reload). Options-flow saves reload the
integration, and the resulting fresh entities prefer the just-saved
``entry.options`` value over the restored state. See design.md decisions
1-3 of the ``add-runtime-range-controls`` change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberMode,
    RestoreNumber,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, RANGE_ENTITIES

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the four range entities for this config entry."""
    entities = [
        AdaptiveRangeNumber(
            entry=config_entry,
            field_key=row["field_key"],
            conf_key=row["conf_key"],
            display_name=row["name"],
            native_min=row["native_min"],
            native_max=row["native_max"],
            step=row["step"],
            unit=row["unit"],
            icon=row["icon"],
        )
        for row in RANGE_ENTITIES
    ]
    async_add_entities(entities)


class AdaptiveRangeNumber(RestoreNumber):
    """Live-tunable slider for one of the four curve range values."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        field_key: str,
        conf_key: str,
        display_name: str,
        native_min: float,
        native_max: float,
        step: float,
        unit: str,
        icon: str,
    ) -> None:
        """Initialise a single range number entity."""
        self._entry = entry
        self._field_key = field_key
        self._conf_key = conf_key
        self._attr_name = display_name
        self._attr_translation_key = field_key
        self._attr_unique_id = f"{entry.entry_id}_{field_key}"
        self._attr_native_min_value = native_min
        self._attr_native_max_value = native_max
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        # Initial value falls back to the options snapshot until
        # async_added_to_hass overrides with a restored or just-saved value.
        self._attr_native_value = self._options_value()

    @property
    def device_info(self) -> DeviceInfo:
        """Group with the profile's switches under one device."""
        profile_name = self._entry.data.get("name") or self._entry.title
        return DeviceInfo(
            identifiers={(DOMAIN, profile_name)},
            name=profile_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _options_value(self) -> float:
        """Read the seed value from entry.options (typed cast)."""
        raw = self._entry.options.get(self._conf_key)
        if raw is None:
            raw = self._entry.data.get(self._conf_key, self._attr_native_min_value)
        return float(raw)

    async def async_added_to_hass(self) -> None:
        """Seed the entity value with three-tier precedence.

        (a) First-creation: no restored state → use ``entry.options[conf_key]``.
        (b) Restored state exists AND was persisted AFTER the entry was last
            modified → the user moved the slider since the last options-flow
            save; use the restored value (slider survives restart).
        (c) Restored state exists BUT the entry was modified AFTER the
            restored state was persisted → an options-flow save changed the
            value; use ``entry.options[conf_key]`` (just-saved wins).
        """
        await super().async_added_to_hass()
        options_value = self._options_value()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "unknown", "unavailable"):
            self._attr_native_value = options_value
            return
        try:
            restored_value = float(last_state.state)
        except (TypeError, ValueError):
            self._attr_native_value = options_value
            return
        entry_modified = getattr(self._entry, "modified_at", None)
        if entry_modified is not None and entry_modified > last_state.last_updated:
            # Entry was edited (via options-flow save) after the entity's
            # last persist → the just-saved options value supersedes.
            self._attr_native_value = options_value
        else:
            self._attr_native_value = restored_value

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new slider value to entity state only.

        Does NOT write to ``entry.options`` — that would trigger an
        ``OptionsFlowWithReload`` reload on every slider tick. The
        RestoreNumber base class persists the value across restarts.
        """
        self._attr_native_value = value
        self.async_write_ha_state()
