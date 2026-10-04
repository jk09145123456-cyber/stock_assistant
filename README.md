# stock-assistant

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC)
![License](https://img.shields.io/badge/license-personal%20use-lightgrey)

보유·관심 종목의 매수/매도를 **실행하지 않고**, 상태를 판단하고 근거를 설명해주는 개인용 투자 보조 시스템입니다.
규칙 기반 지표 분석과 AI 뉴스 해석을 결합해 "지금 보유 종목이 어떤 상태인지, 왜 그런지"를 매일 한눈에 보여줍니다.
**실제 매수/매도 주문은 항상 증권사 앱에서 직접 실행합니다.**

---

## 목차

- [핵심 원칙](#핵심-원칙)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [프로젝트 구조](#프로젝트-구조)
- [시작하기](#시작하기)
  - [요구 사항](#요구-사항)
  - [설치](#설치)
  - [설정](#설정)
  - [실행](#실행)
- [판단 로직 요약](#판단-로직-요약)
- [구현 현황](#구현-현황)
- [보안 및 개인정보](#보안-및-개인정보)
- [알아둘 점 / 한계](#알아둘-점--한계)
- [참고 자료](#참고-자료)
- [라이선스](#라이선스)

---

## 핵심 원칙

이 시스템은 **주문을 대신 내리지 않습니다.** 할 수 있는 판단은 아래 6가지뿐이며, 각 판단마다 근거·반대 근거·해제 조건을 같이 제시합니다.

| 판단 | 의미 |
|---|---|
| 관심 | 매수 조건 미충족, 계속 관찰 |
| 보유 | 뚜렷한 신호 없음, 기존 포지션 유지 |
| 일부 매도 검토 | 익절/트레일링/위험 신호 - 비중 일부 축소 검토 |
| 전량 매도 검토 | 추세 완전 훼손 또는 구조적 손절 기준 도달 |
| 추가매수 검토 | 전략 신호 + 리스크 한도 충족 |
| 추가매수 금지 | 신호는 있으나 현금/한도/급락장으로 보류 |
| *(데이터 이상 시)* **판단 중지** | 시세 결측·지연 등 데이터 품질 문제 감지 |

모든 손절/목표가 기준선은 가능한 한 **매번 재계산되는 동적 값**입니다 (예: 장기 보유 종목의 손절선 = 전고점 × (1 − 종목별 역대 최악낙폭 기준 임계값)). 사람이 숫자를 직접 유지보수할 필요가 없고, 직접 고정값을 지정하면 그 값이 우선합니다.

## 주요 기능

- **시세 기반 기술적 판단** — EMA/RSI/MACD/ADX/볼린저 밴드 등을 조합한 4개 전략(추세추종·눌림목·돌파·평균회귀) 앙상블 투표
- **시장 국면 인식** — 상승/횡보/하락/급락(crash) 국면을 자동 분류해 신호를 보수화
- **동적 리스크 관리** — 트레일링 스톱, 분할 익절 티어, 종목별 과거 최악낙폭 기반 손절선 자동 계산
- **과매도 반등 통계** — 종목이 과거 유사 과매도 상황에서 실제로 평균 며칠 만에 반등했는지 직접 계산해 제시
- **반대 근거 제시** — 최종 판단과 반대되는 전략/지표 신호를 함께 보여줘 확증편향 방지
- **포트폴리오 위험 가드레일** — 종목/업종 비중 한도, 현금 비율, 추가매수 횟수 제한
- **뉴스 + AI 참고 의견** — 구글 뉴스 헤드라인 수집 후 Gemini로 재무지표·뉴스를 종합 해석 (선택 기능)
- **워크포워드 백테스트** — 수수료·세금·슬리피지를 반영한 전략 검증 엔진
- **신규 매수 후보 스크리너** — 지정한 종목 유니버스를 순회해 매수 후보를 탐색
- **Streamlit 대시보드** — 보유 현황, 매매 기준선, 가격 시나리오, 차트, 행동 기록을 한 화면에서 확인

## 기술 스택

| 분류 | 사용 기술 |
|---|---|
| 언어 | Python 3.11+ |
| 시세 수집 | [pykrx](https://github.com/sharebook-kr/pykrx) (국내), [yfinance](https://github.com/ranaroussi/yfinance) (미국/지수) |
| 데이터 처리 | pandas, numpy |
| 백테스트 | [backtesting.py](https://kernc.github.io/backtesting.py/) |
| 대시보드 | [Streamlit](https://streamlit.io/), Plotly |
| 뉴스 수집 | feedparser (구글 뉴스 RSS) |
| AI 의견 생성 | Google Gemini API (`google-genai`) |
| 테스트 | pytest |

## 프로젝트 구조

```
app/
├─ config.py          # config/*.yaml 로더
├─ portfolio/         # 보유·관심 종목 모델, 비중/현금비율 계산 (환율 반영)
├─ market_data/       # 시세 수집(pykrx/yfinance) + 데이터 신선도 검증 + 환율
├─ indicators/        # EMA/ATR/RSI/MACD/ADX/볼린저/기울기/이격도/과매도 반등 통계
├─ regime/            # 시장 국면(상승/횡보/하락/급락) 분류
├─ strategies/        # 추세추종/눌림목/돌파/평균회귀 전략 + 앙상블 집계
├─ risk/              # 포지션 사이징, 비중 한도, 트레일링 스톱, 분할 익절
├─ scoring/           # 카테고리별 원점수 → 0~100 정규화 + 위험점수
├─ decision/          # 우선순위 규칙 엔진 → 최종 판단
├─ explanations/      # 판단/근거/반대근거/해제조건 텍스트 포맷
├─ alerts/            # 상태 전이 감지 알림
├─ journal.py         # 사용자 실제 행동 기록
├─ backtest/          # 워크포워드 백테스트 엔진
├─ screening/         # 신규 매수 후보 스크리닝
├─ news/              # 종목별 최신 뉴스 헤드라인 수집
└─ llm/               # Gemini 기반 뉴스·지표 해석
dashboard/app.py       # Streamlit 대시보드
config/                # portfolio / risk_rules / strategy_rules / backtest 설정
main.py                # CLI 진입점 (오늘의 판단)
run_backtest.py        # CLI 진입점 (백테스트)
run_screener.py        # CLI 진입점 (신규 매수 후보 스크리닝)
tests/                 # 지표 단위 테스트
```

## 시작하기

### 요구 사항

- Python 3.11 이상
- (선택) [Google AI Studio](https://aistudio.google.com/apikey) 무료 API 키 — AI 뉴스 해석 기능 사용 시에만 필요

### 설치

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

### 설정

실제 계좌 정보가 담기는 설정 파일은 저장소에 올라가지 않도록 `.gitignore` 처리되어 있습니다. 예시 파일을 복사해서 채워 넣으세요.

```bash
cp config/portfolio.example.yaml config/portfolio.yaml            # 보유·관심 종목
cp config/screening_universe.example.yaml config/screening_universe.yaml  # 스크리닝 대상 종목
cp .env.example .env                                               # GEMINI_API_KEY (선택)
```

| 파일 | 용도 |
|---|---|
| `config/portfolio.yaml` | 실제 보유 종목, 수량, 평단가, 계좌별 현금 |
| `config/screening_universe.yaml` | 신규 매수 후보 스캔 대상 종목 목록 |
| `config/risk_rules.yaml` | 익절 티어, 트레일링 배수, 손절 임계값 등 리스크 파라미터 |
| `config/strategy_rules.yaml` | EMA 세트, RSI/MACD/볼린저 파라미터, 앙상블 합의 기준 |
| `config/backtest.yaml` | 백테스트 비용(수수료·세금·슬리피지)·기간 설정 |
| `.env` | `GEMINI_API_KEY` (AI 뉴스 해석 기능 전용) |

### 실행

```bash
# 오늘의 판단 (CLI)
.venv/Scripts/python main.py

# 대시보드
.venv/Scripts/python -m streamlit run dashboard/app.py

# 전략 백테스트
.venv/Scripts/python run_backtest.py <종목코드> KR
.venv/Scripts/python run_backtest.py <티커> US

# 신규 매수 후보 스크리닝
.venv/Scripts/python run_screener.py

# 테스트
.venv/Scripts/python -m pytest tests/ -q
```

## 판단 로직 요약

```
시세 수집 → 데이터 검증 → 지표 계산 → 시장 국면 분류 → 전략 앙상블 투표
   → 카테고리별 점수화 → 우선순위 규칙 엔진 → 최종 판단 + 근거/반대근거
```

우선순위는 다음 순서로 적용됩니다: **데이터 오류 → 시스템 위험 제한 → 포트폴리오 비중 제한 → 시장 급락 여부 → 종목 추세 → 매수/매도 세부 조건**. 상위 규칙이 하위 규칙을 가리지 않도록, 종목 단위 판단을 먼저 계산한 뒤 더 급한 경우에만 상위 규칙으로 대체합니다.

## 구현 현황

- [x] 핵심 시스템 — 보유 종목 입력, 시세 수집/검증, 지표, 시장 국면, 종목별 점수/판단, 설명
- [x] 전략 엔진 — 4개 전략 앙상블, 신뢰도 산출, 워크포워드 백테스트, 리스크 엔진
- [x] 뉴스/AI 연동 — 구글 뉴스 수집 + Gemini 기반 종합 의견 생성
- [ ] 파라미터 설정 UI (현재는 YAML 직접 수정)
- [ ] 실시간 데이터 장애 알림 고도화, 공시 데이터 연동
- [ ] 머신러닝 기반 하락위험 모델 (전체 유니버스 학습 데이터 필요)
- [ ] 실시간 시세(WebSocket) 연동 — `app/market_data/providers.py`의 시그니처는 교체 가능하게 설계됨
- [ ] 실계좌 잔고 자동조회 — 현재는 수량/평단 수동 입력 + 현재가만 실시간 조회

## 보안 및 개인정보

다음 파일/폴더는 전부 `.gitignore`에 등록되어 커밋되지 않습니다.

- `config/portfolio.yaml` — 실제 보유 수량, 평단가, 계좌별 현금
- `config/screening_universe.yaml` — 실제 스크리닝 대상 종목
- `.env` — API 키
- `data/`, `logs/` — 시세/뉴스 캐시, AI 의견, 판단 이력 등 보유종목을 추론할 수 있는 파생 데이터

저장소에는 `*.example.yaml` / `.env.example`만 올라가며, 사용 전에 이를 복사해서 실제 값을 채워 넣는 구조입니다.

## 알아둘 점 / 한계

- 예시 설정 파일을 복사한 직후 상태로는 비중 계산이 무의미합니다. 반드시 실제 보유 수량/평단으로 교체해야 합니다.
- 급락 판정 조건 중 "대부분의 종목이 동반 하락"은 개별 종목 시세만으로 계산할 수 없어 제외했습니다 (나머지 조건으로 판정). 여러 종목을 동시에 스캔하는 기능을 추가하면 보강할 수 있습니다.
- 데이터 신선도 검사는 무료 일봉 데이터 기준으로 "며칠 전 봉인지"를 봅니다. 실시간 체결가로 전환하면 분 단위 검사로 바꿀 수 있도록 파라미터를 분리해 두었습니다.
- 백테스트 기본 전략은 추세추종 골격 + ATR 트레일링 예시입니다. 실사용 전 반드시 `run_backtest.py`로 대상 종목에 대해 검증하세요.
- 과거 데이터 기반 통계(반등 소요일 등)는 미래를 보장하지 않는 참고 지표입니다.

## 참고 자료

- **TradingAgents** (Tauric Research) — 멀티에이전트 LLM 트레이딩 프레임워크. "강세/약세를 일부러 반박시킨다"는 아이디어를 LLM 토론 없이 결정론적 규칙으로 구현한 "반대 근거" 설계(`app/decision/engine.py`)에 참고.
- **Larry Connors의 단기 평균회귀 연구** (*Short-Term Trading Strategies That Work*, Connors & Alvarez) — RSI 과매도 이후 단기 반등 패턴. `app/indicators/core.py`의 `oversold_recovery_stats` 구현에 참고.
- **손익비(R-multiple) 리스크 관리 원칙** — "위험 1당 보상 N을 노린다"는 일반적인 트레이딩 리스크 관리 개념. 익절/손절 사이징 설계에 참고.

## 라이선스

별도 오픈소스 라이선스 없이 개인 학습·연습용으로 관리하는 저장소입니다. 재배포나 상업적 사용 목적의 이용은 허용하지 않습니다.

---

> 이 프로젝트는 투자 판단을 보조하는 참고 도구이며, 실제 투자 결정과 그 결과에 대한 책임은 사용자 본인에게 있습니다.
