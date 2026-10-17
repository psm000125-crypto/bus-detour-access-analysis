import unittest
import numpy as np
from analyze_access import carbon_case, decomposition, threshold_count


class AccessScenarioTests(unittest.TestCase):
    def test_signed_location_change_is_preserved(self):
        b, l, e = decomposition([100, 200], [70, 300], [80, 350])
        np.testing.assert_allclose(l, [-30, 100])
        np.testing.assert_allclose(b + l + e, [80, 350])

    def test_invalid_distance_and_missing_denominator(self):
        with self.assertRaises(ValueError):
            decomposition([100], [300], [299])
        self.assertEqual(threshold_count([500, 501, float("nan")], 500), (1, 2))

    def test_carbon_is_vehicle_distance_not_person_distance(self):
        self.assertAlmostEqual(carbon_case(100, .05, 10, occupants=2, factor=.2), 5)
        self.assertEqual(carbon_case(100, 0, 10), 0)

    def test_carbon_input_constraints(self):
        for args in [(100, 1.1, 5), (100, .1, -5), (-1, .1, 5), (100, .1, 5, 0)]:
            with self.assertRaises(ValueError):
                carbon_case(*args)


if __name__ == "__main__":
    unittest.main()
