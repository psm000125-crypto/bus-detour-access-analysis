"""Reproducible conditional graph analysis, offline after source acquisition.

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
