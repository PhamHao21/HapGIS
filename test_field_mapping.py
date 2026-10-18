# -*- coding: utf-8 -*-
"""Regression coverage for the fixed tenDuong schema and real GIS layer I/O."""
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import box

from app_service import (
    chay_danh_so, doc_nguon, gia_tri_chung, liet_ke_gia_tri,
    liet_ke_layer, liet_ke_truong, loc_tuyen,
)
from core_housenumber import process, COL_SONHA


def fixtures():
    houses = gpd.GeoDataFrame(
        {"tenDuong": [" H9 ", "h9", "H10", None]},
        geometry=[box(10, 5, 20, 15), box(20, 5, 30, 15),
                  box(40, 5, 50, 15), box(60, 5, 70, 15)], crs="EPSG:3857",
    )
    roads = gpd.GeoDataFrame(
        {"tenDuong": ["H9", "H10", "Other"]},
        geometry=[box(0, -5, 35, 5), box(35, -5, 55, 5), box(70, -5, 90, 5)],
        crs=houses.crs,
    )
    return houses, roads


class RouteSchemaTests(unittest.TestCase):
    def setUp(self):
        self.houses, self.roads = fixtures()

    def test_filter_uses_ten_duong_and_normalizes_values(self):
        houses, roads = loc_tuyen(self.houses, self.roads, "h9")
        self.assertEqual(len(houses), 2)
        self.assertEqual(roads.tenDuong.tolist(), ["H9"])
        self.assertEqual(len(self.houses), 4)

    def test_multiple_and_all_values(self):
        houses, roads = loc_tuyen(self.houses, self.roads, "H9; h10")
        self.assertEqual((len(houses), len(roads)), (3, 2))
        houses, roads = loc_tuyen(self.houses, self.roads, "")
        self.assertEqual((len(houses), len(roads)), (4, 3))

    def test_unmatched_values_are_rejected(self):
        for value in ("H9;missing", "; ;"):
            with self.assertRaises(ValueError):
                loc_tuyen(self.houses, self.roads, value)
        self.roads["tenDuong"] = "Different"
        with self.assertRaises(ValueError):
            loc_tuyen(self.houses, self.roads, "")

    def test_exact_value_containing_semicolon(self):
        self.houses.loc[0, "tenDuong"] = "H9;A"
        self.roads.loc[0, "tenDuong"] = "H9;A"
        houses, _ = loc_tuyen(self.houses, self.roads, "H9;A")
        self.assertEqual(len(houses), 1)

    def test_numbering_preserves_source_attributes(self):
        houses, roads = loc_tuyen(self.houses, self.roads, "H9")
        before = houses.copy()
        actual = process(houses, roads, verbose=False)
        self.assertTrue(actual[COL_SONHA].notna().all())
        self.assertEqual(actual.tenDuong.tolist(), houses.tenDuong.tolist())
        self.assertNotIn("tenHem", actual.columns)
        assert_geodataframe_equal(houses, before)

    def test_geopackage_values_and_end_to_end_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.gpkg"
            output = Path(tmp) / "result.gpkg"
            self.houses.to_file(path, layer="parcels", driver="GPKG")
            self.roads.to_file(path, layer="roads", driver="GPKG")
            self.assertEqual(set(liet_ke_layer(path)), {"parcels", "roads"})
            self.assertIn("tenDuong", liet_ke_truong(path, "roads"))
            self.assertNotIn("geometry", liet_ke_truong(path, "roads"))
            self.assertEqual(doc_nguon(path, "roads").tenDuong.tolist(), ["H9", "H10", "Other"])
            values = gia_tri_chung(liet_ke_gia_tri(path, "parcels"),
                                  liet_ke_gia_tri(path, "roads"))
            self.assertEqual(values, ["H10", "H9"])
            out = chay_danh_so(str(path), "parcels", str(path), "roads", "H9", str(output))
            reread = gpd.read_file(output)
            self.assertEqual(len(out), 2)
            self.assertEqual(len(reread), 2)
            self.assertTrue(reread[COL_SONHA].notna().all())
            self.assertEqual(reread.tenDuong.tolist(), [" H9 ", "h9"])

    def test_numeric_values_and_nulls(self):
        self.houses["tenDuong"] = [9, 9, 10, None]
        self.roads["tenDuong"] = [9.0, 10.0, 11.0]
        houses, _ = loc_tuyen(self.houses, self.roads, "9.0")
        self.assertEqual(len(houses), 2)

    def test_missing_or_misspelled_ten_duong_never_falls_back_to_ten_hem(self):
        for side in ("houses", "roads"):
            for alternative in (None, "TenDuong", "tenduong"):
                houses, roads = fixtures()
                source = houses if side == "houses" else roads
                changed = source.drop(columns="tenDuong") if alternative is None else source.rename(columns={"tenDuong": alternative})
                houses, roads = (changed, roads) if side == "houses" else (houses, changed)
                with self.subTest(side=side, alternative=alternative):
                    with self.assertRaisesRegex(ValueError, "tenDuong"):
                        loc_tuyen(houses, roads, "")
                    with self.assertRaisesRegex(ValueError, "tenDuong"):
                        process(houses, roads, verbose=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "only_alley.gpkg"
            self.houses.drop(columns="tenDuong").to_file(path, driver="GPKG")
            with self.assertRaisesRegex(ValueError, "tenDuong"):
                liet_ke_gia_tri(path)

    def test_shapefile_and_gdb_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            shp = Path(tmp) / "parcels.shp"
            self.houses.to_file(shp)
            self.assertIn("tenDuong", liet_ke_truong(shp))
            self.assertEqual(set(liet_ke_gia_tri(shp)), {"h9", "h10"})
            gdb = Path(tmp) / "sources.gdb"
            self.houses.to_file(gdb, layer="parcels", driver="OpenFileGDB")
            self.roads.to_file(gdb, layer="roads", driver="OpenFileGDB")
            self.assertEqual(set(liet_ke_layer(gdb)), {"parcels", "roads"})
            self.assertIn("tenDuong", liet_ke_truong(gdb, "roads"))
            self.assertEqual(len(doc_nguon(gdb, "parcels")), 4)
            self.assertIn("h9", liet_ke_gia_tri(gdb, "roads"))
            with self.assertRaises(ValueError):
                liet_ke_truong(gdb)


if __name__ == "__main__":
    unittest.main()
