"""Reject consequential record corruptions and enforce fixed-anchor filtering."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
import networkx as nx
from analyze_accessibility import restricted_graph
from build_review_drafts import validate_record, build_draft


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((Path(__file__).resolve().parent.parent / "data_09/service_changes.json").read_text(encoding="utf-8"))
        self.record = deepcopy(self.source["records"][0])
        self.ids = {"02002", "02100", "02233", "02006", "02136", "02001"}

    def test_invented_temp_stop_id_rejected(self):
        self.record["boarding_point"]["ars_id"] = "02001"
        with self.assertRaises(ValueError): validate_record(self.record, self.ids)

    def test_inverted_service_window_rejected(self):
        self.record["announced_service_window"]["end"] = "2026-04-05T04:00:00+09:00"
        with self.assertRaises(ValueError): validate_record(self.record, self.ids)

    def test_leading_zero_loss_rejected(self):
        self.record["skipped_stops"][0]["ars_id"] = "2002"
        with self.assertRaises(ValueError): validate_record(self.record, self.ids)

    def test_unverified_accessibility_rejected(self):
        self.record["step_free_connection_verified"] = True
        with self.assertRaises(ValueError): validate_record(self.record, self.ids)

    def test_nulls_and_distinct_time_windows_survive(self):
        draft = build_draft(self.record, self.source)
        self.assertIsNone(draft["boarding_point"]["ars_id"])
        self.assertNotEqual(draft["road_control_window_separate"]["end"], draft["announced_service_window"]["end"])
        self.assertIsNone(draft["unknowns_kept_null"]["step_free_connection_verified"])

    def test_stair_filter_does_not_relocate_or_join_components(self):
        graph = nx.Graph()
        graph.add_edge("anchor_start", 1, way_id=1, steps=True, length_m=3)
        graph.add_edge(1, "target", way_id=2, steps=False, length_m=4)
        out, removed, _ = restricted_graph(graph, {1: {"tags": {}}, 2: {"tags": {}}}, {})
        self.assertIn("anchor_start", out)
        self.assertEqual(removed, 1)
        self.assertFalse(nx.has_path(out, "anchor_start", "target"))
        self.assertTrue(nx.has_path(graph, "anchor_start", "target"))


if __name__ == "__main__": unittest.main()
