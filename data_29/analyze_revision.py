"""Archived 21-origin explanation only; not the current 22-origin analysis.

Run reanalyze_platforms.py for the report. Outputs here have legacy_ prefixes
so that this old explanatory audit cannot overwrite revised results.
"""
from pathlib import Path
import hashlib
import json
import sys
import networkx as nx
import pandas as pd
import pyproj

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data_13"))
from recompute_expanded import prepare, build, choose_origins, base


def main():
    pyproj.network.set_network_enabled(False)
    contract, _, _, _, sources, transformer = prepare()
    raw = ROOT.parent / "data_13/raw/osm_medium_windows_response.txt"
    _, nodes, ways = base.read_osm(raw)
    entries = choose_origins(nodes, transformer, sources["S"], 500)
    graph, anchors, engine = build(nodes, ways, sources, contract, entries, 0)
    labels = {r["origin"]: r["label"] for r in entries}
    journeys = pd.read_csv(ROOT.parent / "data_14/journeys.csv")
    comp = journeys[journeys.policy.eq("coverage_strong")].merge(
        journeys[journeys.policy.eq("equity")], on="origin", suffixes=("_coverage", "_worst"))
    comp["label"] = comp.origin.map(labels)
    comp["reduction_vs_coverage_m"] = comp.D_policy_m_coverage - comp.D_policy_m_worst
    comp.to_csv(ROOT / "legacy_same_two_signs_by_origin.csv", index=False, encoding="utf-8-sig")
    barrier_rows = []
    for entry in entries:
        origin = entry["origin"]
        direct = base.shortest(graph, anchors[origin]["node"], engine.a)
        if direct is None:
            continue
        stair_edges = [(u, v, graph[u][v]) for u, v in zip(direct["path"], direct["path"][1:]) if graph[u][v]["steps"]]
        if not stair_edges:
            continue
        wid_list = sorted({d["way_id"] for _, _, d in stair_edges})
        barrier_rows.append({"origin": origin, "label": entry["label"],
                             "mapped_stair_length_m": sum(d["length_m"] for _, _, d in stair_edges),
                             "stair_way_ids": wid_list,
                             "stair_tags": {str(w): ways[w].get("tags", {}) for w in wid_list},
                             "stair_node_ids": sorted({n for u, v, _ in stair_edges for n in (u, v) if isinstance(n, int)}),
                             "baseline_length_m": direct["length_m"]})
    (ROOT / "legacy_barrier_details.json").write_text(json.dumps(barrier_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    budget = pd.read_csv(ROOT.parent / "data_14/budget.csv")
    after = budget.loc[budget.additional_notices.eq(2)].iloc[0]
    one = budget.loc[budget.additional_notices.eq(1)].iloc[0]
    affected = comp[comp.reduction_vs_coverage_m.gt(1e-7)]
    output = {"same_two_signs_improved_origins": affected[["origin", "label", "E_policy_m_coverage", "E_policy_m_worst", "reduction_vs_coverage_m"]].to_dict("records"),
              "same_two_signs_unchanged": int(comp.reduction_vs_coverage_m.abs().lt(1e-7).sum()),
              "coverage_encounter_without_distance_reduction": int(((comp.reduction_m_coverage.abs() < 1e-7) & comp.first_notice_coverage.notna()).sum()),
              "second_sign_max_delay_improvement_m": float(one.max_E_m - after.max_E_m),
              "second_sign_additional_improved_origins": int(after.improved_journeys - one.improved_journeys),
              "barrier_origins": barrier_rows,
              "scope": "Explanatory audit of existing fixed-anchor scenarios; not new field measurements or a repaired routing network.",
              "input_sha256": {str(raw.relative_to(ROOT.parent)): hashlib.sha256(raw.read_bytes()).hexdigest()}}
    (ROOT / "legacy_explanation_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
