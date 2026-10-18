"""Policy scoring with first-notice order and deterministic tie breaks."""
import itertools
import math
import networkx as nx
from . import network as base
TOL = 1e-7

def clean(value):
    if value < -TOL:
        raise ValueError(f"Negative excess length violates shortest-path bound: {value}")
    return 0.0 if abs(value) <= TOL else value

def evaluate_journey(graph, origin_node, s, a, candidates):
    approach = base.shortest(graph, origin_node, s)
    direct = base.shortest(graph, origin_node, a)
    onward = base.shortest(graph, s, a)
    if not approach or not direct or not onward:
        return {"status": "mapped_disconnection"}
    stop_distance = approach["length_m"] + onward["length_m"]
    notice_distance = stop_distance
    first = next((n for n in approach["path"][:-1] if n in set(candidates)), None)
    if first is not None:
        prefix = approach["path"][:approach["path"].index(first) + 1]
        reroute = base.shortest(graph, first, a)
        if reroute is None:
            return {"status": "notice_onward_disconnection"}
        notice_distance = nx.path_weight(graph, prefix, "length_m") + reroute["length_m"]
    return {"status": "conditional", "first_notice": first,
            "D_known_m": direct["length_m"], "D_stop_m": stop_distance,
            "D_policy_m": notice_distance,
            "E_stop_m": clean(stop_distance - direct["length_m"]),
            "E_policy_m": clean(notice_distance - direct["length_m"]),
            "reduction_m": clean(stop_distance - notice_distance),
            "direct_assumed_street_m": direct["assumed_street_m"]}

def score_policy(graph, origins, s, a, candidates):
    rows = [{"origin": key, **evaluate_journey(graph, node, s, a, candidates)}
            for key, node in origins.items()]
    resolved = [r for r in rows if r["status"] == "conditional"]
    full = len(resolved) == len(rows)
    return {"candidates": list(candidates), "rows": rows,
            "origin_count": len(rows), "resolved_count": len(resolved),
            "covered": sum(r["first_notice"] is not None for r in resolved),
            "max_E_m": max(r["E_policy_m"] for r in resolved) if full and resolved else None,
            "sum_E_m": sum(r["E_policy_m"] for r in resolved) if full and resolved else None}

def select_policies(scores):
    valid = [r for r in scores if r["max_E_m"] is not None]
    if not valid:
        return {}
    def key_id(r):
        return tuple(map(str, r["candidates"]))
    def choose(criteria):
        pool = list(valid)
        for criterion, direction in criteria:
            values = [direction * r[criterion] for r in pool]
            optimum = min(values)
            pool = [r for r in pool if direction * r[criterion] <= optimum + TOL]
        return min(pool, key=key_id)
    return {"coverage_strong": choose([("covered", -1), ("max_E_m", 1), ("sum_E_m", 1)]),
            "efficiency": choose([("sum_E_m", 1), ("max_E_m", 1)]),
            "equity": choose([("max_E_m", 1), ("sum_E_m", 1)])}

def expected_excess(row, p):
    if not 0 <= p <= 1:
        raise ValueError("Recognition sensitivity must lie in [0, 1]")
    return (1 - p) * row["E_stop_m"] + p * row["E_policy_m"]

def choose_with_total_distance(scores):
    policies = select_policies(scores)
    pool = list(scores)
    for criterion in ("max_D_m", "max_E_m", "sum_E_m"):
        minimum = min(r[criterion] for r in pool)
        pool = [r for r in pool if r[criterion] <= minimum + TOL]
    policies["total_distance_equity"] = min(pool, key=lambda r: tuple(map(str, r["candidates"])))
    return policies

def recognition_expectations(graph, origin, s, a, candidates, p):
    if not 0 <= p <= 1:
        raise ValueError("p must lie in [0,1]")
    expected = 0.0
    for flags in itertools.product((False, True), repeat=len(candidates)):
        probability = math.prod(p if flag else 1-p for flag in flags)
        selected = [n for n,flag in zip(candidates,flags) if flag]
        row = evaluate_journey(graph, origin, s, a, selected)
        if row["status"] != "conditional":
            return None
        expected += probability * row["E_policy_m"]
    return expected

class PolicyEngine:
    def __init__(self, graph, origins, s, a, radius=450):
        self.graph, self.s, self.a = graph, s, a
        self.to_a = nx.single_source_dijkstra_path_length(graph, a, weight="length_m")
        self.to_s = nx.single_source_dijkstra_path_length(graph, s, weight="length_m")
        self.origins, self.unresolved = {}, []
        for name, node in origins.items():
            approach = base.shortest(graph, node, s)
            if approach is None or node not in self.to_a or s not in self.to_a:
                self.unresolved.append(name)
                continue
            prefix, position = {}, {}
            cumulative = 0.0
            for index, current in enumerate(approach["path"]):
                if index:
                    cumulative += graph[approach["path"][index-1]][current]["length_m"]
                prefix[current] = cumulative
                position[current] = index
            self.origins[name] = {"node":node,"approach":approach,"prefix":prefix,"position":position,
                                  "D_known_m":self.to_a[node],"D_stop_m":approach["length_m"]+self.to_a[s]}
        candidates = set()
        for row in self.origins.values():
            for node in row["approach"]["path"][:-1]:
                incident = [d["highway"] for _,_,d in graph.edges(node,data=True)]
                if ((graph.degree(node)>=3 or node==row["node"]) and self.to_s.get(node,float("inf"))<=radius+TOL
                    and any(h not in {"steps","corridor"} for h in incident)):
                    candidates.add(node)
        self.candidates = sorted(candidates,key=str)

    def row(self, name, candidates):
        source = self.origins[name]
        encountered = [p for p in candidates if p in source["position"] and p != self.s]
        first = min(encountered,key=lambda p:source["position"][p]) if encountered else None
        distance = source["D_stop_m"] if first is None else source["prefix"][first]+self.to_a[first]
        excess, reduction = distance-source["D_known_m"],source["D_stop_m"]-distance
        if excess < -TOL or reduction < -TOL:
            raise ValueError("Shortest-path inequality violated")
        return {"origin":name,"status":"conditional","first_notice":first,"D_known_m":source["D_known_m"],
                "D_stop_m":source["D_stop_m"],"D_policy_m":distance,
                "E_stop_m":max(0.0,source["D_stop_m"]-source["D_known_m"]),
                "E_policy_m":max(0.0,excess),"reduction_m":max(0.0,reduction)}

    def score(self,candidates):
        rows=[self.row(name,candidates) for name in self.origins]
        return {"candidates":list(candidates),"covered":sum(r["first_notice"] is not None for r in rows),
                "max_E_m":max(r["E_policy_m"] for r in rows),"sum_E_m":sum(r["E_policy_m"] for r in rows),
                "max_D_m":max(r["D_policy_m"] for r in rows)}

    def fit(self,k):
        scores=[self.score(combination) for combination in itertools.combinations(self.candidates,k)]
        return choose_with_total_distance(scores),len(scores)

    def expected_excess(self,name,candidates,p):
        if not 0<=p<=1:
            raise ValueError("p must lie in [0,1]")
        expected=0.0
        for flags in itertools.product((False,True),repeat=len(candidates)):
            probability=1.0
            for flag in flags:
                probability *= p if flag else 1-p
            expected += probability*self.row(name,[n for n,flag in zip(candidates,flags) if flag])["E_policy_m"]
        return expected
