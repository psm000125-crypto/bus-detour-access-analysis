"""Checks of graph/model failure modes; no geographical truth is inferred."""
import unittest

import networkx as nx
from shapely.geometry import Point

from analysis.network import allowed, compare_notice, project_anchors, shortest


def edge(graph, u, v, x1, x2, y=0):
    graph.add_node(u, x=x1, y=y)
    graph.add_node(v, x=x2, y=y)
    graph.add_edge(u, v, length_m=abs(x2-x1), highway="residential",
                   way_id=1, steps=False, assumed_street=True)


class ModelFailureModes(unittest.TestCase):
    def test_access_and_area_are_not_overridden_by_walk_mode(self):
        for extra in ({"foot": "no"}, {"access": "private"}, {"area": "yes"},
                      {"oneway:foot": "yes"}, {"sidewalk": "separate"}):
            self.assertFalse(allowed({"highway": "residential", **extra}, "street_assumed"))
        self.assertFalse(allowed({"highway": "primary"}, "pedestrian_only"))
        self.assertTrue(allowed({"highway": "primary"}, "street_assumed"))
        self.assertFalse(allowed({"highway": "steps"}, "street_assumed_no_steps"))

    def test_multiple_anchor_splits_preserve_existing_line_length(self):
        graph = nx.Graph()
        edge(graph, 1, 2, 0, 100)
        anchors = project_anchors(graph, {"a": Point(20, 3), "b": Point(80, 4)}, 10)
        self.assertAlmostEqual(shortest(graph, 1, 2)["length_m"], 100)
        self.assertAlmostEqual(shortest(graph, anchors["a"]["node"], anchors["b"]["node"])["length_m"], 60)
        self.assertAlmostEqual(anchors["a"]["offset_m"], 3)
        self.assertAlmostEqual(sum(d["length_m"] for _, _, d in graph.edges(data=True)), 100)

    def test_nearest_projection_does_not_jump_to_connected_component(self):
        graph = nx.Graph()
        edge(graph, 1, 2, 0, 100, 0)
        edge(graph, 3, 4, 0, 100, 20)
        anchors = project_anchors(graph, {"a": Point(20, 1), "b": Point(80, 19)}, 10)
        self.assertIsNone(shortest(graph, anchors["a"]["node"], anchors["b"]["node"]))

    def test_out_of_range_anchor_creates_no_false_connector(self):
        graph = nx.Graph()
        edge(graph, 1, 2, 0, 100)
        result = project_anchors(graph, {"a": Point(20, 200)}, 10)
        self.assertFalse(result["a"]["eligible"])
        self.assertNotIn("node", result["a"])
        self.assertEqual(graph.number_of_edges(), 1)

    def test_one_unreachable_journey_blocks_joint_optimization(self):
        graph = nx.Graph()
        edge(graph, 1, 2, 0, 100)
        edge(graph, 3, 4, 0, 100, 20)
        journeys, candidates, best, baseline = compare_notice(graph, {"a": 1, "b": 3}, 2, 1, 450)
        self.assertEqual(len(journeys), 2)
        self.assertIsNone(best)
        self.assertIsNone(baseline)
        self.assertEqual(candidates, [])

    def test_sign_not_encountered_leaves_baseline_burden(self):
        graph = nx.Graph()
        edge(graph, 1, 2, 0, 100)
        edge(graph, 2, 3, 100, 200)
        edge(graph, 3, 4, 200, 300)
        journeys, candidates, best, baseline = compare_notice(graph, {"a": 1, "b": 4}, 3, 1, 450)
        candidate = next(c for c in candidates if c["candidate"] == 1)
        untouched = next(r for r in candidate["rows"] if r["origin"] == "b")
        original = next(j for j in journeys if j["origin"] == "b")
        self.assertFalse(untouched["encountered"])
        self.assertAlmostEqual(untouched["D_notice_m"], original["D_stop_m"])


if __name__ == "__main__":
    unittest.main()
