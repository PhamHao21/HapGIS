# -*- coding: utf-8 -*-
"""Exercise real widgets and background loading without interactive dialogs."""
import tempfile
import gc
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app_gui import AppDanhSoNha
from test_field_mapping import fixtures


class GuiWorkflowTests(unittest.TestCase):
    def tearDown(self):
        # This harness pumps update(), not mainloop(). Tk finalizers must run
        # here on the UI thread, before a later test starts a pandas worker.
        gc.collect()

    def test_layers_fields_values_invalidation_and_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.gpkg"
            houses, roads = fixtures()
            houses.to_file(path, layer="parcels", driver="GPKG")
            roads.to_file(path, layer="roads", driver="GPKG")
            houses.drop(columns="tenDuong").to_file(path, layer="only_alley", driver="GPKG")
            app = AppDanhSoNha()
            app.withdraw()
            callbacks = []
            app.report_callback_exception = lambda *error: callbacks.append(error)

            def wait_until(predicate):
                deadline = time.monotonic() + 30
                while not predicate() and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertFalse(callbacks, callbacks)
                self.assertTrue(predicate(), f"GUI operation timed out; recent log: {app.log_lines[-6:]}")

            try:
                for source in app.sources.values():
                    source["path"].set(str(path))
                wait_until(lambda: all(s["ready"] for s in app.sources.values()))
                house, road = app.sources["thua"], app.sources["duong"]
                self.assertEqual(house["layer"].get(), "parcels")
                self.assertEqual(road["layer"].get(), "roads")
                self.assertNotIn("field", house)
                self.assertNotIn("field", road)
                self.assertEqual(app.btn_run.cget("state"), "disabled")
                wait_until(lambda: not app.value_loading)
                self.assertEqual(app.entry_tuyen.cget("values"), ["H9", "H10"])
                app.entry_tuyen.set("h9")  # Manual input, different case.
                app.output_var.set(str(Path(tmp) / "output.gpkg"))
                self.assertEqual(app.btn_run.cget("state"), "normal")
                with patch.object(app, "hien_bao_cao") as show_report:
                    app.kiem_tra()
                    wait_until(lambda: not app.check_loading)
                    self.assertEqual(app.check_report["matched_count"], 2)
                    self.assertEqual(app.check_report["errors"], [])
                    show_report.assert_called_once()
                previous_check = app.check_generation
                app.entry_tuyen.set("H9")
                self.assertIsNone(app.check_report)
                app.hang_doi.put(("check", previous_check, None, "Stale error"))
                with patch("app_gui.messagebox.showerror") as stale_error:
                    app.update()
                    stale_error.assert_not_called()
                app.hien_quy_tac()
                app.update_idletasks()
                self.assertTrue(app.rules_window.winfo_exists())
                app.rules_window.destroy()
                gc.collect()
                with patch("app_gui.messagebox.showinfo") as success, patch("app_gui.messagebox.showerror") as error:
                    app.bat_dau()
                    self.assertTrue(app.dang_chay)
                    self.assertEqual(house["layer"].cget("state"), "disabled")
                    wait_until(lambda: not app.dang_chay)
                    error.assert_not_called()
                    success.assert_called_once()
                self.assertTrue(Path(app.output_hien_tai).exists())
                self.assertEqual(house["layer"].cget("state"), "readonly")

                # A late background response must not restore old suggestions.
                old_token = app.value_generation
                road["layer"].set("only_alley")
                app.tai_truong("duong")
                app.hang_doi.put(("values", old_token, ["STALE"], None))
                self.assertEqual(app.value_var.get(), "")
                self.assertEqual(app.btn_run.cget("state"), "disabled")
                wait_until(lambda: "Thiếu trường" in road["hint"].cget("text"))
                self.assertFalse(road["ready"])
                self.assertNotIn("tenHem", road["fields"])
                self.assertNotIn("tenDuong", road["fields"])
                self.assertEqual(app.entry_tuyen.cget("values"), [])
                self.assertEqual(app.entry_tuyen.cget("state"), "disabled")
                self.assertEqual(app.btn_run.cget("state"), "disabled")

                # Returning to valid input automatically reloads the route dropdown.
                road["layer"].set("roads")
                app.tai_truong("duong")
                wait_until(lambda: road["ready"] and not app.value_loading)
                self.assertEqual(app.entry_tuyen.cget("values"), ["H9", "H10"])

                road["path"].set(str(Path(tmp) / "missing.shp"))
                wait_until(lambda: "Không đọc được" in road["hint"].cget("text"))
                self.assertFalse(road["ready"])
                self.assertEqual(app.btn_run.cget("state"), "disabled")
            finally:
                # Cancel Tcl timers without deleting commands owned by CTk children.
                for timer in app.tk.call("after", "info"):
                    app.tk.call("after", "cancel", timer)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
