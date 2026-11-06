"""설정 파일 — 어떤 FRED 지표를, 어떤 기준으로 쓸지 전부 여기 모아둔다.
숫자를 바꾸면 backtest.py로 반드시 다시 검증할 것."""

START = "1960-01-01"          # FRED에서 받아올 시작일

# ── 1) 경기: Hard 데이터 (실제로 집계된 숫자) ──
HARD = {
    "PAYEMS": "비농업 고용",
    "UNRATE": "실업률",
    "INDPRO": "산업생산",
    "RSAFS":  "소매판매",
}

# ── 2) 경기: Soft 데이터 (설문으로 본 체감 경기) ──
SOFT = {
    "UMCSENT":            "미시간대 소비자심리",
    "GACDFSA066MSFRBPHI": "필라델피아 연은 제조업 설문",
    "GACDISA066MSFRBNY":  "뉴욕 연은 제조업 설문",
}

# ── 3) 물가 ──
INFLATION = {
    "PCEPILFE": "근원 PCE 물가 (연준이 가장 중시)",
    "CPIAUCSL": "CPI 전체 (소매판매를 실질로 바꿀 때 사용)",
}

# 물가 확산지수에 쓰는 CPI 세부 품목 (계절조정)
CPI_COMPONENTS = {
    "CPIUFDSL":       "식품",
    "CUSR0000SEFV":   "외식",
    "CPIENGSL":       "에너지",
    "CUSR0000SAH1":   "주거",
    "CPIAPPSL":       "의류",
    "CPIMEDSL":       "의료 전체",
    "CUSR0000SAM2":   "의료 서비스",
    "CPITRNSL":       "교통",
    "CUSR0000SETA01": "신차",
    "CUSR0000SETA02": "중고차",
    "CPIRECSL":       "여가",
    "CPIEDUSL":       "교육·통신",
}

# ── 4) 시장 기대 ──
MARKET = {
    "DGS2": "미 국채 2년물 금리",
    "DFF":  "실효 연방기금금리",
}

# ── 검증용: 실제 연준 목표금리 ──
TARGET = {
    "DFEDTAR":  "목표금리 (~2008.12)",
    "DFEDTARU": "목표금리 상단 (2008.12~)",
}

# 발표 시차(개월). 예: 10월 고용은 11월 초에 나오므로 10월 말에는 9월 값까지만 알 수 있다 → 1
# 과거 검증에서 '그때는 몰랐던 숫자'를 쓰지 않기 위한 장치.
LAG = {
    "payrolls": 1, "sahm": 1, "indpro": 1, "real_retail": 1,   # Hard: 다음 달 발표
    "umich": 0, "philly": 0, "empire": 0,                      # Soft: 그 달 안에 발표
    "core_pce": 2,                                             # PCE: 다음 달 말 발표 → 보수적으로 2
    "diffusion": 1,                                            # CPI: 다음 달 중순 발표
    "market": 0,                                               # 시장금리: 매일
}

# 점수 합칠 때 가중치 (+ 인상 압력 / − 인하 압력)
WEIGHTS = {"inflation": 0.4, "growth": 0.3, "market": 0.3}

THRESHOLD = 0.5      # 점수 ≥ +0.5 → 인상 쪽, ≤ −0.5 → 인하 쪽, 그 사이 → 동결
Z_MIN_MONTHS = 60    # 표준화(z점수)를 시작하려면 최소 5년치 과거가 필요

# 검증 설정
HORIZON = 6          # 신호 후 몇 개월 안의 첫 금리 변경을 정답으로 볼지
MOVE_STEP = 0.25     # 이만큼(%p) 움직여야 '변경'으로 인정
EVAL_START = "1990-01"
