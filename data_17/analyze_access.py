"""Conditional access targets and illustrative carbon arithmetic; no deployment claims."""
from pathlib import Path
import hashlib
import json
import sys

import networkx as nx
import numpy as np
import pandas as pd
import pyproj

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_13"))
from recompute_expanded import build, choose_origins, prepare, base
from policy_engine import PolicyEngine

EPA_URL = "https://www.epa.gov/greenvehicles/greenhouse-gas-emissions-typical-passenger-vehicle"
EPA_KG_PER_VEHICLE_KM = 0.400 / 1.609344


def carbon_case(target_journeys, assumed_fraction, car_km, occupants=1, factor=EPA_KG_PER_VEHICLE_KM):
    """Avoided car tailpipe component, not net savings or measured mode shift."""
    if target_journeys < 0 or not 0 <= assumed_fraction <= 1 or car_km < 0 or occupants <= 0 or factor < 0:
        raise ValueError("Invalid carbon scenario input")
    return target_journeys * assumed_fraction / occupants * car_km * factor


def decomposition(normal, known, policy):
    normal, known, policy = map(lambda x: np.asarray(x, dtype=float), (normal, known, policy))
    if not (normal.shape == known.shape == policy.shape) or np.any(policy < known - 1e-7):
        raise ValueError("Inconsistent distance arrays")
    return normal, known - normal, policy - known


def threshold_count(values, threshold):
    values = np.asarray(values, dtype=float)
    valid = values[np.isfinite(values)]
    return int((valid > threshold).sum()), len(valid)


