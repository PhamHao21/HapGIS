import unittest
import customtkinter as ctk

from ui_widgets import RouteMultiSelect, SearchableCombo


class DropdownTests(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()

    def test_bounded_search_scroll_select_and_invalidation(self):
        root = ctk.CTk()
        root.geometry("500x400+30+30")
        selected = []
        combo = SearchableCombo(root, values=[f"Trường {i}" for i in range(100)] + ["Đường Nguyễn Huệ"],
                                command=selected.append, state="readonly", width=350)
        combo.pack(padx=20, pady=20)
        try:
            root.update()
            combo._open_dropdown_menu()
            root.update_idletasks()
            self.assertLessEqual(combo.popup.winfo_height(), 300)
            self.assertLessEqual(combo.popup.winfo_width(), 420)
            self.assertEqual(combo.listbox.size(), 101)
            combo.listbox.yview_moveto(1)
            self.assertGreater(combo.listbox.yview()[0], 0)
            combo.search_var.set("duong nguyen hue")
            self.assertEqual(combo.filtered_values, ["Đường Nguyễn Huệ"])
            combo._choose()
            self.assertEqual(combo.get(), "Đường Nguyễn Huệ")
            self.assertEqual(selected, ["Đường Nguyễn Huệ"])
            self.assertIsNone(combo.popup)
            combo._open_dropdown_menu()
            combo.search_var.set("no-match")
            self.assertEqual(combo.listbox.size(), 0)
            combo._choose()  # An empty search must never select an old value.
            self.assertEqual(selected, ["Đường Nguyễn Huệ"])
            combo.configure(values=["New field"], state="disabled")
            self.assertIsNone(combo.popup)
            combo.set("")
            self.assertEqual(combo.get(), "")
            combo._open_dropdown_menu()
            self.assertIsNone(combo.popup)
        finally:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()

    def test_route_multiselect_summary_remove_clear_and_bounded_popup(self):
        root = ctk.CTk()
        root.geometry("600x500+30+30")
        catalog = {
            "hierarchical": True,
            "groups": [{
                "key": "đường a", "parent": "Đường A",
                "items": [
                    {"key": ("đường a", ""), "parent": "Đường A", "alley": "",
                     "label": "Đường A", "is_main": True},
                    *[{"key": ("đường a", f"hẻm {i}"), "parent": "Đường A", "alley": f"Hẻm {i}",
                       "label": f"Đường A › Hẻm {i}", "is_main": False} for i in range(1, 21)],
                ],
            }],
        }
        catalog["items"] = catalog["groups"][0]["items"]
        catalog["keys"] = [item["key"] for item in catalog["items"]]
        widget = RouteMultiSelect(root, width=420)
        widget.pack(padx=20, pady=20)
        try:
            widget.set_catalog(catalog, select_all=True)
            root.update()
            self.assertEqual(len(widget.get_route_keys()), 21)
            self.assertEqual(widget.get(), "21 tuyến đã chọn")
            widget.remove_key(("đường a", "hẻm 7"))
            self.assertEqual(len(widget.get_route_keys()), 20)
            widget.open_popup()
            root.update_idletasks()
            self.assertLessEqual(widget.popup.winfo_height(), 590)
            self.assertLessEqual(widget.popup.winfo_width(), 780)
            before = widget._route_canvas.yview()[0]
            widget._route_canvas.event_generate("<MouseWheel>", delta=-120)
            root.update_idletasks()
            self.assertGreater(widget._route_canvas.yview()[0], before)
            widget.close_popup()
            widget.clear_selection()
            self.assertEqual(widget.get_route_keys(), [])
            widget.set("Đường A › Hẻm 2")
            self.assertIsNone(widget.get_route_keys())
            self.assertEqual(widget.get_manual_text(), "Đường A › Hẻm 2")
        finally:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()

    def test_legacy_routes_are_flat_without_duplicate_main_rows(self):
        root = ctk.CTk()
        root.geometry("600x500+30+30")
        items = [{"key": (f"hẻm {i}", ""), "parent": f"Hẻm {i}", "alley": "",
                  "label": f"Hẻm {i}", "is_main": True} for i in range(1, 6)]
        catalog = {
            "hierarchical": False,
            "groups": [{"key": item["key"][0], "parent": item["parent"], "items": [item]}
                       for item in items],
            "items": items, "keys": [item["key"] for item in items],
        }
        widget = RouteMultiSelect(root, width=420)
        widget.pack(padx=20, pady=20)
        try:
            widget.set_catalog(catalog, select_all=True)
            root.update()
            widget.open_popup()
            root.update_idletasks()
            def descendants(parent):
                result = []
                for child in parent.winfo_children():
                    result.append(child)
                    result.extend(descendants(child))
                return result
            labels = [child.cget("text") for child in descendants(widget.popup)
                      if isinstance(child, __import__("tkinter").Checkbutton)]
            self.assertEqual(labels, [f"Hẻm {i}" for i in range(1, 6)])
            self.assertNotIn("Đường chính", labels)
        finally:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
