#!/usr/bin/env python3
"""Create paper-ready descriptive figures from an analysis-ready trial CSV.

The script does not invent missing values. It creates only figures supported by
available columns and labels reference outcomes as comparison evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CONDITION_LABELS = {
    "baseline": "Signal only",
    "peakaboo": "Decomposed evidence",
    "peakaboo_recommendation": "Evidence + recommendation",
}


def save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def decision_figure(df: pd.DataFrame, output_dir: Path) -> None:
    completed = df.dropna(subset=["decision_code", "condition"]).copy()
    if completed.empty:
        return
    table = pd.crosstab(completed["condition"], completed["decision_code"], normalize="index")
    for code in [1, 2, 3]:
        if code not in table:
            table[code] = 0.0
    table = table[[1, 2, 3]]
    table.index = [CONDITION_LABELS.get(str(v), str(v)) for v in table.index]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    left = np.zeros(len(table))
    labels = ["Accept", "Reject", "Defer"]
    for code, label in zip([1, 2, 3], labels):
        values = table[code].to_numpy()
        ax.barh(table.index, values, left=left, label=label)
        left += values
    ax.set_xlabel("Proportion of decisions")
    ax.set_xlim(0, 1)
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.02))
    ax.set_title("Accept, reject, and defer decisions by condition")
    save(fig, output_dir, "figure_decisions_by_condition")


def outcome_figure(df: pd.DataFrame, output_dir: Path) -> None:
    completed = df.dropna(subset=["condition", "decision_code"]).copy()
    if completed.empty:
        return
    summary = completed.groupby("condition", as_index=False).agg(
        reference_alignment=("reference_alignment", "mean"),
        defer_rate=("decision_code", lambda x: (x == 3).mean()),
        calibration_error=("calibration_error", "mean"),
    )
    long = summary.melt(id_vars="condition", var_name="outcome", value_name="value")
    outcomes = ["reference_alignment", "defer_rate", "calibration_error"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5), sharey=False)
    for ax, outcome in zip(axes, outcomes):
        subset = long[long["outcome"] == outcome]
        labels = [CONDITION_LABELS.get(str(v), str(v)) for v in subset["condition"]]
        ax.bar(range(len(subset)), subset["value"])
        ax.set_xticks(range(len(subset)), labels, rotation=25, ha="right")
        ax.set_title(outcome.replace("_", " ").title())
        if outcome != "calibration_error":
            ax.set_ylim(0, 1)
    fig.suptitle("Decision quality, deferral, and confidence calibration")
    save(fig, output_dir, "figure_condition_outcomes")


def evidence_figure(df: pd.DataFrame, output_dir: Path) -> None:
    if "primary_evidence" not in df:
        return
    subset = df.dropna(subset=["primary_evidence"]).copy()
    if subset.empty:
        return
    counts = subset["primary_evidence"].value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(7.2, max(3.5, 0.38 * len(counts))))
    ax.barh(counts.index, counts.values)
    ax.set_xlabel("Number of decisions")
    ax.set_title("Information reported as most influential")
    save(fig, output_dir, "figure_evidence_usage")


def conflict_figure(df: pd.DataFrame, output_dir: Path) -> None:
    required = {"case_has_evidence_conflict", "condition", "decision_code", "reference_alignment", "response_time_seconds"}
    if not required.issubset(df.columns):
        return
    completed = df.dropna(subset=["decision_code"]).copy()
    summary = completed.groupby(["condition", "case_has_evidence_conflict"], as_index=False).agg(
        defer_rate=("decision_code", lambda x: (x == 3).mean()),
        reference_alignment=("reference_alignment", "mean"),
        response_time=("response_time_seconds", "mean"),
    )
    if summary.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5))
    for ax, metric in zip(axes, ["defer_rate", "reference_alignment", "response_time"]):
        pivot = summary.pivot(index="condition", columns="case_has_evidence_conflict", values=metric).fillna(0)
        x = np.arange(len(pivot))
        width = 0.36
        no_conflict = pivot.get(0, pd.Series(0, index=pivot.index)).to_numpy()
        conflict = pivot.get(1, pd.Series(0, index=pivot.index)).to_numpy()
        ax.bar(x - width / 2, no_conflict, width, label="Agreement")
        ax.bar(x + width / 2, conflict, width, label="Conflict")
        ax.set_xticks(x, [CONDITION_LABELS.get(str(v), str(v)) for v in pivot.index], rotation=25, ha="right")
        ax.set_title(metric.replace("_", " ").title())
    axes[0].legend(frameon=False)
    fig.suptitle("How evidence conflict changes review behavior")
    save(fig, output_dir, "figure_evidence_conflict")


def reliance_figure(df: pd.DataFrame, output_dir: Path) -> None:
    if "reliance_category" not in df:
        return
    subset = df.dropna(subset=["reliance_category"]).copy()
    if subset.empty:
        return
    order = ["appropriate_reliance", "over_reliance", "under_reliance", "appropriate_skepticism"]
    counts = subset["reliance_category"].value_counts().reindex(order, fill_value=0)
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    labels = [value.replace("_", " ").title() for value in counts.index]
    ax.bar(labels, counts.values)
    ax.set_ylabel("Number of decisions")
    ax.set_title("Reliance on algorithmic recommendations")
    ax.tick_params(axis="x", rotation=25)
    save(fig, output_dir, "figure_reliance_categories")


def calibration_figure(df: pd.DataFrame, output_dir: Path) -> None:
    completed = df.dropna(subset=["confidence", "reference_alignment", "condition"]).copy()
    if completed.empty:
        return
    completed["confidence_bin"] = pd.cut(completed["confidence"], bins=[0, 20, 40, 60, 80, 100], include_lowest=True)
    summary = completed.groupby(["condition", "confidence_bin"], observed=True, as_index=False).agg(
        mean_confidence=("confidence", "mean"),
        alignment=("reference_alignment", "mean"),
    )
    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1, label="Perfect calibration")
    for condition, group in summary.groupby("condition"):
        ax.plot(group["mean_confidence"] / 100.0, group["alignment"], marker="o", label=CONDITION_LABELS.get(condition, condition))
    ax.set_xlabel("Mean reported confidence")
    ax.set_ylabel("Reference-alignment rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.set_title("Confidence calibration")
    save(fig, output_dir, "figure_confidence_calibration")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="Analysis-ready trial CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/paper_figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.csv)
    decision_figure(df, args.output_dir)
    outcome_figure(df, args.output_dir)
    evidence_figure(df, args.output_dir)
    conflict_figure(df, args.output_dir)
    reliance_figure(df, args.output_dir)
    calibration_figure(df, args.output_dir)
    print(f"Figures written to {args.output_dir}")


if __name__ == "__main__":
    main()
