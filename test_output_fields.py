# -*- coding: utf-8 -*-
"""Output parcels always carry the standard attribute fields, in order."""
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import Point, Polygon

from app_service import TRUONG_THUA_DAU_RA, chay_danh_so, chuan_hoa_truong_dau_ra
from test_field_mapping import fixtures


class OutputFieldTests(unittest.TestCase):
    def test_all_fields_in_order_and_extra_columns_kept(self):
        houses, _ = fixtures()
        houses["ghiChu"] = "x"
        out = chuan_hoa_truong_dau_ra(houses)
        self.assertEqual(list(out.columns[:len(TRUONG_THUA_DAU_RA)]), TRUONG_THUA_DAU_RA)
        self.assertEqual(list(out.columns[len(TRUONG_THUA_DAU_RA):]), ["ghiChu", "geometry"])
        self.assertEqual(out.object_ID.tolist(), [1, 2, 3, 4])

    def test_source_values_kept_only_blanks_filled(self):
        houses, _ = fixtures()  # box(10, 5, 20, 15) etc.: 100 m² each
        houses["dienTich"] = [250.0, None, None, None]   # legal area differs from geometry
        houses["toaDoX"] = ["123,4", "", None, None]     # text values from source
        houses["maTinh"] = ["92", None, "92", None]
        out = chuan_hoa_truong_dau_ra(houses)
        self.assertEqual(out.dienTich.tolist(), [250.0, 100.0, 100.0, 100.0])
        self.assertEqual(out.toaDoX.tolist()[:2], ["123,4", "25.000"])
        self.assertEqual(out.toaDoY.tolist(), [10.0, 10.0, 10.0, 10.0])
        self.assertEqual(out.maTinh.fillna("").tolist(), ["92", "", "92", ""])

    def test_coordinates_are_parcel_centroid_kept_inside(self):
        houses, _ = fixtures()
        # Irregular parcel: centroid (not the bbox centre) and inside the parcel.
        houses.loc[0, "geometry"] = Polygon([(0, 0), (30, 0), (30, 10), (0, 30)])
        # L-shaped parcel whose centroid falls in the notch, outside the parcel.
        houses.loc[1, "geometry"] = Polygon([(0, 0), (40, 0), (40, 2), (2, 2), (2, 40), (0, 40)])
        out = chuan_hoa_truong_dau_ra(houses)
        centroid = houses.geometry[0].centroid
        self.assertAlmostEqual(out.toaDoX[0], round(centroid.x, 3))
        self.assertAlmostEqual(out.toaDoY[0], round(centroid.y, 3))
        self.assertFalse(houses.geometry[1].intersects(houses.geometry[1].centroid))
        self.assertTrue(houses.geometry[1].covers(Point(out.toaDoX[1], out.toaDoY[1])))

    def test_run_writes_standard_fields_with_source_object_ids(self):
        houses, roads = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            houses.to_file(source, layer="parcels", driver="GPKG")
            roads.to_file(source, layer="roads", driver="GPKG")
            fids = list(pyogrio.read_dataframe(source, layer="parcels", columns=[],
                                               read_geometry=False, fid_as_index=True).index)
            gpkg = Path(tmp) / "out.gpkg"
            chay_danh_so(str(source), "parcels", str(source), "roads", "", str(gpkg))
            saved = gpd.read_file(gpkg)
            self.assertEqual(list(saved.columns[:len(TRUONG_THUA_DAU_RA)]), TRUONG_THUA_DAU_RA)
            self.assertEqual(sorted(saved.object_ID.tolist()), sorted(fids))
            self.assertEqual(int(saved.soNhaHienThi.notna().sum()), 3)
            shp = Path(tmp) / "out.shp"
            chay_danh_so(str(source), "parcels", str(source), "roads", "", str(shp))
            self.assertEqual(len(gpd.read_file(shp).columns), len(saved.columns))


if __name__ == "__main__":
    unittest.main()
