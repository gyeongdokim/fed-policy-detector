"""FRED에서 지표를 받아오는 파일.
- 한 번 받은 데이터는 data/ 폴더에 저장해두고 12시간 동안 재사용 (반복 실행 시 빠름)
- 지표 하나가 실패해도 전체가 멈추지 않고 경고만 출력"""
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

import config as C

URL = "https://api.stlouisfed.org/fred/series/observations"
CACHE = Path(__file__).parent / "data"


def _api_key() -> str:
    load_dotenv()
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit("FRED_API_KEY가 없습니다. .env 파일에 FRED_API_KEY=발급받은키 를 넣어주세요.")
    return key


def fetch(series_id: str, max_age_hours: float = 12) -> pd.Series:
    """FRED 지표 하나를 날짜-값 시리즈로 받아온다."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{series_id}.csv"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
        s.name = series_id
        return s

    params = {"series_id": series_id, "api_key": _api_key(),
              "file_type": "json", "observation_start": C.START}
    r = requests.get(URL, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{series_id}: HTTP {r.status_code} {r.text[:150]}")
    obs = r.json()["observations"]
    s = pd.Series({o["date"]: o["value"] for o in obs}, name=series_id)
    s.index = pd.to_datetime(s.index)
    s = pd.to_numeric(s, errors="coerce").dropna()   # FRED는 빈 값을 "." 로 준다
    s.to_csv(path)
    return s


def fetch_many(ids) -> dict:
    out = {}
    for sid in ids:
        try:
            out[sid] = fetch(sid)
        except SystemExit:
            raise
        except Exception as e:  # 지표 하나 실패는 경고만
            print(f"[경고] {sid} 받기 실패 → 이 지표는 빼고 계산합니다 ({e})")
        time.sleep(0.1)  # FRED 호출 한도(분당 120회) 여유
    return out


def all_ids() -> list:
    ids = []
    for group in (C.HARD, C.SOFT, C.INFLATION, C.CPI_COMPONENTS, C.MARKET, C.TARGET):
        ids += list(group)
    return ids


def monthly(s: pd.Series, how: str = "mean") -> pd.Series:
    """일별/월별 데이터를 월 단위로 맞춘다 (인덱스: 2026-10 같은 '월')."""
    g = s.groupby(s.index.to_period("M"))
    return g.last() if how == "last" else g.mean()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    raw = fetch_many(all_ids())
    print(f"\n받은 지표 {len(raw)}개")
    for sid, s in raw.items():
        print(f"  {sid:<20} {s.index[0].date()} ~ {s.index[-1].date()}  최근값 {s.iloc[-1]:.2f}")
