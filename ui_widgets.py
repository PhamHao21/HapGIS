# -*- coding: utf-8 -*-
"""Small, searchable dropdowns for the desktop GIS workflow."""
import tkinter as tk
from tkinter import ttk
import unicodedata
import re
import customtkinter as ctk


class StableScrollableFrame(ctk.CTkScrollableFrame):
    """Avoid CTk 6 scrollbar redraw re-entry for unchanged canvas fractions.

    CTkScrollbar._draw calls update_idletasks; during nested layout this can
    dispatch the same yscroll notification recursively until the UI hangs.
    Record the fractions before drawing so identical notifications are no-ops.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._last_scroll_fractions = None
        self._parent_canvas.configure(yscrollcommand=self._update_scrollbar)

    def _update_scrollbar(self, start, end):
        fractions = (round(float(start), 8), round(float(end), 8))
        if fractions != self._last_scroll_fractions:
            self._last_scroll_fractions = fractions
            self._scrollbar.set(start, end)


def search_key(value):
    text = unicodedata.normalize("NFD", str(value).casefold().replace("đ", "d"))
    return "".join(char for char in text if not unicodedata.combining(char))


class SearchableCombo(ctk.CTkComboBox):
    """Keep CTk's entry API, replace the unbounded native menu with a listbox.

    Search is accent-insensitive for discovery only; selected values are untouched.
    The popup uses physical pixels and stays inside the current screen bounds.
    """
    def __init__(self, master, **kwargs):
        self.popup = None
        self._outside_binding = None
        self._move_binding = None
        self._closing_timer = None
        self._owner_variable = kwargs.get("variable") or tk.StringVar(master=master)
        kwargs["variable"] = self._owner_variable
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        super().__init__(master, **kwargs)
        self.bind("<Down>", self._open_with_keyboard)
        self.bind("<Alt-Down>", self._open_with_keyboard)
        self.bind("<Button-1>", self._entry_click)

    def set(self, value):
        # CTkComboBox.set cannot clear disabled entries in CTk 6.0.
        self._owner_variable.set(value)

    def configure(self, require_redraw=False, **kwargs):
        if "values" in kwargs or kwargs.get("state") == "disabled":
            self.close_popup()
        return super().configure(require_redraw=require_redraw, **kwargs)

    def _entry_click(self, _event):
        if self.cget("state") == "readonly":
            self._clicked()

    def _open_with_keyboard(self, _event=None):
        self._open_dropdown_menu()
        return "break"

    def _clicked(self, event=None):
        if self.popup:
            self.close_popup()
        else:
            self._open_dropdown_menu()

    def _open_dropdown_menu(self):
        if self.cget("state") == "disabled" or self.popup:
            return
        root = self.winfo_toplevel()
        previous = getattr(root, "_active_dropdown", None)
        if previous and previous is not self:
            previous.close_popup()
        root._active_dropdown = self
        dark = ctk.get_appearance_mode() == "Dark"
        bg, ink, muted, border = ("#2C2534", "#FFF1F8", "#C1ADC9", "#514056") if dark else ("#FFFFFF", "#34263F", "#7B6B85", "#F0DCE8")
        popup = self.popup = tk.Toplevel(root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(root)
        popup.configure(bg=border)
        panel = tk.Frame(popup, bg=bg)
        panel.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(panel, text="TÌM TRONG DANH SÁCH", bg=bg, fg=muted,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=12, pady=(9, 3))
        self.search_var = tk.StringVar(popup)
        search = tk.Entry(panel, textvariable=self.search_var, relief="flat", bg=bg, fg=ink,
                          insertbackground=ink, highlightthickness=1, highlightbackground=border,
                          highlightcolor="#DB2777", font=("Segoe UI", 11))
        search.pack(fill="x", padx=12, pady=(0, 7), ipady=4)
        list_frame = tk.Frame(panel, bg=bg)
        list_frame.pack(fill="both", expand=True, padx=7)
        self.listbox = tk.Listbox(list_frame, height=7, activestyle="none", borderwidth=0,
                                  highlightthickness=0, bg=bg, fg=ink, selectbackground="#FCE7F3",
                                  selectforeground="#9D174D", exportselection=False,
                                  font=("Segoe UI", 11), selectmode="browse")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.result_label = tk.Label(panel, anchor="w", bg=bg, fg=muted, font=("Segoe UI", 9))
        self.result_label.pack(fill="x", padx=12, pady=(5, 8))
        self.search_var.trace_add("write", self._filter_values)
        self._filter_values()
        search.bind("<Down>", self._focus_list)
        search.bind("<Return>", self._choose)
        self.listbox.bind("<Return>", self._choose)
        self.listbox.bind("<ButtonRelease-1>", self._choose)
        self.listbox.bind("<MouseWheel>", self._wheel)
        self.listbox.bind("<Button-4>", lambda _: self.listbox.yview_scroll(-1, "units"))
        self.listbox.bind("<Button-5>", lambda _: self.listbox.yview_scroll(1, "units"))
        popup.bind("<Escape>", lambda _: self.close_popup(refocus=True))
        popup.bind("<FocusOut>", self._check_focus)
        popup.update_idletasks()
        # Hard physical-pixel limits: long layers/field lists never cover the screen.
        width = min(420, max(280, self.winfo_width()), self.winfo_screenwidth() - 24)
        height = min(300, popup.winfo_reqheight(), self.winfo_screenheight() - 48)
        x = max(8, min(self.winfo_rootx(), self.winfo_screenwidth() - width - 8))
        below = self.winfo_rooty() + self.winfo_height() + 4
        y = below if below + height < self.winfo_screenheight() - 12 else self.winfo_rooty() - height - 4
        y = max(8, min(y, self.winfo_screenheight() - height - 8))
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        search.focus_set()
        self._outside_binding = root.bind("<Button-1>", self._outside_click, add="+")
        self._move_binding = root.bind("<Configure>", self._owner_moved, add="+")

    def _filter_values(self, *_):
        key = search_key(self.search_var.get())
        self.filtered_values = [value for value in self.cget("values") if key in search_key(value)]
        self.listbox.delete(0, "end")
        if self.filtered_values:
            self.listbox.insert("end", *self.filtered_values)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        count = len(self.filtered_values)
        self.result_label.configure(text=f"{count} kết quả · ↑ ↓ chọn · Enter xác nhận" if count else "Không tìm thấy giá trị phù hợp")

    def _focus_list(self, _event=None):
        self.listbox.focus_set()
        return "break"

    def _wheel(self, event):
        self.listbox.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _choose(self, _event=None):
        selected = self.listbox.curselection()
        if selected:
            value = self.filtered_values[selected[0]]
            self.set(value)
            self.close_popup(refocus=True)
            if self._command:
                self._command(value)
        return "break"

    def _outside_click(self, event):
        if event.widget is self._entry or event.widget is self._canvas:
            return
        self.close_popup()

    def _owner_moved(self, event):
        if event.widget is self.winfo_toplevel():
            self.close_popup()

    def _check_focus(self, _event=None):
        if not self.popup:
            return
        if self._closing_timer:
            self.after_cancel(self._closing_timer)
        self._closing_timer = self.after(80, self._close_if_unfocused)

    def _close_if_unfocused(self):
        self._closing_timer = None
        if self.popup:
            focus = self.focus_get()
            if focus is None or focus.winfo_toplevel() != self.popup:
                self.close_popup()

    def close_popup(self, refocus=False):
        if self._closing_timer:
            self.after_cancel(self._closing_timer)
            self._closing_timer = None
        if not self.popup:
            return
        root = self.winfo_toplevel()
        for sequence, binding in (("<Button-1>", self._outside_binding), ("<Configure>", self._move_binding)):
            if binding:
                root.unbind(sequence, binding)
        self._outside_binding = self._move_binding = None
        popup, self.popup = self.popup, None
        popup.destroy()
        if getattr(root, "_active_dropdown", None) is self:
            root._active_dropdown = None
        if refocus:
            self._entry.focus_set()

    def destroy(self):
        self.close_popup()
        super().destroy()


class RouteMultiSelect(ctk.CTkFrame):
    """Editable route field with a bounded searchable checkbox tree."""
    def __init__(self, master, variable=None, command=None, **kwargs):
        height = kwargs.pop("height", 36)
        state = kwargs.pop("state", "normal")
        fg_color = kwargs.pop("fg_color", ("#FFF0F7", "#211B28"))
        border_color = kwargs.pop("border_color", ("#F0DCE8", "#514056"))
        text_color = kwargs.pop("text_color", ("#34263F", "#FFF1F8"))
        font = kwargs.pop("font", None)
        super().__init__(master, height=height, fg_color=fg_color, corner_radius=8,
                         border_width=1, border_color=border_color, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)
        self.variable = variable or tk.StringVar(master=master)
        self.command = command
        self.catalog = {"hierarchical": False, "groups": [], "items": [], "keys": []}
        self._selected = set()
        self._structured = False
        self._guard = False
        self._state = state
        self.popup = None
        self._outside_binding = None
        self.entry = ctk.CTkEntry(self, textvariable=self.variable, height=height - 2,
                                  fg_color="transparent", border_width=0,
                                  text_color=text_color, font=font)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(5, 0), pady=1)
        self.button = ctk.CTkButton(self, text="Chọn…", width=76, height=height - 4,
                                    fg_color="transparent", hover_color=("#FCE7F3", "#48283E"),
                                    text_color=("#B91C63", "#FFADD6"), command=self.open_popup)
        self.button.grid(row=0, column=1, padx=(0, 2), pady=2)
        self._trace = self.variable.trace_add("write", self._manual_changed)
        self.configure(state=state)

    def _manual_changed(self, *_):
        if self._guard:
            return
        self._structured = False
        self._selected.clear()
        if self.command:
            self.command()

    def cget(self, attribute_name):
        if attribute_name == "state":
            return self._state
        if attribute_name == "values":
            return [item["label"] for item in self.catalog["items"]]
        return super().cget(attribute_name)

    def configure(self, require_redraw=False, **kwargs):
        catalog = kwargs.pop("catalog", None)
        values = kwargs.pop("values", None)
        if catalog is not None:
            self.set_catalog(catalog)
        elif values is not None and not values:
            self.set_catalog({"hierarchical": False, "groups": [], "items": [], "keys": []})
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            child_state = "disabled" if self._state == "disabled" else "normal"
            if hasattr(self, "entry"):
                self.entry.configure(state=child_state)
                self.button.configure(state=child_state)
            if self._state == "disabled":
                self.close_popup()
        return super().configure(require_redraw=require_redraw, **kwargs)

    config = configure

    def set_catalog(self, catalog, select_all=False):
        self.close_popup()
        self.catalog = catalog
        known = {tuple(key) for key in catalog.get("keys", [])}
        self._selected.intersection_update(known)
        if select_all:
            self._selected = known
            self._structured = True
        self._render_value()

    def set(self, value):
        self._selected.clear()
        self._structured = False
        self._set_variable(str(value or ""))
        if self.command:
            self.command()

    def get(self):
        return self.variable.get()

    def get_route_keys(self):
        if not self._structured:
            return None
        order = [tuple(key) for key in self.catalog.get("keys", [])]
        return [key for key in order if key in self._selected]

    def get_manual_text(self):
        return "" if self._structured else self.variable.get().strip()

    def select_all(self):
        self._selected = {tuple(key) for key in self.catalog.get("keys", [])}
        self._structured = True
        self._render_value(notify=True)

    def clear_selection(self):
        self._selected.clear()
        self._structured = True
        self._render_value(notify=True)

    def remove_key(self, key):
        self._selected.discard(tuple(key))
        self._structured = True
        self._render_value(notify=True)

    def _set_variable(self, value):
        self._guard = True
        try:
            self.variable.set(value)
        finally:
            self._guard = False

    def _render_value(self, notify=False):
        if self._structured:
            labels = [item["label"] for item in self.catalog.get("items", [])
                      if tuple(item["key"]) in self._selected]
            text = (labels[0] if len(labels) == 1 else
                    f"{len(labels)} tuyến đã chọn" if labels else "Chưa chọn tuyến")
            self._set_variable(text)
        if notify and self.command:
            self.command()

    def selected_items(self):
        return [item for item in self.catalog.get("items", [])
                if tuple(item["key"]) in self._selected]

    def open_popup(self):
        if self._state == "disabled" or self.popup:
            return
        root = self.winfo_toplevel()
        previous = getattr(root, "_active_dropdown", None)
        if previous and previous is not self:
            previous.close_popup()
        root._active_dropdown = self
        dark = ctk.get_appearance_mode() == "Dark"
        bg, ink, muted, border, soft, page = (
            ("#2C2534", "#FFF1F8", "#C1ADC9", "#514056", "#48283E", "#211B28")
            if dark else ("#FFFFFF", "#34263F", "#7B6B85", "#F0DCE8", "#FCE7F3", "#FFF8FB")
        )
        popup = self.popup = tk.Toplevel(root)
        popup.withdraw()
        popup.transient(root)
        popup.title("HAPGIS · Chọn tuyến xử lý")
        popup.configure(bg=page)
        popup.minsize(620, 430)
        popup.protocol("WM_DELETE_WINDOW", self.close_popup)
        panel = tk.Frame(popup, bg=bg)
        panel.pack(fill="both", expand=True, padx=14, pady=14)

        header = tk.Frame(panel, bg=bg)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="Chọn tuyến xử lý", bg=bg, fg=ink,
                 font=("Segoe UI", 17, "bold"), anchor="w").pack(fill="x")
        schema_text = ("Chọn đường cha để lấy cả đường chính và các hẻm; có thể bỏ từng hẻm."
                       if self.catalog.get("hierarchical") else
                       "Dữ liệu tenDuong cũ · mỗi dòng là một tuyến độc lập, không lặp dòng cha.")
        tk.Label(header, text=schema_text, bg=bg, fg=muted,
                 font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(3, 0))

        search_var = tk.StringVar(popup)
        search_row = tk.Frame(panel, bg=bg)
        search_row.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(search_row, text="⌕", bg=bg, fg="#DB2777",
                 font=("Segoe UI", 16)).pack(side="left", padx=(0, 7))
        search = tk.Entry(search_row, textvariable=search_var, relief="flat", bg=page, fg=ink,
                          insertbackground=ink, highlightthickness=1, highlightbackground=border,
                          highlightcolor="#DB2777", font=("Segoe UI", 11))
        search.pack(side="left", fill="x", expand=True, ipady=7)
        search.insert(0, "")

        tools = tk.Frame(panel, bg=bg)
        tools.pack(fill="x", padx=18, pady=(0, 8))
        result_label = tk.Label(tools, text="", bg=bg, fg=muted,
                                font=("Segoe UI", 9), anchor="e")
        result_label.pack(side="right")

        list_shell = tk.Frame(panel, bg=border)
        list_shell.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        canvas = tk.Canvas(list_shell, bg=page, highlightthickness=0, height=310)
        scroll = ttk.Scrollbar(panel, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=page)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        scroll.configure(command=canvas.yview)
        scroll.pack(in_=list_shell, side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self._route_canvas = canvas
        self._route_search_var = search_var

        pending = set(self._selected)
        leaf_vars, parent_vars = {}, {}
        group_views, flat_views = [], []

        def is_alley(item):
            if self.catalog.get("hierarchical"):
                return bool(item["alley"])
            return bool(re.match(r"^(?:hẻm|hem)(?:\s+|$)", item["parent"], re.IGNORECASE))

        def update_summary():
            visible = sum(1 for item in self.catalog.get("items", [])
                          if not search_key(search_var.get()) or search_key(search_var.get()) in search_key(item["label"]))
            result_label.configure(text=f"{visible} kết quả  ·  {len(pending)} tuyến đã chọn")

        def update_parents():
            for group in self.catalog.get("groups", []):
                keys = [tuple(item["key"]) for item in group["items"]]
                count = sum(key in pending for key in keys)
                if group["key"] in parent_vars:
                    parent_vars[group["key"]].set(1 if count == len(keys) and keys else -1 if count else 0)
            update_summary()

        def toggle_leaf(key, variable):
            (pending.add if variable.get() else pending.discard)(key)
            update_parents()

        def toggle_parent(group):
            keys = [tuple(item["key"]) for item in group["items"]]
            enabled = parent_vars[group["key"]].get() != 1
            for key in keys:
                (pending.add if enabled else pending.discard)(key)
                leaf_vars[key].set(1 if enabled else 0)
            update_parents()

        if self.catalog.get("hierarchical"):
            for group in self.catalog.get("groups", []):
                section = tk.Frame(body, bg=bg, highlightthickness=1, highlightbackground=border)
                section.pack(fill="x", padx=8, pady=(7, 0))
                pv = parent_vars[group["key"]] = tk.IntVar(popup)
                parent = tk.Checkbutton(
                    section, text=group["parent"], variable=pv, tristatevalue=-1,
                    command=lambda g=group: toggle_parent(g), bg=soft, fg=ink,
                    activebackground=soft, selectcolor=soft, anchor="w",
                    font=("Segoe UI", 11, "bold"), padx=10, pady=8,
                )
                parent.pack(fill="x")
                children = []
                for item in group["items"]:
                    key = tuple(item["key"])
                    lv = leaf_vars[key] = tk.IntVar(popup, value=1 if key in pending else 0)
                    title = "Đường chính" if item["is_main"] else item["alley"]
                    child = tk.Checkbutton(
                        section, text=title, variable=lv,
                        command=lambda k=key, v=lv: toggle_leaf(k, v),
                        bg=bg, fg=ink, activebackground=soft, selectcolor=bg,
                        anchor="w", font=("Segoe UI", 10), padx=28, pady=5,
                    )
                    child.pack(fill="x")
                    children.append((child, item))
                group_views.append((section, parent, group, children))
        else:
            for index, item in enumerate(self.catalog.get("items", [])):
                row = tk.Frame(body, bg=bg if index % 2 == 0 else page)
                row.pack(fill="x", padx=8, pady=(5 if index == 0 else 1, 0))
                key = tuple(item["key"])
                lv = leaf_vars[key] = tk.IntVar(popup, value=1 if key in pending else 0)
                checkbox = tk.Checkbutton(
                    row, text=item["label"], variable=lv,
                    command=lambda k=key, v=lv: toggle_leaf(k, v),
                    bg=row["bg"], fg=ink, activebackground=soft, selectcolor=row["bg"],
                    anchor="w", font=("Segoe UI", 10), padx=10, pady=7,
                )
                checkbox.pack(side="left", fill="x", expand=True)
                badge_text = "HẺM" if is_alley(item) else "ĐƯỜNG"
                tk.Label(row, text=badge_text, bg=soft, fg="#B91C63" if not dark else "#FFADD6",
                         font=("Segoe UI", 8, "bold"), padx=8, pady=3).pack(side="right", padx=8)
                flat_views.append((row, item))
        update_parents()

        def filter_rows(*_):
            query = search_key(search_var.get())
            if self.catalog.get("hierarchical"):
                for section, parent, group, children in group_views:
                    section.pack_forget()
                    parent_match = query in search_key(group["parent"])
                    any_child = False
                    for child, item in children:
                        child.pack_forget()
                        if parent_match or query in search_key(item["label"]):
                            child.pack(fill="x")
                            any_child = True
                    if parent_match or any_child:
                        section.pack(fill="x", padx=8, pady=(7, 0))
            else:
                for row, item in flat_views:
                    row.pack_forget()
                    if query in search_key(item["label"]):
                        row.pack(fill="x", padx=8, pady=1)
            body.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(0)
            update_summary()

        def select_results():
            query = search_key(search_var.get())
            for group in self.catalog.get("groups", []):
                for item in group["items"]:
                    key = tuple(item["key"])
                    title = group["parent"] + " " + ("Đường chính" if item["is_main"] else item["alley"])
                    if query in search_key(title):
                        pending.add(key)
                        leaf_vars[key].set(1)
            update_parents()

        search_var.trace_add("write", filter_rows)
        def style_button(parent, text, command, primary=False):
            return tk.Button(
                parent, text=text, command=command, relief="flat",
                bg="#DB2777" if primary else soft, fg="white" if primary else ink,
                activebackground="#BE185D" if primary else border,
                activeforeground="white" if primary else ink,
                font=("Segoe UI", 9, "bold" if primary else "normal"), padx=11, pady=5,
            )

        style_button(tools, "Chọn kết quả tìm kiếm", select_results).pack(side="left", padx=(0, 5))
        def clear():
            pending.clear()
            for variable in leaf_vars.values(): variable.set(0)
            update_parents()
        def select_kind(want_alley):
            pending.clear()
            for item in self.catalog.get("items", []):
                key = tuple(item["key"])
                if is_alley(item) == want_alley:
                    pending.add(key)
                leaf_vars[key].set(1 if key in pending else 0)
            update_parents()
        style_button(tools, "Chỉ đường", lambda: select_kind(False)).pack(side="left", padx=5)
        style_button(tools, "Chỉ hẻm", lambda: select_kind(True)).pack(side="left", padx=5)
        style_button(tools, "Bỏ chọn", clear).pack(side="left", padx=5)

        actions = tk.Frame(panel, bg=bg)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        selected_label = tk.Label(actions, text="Các thay đổi chỉ có hiệu lực khi bấm Áp dụng",
                                  bg=bg, fg=muted, font=("Segoe UI", 9), anchor="w")
        selected_label.pack(side="left")
        def apply():
            self._selected = pending
            self._structured = True
            self._render_value(notify=True)
            self.close_popup()
        style_button(actions, "Áp dụng lựa chọn", apply, primary=True).pack(side="right", padx=(8, 0))
        style_button(actions, "Hủy", self.close_popup).pack(side="right")

        def wheel(event):
            delta = getattr(event, "delta", 0)
            direction = -1 if delta > 0 else 1
            if getattr(event, "num", None) == 4:
                direction = -1
            elif getattr(event, "num", None) == 5:
                direction = 1
            canvas.yview_scroll(direction * 3, "units")
            return "break"
        def bind_wheel_tree(widget):
            widget.bind("<MouseWheel>", wheel, add="+")
            widget.bind("<Button-4>", wheel, add="+")
            widget.bind("<Button-5>", wheel, add="+")
            for child in widget.winfo_children():
                bind_wheel_tree(child)
        bind_wheel_tree(popup)
        popup.bind("<Escape>", lambda _: self.close_popup())
        popup.update_idletasks()
        width = min(780, self.winfo_screenwidth() - 60)
        height = min(590, self.winfo_screenheight() - 80)
        x = max(20, root.winfo_rootx() + (root.winfo_width() - width) // 2)
        y = max(20, root.winfo_rooty() + (root.winfo_height() - height) // 2)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        popup.update()
        popup.grab_set()
        search.focus_set()
        filter_rows()
        popup.update_idletasks()

    def close_popup(self):
        if not self.popup:
            return
        root = self.winfo_toplevel()
        popup, self.popup = self.popup, None
        try:
            popup.grab_release()
        except tk.TclError:
            pass
        popup.destroy()
        if getattr(root, "_active_dropdown", None) is self:
            root._active_dropdown = None

    def destroy(self):
        self.close_popup()
        try:
            self.variable.trace_remove("write", self._trace)
        except Exception:
            pass
        super().destroy()
