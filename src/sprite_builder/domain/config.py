"""Configuration loading with optional PyYAML support."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sprite_builder.domain.errors import ConfigurationError
from sprite_builder.domain.models import JobSpec


def load_mapping(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ConfigurationError(
                "YAML support requires PyYAML; install the project or supply JSON"
            ) from exc
        value = yaml.safe_load(text)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{source} must contain a top-level object")
    return value


def load_job(path: str | Path) -> JobSpec:
    return JobSpec.from_dict(load_mapping(path))
