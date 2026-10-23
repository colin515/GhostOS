"""Declarative, finite YAML recipes; no eval, interpolation or embedded Python."""
from pathlib import Path
import yaml
from pydantic import BaseModel, ConfigDict, Field
from agent.models import Action

class Recipe(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=200)
    steps: list[Action] = Field(min_length=1)


def load_recipe(path: Path) -> Recipe:
    if path.suffix.lower() not in ('.yaml', '.yml'):
        raise ValueError('Recipe must be YAML')
    if path.stat().st_size > 256000:
        raise ValueError('Recipe exceeds 256 KB')
    return Recipe.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
