"""Post-stress-test revision on the calculable subset; never an all-origin guarantee."""
import hashlib
import itertools
import json
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import Point

from evaluate_policies import ROOT, TOL, base, evaluate_journey, graph_with_anchors, prepare, select_policies


def choose_with_total_distance(scores):
    policies = select_policies(scores)
    pool = list(scores)
    for criterion in ("max_D_m", "max_E_m", "sum_E_m"):
        minimum = min(r[criterion] for r in pool)
        pool = [r for r in pool if r[criterion] <= minimum + TOL]
    policies["total_distance_equity"] = min(pool, key=lambda r: tuple(map(str, r["candidates"])))
    return policies


def main():
    contract, raw, nodes, ways, sources, transformer = prepare()
    adaptation = json.loads((ROOT / "adaptation_contract.json").read_text(encoding="utf-8"))
    entrances = pd.read_csv(ROOT / "expanded_origin_selection.csv")
    for row in entrances.to_dict("records"):
        sources[row["origin"]] = Point(transformer.transform(row["lon"], row["lat"]))
    graph, anchors = graph_with_anchors(nodes, ways, sources, contract)
    all_origins, resolved, unresolved = {}, {}, []
    for row in entrances.to_dict("records"):
        name = row["origin"]
        anchor = anchors[name]
        if not anchor["eligible"]:
            unresolved.append({**row, "status": "anchor_out_of_range"})
            continue
        all_origins[name] = anchor["node"]
        result = evaluate_journey(graph, anchor["node"], anchors["S"]["node"], anchors["A"]["node"], ())
        if result["status"] == "conditional":
            resolved[name] = anchor["node"]
        else:
            unresolved.append({**row, **result})
    journeys, scores, _, _ = base.compare_notice(graph, resolved, anchors["S"]["node"], anchors["A"]["node"],
                                                contract["candidate_radius_from_S_m"])
    if not scores:
        raise ValueError("No calculable subset policy; do not invent a result")
    converted = [{"candidates": [r["candidate"]], "covered": r["covered"],
                  "max_E_m": r["max_E_m"], "sum_E_m": r["sum_E_m"],
                  "max_D_m": max(row["D_notice_m"] for row in r["rows"])} for r in scores]
    policies = choose_with_total_distance(converted)
    pair_scores = []
    for left, right in itertools.combinations(scores, 2):
        assert [r["origin"] for r in left["rows"]] == [r["origin"] for r in right["rows"]]
        paired = [{"E": min(lr["E_notice_m"], rr["E_notice_m"]),
                   "D": min(lr["D_notice_m"], rr["D_notice_m"]),
                   "encountered": lr["encountered"] or rr["encountered"]}
                  for lr, rr in zip(left["rows"], right["rows"])]
        pair_scores.append({"candidates": [left["candidate"], right["candidate"]],
                            "covered": sum(r["encountered"] for r in paired),
                            "max_E_m": max(r["E"] for r in paired),
                            "sum_E_m": sum(r["E"] for r in paired),
                            "max_D_m": max(r["D"] for r in paired)})
    pair_policies = choose_with_total_distance(pair_scores)
    result_rows, summaries = [], {}
    for name, policy in policies.items():
        rows = []
        for entry in entrances.to_dict("records"):
            origin = entry["origin"]
            anchor = anchors[origin]
            result = ({"status": "anchor_out_of_range"} if not anchor["eligible"] else
                      evaluate_journey(graph, anchor["node"], anchors["S"]["node"], anchors["A"]["node"], policy["candidates"]))
            rows.append({**entry, "policy": name, **result})
        result_rows.extend(rows)
        valid = [r for r in rows if r["status"] == "conditional"]
        summaries[name] = {**policy, "selected_count": len(rows), "fit_count": len(valid),
                           "unresolved_count": len(rows)-len(valid),
                           "all_origin_max_E_m": None if len(valid) != len(rows) else policy["max_E_m"],
                           "all_origin_max_D_m": None if len(valid) != len(rows) else policy["max_D_m"],
                           "improved_vs_stop_count": sum(r["reduction_m"] > TOL for r in valid),
                           "unchanged_vs_stop_count": sum(r["reduction_m"] <= TOL for r in valid),
                           "min_D_known_m": min(r["D_known_m"] for r in valid),
                           "max_D_known_m": max(r["D_known_m"] for r in valid),
                           "min_D_policy_m": min(r["D_policy_m"] for r in valid)}
    pd.DataFrame(converted).to_csv(ROOT / "adapted_candidate_scores.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(result_rows).to_csv(ROOT / "adapted_journeys.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"policy": k, **v} for k, v in summaries.items()]).to_csv(ROOT / "adapted_policy_comparison.csv", index=False, encoding="utf-8-sig")
    pair_rows = []
    for policy_name, policy in pair_policies.items():
        rows = [{"origin": origin, **evaluate_journey(graph, node, anchors["S"]["node"], anchors["A"]["node"], policy["candidates"])}
                for origin, node in resolved.items()]
        # Verify cached distance composition against actual first encounter and rerouting.
        assert abs(max(r["E_policy_m"] for r in rows) - policy["max_E_m"]) < TOL
        assert abs(sum(r["E_policy_m"] for r in rows) - policy["sum_E_m"]) < TOL
        assert abs(max(r["D_policy_m"] for r in rows) - policy["max_D_m"]) < TOL
        assert sum(r["first_notice"] is not None for r in rows) == policy["covered"]
        pair_rows.extend({"policy": policy_name, **r} for r in rows)
        pair_rows.extend({"policy": policy_name, **r} for r in unresolved)
        policy.update({"selected_count": len(entrances), "fit_count": len(resolved),
                       "unresolved_count": len(unresolved), "all_origin_max_E_m": None,
                       "all_origin_max_D_m": None,
                       "improved_vs_stop_count": sum(r["reduction_m"] > TOL for r in rows),
                       "unchanged_vs_stop_count": sum(r["reduction_m"] <= TOL for r in rows)})
    pd.DataFrame(pair_rows).to_csv(ROOT / "adapted_two_notice_journeys.csv", index=False, encoding="utf-8-sig")
    budget_rows = [{"additional_notices": count, "policy": name, **policy}
                   for count, pset in [(1, summaries), (2, pair_policies)] for name, policy in pset.items()]
    pd.DataFrame(budget_rows).to_csv(ROOT / "adapted_policy_budget_frontier.csv", index=False, encoding="utf-8-sig")
    output = {"adaptation_contract": adaptation, "selected_entrances": len(entrances),
              "fit_entrances": len(resolved), "unresolved": unresolved, "candidate_count": len(scores),
              "policies": summaries, "two_notice_combinations": len(pair_scores), "two_notice_policies": pair_policies,
              "contract_sha256": hashlib.sha256((ROOT / "adaptation_contract.json").read_bytes()).hexdigest(),
              "selection_sha256": hashlib.sha256((ROOT / "expanded_origin_selection.csv").read_bytes()).hexdigest()}
    (ROOT / "adapted_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plot_comparison(summaries)
    plot_budget_pair(pair_policies)
    print(json.dumps(output, ensure_ascii=True, indent=2))


def plot_comparison(summaries):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    labels = {"coverage_strong": "최다 여정", "efficiency": "총 추가길이 최소",
              "equity": "최대 추가길이 최소", "total_distance_equity": "최대 전체길이 최소"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.5))
    keys = list(summaries)
    colors = ["#c88432", "#3b8065", "#235789", "#8b5a9c"]
    for ax, metric, title in zip(axes, ["covered", "max_E_m", "max_D_m"],
                               ["후보를 만나는 계산 가능 여정 수", "21개 여정 중 최대 추가길이 E(m)", "21개 여정 중 최대 전체길이 D(m)"]):
        values = [summaries[k][metric] for k in keys]
        ax.barh(range(len(keys)), values, color=colors)
        ax.set_yticks(range(len(keys)), [labels[k] for k in keys], fontsize=9)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11)
        ax.set_xlim(0, max(values)*1.2)
        for y, value in enumerate(values):
            ax.text(value + max(values)*.015, y, f"{value:.0f}", va="center", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("계산 가능한 21개 출입구로 다시 산정한 후보 비교", fontsize=15)
    fig.text(.02, .045, "전체 선정 22개 중 1개 지도 연결 미해결. 동일 자료로 다시 맞춘 결과이며 독립 검증 아님. 추가 안내는 모두 1곳.", fontsize=9)
    fig.text(.02, .015, "지도상 일반도로·임시 승차 대체점 가정. 실제 보행·게시·인지·승차 가능성 미검증. 현장 배치 추천 불가.", fontsize=9)
    fig.tight_layout(rect=(0, .09, 1, .93))
    fig.savefig(ROOT / "adapted_policy_comparison.png", dpi=180)
    plt.close(fig)


def plot_budget_pair(policies):
    import matplotlib.pyplot as plt
    names = ["coverage_strong", "equity", "total_distance_equity"]
    colors = ["#c88432", "#235789", "#8b5a9c"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.2))
    for ax, metric, title, unit in zip(axes, ["covered", "max_E_m", "max_D_m"],
                                     ["안내 후보를 만나는 여정", "최대 추가 지도 길이", "최대 전체 지도 길이"],
                                     ["개 / 계산 가능 21개", "m", "m"]):
        values = [policies[n][metric] for n in names]
        ax.bar(range(3), values, color=colors, width=.6)
        ax.set_xticks(range(3), ["만나는\n여정 수 우선", "추가 이동\n부담 우선", "전체 이동\n부담 우선"], fontsize=9)
        ax.set_title(title, fontsize=12)
        ax.set_ylabel(unit)
        ax.set_ylim(0, max(values)*1.22)
        for x, value in enumerate(values):
            ax.text(x, value + max(values)*.035, f"{value:.0f}", ha="center", fontsize=12)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("같은 추가 안내 2곳: 많이 만나게 하면 이동 부담도 줄까?", fontsize=15)
    fig.text(.02, .055, "선정 출입구 22개 중 계산 가능 21개에 한정한 재산정. 1개 연결 미해결. 이용자 수·실제 인지·보행 효과를 측정한 결과가 아님.", fontsize=8)
    fig.text(.02, .02, "전체 이동 부담 우선은 일부 여정에 다른 배치보다 불리함. 실제 대기 위치·통제·보행 연결 미검증. © OpenStreetMap contributors (ODbL)", fontsize=8)
    fig.tight_layout(rect=(0, .1, 1, .93))
    fig.savefig(ROOT / "two_notice_tradeoff.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
