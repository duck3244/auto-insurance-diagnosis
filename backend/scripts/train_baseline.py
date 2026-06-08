#!/usr/bin/env python
"""M1 베이스라인 학습 — freMTPL2 GLM(빈도·심도) end-to-end.

파이프라인:
  로드 → 정합성검증·capping·고아claim 처리 → 설계행렬 → policy 단위 split
  → raking 가중치(KOSIS 2024) → GLM Poisson 빈도 + Gamma 심도
  → 평가(Poisson/Gamma deviance, 정규화 Gini, 순보험료 Gini)

사용:
  python scripts/train_baseline.py                 # openml 로드, 10만 표본
  python scripts/train_baseline.py --sample 0      # 전체 데이터
  python scripts/train_baseline.py --no-raking     # raking 끄고 비교
  python scripts/train_baseline.py --source csv    # data/raw CSV 사용

데이터: data/raw 에 CSV 없으면 sklearn fetch_openml('freMTPL2freq'/'sev') 사용.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_insurance.config import load_config  # noqa: E402
from auto_insurance.data.load import check_consistency, preprocess  # noqa: E402
from auto_insurance.data.split import train_test_split_grouped  # noqa: E402
from auto_insurance.evaluation.metrics import (  # noqa: E402
    gamma_deviance,
    normalized_gini,
    poisson_deviance,
)
from auto_insurance.features.encode import CATEGORICAL, NUMERIC  # noqa: E402
from auto_insurance.models.glm import fit_gamma_severity, fit_poisson_frequency  # noqa: E402
from auto_insurance.models.weights import training_weight  # noqa: E402
from auto_insurance.pipeline import (  # noqa: E402
    build_design,
    coerce_numeric,
    load_raw,
    predict_glm,
)


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100_000,
                    help="행 수 제한(0=전체)")
    ap.add_argument("--source", choices=["auto", "csv", "openml"], default="auto")
    ap.add_argument("--no-raking", action="store_true")
    ap.add_argument("--test-size", type=float, default=0.2)
    args = ap.parse_args()

    cfg = load_config()
    cfg["mitigation"]["raking"]["enabled"] = not args.no_raking

    freq, sev = coerce_numeric(*load_raw(cfg, args.source), cfg)

    rep = check_consistency(freq, sev)
    print(f"[consistency] 정책 {rep['n_policies']:,} · claim {rep['n_claim_records']:,} "
          f"· 불일치 {rep['n_mismatched_policies']:,} · 고아 {rep['n_orphan_claims']:,}")

    df = preprocess(freq, sev, cfg)
    if args.sample and args.sample < len(df):
        df = df.sample(args.sample, random_state=cfg["split"]["seed"]).reset_index(drop=True)
    print(f"[preprocess] 학습 테이블 {df.shape} · 청구정책 {int((df.sev_count>0).sum()):,}")

    X = build_design(df, CATEGORICAL, NUMERIC)
    print(f"[design] 설계행렬 {X.shape} (수치 {len(NUMERIC)} + 더미)")

    tr, te = train_test_split_grouped(
        df, id_col=cfg["data"]["id_col"], test_size=args.test_size,
        seed=cfg["split"]["seed"])
    Xtr, Xte = X.loc[tr.index], X.loc[te.index]
    print(f"[split] train {len(tr):,} / test {len(te):,} (policy 단위)")

    # ---- raking 가중치 (빈도: base 없음) ----
    w = training_weight(cfg, tr, dataset="fremtpl2", base_weight=None)
    tag = "OFF" if args.no_raking else "ON"
    if w is not None:
        print(f"[raking] {tag} · weight mean {w.mean():.4f} min {w.min():.3f} max {w.max():.3f}")

    # ================= 빈도 (Poisson GLM) =================
    print("\n=== 빈도 Poisson GLM ===")
    fm = fit_poisson_frequency(Xtr, tr.ClaimNb, tr.Exposure, sample_weight=w)
    pred_te = predict_glm(fm, Xte, offset=np.log(np.clip(te.Exposure, 1e-6, None)))
    pred_te = np.clip(pred_te, 1e-8, None)
    pd_dev = poisson_deviance(te.ClaimNb, pred_te, sample_weight=te.Exposure)
    freq_gini = normalized_gini(te.ClaimNb, pred_te, exposure=te.Exposure)
    print(f"  test Poisson deviance {pd_dev:.4f} · 정규화 Gini {freq_gini:.4f}")

    # ================= 심도 (Gamma GLM, 청구건만) =================
    print("\n=== 심도 Gamma GLM ===")
    claim_tr = tr[tr.sev_count > 0]
    claim_te = te[te.sev_count > 0]
    ytr = claim_tr.sev_total / claim_tr.sev_count          # 평균 청구액
    yte = claim_te.sev_total / claim_te.sev_count
    # claim_count 는 freq_weights 로, raking 은 var_weights(sample_weight)로 분리 전달
    w_sev = training_weight(cfg, claim_tr, dataset="fremtpl2", base_weight=None)
    sm_res = fit_gamma_severity(X.loc[claim_tr.index], ytr, claim_tr.sev_count,
                                sample_weight=w_sev)
    pred_sev = predict_glm(sm_res, X.loc[claim_te.index])
    pred_sev = np.clip(pred_sev, 1e-3, None)
    gm_dev = gamma_deviance(yte, pred_sev, sample_weight=claim_te.sev_count)
    print(f"  청구 train {len(claim_tr):,} / test {len(claim_te):,}")
    print(f"  test Gamma deviance {gm_dev:.2f}")

    # ================= 순보험료 (빈도×심도) Gini =================
    print("\n=== 순보험료(빈도×심도) ===")
    rate_te = pred_te / np.clip(te.Exposure, 1e-6, None)    # 기대 빈도율
    sev_all = predict_glm(sm_res, Xte)                      # 전 정책 심도 예측
    pure_pred = rate_te * np.clip(sev_all, 1e-3, None)
    pp_gini = normalized_gini(te.pure_premium, pure_pred, exposure=te.Exposure)
    print(f"  순보험료 정규화 Gini {pp_gini:.4f}")

    print("\n[요약]")
    print(f"  raking={tag}  freq_dev={pd_dev:.4f}  freq_gini={freq_gini:.4f}  "
          f"sev_dev={gm_dev:.1f}  pp_gini={pp_gini:.4f}")


if __name__ == "__main__":
    main()
