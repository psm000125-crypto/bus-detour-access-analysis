"""Reproducible conditional graph analysis, offline after source acquisition.

Run: .venv_transport/Scripts/python.exe data_10/analyze_walks.py
The model uses mapped line anchors, never invented links across disconnected ways.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
import pyproj
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parent
EXPLICIT = {"footway", "path", "pedestrian", "steps", "corridor"}
EXCLUDED = {"motorway", "motorway_link", "trunk", "trunk_link", "construction",
            "cycleway", "platform", "busway", "bus_guideway", "proposed", "raceway",
            "abandoned", "planned", "razed", "rest_area", "services", "no"}


def allowed(tags, mode):
    h = tags.get("highway")
    if not h or h in EXCLUDED or tags.get("area") == "yes":
        return False
    if tags.get("foot") in {"no", "private"} or tags.get("access") in {"no", "private"}:
        return False
    if tags.get("service") == "private" or tags.get("motorroad") == "yes":
        return False
    if tags.get("oneway:foot") not in {None, "no", "false", "0"}:
        return False  # unresolved directional pedestrian restrictions are not erased
    if any(tags.get(k) == "separate" for k in
           ("sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right")):
        return False
    if mode == "pedestrian_only" and h not in EXPLICIT:
        return False
    if mode == "street_assumed_no_steps" and h == "steps":
        return False
    return True


def read_osm(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("remark"):
        raise ValueError(f"Incomplete Overpass response: {raw['remark']}")
    nodes, ways = {}, {}
    for e in raw["elements"]:
        if e["type"] == "node":
            if e["id"] not in nodes:
                nodes[e["id"]] = e.copy()
            else:
                nodes[e["id"]].setdefault("tags", {}).update(e.get("tags", {}))
        elif e["type"] == "way":
            ways[e["id"]] = e
    return raw, nodes, ways


def make_graph(nodes, ways, mode, target_crs):
    node_ids = sorted(nodes)
    points = gpd.GeoSeries(
        [Point(nodes[i]["lon"], nodes[i]["lat"]) for i in node_ids], crs="EPSG:4326"
    ).to_crs(target_crs)
    xy = {i: (p.x, p.y) for i, p in zip(node_ids, points)}
    graph = nx.Graph()
    for wid in sorted(ways):
        way = ways[wid]
        tags = way.get("tags", {})
        if not allowed(tags, mode):
            continue
        for u, v in zip(way["nodes"], way["nodes"][1:]):
            if u not in xy or v not in xy:
                raise ValueError(f"Missing way node: {wid}")
            if u == v:
                continue
            length = math.dist(xy[u], xy[v])
            if not math.isfinite(length) or length <= 0:
                raise ValueError("Invalid mapped edge length")
            if graph.has_edge(u, v):
                old = graph[u][v]
                if old["length_m"] <= length and old["highway"] in EXPLICIT:
                    continue
            graph.add_node(u, x=xy[u][0], y=xy[u][1])
            graph.add_node(v, x=xy[v][0], y=xy[v][1])
            graph.add_edge(u, v, length_m=length, way_id=wid,
                           highway=tags["highway"], steps=tags["highway"] == "steps",
                           assumed_street=tags["highway"] not in EXPLICIT)
    return graph, xy


def project_anchors(graph, sources, max_offset):
    """Split existing segments at projections; create no off-network connectors."""
    edges = sorted(graph.edges(), key=lambda uv: (str(uv[0]), str(uv[1])))
    lines = gpd.GeoSeries([
        LineString([(graph.nodes[u]["x"], graph.nodes[u]["y"]),
                    (graph.nodes[v]["x"], graph.nodes[v]["y"])]) for u, v in edges
    ], crs="EPSG:32652")
    anchor_eligible = [i for i, (u, v) in enumerate(edges)
                       if graph[u][v]["highway"] not in {"steps", "corridor"}]
    if not anchor_eligible:
        raise ValueError("No street-level mapped segments for proxy anchors")
    planned, groups = {}, {}
    for name, point in sources.items():
        distances = lines.loc[anchor_eligible].distance(point)
        index = int(distances.idxmin())
        offset = float(distances.loc[index])
        line = lines.iloc[index]
        along = float(line.project(point))
        projected = line.interpolate(along)
        entry = {"offset_m": offset, "x": projected.x, "y": projected.y,
                 "segment_u": edges[index][0], "segment_v": edges[index][1],
                 "eligible": offset <= max_offset}
        planned[name] = entry
        if entry["eligible"]:
            groups.setdefault(index, []).append((along, name, projected))
    for index, items in groups.items():
        u, v = edges[index]
        attrs = dict(graph[u][v])
        total = lines.iloc[index].length
        graph.remove_edge(u, v)
        chain = [(0.0, u), (total, v)]
        last_position, last_node = None, None
        for along, name, point in sorted(items):
            if along <= 1e-6:
                node = u
            elif total - along <= 1e-6:
                node = v
            elif last_position is not None and abs(along - last_position) <= 1e-6:
                node = last_node
            else:
                node = f"anchor_{name}"
                graph.add_node(node, x=point.x, y=point.y)
                chain.append((along, node))
            planned[name]["node"] = node
            last_position, last_node = along, node
        chain.sort(key=lambda p: p[0])
        for (a, na), (b, nb) in zip(chain, chain[1:]):
            if b - a > 1e-6:
                graph.add_edge(na, nb, **{**attrs, "length_m": b - a})
    return planned


def shortest(graph, source, target):
    try:
        path = nx.shortest_path(graph, source, target, weight="length_m")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return {"path": path, "length_m": nx.path_weight(graph, path, "length_m"),
            "assumed_street_m": sum(graph[u][v]["length_m"]
                                    for u, v in zip(path, path[1:]) if graph[u][v]["assumed_street"]),
            "steps_m": sum(graph[u][v]["length_m"]
                           for u, v in zip(path, path[1:]) if graph[u][v]["steps"])}


def compare_notice(graph, origins, s, a, radius):
    journeys = []
    s_to_a = shortest(graph, s, a)
    for name, node in origins.items():
        approach, direct = shortest(graph, node, s), shortest(graph, node, a)
        if not approach or not direct or not s_to_a:
            journeys.append({"origin": name, "status": "mapped_disconnection"})
            continue
        after = approach["length_m"] + s_to_a["length_m"]
        journeys.append({"origin": name, "status": "conditional",
                         "D_known_m": direct["length_m"], "D_stop_m": after,
                         "E_stop_m": after - direct["length_m"],
                         "direct_assumed_street_m": direct["assumed_street_m"],
                         "direct_steps_m": direct["steps_m"],
                         "approach": approach, "direct": direct, "stop_to_A": s_to_a})
    valid = [j for j in journeys if j["status"] == "conditional"]
    if len(valid) != len(journeys):
        return journeys, [], None, None
    candidates = set()
    for j in valid:
        for n in j["approach"]["path"][:-1]:
            if graph.degree(n) >= 3 or n == origins[j["origin"]]:
                ds = shortest(graph, n, s)
                incident = [d["highway"] for _, _, d in graph.edges(n, data=True)]
                if ds and ds["length_m"] <= radius and any(h not in {"steps", "corridor"} for h in incident):
                    candidates.add(n)
    scores = []
    for p in sorted(candidates, key=str):
        pa = shortest(graph, p, a)
        if pa is None:
            continue
        rows = []
        for j in valid:
            path = j["approach"]["path"]
            encountered = p in path
            if encountered:
                prefix = path[:path.index(p) + 1]
                d = nx.path_weight(graph, prefix, "length_m") + pa["length_m"]
            else:
                d = j["D_stop_m"]
            rows.append({"origin": j["origin"], "encountered": encountered,
                         "D_notice_m": d, "E_notice_m": d - j["D_known_m"],
                         "reduction_m": j["D_stop_m"] - d})
        scores.append({"candidate": p, "covered": sum(r["encountered"] for r in rows),
                       "max_E_m": max(r["E_notice_m"] for r in rows),
                       "sum_E_m": sum(r["E_notice_m"] for r in rows),
                       "distance_to_S_m": shortest(graph, p, s)["length_m"],
                       "rows": rows})
    if not scores:
        return journeys, scores, None, None
    best = min(scores, key=lambda r: (r["max_E_m"], r["sum_E_m"], str(r["candidate"])))
    baseline = min(scores, key=lambda r: (-r["covered"], r["distance_to_S_m"], str(r["candidate"])))
    return journeys, scores, best, baseline


def main():
    pyproj.network.set_network_enabled(False)
    contract = json.loads((ROOT / "analysis_contract.json").read_text(encoding="utf-8"))
    raw, nodes, ways = read_osm(ROOT / contract["osm_source"])
    city = pd.read_excel(ROOT / contract["city_stop_source"], dtype=str)
    recent = pd.read_excel(ROOT / contract["city_comparison_source"], dtype=str)
    requested = {"02001", "02002", "02006", "02100", "02233", "02136"}
    selected = city[city["ARS_ID"].isin(requested)].copy()
    assert selected["ARS_ID"].is_unique and set(selected["ARS_ID"]) == requested
    selected.to_csv(ROOT / "selected_stops_20260402.csv", index=False, encoding="utf-8-sig")
    differences = selected.merge(recent, on="ARS_ID", how="left", suffixes=("_apr", "_sep"), validate="one_to_one")
    differences.to_csv(ROOT / "selected_stops_date_comparison.csv", index=False, encoding="utf-8-sig")
    # Column names come from the downloaded workbook; raw coordinates are never relabelled in place.
    city_s = selected.set_index("ARS_ID").loc[contract["original_stop"]["ars_id"]]
    xcol, ycol = city.columns[3], city.columns[4]
    transformer = pyproj.Transformer.from_crs("EPSG:4326", contract["measurement_crs"], always_xy=True)
    sources = {o["id"]: Point(transformer.transform(nodes[o["osm_node_id"]]["lon"], nodes[o["osm_node_id"]]["lat"]))
               for o in contract["origins"]}
    sources["S"] = Point(transformer.transform(float(city_s[xcol]), float(city_s[ycol])))
    building = ways[contract["alternative"]["osm_building_way_id"]]
    polygon = Polygon([transformer.transform(nodes[i]["lon"], nodes[i]["lat"]) for i in building["nodes"]])
    sources["A"] = polygon.centroid
    output = {"contract": contract, "osm_server_metadata": raw.get("osm3s"),
              "city_rows_apr": len(city), "city_rows_sep": len(recent),
              "source_building_centroid": {"x": sources["A"].x, "y": sources["A"].y}, "modes": {}}
    for mode in ("pedestrian_only", "street_assumed", "street_assumed_no_steps"):
        graph, xy = make_graph(nodes, ways, mode, contract["measurement_crs"])
        original_components = sorted((len(c) for c in nx.connected_components(graph)), reverse=True)
        anchors = project_anchors(graph, sources, contract["max_proxy_offset_m"])
        if not all(p["eligible"] for p in anchors.values()):
            output["modes"][mode] = {"status": "anchor_out_of_range", "anchors": anchors}
            continue
        origins = {o["id"]: anchors[o["id"]]["node"] for o in contract["origins"]}
        journeys, scores, best, baseline = compare_notice(
            graph, origins, anchors["S"]["node"], anchors["A"]["node"], contract["candidate_radius_from_S_m"])
        output["modes"][mode] = {"status": "conditional" if best else "mapped_disconnection",
                                "nodes": len(graph), "edges": graph.number_of_edges(),
                                "components": len(original_components), "largest_components": original_components[:10],
                                "anchors": anchors, "journeys": journeys, "candidate_count": len(scores),
                                "best": best, "coverage_baseline": baseline}
        if mode == "street_assumed" and best:
            rows = []
            for j in journeys:
                br = next(r for r in best["rows"] if r["origin"] == j["origin"])
                cr = next(r for r in baseline["rows"] if r["origin"] == j["origin"])
                rows.append({k: j[k] for k in ("origin", "D_known_m", "D_stop_m", "E_stop_m")} |
                            {"D_best_notice_m": br["D_notice_m"], "E_best_notice_m": br["E_notice_m"],
                             "reduction_best_m": br["reduction_m"], "E_coverage_baseline_m": cr["E_notice_m"],
                             "direct_assumed_street_m": j["direct_assumed_street_m"],
                             "status": "conditional mapped-network scenario"})
            pd.DataFrame(rows).to_csv(ROOT / "journey_comparison.csv", index=False, encoding="utf-8-sig")
            plot_result(graph, anchors, best, baseline, journeys, contract)
            plot_budgets(journeys, best, baseline)
        # Endpoint sensitivity perturbs the source target before projection; it does not certify a curb.
        if best:
            sensitivity = []
            for shift in contract["alternative"]["frontage_sensitivity_m"]:
                # Work from the unmodified graph so each alternative endpoint is independent.
                changed, _ = make_graph(nodes, ways, mode, contract["measurement_crs"])
                changed_sources = {**sources, "A": Point(sources["A"].x, sources["A"].y + shift)}
                aa = project_anchors(changed, changed_sources, contract["max_proxy_offset_m"])
                jj, ss, bb, cc = compare_notice(changed, {o: aa[o]["node"] for o in origins},
                                               aa["S"]["node"], aa["A"]["node"], contract["candidate_radius_from_S_m"])
                sensitivity.append({"requested_shift_m": shift,
                                    "projected_endpoint_displacement_m": math.hypot(aa["A"]["x"] - anchors["A"]["x"], aa["A"]["y"] - anchors["A"]["y"]),
                                    "best": bb, "journeys": jj,
                                    "fixed_main_candidate": next((c for c in ss if c["candidate"] == best["candidate"]), None)})
            output["modes"][mode]["endpoint_sensitivity"] = sensitivity
    output["versions"] = {"networkx": nx.__version__, "geopandas": gpd.__version__,
                          "pyproj": pyproj.__version__, "PROJ": pyproj.proj_version_str,
                          "pandas": pd.__version__}
    for package in ("numpy", "shapely", "pyogrio", "openpyxl", "matplotlib"):
        output["versions"][package] = importlib.metadata.version(package)
    (ROOT / "requirements.txt").write_text("\n".join(
        f"{name}=={version}" for name, version in output["versions"].items() if name != "PROJ") + "\n", encoding="utf-8")
    output["raw_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((ROOT / "raw").iterdir()) if p.is_file()}
    (ROOT / "analysis_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({m: {"status": r["status"], "candidates": r.get("candidate_count", 0),
                         "best_max_E_m": r.get("best", {}).get("max_E_m") if r.get("best") else None}
                      for m, r in output["modes"].items()}, ensure_ascii=True))


def plot_result(graph, anchors, best, baseline, journeys, contract):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, (ax, bar) = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={"width_ratios": [1.3, 1]})
    segments = [[(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
                for u, v in graph.edges]
    ax.add_collection(LineCollection(segments, colors="#d6dbdf", linewidths=.5))
    colors = ["#235789", "#3b8065", "#8b5a9c"]
    for j, color in zip(journeys, colors):
        route = j["direct"]["path"]
        ax.plot([graph.nodes[n]["x"] for n in route], [graph.nodes[n]["y"] for n in route],
                color=color, lw=1.8, alpha=.8, label=f"{j['origin']} → A")
    labels = {"O2": "O2 출구 인근", "O4": "O4 출구 인근", "O9": "O9 출구 인근",
              "S": "S 기존 승차지 인근", "A": "A 건물 앞 지도 대체점"}
    for name, p in anchors.items():
        ax.scatter(p["x"], p["y"], s=24, color="#202c39", zorder=5)
        ax.annotate(labels[name], (p["x"], p["y"]), xytext=(-5 if name == "A" else 5, 7),
                    ha="right" if name == "A" else "left", textcoords="offset points", fontsize=8)
    for score, marker, label in [(best, "*", "불리한 여정 우선 후보"), (baseline, "s", "여정 수 기준 후보")]:
        n = graph.nodes[score["candidate"]]
        ax.scatter(n["x"], n["y"], marker=marker, s=110, color="#d47721", zorder=7, label=label)
    xs = [p["x"] for p in anchors.values()]
    ys = [p["y"] for p in anchors.values()]
    ax.set_xlim(min(xs)-200, max(xs)+200)
    ax.set_ylim(min(ys)-200, max(ys)+200)
    ax.set_aspect("equal")
    ax.set_title("지도상 연결·후보 위치\n실제 승차·게시·안전 경로 안내 아님", fontsize=12)
    ax.set_xlabel("UTM 52N 동서 좌표(m)")
    ax.set_ylabel("UTM 52N 남북 좌표(m)")
    ax.legend(loc="lower right", fontsize=7)
    x = list(range(len(journeys)))
    width = .25
    bar.bar([i-width for i in x], [j["E_stop_m"] for j in journeys], width, color="#9ba7ae", label="S에서 처음 확인")
    bar.bar(x, [r["E_notice_m"] for r in baseline["rows"]], width, color="#e5b67a", label="추가 1장: 여정 수 기준")
    bar.bar([i+width for i in x], [r["E_notice_m"] for r in best["rows"]], width, color="#235789", label="추가 1장: 최악 부담 기준")
    bar.set_xticks(x, [j["origin"] for j in journeys])
    bar.set_ylabel("사전 인지 조건 대비 추가 지도 경로 길이(m)")
    bar.set_title("같은 추가 안내 수량에서의 조건부 비교", fontsize=12)
    bar.legend(fontsize=8)
    bar.spines[["top", "right"]].set_visible(False)
    fig.suptitle("8800 우회 계획 + 행사일 OSM 기록 기반 시나리오", fontsize=15)
    fig.text(.02, .025, "가정: 일반도로 보행·투영 지점·안내 인지. 현장·임시 승차지·당시 통제 미검증. © OpenStreetMap contributors (ODbL)", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .94))
    fig.savefig(ROOT / "conditional_comparison.png", dpi=180)
    plt.close(fig)


def plot_budgets(journeys, best, baseline):
    import matplotlib.pyplot as plt
    sets = {
        "known": [j["D_known_m"] for j in journeys],
        "stop_only": [j["D_stop_m"] for j in journeys],
        "coverage": [r["D_notice_m"] for r in baseline["rows"]],
        "minimax": [r["D_notice_m"] for r in best["rows"]],
    }
    # Display limits follow the observed model distances, not a clinical walking threshold.
    low = math.floor(min(min(d) for d in sets.values()) / 100) * 100 - 100
    high = math.ceil(max(max(d) for d in sets.values()) / 100) * 100 + 100
    thresholds = sorted({low, high} | {d for values in sets.values() for d in values})
    rows = [{"budget_m": b, **{k: sum(d <= b + 1e-8 for d in values) for k, values in sets.items()}}
            for b in thresholds]
    pd.DataFrame(rows).to_csv(ROOT / "budget_sensitivity.csv", index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(9, 5))
    for key, label, color, style in [
        ("known", "처음부터 대체지점을 아는 조건", "#3b8065", "--"),
        ("stop_only", "원래 승차지에서 처음 확인", "#7b8991", "-"),
        ("coverage", "추가 1장: 여정 수 기준", "#d4974d", "-"),
        ("minimax", "추가 1장: 최악 부담 기준", "#235789", "-")]:
        ax.step(thresholds, [r[key] for r in rows], where="post", label=label, color=color, linestyle=style, lw=2)
    ax.set_yticks(range(len(journeys) + 1))
    ax.set_xlabel("대체지점까지의 전체 지도 경로 길이 한도 B(m) — 임의 집단 능력 아님")
    ax.set_ylabel("한도 내 도달 가능한 시험 여정 수(전체 3개)")
    ax.set_title("안내 위치를 바꿔도 남는 대체 승차 접근 부담\n일반도로 보행·안내 인지·지도 투영 지점 가정", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", fontsize=9)
    fig.text(.02, .025, "실제 이용자·도보 허용거리·행사일 통행을 측정한 결과가 아님. 현장·정확한 임시 승차지 미검증.", fontsize=8)
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(ROOT / "budget_sensitivity.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
