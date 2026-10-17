# crypto-alert (코인 차트 알림)

업비트 + 바이낸스 + OKX 시세를 분석해 **팝업/사운드 + 텔레그램**으로 알려주는 Windows용 프로그램.

## 확정된 요구사항 (사용자와 합의)

- **거래소:** 업비트, 바이낸스, OKX (3곳) — 공통 인터페이스로 통합, 추가 거래소 확장 가능
- **감시 코인:** `src/crypto_alert/watchlist.json` 파일로 관리 (파일 편집 또는 `config.add_symbol()`/`remove_symbol()`로 추가·삭제)
  - 업비트 원화마켓 26종목 / 바이낸스 현물 7종목 / OKX 현물 1종목(PI/USDT)
  - ※ DRIFT·MOCA·ZETA는 바이낸스 현물 미상장(선물 전용)이라 제외 결정 (2단계 합의)
  - ※ PI는 업비트·바이낸스 미상장이라 OKX 연동으로 추가 (OKX 현물 PI-USDT 실측 확인)
- **알림 조건:** 가격 돌파 + 기본 지표 신호(골든크로스 등), 이후 조건을 무한 확장 가능한 구조
- **자동매매:** 이번 버전은 알림만 (매매는 이후 확장 가능하도록 인터페이스 분리)
- **화면 구성:** 상단 메뉴(파일: 캡처·닫기 / 보기: 종목·시가총액) + 탭 3종 — 첫 화면은 차트+알림(조건/이력 절반), 종목(보유종목 입력), 시가총액 순위

## 개발 단계

1. 개발 환경 만들기 ✅
2. 시세 데이터 수신 ✅ — 업비트/바이낸스 REST + WebSocket 실시간 스트림
3. 캔들차트 렌더링 ✅ — 4패널 화면 + pyqtgraph 캔들/거래량 + 시간봉 전환 + 실시간 갱신
4. 보조지표 (MA, RSI, MACD, 볼린저밴드) ✅ — 순수 계산 모듈 + 캔들 오버레이/서브패널 토글
5. 알림 조건 설정 UI ✅ — 규칙 등록/감지 엔진 (발송은 6단계)
6. 알림 발송 (팝업 + 사운드 + 텔레그램) ✅ — 채널별 on/off + 봇 토큰 설정
7. Windows exe 패키징 (PyInstaller) ✅ — `dist/crypto-alert.exe` 단일 파일 (66MB)
8. pytest 테스트 ✅ — 커버리지 99% 유지하며 지속 보강
9. UI 개편 + 차트 사양 변경 ✅ — 탭/메뉴 구조 + 캔들 200 + 주기별 MA + BB 중심선 점선

### 9단계 상세 (완료)

- **탭/메뉴 (`ui/main_window.py`):** 상단에 `파일`(캡처·닫기)·`보기`(종목·시가총액) 메뉴 + 탭 3종(차트알림/종목/시가총액). 첫 화면은 차트+알림 탭이며 차트와 (알림 조건·이력)이 좌우 절반. 보기 메뉴 항목과 탭 선택은 동일 기능(현재 탭에 맞춰 체크 표시)
- **캡처 (`MainWindow.capture_chart`):** 파일 > 캡처로 차트 패널만 PNG 저장 (기본 파일명 `chart_종목_주기_시각.png`, 저장 다이얼로그 취소는 무시)
- **캔들 200개:** 엔진은 이미 200개 요청. OKX는 1회 100개 제한이라 `after`(과거 방향) 페이지네이션으로 요청 개수까지 보충 (`exchanges/okx.py`, 최대 10페이지)
- **주기별 MA (`ui/chart_panel.py`):** 15분=MA 8/96/192, 4시간=MA 6/42/168, 일/주/월=MA 60/120/200 (`MA_PERIODS_BY_INTERVAL`). 주기 전환 시 이전 주기 MA선은 자동 분리, MA 버튼 툴팁도 현재 주기 기간을 표시. 색상은 주기 내 짧은/중간/긴 순 고정(주황/파랑/보라)
- **BB 중심선:** 상·하단과 같은 점선으로 중앙선(20일 SMA)도 표시
- **검증:** pytest 196건 통과 · ruff 통과 · 실거래 GUI 캡처(15m·4h·OKX PI 모두 캔들 200개, MA 교체, BB 점선 확인) · exe 재빌드 후 `--smoke` + 실구동 확인

### 8단계 상세 (완료)

