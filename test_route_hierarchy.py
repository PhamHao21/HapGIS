# -*- coding: utf-8 -*-
"""Regression tests for structured road/alley keys and selected-scope checks."""
import unicodedata
import unittest

import geopandas as gpd
from shapely.geometry import Polygon, box

from app_service import kiem_tra_du_lieu, loc_tuyen
from core_housenumber import COL_SONHA, process
from route_catalog import build_route_catalog, normalize_name, resolve_manual_selection
from test_alley_numbering import alley_fixture


def hierarchy_fixture():
    houses, roads = alley_fixture("Hẻm 236 đường A")
    houses["tenDuong"] = "Đường A"
    houses["tenHem"] = "hẺm 236"
    roads["tenHem"] = ["Hẻm 236", ""]
    roads["tenDuong"] = ["Đường A", "Đường A"]
    return houses, roads


class RouteHierarchyTests(unittest.TestCase):
    def test_catalog_parent_expands_main_and_ten_alleys(self):
        names = [""] + [f"Hẻm {number}" for number in range(1, 11)]
        houses = gpd.GeoDataFrame(
            {"tenDuong": ["Đường Quyết Thắng"] * 11, "tenHem": names},
            geometry=[box(i * 10, 10, i * 10 + 5, 15) for i in range(11)], crs="EPSG:3857")
        roads = gpd.GeoDataFrame(
            {"tenDuong": ["đường quyết thắng"] * 11,
             "tenHem": [name.swapcase() for name in names]},
            geometry=[box(i * 10, 0, i * 10 + 5, 5) for i in range(11)], crs=houses.crs)
        catalog = build_route_catalog(houses, roads)
        self.assertTrue(catalog["hierarchical"])
        self.assertEqual(len(catalog["groups"]), 1)
        self.assertEqual(len(catalog["items"]), 11)
        selected = resolve_manual_selection(catalog, "ĐƯỜNG QUYẾT THẮNG")
        self.assertEqual(len(selected), 11)
        filtered_h, filtered_r = loc_tuyen(houses, roads, "Đường Quyết Thắng")
        self.assertEqual((len(filtered_h), len(filtered_r)), (11, 11))
        one_h, one_r = loc_tuyen(houses, roads, route_keys=[("đường quyết thắng", "hẻm 7")])
        self.assertEqual((len(one_h), len(one_r)), (1, 1))

    def test_case_and_unicode_normalization_preserves_accents_and_inner_spaces(self):
        decomposed = unicodedata.normalize("NFD", "Hẻm Nam Long")
        houses = gpd.GeoDataFrame(
            {"tenDuong": [" Đường Quyết Thắng "], "tenHem": ["hẻm nAm LONG"]},
            geometry=[box(0, 5, 5, 10)], crs="EPSG:3857")
        roads = gpd.GeoDataFrame(
            {"tenDuong": ["đường quyết thắng"], "tenHem": [decomposed]},
            geometry=[box(0, 0, 5, 5)], crs=houses.crs)
        self.assertEqual(len(build_route_catalog(houses, roads)["items"]), 1)
        roads.loc[0, "tenHem"] = "Hem Nam Long"
        self.assertEqual(build_route_catalog(houses, roads)["items"], [])
        roads.loc[0, "tenHem"] = "Hẻm  Nam Long"
        self.assertEqual(build_route_catalog(houses, roads)["items"], [])

    def test_same_alley_name_under_two_parents_is_not_merged(self):
        houses = gpd.GeoDataFrame(
            {"tenDuong": ["Đường A", "Đường B"], "tenHem": ["Hẻm 1", "Hẻm 1"]},
            geometry=[box(0, 5, 5, 10), box(20, 5, 25, 10)], crs="EPSG:3857")
        roads = gpd.GeoDataFrame(
            {"tenDuong": ["Đường A", "Đường B"], "tenHem": ["Hẻm 1", "Hẻm 1"]},
            geometry=[box(0, 0, 5, 5), box(20, 0, 25, 5)], crs=houses.crs)
        catalog = build_route_catalog(houses, roads)
        self.assertEqual(len(catalog["groups"]), 2)
        selected, _ = loc_tuyen(houses, roads, route_keys=[("Đường B", "Hẻm 1")])
        self.assertEqual(selected.tenDuong.tolist(), ["Đường B"])

    def test_schema_mismatch_blocks_instead_of_guessing(self):
        houses, roads = hierarchy_fixture()
        with self.assertRaisesRegex(ValueError, "Schema tenHem không đồng nhất"):
            build_route_catalog(houses.drop(columns="tenHem"), roads)
        report = kiem_tra_du_lieu(houses.drop(columns="tenHem"), roads)
        self.assertTrue(any("tenHem" in error for error in report["errors"]))

    def test_split_schema_numbers_from_ten_hem_and_preserves_attributes(self):
        houses, roads = hierarchy_fixture()
        report = kiem_tra_du_lieu(
            houses, roads, route_keys=[("đường a", "HẺM 236")])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["parent_count"], 1)
        self.assertEqual(report["alley_count"], 1)
        selected_h, selected_r = loc_tuyen(
            houses, roads, route_keys=[("Đường A", "Hẻm 236")])
        out = process(selected_h, selected_r, verbose=False,
                      reference_roads=roads, alley_contexts=report["_alley_contexts"])
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())
        self.assertEqual(out.tenDuong.tolist(), houses.tenDuong.tolist())
        self.assertEqual(out.tenHem.tolist(), houses.tenHem.tolist())
        self.assertEqual(out.parcel_id.tolist(), houses.parcel_id.tolist())

    def test_split_schema_sibling_contact_warns_but_other_parent_blocks(self):
        houses, roads = hierarchy_fixture()
        roads.loc[len(roads), ["tenDuong", "tenHem", "geometry"]] = [
            "Đường A", "Hẻm 99", box(1.95, 20, 6, 40)]
        roads.set_crs(houses.crs, inplace=True)
        selected = [("Đường A", "Hẻm 236")]
        report = kiem_tra_du_lieu(houses, roads, route_keys=selected)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("Bỏ qua dải chồng mỏng" in warning
                            for warning in report["warnings"]))

        roads.loc[2, "geometry"] = box(1.5, 20, 6, 40)
        report = kiem_tra_du_lieu(houses, roads, route_keys=selected)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("cùng đường cha" in warning for warning in report["warnings"]))

        roads.loc[2, ["tenDuong", "tenHem"]] = ["Đường B", "Hẻm 99"]
        report = kiem_tra_du_lieu(houses, roads, route_keys=selected)
        self.assertTrue(any("ở giữa hẻm" in error for error in report["errors"]))

    def test_unselected_invalid_legacy_road_does_not_block_selected_alley(self):
        houses, roads = alley_fixture("Hẻm 17 Đường Quyết Thắng")
        roads.loc[1, "tenDuong"] = "Đường Quyết Thắng"
        invalid = Polygon([(100, 100), (110, 110), (100, 110), (110, 100), (100, 100)])
        roads.loc[len(roads)] = ["đường bên hoa viên", invalid]
        roads.set_crs(houses.crs, inplace=True)
        report = kiem_tra_du_lieu(houses, roads, "Hẻm 17 Đường Quyết Thắng")
        self.assertEqual(report["errors"], [])
        roads.loc[0, "geometry"] = invalid
        report = kiem_tra_du_lieu(houses, roads, "Hẻm 17 Đường Quyết Thắng")
        self.assertTrue(report["errors"])


if __name__ == "__main__":
    unittest.main()
