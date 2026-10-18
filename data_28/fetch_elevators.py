"""Optional historical OSM inventory, separate from routing assumptions."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parent / "raw"
root.mkdir(parents=True, exist_ok=True)
query = '[out:json][timeout:35][date:"2026-04-04T22:00:00Z"];nwr["highway"="elevator"](37.545,126.958,37.578,127.003);out center body;'
(root / "elevators_query.txt").write_text(query, encoding="utf-8")
endpoint = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
record = {"endpoint": endpoint, "query": query, "acquired_at_utc": datetime.now(timezone.utc).isoformat()}
try:
    request = urllib.request.Request(endpoint + "?" + urllib.parse.urlencode({"data": query}), headers={"User-Agent": "ResearchAudit/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read()
    data = json.loads(body)
    if data.get("remark") or not isinstance(data.get("elements"), list):
        raise ValueError("Incomplete Overpass response")
    (root / "elevators_20260405.json").write_bytes(body)
    record.update(success=True, elements=len(data["elements"]), sha256=hashlib.sha256(body).hexdigest())
except Exception as exc:
    record.update(success=False, error=str(exc))
(root / "acquisition.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(record, ensure_ascii=True))
