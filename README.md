# stock-assistant

보유·관심 종목의 매수/매도를 **실행하지 않고**, 상태를 판단하고 근거를 설명해주는
개인용 투자 보조 시스템. 실제 주문은 항상 증권사 앱에서 직접 한다.

원본 기획 문서의 1장~18장 구조를 그대로 구현했다. 판단은 다음 6가지로만 제한된다:
관심 / 보유 / 일부 매도 검토 / 전량 매도 검토 / 추가매수 검토 / 추가매수 금지
(+ 데이터 이상 시 "판단 중지").

## 빠른 시작

```bash
# 1. 가상환경
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# 2. 개인 설정 파일 준비 (둘 다 .gitignore에 등록돼 있어 커밋되지 않음)
cp config/portfolio.example.yaml config/portfolio.yaml   # 실제 보유·관심 종목으로 수정
cp config/screening_universe.example.yaml config/screening_universe.yaml # 분석 대상 종목으로 수정
cp .env.example .env                                      # GEMINI_API_KEY 입력 (선택)

# 3. CLI로 오늘 판단 확인
.venv/Scripts/python main.py

# 4. 대시보드 (16장 화면 구성)
.venv/Scripts/python -m streamlit run dashboard/app.py

# 5. 전략 백테스트 (15장 워크포워드 검증)
.venv/Scripts/python run_backtest.py YOUR_KR_SYMBOL KR
.venv/Scripts/python run_backtest.py YOUR_US_TICKER US

# 6. 신규 매수 후보 스크리닝 (직접 작성한 config/screening_universe.yaml)
.venv/Scripts/python run_screener.py

# 7. 테스트
.venv/Scripts/python -m pytest tests/ -q
```

## 폴더 구조 (18장)

```
app/
  config.py         # config/*.yaml 로더
  portfolio/         # 4장: 보유·관심 종목 모델, 비중/현금비율 계산 (환율 반영)
  market_data/        # 4장: 시세 수집(pykrx/yfinance) + 검증 + 환율
  indicators/         # 5장/10장: EMA/ATR/RSI/MACD/ADX/볼린저/기울기/이격도
  regime/              # 6장: 시장 국면(상승/횡보/하락/급락) 분류
  strategies/          # 13장: 추세추종/눌림목/돌파/평균회귀 + 앙상블 집계
  risk/                # 3장/7장/12장: 포지션 사이징, 비중 한도, 종목 간 우선순위
  scoring/              # 11장: 카테고리별 원점수 -> 0~100 정규화 + 위험점수
  decision/            # 12장: 우선순위 규칙 엔진 -> 최종 판단
  explanations/        # 1장: 판단/근거/반대근거/해제조건 텍스트 포맷
  alerts/               # 17장: 상태 전이 감지 알림 (data/decision_state.json)
  journal.py            # 16장: 사용자 실제 행동 기록 (data/action_journal.csv)
  backtest/             # 15장: backtesting.py 기반 워크포워드 백테스트
  screening/            # 신규 매수 후보 스크리닝 (기존 파이프라인 재사용, 유니버스 순회)
  news/                 # 종목별 최신 뉴스 헤드라인 (구글 뉴스 RSS, API 키 불필요)
dashboard/app.py         # 16장: Streamlit 대시보드 (가격 시나리오 표 + 뉴스 섹션 포함)
config/                  # portfolio/risk_rules/strategy_rules/backtest yaml
main.py                  # CLI 진입점 (오늘의 판단)
run_backtest.py           # CLI 진입점 (백테스트)
```

## 사용한 오픈소스

- **yfinance** – 미국 종목/지수 시세 (KOSPI·KOSDAQ 지수도 `^KS11`/`^KQ11`로 이 경로를 씀 — pykrx의 지수 API가 KRX 서버 사정으로 불안정해서 우회)
- **pykrx** – 한국 개별 종목 시세
- **backtesting.py** – 워크포워드 백테스트 엔진 (수수료/세금/슬리피지 반영)
- **pandas/numpy** – 지표 계산은 TA-Lib 등 C 확장 의존성 없이 직접 구현 (Windows 설치 이슈 회피)
- **Streamlit** – 대시보드
- **scikit-learn** – 14장 2단계(로지스틱 회귀 하락위험 모델) 확장 시 사용 예정 (아직 미구현)

