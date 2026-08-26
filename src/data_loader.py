from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .models import SignalBundle


@lru_cache(maxsize=8)
def load_case_bank(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Case bank not found: {path}")
    frame = pd.read_csv(path)
    required = {
        "case_id",
        "pair_id",
        "source_type",
        "condition_eligible",
        "candidate_time",
        "signal_key",
        "pilot_ready",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Case bank is missing required columns: {missing}")
    frame["case_id"] = frame["case_id"].astype(str)
    frame["pair_id"] = frame["pair_id"].astype(str)
    return frame


@lru_cache(maxsize=4)
def _load_npz(path: str | Path) -> dict[str, np.ndarray]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Signal archive not found: {path}")
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def load_signal_bundle(path: str | Path, signal_key: str) -> SignalBundle:
    arrays = _load_npz(path)

    def get(name: str, default: np.ndarray | None = None) -> np.ndarray:
        key = f"{signal_key}__{name}"
        if key in arrays:
            return arrays[key]
        if default is None:
            raise KeyError(f"Missing signal array: {key}")
        return default

    time = get("time")
    raw = get("raw")
    return SignalBundle(
        time=time,
        raw=raw,
        smooth=get("smooth"),
        sigma=get("sigma"),
        lower=get("lower"),
        upper=get("upper"),
        candidate_index=int(get("candidate_index")[0]),
        nearby_peak_indices=get("nearby_peak_indices", np.array([], dtype=int)).astype(int),
        stability_hits=get("stability_hits", np.array([], dtype=int)).astype(int),
        stability_offsets=get("stability_offsets", np.array([], dtype=float)).astype(float),
        parameter_matrix=get("parameter_matrix", np.zeros((1, 1), dtype=int)).astype(int),
        parameter_smoothing=get("parameter_smoothing", np.array([1], dtype=int)).astype(int),
        parameter_k=get("parameter_k", np.array([1.0], dtype=float)).astype(float),
    )


def parse_provenance(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {"raw": str(value)}


def case_record(frame: pd.DataFrame, case_id: str) -> dict[str, Any]:
    rows = frame.loc[frame["case_id"].astype(str) == str(case_id)]
    if rows.empty:
        raise KeyError(f"Unknown case_id: {case_id}")
    return rows.iloc[0].to_dict()
