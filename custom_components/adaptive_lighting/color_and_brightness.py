"""Curve math for the Adaptive Lighting integration (CDiT fork).

Replaces upstream's astral-driven, brightness-mode-switchable system with a
single tanh ramp at each sun event. The two event timestamps are not
computed here — they come in as method arguments from the caller, which
reads them from user-configured HA entities (typically `sensor.sun_next_*`
or a Sun2 sensor). See design.md decisions 2, 3, 11.
"""

from __future__ import annotations

import colorsys
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, cast

from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

utcnow: partial[datetime] = partial(datetime.now, UTC)
utcnow.__doc__ = "Get now in UTC time."

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SunLightSettings:
    """Pure curve-math wrapper for one AL profile.

    Holds the brightness/color-temp bounds and the ramp half-width. Sun
    event timestamps are passed into each method by the caller — this
    class does not touch HA state.
    """

    name: str
    max_brightness: int
    max_color_temp: int
    min_brightness: int
    min_color_temp: int
    ramp_half_width_seconds: int

    def brightness_pct(
        self,
        dt: datetime,
        t_sunrise: datetime,
        t_sunset: datetime,
    ) -> float:
        """Brightness percentage at `dt`, ramping tanh-style around each event."""
        return _tanh_day_curve(
            now_ts=dt.timestamp(),
            t_sunrise_ts=t_sunrise.timestamp(),
            t_sunset_ts=t_sunset.timestamp(),
            value_min=self.min_brightness,
            value_max=self.max_brightness,
            half_width=self.ramp_half_width_seconds,
        )

    def color_temp_kelvin(
        self,
        dt: datetime,
        t_sunrise: datetime,
        t_sunset: datetime,
    ) -> int:
        """Color temperature in Kelvin at `dt`, same curve shape as brightness."""
        ct = _tanh_day_curve(
            now_ts=dt.timestamp(),
            t_sunrise_ts=t_sunrise.timestamp(),
            t_sunset_ts=t_sunset.timestamp(),
            value_min=self.min_color_temp,
            value_max=self.max_color_temp,
            half_width=self.ramp_half_width_seconds,
        )
        return 5 * round(ct / 5)  # round to nearest 5 K

    def sun_position(
        self,
        dt: datetime,
        t_sunrise: datetime,
        t_sunset: datetime,
    ) -> float:
        """Synthetic sun position in [-1, +1].

        +1 at peak day (between sunrise + half_width and sunset - half_width),
        -1 at night, 0 at the exact sunrise or sunset event.
        Derived directly from the brightness curve so callers that key off
        sun_position (e.g., for legacy attributes) stay coherent.
        """
        b = self.brightness_pct(dt, t_sunrise, t_sunset)
        delta = self.max_brightness - self.min_brightness
        if delta == 0:
            return 0.0
        return 2 * ((b - self.min_brightness) / delta) - 1

    def brightness_and_color(
        self,
        dt: datetime,
        t_sunrise: datetime,
        t_sunset: datetime,
    ) -> dict[str, Any]:
        """Compute all light values at `dt` from the two sun events."""
        brightness_pct = self.brightness_pct(dt, t_sunrise, t_sunset)
        color_temp_kelvin = self.color_temp_kelvin(dt, t_sunrise, t_sunset)
        sun_position = self.sun_position(dt, t_sunrise, t_sunset)
        r, g, b = color_temperature_to_rgb(color_temp_kelvin)
        rgb_color: tuple[int, int, int] = (round(r), round(g), round(b))
        color_temp_mired: float = math.floor(1000000 / color_temp_kelvin)
        xy_color: tuple[float, float] = color_RGB_to_xy(*rgb_color)
        hs_color: tuple[float, float] = color_xy_to_hs(*xy_color)
        return {
            "brightness_pct": brightness_pct,
            "color_temp_kelvin": color_temp_kelvin,
            "color_temp_mired": color_temp_mired,
            "rgb_color": rgb_color,
            "xy_color": xy_color,
            "hs_color": hs_color,
            "sun_position": sun_position,
            "force_rgb_color": False,
        }

    def get_settings(
        self,
        transition: float | None,
        t_sunrise: datetime,
        t_sunset: datetime,
    ) -> dict[str, float | int | tuple[float, float] | tuple[float, float, float]]:
        """All light values shifted `transition` seconds into the future."""
        dt = utcnow() + timedelta(seconds=transition or 0)
        return self.brightness_and_color(dt, t_sunrise, t_sunset)


