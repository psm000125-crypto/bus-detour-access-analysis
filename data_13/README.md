# 약점 감사와 확대 지도 재계산

확인일: 2026-10-17, 한국시간. 공개자료만 사용했다. 기존 결과를 좋은 방향으로 유지하는 것이 아니라 입력·가정·결론을 함께 점검했다.

## 현재 분석 기준

주 결과는 `recompute_expanded.py` → `expanded_review_results.json`과 `review_*.csv`다. `audit_robustness.py`의 `robustness_results.json`은 확대 지도 확보 전 기존 추출본에서 수행한 400m·300m 보조 검토다. 두 결과를 합쳐 독립 검증 수를 늘리지 않는다.

```powershell
.venv_transport/Scripts/python.exe data_13/recompute_expanded.py
.venv_transport/Scripts/python.exe data_13/verify_review.py
.venv_transport/Scripts/python.exe -m unittest discover -s data_10 -p test_walk_analysis.py -v
.venv_transport/Scripts/python.exe -m unittest discover -s data_11 -p test_policy_models.py -v
.venv_transport/Scripts/python.exe -m unittest discover -s data_13 -p test_review_models.py -v
```

Python 3.12와 패키지는 `../data_10/requirements.txt` 기준이다. 새 패키지는 설치하지 않았다. 로컬 분석은 네트워크를 사용하지 않는다. `review_contract.json`에 질문·범위·결과 해석을 고정했다. 기존 분석 뒤의 사후 보완이며 사전등록 연구가 아니다.

## 원본 취득과 경계 보완

기존: bbox `(37.551,126.968,37.569,126.993)`, 노드 9,503개·way 1,730개. 기존 S 좌표와 경계의 최소 지도 거리는 약 429m여서 500m 원 전체를 포함하지 않았다.

확대: bbox `(37.545,126.958,37.578,127.003)`, 노드 26,902개·way 5,845개. 원응답 4,053,458바이트, 33,251개 요소다. S에서 경계까지 약 1,163m로 500m 원을 포함한다. 여기의 노드·way 수는 재귀 응답의 같은 ID를 합친 값이며 보행망의 노드·간선 수와 다르다.

- 제공 endpoint: https://maps.mail.ru/osm/tools/overpass/api/interpreter
- 제공 근거: OSM 공식 위키의 과거자료 지원 공개 인스턴스 목록 https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances
- 요청문: `raw/osm_medium_query.txt`, `[date:"2026-04-04T22:00:00Z"]`로 행사일 한국시간 07:00 기록 요청.
- 원본: `raw/osm_medium_windows_response.txt`, HTTP 헤더: `raw/osm_medium_windows_headers.txt`.
- 원본 SHA-256: `6f7e2e9e4af739a4133b708f2c15a60984277aabbcf827c8e0ffe58a827d7444`.
- 서버 `timestamp_osm_base=2026-10-17T07:45:21Z`는 서버 갱신 시각이며 요청한 과거 스냅숏 시각이 아니다.

실제 성공한 다운로드 명령:

```powershell
curl.exe --fail-with-body --silent --show-error --get --data-urlencode "data@data_13/raw/osm_medium_query.txt" --output data_13/raw/osm_medium_windows_response.txt --dump-header data_13/raw/osm_medium_windows_headers.txt --connect-timeout 15 --max-time 55 https://maps.mail.ru/osm/tools/overpass/api/interpreter
```

초기 Private.coffee 요청은 HTTP 500, main 요청은 혼잡에 따른 HTTP 502였다. Python의 VK 요청은 인증서 체인 검증에 실패했다. 인증서 검증을 끄지 않고 Windows 기본 신뢰 저장소를 사용하는 Schannel curl로 같은 요청을 성공했다. 실패 응답과 로그도 `raw/`에 보존했다.

한 단계 더 큰 bbox `(37.535,126.943,37.588,127.018)` 요청은 45초·90초 서버 처리 설정에서 모두 HTTP 504로 실패했다. `osm_large*_response.txt`는 오류 응답이며 지도 입력으로 사용하지 않는다. 더 큰 범위까지의 수렴을 검증했다고 표현하지 않는다.

기존·확대 추출본의 공통 way 1,730개는 노드열·태그가 같고 공통 노드 좌표도 같았다. 추가로 읽힌 일부 노드 태그 차이는 있으므로 두 원본 전체가 같다고 표현하지 않는다. 500m 안의 조건 충족 출입구 ID 집합은 같았다. 이는 확보한 두 스냅숏의 일치이며 실제 모든 출입구를 현장 전수조사한 결과는 아니다.

