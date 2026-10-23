"""Benchmark reports measured local inference/offload without capturing private screens."""
from types import SimpleNamespace
import sys
import pytest
from config import Settings
from agent.hardware import benchmark_model


def fake_client(monkeypatch, models, duration=2_000_000_000):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
        def generate(self, **kwargs):
            calls.append(kwargs)
            assert kwargs['images'][0].startswith(b'\x89PNG')
            assert kwargs['options']['num_predict'] == 24
            return SimpleNamespace(eval_count=20, eval_duration=duration, load_duration=1_000_000_000)
        def ps(self):
            return SimpleNamespace(models=models)
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=Client))
    monkeypatch.setattr('agent.brain.local_model_metadata', lambda *args: {'capabilities': ['vision']})
    return calls


@pytest.mark.parametrize('vram,expected', [(2 * 1024**3, 'GPU offload observed'), (0, 'CPU only observed')])
def test_benchmark_measures_rate_and_offload(monkeypatch, vram, expected):
    calls = fake_client(monkeypatch, [SimpleNamespace(model='llava:latest', size_vram=vram)])
    report = benchmark_model(Settings(), 'llava', lambda message: None)
    assert report['tokens_per_second'] == 10
    assert report['load_seconds'] == 1
    assert report['gpu_acceleration'] == expected
    assert report['model_vram_gb'] == vram / 1024**3
    assert len(calls) == 1


def test_benchmark_does_not_claim_acceleration_without_matching_model(monkeypatch):
    fake_client(monkeypatch, [SimpleNamespace(model='other:latest', size_vram=123)], duration=0)
    report = benchmark_model(Settings(), 'llava', lambda message: None)
    assert report['gpu_acceleration'] == 'not verified'
    assert report['tokens_per_second'] is None


def test_benchmark_refuses_remote_alias_before_inference(monkeypatch):
    calls = fake_client(monkeypatch, [])
    monkeypatch.setattr('agent.brain.local_model_metadata', lambda *args: {'remote_host': 'https://ollama.com', 'capabilities': ['vision']})
    with pytest.raises(ValueError, match='Cloud/remote'):
        benchmark_model(Settings(), 'llava', lambda message: None)
    assert not calls


@pytest.mark.parametrize('vram,model', [(8,'qwen3.5:4b'), (12,'qwen3-vl:8b'), (4,'qwen3.5:2b')])
def test_model_recommendation_leaves_headroom_for_8gb_gpus(monkeypatch, vram, model):
    from agent.hardware import hardware_report
    monkeypatch.setattr('agent.hardware.subprocess.check_output',lambda *a,**kw:f'Local GPU, {vram * 1024}\n')
    report = hardware_report()
    assert report['recommended_model'] == model
