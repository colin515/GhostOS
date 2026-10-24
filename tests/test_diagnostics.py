from agent.diagnostics import diagnostics


def test_diagnostics_structure():
    info = diagnostics()
    assert isinstance(info, dict)
    assert 'version' in info
    assert 'windows' in info
    assert 'dpi_scale' in info
    assert 'resources' in info
    assert 'modules' in info
    assert 'import_errors' in info
    assert isinstance(info['resources'], dict)
    assert isinstance(info['modules'], dict)
    assert isinstance(info['import_errors'], dict)
