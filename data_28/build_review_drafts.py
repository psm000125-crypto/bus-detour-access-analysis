"""Generate review drafts from preserved AI transcriptions, not a new LLM call.

Machine checks are consistency checks, not extraction-accuracy measurements.
All outputs require source review and operational approval before release.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "data_09/service_changes.json"


def validate_record(record, allowed_stop_ids):
    window = record["announced_service_window"]
    start, end = (datetime.fromisoformat(window[k]) for k in ("start", "end"))
    if end <= start:
        raise ValueError("Service window must end after start")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone is required")
    point = record["boarding_point"]
    if point["type"] == "temporary_landmark" and point["ars_id"] is not None:
        raise ValueError("Unverified temporary-place stop ID must remain null")
    if point["is_regular_stop"] != (point["type"] == "regular_stop"):
        raise ValueError("Stop type conflicts with regular-stop flag")
    for stop in (record.get("skipped_stops") or []) + ([point] if point["ars_id"] else []):
        sid = stop["ars_id"]
        if not isinstance(sid, str) or not re.fullmatch(r"[0-9]{5}", sid) or sid not in allowed_stop_ids:
            raise ValueError("Unknown stop ID or missing leading zero")
    if record.get("actual_service_window") is not None:
        raise ValueError("Observed service was not supplied")
    if point["longitude"] is not None or point["latitude"] is not None:
        raise ValueError("Official boarding coordinates were not supplied")
    if record.get("step_free_connection_verified") is not None:
        raise ValueError("Step-free operation was not supplied")
    return True


def build_draft(record, source):
    window, point = record["announced_service_window"], record["boarding_point"]
    return {"route": record["route_name"], "source_url": source["source_page"],
            "source_locations": record["source_locations"],
            "announced_service_window": deepcopy(window),
            "road_control_window_separate": deepcopy(source["common_road_control_window"]),
            "boarding_point": deepcopy(point), "skipped_stops": deepcopy(record["skipped_stops"]),
            "needs_review": ["현장 승하차·보도·횡단·계단 없는 연결", "저상·휠체어 승차 가능 차량과 대체 이동 지원", "담당기관 협의·비용·안내 설치"],
            "release_status": "검토 초안: 원문 대조와 운영기관 확인 필요",
            "unknowns_kept_null": {"actual_service_window": None, "step_free_connection_verified": None,
                                  "boarding_longitude": None, "boarding_latitude": None}}


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    # This explicit list is a reviewed transcription, not an independent gold set.
    ids = {"02002", "02100", "02233", "02006", "02136", "02001"}
    drafts = []
    for record in source["records"]:
        validate_record(record, ids)
        drafts.append(build_draft(record, source))
    result = {"status": "2 preserved AI-transcribed route records to deterministic review drafts; no new inference API called",
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "input_records": len(source["records"]), "generated_drafts": len(drafts),
              "consistency_checks_passed": len(drafts), "independent_accuracy_evaluation": None,
              "drafts": drafts}
    (ROOT / "review_drafts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# AI 전사에서 만든 우회 검토서 초안", "", "기존 Codex 전사 2건을 입력으로 규칙 검사를 거쳐 생성했다. 새 모델 호출·독립 정확도 평가·자동 공표는 수행하지 않았다.", ""]
    for draft in drafts:
        lines += [f"## {draft['route']}번", "", f"원문: {draft['source_url']}", "",
                  f"예정 운행시간: {draft['announced_service_window']['start']} ~ {draft['announced_service_window']['end']}", "",
                  f"임시·대체 승하차 장소: {draft['boarding_point']['name']} / " + (f"정류소 ID {draft['boarding_point']['ars_id']}" if draft['boarding_point']['ars_id'] else "정류소 ID 미확인"), "",
                  f"복귀조건: {draft['announced_service_window']['early_restoration_condition']}", "",
                  "공통 도로 통제시간은 별도 필드로 유지했다. 실제 운행시간·정확한 대기좌표·계단 없는 연결은 확인 필요.", "",
                  "원문 대조 후 검토: " + "; ".join(draft["needs_review"]), ""]
    (ROOT / "검토서_초안.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "drafts"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
