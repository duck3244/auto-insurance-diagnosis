"""설정·비밀값 로더.

- config.yaml : 비밀이 아닌 설정(경로·파라미터·환경변수 '이름')
- .env        : 비밀값(API 키 등). git 제외. 코드/yaml 에 키를 직접 쓰지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()                      # 프로젝트 루트의 .env 자동 로드
except ImportError:                    # python-dotenv 미설치 시에도 OS 환경변수는 동작
    pass

_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path = "configs/config.yaml") -> dict:
    path = Path(path)
    if not path.is_absolute():
        path = _ROOT / path
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_secret(env_name: str, required: bool = True) -> str | None:
    """환경변수(.env 포함)에서 비밀값을 읽는다."""
    val = os.environ.get(env_name)
    if required and not val:
        raise RuntimeError(
            f"환경변수 {env_name} 가 없습니다. .env 에 {env_name}=... 를 설정하세요 "
            f"(.env.example 참고)."
        )
    return val


def kosis_api_key(cfg: dict | None = None) -> str:
    """config.apis.kosis.api_key_env 가 가리키는 환경변수에서 KOSIS 키를 읽는다."""
    cfg = cfg or load_config()
    env_name = cfg["apis"]["kosis"]["api_key_env"]
    return get_secret(env_name)
