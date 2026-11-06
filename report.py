"""텔레그램 리포트: 최신 판단을 요약해서 보낸다.

실행
  python report.py --dry   # 보내지 않고 화면에만 출력
  python report.py         # 텔레그램으로 전송
"""
import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

import config as C
from fred_data import fetch_many, all_ids
from signals import build

KST = timezone(timedelta(hours=9))


def f(x, fmt="+.2f", unit=""):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:{fmt}}{unit}"


def latest_spread(raw):
    """가장 최근 영업일의 2년물 − 기준금리 (월평균보다 빠른 신호)."""
    if "DGS2" not in raw or "DFF" not in raw:
        return None, None
    both = pd.concat([raw["DGS2"], raw["DFF"]], axis=1).dropna()
    if both.empty:
        return None, None
    return both.index[-1].date(), both.iloc[-1, 0] - both.iloc[-1, 1]


def make_message(df: pd.DataFrame, raw: dict) -> str:
    rows = df.dropna(subset=["score"])
    cur, prev = rows.iloc[-1], rows.iloc[-2]
    month = rows.index[-1]
    icon = {"인하 쪽": "🔵", "동결": "⚪", "인상 쪽": "🔴"}[cur["label"]]

    lines = [f"🏛 연준 정책 기조 점검 ({datetime.now(KST):%Y-%m-%d})", ""]
    lines.append(f"{icon} 판단: {cur['label']}  (점수 {f(cur['score'])}, {month} 기준)")
    if cur["label"] != prev["label"]:
        lines.append(f"🔔 기조 변화: {prev['label']} → {cur['label']}")
    else:
        lines.append(f"지난달 {prev['label']} (점수 {f(prev['score'])}) 유지")

    lines += ["", "구성 (+ 인상 압력 / − 인하 압력)",
              f"· 물가 {f(cur['inflation'])}  근원PCE 3개월 연율 {f(cur.get('v_core_pce'), '.1f', '%')}, "
              f"가속 품목 {f(cur.get('v_diffusion', float('nan')) * 100, '.0f', '%')}",
              f"· 경기 {f(cur['growth'])}  Hard {f(cur['hard'])} / Soft {f(cur['soft'])}",
              f"· 시장 {f(cur['market'])}  2년물−기준금리 월평균 {f(cur.get('v_market'), '+.2f', '%p')}"]

    day, spread = latest_spread(raw)
    if spread is not None:
        lines.append(f"  └ 최근({day}) {spread:+.2f}%p")

    gap = cur["soft"] - cur["hard"]
    if not math.isnan(gap) and abs(gap) >= 1:
        side = "체감(설문)이 실제 지표보다 약함 → 경기 둔화가 먼저 올 수 있음" if gap < 0 \
            else "체감(설문)이 실제 지표보다 강함 → 회복 기대가 먼저 반영"
        lines.append(f"  └ Soft−Hard 차이 {gap:+.2f}: {side}")

    sahm = cur.get("v_sahm")
    if sahm is not None and not math.isnan(sahm) and sahm >= 0.5:
        lines.append(f"⚠️ Sahm 지표 {sahm:.2f}%p — 경기침체 경고선(0.5) 넘음")

    lines += ["", f"기준: ±{C.THRESHOLD} 넘으면 인상/인하 쪽. 투자 참고용."]
    return "\n".join(lines)


def send(text: str):
    load_dotenv()
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise SystemExit("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없습니다 (.env 또는 GitHub Secrets 확인).")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=20)
    if not r.ok:
        raise SystemExit(f"텔레그램 전송 실패: {r.status_code} {r.text[:200]}")
    print("텔레그램 전송 완료")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="보내지 않고 출력만")
    args = ap.parse_args()

    raw = fetch_many(all_ids())
    msg = make_message(build(raw), raw)
    print(msg)
    if not args.dry:
        send(msg)
