Baseline: `baseline` (git None, seed 42) · PoC: `poc` (git None, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (fraction) | all | 0.5185 | 0.7407 | 0.2222 | +42.9% | higher | 56 |
| Precision@B (fraction) | all | 0.7000 | 1.0000 | 0.3000 | +42.9% | higher | 56 |
| False alarm in top-B (fraction) | light=night | 0.2000 | 0.0000 | -0.2000 | -100.0% | lower | 20 |
| Runtime / 100 items (s) | all | 0.3457 | 0.4431 | | | lower | |
