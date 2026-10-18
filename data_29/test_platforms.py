"""Platform eligibility and source topology regression checks."""
import unittest
import pyproj
from reanalyze_platforms import platform_allowed, make_graph


class Platforms(unittest.TestCase):
    def setUp(self):
        self.tags={"highway":"platform","public_transport":"platform","bus":"yes"}

    def test_bus_passenger_line_allowed(self):
        self.assertTrue(platform_allowed(self.tags))

    def test_access_and_area_restrictions_remain(self):
        for key,value in [("access","no"),("foot","no"),("access","private"),("oneway:foot","yes"),("area","yes")]:
            self.assertFalse(platform_allowed({**self.tags,key:value}), (key,value))

    def test_taxi_platform_and_busway_not_admitted(self):
        self.assertFalse(platform_allowed({"highway":"platform","public_transport":"platform","taxi":"yes"}))
        self.assertFalse(platform_allowed({"highway":"busway","access":"no"}))

    def test_closed_platform_outline_excluded(self):
        nodes={1:{"lon":126.97,"lat":37.55},2:{"lon":126.971,"lat":37.551},3:{"lon":126.972,"lat":37.55}}
        graph=make_graph(nodes,{1:{"nodes":[1,2,3,1],"tags":self.tags}},pyproj.Transformer.from_crs(4326,32652,always_xy=True))
        self.assertEqual(graph.number_of_edges(),0)

    def test_parallel_nearby_lines_do_not_get_fake_connector(self):
        nodes={1:{"lon":126.9700,"lat":37.55},2:{"lon":126.9701,"lat":37.55},3:{"lon":126.9702,"lat":37.55},4:{"lon":126.9703,"lat":37.55}}
        ways={1:{"nodes":[1,2],"tags":self.tags},2:{"nodes":[3,4],"tags":self.tags}}
        graph=make_graph(nodes,ways,pyproj.Transformer.from_crs(4326,32652,always_xy=True))
        self.assertEqual(graph.number_of_edges(),2)
        self.assertFalse(graph.has_edge(2,3))


if __name__=="__main__":unittest.main()
