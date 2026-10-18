# 버스 임시우회 안내의 접근 부담 분석 코드

공모전 분석보고서의 공개자료 감사·조건부 정책 비교 재현 자료입니다.
현재 보고서의 공간·정책·접근성 주 분석은 data_29/reanalyze_platforms.py입니다.
버스 승객용 선형 승강장을 포함하여 9-1출구 연결과 기존 승차지 위치를 수정한 22개 출발점 모형입니다.
data_13·14·17·28은 이전 21개 모형의 보존 결과이며 현재 본문과 수치를 섞으면 안 됩니다.
data_10·data_11 모듈은 필요한 공통 함수와 초기 모형 테스트를 제공합니다.

## 실행 환경과 실행

검증 환경은 Windows, Python 3.12입니다. Windows 기본 맑은 고딕을 그림에 사용합니다.
다른 운영체제에서는 한글 폰트를 준비해야 그림의 한글이 정상 표시됩니다.
숫자 계산과 지리적 사실 검증은 구분합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run_analysis.py
```

패키지 설치에는 인터넷이 필요합니다. 이후 주 분석·검증은 동봉한 원본만 사용하며
새 지도 취득·로그인·API 키·유료 AI 서비스가 필요하지 않습니다.
의존 패키지는 requirements.txt에 고정했습니다. 가상환경 자체는 동봉하지 않았습니다.

run_analysis.py는 이전 모형의 보존 검증, data_29의 최신 22개 출발점 분석과 독립 조합 열거·88행 직접 경로 검산,
검토서 초안 생성과 모형 테스트 39개를 실행합니다.
설치가 끝난 기존 Python 3.12 환경에서는 바로 `python run_analysis.py`로 실행할 수 있습니다.
최신 주 결과는 출입구 22개·계산 가능 22개·후보 50개·2곳 조합 1,225개입니다.
같은 추가 2곳에서 최대 추가보행은 도달 경로 수 우선 1,392.793m, 최댓값 최소 1,007.157m입니다.
후자는 전자보다 11개 경로가 짧고 11개는 깁니다. 수량별 위치를 다시 고르는 비교이며 실제 승객 효과가 아닙니다.

## 확인할 파일

- data_13/review_policy_summary.csv: 범위·대체점·수량별 정책 지표
- data_13/review_journeys.csv: 미해결 행을 포함한 여정별 결과
- data_13/review_distribution.csv: 같은 수량 대조군 대비 손익
- data_13/review_recognition*.csv: 가정 인지확률별 기대 지표
- data_13/expanded_review_results.json: 원본 대조·고립 성분·입력 해시
- data_13/verification_review.json: 계산 정합성 검증
- data_13/README.md: 원본 취득·실패·한계·요청 시점과 서버 갱신 시점의 구분
- data_14/README.md: B·L·E 분해, 안내 한계효과, 국소적 경로·인지 의존성의 계산과 한계
- data_14/decision_results.json 및 *.csv: 새 분석 결과
- data_14/verification_decisions.json: 이전 독립 인지 20개 값·분해 항등식·경로 정합성 검증
- data_17/README.md: 위치 변경·보행속도·거리값·탄소 입력 가정과 해석 범위
- data_17/*.csv 및 access_results.json: 접근 목표·보행 부담·H1000 거리 가산성과 국내 지침·가정 연비를 결합한 대상 여정당 CO2
- data_17/ai_source_recheck.csv: AI의 동일 원문 ID 재대조 기록. 사람 검수 정확도가 아님
- data_28/README.md 및 accessibility_results.json: 고정 출입구에서 계단·휠체어 제한을 반영한 지도 점검과 결측
- data_28/review_drafts.json 및 검토서_초안.md: 기존 AI 전사 2건에서 생성한 검토 초안. 새 모델 호출·독립 정확도 평가가 아님
- data_29/README.md 및 results.json: 현재 22개 출발점 모형·승객용 승강장 포함 규칙·정책 비교·접근성
- data_29/peer_policy_verification.json: 1,225개 조합의 별도 열거와 88행 직접 최단경로 평가 대조
- data_30/README.md: OSM 휠체어 접근 항목의 원본 재집계, 별도 AI 성능 평가 절차와 빈 기록 양식
- data_31/README.md: 권고 규칙·공식 시설 교차 확인·공지 5건 25항목의 별도 에이전트 대조·탄소 계산 예시
- data_31/verify_revision_evidence.py: 새 AI 호출 없이 보존된 대조표·정책 손익·탄소 가정 검산
- data_33/README.md 및 verify_policy_choice.py: 최대 추가보행 최소 최종 권고·대조 기준별 경로 손익·검산. data_31 정책 선택은 수정31 당시 기록
- data_34/README.md 및 verify_baselines.py: 추가 안내 도달11개와 기존정류소안내대비11개개선·11개동일·0개악화, 세 비교 기준 검산
- BUNDLE_MANIFEST.json: 이 압축파일에 포함한 파일과 SHA-256
- SOURCE_NOTICE.md: 데이터·스킬 출처와 이용 조건

## 제출 링크 연결

이 ZIP은 개인 재현용 자료이며 예선 공식 필수·허용 첨부로 확인된 것은 아닙니다.

압축을 풀고 디렉터리 구조를 유지해 GitHub 또는 클라우드 폴더에 올린 뒤,
심사자가 열람할 수 있는 링크를 보고서의 코드 열람 링크 칸에 넣습니다.
GitHub에는 ZIP만 올리기보다 소스 파일을 폴더 구조대로 올려 웹에서 읽을 수 있게 합니다.
연결 후 별도 브라우저에서 권한과 파일 열람을 확인합니다. 링크 생성·공개 범위 결정은 참가팀이 합니다.

## 해석과 포함 범위

일반도로 보행·지도 대체점·고정 접근 경로를 가정한 모형입니다.
실제 보도·횡단·행사 통제·역사적 임시 대기 위치·수요·인지율은 미확인입니다.
모형 테스트가 실제 보행이나 정책 효과를 인증하지 않습니다.
명시 보행선만의 모형은 확대 지도에서도 공동 비교 경로가 부족했습니다.

공식 안내와 AI 활용 기록은 근거 설명을 위해 포함합니다. 기록에 등장하는 모든 과거 작업 파일을
동봉한 것은 아닙니다. 사적 브라우저 정보·신청자 개인정보·가상환경·지도 서비스 화면 캡처는 없습니다.
공지 이미지와 민간 위치도는 공개 재배포 묶음에 복제하지 않고 원문 URL로 안내합니다.
추가 광진구 통제도와 공항리무진 공지 원본도 로컬 확인용으로만 보존하며 ZIP에는 포함하지 않습니다.
추가 자료의 사실 전사·시점·상충 표기는 data_14/source_review.json에 있습니다.
원본 출처의 정규·임시 승차를 구분한 사실 전사는 data_09/service_changes.json에 있습니다.
data_10/analyze_walks.py의 초기 파이프라인 전체를 실행하는 묶음이 아니라 현재 분석을 재현하는 묶음입니다.