- **결과:** pytest 196건 전부 통과, 라인 커버리지 99% (진입점 `main.py` GUI 실행부 9줄 제외 시 100%). 네트워크를 쓰는 코드는 스텁/모의로 대체해 외부 API 없이 13초에 끝난다
- **보강 내용:** 거래소 REST/웹소켓(재연결·백오프 포함), 데이터 엔진 스레드 수명주기, 메인윈도우 라우팅·에러 분기, 다이얼로그 검증 분기, 차트 렌더·범위 엣지, 포맷터 전 분기, 손상 파일·잘못된 입력 등 실패 경로
- **워크플로우:** `pytest-cov`를 dev 의존성에 추가. 평소 `pytest`, 병합 전 `pytest --cov=src/crypto_alert` + `ruff check src tests` + `ruff format --check src tests`
- **커버리지 제외:** `main.py` GUI 진입점 본문(별도 프로세스 `--smoke` 테스트 + exe 실구동 캡처로 검증, 6~7단계), `if __name__ == "__main__"` 블록

### 7단계 상세 (완료)

- **빌드:** `crypto-alert.spec` + `python -m PyInstaller crypto-alert.spec --noconfirm` → `dist/crypto-alert.exe` 단일 파일 (66MB, 콘솔 창 없음). 재빌드 시 같은 명령 그대로 실행
- **frozen 대응 (`paths.py`):** 사용자 수정 JSON 4종(watchlist/holdings/alert_rules/notify_settings)은 exe 옆 폴더에 읽기·쓰기, 읽기 전용 supplies.json은 exe에 번들(_MEIPASS). exe 옆 동명 파일이 있으면 우선 사용(supplies 덮어쓰기 가능)
- **검증:** `crypto-alert.exe --smoke`로 번들 실행 확인 (watchlist 33종목·supplies 26개 로드), 실GUI 60초 구동 후 데스크톱 캡처로 차트·실시간 수신 정상 확인. 첫 실행 시 exe 옆에 `watchlist.json` 자동 생성됨
- **유의:** onefile 방식이라 실행마다 임시 압축 해제(약 수초), 쓰기 가능 폴더에 exe를 둘 것. SmartScreen 경고 시 "추가 정보 → 실행"

### 6단계 상세 (완료)

- **발송기 (`alerts/notify.py`):** `Notifier.dispatch(event)` 한 줄로 팝업 + 사운드 + 텔레그램 발송. 팝업은 우하단 토스트(6초 자동 닫힘·포커스 탈취 없음), 사운드는 Windows 비프, 텔레그램은 Bot API를 별도 스레드로 전송해 시세 처리가 멈추지 않는다. 발송 실패는 예외 대신 신호(상태표시줄)로만 전달
- **발송 설정:** 알림 패널의 "발송 설정" 버튼 → 채널별 on/off + 봇 토큰/챗ID 입력 + "테스트 발송" 버튼 (결과 팝업). `notify_settings.json` 자동 저장, 토큰은 로그에 남기지 않는다
- **텔레그램 준비물:** `@BotFather` → `/newbot` → 토큰 발급, 봇에게 1통 전송 후 `https://api.telegram.org/bot<토큰>/getUpdates` 에서 `chat.id` 확인
- **테스트:** `Notifier.set_test_hook` 으로 네트워크 없이 채널별 발송 검증 (pytest 11건)

### 5단계 상세 (완료)

- **조건 10종 (`alerts/conditions.py`):** 가격 ≥/≤ 목표가, 골든/데드크로스, RSI 과매수/과매도, MACD 상향/하향, BB 상단/하단 돌파. 새 조건은 `CONDITIONS`에 Spec 한 줄 등록으로 끝나고 다이얼로그·저장·감지가 그대로 따라온다
- **규칙 UI:** 알림 패널 상단에 조건 목록 + 추가/수정/삭제/켜기·끄기, 추가·수정은 다이얼로그 (거래소/종목/주기/조건 선택, 파라미터 칸 자동 생성, 재알림 간격). `alert_rules.json` 자동 저장
- **감지 엔진 (`alerts/engine.py`):** 가격 조건은 실시간 티커로, 지표 조건은 캔들(60초 주기 자동 조회 + 차트 캔들 재사용)로 평가. 거짓→참 전환 순간 1회 발동 + 쿨다운으로 반복 울림 방지
- **6단계 연결점:** 발동 결과(`AlertEvent`)는 `MainWindow._dispatch_alert` 하나로 모이므로 발송기(팝업/사운드/텔레그램)는 여기만 확장하면 된다

### 4단계 상세 (완료)

