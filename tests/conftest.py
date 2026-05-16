"""Pytest configuration for Adaptive Lighting tests (CDiT fork).

Uses `pytest-homeassistant-custom-component` (PHACC). The
`enable_custom_integrations` fixture lets HA discover and load this
integration from `custom_components/` during tests.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """PHACC requires this fixture to be active for HA to find the
    integration under custom_components/.
    """
    return


@pytest.fixture(autouse=True)
def mock_template_deprecation_issue():
    """Mock the template helpers' legacy deprecation-issue creation.

    Template lights used as fixtures in upstream tests trigger a
    deprecation-issue call that requires translation entries we don't ship.
    No-op the call so tests don't fail on translation validation.
    """
    try:
        with patch(
            "homeassistant.components.template.helpers.create_legacy_template_issue",
        ):
            yield
    except (ImportError, ModuleNotFoundError, AttributeError):
        yield
