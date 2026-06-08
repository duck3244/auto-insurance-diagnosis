"""policy 단위 그룹 분할 (row 누수 방지) — M2 CV 전략."""
from __future__ import annotations

from sklearn.model_selection import GroupKFold, GroupShuffleSplit


def train_test_split_grouped(df, id_col="IDpol", test_size=0.2, seed=42):
    """동일 policy가 train/test에 섞이지 않도록 그룹 분할."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(df, groups=df[id_col]))
    return df.iloc[train_idx], df.iloc[test_idx]


def group_kfold(df, id_col="IDpol", n_folds=5):
    """policy 단위 GroupKFold 인덱스 제너레이터."""
    gkf = GroupKFold(n_splits=n_folds)
    return gkf.split(df, groups=df[id_col])
