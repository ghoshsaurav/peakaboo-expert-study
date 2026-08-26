from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    case_bank: Path
    signals: Path
    database: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else project_root() / "config" / "study_config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Study configuration not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    config["_config_path"] = str(cfg_path)
    return config


def resolve_paths(config: dict[str, Any] | None = None) -> Paths:
    config = config or load_config()
    root = project_root()
    paths_cfg = config.get("paths", {})

    def resolve(value: str, fallback: str) -> Path:
        raw = Path(value or fallback)
        return raw if raw.is_absolute() else root / raw

    return Paths(
        root=root,
        config=Path(config["_config_path"]),
        case_bank=resolve(paths_cfg.get("case_bank", ""), "data/demo/case_bank.csv"),
        signals=resolve(paths_cfg.get("signals", ""), "data/demo/signals.npz"),
        database=resolve(paths_cfg.get("database", ""), "data/results/study.db"),
    )
