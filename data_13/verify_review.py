"""Validate traceability and numerical consistency, never geographic ground truth."""
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parent
TOL=1e-7


def main():
    output=json.loads((ROOT/"expanded_review_results.json").read_text(encoding="utf-8"))
    rows=pd.read_csv(ROOT/"review_journeys.csv")
    summary=pd.read_csv(ROOT/"review_policy_summary.csv")
    recognition=pd.read_csv(ROOT/"review_recognition_journeys.csv")
    origins=pd.read_csv(ROOT/"review_origin_selection.csv")
    assert origins.osm_node_id.is_unique and len(origins)==22
    for relative,digest in output["input_sha256"].items():
        assert hashlib.sha256((ROOT.parent/relative).read_bytes()).hexdigest()==digest,relative
    for record in summary.to_dict("records"):
        subset=rows[(rows.scenario==record["scenario"])&(rows.K==record["K"])&(rows.policy==record["policy"])]
        valid=subset[subset.status=="conditional"]
        assert len(subset)==record["selected"] and len(valid)==record["resolved"]
        assert subset.origin.is_unique
        assert int((subset.status!="conditional").sum())==record["unresolved"]==1
        assert pd.isna(record["all_origin_max_E_m"]) and pd.isna(record["all_origin_max_D_m"])
        assert abs(valid.E_policy_m.max()-record["max_E_m"])<TOL
        assert abs(valid.E_policy_m.sum()-record["sum_E_m"])<TOL
        assert abs(valid.D_policy_m.max()-record["max_D_m"])<TOL
        assert (valid.reduction_m>=-TOL).all()
    main=summary[(summary.scenario=="medium_r500_A+0")&(summary.K==2)].set_index("policy")
    old=summary[(summary.scenario=="original_r500_A+0")&(summary.K==2)].set_index("policy")
    for metric in ("max_E_m","sum_E_m","max_D_m"):
        assert ((main[metric]-old[metric]).abs()<TOL).all()
    for name,input_info in output["input_comparison"].items():
        assert input_info["shared_original_way_changes"]==0
        assert input_info["shared_original_node_coordinate_changes"]==0
    assert output["input_comparison"]["medium"]["circle_clearance_m"]>500
    assert output["input_comparison"]["medium"]["qualifying_origin_ids"]==output["input_comparison"]["original"]["qualifying_origin_ids"]
    assert output["pedestrian_only"]["resolved"]==0
    assert output["isolated_entrance_3390524793"]["nodes"]==7
    main_rows=rows[(rows.scenario=="medium_r500_A+0")&(rows.K==2)&(rows.status=="conditional")]
    cov=main_rows[main_rows.policy=="coverage_strong"].set_index("origin")
    eq=main_rows[main_rows.policy=="equity"].set_index("origin")
    difference=eq.E_policy_m-cov.E_policy_m
    assert int((difference < -TOL).sum())==2
    assert int((difference > TOL).sum())==0
    recognition_comparisons=[]
    for p in sorted(recognition.p_assumed.unique()):
        part=recognition[recognition.p_assumed==p]
        coverage=part[part.policy=="coverage_strong"].set_index("origin").expected_E_m
        equity=part[part.policy=="equity"].set_index("origin").expected_E_m
        delta=equity-coverage
        recognition_comparisons.append({"p_assumed":float(p),"better":int((delta < -TOL).sum()),
                                       "same":int((delta.abs()<=TOL).sum()),"worse":int((delta > TOL).sum())})
        if p==0:
            assert (delta.abs()<TOL).all()
        assert (delta<=TOL).all()
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted((ROOT/"raw").iterdir()) if p.is_file()}
    (ROOT/"raw_sha256.json").write_text(json.dumps(files,indent=2)+"\n",encoding="utf-8")
    report={"status":"passed computational consistency and input-integrity checks; pedestrian validity remains unresolved",
            "selected":22,"resolved":21,"unresolved":1,"candidate_count":53,"two_notice_combinations":1378,
            "boundary_comparison":"same selected IDs and policy metrics between original and enlarged archived extracts",
            "same_budget_equity_vs_coverage":{"better":2,"same":19,"worse":0},
            "hypothetical_recognition_comparison":recognition_comparisons,
            "unresolved_major_limitations":["Actual pedestrian connectivity and event controls","Historical temporary boarding kerb",
                                             "Passenger demand and notice recognition","Additional larger extract timed out"],
            "raw_files_hashed":len(files)}
    (ROOT/"verification_review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=="__main__":main()
