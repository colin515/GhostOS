

def test_old_default_limits_migrate_to_unlimited_but_custom_limits_remain(tmp_path):
    import json
    from config import Settings
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'max_steps':40, 'max_runtime':600}))
    migrated = Settings.load(tmp_path)
    assert migrated.max_steps == migrated.max_runtime == 0
    migrated.save()
    assert Settings.load(tmp_path).max_steps == 0
    path.write_text(json.dumps({'max_steps':777, 'max_runtime':555}))
    custom = Settings.load(tmp_path)
    assert custom.max_steps == 777 and custom.max_runtime == 555


def test_corrupt_settings_recover_strictly_and_preserve_original(tmp_path):
    from config import Settings
    path = tmp_path / 'settings.json'
    broken = '{not valid JSON'
    path.write_text(broken)
    settings = Settings.load(tmp_path)
    assert settings.tier == 1
    assert not settings.setup_complete
    assert 'Invalid saved settings' in settings.startup_notice
    backups = list(tmp_path.glob('settings.backup_*.json'))
    assert len(backups) == 1 and backups[0].read_text() == broken
    assert Settings.load(tmp_path).tier == 1


def test_unknown_legacy_fields_do_not_prevent_startup(tmp_path):
    import json
    from config import Settings
    (tmp_path / 'settings.json').write_text(json.dumps({'tier':1,'model':'llava:7b','obsolete_ui_field':True}))
    settings = Settings.load(tmp_path)
    assert settings.model == 'llava:7b' and settings.tier == 1
    assert 'obsolete_ui_field' not in json.loads((tmp_path / 'settings.json').read_text())
    assert list(tmp_path.glob('settings.backup_*.json'))


def test_invalid_setting_types_do_not_silently_enable_risk(tmp_path):
    import json
    from config import Settings
    (tmp_path / 'settings.json').write_text(json.dumps({'tier':'3', 'setup_complete':'true'}))
    settings = Settings.load(tmp_path)
    assert settings.tier == 1 and not settings.setup_complete


def test_explicit_repair_preserves_models_recipes_and_logs(tmp_path):
    from config import Settings
    Settings(data_dir=tmp_path,tier=3).save()
    for name in ('recipes','logs','voice-model'):
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'sentinel').write_text(name)
    repaired = Settings.repair(tmp_path)
    assert repaired.tier == 1 and not repaired.setup_complete
    for name in ('recipes','logs','voice-model'):
        assert (tmp_path / name / 'sentinel').read_text() == name