## 계산 보완

- 확대된 500m 선택: 노드 22개, 계산 가능 21개, 지도 연결 미해결 1개. 미해결은 현실의 불가능 판정이 아니다.
- 원본·확대 지도의 동일 후보 규칙 비교: 주요 선택과 수치 유지. 추가 2곳 최대 E 약 962m 대 649m, 최대 D 약 3,186m 대 3,186m.
- 대체 목표점 남북 ±20m 이동 후 동일 투영: 최대 E와 주요 선택 유지. 전체길이는 달라졌다. 실제 임시 대기 위치의 신뢰구간이 아니다.
- 400m·300m 출발 범위: 최대 E와 선택이 달라졌다. 분모와 출발점이 바뀌므로 정책 개선율처럼 비교하지 않는다.
- 인지 민감도: 두 안내를 각각 독립적으로 읽을 확률 p의 모든 읽음/못 읽음 조합을 계산했다. 실제 p와 독립성은 관측하지 않았다. ‘여정별 기대 E의 최댓값’이며 실제 최대 부담이나 최대값의 기댓값이 아니다.
- `policy_engine.py`는 최단거리와 고정 접근경로를 캐시한다. 선택된 실제 주 분석 여정은 기존 명시적 최단경로 함수와 대조해 결과가 같은지 확인한다. 캐시를 지리적 사실 보완으로 제시하지 않는다.

명시 보행선만 사용하면 확대 후에도 22개 출입구에서 공동 비교를 위한 경로가 계산되지 않았다. 일반도로 보행 가정 모형의 21개 직접 경로 중 가정 선형 비율은 약 80~100%다. **지도를 넓힌 것과 보행 연결을 검증한 것은 다르다.**

## 출력 해석

| 파일 | 내용 |
|---|---|
| `review_origin_selection.csv` | 확대 지도에서 선택한 출입구 ID·원본 태그·거리 |
| `review_policy_summary.csv` | 범위·대체점·안내 수량별 정책 요약 |
| `review_journeys.csv` | 미해결을 포함한 여정별 계산 결과 |
| `review_distribution.csv` | 같은 수량의 여정 수 기준 대비 손익 |
| `review_fixed_policies.csv` | 주 분석의 추가 2곳 후보를 고정한 조건 변화 |
| `review_recognition.csv` / `review_recognition_journeys.csv` | 가정한 인지확률별 기대 지표와 여정별 값 |
| `review_route_assumptions.csv` | 직접 경로의 일반도로 가정 비율·계단·투영 간격 |
| `expanded_review_results.json` | 원본 대조·경계·시나리오·고립 성분·입력 해시 |
| `expanded_review.png` | 주 비교와 인지 민감도 |
| `verification_review.json` | 정합성·입력 무결성 검증 결과 |

계산 가능 부분집합의 최대값만 제공하며 전체 출입구 최대값은 결측으로 보존한다. 실제 승객·사회집단·보행허용거리·대기·요금·시간·자동차 전환·탄소 감축은 계산하지 않았다. 안내 후보는 실제 게시 승인을 받은 장소가 아니다.

## AI·출처

실제 이번 사용자 지시: “약점 보완 하자. 그리고 전체적으로 돌아보면서 공모전의 취지에 맞게 내용들 수정 및 보완하면 될듯?” Codex를 공개자료 요청·원본 대조·코드·분석·그림·문서 검토에 사용했다. 이미지 원문도 다시 읽었으나 AI 재검토이며 사람의 독립 검수가 아니다. 테스트 기대값을 계산할 때 S→A의 더 짧은 우회 경로를 빠뜨린 사례를 수정했다. 계산 엔진은 그대로였고 잘못된 테스트의 기대값을 13.75m에서 10m로 고쳤다.

스킬은 NetworkX·GeoPandas·Scientific Critical Thinking을 계속 적용했다. 출처 논문을 보고서 참고문헌에 유지했다: Kassis et al. (2026), *Scientific Agent Skills*, https://doi.org/10.48550/arXiv.2609.00065 . 이는 도구 출처이며 교통 효과 근거가 아니다. OSM 데이터 및 파생 지도: © OpenStreetMap contributors, ODbL 1.0.
