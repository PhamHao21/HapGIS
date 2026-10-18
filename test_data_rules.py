import unittest
from unittest.mock import patch

from shapely.geometry import Point, Polygon

from app_service import kiem_tra_du_lieu, chay_danh_so
from core_housenumber import kiem_tra_he_toa_do
from test_field_mapping import fixtures


class DataRulesTests(unittest.TestCase):
    def report(self, houses, roads, value=""):
        return kiem_tra_du_lieu(houses, roads, value)

    def test_vn2000_projected_meters(self):
        houses, roads = fixtures()
        houses = houses.set_crs("EPSG:3405", allow_override=True)
        roads = roads.set_crs("EPSG:3405", allow_override=True)
        report = self.report(houses, roads, "H9")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["matched_count"], 2)

    def test_geographic_vn2000_and_feet_are_rejected(self):
        for crs in ("EPSG:4756", "EPSG:4326", "EPSG:2263"):
            houses, roads = fixtures()
            houses = houses.set_crs(crs, allow_override=True)
            roads = roads.set_crs(crs, allow_override=True)
            self.assertTrue(self.report(houses, roads)["errors"], crs)
            with self.assertRaises(ValueError):
                kiem_tra_he_toa_do(houses, roads)

    def test_mismatched_and_missing_crs(self):
        houses, roads = fixtures()
        roads = roads.set_crs("EPSG:3405", allow_override=True)
        self.assertTrue(self.report(houses, roads)["errors"])
        houses = houses.set_crs(None, allow_override=True)
        self.assertTrue(self.report(houses, roads)["errors"])

    def test_blank_and_unmatched_keys_reported_without_modifying_data(self):
        houses, roads = fixtures()
        houses.loc[2, "tenDuong"] = "Missing road"
        report = self.report(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["matched_count"], 2)
        self.assertTrue(any("giá trị đối chiếu trống" in s for s in report["warnings"]))
        self.assertTrue(any("không khớp đường" in s for s in report["warnings"]))
        self.assertEqual(houses.loc[2, "tenDuong"], "Missing road")

    def test_wrong_type_empty_and_invalid_geometry_rejected(self):
        # LineString roads are accepted as centerlines (test_centerline.py).
        for geometry in (Point(1, 1), None,
                         Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])):
            houses, roads = fixtures()
            roads.loc[0, "geometry"] = geometry
            self.assertTrue(self.report(houses, roads, "H9")["errors"])

    def test_run_blocks_bad_data_before_algorithm_or_file_write(self):
        houses, roads = fixtures()
        roads.loc[0, "geometry"] = Point(1, 1)
        with patch("app_service.doc_nguon", side_effect=[houses, roads]), \
             patch("app_service.process") as algorithm, patch("app_service.luu_ket_qua") as save:
            with self.assertRaises(ValueError):
                chay_danh_so("houses", None, "roads", None, "H9", "out.gpkg")
            algorithm.assert_not_called()
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
