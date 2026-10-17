"""Recompute the declared policies on independently enlarged archived extracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import networkx as nx
import pandas as pd
import pyproj
from shapely.geometry import Point

from audit_robustness import ROOT, TOL, base, choose_origins, difference, prepare, query_polygon
from evaluate_policies import evaluate_journey
from policy_engine import PolicyEngine


def build(nodes,ways,sources,contract,entries,shift,mode="street_assumed"):
    points={e["origin"]:Point(e["x"],e["y"]) for e in entries}
    points.update(S=sources["S"],A=Point(sources["A"].x,sources["A"].y+shift))
    graph,_=base.make_graph(nodes,ways,mode,contract["measurement_crs"])
    anchors=base.project_anchors(graph,points,100)
    if not anchors["S"]["eligible"] or not anchors["A"]["eligible"]:
        return graph,anchors,None
    origins={e["origin"]:anchors[e["origin"]]["node"] for e in entries if anchors[e["origin"]]["eligible"]}
    return graph,anchors,PolicyEngine(graph,origins,anchors["S"]["node"],anchors["A"]["node"])


def rows_for(engine,entries,candidates):
    return [{"origin":e["origin"],"osm_node_id":e["osm_node_id"],"label":e["label"],
             **(engine.row(e["origin"],candidates) if e["origin"] in engine.origins else {"status":"mapped_disconnection_or_proxy_out_of_range"})}
            for e in entries]


def main():
    pyproj.network.set_network_enabled(False)
    contract,raw0,n0,w0,sources,transformer=prepare()
    review=json.loads((ROOT/"review_contract.json").read_text(encoding="utf-8"))
    paths={"original":ROOT.parent/"data_10/raw/osm_20260405.json",
           "medium":ROOT/"raw/osm_medium_windows_response.txt"}
    large=ROOT/"raw/osm_large_retry_response.txt"
    if large.exists():
        try:
            candidate=json.loads(large.read_text(encoding="utf-8"))
            if isinstance(candidate.get("elements"),list) and not candidate.get("remark"):
                paths["large"]=large
        except (ValueError,UnicodeError):
            pass
    extracts={name:base.read_osm(path) for name,path in paths.items()}
    entries=choose_origins(extracts["medium"][1],transformer,sources["S"],500)
    # Circle extent coverage is measured separately from actual completeness of mapping.
    extent_clearance={name:sources["S"].distance(query_polygon(transformer,review["extents_south_west_north_east"][name]).boundary)
                      for name in paths}
    assert extent_clearance["medium"]>500+100
    pd.DataFrame([{**e,"tags":json.dumps(e["tags"],ensure_ascii=False)} for e in entries]).to_csv(
        ROOT/"review_origin_selection.csv",index=False,encoding="utf-8-sig")
    input_comparison={}
    for name,(_,nodes,ways) in extracts.items():
        input_comparison[name]={"nodes":len(nodes),"ways":len(ways),
                                "circle_clearance_m":extent_clearance[name],
                                "qualifying_origin_ids":[e["osm_node_id"] for e in choose_origins(nodes,transformer,sources["S"],500)],
                                "shared_original_way_count":len(w0.keys()&ways.keys()),
                                "shared_original_way_changes":sum({k:w0[i].get(k) for k in ("nodes","tags")}!={k:ways[i].get(k) for k in ("nodes","tags")} for i in w0.keys()&ways.keys()),
                                "shared_original_node_coordinate_changes":sum((n0[i]["lon"],n0[i]["lat"])!=(nodes[i]["lon"],nodes[i]["lat"]) for i in n0.keys()&nodes.keys()),
                                "server_metadata":extracts[name][0].get("osm3s")}
    summaries,journey_rows,comparisons,fixed,recognition,recognition_rows,scenario_meta=[],[],[],[],[],[],{}
    main_policies=None
    # Run the main enlarged extract first so every sensitivity can keep its policies fixed.
    specifications=[("medium",500,0),("original",500,0)]
    if "large" in extracts:
        specifications.append(("large",500,0))
    specifications += [("medium",500,-20),("medium",500,20),("medium",400,0),("medium",300,0)]
    for extent,radius,shift in specifications:
        raw,nodes,ways=extracts[extent]
        chosen=[e for e in entries if e["radius_distance_m"]<=radius+TOL]
        graph,anchors,engine=build(nodes,ways,sources,contract,chosen,shift)
        scenario=f"{extent}_r{radius}_A{shift:+d}"
        policies,counts={},{}
        for k in (1,2):
            policies[str(k)],counts[str(k)]=engine.fit(k)
        if main_policies is None:
            main_policies=policies
        unresolved=[e["osm_node_id"] for e in chosen if e["origin"] not in engine.origins]
        scenario_meta[scenario]={"selected":len(chosen),"resolved":len(engine.origins),"unresolved_ids":unresolved,
                                 "candidate_count":len(engine.candidates),"combinations":counts,
                                 "projected_A":anchors["A"],"policies":policies}
        for k,pset in policies.items():
            evaluated={key:rows_for(engine,chosen,policy["candidates"]) for key,policy in pset.items()}
            for key,policy in pset.items():
                valid=[r for r in evaluated[key] if r["status"]=="conditional"]
                record={"scenario":scenario,"extent":extent,"radius_m":radius,"A_shift_m":shift,"K":int(k),"policy":key,
                        "selected":len(chosen),"resolved":len(valid),"unresolved":len(unresolved),
                        "all_origin_max_E_m":None if unresolved else policy["max_E_m"],
                        "all_origin_max_D_m":None if unresolved else policy["max_D_m"],
                        "improved_vs_stop":sum(r["reduction_m"]>TOL for r in valid),
                        "min_D_known_m":min(r["D_known_m"] for r in valid),"max_D_known_m":max(r["D_known_m"] for r in valid),**policy}
                summaries.append(record)
                journey_rows.extend({"scenario":scenario,"K":int(k),"policy":key,**r} for r in evaluated[key])
                comparisons.append({"scenario":scenario,"K":int(k),"policy":key,**difference(evaluated[key],evaluated["coverage_strong"])})
                # Verify selected real-data rows against the earlier explicit evaluator.
                if extent=="medium" and radius==500 and shift==0 and int(k)==2:
                    for r in valid:
                        explicit=evaluate_journey(graph,engine.origins[r["origin"]]["node"],engine.s,engine.a,policy["candidates"])
                        assert explicit["first_notice"]==r["first_notice"]
                        for column in ("D_known_m","D_stop_m","D_policy_m","E_policy_m"):
                            assert abs(explicit[column]-r[column])<TOL,(key,r["origin"],column)
        for key,policy in main_policies["2"].items():
            score=engine.score(policy["candidates"])
            fixed.append({"scenario":scenario,"policy":key,"selected":len(chosen),"resolved":len(engine.origins),**score})
        if extent=="medium" and radius==500 and shift==0:
            assumptions=[]
            for name,data in engine.origins.items():
                direct=base.shortest(graph,data["node"],engine.a)
                assumptions.append({"origin":name,"D_known_m":direct["length_m"],
                                    "assumed_street_share":direct["assumed_street_m"]/direct["length_m"],
                                    "steps_m":direct["steps_m"],"proxy_offset_m":anchors[name]["offset_m"]})
            pd.DataFrame(assumptions).to_csv(ROOT/"review_route_assumptions.csv",index=False,encoding="utf-8-sig")
            for p in (0,.25,.5,.75,1):
                for key,policy in policies["2"].items():
                    values=[engine.expected_excess(name,policy["candidates"],p) for name in engine.origins]
                    recognition_rows.extend({"origin":name,"p_assumed":p,"policy":key,"expected_E_m":value}
                                            for name,value in zip(engine.origins,values))
                    recognition.append({"p_assumed":p,"policy":key,"max_expected_E_m":max(values),
                                        "sum_expected_E_m":sum(values),"resolved":len(engine.origins),"unresolved":len(unresolved)})
            component=nx.node_connected_component(graph,anchors["N3390524793"]["node"])
            component_audit={"nodes":len(component),"edges":graph.subgraph(component).number_of_edges(),
                             "way_ids":sorted({d["way_id"] for u,v,d in graph.subgraph(component).edges(data=True)}),
                             "highways":sorted({d["highway"] for u,v,d in graph.subgraph(component).edges(data=True)})}
            source_only=engine.score(())
    # Pedestrian-only data are still not made usable by expansion or by hiding disconnections.
    _,nodes,ways=extracts["medium"]
    pedestrian_graph,pedestrian_anchors,pedestrian_engine=build(nodes,ways,sources,contract,entries,0,"pedestrian_only")
    pedestrian_summary={"selected":len(entries),"resolved":len(pedestrian_engine.origins) if pedestrian_engine else 0,
                         "anchor_range_passed":pedestrian_engine is not None}
    output={"status":"enlarged archived-map conditional sensitivity; no observed pedestrian policy effects",
            "main_scenario":"medium_r500_A+0","input_comparison":input_comparison,"scenarios":scenario_meta,
            "primary_stop_only":source_only,"isolated_entrance_3390524793":component_audit,
            "pedestrian_only":pedestrian_summary,
            "input_sha256":{str(path.relative_to(ROOT.parent)):hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in [*paths.values(),ROOT/"recompute_expanded.py",ROOT/"policy_engine.py",
                                          ROOT/"audit_robustness.py",ROOT/"review_contract.json",
                                          ROOT/"raw/osm_medium_query.txt",ROOT.parent/"data_10/analyze_walks.py",
                                          ROOT.parent/"data_10/selected_stops_20260402.csv",
                                          ROOT.parent/"data_10/analysis_contract.json",ROOT.parent/"data_10/requirements.txt",
                                          ROOT.parent/"data_11/evaluate_policies.py",ROOT.parent/"data_11/adapt_subset.py"]}}
    (ROOT/"expanded_review_results.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for filename,rows in [("review_policy_summary.csv",summaries),("review_journeys.csv",journey_rows),
                          ("review_distribution.csv",comparisons),("review_fixed_policies.csv",fixed),
                          ("review_recognition.csv",recognition),("review_recognition_journeys.csv",recognition_rows)]:
        pd.DataFrame(rows).to_csv(ROOT/filename,index=False,encoding="utf-8-sig")
    plot_review(summaries,recognition)
    print(json.dumps({"extents":list(paths),"main":scenario_meta["medium_r500_A+0"],
                      "pedestrian_only":pedestrian_summary,"isolated_entrance":component_audit},ensure_ascii=True,indent=2))


def plot_review(summary,recognition):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"]="Malgun Gothic"
    plt.rcParams["axes.unicode_minus"]=False
    fig,axes=plt.subplots(1,2,figsize=(12,5.3))
    keys=[("coverage_strong","여정 수 우선","#bd8137"),("equity","추가길이 부담 우선","#245779"),
          ("total_distance_equity","전체길이 부담 우선","#86578c")]
    main=[r for r in summary if r["scenario"]=="medium_r500_A+0" and r["K"]==2]
    for x,(key,label,color) in enumerate(keys):
        row=next(r for r in main if r["policy"]==key)
        axes[0].bar(x,row["max_E_m"],color=color,width=.6)
        axes[0].text(x,row["max_E_m"]+25,f"{row['max_E_m']:.0f}m",ha="center")
        rec=[r for r in recognition if r["policy"]==key]
        axes[1].plot([r["p_assumed"] for r in rec],[r["max_expected_E_m"] for r in rec],"o-",label=label,color=color)
    axes[0].set_xticks(range(3),["만나는 여정 수\n우선","추가길이 부담\n우선","전체길이 부담\n우선"])
    axes[0].set_ylim(0,max(r["max_E_m"] for r in main)*1.2)
    axes[0].set_title("같은 추가 안내 2곳: 재산정된 최대 E")
    axes[0].set_ylabel("계산 가능한 21개 여정 중 최대 E(m)")
    axes[1].set_title("후보 고정: 안내 인지 민감도")
    axes[1].set_xlabel("각 안내를 독립적으로 읽을 확률 p — 가정값")
    axes[1].set_ylabel("여정별 기대 E의 최댓값(m)")
    axes[1].legend(fontsize=8)
    for ax in axes:ax.spines[["top","right"]].set_visible(False)
    fig.suptitle("확대한 행사일 지도에서 다시 확인한 안내 정책 비교",fontsize=15)
    fig.text(.02,.045,"선정 22개 중 21개 계산·1개 지도 연결 미해결. 지도 확대는 실제 보도·횡단·행사 통제·임시 승차 위치의 검증을 대신하지 않음.",fontsize=8)
    fig.text(.02,.015,"일반도로 보행·대체점·고정 접근 경로 가정. p는 측정값 아님. 최대 기대값은 실제 최악 상황이 아님. © OpenStreetMap contributors (ODbL)",fontsize=8)
    fig.tight_layout(rect=(0,.1,1,.93))
    fig.savefig(ROOT/"expanded_review.png",dpi=180)
    plt.close(fig)


if __name__=="__main__":main()
