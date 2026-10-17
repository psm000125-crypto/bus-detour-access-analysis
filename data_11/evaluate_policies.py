"""Offline policy comparisons and spatial stress test; not a pedestrian navigator."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "data_10"
sys.path.insert(0, str(PARENT))
import analyze_walks as base
import networkx as nx
import pandas as pd
import pyproj
from shapely.geometry import Point, Polygon

TOL = 1e-7


def clean(value):
    if value < -TOL:
        raise ValueError(f"Negative excess length violates shortest-path bound: {value}")
    return 0.0 if abs(value) <= TOL else value


def evaluate_journey(graph, origin_node, s, a, candidates):
    approach = base.shortest(graph, origin_node, s)
    direct = base.shortest(graph, origin_node, a)
    onward = base.shortest(graph, s, a)
    if not approach or not direct or not onward:
        return {"status": "mapped_disconnection"}
    stop_distance = approach["length_m"] + onward["length_m"]
    notice_distance = stop_distance
    first = next((n for n in approach["path"][:-1] if n in set(candidates)), None)
    if first is not None:
        prefix = approach["path"][:approach["path"].index(first) + 1]
        reroute = base.shortest(graph, first, a)
        if reroute is None:
            return {"status": "notice_onward_disconnection"}
        notice_distance = nx.path_weight(graph, prefix, "length_m") + reroute["length_m"]
    return {"status": "conditional", "first_notice": first,
            "D_known_m": direct["length_m"], "D_stop_m": stop_distance,
            "D_policy_m": notice_distance,
            "E_stop_m": clean(stop_distance - direct["length_m"]),
            "E_policy_m": clean(notice_distance - direct["length_m"]),
            "reduction_m": clean(stop_distance - notice_distance),
            "direct_assumed_street_m": direct["assumed_street_m"]}


def score_policy(graph, origins, s, a, candidates):
    rows = [{"origin": key, **evaluate_journey(graph, node, s, a, candidates)}
            for key, node in origins.items()]
    resolved = [r for r in rows if r["status"] == "conditional"]
    full = len(resolved) == len(rows)
    return {"candidates": list(candidates), "rows": rows,
            "origin_count": len(rows), "resolved_count": len(resolved),
            "covered": sum(r["first_notice"] is not None for r in resolved),
            "max_E_m": max(r["E_policy_m"] for r in resolved) if full and resolved else None,
            "sum_E_m": sum(r["E_policy_m"] for r in resolved) if full and resolved else None}


def select_policies(scores):
    valid = [r for r in scores if r["max_E_m"] is not None]
    if not valid:
        return {}
    def key_id(r):
        return tuple(map(str, r["candidates"]))
    def choose(criteria):
        pool = list(valid)
        for criterion, direction in criteria:
            values = [direction * r[criterion] for r in pool]
            optimum = min(values)
            pool = [r for r in pool if direction * r[criterion] <= optimum + TOL]
        return min(pool, key=key_id)
    return {"coverage_strong": choose([("covered", -1), ("max_E_m", 1), ("sum_E_m", 1)]),
            "efficiency": choose([("sum_E_m", 1), ("max_E_m", 1)]),
            "equity": choose([("max_E_m", 1), ("sum_E_m", 1)])}


def expected_excess(row, p):
    if not 0 <= p <= 1:
        raise ValueError("Recognition sensitivity must lie in [0, 1]")
    return (1 - p) * row["E_stop_m"] + p * row["E_policy_m"]


def prepare():
    contract = json.loads((PARENT / "analysis_contract.json").read_text(encoding="utf-8"))
    raw, nodes, ways = base.read_osm(PARENT / contract["osm_source"])
    transformer = pyproj.Transformer.from_crs(4326, contract["measurement_crs"], always_xy=True)
    stops = pd.read_csv(PARENT / "selected_stops_20260402.csv", dtype=str).set_index("ARS_ID")
    stop = stops.loc[contract["original_stop"]["ars_id"]]
    sources = {o["id"]: Point(transformer.transform(nodes[o["osm_node_id"]]["lon"], nodes[o["osm_node_id"]]["lat"]))
               for o in contract["origins"]}
    sources["S"] = Point(transformer.transform(float(stop["X좌표"]), float(stop["Y좌표"])))
    sources["A"] = Polygon([transformer.transform(nodes[i]["lon"], nodes[i]["lat"])
                              for i in ways[contract["alternative"]["osm_building_way_id"]]["nodes"]]).centroid
    return contract, raw, nodes, ways, sources, transformer


def graph_with_anchors(nodes, ways, sources, contract):
    graph, _ = base.make_graph(nodes, ways, "street_assumed", contract["measurement_crs"])
    anchors = base.project_anchors(graph, sources, contract["max_proxy_offset_m"])
    return graph, anchors


def main():
    pyproj.network.set_network_enabled(False)
    extension = json.loads((ROOT / "analysis_contract.json").read_text(encoding="utf-8"))
    contract, raw, nodes, ways, sources, transformer = prepare()
    graph, anchors = graph_with_anchors(nodes, ways, sources, contract)
    origins = {o["id"]: anchors[o["id"]]["node"] for o in contract["origins"]}
    s, a = anchors["S"]["node"], anchors["A"]["node"]
    journeys, candidates, _, legacy = base.compare_notice(graph, origins, s, a, contract["candidate_radius_from_S_m"])
    candidate_ids = [r["candidate"] for r in candidates]
    all_scores, selections = {}, {}
    for count in extension["additional_notices"]:
        scores = [score_policy(graph, origins, s, a, combination)
                  for combination in itertools.combinations(candidate_ids, count)]
        all_scores[str(count)] = scores
        selections[str(count)] = select_policies(scores)
    selected = selections["1"]
    primary_rows = []
    for name, policy in {"stop_only": selections["0"]["equity"], **selected}.items():
        for row in policy["rows"]:
            primary_rows.append({"policy": name, **row})
    pd.DataFrame(primary_rows).to_csv(ROOT / "primary_journeys.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{k: v for k, v in score.items() if k != "rows"}
                  for score in all_scores["1"]]).to_csv(ROOT / "all_one_notice_candidates.csv", index=False, encoding="utf-8-sig")
    frontier = [{"additional_notices": int(count), "objective": objective,
                 "combinations_evaluated": len(all_scores[count]),
                 **{k: v for k, v in policy.items() if k not in {"rows"}}}
                for count, policies in selections.items() for objective, policy in policies.items()]
    pd.DataFrame(frontier).to_csv(ROOT / "notice_budget_frontier.csv", index=False, encoding="utf-8-sig")
    recognition = []
    for p in extension["notice_detection_probabilities"]:
        for name, policy in selected.items():
            values = [expected_excess(row, p) for row in policy["rows"]]
            recognition.append({"p_sensitivity_only": p, "policy": name,
                                "max_expected_E_m": max(values), "sum_expected_E_m": sum(values)})
    pd.DataFrame(recognition).to_csv(ROOT / "recognition_sensitivity.csv", index=False, encoding="utf-8-sig")
    # All tagged entrances selected before examining their policy effects. Keep every node ID.
    original_ids = {o["osm_node_id"]: o["id"] for o in contract["origins"]}
    entrances = []
    expanded_sources = dict(sources)
    for node_id, node in sorted(nodes.items()):
        if node.get("tags", {}).get("railway") != "subway_entrance":
            continue
        point = Point(transformer.transform(node["lon"], node["lat"]))
        distance = point.distance(sources["S"])
        if distance > extension["expanded_radius_m"] + TOL:
            continue
        name = original_ids.get(node_id, f"X{node_id}")
        tags = node.get("tags", {})
        label = tags.get("name", tags.get("description", f"출입구 {tags.get('ref', '?')} / OSM {node_id}"))
        entrances.append({"origin": name, "osm_node_id": node_id, "label": label,
                          "radius_distance_m": distance,
                          "is_primary_origin": node_id in original_ids,
                          "lon": node["lon"], "lat": node["lat"],
                          "tags": json.dumps(tags, ensure_ascii=False)})
        expanded_sources[name] = point
    expanded_graph, expanded_anchors = graph_with_anchors(nodes, ways, expanded_sources, contract)
    expanded_rows = []
    for entry in entrances:
        anchor = expanded_anchors[entry["origin"]]
        for policy_name, policy in {"stop_only": selections["0"]["equity"], **selected}.items():
            result = ({"status": "anchor_out_of_range"} if not anchor["eligible"] else
                      evaluate_journey(expanded_graph, anchor["node"], expanded_anchors["S"]["node"],
                                       expanded_anchors["A"]["node"], policy["candidates"]))
            expanded_rows.append({**entry, "policy": policy_name, "proxy_offset_m": anchor["offset_m"], **result})
    expanded_table = pd.DataFrame(expanded_rows)
    expanded_table.to_csv(ROOT / "expanded_entrance_stress_test.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(entrances).to_csv(ROOT / "expanded_origin_selection.csv", index=False, encoding="utf-8-sig")
    expanded_summary = {}
    for name in ("stop_only", *selected):
        rows = [r for r in expanded_rows if r["policy"] == name]
        valid = [r for r in rows if r["status"] == "conditional"]
        expanded_summary[name] = {
            "selected_count": len(rows), "resolved_count": len(valid),
            "unresolved_count": len(rows) - len(valid),
            "additional_origins_count": sum(not r["is_primary_origin"] for r in rows),
            "all_origin_max_E_m": max(r["E_policy_m"] for r in valid) if len(valid) == len(rows) else None,
            "resolved_subset_max_E_m": max((r["E_policy_m"] for r in valid), default=None),
            "resolved_subset_sum_E_m": sum(r["E_policy_m"] for r in valid),
            "resolved_subset_max_D_m": max((r["D_policy_m"] for r in valid), default=None),
            "resolved_subset_min_D_m": min((r["D_policy_m"] for r in valid), default=None),
            "improved_vs_stop_count": sum(r["reduction_m"] > TOL for r in valid),
            "unchanged_vs_stop_count": sum(r["reduction_m"] <= TOL for r in valid),
            "unresolved_ids": [r["osm_node_id"] for r in rows if r["status"] != "conditional"]}
    # Numerical invariance checks across additional splits, not geographic truth checks.
    for name, policy in selected.items():
        for row in policy["rows"]:
            expanded = next(r for r in expanded_rows if r["origin"] == row["origin"] and r["policy"] == name)
            for key in ("D_known_m", "D_stop_m", "E_policy_m"):
                assert abs(row[key] - expanded[key]) < TOL, (name, row["origin"], key)
    output = {"extension_contract": extension, "primary_candidate_count": len(candidates),
              "primary_selections": selections, "legacy_coverage_baseline": legacy,
              "strong_coverage_same_candidate_as_legacy": selected["coverage_strong"]["candidates"] == [legacy["candidate"]],
              "equity_and_efficiency_same_selection": selected["equity"]["candidates"] == selected["efficiency"]["candidates"],
              "all_policy_scores": all_scores, "recognition_sensitivity": recognition,
              "expanded_summary": expanded_summary,
              "inputs_sha256": {str(p.relative_to(ROOT.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [ROOT / "analysis_contract.json", PARENT / "analysis_contract.json",
                                          PARENT / contract["osm_source"], PARENT / "selected_stops_20260402.csv",
                                          PARENT / "analyze_walks.py"]}}
    (ROOT / "policy_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plot_primary(selections, recognition)
    plot_expanded(expanded_rows)
    print(json.dumps({"primary_candidates": len(candidates),
                      "strong_coverage_same_as_legacy": output["strong_coverage_same_candidate_as_legacy"],
                      "equity_equals_efficiency": output["equity_and_efficiency_same_selection"],
                      "frontier_equity": {k: p["equity"]["max_E_m"] for k, p in selections.items()},
                      "expanded": expanded_summary}, ensure_ascii=True, indent=2))


def plot_primary(selections, recognition):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.8))
    colors = {"coverage_strong": "#c88432", "equity": "#235789", "stop_only": "#8c969e"}
    ax = axes[0]
    for shift, (key, label) in zip((-.25, 0, .25), [("stop_only", "기존 승차지 안내"),
                                                  ("coverage_strong", "추가 1곳: 최다 여정"),
                                                  ("equity", "추가 1곳: 최대 추가길이 최소")]):
        policy = selections["0"]["equity"] if key == "stop_only" else selections["1"][key]
        ax.bar([i + shift for i in range(3)], [r["E_policy_m"] for r in policy["rows"]],
               width=.25, label=label, color=colors[key])
    ax.set_xticks(range(3), [r["origin"] for r in selections["1"]["equity"]["rows"]])
    ax.set_title("누구의 추가 경로가 줄어드나")
    ax.set_ylabel("사전 인지 대비 추가 지도 길이 E(m)")
    ax.legend(fontsize=7, loc="upper right")
    ax = axes[1]
    ks = [int(k) for k in selections]
    vals = [selections[str(k)]["equity"]["max_E_m"] for k in ks]
    ax.plot(ks, vals, "o-", color="#235789", lw=2)
    for x, y in zip(ks, vals):
        ax.annotate(f"{y:.0f}m", (x, y), xytext=(0, 9), textcoords="offset points", ha="center")
    ax.set_xticks(ks)
    ax.set_ylim(-25, max(vals) + 70)
    ax.set_xlabel("추가 안내 후보 수 K (기존 승차지 안내 유지)")
    ax.set_ylabel("세 시험 여정 중 최대 E(m)")
    ax.set_title("최대 부담과 안내 수량의 관계")
    ax = axes[2]
    for key, label in [("coverage_strong", "최다 여정 기준"), ("equity", "최대 추가길이 최소 기준")]:
        rows = [r for r in recognition if r["policy"] == key]
        ax.plot([r["p_sensitivity_only"] for r in rows], [r["max_expected_E_m"] for r in rows],
                "o-", label=label, color=colors[key])
    ax.set_xlabel("추가 안내 인지확률 p — 측정값 아님")
    ax.set_ylabel("세 여정 중 최대 기대 E(m)")
    ax.set_title("안내를 못 읽으면 효과 감소")
    ax.legend(fontsize=8)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("안내 배치의 조건부 효과·분배·인지 민감도", fontsize=16)
    fig.text(.02, .045, "주의: 지도상 일반도로 보행·대체 지점·고정 접근경로를 가정. 실제 게시 위치·인지율·보행 가능성·이용자 효과 미검증.", fontsize=9)
    fig.text(.02, .015, "동일 시험에서는 최대 추가길이 최소 해와 총 추가길이 최소 해가 같음. 형평성 목적의 별도 우월성을 입증한 결과가 아님.", fontsize=9)
    fig.tight_layout(rect=(0, .09, 1, .94))
    fig.savefig(ROOT / "policy_comparison.png", dpi=180)
    plt.close(fig)


def plot_expanded(rows):
    import matplotlib.pyplot as plt
    chosen = [r for r in rows if r["policy"] == "equity"]
    chosen.sort(key=lambda r: (r["status"] != "conditional", -r.get("E_stop_m", 0), r["osm_node_id"]))
    fig, ax = plt.subplots(figsize=(11, max(7, len(chosen)*.34 + 2)))
    for y, row in enumerate(chosen):
        if row["status"] != "conditional":
            ax.text(3, y, "연결/투영 미해결 — 도달 0으로 간주하지 않음", fontsize=8, va="center", color="#ad4e38")
        else:
            ax.barh(y + .15, row["E_stop_m"], .3, color="#b8c0c5")
            ax.barh(y - .15, row["E_policy_m"], .3, color="#235789")
    labels = [f"{'● ' if r['is_primary_origin'] else ''}{r['label']} [{str(r['osm_node_id'])[-4:]}]" for r in chosen]
    ax.set_yticks(range(len(chosen)), labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("사전 인지 대비 추가 지도 길이 E(m)")
    ax.set_title("확보한 지도 내 반경 500m 출입구 22개: 고정 후보 적용\n회색=기존 승차지에서 확인 / 파랑=3개 여정에서 고른 안내 후보", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(.02, .04, "● 기존 시험 3곳. 출입구 노드 수는 이용자 수가 아님. 동일 지도의 공간 확장 검토이며 독립 검증 아님.", fontsize=8)
    fig.text(.02, .018, "보도·횡단·행사 통제·실제 승차지·안내 인지 미검증. © OpenStreetMap contributors (ODbL)", fontsize=8)
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(ROOT / "expanded_stress_test.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
