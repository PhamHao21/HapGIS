# -*- coding: utf-8 -*-
"""Road-surface polygons shaped like an L: the reference line must follow both legs."""
import unittest

from core_housenumber import truc_cong_tu_polygon, ty_le_khong_phu_truc
import test_centerline as tc
from test_centerline import ELL, numbering, roads_of, street

ANGLES = (0, 30, 90, 200, 290)


class PolygonLShapeTests(unittest.TestCase):
    assert_follows_sides = tc.CenterlineNumberingTests.assert_follows_sides

    def test_reference_line_covers_both_legs(self):
        # At 30/90/200 degrees the minimum rotated rectangle lines up with one leg,
        # so cuts across its long axis run along the other leg and skip it.
        for angle in ANGLES:
            with self.subTest(angle=angle):
                _, road, _ = street(ELL, angle)
                self.assertLess(ty_le_khong_phu_truc(road, truc_cong_tu_polygon(road)), 0.05)

    def test_l_shaped_polygon_keeps_each_side_in_order(self):
        for angle in ANGLES:
            with self.subTest(angle=angle):
                houses, road, _ = street(ELL, angle)
                self.assert_follows_sides(houses, numbering(houses, roads_of(road)))


if __name__ == "__main__":
    unittest.main()
