"""Plotly figures used in participant and researcher study views."""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go

from .models import SignalBundle


def chromatogram_figure(
    bundle: SignalBundle,
    show_variation_band: bool,
    title: str = "Candidate review",
    show_nearby_maxima: bool = True,
) -> go.Figure:
    """Plot one case signal, the marked candidate, and optional local evidence layers."""
    figure = go.Figure()
    if show_variation_band:
        figure.add_trace(
            go.Scatter(
                x=np.concatenate([bundle.time, bundle.time[::-1]]),
                y=np.concatenate([bundle.upper, bundle.lower[::-1]]),
                fill="toself",
                fillcolor="rgba(120,120,120,0.18)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip",
                name="Local variation band",
            )
        )
    figure.add_trace(
        go.Scatter(x=bundle.time, y=bundle.raw, mode="lines", name="Raw measured signal", line=dict(width=1))
    )
    figure.add_trace(
        go.Scatter(x=bundle.time, y=bundle.smooth, mode="lines", name="Smoothed signal", line=dict(width=2))
    )
    candidate_index = int(bundle.candidate_index)
    figure.add_trace(
        go.Scatter(
            x=[bundle.time[candidate_index]],
            y=[bundle.smooth[candidate_index]],
            mode="markers",
            marker=dict(size=13, symbol="diamond"),
            name="Marked candidate",
            hovertemplate="Candidate<br>Time: %{x:.4f}<br>Signal: %{y:.4g}<extra></extra>",
        )
    )
    nearby = bundle.nearby_peak_indices.astype(int)
    nearby = nearby[(nearby >= 0) & (nearby < len(bundle.time)) & (nearby != candidate_index)]
    if show_nearby_maxima and len(nearby):
        figure.add_trace(
            go.Scatter(
                x=bundle.time[nearby],
                y=bundle.smooth[nearby],
                mode="markers",
                marker=dict(size=6, symbol="circle-open"),
                name="Nearby maxima",
                hovertemplate="Nearby maximum<br>Time: %{x:.4f}<extra></extra>",
            )
        )
    figure.update_layout(
        title=title,
        xaxis_title="Time (retention time)",
        yaxis_title="Measured signal",
        height=430,
        margin=dict(l=40, r=20, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    return figure


def detectability_figure(score: float, boundary: float) -> go.Figure:
    """Show candidate detectability relative to the configured decision boundary."""
    maximum = max(boundary * 2.0, score * 1.25, 1.0)
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=[min(score, maximum)],
            y=["Stands out from noise"],
            orientation="h",
            name="Candidate value",
            hovertemplate="W = %{x:.2f}<extra></extra>",
        )
    )
    figure.add_vline(x=boundary, line_dash="dash", annotation_text=f"Detector cutoff {boundary:.2f}")
    figure.update_layout(
        height=150,
        margin=dict(l=15, r=15, t=25, b=20),
        xaxis=dict(range=[0, maximum], title="Rise above surroundings / nearby noise"),
        yaxis=dict(showticklabels=False),
        showlegend=False,
    )
    return figure


def stability_figure(hits: np.ndarray) -> go.Figure:
    """Show whether the candidate was recovered in each perturbation run."""
    hits = np.asarray(hits, dtype=int)
    if len(hits) == 0:
        hits = np.array([0])
    figure = go.Figure(
        data=go.Heatmap(
            z=[hits],
            x=list(range(1, len(hits) + 1)),
            y=["Found again"],
            zmin=0,
            zmax=1,
            showscale=False,
            hovertemplate="Run %{x}<br>Recovered: %{z}<extra></extra>",
        )
    )
    figure.update_layout(
        height=120,
        margin=dict(l=15, r=15, t=15, b=25),
        xaxis_title="Small signal-change test",
        yaxis=dict(showticklabels=False),
    )
    return figure


def parameter_robustness_figure(matrix: np.ndarray, smoothing: np.ndarray, k_values: np.ndarray) -> go.Figure:
    """Show candidate recovery across the smoothing-by-threshold parameter grid."""
    matrix = np.asarray(matrix, dtype=int)
    figure = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=[f"Peak-size setting {value:g}" for value in k_values],
            y=[f"Smoothing {value}" for value in smoothing],
            zmin=0,
            zmax=1,
            showscale=False,
            hovertemplate="%{y}<br>%{x}<br>Recovered: %{z}<extra></extra>",
        )
    )
    figure.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=15, b=35),
        xaxis_title="Peak-size setting",
        yaxis_title="Smoothing setting",
    )
    return figure


def evidence_summary_figure(case: dict[str, Any]) -> go.Figure:
    """Summarize four evidence dimensions on a common normalized display scale."""
    labels = ["Detectability", "Stability", "Parameter robustness", "Structural clarity"]
    boundary = float(case.get("weber_boundary", 15.96))
    score = float(case.get("detectability", 0.0))
    stability = float(case.get("stability", 0.0))
    robustness = float(case.get("parameter_robustness", 0.0))
    structural = 0.2 if bool(case.get("overlap_flag", False)) else 0.9
    values = [min(score / max(boundary, 1e-12), 1.5) / 1.5, stability, robustness, structural]
    figure = go.Figure(
        data=go.Bar(x=values, y=labels, orientation="h", text=[f"{v:.2f}" for v in values], textposition="auto")
    )
    figure.update_layout(
        height=230,
        margin=dict(l=20, r=20, t=20, b=30),
        xaxis=dict(range=[0, 1], title="Normalized evidence level"),
        showlegend=False,
    )
    return figure