- **지표 계산 (`indicators.py`):** UI와 분리된 순수 함수 — MA, 볼린저밴드(20, 2σ, 모집단 ddof=0), RSI(14, Wilder), MACD(12/26/9). 웜업 구간은 NaN으로 채우고 `cross_over`/`cross_under`(골든크로스 등 신호 판정용) 포함 → 5단계 알림 조건에서 그대로 재사용
- **표시 방식:** MA·볼린저는 캔들 위 오버레이, RSI·MACD는 하단 서브패널. 툴바의 `지표: MA / BB / RSI / MACD` 버튼으로 각각 독립 토글 — 새 지표 추가는 `INDICATORS` 목록에 한 줄 추가로 끝나는 구조
- **서브패널 레이아웃:** GraphicsLayout에 동적 add/remove (행 0=캔들, 1=거래량, 2=RSI, 3=MACD). 거래량 110px · 서브패널 100px 높이 제한으로 캔들 차트가 나머지 전체를 차지
- **축·범위:** RSI는 0~100 고정(30/70 가이드선), MACD는 데이터에 자동 맞추되 실시간에는 바깥으로만 확장(사용자 확대·축소 유지), 오버레이 포함 y범위 자동 설정, X축은 전 플롯 동기화, 시간축 라벨은 최하단 플롯에만 표시
- **파라미터:** `IndicatorParams`(frozen dataclass) + `DEFAULT_PARAMS`로 감싸 두어 이후 설정 UI에서 교체 가능

### 3단계 상세 (완료)

- **4패널 화면:** 차트(좌) / 알림(우상) / 시가총액 순위(우하) / 보유종목(하단)
- **시간봉 전환:** 15분 · 4시간 · 1일 · 1주 · 1월 (업비트는 주/월봉을 N일 캔들 unit=7/30으로 근사, 바이낸스는 `1w`/`1M` 네이티브)
- **캔들차트:** pyqtgraph + QPicture 렌더링, 위쪽 캔들(+ 거래량), 업비트 관행 색상(상승 빨강/하락 파랑), 마우스 확대/축소·이동
- **실시간 갱신:** WebSocket 틱으로 마지막 캔들의 시고저종 갱신 (250ms 스로틀), 구간 경계 넘김 시 재조회 (10초 폭주 방지)
- **시가총액 순위 자체 계산:** `supplies.json`의 유통공급량 × 현재가 (외부 API·키 불필요, 파일 직접 편집 가능). 바이낸스 USDT가를 우선 USD로 쓰고 업비트 KRW가는 업비트 KRW-USDT 환율(USD/KRW)로 환산. BTTC↔BTT 동일 자산 취급
- **보유종목:** 종목/수량/평균단가 수동 입력 → `holdings.json` 자동 저장, 현재가 수신 시 평가금액·손익 자동 갱신

## 거래소 추가 방법 (OKX 추가 사례)

새 거래소는 `ExchangeClient` 인터페이스만 구현하면 차트·알림·시총이 그대로 따라온다:

1. `exchanges/<새거래소>.py` — REST 캔들/시세 + WS 구독·파싱 구현 (OKX 파일이 템플릿)
2. `exchanges/symbols.py` — `normalize_symbol` 분기 + API 표기 변환 2종
3. `config.py` — `EXCHANGES`에 키 추가 + 기본 감시 종목
4. `engine.py` — `_clients`에 등록 1줄
5. UI 콤보 2곳 (`chart_panel.py`, `alert_rule_dialog.py`의 거래소 목록) + 상태바 라벨
6. 심볼→거래소 판별이 필요한 곳은 감시 목록 조회 우선 (접미사 추정은 폴백 유지)

## 개발 명령

```powershell
# 가상환경 생성 (최초 1회)
py -m venv .venv

# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# 의존성 설치 (editable 모드)
pip install -e ".[dev]"

# 프로그램 실행 (GUI)
python -m crypto_alert.main

# 2단계 시세 수신 확인 CLI (스냅샷 → 캔들 → 실시간 스트림)
python -m crypto_alert.watch --duration 30

# 테스트
pytest

# 테스트 + 커버리지 (병합 전)
pytest --cov=src/crypto_alert
```

## 프로젝트 구조

