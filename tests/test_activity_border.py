import os
from unittest.mock import MagicMock, patch
import pytest
from ui.activity_border import run_indicator, ActivityIndicator


def test_activity_indicator_init():
    context = MagicMock()
    mock_event = MagicMock()
    mock_process = MagicMock()
    context.Event.return_value = mock_event
    context.Process.return_value = mock_process

    indicator = ActivityIndicator(context)
    assert indicator.stop == mock_event
    assert indicator.ready == mock_event
    assert indicator.process == mock_process


def test_activity_indicator_lifecycle():
    context = MagicMock()
    mock_event = MagicMock()
    mock_process = MagicMock()
    mock_process.pid = 1234
    mock_process.is_alive.side_effect = [True, False]
    context.Event.return_value = mock_event
    context.Process.return_value = mock_process

    mock_event.wait.return_value = True

    indicator = ActivityIndicator(context)
    indicator.start()
    mock_process.start.assert_called_once()
    mock_event.wait.assert_called_once_with(8)

    indicator.request_stop()
    mock_event.set.assert_called()

    indicator.close()
    mock_process.join.assert_called()
