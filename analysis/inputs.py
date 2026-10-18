"""Load archived sources and preserve fixed projection and access rules."""
from pathlib import Path
import json
import pandas as pd
import pyproj
from shapely.geometry import Point, Polygon
from . import network as base

DATA = Path(__file__).resolve().parents[1] / "data"
TOL = 1e-7

def prepare():
    contract = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
    raw, nodes, ways = base.read_osm(DATA / contract["osm_source"])
    transformer = pyproj.Transformer.from_crs(4326, contract["measurement_crs"], always_xy=True)
    stops = pd.read_csv(DATA / "stops.csv", dtype=str).set_index("ARS_ID")
    stop = stops.loc[contract["original_stop"]["ars_id"]]
    sources = {o["id"]: Point(transformer.transform(nodes[o["osm_node_id"]]["lon"], nodes[o["osm_node_id"]]["lat"]))
               for o in contract["origins"]}
    sources["S"] = Point(transformer.transform(float(stop["X좌표"]), float(stop["Y좌표"])))
    sources["A"] = Polygon([transformer.transform(nodes[i]["lon"], nodes[i]["lat"])
                              for i in ways[contract["alternative"]["osm_building_way_id"]]["nodes"]]).centroid
    return contract, raw, nodes, ways, sources, transformer

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
