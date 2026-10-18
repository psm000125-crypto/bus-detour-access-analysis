"""Offline audit of mapped access restrictions; never certifies real accessibility.

Keep the original 22 entrance anchors fixed. Removing stairs must not relocate
an origin onto another component. Unknown wheelchair tags remain unknown.
"""
from pathlib import Path
import hashlib
import json
import sys
from collections import Counter

import networkx as nx
import pandas as pd
import pyproj

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_13"))
from recompute_expanded import build, choose_origins, prepare, base


def restricted_graph(graph, ways, nodes):
    out = graph.copy()
    remove = []
    for u, v, data in graph.edges(data=True):
        tags = ways[data["way_id"]].get("tags", {})
        if data["steps"] or tags.get("wheelchair") == "no":
            remove.append((u, v))
    out.remove_edges_from(remove)
    forbidden = [n for n in out if isinstance(n, int)
                 and nodes.get(n, {}).get("tags", {}).get("wheelchair") == "no"]
    out.remove_nodes_from(forbidden)
    return out, len(remove), len(forbidden)


def main():
    pyproj.network.set_network_enabled(False)
    contract, _, _, _, sources, transformer = prepare()
    raw_path = ROOT.parent / "data_13/raw/osm_medium_windows_response.txt"
    _, nodes, ways = base.read_osm(raw_path)
    entries = choose_origins(nodes, transformer, sources["S"], 500)
    graph, anchors, engine = build(nodes, ways, sources, contract, entries, 0)
    clean, edges_removed, nodes_removed = restricted_graph(graph, ways, nodes)
    stair_only = graph.copy()
    stair_only.remove_edges_from([(u, v) for u, v, d in graph.edges(data=True) if d["steps"]])
    rows = []
    for entry in entries:
        name = entry["origin"]
        tag = entry["tags"].get("wheelchair", "unknown")
        anchor = anchors[name]
        start = anchor.get("node")
        baseline = base.shortest(graph, start, engine.a) if start is not None else None
        no_steps = base.shortest(clean, start, engine.a) if start is not None else None
        stair_path = base.shortest(stair_only, start, engine.a) if start is not None else None
        if tag == "no":
            status = "entrance_explicit_wheelchair_no"
        elif baseline is None:
            status = "baseline_map_unresolved"
        elif no_steps is None:
            status = "no_path_after_mapped_restrictions"
        else:
            status = "mapped_path_exists_accessibility_unverified"
        path = no_steps["path"] if no_steps else []
        path_edges = [clean[u][v] for u, v in zip(path, path[1:])]
        known_length = sum(d["length_m"] for d in path_edges
                           if ways[d["way_id"]].get("tags", {}).get("wheelchair") in {"yes", "designated"})
        rows.append({"origin": name, "label": entry["label"], "osm_node_id": entry["osm_node_id"],
                     "wheelchair_tag": tag, "status": status,
                     "baseline_distance_m": baseline["length_m"] if baseline else None,
                     "baseline_steps_m": baseline["steps_m"] if baseline else None,
                     "stairs_only_connected": stair_path is not None,
                     "restricted_distance_m": no_steps["length_m"] if no_steps else None,
                     "detour_m": no_steps["length_m"] - baseline["length_m"] if no_steps and baseline else None,
                     "wheelchair_yes_way_length_m": known_length,
                     "anchor_offset_m": anchor["offset_m"],
                     "source_url": f"https://www.openstreetmap.org/node/{entry['osm_node_id']}"})
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "entrance_access_audit.csv", index=False, encoding="utf-8-sig")
    # Inventory is complete only for objects selected by the historical query.
    # Its recursion requests skeletal nodes, so absent elevator tags cannot prove
    # that elevators do not exist. A separate raw acquisition can supplement it.
    elevators = [{"osm_type": "node", "osm_id": n, "lon": obj["lon"], "lat": obj["lat"], "tags": obj.get("tags", {})}
                 for n, obj in nodes.items() if obj.get("tags", {}).get("highway") == "elevator"]
    extra = ROOT / "raw/elevators_20260405.json"
    if extra.exists():
        obj = json.loads(extra.read_text(encoding="utf-8"))
        if obj.get("remark"):
            raise ValueError(obj["remark"])
        elevators = [{"osm_type": e["type"], "osm_id": e["id"], "lon": e.get("lon"),
                      "lat": e.get("lat"), "tags": e.get("tags", {})} for e in obj["elements"]]
    (ROOT / "mapped_elevators.json").write_text(json.dumps(elevators, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"selected_entrances": len(rows), "baseline_connected": int(frame.baseline_distance_m.notna().sum()),
               "status_counts": dict(Counter(frame.status)), "entrance_wheelchair_tag_counts": dict(Counter(frame.wheelchair_tag)),
               "removed_edges": edges_removed, "removed_nodes": nodes_removed,
               "baseline_routes_with_steps": int(frame.baseline_steps_m.fillna(0).gt(0).sum()),
               "new_disconnections_stairs_only": int((frame.baseline_distance_m.notna() & ~frame.stairs_only_connected).sum()),
               "restricted_connected_geometrically": int(frame.restricted_distance_m.notna().sum()),
               "max_stair_exclusion_detour_m": float(frame.detour_m.max()),
               "mapped_elevators_in_supplement": len(elevators), "supplement_acquired": extra.exists(),
               "scope": "22 mapped entrance records, not 22 passengers or stations. wheelchair=no is a historical OSM annotation, not a field audit. Existing anchors remain fixed. Road assumptions, kerbs, gradients, entrance interiors, elevator operation and vehicle boarding remain unverified. Missing tags are unknown, never accessible.",
               "input_sha256": {str(raw_path.relative_to(ROOT.parent)): hashlib.sha256(raw_path.read_bytes()).hexdigest()}}
    (ROOT / "accessibility_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
