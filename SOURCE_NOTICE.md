# 데이터와 도구 출처

분석 코드는 이 프로젝트에서 AI 보조로 작성했습니다. 코드의 공개 배포 라이선스는 참가팀이 결정합니다.
아래 원자료의 이용 조건은 이 코드에 대한 권리와 별개로 보존합니다.

## OpenStreetMap

동봉한 OSM 원응답과 파생 공간자료: © OpenStreetMap contributors, Open Database License 1.0.
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/
원응답의 저작권 안내와 요청문·기준시점·해시를 유지합니다.
원본·확대 추출본의 제공 서버는 data_13/README.md에 기록했습니다.

## 서울시 정류소 위치정보

제공기관: 서울특별시. 플랫폼: 서울 열린데이터광장 OA-15067.
https://data.seoul.go.kr/dataList/OA-15067/A/1/datasetView.do
원본 페이지의 이용허락은 공공누리 제1유형 출처표시입니다.
동봉한 selected_stops_20260402.csv는 20260402 파일의 선택 ID 6개 행입니다.
원자료의 좌표 설명 충돌은 원본을 변경하지 않고 조건으로 기록했습니다.

## 우회 계획과 기관 위치

수원시 공식 우회 공지의 노선·시각·정류소·승차 유형 사실 전사:
https://www.suwon.go.kr/web/board/BD_board.view.do?bbsCd=1042&seq=20260402100206435
CPBC 공식 기관 위치:
https://web.cpbc.co.kr/company/page/page1-8.html
광진구 같은 행사 공지·통제도(표시 등록일 2026-04-06, 행사 전 가용성 미확인):
https://gwangjin.go.kr/portal/bbs/B0000001/view.do?deptId=100161&menuNo=200190&nttId=6570763&pSiteId=portal&pageIndex=1
한국공항리무진 같은 행사 우회 공지:
https://www.klimousine.com/center/notice_view.php?code=&idx=6393&page=1&ptype=view
공지 이미지·민간 위치도·카카오맵 화면은 이 공개용 묶음에 포함하지 않았습니다.

## 탄소 입력의 참고 계수

환경정보공개시스템, 2024년 환경정보공개제도 등록 가이드라인(2024.4.), 인쇄면 156~157쪽.
https://env-info.kr/v2/publish/testfiles/2024년%20환경정보공개제도%20등록%20가이드라인.pdf
확인 2026-10-17. 휘발유 순발열량 30.4MJ/L와 CO2 계수 69,300kg/TJ를 사용했습니다.
연비 10·15·20km/L는 입력 가정입니다. 국내 운행차량 실측 평균·전 과정 온실가스·정책 순감축량이 아닙니다.
CO2 성분만 산정하고 다른 온실가스는 제외합니다. 회피 전환율·거리는 관측값이 아닌 입력 가정입니다.
원문 전체는 묶음에 재배포하지 않으며 수치·출처·계산 가정을 보존합니다. data_17/README.md 참조.

## 스킬과 AI

적용 스킬: NetworkX, GeoPandas, Scientific Critical Thinking.
Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents.
https://doi.org/10.48550/arXiv.2609.00065
스킬 파일·외부 예제 코드·설치한 패키지와 가상환경은 동봉하지 않았습니다.
활용 기록을 포함하되 AI 재검토를 사람의 독립 검수로 표시하지 않습니다.
