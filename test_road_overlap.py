# -*- coding: utf-8 -*-
"""Pre-run detection of parcels drawn on top of / across the same-route road polygon."""
import unittest

import geopandas as gpd
from shapely.geometry import box

from app_service import ROAD_OVERLAP_WARNING_RATIO, kiem_tra_du_lieu

CRS = "EPSG:3405"  # VN-2000 projected, metres: no CRS warning in the report.


def overlap_fixture(*parcels, routes=None):
    houses = gpd.GeoDataFrame(
        {"tenDuong": routes or ["Đường A"] * len(parcels)}, geometry=list(parcels), crs=CRS)
    roads = gpd.GeoDataFrame(
        {"tenDuong": ["Đường A", "Đường B"]},
        geometry=[box(-50, -5, 150, 0), box(-50, 100, 150, 105)], crs=CRS)
    return houses, roads


def overlap_messages(report):
    return ([e for e in report["errors"] if "polygon đường" in e],
            [w for w in report["warnings"] if "lấn lên mặt đường" in w])


class RoadOverlapTests(unittest.TestCase):
    def test_parcel_touching_road_is_not_reported(self):
        report = kiem_tra_du_lieu(*overlap_fixture(box(0, 0, 10, 10), box(10, 0, 20, 10)))
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])

    def test_thirty_percent_overlap_warns_without_blocking(self):
        self.assertLess(ROAD_OVERLAP_WARNING_RATIO, 0.30)
        report = kiem_tra_du_lieu(*overlap_fixture(box(0, 0, 10, 10), box(10, -3, 20, 7)))
        errors, warnings = overlap_messages(report)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("1 thửa", warnings[0])
        self.assertIn("dòng #1 (Đường A, 30% trên đường)", warnings[0])

    def test_representative_point_inside_road_is_error(self):
        report = kiem_tra_du_lieu(*overlap_fixture(box(0, 0, 10, 10), box(10, -7, 20, 3)))
        errors, warnings = overlap_messages(report)
        self.assertEqual(len(errors), 1)
        self.assertIn("tâm (representative point)", errors[0])
        self.assertIn("dòng #1 (Đường A", errors[0])
        self.assertEqual(warnings, [])

    def test_parcel_drawn_across_road_is_error(self):
        # Centre stays north of the road and only ~18% lies on it, but the road splits the parcel.
        report = kiem_tra_du_lieu(*overlap_fixture(box(0, 0, 10, 10), box(10, -8, 20, 20)))
        errors, warnings = overlap_messages(report)
        self.assertEqual(len(errors), 1)
        self.assertIn("cắt ngang", errors[0])
        self.assertIn("dòng #1", errors[0])
        self.assertEqual(warnings, [])

    def test_only_same_route_road_counts(self):
        report = kiem_tra_du_lieu(*overlap_fixture(
            box(0, 0, 10, 10), box(10, -7, 20, 3), routes=["Đường A", "Đường B"]))
        self.assertEqual(overlap_messages(report), ([], []))

    def test_counts_and_examples_are_limited(self):
        parcels = [box(i * 10, -7, i * 10 + 10, 3) for i in range(8)]
        errors, _ = overlap_messages(kiem_tra_du_lieu(*overlap_fixture(*parcels)))
        self.assertIn("8 thửa", errors[0])
        self.assertEqual(errors[0].count("dòng #"), 5)


if __name__ == "__main__":
    unittest.main()