def _tanh_day_curve(
    now_ts: float,
    t_sunrise_ts: float,
    t_sunset_ts: float,
    value_min: float,
    value_max: float,
    half_width: int,
) -> float:
    """Piecewise tanh ramp from value_min to value_max around sunrise/sunset.

    Schema (specs/options-flow/spec.md R4):
      - t ≤ t_sunrise − half_width:                  value_min
      - t_sunrise − half_width < t < t_sunrise + half_width:
                                                     tanh ramp min → max
      - t_sunrise + half_width ≤ t ≤ t_sunset − half_width:
                                                     value_max
      - t_sunset − half_width < t < t_sunset + half_width:
                                                     tanh ramp max → min
      - t ≥ t_sunset + half_width:                   value_min
    """
    sunrise_lo = t_sunrise_ts - half_width
    sunrise_hi = t_sunrise_ts + half_width
    sunset_lo = t_sunset_ts - half_width
    sunset_hi = t_sunset_ts + half_width

    if now_ts <= sunrise_lo or now_ts >= sunset_hi:
        return value_min
    if sunrise_hi <= now_ts <= sunset_lo:
        return value_max
    if sunrise_lo < now_ts < sunrise_hi:
        return scaled_tanh(
            now_ts - t_sunrise_ts,
            x1=-half_width,
            x2=+half_width,
            y1=0.05,
            y2=0.95,
            y_min=value_min,
            y_max=value_max,
        )
    return scaled_tanh(
        now_ts - t_sunset_ts,
        x1=-half_width,
        x2=+half_width,
        y1=0.95,
        y2=0.05,
        y_min=value_min,
        y_max=value_max,
    )


def find_a_b(x1: float, x2: float, y1: float, y2: float) -> tuple[float, float]:
    """Coefficients `a, b` for y = 0.5 * (tanh(a * (x - b)) + 1) passing through (x1,y1) and (x2,y2)."""
    a = (math.atanh(2 * y2 - 1) - math.atanh(2 * y1 - 1)) / (x2 - x1)
    b = x1 - (math.atanh(2 * y1 - 1) / a)
    return a, b


def scaled_tanh(
    x: float,
    x1: float,
    x2: float,
    y1: float = 0.05,
    y2: float = 0.95,
    y_min: float = 0.0,
    y_max: float = 100.0,
) -> float:
    """Scaled and shifted tanh from y_min to y_max, with knees at (x1,y1) and (x2,y2)."""
    a, b = find_a_b(x1, x2, y1, y2)
    return y_min + (y_max - y_min) * 0.5 * (math.tanh(a * (x - b)) + 1)


def lerp_color_hsv(
    rgb1: tuple[float, float, float],
    rgb2: tuple[float, float, float],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors in HSV color space.

    Kept for backwards compatibility with any caller that imports it. Not
    used by the curve path in this fork.
    """
    t = abs(t)
    assert 0 <= t <= 1
    hsv1 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb1])
    hsv2 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb2])
    hsv = (
        hsv1[0] + t * (hsv2[0] - hsv1[0]),
        hsv1[1] + t * (hsv2[1] - hsv1[1]),
        hsv1[2] + t * (hsv2[2] - hsv1[2]),
    )
    rgb = tuple(round(x * 255) for x in colorsys.hsv_to_rgb(*hsv))
    return cast("tuple[int, int, int]", rgb)


def lerp(x: float, x1: float, x2: float, y1: float, y2: float) -> float:
    """Linearly interpolate between two values."""
    return y1 + (x - x1) * (y2 - y1) / (x2 - x1)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))
