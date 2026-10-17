"""Analytic checks for dependence bounds; no geographic truth claims."""
import unittest
import numpy as np
from analyze_decisions import joint_weights, maximum_expectation_bounds
from analyze_decisions import path_outcome
from types import SimpleNamespace
import networkx as nx


class DependenceTests(unittest.TestCase):
    def test_feasible_weights_sum_and_marginals(self):
        for q in (.1, .2, .3):
            w = joint_weights(.3, .8, q)
            self.assertTrue(np.all(w >= -1e-7))
            self.assertAlmostEqual(w.sum(), 1)
            self.assertAlmostEqual(w[2] + w[3], .3)
            self.assertAlmostEqual(w[1] + w[3], .8)

    def test_impossible_probabilities_rejected(self):
        for args in [(-.1, .5, 0), (.5, 1.1, .5), (.8, .8, .5), (.2, .8, .3)]:
            with self.assertRaises(ValueError):
                joint_weights(*args)

    def test_redundant_notices_depend_on_joint_detection(self):
        # Either notice removes all excess; only missing both retains 100m.
        result = maximum_expectation_bounds([[100, 0, 0, 0]], .5, .5)
        self.assertAlmostEqual(result["minimum_max_expected_E_m"], 0)
        self.assertAlmostEqual(result["maximum_max_expected_E_m"], 50)
        self.assertAlmostEqual(result["independent_max_expected_E_m"], 25)

    def test_convex_maximum_can_have_interior_minimum(self):
        # At p=.5 these lines are 100q and 40-20q; intersection q=1/3.
        result = maximum_expectation_bounds([[100, 0, 0, 0], [30, 40, 40, 30]], .5, .5)
        self.assertAlmostEqual(result["minimum_q"], 1/3)
        self.assertAlmostEqual(result["minimum_max_expected_E_m"], 100/3)
        self.assertAlmostEqual(result["maximum_max_expected_E_m"], 50)

    def test_zero_and_full_recognition_collapse_bounds(self):
        for p, expected in [(0, 100), (1, 10)]:
            result = maximum_expectation_bounds([[100, 30, 50, 10]], p, p)
            self.assertAlmostEqual(result["minimum_max_expected_E_m"], expected)
            self.assertAlmostEqual(result["maximum_max_expected_E_m"], expected)

    def test_alternative_path_uses_first_encountered_notice(self):
        graph = nx.Graph()
        graph.add_edge("O", "P", length_m=3)
        graph.add_edge("P", "Q", length_m=4)
        graph.add_edge("Q", "S", length_m=5)
        engine = SimpleNamespace(graph=graph, s="S", to_a={"S": 10, "P": 8, "Q": 7},
                                 origins={"origin": {"node": "O", "D_known_m": 10}})
        row = path_outcome(engine, "origin", ["O", "P", "Q", "S"], ["Q", "P"])
        self.assertEqual(row["first_notice"], "P")
        self.assertAlmostEqual(row["D_policy_m"], 11)
        self.assertAlmostEqual(row["E_policy_m"], 1)
        fallback = path_outcome(engine, "origin", ["O", "P", "Q", "S"], [])
        self.assertAlmostEqual(fallback["D_policy_m"], 22)


if __name__ == "__main__":
    unittest.main()
