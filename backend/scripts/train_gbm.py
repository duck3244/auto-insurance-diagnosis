#!/usr/bin/env python
"""M2 — LightGBM GBM(빈도 Poisson · 순보험료 Tweedie), GLM 대비 lift 비교.

파이프라인:
  로드 → 정합성·capping·고아claim → policy 단위 split → raking(KOSIS 2024)
  → [GLM 빈도 baseline]  vs  [LightGBM Poisson 빈도]
  → LightGBM Tweedie 순보험료: policy 단위 CV 로 power 탐색 → test 평가
  → Gini/Deviance 비교표

사용:
  python scripts/train_gbm.py                 # openml, 10만 표본
  python scripts/train_gbm.py --sample 0      # 전체
  python scripts/train_gbm.py --no-raking
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
from auto_insurance.data.split import group_kfold, train_test_split_grouped  # noqa: E402
from auto_insurance.evaluation.metrics import (  # noqa: E402
    normalized_gini,
    poisson_deviance,
    tweedie_deviance,
)
from auto_insurance.features.encode import CATEGORICAL, NUMERIC  # noqa: E402
from auto_insurance.models.gbm import fit_tweedie_pure_premium  # noqa: E402
from auto_insurance.models.glm import fit_poisson_frequency  # noqa: E402
from auto_insurance.models.weights import combine_weights, training_weight  # noqa: E402
from auto_insurance.pipeline import (  # noqa: E402
    build_design,
    coerce_numeric,
    load_raw,
    predict_glm,
    to_lgb_frame,
)

LGB_PARAMS = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 100,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
              "num_boost_round": 300, "seed": 42, "verbose": -1, "num_threads": 4}


def lgb_poisson_es(Xtr, ytr, exp_tr, wtr, Xval, yval, exp_val, wval, cats):
    """Early-stopping LightGBM Poisson 빈도 (init_score=log exposure)."""
    base = {k: v for k, v in LGB_PARAMS.items() if k != "num_boost_round"}
    params = {"objective": "poisson", "metric": "poisson", **base}
    dtr = lgb.Dataset(Xtr, label=ytr, weight=wtr,
                      init_score=np.log(np.clip(exp_tr, 1e-6, None)),
                      categorical_feature=cats)
    dval = lgb.Dataset(Xval, label=yval, weight=wval,
                       init_score=np.log(np.clip(exp_val, 1e-6, None)),
                       reference=dtr)
    model = lgb.train(params, dtr, num_boost_round=2000, valid_sets=[dval],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
    return model


def search_tweedie_power(Xlgb, df, idx, cats, grid, w_rake, n_folds=3):
    """policy 단위 CV로 Tweedie power 선택.

    선택 기준 = 검증 **정규화 Gini(최대화)**. (mean_tweedie_deviance는 power별
    정규화상수를 생략해 power 간 스케일이 달라 비교 불가 → Gini 같은 순위지표 사용.)
    """
    sub = df.loc[idx]
    scores = {}
    for power in grid:
        ginis = []
        for tr_i, va_i in group_kfold(sub, id_col="IDpol", n_folds=n_folds):
            ti, vi = sub.index[tr_i], sub.index[va_i]
            wk = combine_weights(df.loc[ti, "Exposure"].to_numpy(),
                                 w_rake[sub.index.get_indexer(ti)])
            dtr = lgb.Dataset(Xlgb.loc[ti], label=df.loc[ti, "pure_premium"],
                              weight=wk, categorical_feature=cats)
            params = {"objective": "tweedie", "tweedie_variance_power": power,
                      **{k: v for k, v in LGB_PARAMS.items() if k != "num_boost_round"}}
            m = lgb.train(params, dtr, num_boost_round=150)
            pred = np.clip(m.predict(Xlgb.loc[vi]), 1e-6, None)
            ginis.append(normalized_gini(df.loc[vi, "pure_premium"], pred,
                                         exposure=df.loc[vi, "Exposure"]))
        scores[power] = float(np.mean(ginis))
        print(f"    power={power}: CV Gini {scores[power]:.4f}")
    best = max(scores, key=scores.get)
    return best, scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100_000)
    ap.add_argument("--source", choices=["auto", "csv", "openml"], default="auto")
    ap.add_argument("--no-raking", action="store_true")
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--folds", type=int, default=3)
    args = ap.parse_args()

    cfg = load_config()
    cfg["mitigation"]["raking"]["enabled"] = not args.no_raking
    grid = cfg["model"]["pure_premium"]["tweedie_power_grid"]

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
    print(f"[split] train {len(tr):,} / test {len(te):,} (policy 단위) · 표본 {len(df):,}")

    w = training_weight(cfg, tr, dataset="fremtpl2", base_weight=None)
    tag = "OFF" if args.no_raking else "ON"
    print(f"[raking] {tag}\n")

    # ---------------- 빈도: GLM vs GBM ----------------
    off_te = np.log(np.clip(te.Exposure, 1e-6, None))
    glm = fit_poisson_frequency(Xglm.loc[tr.index], tr.ClaimNb, tr.Exposure, sample_weight=w)
    glm_pred = np.clip(predict_glm(glm, Xglm.loc[te.index], offset=off_te), 1e-8, None)
    glm_dev = poisson_deviance(te.ClaimNb, glm_pred, sample_weight=te.Exposure)
    glm_gini = normalized_gini(te.ClaimNb, glm_pred, exposure=te.Exposure)

    # 빈도 GBM: train 에서 grouped 검증셋 분리 → early stopping
    tr2, val = train_test_split_grouped(tr, id_col="IDpol", test_size=0.15,
                                        seed=cfg["split"]["seed"])
    w2 = training_weight(cfg, tr2, dataset="fremtpl2", base_weight=None)
    wv = training_weight(cfg, val, dataset="fremtpl2", base_weight=None)
    gbm = lgb_poisson_es(Xlgb.loc[tr2.index], tr2.ClaimNb.to_numpy(), tr2.Exposure.to_numpy(), w2,
                         Xlgb.loc[val.index], val.ClaimNb.to_numpy(), val.Exposure.to_numpy(), wv,
                         cats)
    print(f"  (GBM best_iteration={gbm.best_iteration})")
    gbm_rate = gbm.predict(Xlgb.loc[te.index])
    gbm_cnt = np.clip(te.Exposure.to_numpy() * gbm_rate, 1e-8, None)
    gbm_dev = poisson_deviance(te.ClaimNb, gbm_cnt, sample_weight=te.Exposure)
    gbm_gini = normalized_gini(te.ClaimNb, gbm_cnt, exposure=te.Exposure)
    print("=== 빈도 비교 (test) ===")
    print(f"  GLM  : Poisson dev {glm_dev:.4f} · Gini {glm_gini:.4f}")
    print(f"  GBM  : Poisson dev {gbm_dev:.4f} · Gini {gbm_gini:.4f}")
    print(f"  → Gini lift {gbm_gini - glm_gini:+.4f}\n")

    # ---------------- 순보험료: Tweedie GBM + power 탐색 ----------------
    print(f"=== 순보험료 Tweedie GBM · policy CV power 탐색 {grid} ===")
    best_p, _ = search_tweedie_power(Xlgb, df, tr.index, cats, grid, w, n_folds=args.folds)
    print(f"  → 선택 power = {best_p}")
    tw = fit_tweedie_pure_premium(
        Xlgb.loc[tr.index], tr.pure_premium.to_numpy(), tr.Exposure.to_numpy(),
        power=best_p,
        params={k: v for k, v in LGB_PARAMS.items() if k != "num_boost_round"},
        sample_weight=w)
    pp_pred = np.clip(tw.predict(Xlgb.loc[te.index]), 1e-6, None)
    pp_dev = tweedie_deviance(te.pure_premium, pp_pred, power=best_p, sample_weight=te.Exposure)
    pp_gini = normalized_gini(te.pure_premium, pp_pred, exposure=te.Exposure)
    print(f"  test Tweedie(p={best_p}) dev {pp_dev:.2f} · 순보험료 Gini {pp_gini:.4f}\n")

    print("[요약]")
    print(f"  raking={tag}  freq: GLM {glm_gini:.4f} → GBM {gbm_gini:.4f} "
          f"({gbm_gini-glm_gini:+.4f})  |  pure_premium Tweedie(p={best_p}) Gini {pp_gini:.4f}")
    if gbm_gini <= glm_gini and args.sample and args.sample < 200_000:
        print("  ⓘ 소표본에선 GLM이 경쟁적(기획안 기대: ML lift는 modest). "
              "전체 데이터는 --sample 0 로 재현 권장.")


if __name__ == "__main__":
    main()
