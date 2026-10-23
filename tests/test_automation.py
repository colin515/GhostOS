from pathlib import Path
from types import SimpleNamespace
import pytest
from automation.recipe_parser import load_recipe
from automation.scheduler import task_xml


def test_load_recipe_file_extension(tmp_path):
    txt_file = tmp_path / "recipe.txt"
    txt_file.write_text("name: test\nsteps:\n  - kind: wait\n    args: {seconds: 0.1}\n")
    with pytest.raises(ValueError, match="Recipe must be YAML"):
        load_recipe(txt_file)


def test_load_recipe_size_limit(tmp_path):
    yaml_file = tmp_path / "large_recipe.yaml"
    # Write slightly more than 256 KB
    content = "# " + "a" * (256 * 1024 + 10)
    yaml_file.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="Recipe exceeds 256 KB"):
        load_recipe(yaml_file)


def test_task_xml_parameter_validation(tmp_path):
    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text("name: test\nsteps:\n  - kind: wait\n    args: {seconds: 0.1}\n")

    with pytest.raises(ValueError, match="Time must be HH:MM"):
        task_xml(recipe_path, "11:60", 2)

    with pytest.raises(ValueError, match="Invalid permission tier"):
        task_xml(recipe_path, "11:30", 4)


def test_watcher_parameter_validation(tmp_path):
    pytest.importorskip("watchdog")
    from automation.watcher import watch

    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text("name: test\nsteps:\n  - kind: wait\n    args: {seconds: 0.1}\n")

    file_target = tmp_path / "not_a_dir.txt"
    file_target.write_text("hello")

    runtime = SimpleNamespace(settings=SimpleNamespace(data_dir=tmp_path / "data"))

    with pytest.raises(ValueError, match="Watch target must be a directory"):
        watch(file_target, recipe_path, runtime)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with pytest.raises(ValueError, match="Watch directory must not contain GhostOS application data/logs"):
        watch(data_dir, recipe_path, runtime)
