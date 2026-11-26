# -*- coding: utf-8 -*-
"""soNhaCu: existing house numbers are kept as fixed anchors; the rest fill in from the start."""
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, box

from app_service import COT_RA_SOAT, chay_danh_so
from core_housenumber import (
    COL_BEN, COL_LY_DO_SO_CU, COL_SO_CU, COL_SONHA, doc_so_nha_cu, process,
)
from test_alley_numbering import alley_fixture

CRS = "EPSG:3405"
# North-south lane: numbering starts at the north end; east side = TRAI (odd).
LANE = LineString([(0, 200), (0, 0)])


def run(east_anchors, west_anchors=None, west_count=0):
    """10 east parcels north->south (index 0 = northernmost), optional west parcels."""
    parcels, names, anchors = [], [], []
    for i in range(10):
        y = 190 - 18 * i
        parcels.append(box(3, y - 15, 20, y))
        names.append(f"e{i}")
        anchors.append(east_anchors.get(i))
    for i in range(west_count):
        y = 190 - 18 * i
        parcels.append(box(-20, y - 15, -3, y))
        names.append(f"w{i}")
        anchors.append((west_anchors or {}).get(i))
    houses = gpd.GeoDataFrame({"tenDuong": ["A"] * len(parcels), "ten": names, COL_SO_CU: anchors},
                              geometry=parcels, crs=CRS)
    roads = gpd.GeoDataFrame({"tenDuong": ["A"]}, geometry=[LANE], crs=CRS)
    out = process(houses, roads, verbose=False)
    so = dict(zip(out["ten"], out[COL_SONHA]))
    ly_do = dict(zip(out["ten"], out[COL_LY_DO_SO_CU].fillna("")))
    ben = dict(zip(out["ten"], out[COL_BEN]))
    return so, ly_do, ben


def east(so):
    return [so[f"e{i}"] for i in range(10)]


SEQUENTIAL = [str(n) for n in range(1, 20, 2)]


class ExistingNumberTests(unittest.TestCase):
    def test_lane_layout_is_odd_on_the_east(self):
        so, _, ben = run({})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertEqual({ben[f"e{i}"] for i in range(10)}, {"TRAI"})

    def test_single_anchor_packs_before_and_continues_after(self):
        so, ly_do, _ = run({4: "65"})
        self.assertEqual(east(so), ["1", "3", "5", "7", "65", "67", "69", "71", "73", "75"])
        self.assertEqual(set(ly_do.values()), {""})

    def test_several_anchors_and_numeric_field(self):
        so, _, _ = run({2: 21.0, 6: 65})
        self.assertEqual(east(so), ["1", "3", "21", "23", "25", "27", "65", "67", "69", "71"])

    def test_anchor_on_the_other_side_is_independent(self):
        so, _, _ = run({4: "65"}, west_anchors={1: "40"}, west_count=3)
        self.assertEqual([so["w0"], so["w1"], so["w2"]], ["2", "40", "42"])
        self.assertEqual(so["e4"], "65")

    def test_reversed_anchors_keep_tool_numbers_and_explain(self):
        so, ly_do, _ = run({2: "65", 6: "21"})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertIn("ngược chiều", ly_do["e6"])
        self.assertIn("tuyến có mốc lỗi", ly_do["e2"])

    def test_wrong_parity_means_wrong_side(self):
        so, ly_do, _ = run({4: "64"})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertIn("chẵn", ly_do["e4"])

    def test_not_enough_numbers_before_anchor(self):
        so, ly_do, _ = run({2: "3"})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertIn("không đủ số cho 2 thửa", ly_do["e2"])

    def test_duplicate_and_malformed_values(self):
        so, ly_do, _ = run({2: "21", 5: "21"})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertIn("trùng mốc 21", ly_do["e5"])
        so, ly_do, _ = run({3: "7A"})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertIn("không phải số nguyên", ly_do["e3"])

    def test_blank_values_change_nothing(self):
        so, ly_do, _ = run({1: "", 3: None, 5: "  "})
        self.assertEqual(east(so), SEQUENTIAL)
        self.assertEqual(set(ly_do.values()), {""})

    def test_parse_alley_values(self):
        self.assertEqual(doc_so_nha_cu("236/9", "236"), (9, ""))
        self.assertEqual(doc_so_nha_cu("9", "236"), (9, ""))
        self.assertIsNone(doc_so_nha_cu("237/9", "236")[0])
        self.assertIsNone(doc_so_nha_cu("236/9")[0])

    def test_alley_anchor_keeps_prefix_number(self):
        houses, roads = alley_fixture()
        houses[COL_SO_CU] = None
        houses.loc[houses.parcel_id == "TRAI-3", COL_SO_CU] = "236/15"
        out = process(houses, roads, verbose=False)
        so = dict(zip(out.parcel_id, out[COL_SONHA]))
        self.assertEqual([so[f"TRAI-{r}"] for r in range(1, 5)], ["236/1", "236/3", "236/15", "236/17"])
        self.assertEqual([so[f"PHAI-{r}"] for r in range(1, 5)], ["236/2", "236/4", "236/6", "236/8"])

    def test_run_from_files_writes_reasons_to_review_column(self):
        anchors = [None] * 10
        anchors[2], anchors[6] = "65", "21"
        houses = gpd.GeoDataFrame(
            {"tenDuong": ["A"] * 10, COL_SO_CU: anchors},
            geometry=[box(3, 175 - 18 * i, 20, 190 - 18 * i) for i in range(10)], crs=CRS)
        roads = gpd.GeoDataFrame({"tenDuong": ["A"]}, geometry=[LANE], crs=CRS)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            houses.to_file(source, layer="parcels", driver="GPKG")
            roads.to_file(source, layer="roads", driver="GPKG")
            for name in ("out.gpkg", "out.shp"):
                out_path = Path(tmp) / name
                chay_danh_so(str(source), "parcels", str(source), "roads", "", str(out_path))
                saved = gpd.read_file(out_path)
                self.assertNotIn(COL_LY_DO_SO_CU, saved.columns)
                self.assertIn(COL_SO_CU, saved.columns)
                review = saved[COT_RA_SOAT].fillna("")
                self.assertIn("ngược chiều", review.iloc[6])
                self.assertIn("tuyến có mốc lỗi", review.iloc[2])


if __name__ == "__main__":
    unittest.main()
