"""Real GUI metadata, previews, alley report and source invalidation."""
import tempfile
import gc
import time
import unittest
from pathlib import Path

from app_gui import AppDanhSoNha
from test_alley_numbering import alley_fixture


class AlleyGuiTests(unittest.TestCase):
    def tearDown(self):
        gc.collect()  # Dispose Tk fonts on the UI thread between root windows.

    def test_preview_report_scroll_and_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            houses, roads = alley_fixture()
            houses.to_file(source, layer="parcels", driver="GPKG")
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
                for item in app.sources.values():
                    item["path"].set(str(source))
                wait(lambda: app.truong_hop_le() and not app.value_loading)
                app.entry_tuyen.set("Hẻm 236 đường A")
                self.assertIn("236/1", app.route_hint.cget("text"))
                app.kiem_tra()
                wait(lambda: not app.check_loading)
                self.assertEqual(app.check_report["errors"], [])
                self.assertTrue(app.report_window.winfo_exists())
                self.assertEqual(app.route_table.cget("height"), 165)
                rows = app.check_report["alley_routes"]
                self.assertEqual(rows[0]["parent"], "Đường A")
                self.assertTrue(any(child.cget("text") == "236" for child in app.route_table.winfo_children()))
                # All routes retains the same bounded report table.
                app.entry_tuyen.set("")
                app.kiem_tra()
                wait(lambda: not app.check_loading)
                self.assertEqual(len(app.check_report["alley_routes"]), 1)
                app.entry_tuyen.set("Hẻm 1 A;Hẻm 236 đường A")
                self.assertIn("Nhiều tuyến", app.route_hint.cget("text"))
                self.assertIsNone(app.check_report)
                app.entry_tuyen.set("Hẻm 1A")
                self.assertIn("chuẩn hóa", app.route_hint.cget("text"))
                app.sources["duong"]["path"].set("")
                app.update()
                self.assertNotIn("236/1", app.route_hint.cget("text"))
                self.assertFalse(app.truong_hop_le())
            finally:
                for timer in app.tk.call("after", "info"):
                    app.tk.call("after", "cancel", timer)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
