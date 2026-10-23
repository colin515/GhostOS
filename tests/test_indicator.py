import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import multiprocessing as mp
import pytest
pytest.importorskip('PyQt6')


def test_indicator_process_lifecycle_has_no_automation_input():
    from ui.activity_border import ActivityIndicator
    indicator = ActivityIndicator(mp.get_context('spawn'))
    try:
        indicator.start()
        assert indicator.ready.is_set()
        assert indicator.process.is_alive()
        indicator.request_stop()
    finally:
        indicator.close()
    assert not indicator.process.is_alive()
    assert indicator.process.exitcode == 0
