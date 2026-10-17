import unittest

import networkx as nx

from audit_robustness import recognition_expectations
from evaluate_policies import evaluate_journey
from policy_engine import PolicyEngine


def graph():
    result=nx.Graph()
    for u,v,length in [("O","P",20),("P","Q",20),("Q","S",20),("Q","A",25),("S","A",60)]:
        result.add_edge(u,v,length_m=length,assumed_street=True,steps=False,highway="residential")
    return result


class ReviewModels(unittest.TestCase):
    def test_cache_matches_explicit_first_encounter_with_missed_signs(self):
        g=graph()
        model=PolicyEngine(g,{"origin":"O"},"S","A")
        for candidates in [(),("P",),("Q",),("Q","P")]:
            cached=model.row("origin",candidates)
            explicit=evaluate_journey(g,"O","S","A",candidates)
            for key in ("D_known_m","D_stop_m","D_policy_m","E_policy_m"):
                self.assertAlmostEqual(cached[key],explicit[key])
            self.assertEqual(cached["first_notice"],explicit["first_notice"])

    def test_two_sign_recognition_is_not_one_sign_probability(self):
        g=graph()
        model=PolicyEngine(g,{"origin":"O"},"S","A")
        # S->Q->A is 45m, so either notice avoids 40m; miss both=.25.
        self.assertAlmostEqual(model.expected_excess("origin",("P","Q"),.5),10)
        self.assertAlmostEqual(recognition_expectations(g,"O","S","A",("P","Q"),.5),10)
        self.assertEqual(model.expected_excess("origin",("P","Q"),1),0)
        self.assertEqual(model.expected_excess("origin",("P","Q"),0),40)

    def test_unresolved_origin_is_retained_outside_resolved_engine(self):
        g=graph()
        g.add_edge("X","Y",length_m=2,assumed_street=True,steps=False,highway="footway")
        model=PolicyEngine(g,{"origin":"O","missing":"X"},"S","A")
        self.assertEqual(model.unresolved,["missing"])
        self.assertEqual(list(model.origins),["origin"])

    def test_encounter_does_not_imply_distance_improvement(self):
        g=graph()
        model=PolicyEngine(g,{"origin":"O"},"S","A")
        # Onward shortest path through S makes this notice informationally redundant.
        g2=nx.Graph()
        for u,v,l in [("O","P",10),("P","S",10),("S","A",10)]:
            g2.add_edge(u,v,length_m=l,assumed_street=True,steps=False,highway="residential")
        m2=PolicyEngine(g2,{"origin":"O"},"S","A")
        row=m2.row("origin",("P",))
        self.assertEqual(row["first_notice"],"P")
        self.assertEqual(row["reduction_m"],0)


if __name__=="__main__":
    unittest.main()
