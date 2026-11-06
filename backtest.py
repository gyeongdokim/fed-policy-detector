"""과거 검증: 매달 말에 낸 판단이, 그 뒤 6개월 안의 실제 연준 결정과 맞았는가?

정답 만드는 법
  - 매달 말 목표금리를 기준으로, 이후 6개월 안에 0.25%p 이상 처음 움직인 방향
  - 처음 움직임이 내림 → '인하', 올림 → '인상', 안 움직임 → '동결'

실행
  python backtest.py            # 전체 모델 + 매크로만 모델 둘 다 검증, docs/에 차트·CSV 저장
"""
import sys

import pandas as pd

import config as C
from fred_data import fetch_many, all_ids, monthly
from signals import build


def policy_rate(raw: dict) -> pd.Series:
    """연준 목표금리(2008.12 이전은 단일값, 이후는 범위 상단)를 이어 붙인 월말 값."""
    parts = [raw[k] for k in ("DFEDTAR", "DFEDTARU") if k in raw]
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    m = monthly(s, how="last")
    return m[m.index < pd.Timestamp.today().to_period("M")]   # 아직 안 끝난 이번 달 제외


def first_move(rate: pd.Series) -> pd.Series:
    vals, out = rate.values, {}
    for i, month in enumerate(rate.index):
        if i + C.HORIZON >= len(vals):
            break                              # 6개월 뒤가 아직 안 옴 → 채점 불가
        res = "동결"
        for j in range(i + 1, i + C.HORIZON + 1):
            d = vals[j] - vals[i]
            if d <= -C.MOVE_STEP + 1e-9:
                res = "인하"; break
            if d >= C.MOVE_STEP - 1e-9:
                res = "인상"; break
        out[month] = res
    return pd.Series(out)


def evaluate(df: pd.DataFrame, actual: pd.Series, title: str) -> pd.DataFrame:
    d = pd.DataFrame({"신호": df["label"], "실제": actual}).dropna()
    d = d[d.index >= pd.Period(C.EVAL_START, "M")]
    order_sig, order_act = ["인하 쪽", "동결", "인상 쪽"], ["인하", "동결", "인상"]

    print(f"\n{'=' * 60}\n{title}  ({d.index[0]} ~ {d.index[-1]}, {len(d)}개월)\n{'=' * 60}")
    counts = pd.crosstab(d["신호"], d["실제"]).reindex(index=order_sig, columns=order_act, fill_value=0)
    pct = counts.div(counts.sum(axis=1).replace(0, 1), axis=0) * 100
    table = pct.round(0).astype(int).astype(str) + "%"
    table["개월 수"] = counts.sum(axis=1)
    print("행 = 그달 말 신호, 열 = 이후 6개월 안 실제 첫 결정")
    print(table.to_string())

    base = d["실제"].value_counts(normalize=True).reindex(order_act, fill_value=0) * 100
    print("\n아무 신호 없이 본 기본 확률:  " + "  ".join(f"{k} {v:.0f}%" for k, v in base.items()))

    hit = {"인하 쪽": "인하", "동결": "동결", "인상 쪽": "인상"}
    acc = (d["신호"].map(hit) == d["실제"]).mean() * 100
    naive = (d["실제"] == "동결").mean() * 100
    print(f"전체 적중률 {acc:.0f}%  (비교: '항상 동결'이라고만 했을 때 {naive:.0f}%)")
    for sig, act in (("인하 쪽", "인하"), ("인상 쪽", "인상")):
        n = counts.loc[sig].sum()
        if n:
            print(f"'{sig}' 신호 뒤 실제 {act}: {pct.loc[sig, act]:.0f}%  (기본 확률 {base[act]:.0f}%)")
    return d


def save_chart(df: pd.DataFrame, rate: pd.Series, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for f in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f
            break
    plt.rcParams["axes.unicode_minus"] = False

    s = df["score"].dropna()
    s = s[s.index >= pd.Period(C.EVAL_START, "M")]
    r = rate[rate.index >= pd.Period(C.EVAL_START, "M")]
    x1, x2 = s.index.to_timestamp(), r.index.to_timestamp()

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True,
                                 gridspec_kw={"height_ratios": [2, 1]})
    a1.plot(x1, s.values, color="#0B47C2", lw=1.2)
    a1.axhline(C.THRESHOLD, color="#CF3A2C", ls="--", lw=0.8)
    a1.axhline(-C.THRESHOLD, color="#0B47C2", ls="--", lw=0.8)
    a1.axhline(0, color="#999", lw=0.6)
    a1.fill_between(x1, s.values, C.THRESHOLD, where=s.values >= C.THRESHOLD, color="#CF3A2C", alpha=.2)
    a1.fill_between(x1, s.values, -C.THRESHOLD, where=s.values <= -C.THRESHOLD, color="#0B47C2", alpha=.2)
    a1.set_title("연준 정책 점수 (+ 인상 압력 / − 인하 압력)")
    a2.step(x2, r.values, where="post", color="#0E1A2B", lw=1.2)
    a2.set_title("실제 연준 목표금리(%)")
    for a in (a1, a2):
        a.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"\n차트 저장: {path}")


def main(raw=None):
    from pathlib import Path
    docs = Path(__file__).parent / "docs"
    docs.mkdir(exist_ok=True)

    raw = raw if raw is not None else fetch_many(all_ids())
    rate = policy_rate(raw)
    actual = first_move(rate)

    full = build(raw, use_market=True)
    d = evaluate(full, actual, "전체 모델 (물가 + 경기 + 시장)")
    evaluate(build(raw, use_market=False), actual, "매크로만 (시장 지표 제외)")
    print("\n※ 시장 지표(2년물)는 이미 연준 예상을 담고 있어 적중률을 끌어올린다."
          "\n  '매크로만' 결과가 경제지표 자체의 설명력이다.")

    out = full[["score", "label", "inflation", "growth", "hard", "soft", "market"]].copy()
    out["실제_6개월"] = actual
    out.loc[out.index >= pd.Period(C.EVAL_START, "M")].round(3).to_csv(docs / "backtest.csv", encoding="utf-8-sig")
    save_chart(full, rate, docs / "score.png")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
