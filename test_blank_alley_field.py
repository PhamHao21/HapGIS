# -*- coding: utf-8 -*-
"""A tenHem column left blank in only one layer must not block tenDuong-only data."""
import gc
import tempfile
import time
import unittest
from pathlib import Path

import geopandas as gpd

from app_service import chay_danh_so, kiem_tra_du_lieu
from core_housenumber import COL_SONHA, process
from route_catalog import build_route_catalog
from test_alley_numbering import alley_fixture
from test_field_mapping import fixtures


def blank_alley_houses(houses):
    houses = houses.copy()
    houses["tenHem"] = gpd.pd.Series([None] * len(houses), index=houses.index, dtype="object")
    return houses


class BlankAlleyFieldTests(unittest.TestCase):
    def test_blank_column_in_one_layer_falls_back_to_ten_duong(self):
        houses, roads = fixtures()
        reference = process(houses, roads, verbose=False)[COL_SONHA].tolist()
        for houses_x, roads_x in ((blank_alley_houses(houses), roads),
                                  (houses, roads.assign(tenHem=["", "  ", None]))):
            with self.subTest(blank_in="houses" if "tenHem" in houses_x else "roads"):
                self.assertFalse(build_route_catalog(houses_x, roads_x)["hierarchical"])
                report = kiem_tra_du_lieu(houses_x, roads_x)
                self.assertEqual(report["errors"], [])
                self.assertEqual(report["matched_count"], 3)
                self.assertEqual(process(houses_x, roads_x, verbose=False)[COL_SONHA].tolist(), reference)

    def test_legacy_alley_names_still_resolve(self):
        houses, roads = alley_fixture("Hẻm 236 đường A")
        out = process(blank_alley_houses(houses), roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses["expected"].tolist())

    def test_one_sided_column_with_values_is_still_an_error(self):
        houses, roads = fixtures()
        houses = houses.assign(tenHem=["Hẻm 1", None, None, None])
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(any("Schema tenHem không đồng nhất" in e for e in report["errors"]))

    def test_run_from_files(self):
        houses, roads = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            blank_alley_houses(houses).to_file(source, layer="parcels", driver="GPKG")
            roads.to_file(source, layer="roads", driver="GPKG")
            out = chay_danh_so(str(source), "parcels", str(source), "roads", "", str(Path(tmp) / "out.gpkg"))
            self.assertEqual(int(out[COL_SONHA].notna().sum()), 3)


class BlankAlleyFieldGuiTests(unittest.TestCase):
    def tearDown(self):
        gc.collect()  # Dispose Tk fonts on the UI thread between root windows.

    def test_gui_loads_routes_and_runs(self):
        from app_gui import AppDanhSoNha

        houses, roads = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            blank_alley_houses(houses).to_file(source, layer="parcels", driver="GPKG")
            roads.to_file(source, layer="roads", driver="GPKG")
            app = AppDanhSoNha()
            app.withdraw()
            errors = []
            app.report_callback_exception = lambda *args: errors.append(args)

            def wait(predicate):
                deadline = time.monotonic() + 30
                while not predicate() and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                self.assertFalse(errors, errors)
                self.assertTrue(predicate(), app.log_lines[-5:])

            try:
                app.sources["thua"]["path"].set(str(source))
                app.sources["duong"]["path"].set(str(source))
                wait(lambda: all(s["layers"] for s in app.sources.values()))
                app.sources["thua"]["layer"].set("parcels")
                app.tai_truong("thua")
                app.sources["duong"]["layer"].set("roads")
                app.tai_truong("duong")
                wait(lambda: app.schema_hierarchical is not None and not app.value_loading)
                self.assertFalse(app.schema_hierarchical)
                self.assertIn("dữ liệu cũ", app.field_hint.cget("text"))
                app.kiem_tra()
                wait(lambda: not app.check_loading)
                self.assertEqual(app.check_report["errors"], [])
                self.assertEqual(str(app.btn_check.cget("state")), "normal")
            finally:
                for timer in app.tk.call("after", "info"):
                    app.tk.call("after", "cancel", timer)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