## 현재 구현 범위 (기획서 19장 로드맵 기준)

- ✅ 1단계 핵심 시스템: 보유 종목 입력, 시세 수집·검증, 지표, 시장 국면, 종목별 점수/판단, 설명
- ✅ 2단계 대부분: 4개 전략 앙상블, 신뢰도, 워크포워드 백테스트(비용 반영), 리스크 엔진(비중/사이징/우선순위)
- 🟡 2단계 일부 남음: 파라미터 설정 UI (지금은 yaml 직접 수정)
- ⬜ 3단계: 실시간 데이터 장애 알림 고도화, 뉴스/공시/재무 데이터 연동
- ⬜ 14장 2~3단계: 로지스틱 회귀·XGBoost 하락위험 모델 (전체 유니버스 학습 데이터 필요 - 보유종목만으로는 과최적화 위험 있음, 별도 데이터 파이프라인 필요)
- ⬜ 실시간 시세(WebSocket): 한국투자증권 Open API로 교체 가능하도록 `app/market_data/providers.py`의 `get_ohlcv`/`get_last_price` 시그니처를 유지했음. 계좌·주문 API는 사용하지 않고 시세 조회만 연결하면 된다.
- ⬜ 실계좌 잔고 자동조회(KIS Open API): 논의만 하고 보류함 - 지금은 `config/portfolio.yaml`에 수량/평단을 수동 입력하고 현재가만 실시간 조회하는 방식. 나중에 필요하면 KIS Developers에서 앱키 발급 후 붙이면 됨(주문 API는 여전히 안 씀).
- ✅ 뉴스 LLM 자동 해석: 대시보드 "새로고침" 버튼을 누르면 `app/news/fetcher.py`(구글 뉴스 RSS, 무료)로 최신 헤드라인을 다시 가져오고, `app/llm/gemini_opinion.py`가 Gemini(`gemini-3.6-flash`, 무료 티어, 그라운딩 도구는 결제 필요해서 안 씀)로 뉴스+지표를 해석해 `data/ai_opinion.yaml`을 갱신한다. `.env`에 `GEMINI_API_KEY` 필요 (Google AI Studio에서 무료 발급, 절대 커밋/공유 금지 - `.gitignore`에 `.env` 등록됨).

## 개인정보/보안

- `config/portfolio.yaml`(실제 보유 수량/평단/현금), `.env`(API 키), `data/`(시세·뉴스 캐시 및 AI 의견 - 보유종목을 추론할 수 있음), `logs/`는 전부 `.gitignore`에 등록돼 있어 커밋되지 않는다.
- 저장소에는 `config/portfolio.example.yaml` / `.env.example`만 올라간다. 처음 쓸 때 이걸 복사해서 실제 값을 채워 넣을 것 (위 빠른 시작 2번 참고).

## 알아둘 것

- `config/portfolio.yaml`을 실제 보유 수량/평단으로 바꾸지 않으면(예시 파일을 복사한 직후 상태) 비중 계산이 무의미하다.
- 급락(6장) 판정 6개 조건 중 "대부분의 종목이 동반 하락"은 개별 종목 시세만으로 계산할 수 없어 제외했다(5개 조건으로 판정). 여러 종목을 함께 스캔하는 기능을 추가하면 보강 가능.
- 데이터 신선도 검사(`app/market_data/validate.py`)는 무료 일봉 데이터 기준으로 "며칠 전 봉인지"를 본다. 실시간 체결가로 바꾸면 분 단위 검사(12장의 "30분 이상 지연")로 전환할 수 있게 파라미터를 분리해뒀다.
- 백테스트 기본 전략(`TrendFollowingATR`)은 13장의 "추세추종" 골격 + ATR 트레일링 예시일 뿐이다. 실사용 전에 반드시 `run_backtest.py`로 본인 종목에 대해 검증하고 파라미터(`config/strategy_rules.yaml`, `config/backtest.yaml`)를 조정할 것.
