from pathlib import Path
import json
import os
import xml.etree.ElementTree as ET
import pytest
from PIL import Image
from config import Settings
from agent.vision import Frame, Vision
from agent.events import EventBus
from agent.brain import Brain, Context
from automation.recipe_parser import load_recipe
from automation.scheduler import task_xml


def test_dpi_transform_and_boundary():
    frame = Frame(Image.new('RGB', (1280, 720)), (2560, 1440))
    assert frame.physical(640, 360) == (1280, 720)
    with pytest.raises(ValueError):
        frame.physical(1280, 720)


def test_changed_ignores_identical_frames():
    a = Frame(Image.new('RGB', (100, 100), 'black'), (100, 100))
    b = Frame(Image.new('RGB', (100, 100), 'white'), (100, 100))
    assert not Vision.changed(a, a)
    assert Vision.changed(a, b)


def test_template_maps_to_model_pixels(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    template = Image.fromarray(noise)
    template.save(tmp_path / 'button.png')
    screen = Image.new('RGB', (300, 200), 'black')
    screen.paste(template, (100, 50))
    vision = Vision(templates=tmp_path)
    match = vision.match(Frame(screen, screen.size), 'button.png', 0.95)
    assert (match['x'], match['y']) == (112, 62)
    with pytest.raises(ValueError):
        vision.match(Frame(screen, screen.size), '../button.png')


def test_event_journal_does_not_accumulate_images():
    bus = EventBus(limit=3)
    for i in range(10):
        bus.publish('ACTION', step=i)
        bus.publish('FRAME', image='image' + str(i))
    assert len(bus.after()) == 3
    assert all(event['kind'] != 'FRAME' for event in bus.after())
    assert bus.latest_frame()['image'] == 'image9'


def test_context_is_bounded_text_without_images():
    context = Context()
    for i in range(100):
        context.add({'kind': 'hotkey', 'args': {'keys': ['ctrl', 'l']}}, 'result ' + str(i) * 100)
    assert len(context.recent) == 6
    assert len(context.text()) <= 6500
    assert 'hotkey' in context.summary
    assert 'images' not in context.text()


def test_explicit_fast_path_only():
    assert Brain.fast_command('please run a command') is None
    assert Brain.fast_command('/action {"kind":"hotkey","args":{"keys":["ctrl","l"]}}').kind == 'hotkey'


def test_settings_roundtrip_and_local_only(tmp_path):
    settings = Settings(data_dir=tmp_path, tier=1)
    settings.save()
    assert Settings.load(tmp_path).tier == 1
    with pytest.raises(ValueError):
        Settings(ollama_host='https://example.com')
    with pytest.raises(ValueError):
        Settings(cdp_url='http://192.168.1.2:9222')


def test_recipe_validation_and_scheduler_escaping(tmp_path):
    path = tmp_path / 'a & b.yaml'
    path.write_text('name: test\nsteps:\n  - kind: wait\n    args: {seconds: 0.1}\n')
    assert len(load_recipe(path).steps) == 1
    xml = task_xml(path, '11:30', 2)
    root = ET.fromstring(xml)
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    assert root.find('.//t:LogonType', ns).text == 'InteractiveToken'
    assert root.find('.//t:RunLevel', ns).text == 'LeastPrivilege'
    assert 'a &amp; b.yaml' in xml
    assert '11:30:00' in xml
    with pytest.raises(ValueError):
        task_xml(path, '25:00', 2)


def test_recipe_rejects_unknown_capabilities(tmp_path):
    path = tmp_path / 'bad.yaml'
    path.write_text('name: bad\nsteps:\n- kind: python\n  args: {code: whoami}\n')
    with pytest.raises(ValueError):
        load_recipe(path)


@pytest.mark.skipif(os.name != 'nt', reason='Win32 ABI only')
def test_sendinput_has_native_union_size():
    import ctypes
    from agent.gaming_engine import INPUT
    assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_cloud_alias_and_nonvision_models_are_refused():
    from agent.brain import ensure_local_vision
    with pytest.raises(ValueError, match='Cloud/remote'):
        ensure_local_vision({'remote_host': 'https://ollama.com', 'capabilities': ['vision']})
    with pytest.raises(ValueError, match='vision'):
        ensure_local_vision({'capabilities': ['completion']})
    with pytest.raises(ValueError, match='Cloud model'):
        Settings(model='custom:cloud')
    ensure_local_vision({'capabilities': ['completion', 'vision']})


def test_raw_model_metadata_keeps_remote_host(monkeypatch):
    import io
    import urllib.request
    from agent.brain import local_model_metadata, ensure_local_vision
    class FakeOpener:
        def open(self, request, timeout):
            assert request.full_url == 'http://127.0.0.1:11434/api/show'
            assert json.loads(request.data) == {'model': 'local-alias:latest'}
            return io.BytesIO(json.dumps({'remote_host':'https://ollama.com','capabilities':['vision']}).encode())
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *args: FakeOpener())
    metadata = local_model_metadata('http://127.0.0.1:11434', 'local-alias:latest')
    with pytest.raises(ValueError, match='Cloud/remote'):
        ensure_local_vision(metadata)