def main():
    pyproj.network.set_network_enabled(False)
    contract, _, _, _, sources, transformer = prepare()
    raw = ROOT.parent / "data_13/raw/osm_medium_windows_response.txt"
    _, nodes, ways = base.read_osm(raw)
    entries = choose_origins(nodes, transformer, sources["S"], 500)
    graph, anchors, original = build(nodes, ways, sources, contract, entries, 0)
    previous = json.loads((ROOT.parent / "data_13/expanded_review_results.json").read_text(encoding="utf-8"))
    notices = previous["scenarios"]["medium_r500_A+0"]["policies"]["2"]["equity"]["candidates"]
    origin_nodes = {name: row["node"] for name, row in original.origins.items()}
    # Targets depend only on the existing S-A shortest path and requested S distance.
    # They are hypothetical access locations, not feasible bus-stop recommendations.
    path = nx.shortest_path(graph, original.s, original.a, weight="length_m")
    distance = nx.single_source_dijkstra_path_length(graph, original.s, weight="length_m")
    eligible = [node for node in path[1:-1] if isinstance(node, int)
                and any(d["highway"] not in {"steps", "corridor"} for _, _, d in graph.edges(node, data=True))]
    targets = {f"H{budget}": min(eligible, key=lambda n: (abs(distance[n] - budget), str(n))) for budget in (500, 1000)}
    assert len(set(targets.values())) == 2
    cases = {"official_proxy": original.a, **targets}
    inverse = pyproj.Transformer.from_crs(contract["measurement_crs"], 4326, always_xy=True)
    rows, summary, burdens, speeds, locations = [], [], [], [], []
    ref = {name: original.row(name, notices) for name in original.origins}
    for label, target in cases.items():
        engine = PolicyEngine(graph, origin_nodes, original.s, target)
        assert set(engine.origins) == set(original.origins)
        lon, lat = inverse.transform(graph.nodes[target]["x"], graph.nodes[target]["y"])
        road_names = sorted({ways[d["way_id"]].get("tags", {}).get("name", "이름 미기록")
                             for _, _, d in graph.edges(target, data=True)})
        locations.append({"scenario": label, "node": target, "longitude": lon, "latitude": lat,
                          "distance_from_S_m": distance[target], "mapped_adjacent_roads": " / ".join(road_names),
                          "bus_operation_feasibility": "not verified", "pedestrian_event_feasibility": "not verified"})
        current = []
        for name in engine.origins:
            row = engine.row(name, notices)
            normal = original.origins[name]["approach"]["length_m"]
            b, l, e = decomposition(normal, row["D_known_m"], row["D_policy_m"])
            item = {"scenario": label, "origin": name, "B_m": float(b), "L_m": float(l), "E_m": float(e),
                    "D_known_m": row["D_known_m"], "D_policy_m": row["D_policy_m"],
                    "delta_D_vs_official_proxy_m": row["D_policy_m"] - ref[name]["D_policy_m"],
                    "delta_known_vs_official_proxy_m": row["D_known_m"] - ref[name]["D_known_m"]}
            assert abs(item["B_m"] + item["L_m"] + item["E_m"] - item["D_policy_m"]) < 1e-7
            rows.append(item); current.append(item)
        frame = pd.DataFrame(current)
        summary.append({"scenario": label, "resolved": len(frame), "unresolved_of_22": 1,
                        "mean_B_m": frame.B_m.mean(), "mean_L_m": frame.L_m.mean(), "mean_E_m": frame.E_m.mean(),
                        "mean_D_known_m": frame.D_known_m.mean(), "max_D_known_m": frame.D_known_m.max(),
                        "mean_D_policy_m": frame.D_policy_m.mean(), "max_D_policy_m": frame.D_policy_m.max(),
                        "mean_L_change_vs_official_proxy_m": frame.L_m.mean() - (pd.Series([r["D_known_m"] for r in ref.values()]).mean() - frame.B_m.mean()),
                        "better_policy_journeys": int((frame.delta_D_vs_official_proxy_m < -1e-7).sum()),
                        "worse_policy_journeys": int((frame.delta_D_vs_official_proxy_m > 1e-7).sum())})
        for column in ("D_known_m", "D_policy_m"):
            for cutoff in (500, 1000, 1500):
                count, valid = threshold_count(frame[column], cutoff)
                burdens.append({"scenario": label, "distance_type": column, "planning_threshold_m": cutoff,
                                "above_threshold": count, "resolved_denominator": valid,
                                "unresolved_of_22": 1, "fraction_of_resolved": count / valid})
            for speed in (0.5, 0.8, 1.2):
                speeds.append({"scenario": label, "distance_type": column, "assumed_speed_m_s": speed,
                               "mean_minutes": frame[column].mean() / speed / 60,
                               "max_minutes": frame[column].max() / speed / 60})
    carbon = [{"target_journeys_assumed": 100, "avoided_car_fraction_assumed": fraction,
               "car_km_assumed": km, "occupants_assumed": 1,
               "kg_CO2_per_vehicle_km_US_EPA_reference": EPA_KG_PER_VEHICLE_KM,
               "avoided_car_tailpipe_component_kg_CO2": carbon_case(100, fraction, km)}
              for fraction in (0, 0.01, 0.03, 0.05) for km in (2, 5, 10)]
    for name, records in (("location_journeys", rows), ("location_summary", summary), ("hypothetical_locations", locations),
                          ("distance_thresholds", burdens), ("walking_speed_scenarios", speeds), ("carbon_scenarios", carbon)):
        pd.DataFrame(records).to_csv(ROOT / f"{name}.csv", index=False, encoding="utf-8-sig")
    output = {"status": "hypothetical target locations and illustrative arithmetic, not operational alternatives or observed effects",
              "targets_rule": "Existing non-step/corridor OSM node on official-proxy S-A shortest path nearest S distances 500/1000m; no outcome-based selection",
              "fixed_notices": notices, "common_resolved_origins": 21, "unresolved_of_22": 1,
              "distance_thresholds": "500/1000/1500m are analyst-selected planning sensitivity values, not disability cutoffs",
              "speeds": "0.5/0.8/1.2 m/s are assumed sensitivity values, not group measurements; walking only, no waiting or crossing delay",
              "EPA_reference": {"url": EPA_URL, "checked_on": "2026-10-17", "source_g_CO2_per_mile": 400,
                                "mile_km": 1.609344, "scope": "US typical passenger vehicle tailpipe CO2; not Korean fleet or lifecycle"},
              "carbon_scope": "100 target journeys, one occupant; 0/1/3/5% preventable car switching and 2/5/10km all assumed. Only avoided car component; subtract additional bus/shuttle/operations to assess net savings.",
              "input_sha256": {str(raw.relative_to(ROOT.parent)): hashlib.sha256(raw.read_bytes()).hexdigest()},
              "locations": locations, "summary": summary}
    (ROOT / "access_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
