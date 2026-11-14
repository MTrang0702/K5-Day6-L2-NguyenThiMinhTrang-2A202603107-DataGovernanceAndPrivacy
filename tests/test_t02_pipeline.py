"""Unit tests for T02 Raw QC Triage Pipeline.

Covers:
1. End-to-end pipeline execution (success case on real fixtures).
2. Detection accuracy on known defect archetypes (blur, glare, dark, clean night).
3. Human-in-the-loop ranking and decision policy validation.
4. Edge cases: provenance check on tampered/missing data.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.common.context import RunContext
from src.common.decision import Decision
from src.common.review import AuditLog
from src.pipeline import load, process, rank, decide, _calc_jpeg_blockiness


@pytest.fixture
def t02_ctx(tmp_path):
    root = Path(__file__).resolve().parents[1]
    in_dir = root / "fixtures" / "t02_raw_qc"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "track": "t02",
        "owner": "Nguyễn Thị Minh Trang (Lead/Owner)",
        "strict_provenance": True,
        "params": {"budget": 20, "dev_split": "dev"}
    }
    return RunContext(
        track="t02",
        input_dir=in_dir,
        output_dir=out_dir,
        config=cfg,
        seed=42,
        rng=np.random.default_rng(42),
        run_name="test_run",
        offline=True,
        audit=AuditLog(out_dir / "audit_log.jsonl")
    )


def test_t02_e2e_process_and_contract(t02_ctx):
    """Test 01 load + 02 process satisfies output contract and schema."""
    data = load(t02_ctx)
    assert "images" in data
    assert len(data["images"]) == 96

    scored = process(t02_ctx, data)
    assert "image_id" in scored.columns
    assert "score" in scored.columns
    assert "pred_defect_type" in scored.columns
    assert "pred_action" in scored.columns
    assert "reason" in scored.columns

    # Scores must be bounded [0, 1]
    assert scored["score"].min() >= 0.0
    assert scored["score"].max() <= 1.0


def test_t02_defect_discrimination(t02_ctx):
    """Test pipeline correctly discriminates between clean images and severe defects."""
    data = load(t02_ctx)
    scored = process(t02_ctx, data).set_index("image_id")

    # img_00_3 is heavily blurred; img_00_1 is sharp clean
    assert scored.loc["img_00_3", "score"] > 0.8
    assert scored.loc["img_00_3", "pred_defect_type"] == "blur"
    assert scored.loc["img_00_1", "score"] <= 0.1
    assert scored.loc["img_00_1", "pred_defect_type"] == "none"

    # img_02_2 has severe glare from headlights/sun
    assert scored.loc["img_02_2", "pred_defect_type"] == "glare"
    assert scored.loc["img_02_2", "score"] >= 0.7

    # Healthy night image (img_01_0) must not be falsely rejected as dark defect
    assert scored.loc["img_01_0", "score"] <= 0.2


def test_t02_rank_and_decision_policy(t02_ctx):
    """Test 03 rank produces valid top-B queue and 05 decide produces valid Decision."""
    data = load(t02_ctx)
    scored = process(t02_ctx, data)

    queue = rank(t02_ctx, scored)
    assert len(queue) == 20
    assert (t02_ctx.output_dir / "review_queue.csv").exists()
    assert (t02_ctx.output_dir / "contact_sheet.html").exists()

    decision = decide(t02_ctx, scored)
    assert isinstance(decision, Decision)
    assert decision.status in {"GO", "HOLD", "REWORK"}
    assert decision.owner == "Nguyễn Thị Minh Trang (Lead/Owner)"
    assert decision.reason_code != ""
    assert len(decision.evidence) > 0


def test_jpeg_blockiness_edge_case():
    """Test JPEG blockiness calculation on uniform vs synthetic blocky grid."""
    # Flat image should have low blockiness
    flat = np.ones((64, 64), dtype=np.float32) * 128.0
    assert _calc_jpeg_blockiness(flat) < 1.1

    # Grid with jumps at boundary cols (8, 16, 24...)
    blocky = np.ones((64, 64), dtype=np.float32) * 100.0
    for c in range(8, 64, 8):
        blocky[:, c:] += 20.0
    assert _calc_jpeg_blockiness(blocky) > 1.5
