"""Decision analysis of staged conditional journeys, not observed policy effects."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import networkx as nx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_13"))
from recompute_expanded import build, choose_origins, prepare, base

TOL = 1e-7
SCENARIO = "medium_r500_A+0"


def joint_weights(p1, p2, q):
    """q=P(both read); flag order is 00, 01, 10, 11."""
    if not 0 <= p1 <= 1 or not 0 <= p2 <= 1:
        raise ValueError("Recognition marginals must lie in [0,1]")
    lower, upper = max(0.0, p1 + p2 - 1), min(p1, p2)
    if q < lower - TOL or q > upper + TOL:
        raise ValueError("Joint probability violates Frechet bounds")
    q = min(upper, max(lower, q))
    return np.array([1 - p1 - p2 + q, p2 - q, p1 - q, q])


def maximum_expectation_bounds(states, p1, p2):
    """Exact min/max over a common q of max_i E[E_i], not E[max_i E_i]."""
    states = np.asarray(states, dtype=float)
    if states.ndim != 2 or states.shape[1] != 4 or not len(states):
        raise ValueError("states must be a nonempty n-by-4 matrix")
    lower, upper = max(0.0, p1 + p2 - 1), min(p1, p2)
    intercept = states @ joint_weights(p1, p2, lower)
    slope = states[:, 0] - states[:, 1] - states[:, 2] + states[:, 3]
    # The maximum of affine lines is convex and piecewise linear. Its minimum
    # lies at a bound or a line crossing; its maximum lies at a bound.
    qs = [lower, upper]
    for i, j in itertools.combinations(range(len(states)), 2):
        delta = slope[i] - slope[j]
        if abs(delta) > TOL:
            q = lower + (intercept[j] - intercept[i]) / delta
            if lower <= q <= upper:
                qs.append(q)
    value = lambda q: float(np.max(states @ joint_weights(p1, p2, q)))
    minimum_q = min(qs, key=lambda q: (value(q), q))
    return {"q_lower": lower, "q_upper": upper, "minimum_q": minimum_q,
            "minimum_max_expected_E_m": value(minimum_q),
            "maximum_max_expected_E_m": max(value(lower), value(upper)),
            "independent_max_expected_E_m": value(p1 * p2)}


def policy_arrays(engine, candidates):
    return np.array([[engine.row(name, [node for node, flag in zip(candidates, flags) if flag])["E_policy_m"]
                      for flags in itertools.product((False, True), repeat=2)] for name in engine.origins])


def path_outcome(engine, name, path, candidates):
    if path[0] != engine.origins[name]["node"] or path[-1] != engine.s:
        raise ValueError("Approach path must connect its origin to the original stop")
    prefix, first = 0.0, None
    for index, node in enumerate(path[:-1]):
        if node in candidates:
            first = node
            break
        prefix += engine.graph[node][path[index + 1]]["length_m"]
    approach_length = nx.path_weight(engine.graph, path, "length_m")
    distance = approach_length + engine.to_a[engine.s] if first is None else prefix + engine.to_a[first]
    known = engine.origins[name]["D_known_m"]
    return {"approach_length_m": approach_length, "first_notice": first,
            "D_policy_m": distance, "E_policy_m": max(0.0, distance - known)}


def alternative_approaches(engine, policies):
    """Original approach plus up to two near-shortest simple paths per origin.

    At most three generated paths are inspected. Keep paths within both 20%
    and 100m of the original shortest length; this is a bounded local stress
    test, not exhaustive route uncertainty or a model of observed route choice.
    """
    rows = []
    for name, origin in engine.origins.items():
        original = origin["approach"]["path"]
        shortest_length = origin["approach"]["length_m"]
        limit = min(shortest_length * 1.2, shortest_length + 100)
        paths = [original]
        generated = nx.shortest_simple_paths(engine.graph, origin["node"], engine.s, weight="length_m")
        for path in itertools.islice(generated, 3):
            if path in paths:
                continue
            if nx.path_weight(engine.graph, path, "length_m") > limit + TOL:
                break
            paths.append(path)
            if len(paths) == 3:
                break
        for index, path in enumerate(paths):
            for key, policy in policies.items():
                rows.append({"origin": name, "path_index": index, "policy": key,
                             "path_nodes_json": json.dumps(path), "paths_for_origin": len(paths),
                             "original_shortest_length_m": shortest_length,
                             **path_outcome(engine, name, path, policy["candidates"])})
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "approach_paths.csv", index=False, encoding="utf-8-sig")
    summary = [{"policy": key, "path_cases": len(group), "origins_with_alternatives": int(group[group.path_index.gt(0)].origin.nunique()),
                "max_E_m": float(group.E_policy_m.max()), "max_D_m": float(group.D_policy_m.max())}
               for key, group in frame.groupby("policy")]
    pivot = frame.pivot(index=["origin", "path_index"], columns="policy", values="D_policy_m")
    delta = pivot.equity - pivot.coverage_strong
    return {"rule": "Original path plus up to two alternatives from first three shortest simple paths, within both 20% and 100m additional approach; fixed selected policies, full recognition",
            "policies": summary,
            "equity_vs_coverage_path_cases": {"better": int((delta < -TOL).sum()), "same": int((abs(delta) <= TOL).sum()), "worse": int((delta > TOL).sum())}}


def main():
    contract, _, _, _, sources, transformer = prepare()
    _, nodes, ways = base.read_osm(ROOT.parent / "data_13/raw/osm_medium_windows_response.txt")
    entries = choose_origins(nodes, transformer, sources["S"], 500)
    graph, anchors, engine = build(nodes, ways, sources, contract, entries, 0)
    previous = json.loads((ROOT.parent / "data_13/expanded_review_results.json").read_text(encoding="utf-8"))
    selected = previous["scenarios"][SCENARIO]["policies"]
    journeys = pd.read_csv(ROOT.parent / "data_13/review_journeys.csv")
    main_rows = journeys[journeys.scenario.eq(SCENARIO) & journeys.K.eq(2)]
    assert len(engine.origins) == 21 and len(entries) == 22
    for key, policy in selected["2"].items():
        for _, row in main_rows[main_rows.policy.eq(key) & main_rows.status.eq("conditional")].iterrows():
            assert abs(engine.row(row.origin, policy["candidates"])["E_policy_m"] - row.E_policy_m) < TOL

    baseline = engine.score(())
    budget = []
    for k, policy in [(0, baseline), (1, selected["1"]["equity"]), (2, selected["2"]["equity"])]:
        rows = [engine.row(name, policy["candidates"]) for name in engine.origins]
        budget.append({"additional_notices": k, **engine.score(policy["candidates"]),
                       "improved_journeys": sum(r["reduction_m"] > TOL for r in rows),
                       "max_E_reduction_vs_stop_m": baseline["max_E_m"] - policy["max_E_m"],
                       "mean_E_m": float(np.mean([r["E_policy_m"] for r in rows]))})
    for i, row in enumerate(budget):
        row["marginal_max_E_reduction_m"] = None if i == 0 else budget[i-1]["max_E_m"] - row["max_E_m"]
    pd.DataFrame(budget).to_csv(ROOT / "budget.csv", index=False, encoding="utf-8-sig")

    distributions, coverage, failures, correlation = [], [], [], []
    cover_rows = {name: engine.row(name, selected["2"]["coverage_strong"]["candidates"]) for name in engine.origins}
    for key, policy in selected["2"].items():
        rows = [engine.row(name, policy["candidates"]) for name in engine.origins]
        for row in rows:
            normal = engine.origins[row["origin"]]["approach"]["length_m"]
            row["B_normal_access_m"] = normal
            row["L_known_location_change_m"] = row["D_known_m"] - normal
        coverage.append({"policy": key, "encountered": sum(r["first_notice"] is not None for r in rows),
                         "improved": sum(r["reduction_m"] > TOL for r in rows),
                         "encountered_without_reduction": sum(r["first_notice"] is not None and r["reduction_m"] <= TOL for r in rows),
                         "mean_D_known_m": float(np.mean([r["D_known_m"] for r in rows])),
                         "mean_D_stop_m": float(np.mean([r["D_stop_m"] for r in rows])),
                         "mean_D_policy_m": float(np.mean([r["D_policy_m"] for r in rows])),
                         "mean_B_normal_access_m": float(np.mean([r["B_normal_access_m"] for r in rows])),
                         "mean_L_known_location_change_m": float(np.mean([r["L_known_location_change_m"] for r in rows])),
                         "mean_E_m": float(np.mean([r["E_policy_m"] for r in rows])),
                         "max_D_m": max(r["D_policy_m"] for r in rows),
                         "known_share_of_sum_D": sum(r["D_known_m"] for r in rows) / sum(r["D_policy_m"] for r in rows),
                         "location_share_of_added_distance": sum(r["L_known_location_change_m"] for r in rows) / sum(r["D_policy_m"] - r["B_normal_access_m"] for r in rows)})
        for row in rows:
            distributions.append({"policy": key, **row,
                                  "delta_vs_coverage_m": row["D_policy_m"] - cover_rows[row["origin"]]["D_policy_m"]})
        for excluded in policy["candidates"]:
            remaining = [n for n in policy["candidates"] if n != excluded]
            failures.append({"policy": key, "unavailable_notice": excluded, **engine.score(remaining)})
        states = policy_arrays(engine, policy["candidates"])
        for p in (0, .25, .5, .75, 1):
            correlation.append({"policy": key, "p1_assumed": p, "p2_assumed": p,
                                **maximum_expectation_bounds(states, p, p)})
    for filename, rows in [("policy_decomposition.csv", coverage), ("journeys.csv", distributions),
                           ("notice_unavailable.csv", failures), ("recognition_dependence.csv", correlation)]:
        pd.DataFrame(rows).to_csv(ROOT / filename, index=False, encoding="utf-8-sig")

    candidate_rows = []
    used = set(n for policy in selected["2"].values() for n in policy["candidates"])
    for node in sorted(used):
        incident = list(graph.edges(node, data=True))
        road_names = sorted({ways[d["way_id"]].get("tags", {}).get("name", "이름 미기록") for _, _, d in incident})
        candidate_rows.append({"candidate_osm_node": node, "lon": nodes[node]["lon"], "lat": nodes[node]["lat"],
                               "mapped_road_names": " / ".join(road_names),
                               "mapped_highway_types": " / ".join(sorted({d["highway"] for _, _, d in incident})),
                               "physical_installation_permission": "unverified", "directional_visibility": "unverified",
                               "pedestrian_crossing_during_event": "unverified", "safe_waiting_space": "unverified"})
    pd.DataFrame(candidate_rows).to_csv(ROOT / "candidate_review.csv", index=False, encoding="utf-8-sig")
    approaches = alternative_approaches(engine, selected["2"])

    equity = [r for r in distributions if r["policy"] == "equity"]
    coverage1 = [engine.row(name, selected["1"]["coverage_strong"]["candidates"]) for name in engine.origins]
    duplicate_notice_gain = max(abs(r["D_policy_m"] - cover_rows[r["origin"]]["D_policy_m"]) for r in coverage1)
    inputs = [ROOT.parent / "data_13/expanded_review_results.json", ROOT.parent / "data_13/review_journeys.csv",
              ROOT.parent / "data_13/raw/osm_medium_windows_response.txt", Path(__file__)]
    result = {"status": "conditional decision analysis; no field validation or observed policy effects",
              "selected_origins": 22, "resolved_origins": 21, "unresolved_origins": engine.unresolved,
              "max_D_known_m": max(r["D_known_m"] for r in equity),
              "first_notice_share_of_two_notice_max_E_reduction": budget[1]["max_E_reduction_vs_stop_m"] / budget[2]["max_E_reduction_vs_stop_m"],
              "coverage_second_notice_max_distance_change_m": duplicate_notice_gain,
              "equity_vs_coverage": {"better": sum(r["delta_vs_coverage_m"] < -TOL for r in equity),
                                     "same": sum(abs(r["delta_vs_coverage_m"]) <= TOL for r in equity),
                                     "worse": sum(r["delta_vs_coverage_m"] > TOL for r in equity)},
              "unknown_demand_interpretation": "At full recognition, the equity two-notice policy weakly dominates the coverage policy for every modeled journey. Therefore no nonnegative weighting of these same 21 rows reverses the weighted distance comparison. This does not identify passenger counts, protect unresolved/unmodeled journeys, or establish recognition/geographic robustness.",
              "budget": budget, "decomposition": coverage,
              "alternative_approaches": approaches,
              "recognition_dependence": correlation, "notice_unavailable": failures,
              "input_sha256": {str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}}
    (ROOT / "decision_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plot_budget(budget)
    print(json.dumps({"budget": budget, "dominance": result["equity_vs_coverage"],
                      "p05": [r for r in correlation if r["p1_assumed"] == .5]}, ensure_ascii=True, indent=2))


def plot_budget(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(7.6, 3.2))
    ax.bar([r["additional_notices"] for r in rows], [r["max_E_m"] for r in rows], color=["#929da8", "#3b7898", "#245879"], width=.55)
    for row in rows:
        ax.text(row["additional_notices"], row["max_E_m"] + 20, f'{row["max_E_m"]:.0f}m', ha="center")
    ax.set_xticks([0, 1, 2], ["기존 정류소 안내만", "추가 1곳", "추가 2곳"])
    ax.set_ylabel("21개 계산 가능 여정 중 최대 E(m)")
    ax.set_ylim(0, 1180)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("최대 추가길이 우선: 첫 안내 357m · 둘째 안내 16m 감소")
    fig.text(.02, .01, "일반도로 보행·고정 접근·모든 안내 인지 가정. 실제 보행·비용·승객 효과 아님. © OpenStreetMap contributors", fontsize=7)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(ROOT / "budget_frontier.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
