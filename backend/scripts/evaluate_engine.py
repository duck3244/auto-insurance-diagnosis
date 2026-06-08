#!/usr/bin/env python
"""M3 — 통합 리스크 엔진: 순보험료(빈도×심도) + auto-calibration 검증/재보정 + SHAP.

파이프라인:
  로드 → 전처리 → policy split → raking
  → 빈도 GBM(Poisson, ES) · 심도 GLM(Gamma) → 순보험료 = rate × severity
  → auto-calibration 검증(balance, cohort 오차) → isotonic 재보정 → 개선 확인
  → SHAP 리스크 요인(빈도 모델)

사용:
  python scripts/evaluate_engine.py                # openml, 10만 표본
  python scripts/evaluate_engine.py --sample 0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_insurance.config import load_config  # noqa: E402
from auto_insurance.data.load import check_consistency, preprocess  # noqa: E402
from auto_insurance.data.split import train_test_split_grouped  # noqa: E402
from auto_insurance.evaluation.calibration import (  # noqa: E402
    apply_isotonic,
    calibration_report,
    fit_isotonic,
)
from auto_insurance.evaluation.metrics import normalized_gini  # noqa: E402
from auto_insurance.features.encode import CATEGORICAL, NUMERIC  # noqa: E402
from auto_insurance.models.glm import fit_gamma_severity  # noqa: E402
from auto_insurance.models.weights import training_weight  # noqa: E402
from auto_insurance.pipeline import (  # noqa: E402
    build_design,
    coerce_numeric,
    load_raw,
    predict_glm,
    to_lgb_frame,
)

LGB = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 100,
       "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
       "objective": "poisson", "metric": "poisson", "seed": 42,
       "verbose": -1, "num_threads": 4}


def fit_freq_gbm(Xtr, ytr, exp_tr, wtr, Xval, yval, exp_val, wval, cats):
    dtr = lgb.Dataset(Xtr, label=ytr, weight=wtr,
                      init_score=np.log(np.clip(exp_tr, 1e-6, None)),
                      categorical_feature=cats)
    dval = lgb.Dataset(Xval, label=yval, weight=wval,
                       init_score=np.log(np.clip(exp_val, 1e-6, None)), reference=dtr)
    return lgb.train(LGB, dtr, num_boost_round=2000, valid_sets=[dval],
                     callbacks=[lgb.early_stopping(50, verbose=False)])


def shap_top_drivers(model, X, k=8, n=2000):
    """빈도 GBM SHAP 평균 절대값 상위 k 요인."""
    try:
        import shap
    except ImportError:
        return None
    Xs = X.sample(min(n, len(X)), random_state=0)
    sv = shap.TreeExplainer(model).shap_values(Xs)
    imp = np.abs(np.asarray(sv)).mean(axis=0)
    order = np.argsort(imp)[::-1][:k]
    return [(X.columns[i], float(imp[i])) for i in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100_000)
    ap.add_argument("--source", choices=["auto", "csv", "openml"], default="auto")
    ap.add_argument("--no-raking", action="store_true")
    ap.add_argument("--test-size", type=float, default=0.2)
    args = ap.parse_args()

    cfg = load_config()
    cfg["mitigation"]["raking"]["enabled"] = not args.no_raking

    freq, sev = coerce_numeric(*load_raw(cfg, args.source), cfg)
    rep = check_consistency(freq, sev)
    print(f"[consistency] 정책 {rep['n_policies']:,} · 불일치 {rep['n_mismatched_policies']:,} "
          f"· 고아 {rep['n_orphan_claims']:,}")
    df = preprocess(freq, sev, cfg)
    if args.sample and args.sample < len(df):
        df = df.sample(args.sample, random_state=cfg["split"]["seed"]).reset_index(drop=True)

    Xglm = build_design(df, CATEGORICAL, NUMERIC)
    Xlgb, cats = to_lgb_frame(df, CATEGORICAL, NUMERIC)
    tr, te = train_test_split_grouped(df, id_col="IDpol",
                                      test_size=args.test_size, seed=cfg["split"]["seed"])
    print(f"[split] train {len(tr):,} / test {len(te):,} · 표본 {len(df):,}")

    # ---- 빈도 GBM (ES) ----
    tr2, val = train_test_split_grouped(tr, id_col="IDpol", test_size=0.15,
                                        seed=cfg["split"]["seed"])
    w2 = training_weight(cfg, tr2, dataset="fremtpl2", base_weight=None)
    wv = training_weight(cfg, val, dataset="fremtpl2", base_weight=None)
    fm = fit_freq_gbm(Xlgb.loc[tr2.index], tr2.ClaimNb.to_numpy(), tr2.Exposure.to_numpy(), w2,
                      Xlgb.loc[val.index], val.ClaimNb.to_numpy(), val.Exposure.to_numpy(), wv,
                      cats)

    # ---- 심도 GLM Gamma (청구건) ----
    claim_tr = tr[tr.sev_count > 0]
    ytr = claim_tr.sev_total / claim_tr.sev_count
    wsev = training_weight(cfg, claim_tr, dataset="fremtpl2", base_weight=None)
    sm_res = fit_gamma_severity(Xglm.loc[claim_tr.index], ytr, claim_tr.sev_count,
                                sample_weight=wsev)

    # ---- 순보험료 통합 = 빈도율 × 심도 ----
    def pure_premium(idx):
        rate = fm.predict(Xlgb.loc[idx])                 # 기대 빈도율
        sev_pred = np.clip(predict_glm(sm_res, Xglm.loc[idx]), 1e-3, None)
        return np.clip(rate * sev_pred, 1e-8, None)

    pp_tr = pure_premium(tr.index)
    pp_te = pure_premium(te.index)
    # 평가 가중치: raked 모델은 한국 재가중 분포를 타깃 → exposure×raking 으로 평가해야
    # self-consistent (raking OFF 시 raking_w=1 → 표준 exposure 가중).
    cal_w_tr = tr.Exposure.to_numpy() * training_weight(cfg, tr, "fremtpl2")
    cal_w_te = te.Exposure.to_numpy() * training_weight(cfg, te, "fremtpl2")

    print("\n=== 순보험료(빈도×심도) ===")
    gini = normalized_gini(te.pure_premium, pp_te, exposure=cal_w_te)
    print(f"  test Gini {gini:.4f}")

    # ---- auto-calibration 검증 → isotonic 재보정 ----
    print("\n=== Auto-calibration 검증/재보정 ===")
    before = calibration_report(te.pure_premium, pp_te, weight=cal_w_te)
    iso = fit_isotonic(pp_tr, tr.pure_premium, weight=cal_w_tr)
    pp_te_cal = apply_isotonic(iso, pp_te)
    after = calibration_report(te.pure_premium, pp_te_cal, weight=cal_w_te)
    gini_cal = normalized_gini(te.pure_premium, pp_te_cal, exposure=cal_w_te)
    print(f"  {'':9} {'balance':>9} {'autoCalErr':>11} {'Gini':>8}")
    print(f"  {'raw':9} {before['balance']:9.4f} {before['auto_cal_error']:11.4f} {gini:8.4f}")
    print(f"  {'isotonic':9} {after['balance']:9.4f} {after['auto_cal_error']:11.4f} {gini_cal:8.4f}")
    print("  → isotonic 재보정: balance≈1·cohort오차↓ (단조보정→순위 대체로 보존, Gini 거의 불변)")

    # ---- SHAP 리스크 요인 ----
    print("\n=== SHAP 리스크 요인(빈도 모델) ===")
    drivers = shap_top_drivers(fm, Xlgb.loc[te.index])
    if drivers is None:
        print("  (shap 미설치 — pip install shap)")
    else:
        for name, imp in drivers:
            print(f"  {name:12s} {imp:.4f}")

    print("\n[요약]")
    print(f"  raking={'OFF' if args.no_raking else 'ON'}  pp_Gini {gini:.4f}  "
          f"balance {before['balance']:.3f}→{after['balance']:.3f}  "
          f"autoCalErr {before['auto_cal_error']:.3f}→{after['auto_cal_error']:.3f}")


if __name__ == "__main__":
    main()
