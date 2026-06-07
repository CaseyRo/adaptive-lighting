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
    anchor_sun_events,
    lux_reduce,
)

HALF_WIDTH = 1800  # seconds — matches RAMP_HALF_WIDTH_SECONDS

# Fixed reference day: 2026-03-21 in UTC, sunrise 06:00, sunset 18:00.
T_SUNRISE = dt.datetime(2026, 3, 21, 6, 0, 0, tzinfo=UTC)
T_SUNSET = dt.datetime(2026, 3, 21, 18, 0, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> SunLightSettings:
    """Fixed test range — 5-100 % brightness, 2200-5500 K (explicit, not DEFAULT_*)."""
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
        """T = sunrise - 2h → still deep night, brightness at minimum."""
        t = T_SUNRISE - timedelta(hours=2)
        assert settings.brightness_pct(t, T_SUNRISE, T_SUNSET) == 5

    def test_min_brightness_exactly_at_clamp_boundary(self, settings):
        """T = sunrise - half_width → exactly at the boundary, still min."""
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


class TestLuxReduce:
    """Reduce-only lux gate: target/current ratio, floor at min_brightness."""

    def test_above_target_reduces_brightness(self):
        result = lux_reduce(85.0, 500, 700, 5)
        assert result == pytest.approx(85.0 * 500 / 700, abs=0.1)

    def test_below_target_passes_through(self):
        assert lux_reduce(85.0, 500, 300, 5) == 85.0

    def test_exactly_at_target_passes_through(self):
        assert lux_reduce(85.0, 500, 500, 5) == 85.0

    def test_below_min_brightness_returns_none(self):
        assert lux_reduce(80.0, 500, 10000, 5) is None

    def test_zero_current_lux_passes_through(self):
        assert lux_reduce(85.0, 500, 0, 5) == 85.0

    def test_negative_current_lux_passes_through(self):
        assert lux_reduce(85.0, 500, -10, 5) == 85.0

    def test_zero_target_lux_passes_through(self):
        assert lux_reduce(85.0, 0, 500, 5) == 85.0

    def test_exactly_at_min_brightness_keeps_on(self):
        # 100 * (500/10000) = 5.0, which is NOT < 5 → stays on at 5.0
        result = lux_reduce(100.0, 500, 10000, 5)
        assert result == pytest.approx(5.0)

    def test_boundary_just_above_min(self):
        result = lux_reduce(100.0, 500, 9900, 5)
        assert result is not None
        assert result >= 5

    def test_boundary_just_below_min(self):
        result = lux_reduce(100.0, 500, 10100, 5)
        assert result is None  # 100 * 500/10100 ≈ 4.95 < 5


class TestAnchorSunEvents:
    """Day-anchoring of `next_*`-style sun sensor timestamps.

    Regression for the June bug: `sun_next_rising` flips to tomorrow at
    sunrise, and on long summer days tomorrow's sunrise is < 12 h away by
    mid-afternoon — the old `now + 12h` guard then left the pair
    describing tomorrow, collapsing the curve to minimum around 17:30
    local instead of ramping down at sunset.
    """

    # June day in NL: sunrise 03:20 UTC (05:20 CEST), sunset 20:00 UTC.
    JUNE_SUNRISE = dt.datetime(2026, 6, 7, 3, 20, tzinfo=UTC)
    JUNE_SUNSET = dt.datetime(2026, 6, 7, 20, 0, tzinfo=UTC)
    ONE_DAY = timedelta(days=1)

    def test_morning_before_sunrise_unchanged(self):
        """Pre-sunrise both sensors hold today's events — no shift."""
        now = self.JUNE_SUNRISE - timedelta(hours=2)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE,
            self.JUNE_SUNSET,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)

    def test_daytime_sunrise_flipped_is_pulled_back(self):
        """Mid-morning: next_rising points at tomorrow → pulled back a day."""
        now = self.JUNE_SUNRISE + timedelta(hours=4)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE + self.ONE_DAY,
            self.JUNE_SUNSET,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)

    def test_june_late_afternoon_regression(self):
        """17:30 CEST in June: tomorrow's sunrise is < 12 h away.

        The old heuristic refused to pull it back and the curve collapsed
        to min. The anchored pair must still describe *today*.
        """
        now = dt.datetime(2026, 6, 7, 15, 30, tzinfo=UTC)  # 17:30 CEST
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE + self.ONE_DAY,
            self.JUNE_SUNSET,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)
        # And the curve at that moment is full day, not minimum.
        settings = SunLightSettings(
            name="t",
            min_brightness=5,
            max_brightness=100,
            min_color_temp=2200,
            max_color_temp=5500,
            ramp_half_width_seconds=HALF_WIDTH,
        )
        assert settings.brightness_pct(now, r, s) == 100

    def test_post_sunset_ramp_tail_completes(self):
        """10 min after sunset both sensors flipped to tomorrow.

        Still inside the down-ramp → both pulled back so the ramp
        finishes instead of snapping to minimum.
        """
        now = self.JUNE_SUNSET + timedelta(minutes=10)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE + self.ONE_DAY,
            self.JUNE_SUNSET + self.ONE_DAY,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)

    def test_after_ramp_tail_stays_tomorrow(self):
        """Past sunset + half_width the tomorrow pair is fine (night = min)."""
        now = self.JUNE_SUNSET + timedelta(seconds=HALF_WIDTH, minutes=5)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE + self.ONE_DAY,
            self.JUNE_SUNSET + self.ONE_DAY,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (
            self.JUNE_SUNRISE + self.ONE_DAY,
            self.JUNE_SUNSET + self.ONE_DAY,
        )

    def test_after_midnight_unchanged(self):
        """00:30: sensors hold today's events again — no shift."""
        now = dt.datetime(2026, 6, 7, 0, 30, tzinfo=UTC)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE,
            self.JUNE_SUNSET,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)

    def test_winter_afternoon_still_anchors(self):
        """Long-night season: the old guard happened to work; new code too."""
        sunrise = dt.datetime(2026, 12, 21, 7, 30, tzinfo=UTC)
        sunset = dt.datetime(2026, 12, 21, 15, 30, tzinfo=UTC)
        now = dt.datetime(2026, 12, 21, 13, 0, tzinfo=UTC)
        r, s = anchor_sun_events(sunrise + self.ONE_DAY, sunset, now, HALF_WIDTH)
        assert (r, s) == (sunrise, sunset)

    def test_stale_today_sunset_pushed_forward(self):
        """A 'today's sunset' sensor still holding yesterday's event."""
        now = self.JUNE_SUNRISE + timedelta(hours=4)
        r, s = anchor_sun_events(
            self.JUNE_SUNRISE,
            self.JUNE_SUNSET - self.ONE_DAY,
            now,
            HALF_WIDTH,
        )
        assert (r, s) == (self.JUNE_SUNRISE, self.JUNE_SUNSET)
