"""Fixed-anchor access filtering regression test."""
import unittest
import networkx as nx
from analysis.inputs import restricted_graph

class AccessibilityTests(unittest.TestCase):
    def test_stair_filter_does_not_relocate_or_join_components(self):
        graph = nx.Graph()
        graph.add_edge("anchor_start", 1, way_id=1, steps=True, length_m=3)
        graph.add_edge(1, "target", way_id=2, steps=False, length_m=4)
        out, removed, _ = restricted_graph(graph, {1: {"tags": {}}, 2: {"tags": {}}}, {})
        self.assertIn("anchor_start", out)
        self.assertEqual(removed, 1)
        self.assertFalse(nx.has_path(out, "anchor_start", "target"))
        self.assertTrue(nx.has_path(graph, "anchor_start", "target"))
