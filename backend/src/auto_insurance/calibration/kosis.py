"""KOSIS OpenAPI 클라이언트 — 한국 집계통계 마진 수집(§8.1 raking 보완).

키는 .env(KOSIS_API_KEY)에서 로드(config.py). 코드/yaml 에 키 하드코딩 금지.

용례:
    from auto_insurance.calibration.kosis import fetch_all_korea_margins
    margins = fetch_all_korea_margins()   # Gender·DrivAge·차종·용도 비율 일괄
"""
from __future__ import annotations

import requests

from auto_insurance.config import kosis_api_key, load_config


def fetch_table(org_id: str, tbl_id: str, start: str | None = None,
                end: str | None = None, obj_levels: int = 2,
                prd_se: str = "Y") -> list[dict]:
    """KOSIS 통계자료(파라미터 방식) 조회. obj_levels 만큼 objL1..N=ALL 부여.

    start/end 미지정 시 newEstPrdCnt=1 로 최신연도만 조회.
    """
    cfg = load_config()
    base = cfg["apis"]["kosis"]["base_url"]
    params = {
        "method": "getList", "apiKey": kosis_api_key(cfg),
        "orgId": org_id, "tblId": tbl_id,
        "prdSe": prd_se, "itmId": "ALL", "format": "json", "jsonVD": "Y",
    }
    if start:
        params["startPrdDe"], params["endPrdDe"] = start, end or start
    else:
        params["newEstPrdCnt"] = "1"
    for i in range(1, obj_levels + 1):
        params[f"objL{i}"] = "ALL"
    r = requests.get(base, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):                       # {"err":..,"errMsg":..}
        raise RuntimeError(f"KOSIS error: {data.get('errMsg', data)}")
    return data


_AGE_ORDER = ["<20", "20s", "30s", "40s", "50s", "60s", "70+"]


def _age_bucket(name: str) -> str | None:
    import re
    m = re.search(r"\d+", name)
    if not m:
        return None
    lo = int(m.group())
    return ("<20" if lo < 20 else "20s" if lo < 30 else "30s" if lo < 40 else
            "40s" if lo < 50 else "50s" if lo < 60 else "60s" if lo < 70 else "70+")


def _tbl(cfg, name):
    return cfg["apis"]["kosis"]["tables"][name]


def fetch_license_gender(year: str | None = None) -> dict:
    """운전면허 소지자 성별 비율 (DT_13201_A004). C1=총계 행의 남자/여자."""
    cfg = load_config()
    t = _tbl(cfg, "license_gender")
    rows = fetch_table(t["orgId"], t["tblId"], year, year, obj_levels=2)
    g = {c2: next((int(r["DT"]) for r in rows
                   if r.get("C1_NM") == "총계" and r.get("C2_NM") == c2), None)
         for c2 in ("남자", "여자")}
    tot = g["남자"] + g["여자"]
    return {"Male": round(g["남자"] / tot, 3), "Female": round(g["여자"] / tot, 3)}


def fetch_license_age(year: str | None = None) -> dict:
    """운전면허 소지자 연령대 비율 (DT_13201_A002). C2=총계(전 면허종), C1=연령."""
    cfg = load_config()
    t = _tbl(cfg, "license_age")
    rows = fetch_table(t["orgId"], t["tblId"], year, year, obj_levels=2)
    agg: dict[str, int] = {}
    for r in rows:
        if r.get("C2_NM") == "총계" and r.get("C1_NM") != "총계":
            b = _age_bucket(r.get("C1_NM", ""))
            if b:
                agg[b] = agg.get(b, 0) + int(r["DT"])
    tot = sum(agg.values())
    prop = {b: round(agg.get(b, 0) / tot, 3) for b in _AGE_ORDER}
    residual = round(1 - sum(prop.values()), 3)        # 반올림 잔차
    if residual:                                       # 최대 버킷에 흡수(상대오차 최소)
        top = max(prop, key=prop.get)
        prop[top] = round(prop[top] + residual, 3)
    return prop


def fetch_vehicle_registration(year: str | None = None) -> dict:
    """자동차등록대수현황(DT_MLTM_1244, 국토부) → 차종·용도 비율.

    표 구조: ITM(계/관용/영업용/자가용) × C2(승용/승합/화물/특수/총계).
    KOSIS엔 규모별(경/소/중/대)이 없어 차종·용도로 대체.
    """
    cfg = load_config()
    t = _tbl(cfg, "vehicle_registration")
    rows = fetch_table(t["orgId"], t["tblId"], year, year, obj_levels=2)

    def dt(itm, c2):
        return next((int(r["DT"]) for r in rows
                     if r.get("ITM_NM") == itm and r.get("C2_NM") == c2), None)

    total = dt("계", "총계")
    vehicle_type = {c2: round(dt("계", c2) / total, 4)
                    for c2 in ("승용", "승합", "화물", "특수")}
    passenger_total = dt("계", "승용")
    passenger_use = {u: round(dt(u, "승용") / passenger_total, 4)
                     for u in ("자가용", "영업용", "관용")}
    return {"total": total, "vehicle_type": vehicle_type,
            "passenger_use": passenger_use}


def fetch_all_korea_margins(year: str | None = None) -> dict:
    """config.apis.kosis.reference_year(기본) 기준 한국 마진 일괄 수집."""
    cfg = load_config()
    year = year or cfg["apis"]["kosis"].get("reference_year")
    veh = fetch_vehicle_registration(year)
    return {
        "year": year,
        "Gender": fetch_license_gender(year),
        "DrivAge": fetch_license_age(year),
        "vehicle_type": veh["vehicle_type"],
        "passenger_use": veh["passenger_use"],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all_korea_margins(), ensure_ascii=False, indent=2))
