from pathlib import Path
from unittest.mock import MagicMock
import pytest
from automation.watcher import watch

VALID_RECIPE = """
name: Open Notepad and write a greeting
steps:
  - kind: wait
    args: {seconds: 1.0}
"""


def test_watch_non_existent_directory(tmp_path):
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(VALID_RECIPE)
    non_existent = tmp_path / "does_not_exist"
    runtime = MagicMock()

    with pytest.raises(FileNotFoundError):
        watch(non_existent, recipe, runtime)


def test_watch_app_data_collision(tmp_path):
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(VALID_RECIPE)
    runtime = MagicMock()
    runtime.settings.data_dir = tmp_path

    with pytest.raises(ValueError, match="Watch directory must not contain GhostOS application data/logs"):
        watch(tmp_path, recipe, runtime)
