

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
