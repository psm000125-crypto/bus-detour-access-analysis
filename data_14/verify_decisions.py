"""Cross-file checks of new decision results against the unchanged older model."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
TOL = 1e-7


def main():
    result = json.loads((ROOT / "decision_results.json").read_text(encoding="utf-8"))
    for name, expected in result["input_sha256"].items():
        assert hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == expected, name
    budget = pd.read_csv(ROOT / "budget.csv")
    rows = pd.read_csv(ROOT / "journeys.csv")
    old = pd.read_csv(ROOT.parent / "data_13/review_recognition.csv")
    dependence = pd.read_csv(ROOT / "recognition_dependence.csv")
    assert result["selected_origins"] == 22 and result["resolved_origins"] == 21
    assert len(rows) == 84 and len(rows.origin.unique()) == 21
    assert result["equity_vs_coverage"] == {"better": 2, "same": 19, "worse": 0}
    assert abs(result["coverage_second_notice_max_distance_change_m"]) < TOL
    assert np.all(np.diff(budget.max_E_m) <= TOL)
    assert abs(budget.max_E_m.iloc[0] - 1023.0519057535764) < TOL
    for _, row in rows.iterrows():
        assert abs(row.D_policy_m - row.D_known_m - row.E_policy_m) < TOL
        assert abs(row.D_policy_m - row.B_normal_access_m - row.L_known_location_change_m - row.E_policy_m) < TOL
        assert abs(row.D_stop_m - row.D_policy_m - row.reduction_m) < TOL
        assert row.reduction_m >= -TOL
    for _, row in dependence.iterrows():
        reference = old[old.policy.eq(row.policy) & old.p_assumed.eq(row.p1_assumed)].iloc[0]
        assert abs(reference.max_expected_E_m - row.independent_max_expected_E_m) < TOL
        assert row.minimum_max_expected_E_m - TOL <= row.independent_max_expected_E_m <= row.maximum_max_expected_E_m + TOL
    decomp = pd.read_csv(ROOT / "policy_decomposition.csv").set_index("policy")
    assert decomp.loc["coverage_strong", "encountered_without_reduction"] == 8
    assert decomp.loc["equity", "encountered_without_reduction"] == 0
    assert abs(decomp.loc["equity", "known_share_of_sum_D"] - .8951606477205952) < TOL
    candidate = pd.read_csv(ROOT / "candidate_review.csv")
    assert candidate.physical_installation_permission.eq("unverified").all()
    assert candidate.pedestrian_crossing_during_event.eq("unverified").all()
    paths = pd.read_csv(ROOT / "approach_paths.csv")
    assert paths.policy.value_counts().nunique() == 1
    assert (paths.approach_length_m <= paths.original_shortest_length_m * 1.2 + TOL).all()
    assert (paths.approach_length_m <= paths.original_shortest_length_m + 100 + TOL).all()
    main_paths = paths[paths.path_index.eq(0)].merge(rows, on=["policy", "origin"], suffixes=("_path", "_main"))
    assert (abs(main_paths.E_policy_m_path - main_paths.E_policy_m_main) < TOL).all()
    report = {"status": "passed computational and cross-file checks; geographic and field validity remain unverified",
              "recognition_independent_rows_matched": len(dependence), "journeys_checked": len(rows),
              "modeled_origins": 21, "unresolved_origins_retained": 1,
              "approach_path_cases_per_policy": int(paths.policy.value_counts().iloc[0]),
              "same_event_additional_sources_are_not_replications": True,
              "output_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(ROOT.glob("*.csv"))}}
    (ROOT / "verification_decisions.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
