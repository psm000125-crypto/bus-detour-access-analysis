"""Post-hoc scope repair and sensitivity analysis using only staged public data.

Results concern mapped proxy journeys, not observed walking or deployment sites.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_11"))
from evaluate_policies import TOL, base, evaluate_journey, prepare
from adapt_subset import choose_with_total_distance
import networkx as nx
import pandas as pd
import pyproj
from shapely.geometry import LineString, Point, Polygon


def choose_origins(nodes, transformer, stop_point, radius):
    rows = []
    for node_id, node in sorted(nodes.items()):
        tags = node.get("tags", {})
        if tags.get("railway") != "subway_entrance":
            continue
        point = Point(transformer.transform(node["lon"], node["lat"]))
        distance = point.distance(stop_point)
        if distance <= radius + TOL:
            rows.append({"origin": f"N{node_id}", "osm_node_id": node_id,
                         "label": tags.get("name", tags.get("description", f"출입구 {tags.get('ref', '?')}")),
                         "radius_distance_m": distance, "x": point.x, "y": point.y,
                         "tags": tags})
    return rows


def query_polygon(transformer, bbox):
    south, west, north, east = bbox
    # Dense boundary is a planar approximation for extent auditing, not a CRS accuracy claim.
    ring = []
    for start, end in [((west,south),(east,south)), ((east,south),(east,north)),
                       ((east,north),(west,north)), ((west,north),(west,south))]:
        for i in range(101):
            t = i/100
            ring.append(transformer.transform(start[0]+t*(end[0]-start[0]), start[1]+t*(end[1]-start[1])))
    return Polygon(ring)


def make_context(nodes, ways, source_points, contract, origins, shift):
    points = {r["origin"]: Point(r["x"], r["y"]) for r in origins}
    points.update({"S": source_points["S"], "A": Point(source_points["A"].x, source_points["A"].y + shift)})
    graph, _ = base.make_graph(nodes, ways, "street_assumed", contract["measurement_crs"])
    anchors = base.project_anchors(graph, points, contract["max_proxy_offset_m"])
    s, a = anchors["S"]["node"], anchors["A"]["node"]
    resolved, unresolved = {}, []
    for row in origins:
        anchor = anchors[row["origin"]]
        if not anchor["eligible"]:
            status = "anchor_out_of_range"
        else:
            status = evaluate_journey(graph, anchor["node"], s, a, ())["status"]
        if status == "conditional":
            resolved[row["origin"]] = anchor["node"]
        else:
            unresolved.append({**row, "status": status, "proxy_offset_m": anchor["offset_m"]})
    return graph, anchors, resolved, unresolved


def fit_policies(graph, origins, s, a, radius):
    journeys, singles, _, _ = base.compare_notice(graph, origins, s, a, radius)
    scores = [{"candidates": [r["candidate"]], "covered": r["covered"], "max_E_m": r["max_E_m"],
               "sum_E_m": r["sum_E_m"], "max_D_m": max(j["D_notice_m"] for j in r["rows"])} for r in singles]
    pairs = []
    for left, right in itertools.combinations(singles, 2):
        rows = [(min(l["E_notice_m"],r["E_notice_m"]), min(l["D_notice_m"],r["D_notice_m"]),
                 l["encountered"] or r["encountered"]) for l,r in zip(left["rows"],right["rows"])]
        pairs.append({"candidates": [left["candidate"],right["candidate"]], "covered": sum(r[2] for r in rows),
                      "max_E_m": max(r[0] for r in rows), "sum_E_m": sum(r[0] for r in rows),
                      "max_D_m": max(r[1] for r in rows)})
    return journeys, {"1": choose_with_total_distance(scores), "2": choose_with_total_distance(pairs)}, len(singles), len(pairs)


def policy_rows(graph, anchors, origins, selection, all_entries):
    rows = []
    for entry in all_entries:
        name = entry["origin"]
        result = ({"status": "mapped_disconnection"} if name not in origins else
                  evaluate_journey(graph, origins[name], anchors["S"]["node"], anchors["A"]["node"], selection))
        rows.append({"origin": name, "osm_node_id": entry["osm_node_id"], "label": entry["label"], **result})
    return rows


def recognition_expectations(graph, origin, s, a, candidates, p):
    if not 0 <= p <= 1:
        raise ValueError("p must lie in [0,1]")
    expected = 0.0
    for flags in itertools.product((False, True), repeat=len(candidates)):
        probability = math.prod(p if flag else 1-p for flag in flags)
        selected = [n for n,flag in zip(candidates,flags) if flag]
        row = evaluate_journey(graph, origin, s, a, selected)
        if row["status"] != "conditional":
            return None
        expected += probability * row["E_policy_m"]
    return expected


def difference(rows, comparator):
    other = {r["origin"]:r for r in comparator if r["status"] == "conditional"}
    values = [r["E_policy_m"] - other[r["origin"]]["E_policy_m"]
              for r in rows if r["status"] == "conditional"]
    return {"better": sum(v < -TOL for v in values), "same": sum(abs(v) <= TOL for v in values),
            "worse": sum(v > TOL for v in values), "largest_worsening_m": max(0.0, max(values, default=0))}


def main():
    pyproj.network.set_network_enabled(False)
    contract, raw, nodes, ways, sources, transformer = prepare()
    review = json.loads((ROOT / "review_contract.json").read_text(encoding="utf-8"))
    boundary = query_polygon(transformer, review["extents_south_west_north_east"]["original"])
    boundary_clearance = sources["S"].distance(boundary.boundary)
    assert boundary.contains(sources["S"]) and boundary_clearance > 400 + 10
    all_rows, summaries, comparisons, fixed_rows, recognition = [], [], [], [], []
    scenario_results, main_policies = {}, None
    for radius, shift in [(400,0),(400,-20),(400,20),(300,0)]:
        entries = choose_origins(nodes, transformer, sources["S"], radius)
        name = f"r{radius}_shift{shift:+d}"
        graph, anchors, resolved, unresolved = make_context(nodes, ways, sources, contract, entries, shift)
        journeys, selections, candidate_count, pair_count = fit_policies(graph, resolved, anchors["S"]["node"], anchors["A"]["node"], 450)
        scenario_results[name] = {"selected": len(entries), "resolved": len(resolved), "unresolved": unresolved,
                                  "candidate_count": candidate_count, "pair_count": pair_count,
                                  "anchors": anchors, "policies": selections}
        if radius == 400 and shift == 0:
            main_policies = selections
            pd.DataFrame([{**entry,"tags":json.dumps(entry["tags"], ensure_ascii=False)} for entry in entries]).to_csv(
                ROOT / "primary_origin_selection.csv", index=False, encoding="utf-8-sig")
            assumptions = []
            for journey in journeys:
                line = LineString([(graph.nodes[n]["x"],graph.nodes[n]["y"]) for n in journey["direct"]["path"]])
                assumptions.append({"origin":journey["origin"], "D_known_m":journey["D_known_m"],
                                    "direct_assumed_street_share":journey["direct_assumed_street_m"]/journey["D_known_m"],
                                    "entire_direct_line_inside_extraction_polygon":boundary.covers(line),
                                    "direct_line_boundary_clearance_m":line.distance(boundary.boundary)})
            pd.DataFrame(assumptions).to_csv(ROOT / "route_assumption_audit.csv",index=False,encoding="utf-8-sig")
        for count, policies in selections.items():
            evaluated = {policy:policy_rows(graph,anchors,resolved,score["candidates"],entries) for policy,score in policies.items()}
            for policy, score in policies.items():
                rows = evaluated[policy]
                valid = [r for r in rows if r["status"] == "conditional"]
                assert abs(max(r["E_policy_m"] for r in valid)-score["max_E_m"]) < TOL
                assert abs(sum(r["E_policy_m"] for r in valid)-score["sum_E_m"]) < TOL
                assert abs(max(r["D_policy_m"] for r in valid)-score["max_D_m"]) < TOL
                all_rows.extend({"scenario":name,"K":int(count),"policy":policy,**row} for row in rows)
                summaries.append({"scenario":name,"radius_m":radius,"shift_m":shift,"K":int(count),"policy":policy,
                                  "selected":len(entries),"resolved":len(valid),"unresolved":len(unresolved),
                                  "all_origin_max_E_m":None if unresolved else score["max_E_m"],
                                  "all_origin_max_D_m":None if unresolved else score["max_D_m"],
                                  "min_D_known_m":min(r["D_known_m"] for r in valid),
                                  "max_D_known_m":max(r["D_known_m"] for r in valid),
                                  **score})
                comparisons.append({"scenario":name,"K":int(count),"policy":policy,
                                    **difference(rows,evaluated["coverage_strong"])})
        # Keep the nominal one/two-notice policies fixed while changing endpoint/radius.
        for count, policies in main_policies.items():
            for policy, score in policies.items():
                rows = policy_rows(graph,anchors,resolved,score["candidates"],entries)
                valid = [r for r in rows if r["status"] == "conditional"]
                fixed_rows.append({"scenario":name,"K":int(count),"policy":policy,
                                   "max_E_m":max(r["E_policy_m"] for r in valid),
                                   "max_D_m":max(r["D_policy_m"] for r in valid),
                                   "sum_E_m":sum(r["E_policy_m"] for r in valid),
                                   "selected":len(entries),"resolved":len(valid),"unresolved":len(unresolved)})
        if radius == 400 and shift == 0:
            for p in (0,.25,.5,.75,1):
                for policy, score in main_policies["2"].items():
                    expected = [recognition_expectations(graph,n,anchors["S"]["node"],anchors["A"]["node"],score["candidates"],p)
                                for n in resolved.values()]
                    recognition.append({"p_assumed":p,"policy":policy,"max_expected_E_m":max(expected),
                                        "sum_expected_E_m":sum(expected),"resolved":len(resolved),"unresolved":len(unresolved)})
    # Diagnose the isolated entrance without substituting a nearer connected network.
    primary = choose_origins(nodes,transformer,sources["S"],400)
    graph,anchors,resolved,unresolved = make_context(nodes,ways,sources,contract,primary,0)
    isolated = anchors["N3390524793"]["node"]
    component = nx.node_connected_component(graph,isolated)
    component_edges = [{"u":u,"v":v,"way_id":d["way_id"],"highway":d["highway"],"length_m":d["length_m"]}
                       for u,v,d in graph.subgraph(component).edges(data=True)]
    stop_only = policy_rows(graph,anchors,resolved,(),primary)
    output = {"status":"conditional within-extract stress test; not validated pedestrian effects",
              "review_contract":review,"origin_circle_boundary_clearance_m":boundary_clearance,
              "primary_radius_m":400,"scenarios":scenario_results,
              "isolated_entrance":{"node_id":3390524793,"component_nodes":len(component),"component_edges":component_edges,
                                   "interpretation":"mapped disconnection; no geometric repair or real-world impossibility claim"},
              "primary_stop_only":{"max_E_m":max(r["E_policy_m"] for r in stop_only if r["status"]=="conditional"),
                                   "max_D_m":max(r["D_policy_m"] for r in stop_only if r["status"]=="conditional")},
              "input_sha256":{str(path.relative_to(ROOT.parent)):hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [ROOT/"review_contract.json",ROOT.parent/"data_10/raw/osm_20260405.json",
                                           ROOT.parent/"data_10/analyze_walks.py",ROOT.parent/"data_11/evaluate_policies.py",
                                           ROOT.parent/"data_11/adapt_subset.py"]}}
    for filename,rows in [("policy_sensitivity.csv",summaries),("journey_sensitivity.csv",all_rows),
                          ("distributional_comparison.csv",comparisons),("fixed_policy_sensitivity.csv",fixed_rows),
                          ("two_notice_recognition.csv",recognition)]:
        pd.DataFrame(rows).to_csv(ROOT/filename,index=False,encoding="utf-8-sig")
    (ROOT/"robustness_results.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    plot_summary(summaries,recognition)
    print(json.dumps({"boundary_clearance_m":boundary_clearance,
                      "scenarios":{k:{j:v[j] for j in ("selected","resolved","candidate_count","pair_count")} for k,v in scenario_results.items()},
                      "primary_two_notice":main_policies["2"]},ensure_ascii=True,indent=2))


def plot_summary(rows,recognition):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"]="Malgun Gothic"
    plt.rcParams["axes.unicode_minus"]=False
    fig,axes=plt.subplots(1,2,figsize=(12,5.4))
    policies=[("coverage_strong","여정 수 우선","#bd8137"),("equity","추가길이 부담 우선","#245779"),
              ("total_distance_equity","전체길이 부담 우선","#86578c")]
    scenarios=["r400_shift+0","r400_shift-20","r400_shift+20","r300_shift+0"]
    for key,label,color in policies:
        data=[next(r for r in rows if r["scenario"]==s and r["K"]==2 and r["policy"]==key) for s in scenarios]
        axes[0].plot(range(4),[r["max_E_m"] for r in data],"o-",label=label,color=color)
        rec=[r for r in recognition if r["policy"]==key]
        axes[1].plot([r["p_assumed"] for r in rec],[r["max_expected_E_m"] for r in rec],"o-",label=label,color=color)
    axes[0].set_xticks(range(4),["400m\n기준","400m\nA 남쪽 20m","400m\nA 북쪽 20m","300m\n범위 축소"])
    axes[0].set_title("같은 추가 2곳: 조건별 재산정")
    axes[0].set_ylabel("계산 가능한 여정 중 최대 E(m)")
    axes[1].set_title("400m 기준 후보 고정: 인지 민감도")
    axes[1].set_xlabel("각 안내를 읽을 확률 p — 가정값")
    axes[1].set_ylabel("여정별 기대 E의 최댓값(m)")
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
        ax.legend(fontsize=8)
    fig.suptitle("안내 정책의 결과는 분석 조건에 얼마나 의존하나",fontsize=15)
    fig.text(.02,.045,"400m: 선정 20개 중 19개 계산 / 300m: 17개 중 16개 계산. 미연결 1개는 각 조건에서 별도 보존.",fontsize=9)
    fig.text(.02,.015,"일반도로 보행·대체 지점·고정 접근 경로 가정. 실제 통행·인지율·행사일 효과 검증 아님. © OpenStreetMap contributors (ODbL)",fontsize=8)
    fig.tight_layout(rect=(0,.1,1,.93))
    fig.savefig(ROOT/"robustness_sensitivity.png",dpi=180)
    plt.close(fig)


if __name__=="__main__":
    main()
