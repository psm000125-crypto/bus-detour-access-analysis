"""Cached shortest-distance policy evaluator with explicit encounter order.

Caching changes runtime only; synthetic and real selected rows are checked against
the earlier explicit shortest-path evaluator. It adds no geographic connections.
"""
import itertools

import networkx as nx

from audit_robustness import TOL, base
from adapt_subset import choose_with_total_distance


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
