import pytest
from unittest.mock import patch, MagicMock
from agent import browser_probe


def test_browser_probe_import():
    assert hasattr(browser_probe, 'run_probe')
