"""지표를 점수로 바꾸고, 지금 연준 기조가 인하·동결·인상 중 어느 쪽인지 판단하는 파일.

흐름
  1) 원지표 → 의미 있는 숫자로 변환 (예: 고용 '수준' → 최근 3개월 평균 증가폭)
  2) z점수: "과거 평균보다 얼마나 높은가"를 표준편차 단위로 (그 시점까지의 과거만 사용)
  3) 발표 시차만큼 뒤로 미룸 → 그 달 말에 실제로 알 수 있었던 값만 남김
  4) 그룹 점수(물가·경기·시장) → 가중합 = 정책 점수
     + 면 인상 압력, − 면 인하 압력
"""
import numpy as np
import pandas as pd

import config as C
from fred_data import fetch_many, all_ids, monthly

# 방향: +1이면 값이 클수록 인상 압력, -1이면 반대
SIGN = {"payrolls": 1, "sahm": -1, "indpro": 1, "real_retail": 1,
        "umich": 1, "philly": 1, "empire": 1,
        "core_pce": 1, "diffusion": 1, "market": 1}
GROUP = {"payrolls": "hard", "sahm": "hard", "indpro": "hard", "real_retail": "hard",
         "umich": "soft", "philly": "soft", "empire": "soft",
         "core_pce": "inflation", "diffusion": "inflation", "market": "market"}
NAME = {"payrolls": "고용 3개월 평균 증가(천 명)", "sahm": "Sahm 지표(%p)",
        "indpro": "산업생산 6개월 연율(%)", "real_retail": "실질 소매판매 6개월 연율(%)",
        "umich": "미시간 소비자심리", "philly": "필라델피아 연은", "empire": "뉴욕 연은",
        "core_pce": "근원 PCE 3개월 연율(%)", "diffusion": "가속 품목 비율",
        "market": "2년물−기준금리(%p)"}


def annualized(s: pd.Series, n: int) -> pd.Series:
    """n개월 변화율을 1년 기준으로 환산(%)."""
    return ((s / s.shift(n)) ** (12 / n) - 1) * 100


def zscore(s: pd.Series) -> pd.Series:
    """각 시점까지의 과거 데이터만으로 계산한 z점수 (미래 정보 사용 안 함)."""
    s = s.dropna()
    mean = s.expanding(C.Z_MIN_MONTHS).mean()
    std = s.expanding(C.Z_MIN_MONTHS).std()
    return ((s - mean) / std).clip(-3, 3)


def diffusion_index(raw: dict) -> pd.Series:
    """물가 확산지수: CPI 세부 품목 중 '최근 3개월 상승 속도 > 최근 1년 상승률'인 품목 비율(0~1)."""
    accel, valid = [], []
    for sid in C.CPI_COMPONENTS:
        if sid not in raw:
            continue
        x = monthly(raw[sid])
        a3 = annualized(x, 3)
        a12 = (x / x.shift(12) - 1) * 100
        ok = a3.notna() & a12.notna()
        accel.append(((a3 > a12) & ok).astype(float))
        valid.append(ok.astype(float))
    if not accel:
        return pd.Series(dtype=float)
    n = pd.concat(valid, axis=1).sum(axis=1)
    share = pd.concat(accel, axis=1).sum(axis=1) / n
    return share[n >= 5]   # 품목이 5개 이상 있을 때만 인정


def indicators(raw: dict) -> pd.DataFrame:
    """원지표 → 해석 가능한 숫자 (월 단위, '해당 월' 기준)."""
    M = lambda sid: monthly(raw[sid])
    out = {}
    if "PAYEMS" in raw:
        out["payrolls"] = M("PAYEMS").diff().rolling(3).mean()
    if "UNRATE" in raw:
        # Sahm 지표: 실업률 3개월 평균 − 직전 12개월 중 최저치. 0.5 이상이면 경기침체 신호로 알려짐
        u3 = M("UNRATE").rolling(3).mean()
        out["sahm"] = u3 - u3.shift(1).rolling(12).min()
    if "INDPRO" in raw:
        out["indpro"] = annualized(M("INDPRO"), 6)
    if "RSAFS" in raw and "CPIAUCSL" in raw:
        out["real_retail"] = annualized(M("RSAFS") / M("CPIAUCSL"), 6)
    if "UMCSENT" in raw:
        out["umich"] = M("UMCSENT")
    if "GACDFSA066MSFRBPHI" in raw:
        out["philly"] = M("GACDFSA066MSFRBPHI")
    if "GACDINA066MSFRBNY" in raw:
        out["empire"] = M("GACDINA066MSFRBNY")
    if "PCEPILFE" in raw:
        out["core_pce"] = annualized(M("PCEPILFE"), 3)
    d = diffusion_index(raw)
    if len(d):
        out["diffusion"] = d
    if "DGS2" in raw and "DFF" in raw:
        out["market"] = M("DGS2") - M("DFF")
    return pd.DataFrame(out).sort_index()


def build(raw: dict = None, use_market: bool = True) -> pd.DataFrame:
    """월별 정책 점수 표를 만든다. 각 행 = 그 달 말에 알 수 있었던 정보로 낸 판단."""
    raw = raw if raw is not None else fetch_many(all_ids())
    ind = indicators(raw)
    idx = pd.period_range(ind.index.min(), pd.Timestamp.today().to_period("M"), freq="M")
    ind = ind.reindex(idx)

    z, known = pd.DataFrame(index=idx), pd.DataFrame(index=idx)
    for col in ind.columns:
        lag = C.LAG[col]
        zc = zscore(ind[col]).reindex(idx) * SIGN[col]
        # 시차만큼 미루고, 새 발표가 없으면 직전 값을 최대 2개월 유지
        z[col] = zc.shift(lag).ffill(limit=2)
        known[col] = ind[col].shift(lag).ffill(limit=2)

    def group_mean(name):
        cols = [c for c in z.columns if GROUP[c] == name]
        return z[cols].mean(axis=1) if cols else pd.Series(np.nan, index=idx)

    g = pd.DataFrame(index=idx)
    g["hard"] = group_mean("hard")
    g["soft"] = group_mean("soft")
    g["growth"] = g[["hard", "soft"]].mean(axis=1)
    g["inflation"] = group_mean("inflation")
    g["market"] = group_mean("market")

    w = {k: v for k, v in C.WEIGHTS.items() if use_market or k != "market"}
    wsum = sum(g[k].notna() * v for k, v in w.items())
    score = sum(g[k].fillna(0) * v for k, v in w.items()) / wsum.replace(0, np.nan)
    # 물가와 경기 둘 다 있어야 판단 (한쪽만 있으면 비움)
    score[g["inflation"].isna() | g["growth"].isna()] = np.nan
    g["score"] = score

    label = np.select([score <= -C.THRESHOLD, score >= C.THRESHOLD], ["인하 쪽", "인상 쪽"], "동결")
    g["label"] = pd.Series(label, index=idx).where(score.notna())

    return pd.concat([g, z.add_prefix("z_"), known.add_prefix("v_")], axis=1)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    df = build()
    cols = ["score", "label", "inflation", "growth", "hard", "soft", "market"]
    print(df[cols].dropna(subset=["score"]).tail(12).round(2).to_string())
