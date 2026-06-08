#!/usr/bin/env python
"""M4 — 진단/추천 레이어: 통합 엔진 → 맞춤 진단 리포트.

파이프라인:
  로드 → 전처리 → policy split → fit_engine(빈도GBM×심도GLM+isotonic, market 분포)
  → 테스트 정책 표본을 진단(백분위·보장권장·grossing-up) → 리포트 출력
  → 엔진 저장(models/diagnosis_engine.joblib)

사용:
  python scripts/train_diagnosis.py                # openml, 10만 표본
  python scripts/train_diagnosis.py --n-examples 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_insurance.config import load_config  # noqa: E402
from auto_insurance.data.load import check_consistency, preprocess  # noqa: E402
from auto_insurance.data.split import train_test_split_grouped  # noqa: E402
from auto_insurance.diagnosis.engine import fit_engine  # noqa: E402
from auto_insurance.pipeline import coerce_numeric, load_raw  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100_000)
    ap.add_argument("--source", choices=["auto", "csv", "openml"], default="auto")
    ap.add_argument("--no-raking", action="store_true")
    ap.add_argument("--n-examples", type=int, default=4)
    ap.add_argument("--save", default="models/diagnosis_engine.joblib")
    args = ap.parse_args()

    cfg = load_config()
    cfg["mitigation"]["raking"]["enabled"] = not args.no_raking

    freq, sev = coerce_numeric(*load_raw(cfg, args.source), cfg)
    rep = check_consistency(freq, sev)
    print(f"[consistency] 정책 {rep['n_policies']:,} · 고아 {rep['n_orphan_claims']:,}")
    df = preprocess(freq, sev, cfg)
    if args.sample and args.sample < len(df):
        df = df.sample(args.sample, random_state=cfg["split"]["seed"]).reset_index(drop=True)

    tr, te = train_test_split_grouped(df, id_col="IDpol", test_size=0.2,
                                      seed=cfg["split"]["seed"])
    print(f"[split] train {len(tr):,} / test {len(te):,}")

    print("[engine] 학습 중(빈도GBM×심도GLM+isotonic) ...")
    eng = fit_engine(cfg, tr, seed=cfg["split"]["seed"])
    print(f"[engine] market 분포 n={len(eng.market):,} · "
          f"중앙값 순보험료 €{float(__import__('numpy').median(eng.market)):.1f}")

    # ---- 테스트 정책 진단 예시 ----
    print(f"\n=== 진단 리포트 예시 ({args.n_examples}건) ===")
    examples = te.sample(args.n_examples, random_state=1)
    for idx in examples.index:
        row = te.loc[[idx]]                  # 1행 DataFrame(dtype 보존)
        report = eng.diagnose(row)
        info = (f"DrivAge={int(row.DrivAge.iloc[0])} BonusMalus={int(row.BonusMalus.iloc[0])} "
                f"VehPower={int(row.VehPower.iloc[0])} VehAge={int(row.VehAge.iloc[0])}")
        print(f"\n[{info}]")
        print("  " + json.dumps(report, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    # ---- 저장 ----
    out = ROOT / args.save
    out.parent.mkdir(parents=True, exist_ok=True)
    eng.save(out)
    print(f"\n[save] {out}")


if __name__ == "__main__":
    main()
