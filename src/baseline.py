"""Baseline implementation for T02: Single global Laplacian variance.

Per docs/tracks/T02.md:
"Baseline: Một ngưỡng Laplacian toàn ảnh duy nhất (src/common/image_ops.laplacian_variance),
cùng testset & budget."
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
from PIL import Image
import numpy as np

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .common.contact_sheet import render_contact_sheet
from .common.image_ops import laplacian_variance
from .metrics.tracks import get_track


def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    if manifest.exists():
        problems = verify_manifest(manifest)
        if problems and ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems)")
    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"images.csv not found in {ctx.input_dir}")
    return {"images": pd.read_csv(images_csv)}


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    df = data["images"].copy()
    scores = []
    reasons = []
    for _, row in df.iterrows():
        img_path = ctx.input_dir / row["path"]
        img = np.asarray(Image.open(img_path).convert("RGB"))
        lap = laplacian_variance(img)
        # Baseline heuristic: low laplacian = blur defect -> high score (more suspicious)
        # Scaled to [0, 1] range: 1000 / (1000 + lap)
        score = float(1000.0 / (1000.0 + max(lap, 0.0)))
        scores.append(score)
        reasons.append("laplacian_sharpness_proxy")

    df["score"] = scores
    df["reason"] = reasons
    return df


def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        evidence_col="path" if "path" in scored.columns else None
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    if "path" in scored.columns:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title="T02 Baseline (Laplacian Variance) Review Queue"
        )
    return q


def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    return scored


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    return Decision(
        status="HOLD",
        reason_code="BASELINE_ONLY",
        reason="Baseline run: Single global Laplacian variance. Never release directly.",
        owner=ctx.config.get("owner", "baseline"),
        scope="t02",
        evidence=[str(ctx.out("ranked_review.csv"))]
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    out_cols = [c for c in spec.pred_columns if c in final.columns]
    for c in final.columns:
        if c not in out_cols:
            out_cols.append(c)
    final[out_cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