```
opencodetool/
├── pyproject.toml          # 의존성 / 빌드 설정
├── ruff.toml               # 코드 스타일 (줄 길이 100)
├── crypto-alert.spec       # PyInstaller 빌드 설정 (--onefile, 7단계)
├── dist/
│   └── crypto-alert.exe    # 배포용 단일 실행 파일 (7단계 결과물)
├── src/
│   └── crypto_alert/
│       ├── __init__.py
│       ├── main.py           # GUI 진입점
│       ├── config.py         # 감시 코인 목록 (추가/삭제 가능)
│       ├── watchlist.json    # 감시 코인 목록 파일 (직접 편집 가능)
│       ├── engine.py         # 데이터 엔진 (asyncio 루프 + Qt 시그널)
│       ├── buckets.py        # 캔들 구간 계산 (15m/4h/1d/1w/1M 경계)
│       ├── marketcap.py      # 시가총액 순위 자체 계산
│       ├── supplies.json     # 유통공급량 표 (시총 계산용, 직접 편집 가능)
│       ├── holdings.py       # 보유종목 저장/평가
│       ├── formatting.py     # 가격/등락률/시총 포맷
│       ├── indicators.py     # 보조지표 순수 계산 (MA/BB/RSI/MACD, 5단계에서 재사용)
│       ├── paths.py          # exe 대응 경로 해결 (exe 옆 JSON ↔ 번들 리소스, 7단계)
│       ├── alert_rules.json  # 알림 규칙 저장 파일 (UI에서 자동 저장, 직접 편집 가능)
│       ├── watch.py          # 2단계 시세 수신 검증 CLI (+ exe 검증용 --smoke는 main.py)
│       ├── alerts/
│       │   ├── conditions.py   # 알림 조건 10종 레지스트리 (가격/지표 신호)
│       │   ├── rules.py        # 규칙 데이터 모델 + 검증
│       │   ├── store.py        # 규칙 JSON 저장/불러오기
│       │   ├── engine.py       # 감지 엔진 (전환 발동 + 쿨다운)
│       │   ├── notify.py       # 발송기 (팝업/사운드/텔레그램, 6단계)
│       │   └── notify_settings.py # 발송 설정 저장/불러오기 (6단계)
│       ├── ui/
│       │   ├── main_window.py    # 탭/메뉴(캡처·닫기·탭 전환) + 엔진 연동
│       │   ├── chart_panel.py    # 캔들/거래량 차트 + 주기 전환 + 주기별 MA/BB 오버레이
│       │   ├── alert_panel.py    # 알림 조건 목록 + 발동 이력
│       │   ├── alert_rule_dialog.py # 규칙 추가/수정 다이얼로그
│       │   ├── alert_toast.py    # 발동 토스트 팝업 (6단계)
│       │   ├── notify_dialog.py  # 발송 설정 다이얼로그 (6단계)
│       │   ├── marketcap_panel.py# 시가총액 순위표
│       │   └── holdings_panel.py # 보유종목 수동 입력표
│       └── exchanges/
│           ├── base.py       # 거래소 공통 인터페이스 (Candle/Ticker/Interval)
│           ├── symbols.py    # 심볼 표기 변환 (BTC ↔ KRW-BTC ↔ BTC/USDT ↔ PI-USDT)
│           ├── upbit.py      # 업비트 REST + WebSocket
│           ├── binance.py    # 바이낸스 REST + WebSocket
│           └── okx.py        # OKX REST + WebSocket (PI 현물용)
└── tests/
    ├── conftest.py           # QApplication 공용 fixture (offscreen)
    ├── test_smoke.py
    ├── test_main.py          # 진입점 --smoke (별도 프로세스) + GUI 배선 테스트
    ├── test_data_engine.py   # 데이터 엔진 수명주기 + 요청 처리 테스트 (8단계)
    ├── test_watch_cli.py     # watch 검증 CLI 테스트 (8단계)
    ├── test_formatting.py    # 화면 포맷터 테스트 (8단계)
    ├── test_config.py        # 심볼 변환 + 코인 목록 테스트
    ├── test_exchanges.py     # 거래소 응답 파싱 + fetch/스트림 스텁 테스트
    ├── test_okx.py           # OKX 파싱 + fetch/WS 테스트 (PI 실측 픽스처)
    ├── test_buckets.py       # 캔들 구간 경계 테스트
    ├── test_market_holdings.py # 시총 계산 + 보유종목 평가 테스트
    ├── test_indicators.py     # 보조지표 계산값 검증 (Wilder RSI / 모집단σ / MACD 웜업)
    ├── test_alerts.py         # 알림 조건 평가 + 감지 엔진 + 규칙 저장 + 규칙 UI 테스트
    ├── test_notify.py         # 발송 설정 + 발송기 채널 + 설정 UI 테스트 (6단계)
    ├── test_paths.py          # exe 대응 경로 해결 테스트 (7단계)
    └── test_ui.py            # 패널 생성/동작 테스트 (offscreen)
```
