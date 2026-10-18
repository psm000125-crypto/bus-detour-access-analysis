"""Revised model: include mapped linear bus passenger platforms, preserving access rules.

No source coordinates or node memberships are edited. Vehicle-only busways and
area platforms remain excluded. All results are conditional mapped distances.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
import networkx as nx
import pandas as pd
import pyproj

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_13"))
sys.path.insert(0, str(ROOT.parent / "data_28"))
from recompute_expanded import prepare, choose_origins, base
from policy_engine import PolicyEngine
from analyze_accessibility import restricted_graph


def platform_allowed(tags):
    if tags.get("highway") != "platform":
        return base.allowed(tags, "street_assumed")
    if tags.get("bus") != "yes" or tags.get("public_transport") != "platform":
        return False
    # Apply every original access/area/direction rule to this passenger space.
    return base.allowed({**tags, "highway": "footway"}, "street_assumed")


def make_graph(nodes, ways, transformer):
    xy = {n: transformer.transform(obj["lon"], obj["lat"]) for n, obj in nodes.items()}
    graph = nx.Graph()
    explicit = base.EXPLICIT | {"platform"}
    for wid, way in sorted(ways.items()):
        tags = way.get("tags", {})
        if not platform_allowed(tags): continue
        if tags.get("highway") == "platform" and way["nodes"][0] == way["nodes"][-1]:
            continue  # A closed platform outline is not a routing centreline.
        for u, v in zip(way["nodes"], way["nodes"][1:]):
            if u == v: continue
            length = math.dist(xy[u], xy[v])
            if not math.isfinite(length) or length <= 0: raise ValueError("Invalid edge length")
            if graph.has_edge(u, v):
                old = graph[u][v]
                if old["length_m"] <= length and old["highway"] in explicit: continue
            graph.add_node(u, x=xy[u][0], y=xy[u][1])
            graph.add_node(v, x=xy[v][0], y=xy[v][1])
            graph.add_edge(u, v, length_m=length, way_id=wid, highway=tags["highway"],
                           steps=tags["highway"] == "steps", assumed_street=tags["highway"] not in explicit)
    return graph


def model():
    pyproj.network.set_network_enabled(False)
    contract, _, _, _, sources, transformer = prepare()
    raw = ROOT.parent / "data_13/raw/osm_medium_windows_response.txt"
    _, nodes, ways = base.read_osm(raw)
    entries = choose_origins(nodes, transformer, sources["S"], 500)
    graph = make_graph(nodes, ways, transformer)
    from shapely.geometry import Point
    points = {e["origin"]: Point(e["x"], e["y"]) for e in entries}
    points.update(sources)
    anchors = base.project_anchors(graph, points, 100)
    origins = {e["origin"]: anchors[e["origin"]]["node"] for e in entries if anchors[e["origin"]]["eligible"]}
    engine = PolicyEngine(graph, origins, anchors["S"]["node"], anchors["A"]["node"])
    return raw, nodes, ways, entries, graph, anchors, engine


def main():
    raw, nodes, ways, entries, graph, anchors, engine = model()
    assert len(entries) == len(engine.origins) == 22
    labels = {e["origin"]: e["label"] for e in entries}
    policies, comparisons = {}, {}
    for k in (1, 2): policies[str(k)], comparisons[str(k)] = engine.fit(k)
    rows, summary = [], []
    for key, policy in policies["2"].items():
        current = []
        for name in engine.origins:
            row = engine.row(name, policy["candidates"])
            row.update(policy=key, label=labels[name], B_m=engine.origins[name]["approach"]["length_m"],
                       L_m=row["D_known_m"] - engine.origins[name]["approach"]["length_m"])
            current.append(row); rows.append(row)
        frame = pd.DataFrame(current)
        summary.append({"policy": key, **engine.score(policy["candidates"]),
                        "improved_vs_stop": int(frame.reduction_m.gt(1e-7).sum()),
                        "encountered_without_reduction": int((frame.first_notice.notna() & frame.reduction_m.abs().lt(1e-7)).sum()),
                        "mean_B_m": frame.B_m.mean(), "mean_L_m": frame.L_m.mean(),
                        "mean_E_m": frame.E_policy_m.mean(), "mean_D_m": frame.D_policy_m.mean(),
                        "mean_known_m": frame.D_known_m.mean(),
                        "location_share_added": frame.L_m.sum() / (frame.L_m.sum() + frame.E_policy_m.sum())})
    pd.DataFrame(rows).to_csv(ROOT / "journeys.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(summary).to_csv(ROOT / "policy_summary.csv", index=False, encoding="utf-8-sig")
    budgets = []
    previous = None
    for k in (0, 1, 2):
        candidates = [] if not k else policies[str(k)]["equity"]["candidates"]
        values = [engine.row(name, candidates) for name in engine.origins]
        score = engine.score(candidates)
        budgets.append({"additional_notices": k, **score, "improved_journeys": sum(r["reduction_m"] > 1e-7 for r in values),
                        "marginal_max_E_reduction_m": None if previous is None else previous - score["max_E_m"]})
        previous = score["max_E_m"]
    pd.DataFrame(budgets).to_csv(ROOT / "budget.csv", index=False, encoding="utf-8-sig")
    all_rows = pd.DataFrame(rows)
    cov = all_rows[all_rows.policy.eq("coverage_strong")].set_index("origin")
    eq = all_rows[all_rows.policy.eq("equity")].set_index("origin")
    delta = cov.D_policy_m - eq.D_policy_m
    diff = pd.DataFrame({"label": cov.label, "coverage_E_m": cov.E_policy_m, "worst_E_m": eq.E_policy_m,
                         "distance_reduction_vs_coverage_m": delta})
    diff.to_csv(ROOT / "same_two_signs_by_origin.csv", encoding="utf-8-sig")
    clean, edges_removed, nodes_removed = restricted_graph(graph, ways, nodes)
    access, stairs = [], []
    for entry in entries:
        name, start = entry["origin"], anchors[entry["origin"]]["node"]
        route = base.shortest(graph, start, engine.a)
        filtered = base.shortest(clean, start, engine.a)
        tag = entry["tags"].get("wheelchair", "unknown")
        status = "entrance_restricted" if tag == "no" else ("mapped_route_needs_field_check" if filtered else "no_route_without_steps")
        access.append({"origin": name, "label": labels[name], "wheelchair_tag": tag, "status": status,
                       "baseline_m": route["length_m"], "steps_m": route["steps_m"],
                       "restricted_m": filtered["length_m"] if filtered else None})
        if route["steps_m"] > 0:
            ids = sorted({graph[u][v]["way_id"] for u, v in zip(route["path"], route["path"][1:]) if graph[u][v]["steps"]})
            stairs.append({"origin": name, "label": labels[name], "steps_m": route["steps_m"], "ways": ids})
    pd.DataFrame(access).to_csv(ROOT / "accessibility.csv", index=False, encoding="utf-8-sig")
    # Location sensitivity is kept as a supplement, not an operating proposal.
    path = nx.shortest_path(graph, engine.s, engine.a, weight="length_m")
    distance = nx.single_source_dijkstra_path_length(graph, engine.s, weight="length_m")
    eligible = [n for n in path[1:-1] if isinstance(n, int) and any(d["highway"] not in {"steps", "corridor"} for _, _, d in graph.edges(n, data=True))]
    locations = {f"H{b}": min(eligible, key=lambda n: (abs(distance[n]-b), str(n))) for b in (500, 1000)}
    loc_rows = []
    notices = policies["2"]["equity"]["candidates"]
    for label, target in {"official_proxy": engine.a, **locations}.items():
        other = PolicyEngine(graph, {name: r["node"] for name, r in engine.origins.items()}, engine.s, target)
        for name in other.origins:
            row = other.row(name, notices)
            loc_rows.append({"scenario": label, "origin": name, "B_m": engine.origins[name]["approach"]["length_m"],
                             "L_m": row["D_known_m"] - engine.origins[name]["approach"]["length_m"],
                             "known_m": row["D_known_m"], "total_m": row["D_policy_m"], "E_m": row["E_policy_m"]})
    pd.DataFrame(loc_rows).to_csv(ROOT / "location_sensitivity.csv", index=False, encoding="utf-8-sig")
    special = "N3390524793"
    route_s = base.shortest(graph, anchors[special]["node"], engine.s)
    route_a = base.shortest(graph, anchors[special]["node"], engine.a)
    (ROOT / "entrance_9_1_path.json").write_text(json.dumps({"to_original": route_s, "to_alternative": route_a,
       "ways_to_original": [{"u": u, "v": v, "way_id": graph[u][v]["way_id"], "tags": ways[graph[u][v]["way_id"]].get("tags", {})}
                            for u, v in zip(route_s["path"], route_s["path"][1:])]}, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"model": "historical mapped network with linear bus passenger platforms included; no artificial connectors",
              "selected": len(entries), "resolved": len(engine.origins), "unresolved": engine.unresolved,
              "candidate_count": len(engine.candidates), "combinations": comparisons, "policies": policies,
              "summary": summary, "budget": budgets,
              "same_two_signs": {"better": int(delta.gt(1e-7).sum()), "same": int(delta.abs().lt(1e-7).sum()), "worse": int(delta.lt(-1e-7).sum())},
              "improved_origins": diff[delta.gt(1e-7)].reset_index().to_dict("records"),
              "accessibility_status_counts": dict(pd.Series([r["status"] for r in access]).value_counts().astype(int)),
              "wheelchair_tag_counts": dict(pd.Series([r["wheelchair_tag"] for r in access]).value_counts().astype(int)),
              "stairs": stairs, "edges_removed_for_access": edges_removed, "nodes_removed_for_access": nodes_removed,
              "entrance_9_1": {"to_S_m": route_s["length_m"], "to_A_m": route_a["length_m"], "path_to_S": route_s["path"]},
              "official_extra_gt1000": sum(r["L_m"] > 1000 for r in loc_rows if r["scenario"] == "official_proxy"),
              "official_extra_gt500": sum(r["L_m"] > 500 for r in loc_rows if r["scenario"] == "official_proxy"),
              "S_A_m": distance[engine.a],
              "input_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
              "limits": "Street walking and projected anchors assumed. Map connection is not event-day field access, elevator operation or wheelchair boarding certification."}
    (ROOT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=int), encoding="utf-8")
    print(json.dumps({k: v for k,v in result.items() if k not in {"policies", "input_sha256"}}, ensure_ascii=False, indent=2, default=int))


if __name__ == "__main__": main()
