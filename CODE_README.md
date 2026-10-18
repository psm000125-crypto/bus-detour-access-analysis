# 분석 코드 실행 안내

이 저장소는 보고서의 **22개 출발점 모형**을 재현합니다. 입력과 결과는 `data/`, 계산 코드는 `analysis/`, 단위 테스트는 `tests/`에 모았습니다.

## 실행 환경

Python 3.12와 `requirements.txt`의 고정 버전을 사용합니다. 가상환경을 만드는 Windows 실행 예시는 다음과 같습니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run_analysis.py
```

의존성 설치에는 인터넷 연결이 필요합니다. 이후 분석은 동봉 입력자료만 읽으며 로그인·API 키·AI 서비스 호출이 필요하지 않습니다. 실행 시 `data/results/`의 계산 결과를 갱신합니다. 보고서 그림은 `assets/`에서 확인할 수 있습니다.

## 실행 순서

`run_analysis.py`는 아래 작업을 차례로 실행하고 실패 시 중단합니다.

| 순서 | 모듈 | 내용 |
|---|---|---|
| 1 | `analysis.model` | 보행망 구성, 22개 출발점·50개 후보의 정책 비교와 접근 제한 점검 |
| 2 | `analysis.verify_routes` | 1,225개 조합의 별도 열거, 네 정책 88행의 직접 최단경로 대조 |
| 3 | `analysis.verify_policy` | 최종 권고안과 다른 배치의 최대·합계·경로별 손익 검산 |
| 4 | `analysis.verify_baselines` | 기존 안내·도달수 우선·합계 최소의 세 비교 기준 검산 |
| 5 | `analysis.verify_sources` | TOPIS 공지 25개 항목의 추출 대조와 탄소 산술 예시 확인 |
| 6 | `tests/` | 투영·접근 제한·안내 순서·정책 선택·승강장 연결의 단위 테스트 |

개별 모듈도 저장소 루트에서 실행할 수 있습니다.

```powershell
python -m analysis.model
python -m analysis.verify_routes
python -m unittest discover -s tests -v
```

## 주요 결과 파일

| `data/results/` 파일 | 내용 |
|---|---|
| `policy_summary.csv` | 네 정책의 최대·합계·평균 거리와 안내 도달 경로 수 |
| `journeys.csv` | 네 정책 × 22개 출발점의 거리·안내 만남·개선량 |
| `budget.csv` | 안내 0·1·2곳에서 위치를 다시 선택한 비교 |
| `baseline_differences.csv` | 세 비교 기준별 출발점의 개선·동일·악화 |
| `accessibility.csv` | 계단·명시된 접근 제한을 제외한 지도상 경로 결과 |
| `location_sensitivity.csv` | 지도상 승차 지점 변경의 보조 시나리오 |
| `results.json` | 선정 위치·정책 지표·접근성 요약·원자료 해시 |
| `peer_policy_verification.json` | 별도 조합 열거 및 직접 경로 계산의 대조 결과 |
| `policy_choice.json`, `baseline_results.json` | 최종 권고와 비교 기준의 검산 결과 |
| `ai_evaluation.json`, `carbon_example.json` | 공지 추출 대조와 가정에 따른 CO2 계산 예시 |

거리 단위는 m입니다. `D_known_m`은 미리 대체 지점을 알고 이동하는 거리, `D_stop_m`은 기존 정류소에서 처음 안내를 받는 거리, `D_policy_m`은 선택한 안내를 적용한 거리입니다. `E_policy_m = D_policy_m - D_known_m`으로 추가보행을 계산합니다. `B_m`은 평소 정류소 접근거리, `L_m`은 승차지 변경으로 늘어난 거리이며 `D_policy_m = B_m + L_m + E_policy_m`입니다.

`BUNDLE_MANIFEST.json`은 배포 시 파일별 SHA-256을 기록합니다. 실행에 따라 결과 파일을 재저장하면 직렬화 방식 등에 따라 파일 해시가 달라질 수 있으므로, 수치와 배포 파일의 동일성은 구분해 확인합니다.
