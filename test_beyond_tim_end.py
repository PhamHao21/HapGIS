# -*- coding: utf-8 -*-
"""Parcels lying past the dead end of their own centerline are flagged by the data check."""
import unittest

import geopandas as gpd
from shapely.geometry import LineString, box

from app_service import THUA_NGOAI_DAU_TIM_M, kiem_tra_du_lieu

CRS = "EPSG:3405"


def scene(far_name="Đường A"):
    """Đường A ends at (100, 0) where Đường B continues north; parcels line both sides of B."""
    names, geoms = [], []
    for x in range(0, 100, 10):  # proper frontage parcels of A, plus one deep lot behind A
        names += ["Đường A"] * 2
        geoms += [box(x, 4, x + 10, 16), box(x, -16, x + 10, -4)]
    names.append("Đường A")
    geoms.append(box(40, 60, 50, 70))
    for y in range(40, 240, 20):  # parcels along B, both sides
        names += [far_name] * 2
        geoms += [box(104, y, 116, y + 20), box(84, y, 96, y + 20)]
    houses = gpd.GeoDataFrame({"tenDuong": names}, geometry=geoms, crs=CRS)
    roads = gpd.GeoDataFrame({"tenDuong": ["Đường A", "Đường B"]},
                             geometry=[LineString([(-5, 0), (100, 0)]), LineString([(100, 0), (100, 300)])],
                             crs=CRS)
    return houses, roads


def warning_of(report):
    return [w for w in report["warnings"] if "cách tim đường cùng tuyến" in w]


class BeyondTimEndTests(unittest.TestCase):
    def test_parcels_past_dead_end_are_warned_with_the_road_they_follow(self):
        houses, roads = scene()
        report = kiem_tra_du_lieu(houses, roads)
        self.assertFalse(report["errors"])
        far = [g for g, n in zip(houses.geometry, houses.tenDuong)
               if n == "Đường A" and g.distance(roads.geometry[0]) > THUA_NGOAI_DAU_TIM_M]
        [message] = warning_of(report)
        self.assertIn(f"{len(far) - 1} thửa", message)  # the deep lot sits beside A, not past its end or by B
        self.assertIn("Đường A", message)
        self.assertIn("nằm dọc Đường B", message)

    def test_correctly_named_parcels_are_not_warned(self):
        houses, roads = scene(far_name="Đường B")
        self.assertEqual(warning_of(kiem_tra_du_lieu(houses, roads)), [])


if __name__ == "__main__":
    unittest.main()
