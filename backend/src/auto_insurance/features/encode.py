"""특징 컬럼 정의 (M1).

freMTPL2 변수: VehPower, VehAge, DrivAge, BonusMalus, VehBrand, VehGas, Area, Density, Region.
실제 인코딩(GLM 설계행렬·LightGBM 프레임)은 pipeline.build_design / to_lgb_frame 참조.
"""
from __future__ import annotations

CATEGORICAL = ["VehBrand", "VehGas", "Area", "Region"]
NUMERIC = ["VehPower", "VehAge", "DrivAge", "BonusMalus", "Density"]
