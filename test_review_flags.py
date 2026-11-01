# -*- coding: utf-8 -*-
"""Per-parcel review column: back lots along another route, dead ends, corner lots, unmatched names."""
import unittest

import geopandas as gpd
from shapely.geometry import LineString, box

from app_service import danh_dau_can_ra_soat

CRS = "EPSG:3405"


def flags(parcels, roads):
    """parcels: {label: (tenDuong, geometry)}; roads: [(tenDuong, line)]."""
    labels = list(parcels)
    out = gpd.GeoDataFrame({"tenDuong": [parcels[k][0] for k in labels], "soNhaHienThi": ["1"] * len(labels)},
                           geometry=[parcels[k][1] for k in labels], crs=CRS)
    road_table = gpd.GeoDataFrame({"tenDuong": [name for name, _ in roads]},
                                  geometry=[line for _, line in roads], crs=CRS)
    return dict(zip(labels, danh_dau_can_ra_soat(out, road_table, False)))


class ReviewFlagTests(unittest.TestCase):
    def setUp(self):
        # Đường A runs east along y=0; Đường B leaves it northwards at x=100 (T junction).
        self.roads = [("Đường A", LineString([(0, 0), (200, 0)])),
                      ("Đường B", LineString([(100, 0), (100, 200)]))]

    def test_back_lot_along_another_route_names_that_route(self):
        res = flags({"back": ("Đường A", box(104, 60, 116, 80))}, self.roads)
        self.assertIn("nằm dọc Đường B", res["back"])
        self.assertIn("Cách Đường A 60 m", res["back"])

    def test_corner_lot_is_flagged_but_not_the_lot_across_the_junction(self):
        res = flags({"corner": ("Đường A", box(104, 4, 120, 20)),
                     "across": ("Đường A", box(92, -20, 108, -4)),
                     "plain": ("Đường A", box(150, 4, 165, 20))}, self.roads)
        self.assertEqual(res["corner"], "Thửa góc, giáp cả Đường B")
        self.assertEqual(res["across"], "")
        self.assertEqual(res["plain"], "")

    def test_parallel_back_road_is_not_a_corner(self):
        roads = self.roads + [("Đường C", LineString([(130, 24), (190, 24)]))]
        res = flags({"deep": ("Đường A", box(150, 4, 165, 20))}, roads)
        self.assertEqual(res["deep"], "")

    def test_far_lot_without_any_road_and_unmatched_name(self):
        res = flags({"far": ("Đường A", box(150, 50, 165, 65)),
                     "ten_sai": ("Đường Z", box(10, 4, 20, 20))}, self.roads)
        self.assertEqual(res["far"], "Cách Đường A 50 m, không có mặt tiền")
        self.assertEqual(res["ten_sai"], "Không có đường cùng tên")

    def test_lot_past_dead_end(self):
        roads = [("Đường A", LineString([(0, 0), (100, 0)]))]
        res = flags({"past": ("Đường A", box(140, -5, 150, 5))}, roads)
        self.assertEqual(res["past"], "Cách Đường A 40 m, nằm sau đầu cụt tim")


if __name__ == "__main__":
    unittest.main()
