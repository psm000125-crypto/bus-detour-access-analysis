# 데이터 출처와 이용 조건

## OpenStreetMap

도로·출입구·건물·승강장 자료: **© OpenStreetMap contributors**, Open Database License 1.0.

- [OpenStreetMap 저작권 안내](https://www.openstreetmap.org/copyright)
- [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
- 제공 서버: `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
- 보존 위치: `data/raw/`. 요청문·원응답·확대 추출본 HTTP 헤더와 원자료의 저작권 안내를 유지했습니다.

과거 지도 요청 시점과 제공 서버 갱신 시각의 구분은 [자료 안내](data/README.md)에 설명했습니다.

## 서울시 정류소 위치정보

제공기관은 서울특별시, 제공 플랫폼은 서울 열린데이터광장입니다. [서울시 버스정류소 위치정보 OA-15067](https://data.seoul.go.kr/dataList/OA-15067/A/1/datasetView.do)의 20260402 파일에서 선택한 정류소 6개 행을 `data/stops.csv`에 수록했습니다. 원자료의 이용허락은 공공누리 제1유형 출처표시입니다. 원문 좌표 설명의 WGS84·EPSG-5179 표기 충돌은 `data/settings.json`에 기록했습니다.

## 우회 공지와 위치 확인

- [수원시 공식 우회 공지](https://www.suwon.go.kr/web/board/BD_board.view.do?bbsCd=1042&seq=20260402100206435): 8800·M5107의 우회 시간·정류소·승차 위치. 사실 전사는 `data/service_changes.json`에 수록했습니다.
- [CPBC 공식 기관 위치](https://web.cpbc.co.kr/company/page/page1-8.html): 지도 대체점의 건물 식별.
- [광진구 행사 공지](https://gwangjin.go.kr/portal/bbs/B0000001/view.do?deptId=100161&menuNo=200190&nttId=6570763&pSiteId=portal&pageIndex=1): 같은 행사 통제 정보. 표시 등록일은 2026-04-06으로 행사 전 가용성은 확인되지 않았습니다.
- [한국공항리무진 우회 공지](https://www.klimousine.com/center/notice_view.php?code=&idx=6393&page=1&ptype=view): 같은 행사 우회 정보.
- [서울시 TOPIS 공지](https://topis.seoul.go.kr/notice/openNoticeList.do): 게시물 6237·6236·6228·6225·6223의 본문·제목 추출 대조. 선정 규칙·원문 전사·대조값은 `data/ai_notice_extraction.json`에 수록했습니다.

공식 공지 이미지·민간 위치도·카카오맵 화면은 이 저장소에 복제하지 않았습니다.

## 접근시설

[GTX-A 서울역 이용 안내](https://www.gtx-a.com/noticeDetail.do?boardId=177)와 [공항철도 서울역 시설 안내](https://www.airportrailroad.com/train/normal/info/010/0)를 참고했습니다. 원문별 확인 내용과 지도상 출입구의 대응 범위는 `data/facility_sources.json`에 기록했습니다.

## 탄소 계산의 참고 계수

환경정보공개시스템의 [2024년 환경정보공개제도 등록 가이드라인](https://env-info.kr/v2/publish/testfiles/2024년%20환경정보공개제도%20등록%20가이드라인.pdf), 인쇄면 156~157쪽을 참고했습니다. 휘발유 순발열량 30.4MJ/L와 CO2 계수 69,300kg/TJ를 사용하며, 연비와 전환율은 별도의 가정입니다. 수치·출처·적용 범위는 `data/carbon_parameters.json`, 계산 예시는 `data/results/carbon_example.json`에 수록했습니다. 원문 전체는 재배포하지 않습니다.

## 분석 도구와 AI

Python·NetworkX·GeoPandas·pyproj 등을 이용했습니다. 분석 코드는 Codex의 보조로 작성했으며 활용 범위는 [AI 활용 내역](AI_USAGE.md)에 정리했습니다. 설치 패키지와 가상환경은 배포에 포함하지 않습니다. 별도 코드 라이선스는 부여하지 않았으며, 원자료의 이용 조건은 각각 유지합니다.
