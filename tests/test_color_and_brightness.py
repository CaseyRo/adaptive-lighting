"""Tests for the CDiT tanh curve in color_and_brightness.py.

Covers spec R4 scenarios: brightness is min before sunrise, midpoint at the
sunrise event, max during the day, and the same curve shape applies to
color temperature. Curve math is pure; no Home Assistant needed.
"""

from __future__ import annotations

import datetime as dt
from datetime import UTC, timedelta

import pytest

from custom_components.adaptive_lighting.color_and_brightness import (
    SunLightSettings,
    _tanh_day_curve,
)

HALF_WIDTH = 1800  # seconds — matches RAMP_HALF_WIDTH_SECONDS

# Fixed reference day: 2026-03-21 in UTC, sunrise 06:00, sunset 18:00.
T_SUNRISE = dt.datetime(2026, 3, 21, 6, 0, 0, tzinfo=UTC)
T_SUNSET = dt.datetime(2026, 3, 21, 18, 0, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> SunLightSettings:
    """Standard CDiT defaults — 5–100 % brightness, 2200–5500 K."""
    return SunLightSettings(
        name="test",
        min_brightness=5,
        max_brightness=100,
        min_color_temp=2200,
        max_color_temp=5500,
        ramp_half_width_seconds=HALF_WIDTH,
    )


class TestBrightnessCurve:
    """Spec R4: piecewise tanh ramp around the two sun events."""

    def test_min_brightness_more_than_half_width_before_sunrise(self, settings):
        """T = sunrise − 2h → still deep night, brightness at minimum."""
        t = T_SUNRISE - timedelta(hours=2)
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 5

    def test_min_brightness_exactly_at_clamp_boundary(self, settings):
        """T = sunrise − half_width → exactly at the boundary, still min."""
        t = T_SUNRISE - timedelta(seconds=HALF_WIDTH)
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 5

    def test_midpoint_at_sunrise_event(self, settings):
        """T = sunrise → exactly the midpoint of min and max by tanh symmetry."""
        b = settings.brightness_pct(T_SUNRISE, T_SUNRISE, T_SUNSET)
        expected_mid = (5 + 100) / 2
        assert abs(b - expected_mid) < 0.5

    def test_max_brightness_30min_after_sunrise(self, settings):
        """T = sunrise + half_width → fully ramped, brightness at max."""
        t = T_SUNRISE + timedelta(seconds=HALF_WIDTH)
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 100

    def test_max_brightness_during_full_day(self, settings):
        """Mid-afternoon → still at max."""
        t = T_SUNRISE + timedelta(hours=6)  # noon
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 100

    def test_min_brightness_long_after_sunset(self, settings):
        """T = sunset + 2h → back to minimum."""
        t = T_SUNSET + timedelta(hours=2)
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 5

    def test_midpoint_at_sunset_event(self, settings):
        """T = sunset → exact midpoint going down."""
        b = settings.brightness_pct(T_SUNSET, T_SUNRISE, T_SUNSET)
        expected_mid = (5 + 100) / 2
        assert abs(b - expected_mid) < 0.5


class TestColorTempCurve:
    """Spec R4: color temperature follows the same shape as brightness."""

    def test_min_color_temp_at_night(self, settings):
        t = T_SUNRISE - timedelta(hours=3)
        # Color temp rounds to nearest 5, so 2200 stays 2200.
        assert settings.color_temp_kelvin(t, T_SUNRISE, T_SUNSET) == 2200

    def test_max_color_temp_at_noon(self, settings):
        t = T_SUNRISE + timedelta(hours=6)
        assert settings.color_temp_kelvin(t, T_SUNRISE, T_SUNSET) == 5500

    def test_same_curve_shape_as_brightness(self, settings):
        """At any ramp-window point, the fraction of the curve should match
        between brightness (5-100) and color temp (2200-5500).
        """
        # Pick a point inside the sunrise ramp window.
        t = T_SUNRISE + timedelta(minutes=10)
        b = settings.brightness_pct(t, T_SUNRISE, T_SUNSET)
        ct = settings.color_temp_kelvin(t, T_SUNRISE, T_SUNSET)
        # fraction of brightness range
        b_frac = (b - 5) / (100 - 5)
        # corresponding raw color-temp before nearest-5 rounding
        ct_expected_raw = settings.min_color_temp + b_frac * 3300
        # allow ±5 K tolerance for the rounding
        assert ct_expected_raw - 5 <= ct <= ct_expected_raw + 5


class TestSunPosition:
    """Synthetic sun position derived from the brightness curve."""

    def test_minus_one_at_night(self, settings):
        t = T_SUNRISE - timedelta(hours=3)
        assert settings.sun_position(t, T_SUNRISE, T_SUNSET) == -1.0

    def test_plus_one_at_noon(self, settings):
        t = T_SUNRISE + timedelta(hours=6)
        assert settings.sun_position(t, T_SUNRISE, T_SUNSET) == 1.0

    def test_zero_at_event(self, settings):
        # By tanh symmetry, sun_position at the event is ~0.
        sp = settings.sun_position(T_SUNRISE, T_SUNRISE, T_SUNSET)
        assert abs(sp) < 0.02


class TestTanhDayCurveDirect:
    """Direct unit tests for the curve helper, without SunLightSettings."""

    def test_below_window(self):
        t = T_SUNRISE.timestamp() - HALF_WIDTH - 1
        v = _tanh_day_curve(
            t,
            T_SUNRISE.timestamp(),
            T_SUNSET.timestamp(),
            value_min=0,
            value_max=100,
            half_width=HALF_WIDTH,
        )
        assert v == 0

    def test_above_window(self):
        t = T_SUNSET.timestamp() + HALF_WIDTH + 1
        v = _tanh_day_curve(
            t,
            T_SUNRISE.timestamp(),
            T_SUNSET.timestamp(),
            value_min=0,
            value_max=100,
            half_width=HALF_WIDTH,
        )
        assert v == 0

    def test_during_day_hold(self):
        # Mid-afternoon, well inside the day window.
        t = T_SUNRISE.timestamp() + 4 * 3600
        v = _tanh_day_curve(
            t,
            T_SUNRISE.timestamp(),
            T_SUNSET.timestamp(),
            value_min=0,
            value_max=100,
            half_width=HALF_WIDTH,
        )
        assert v == 100
