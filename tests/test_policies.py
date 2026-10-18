"""Decision-model edge cases; these tests do not certify geographic truth."""
import unittest
import networkx as nx
from analysis.policies import evaluate_journey, expected_excess, score_policy, select_policies


def graph(edges):
    result = nx.Graph()
    for u, v, length in edges:
        result.add_edge(u, v, length_m=length, assumed_street=True, steps=False)
    return result


class PolicyFailureModes(unittest.TestCase):
    def test_first_notice_changes_route_before_later_notice(self):
        g = graph([("O", "P", 20), ("P", "Q", 20), ("Q", "S", 20),
                   ("Q", "A", 25), ("S", "A", 60)])
        both = evaluate_journey(g, "O", "S", "A", ("P", "Q"))
        only_later = evaluate_journey(g, "O", "S", "A", ("Q",))
        self.assertEqual(both["first_notice"], "P")
        self.assertEqual(only_later["first_notice"], "Q")
        self.assertAlmostEqual(both["D_policy_m"], 65)
        self.assertAlmostEqual(only_later["D_policy_m"], 65)

    def test_notice_on_other_approach_does_not_help(self):
        g = graph([("O", "S", 10), ("S", "A", 10), ("P", "A", 2)])
        row = evaluate_journey(g, "O", "S", "A", ("P",))
        self.assertIsNone(row["first_notice"])
        self.assertEqual(row["D_policy_m"], row["D_stop_m"])

    def test_unresolved_origin_prevents_all_origin_maximum(self):
        g = graph([("O", "S", 10), ("S", "A", 10), ("X", "Y", 2)])
        score = score_policy(g, {"resolved": "O", "unresolved": "X"}, "S", "A", ())
        self.assertEqual(score["origin_count"], 2)
        self.assertEqual(score["resolved_count"], 1)
        self.assertIsNone(score["max_E_m"])
        self.assertIsNone(score["sum_E_m"])
        self.assertEqual(score["rows"][1]["status"], "mapped_disconnection")

    def test_strong_coverage_uses_effective_tie_break(self):
        scores = [dict(candidates=["near"], covered=3, max_E_m=100, sum_E_m=150),
                  dict(candidates=["better"], covered=3, max_E_m=80, sum_E_m=140),
                  dict(candidates=["single"], covered=1, max_E_m=70, sum_E_m=100)]
        policies = select_policies(scores)
        self.assertEqual(policies["coverage_strong"]["candidates"], ["better"])
        self.assertEqual(policies["equity"]["candidates"], ["single"])

    def test_float_noise_does_not_override_declared_id_tie_break(self):
        scores = [dict(candidates=["a"], covered=1, max_E_m=80 + 1e-9, sum_E_m=140),
                  dict(candidates=["z"], covered=1, max_E_m=80, sum_E_m=140)]
        self.assertEqual(select_policies(scores)["equity"]["candidates"], ["a"])

    def test_recognition_endpoints_and_invalid_probability(self):
        row = {"E_stop_m": 100, "E_policy_m": 20}
        self.assertEqual(expected_excess(row, 0), 100)
        self.assertEqual(expected_excess(row, 1), 20)
        self.assertEqual(expected_excess(row, .5), 60)
        with self.assertRaises(ValueError):
            expected_excess(row, 1.01)


if __name__ == "__main__":
    unittest.main()
