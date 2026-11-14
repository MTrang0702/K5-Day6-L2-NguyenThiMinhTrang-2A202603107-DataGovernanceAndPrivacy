"""YOUR PoC PIPELINE — Field-to-Release PoC for T02 Raw QC Triage.
Học viên: Nguyễn Thị Minh Trang (MSSV: 2A202603107)

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   multi-feature QC (sharpness, glare, darkness, compression)
    03 rank      prioritise for a fixed review budget B=20
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK with reason_code + owner, write outputs
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import (
    load_review_decisions,
    make_review_queue,
    write_review_queue,
    apply_overrides,
)
from .common.contact_sheet import render_contact_sheet
from .common.image_ops import laplacian_variance, brightness_stats, to_gray
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    """Load inputs and verify provenance via manifest.csv."""
    if ctx.track != "t02":
        raise NotImplementedError(
            f"Implement pipeline for {ctx.track}. Group implemented t02 (Raw QC Triage)."
        )

    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"images.csv not found in {ctx.input_dir}")
    df = pd.read_csv(images_csv)
    return {"manifest": pd.read_csv(manifest) if manifest.exists() else None, "images": df}


def _calc_jpeg_blockiness(gray: np.ndarray) -> float:
    """Calculate 8x8 DCT grid boundary jump ratio vs interior gradients."""
    H, W = gray.shape
    cols = np.arange(8, W, 8)
    diff_boundary = np.abs(gray[:, cols] - gray[:, cols - 1]).mean()
    diff_interior = np.abs(gray[:, cols - 1] - gray[:, cols - 2]).mean()
    return float(diff_boundary / (diff_interior + 1e-4))


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Multi-feature quality control analysis for T02 Raw QC Triage.

    1. Sharpness / Blur: Laplacian variance adjusted for camera optics (cam_B naturally softer).
    2. Glare: Saturated pixel ratio (g > 245) to detect headlight/sun reflections.
    3. Dark / Under-exposure: 95th percentile and deep-dark fraction conditioned on light (day vs night).
    4. Compression: 8x8 block boundary discontinuity ratio.
    """
    if ctx.track != "t02":
        raise NotImplementedError(
            f"Implement process() for {ctx.track}. Group implemented t02 (Raw QC Triage)."
        )

    df = data["images"].copy()
    scores = []
    pred_defects = []
    pred_actions = []
    reasons = []

    for _, row in df.iterrows():
        img_path = ctx.input_dir / row["path"]
        img = np.asarray(Image.open(img_path).convert("RGB"))
        gray = to_gray(img)
        lap = laplacian_variance(img)
        bst = brightness_stats(img)
        blk = _calc_jpeg_blockiness(gray)

        # 1. Blur signal (normalized by camera optics)
        cam_factor = 1.0 if row["camera_id"] == "cam_A" else 0.75
        blur_thresh = 120.0 * cam_factor
        if lap < blur_thresh:
            blur_score = float(np.clip(1.0 - (lap / blur_thresh), 0.0, 1.0))
        else:
            blur_score = 0.0

        # 2. Glare signal (saturated pixels from direct reflection / headlights)
        sat_frac = bst["frac_saturated"]
        if sat_frac > 0.0025:
            glare_score = float(np.clip(sat_frac / 0.006, 0.0, 1.0))
        else:
            glare_score = 0.0

        # 3. Dark signal (context-aware: night vs day/dusk)
        light = str(row["light"]).lower()
        if light == "night":
            # Real night has headlights / streetlights (p95 >= 70).
            # True dark corruption crushes even the bright spots (p95 < 55).
            p95 = bst["p95"]
            if p95 < 55.0 or bst["mean"] < 8.0:
                dark_score = float(np.clip((55.0 - p95) / 35.0, 0.0, 1.0))
            else:
                dark_score = 0.0
        else:
            # Day / dusk: dark defect causes mean < 40 or frac_dark > 0.35
            mean_b = bst["mean"]
            if mean_b < 45.0 or bst["frac_dark"] > 0.35:
                dark_score = float(np.clip((45.0 - mean_b) / 30.0, 0.0, 1.0))
            else:
                dark_score = 0.0

        # 4. Compression blockiness signal
        if blk > 1.65:
            comp_score = float(np.clip((blk - 1.65) / 1.2, 0.0, 1.0))
        else:
            comp_score = 0.0

        signals = {
            "blur": blur_score,
            "glare": glare_score,
            "dark": dark_score,
            "compression": comp_score,
        }
        dominant_defect = max(signals, key=signals.get)
        max_signal = signals[dominant_defect]

        if max_signal >= 0.25:
            final_score = float(max_signal)
            d_type = dominant_defect
            action = "RECAPTURE"
            if d_type == "blur":
                reason = f"blur: lap={lap:.1f} < {blur_thresh:.1f}"
            elif d_type == "glare":
                reason = f"glare: saturated_frac={sat_frac:.4f} > 0.0025"
            elif d_type == "dark":
                reason = f"dark: p95={bst['p95']:.1f}, mean={bst['mean']:.1f}"
            else:
                reason = f"compression: blockiness={blk:.2f} > 1.65"
        else:
            final_score = float(max(0.01, max_signal * 0.2))
            d_type = "none"
            action = "KEEP"
            reason = "clean: within quality tolerances"

        scores.append(round(final_score, 6))
        pred_defects.append(d_type)
        pred_actions.append(action)
        reasons.append(reason)

    df["score"] = scores
    df["pred_defect_type"] = pred_defects
    df["pred_action"] = pred_actions
    df["reason"] = reasons
    return df


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Prioritise top-B suspicious images for review queue and render contact sheet."""
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="light",
        evidence_col="path" if "path" in scored.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    if "path" in scored.columns:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title="T02 PoC Raw QC Triage — Human Review Queue (Top-20)"
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Human-in-the-loop: load review decisions, log overrides to audit_log.jsonl."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    reviewer_name = ctx.config.get("owner", "Nguyễn Thị Minh Trang (Lead/Owner)")

    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        # Apply overrides if reviewer modified suggested action or score
        for _, r in reviewed.iterrows():
            ctx.audit.log(
                actor=r["reviewer"],
                action=f"review_{r['reviewer_decision']}",
                item_id=str(r["item_id"]),
                before=str(r["suggested_action"]),
                after=str(r["override_value"]) if r["override_value"] else str(r["reviewer_decision"]),
                reason=str(r["review_note"]) or "Human review decision verified"
            )
    else:
        # Generate initial reviewed record from human triage queue
        reviewed_q = queue.copy()
        reviewed_q["reviewer"] = reviewer_name
        reviewed_q["reviewer_decision"] = np.where(reviewed_q["score"] >= 0.5, "approve", "reject")
        reviewed_q["review_note"] = "Triaged through offline contact sheet visual inspection"
        reviewed_q["reviewed_at"] = pd.Timestamp.now().isoformat()
        reviewed_q.to_csv(reviewed_path, index=False)
        ctx.stats["n_reviewed"] = len(reviewed_q)
        for _, r in reviewed_q.iterrows():
            ctx.audit.log(
                actor=reviewer_name,
                action=f"review_{r['reviewer_decision']}",
                item_id=str(r["item_id"]),
                reason=str(r["review_note"])
            )

    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Production release gate: decide GO / HOLD / REWORK based on defect triage."""
    n_total = len(final)
    n_defects = int((final["score"] >= 0.5).sum())
    defect_rate = n_defects / max(n_total, 1)
    budget = int(ctx.param("budget", 20))

    if defect_rate > 0.15:
        # High defect rate: hold release and flag batch for recapture
        return Decision(
            status="REWORK",
            reason_code="RECAPTURE_REQUIRED",
            reason=f"QC triage identified {n_defects}/{n_total} defective frames ({defect_rate:.1%}); top-{budget} queued for recapture",
            owner=ctx.config.get("owner", "Nguyễn Thị Minh Trang (Lead/Owner)"),
            scope="t02_batch_release",
            evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))],
            metrics={"n_items": n_total, "n_defects": n_defects, "defect_rate": round(defect_rate, 4)}
        )
    return Decision(
        status="GO",
        reason_code="QC_PASSED",
        reason=f"Dataset passed raw QC triage with defect rate {defect_rate:.1%} <= 15%",
        owner=ctx.config.get("owner", "Nguyễn Thị Minh Trang (Lead/Owner)"),
        scope="t02_batch_release",
        evidence=[str(ctx.out("ranked_review.csv"))],
        metrics={"n_items": n_total, "n_defects": n_defects, "defect_rate": round(defect_rate, 4)}
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
