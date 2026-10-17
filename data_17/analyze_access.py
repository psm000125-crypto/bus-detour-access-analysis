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

DOMESTIC_URL = "https://env-info.kr/v2/publish/testfiles/2024년%20환경정보공개제도%20등록%20가이드라인.pdf"
GASOLINE_NET_HEAT_MJ_PER_L = 30.4
GASOLINE_CO2_KG_PER_TJ = 69300
ASSUMED_FUEL_ECONOMY_KM_PER_L = 15


def gasoline_kg_per_vehicle_km(fuel_economy):
    """Domestic guideline fuel factor with explicitly assumed economy; CO2 only."""
    if not np.isfinite(fuel_economy) or fuel_economy <= 0:
        raise ValueError("Fuel economy must be positive and finite")
    return GASOLINE_NET_HEAT_MJ_PER_L * GASOLINE_CO2_KG_PER_TJ / 1e6 / fuel_economy


def carbon_case(target_journeys, assumed_fraction, car_km, occupants=1, factor=None):
    """Avoided car tailpipe component, not net savings or measured mode shift."""
    if factor is None:
        factor = gasoline_kg_per_vehicle_km(ASSUMED_FUEL_ECONOMY_KM_PER_L)
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
    rows, summary, burdens, speeds, locations, tail_checks = [], [], [], [], [], []
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
        if label == "H1000":
            tail_length = nx.shortest_path_length(graph, target, original.a, weight="length_m")
            for item in current:
                original_row = ref[item["origin"]]
                known_reduction = original_row["D_known_m"] - item["D_known_m"]
                policy_reduction = original_row["D_policy_m"] - item["D_policy_m"]
                residual = max(abs(known_reduction - tail_length), abs(policy_reduction - tail_length))
                assert residual < 1e-7
                tail_checks.append({"origin": item["origin"], "shared_tail_length_m": tail_length,
                                    "D_known_reduction_m": known_reduction, "D_policy_reduction_m": policy_reduction,
                                    "E_change_m": item["E_m"] - original_row["E_policy_m"], "max_residual_m": residual})
        summary.append({"scenario": label, "resolved": len(frame), "unresolved_of_22": 1,
                        "mean_B_m": frame.B_m.mean(), "mean_L_m": frame.L_m.mean(), "mean_E_m": frame.E_m.mean(),
                        "mean_D_known_m": frame.D_known_m.mean(), "max_D_known_m": frame.D_known_m.max(),
                        "mean_D_policy_m": frame.D_policy_m.mean(), "max_D_policy_m": frame.D_policy_m.max(),
                        "mean_L_change_vs_official_proxy_m": frame.L_m.mean() - (pd.Series([r["D_known_m"] for r in ref.values()]).mean() - frame.B_m.mean()),
                        "better_policy_journeys": int((frame.delta_D_vs_official_proxy_m < -1e-7).sum()),
                        "worse_policy_journeys": int((frame.delta_D_vs_official_proxy_m > 1e-7).sum()),
                        "above_proposed_L500_trigger": int(frame.L_m.gt(500).sum())})
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
    carbon = [{"normalization_target_journeys": 1, "avoided_car_fraction_assumed": fraction,
               "car_km_assumed": km, "occupants_assumed": 1, "fuel_economy_km_L_assumed": economy,
               "kg_CO2_per_vehicle_km_domestic_guideline_with_assumed_economy": gasoline_kg_per_vehicle_km(economy),
               "avoided_car_CO2_g_per_target_journey": 1000 * carbon_case(1, fraction, km, factor=gasoline_kg_per_vehicle_km(economy))}
              for economy in (10, 15, 20) for fraction in (0, 0.01, 0.03, 0.05) for km in (2, 5, 10)]
    for name, records in (("location_journeys", rows), ("location_summary", summary), ("hypothetical_locations", locations),
                          ("distance_thresholds", burdens), ("walking_speed_scenarios", speeds), ("carbon_scenarios", carbon),
                          ("h1000_tail_checks", tail_checks)):
        pd.DataFrame(records).to_csv(ROOT / f"{name}.csv", index=False, encoding="utf-8-sig")
    output = {"status": "hypothetical target locations and illustrative arithmetic, not operational alternatives or observed effects",
              "targets_rule": "Existing non-step/corridor OSM node on official-proxy S-A shortest path nearest S distances 500/1000m; no outcome-based selection",
              "fixed_notices": notices, "common_resolved_origins": 21, "unresolved_of_22": 1,
              "distance_thresholds": "500/1000/1500m are analyst-selected planning sensitivity values, not disability cutoffs",
              "speeds": "0.5/0.8/1.2 m/s are assumed sensitivity values, not group measurements; walking only, no waiting or crossing delay",
              "domestic_carbon_reference": {"url": DOMESTIC_URL, "title": "2024년 환경정보공개제도 등록 가이드라인",
                  "checked_on": "2026-10-17", "printed_pages": [156, 157], "pdf_pages_one_based": [160, 161],
                  "gasoline_net_heat_MJ_L": GASOLINE_NET_HEAT_MJ_PER_L, "gasoline_CO2_kg_TJ": GASOLINE_CO2_KG_PER_TJ,
                  "assumed_economy_km_L": [10, 15, 20], "main_economy_km_L": 15,
                  "main_factor_kg_CO2_vehicle_km": gasoline_kg_per_vehicle_km(15),
                  "scope": "Fuel combustion CO2 component from domestic reporting guideline, with assumed fuel economy; not measured Korean fleet average, CH4/N2O or lifecycle"},
              "carbon_scope": "Per target journey, one occupant; 0/1/3/5% preventable car switching, 2/5/10km and 10/15/20km/L all assumed. Only avoided car CO2 component; multiply by measured target journeys and subtract additional operations for net savings.",
              "h1000_tail_verification": {"checked_origins": len(tail_checks), "tail_length_m": tail_checks[0]["shared_tail_length_m"],
                  "max_residual_m": max(row["max_residual_m"] for row in tail_checks)},
              "proposed_policy_trigger": "Attach mitigation plan if per-origin known destination access minus original-stop access exceeds 500m, or safety/step-free route remains unverified. Analyst-proposed review trigger, not a legal or disability limit; distinct from H500 location selection.",
              "input_sha256": {str(raw.relative_to(ROOT.parent)): hashlib.sha256(raw.read_bytes()).hexdigest()},
              "locations": locations, "summary": summary}
    (ROOT / "access_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
