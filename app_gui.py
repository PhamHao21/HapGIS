# -*- coding: utf-8 -*-
"""Desktop workflow: sources → tenDuong values → house numbering."""
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

import customtkinter as ctk
from app_service import (
    chay_danh_so, co_nhieu_layer, la_gdb, liet_ke_layer,
    liet_ke_truong, kiem_tra_nguon, lap_danh_muc_tuyen, mo_ta_kieu_lop,
)

from ui_widgets import RouteMultiSelect, SearchableCombo, StableScrollableFrame
from data_rules import RULES, format_report
from core_housenumber import FIELD_ROUTE
from route_catalog import FIELD_ALLEY
from alley_numbering import route_preview

APP_NAME = "HAPGIS"
APP_VERSION = "1.1"
APP_FULL_NAME = f"{APP_NAME} v{APP_VERSION}"
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")
BG = ("#FFF5F9", "#211B28")
CARD = ("#FFFFFF", "#2C2534")
INK = ("#34263F", "#FFF1F8")
MUTED = ("#7B6B85", "#C1ADC9")
ACCENT = ("#DB2777", "#DB2777")
HOVER = ("#BE185D", "#BE185D")
BORDER = ("#F0DCE8", "#514056")
SOFT = ("#FCE7F3", "#48283E")
INPUT = ("#FFF0F7", "#211B28")
PINK_INK = ("#B91C63", "#FFADD6")
SUCCESS = ("#13795B", "#6EE7B7")
ERROR = ("#B42342", "#FDA4AF")


def resource_path(relative_path):
    return os.path.join(
        getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
        relative_path,
    )


class AppDanhSoNha(ctk.CTk):
    def __init__(self):
        ctk.set_widget_scaling(1)
        ctk.set_window_scaling(1)
        super().__init__()
        self.title(f"{APP_FULL_NAME} · Đánh số nhà tự động")
        # Keep the workflow inside small screens even with Windows DPI scaling.
        dpi = self._get_window_scaling()
        scale = min(1.0, (self.winfo_screenwidth() - 80) / (1000 * dpi),
                    (self.winfo_screenheight() - 100) / (640 * dpi))
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        effective = dpi * scale
        width = min(1080, int((self.winfo_screenwidth() - 80) / effective))
        height = min(780, int((self.winfo_screenheight() - 100) / effective))
        self.geometry(f"{width}x{height}")
        self.minsize(900, 560)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(resource_path("assets/hapgis.ico"))
        except Exception:
            pass
        self.hang_doi = queue.Queue()
        self.dang_chay = False
        self.output_hien_tai = ""
        self.sources = {}
        self.value_generation = 0
        self.value_loading = False
        self.controls = []
        self.check_generation = 0
        self.check_loading = False
        self.check_report = None
        self.log_lines = []
        self.rules_window = None
        self.report_window = None
        self.output_var = tk.StringVar()
        self.value_var = tk.StringVar()
        self.tao_giao_dien()
        self.output_var.trace_add("write", lambda *_: self.cap_nhat_san_sang())
        self.queue_after = self.after(100, self.doc_hang_doi)

    def label(self, parent, text, size=13, bold=False, **kwargs):
        return ctk.CTkLabel(
            parent, text=text, text_color=INK, anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=size,
                            weight="bold" if bold else "normal"), **kwargs,
        )

    def card(self, parent, row, number, title, description):
        frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16,
                             border_width=1, border_color=BORDER)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 12), padx=(0, 4))
        frame.grid_columnconfigure(0, weight=1)
        heading = ctk.CTkFrame(frame, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        tag = self.label(heading, number, 12, True, width=30, height=28,
                         fg_color=SOFT, corner_radius=8)
        tag.configure(text_color=PINK_INK, anchor="center")
        tag.pack(side="left", padx=(0, 8))
        self.label(heading, title, 15, True).pack(side="left")
        hint = self.label(frame, description, 11, height=18, wraplength=460, justify="left")
        hint.configure(text_color=MUTED)
        hint.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 9))
        return frame

    def button(self, parent, text, command, secondary=False, **kwargs):
        widget = ctk.CTkButton(
            parent, text=text, command=command, height=32, corner_radius=7,
            fg_color=SOFT if secondary else ACCENT,
            text_color=PINK_INK if secondary else "#FFFFFF",
            hover_color=BORDER if secondary else HOVER,
            border_width=1 if secondary else 0, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=12), **kwargs,
        )
        self.controls.append(widget)
        return widget

    def combo(self, parent, **kwargs):
        return SearchableCombo(
            parent, fg_color=INPUT, border_color=BORDER, text_color=INK,
            button_color=SOFT, button_hover_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=12), **kwargs,
        )

    def tao_giao_dien(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.shell = ctk.CTkFrame(self, fg_color="transparent", width=1048)
        self.shell.grid(row=0, column=0, sticky="ns", padx=16, pady=(14, 10))
        self.shell.grid_propagate(False)
        self.shell.grid_columnconfigure(0, weight=1)
        self.shell.grid_rowconfigure(2, weight=1)
        self.bind("<Configure>", self.gioi_han_bo_cuc, add="+")

        header = ctk.CTkFrame(self.shell, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(2, 10))
        header.grid_columnconfigure(1, weight=1)
        emblem = ctk.CTkFrame(header, width=44, height=44, corner_radius=13, fg_color=ACCENT)
        emblem.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        emblem.grid_propagate(False)
        mark = self.label(emblem, "H", 26, True)
        mark.configure(text_color="#FFFFFF", anchor="center")
        mark.place(relx=.5, rely=.5, anchor="center")
        self.label(header, "HAPGIS", 23, True).grid(row=0, column=1, sticky="w")
        sub = self.label(header, "Không gian địa chỉ · Address Studio", 11)
        sub.configure(text_color=MUTED)
        sub.grid(row=1, column=1, sticky="w")
        ctk.CTkButton(header, text="Quy tắc dữ liệu", width=118, height=34,
                      corner_radius=9, fg_color=SOFT, text_color=PINK_INK,
                      hover_color=BORDER, command=self.hien_quy_tac).grid(row=0, column=2, rowspan=2, padx=10)
        self.theme = ctk.CTkOptionMenu(
            header, values=["Sáng", "Tối", "Hệ thống"], width=94, height=34,
            fg_color=CARD, button_color=CARD, button_hover_color=SOFT,
            text_color=INK, dropdown_fg_color=CARD, dropdown_text_color=INK,
            dropdown_hover_color=SOFT, command=self.doi_theme,
        )
        self.theme.set("Sáng")
        self.theme.grid(row=0, column=3, rowspan=2)

        toolbar = ctk.CTkFrame(self.shell, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)
        self.label(toolbar, "Đánh số nhà theo tuyến", 26, True).grid(row=0, column=0, sticky="w")
        badge = self.label(toolbar, "  tenDuong · tenHem tùy chọn  ", 11, True,
                           fg_color=SOFT, corner_radius=10, height=30)
        badge.configure(text_color=PINK_INK)
        badge.grid(row=0, column=1, rowspan=2, sticky="e")

        self.form = StableScrollableFrame(self.shell, fg_color="transparent", corner_radius=0,
                                          scrollbar_button_color=BORDER,
                                          scrollbar_button_hover_color=PINK_INK)
        self.form.grid(row=2, column=0, sticky="nsew")
        self.form.grid_columnconfigure(0, weight=1)
        inputs = self.card(self.form, 0, "01", "Chọn dữ liệu bản đồ",
                           "Kết nối lớp thửa và lớp đường · SHP, GPKG, GeoJSON hoặc GDB")
        sources = ctk.CTkFrame(inputs, fg_color="transparent")
        sources.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        sources.grid_columnconfigure((0, 1), weight=1, uniform="source")
        for col, (kind, title) in enumerate((("thua", "Lớp thửa đất"), ("duong", "Lớp đường"))):
            self.tao_nguon(sources, col, kind, title)

        lower = ctk.CTkFrame(self.form, fg_color="transparent")
        lower.grid(row=1, column=0, sticky="ew")
        lower.grid_columnconfigure((0, 1), weight=1, uniform="lower")
        route_slot = ctk.CTkFrame(lower, fg_color="transparent")
        route_slot.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        route_slot.grid_columnconfigure(0, weight=1)
        route_slot.grid_rowconfigure(0, weight=1)
        output_slot = ctk.CTkFrame(lower, fg_color="transparent")
        output_slot.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        output_slot.grid_columnconfigure(0, weight=1)
        output_slot.grid_rowconfigure(0, weight=1)

        matching = self.card(route_slot, 0, "02", "Chọn tuyến", "Chọn nhiều đường/hẻm theo cây hoặc nhập trực tiếp.")
        matching.grid_configure(sticky="nsew")
        self.field_hint = self.label(matching, "Chọn đủ hai lớp để tải danh sách tuyến.", 11,
                                     height=18, wraplength=350, justify="left")
        self.field_hint.configure(text_color=MUTED)
        self.field_hint.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 6))
        values = ctk.CTkFrame(matching, fg_color="transparent")
        values.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        values.grid_columnconfigure(0, weight=1)
        self.entry_tuyen = RouteMultiSelect(
            values, variable=self.value_var, command=self.doi_gia_tri,
            height=36, state="disabled", fg_color=INPUT,
            border_color=BORDER, text_color=INK,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.entry_tuyen.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.btn_all = self.button(values, "Tất cả", self.entry_tuyen.select_all, secondary=True, width=64)
        self.btn_all.grid(row=0, column=1)
        self.btn_all.configure(state="disabled")
        hint = self.label(matching, "Nhập tay: Đường cha › Hẻm 1 · Nhiều tuyến cách nhau bằng dấu ;", 11, height=18, wraplength=350)
        hint.configure(text_color=MUTED)
        hint.grid(row=6, column=0, sticky="w", padx=16, pady=(0, 12))
        self.route_hint = self.label(matching, route_preview(""), 11, height=18,
                                      wraplength=350, justify="left")
        self.route_hint.configure(text_color=PINK_INK)
        self.route_hint.grid(row=5, column=0, sticky="w", padx=16, pady=(0, 4))
        self.route_chips = ctk.CTkFrame(matching, fg_color="transparent")
        self.route_chips.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 10))

        output = self.card(output_slot, 0, "03", "Lưu kết quả", "Chọn vị trí và tên tệp đầu ra.")
        output.grid_configure(sticky="nsew")
        hint = self.label(output, "Khuyên dùng GeoPackage (.gpkg)", 11, height=18)
        hint.configure(text_color=MUTED)
        hint.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 6))
        outrow = ctk.CTkFrame(output, fg_color="transparent")
        outrow.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        outrow.grid_columnconfigure(0, weight=1)
        self.entry_output = ctk.CTkEntry(outrow, textvariable=self.output_var, height=36,
                                        fg_color=INPUT, border_color=BORDER, text_color=INK, border_width=1)
        self.entry_output.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.controls.append(self.entry_output)
        self.button(outrow, "Chọn nơi lưu", self.chon_output, secondary=True, width=94).grid(row=0, column=1)
        hint = self.label(output, "GeoPackage giữ đầy đủ tên trường dữ liệu.", 11, height=18, wraplength=350)
        hint.configure(text_color=MUTED)
        hint.grid(row=5, column=0, sticky="w", padx=16, pady=(0, 12))

        self.log_panel = ctk.CTkFrame(self.shell, fg_color=CARD, corner_radius=12,
                                      border_width=1, border_color=BORDER)
        self.log_panel.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.log_panel.grid_columnconfigure(0, weight=1)
        logbar = ctk.CTkFrame(self.log_panel, fg_color="transparent")
        logbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 2))
        self.summary = self.label(logbar, "Chọn hai lớp có tenDuong.", 11, wraplength=560, justify="left")
        self.summary.configure(text_color=MUTED)
        self.summary.pack(side="left")
        ctk.CTkButton(logbar, text="Lưu log", width=70, height=28, fg_color=SOFT,
                      text_color=PINK_INK, hover_color=BORDER,
                      command=self.luu_nhat_ky).pack(side="right")
        self.txt_log = ctk.CTkTextbox(self.log_panel, height=82, fg_color=BG,
                                     text_color=INK, corner_radius=8,
                                     font=ctk.CTkFont(family="Segoe UI", size=11), wrap="word", state="disabled")
        self.txt_log.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 10))
        self.log_panel.grid_remove()

        action = ctk.CTkFrame(self.shell, fg_color=CARD, corner_radius=14,
                              border_width=1, border_color=BORDER)
        action.grid(row=4, column=0, sticky="ew")
        action.grid_columnconfigure(0, weight=1)
        self.status_label = self.label(action, "Chờ dữ liệu", 16, True)
        self.status_label.grid(row=0, column=0, sticky="w", padx=18, pady=(10, 0))
        self.check_label = self.label(action, "○  Chưa kiểm tra dữ liệu", 11, wraplength=310, justify="left")
        self.check_label.configure(text_color=MUTED)
        self.check_label.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 8))
        self.btn_check = ctk.CTkButton(action, text="Kiểm tra dữ liệu", width=145, height=40,
                                       fg_color=SOFT, text_color=PINK_INK, hover_color=BORDER,
                                       corner_radius=10, command=self.kiem_tra, state="disabled")
        self.btn_check.grid(row=0, column=1, rowspan=2, padx=(10, 8))
        self.btn_run = ctk.CTkButton(action, text="Bắt đầu đánh số  →", width=204, height=42,
                                     fg_color=ACCENT, text_color="#FFFFFF",
                                     text_color_disabled="#FBCFE8", hover_color=HOVER,
                                     font=ctk.CTkFont(size=14, weight="bold"), corner_radius=10,
                                     command=self.bat_dau, state="disabled")
        self.btn_run.grid(row=0, column=2, rowspan=2, padx=(0, 16))
        self.progress = ctk.CTkProgressBar(action, mode="determinate", progress_color=ACCENT,
                                           fg_color=SOFT, height=3)
        self.progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 6))
        self.progress.set(0)

        footer = ctk.CTkFrame(self.shell, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=4, pady=(6, 0))
        footer.grid_columnconfigure(0, weight=1)
        version = self.label(footer, f"{APP_FULL_NAME}  ·  House Address Processing GIS", 10)
        version.configure(text_color=MUTED)
        version.grid(row=0, column=0, sticky="w")
        self.btn_log = ctk.CTkButton(footer, text="Nhật ký  ▴", width=94, height=28,
                                     fg_color="transparent", text_color=PINK_INK,
                                     hover_color=SOFT, command=self.bat_tat_nhat_ky)
        self.btn_log.grid(row=0, column=1, padx=8)
        self.btn_open = ctk.CTkButton(footer, text="Mở thư mục kết quả  ↗", width=158, state="disabled", height=28,
                                      fg_color=SOFT, hover_color=BORDER, text_color=PINK_INK,
                                      command=self.mo_thu_muc_ket_qua)
        self.btn_open.grid(row=0, column=2)
        self.ghi_log("Sẵn sàng. Chọn nguồn dữ liệu để bắt đầu.")

    def bat_tat_nhat_ky(self):
        if self.log_panel.winfo_manager():
            self.log_panel.grid_remove()
            self.btn_log.configure(text="Nhật ký  ▴")
        else:
            self.log_panel.grid()
            self.btn_log.configure(text="Thu gọn  ▾")

    def gioi_han_bo_cuc(self, event):
        if event.widget is self:
            logical_width = event.width / self._get_widget_scaling()
            self.shell.configure(width=min(1120, max(850, logical_width - 32)))

    def doi_theme(self, value):
        active = getattr(self, "_active_dropdown", None)
        if active:
            active.close_popup()
        ctk.set_appearance_mode({"Hệ thống": "System", "Sáng": "Light", "Tối": "Dark"}[value])

    def tao_nguon(self, parent, col, kind, title):
        frame = ctk.CTkFrame(parent, fg_color=BG, corner_radius=12)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
        frame.grid_columnconfigure(0, weight=1)
        titlebar = ctk.CTkFrame(frame, fg_color="transparent")
        titlebar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        self.label(titlebar, title, 13, True).pack(side="left")
        if kind == "duong":
            self.button(titlebar, "Dùng nguồn thửa", self.dung_nguon_thua,
                        secondary=True, width=112).pack(side="right")
        else:
            self.button(titlebar, "Nạp lại", self.nap_lai,
                        secondary=True, width=65).pack(side="right")
        pathrow = ctk.CTkFrame(frame, fg_color="transparent")
        pathrow.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        pathrow.grid_columnconfigure(0, weight=1)
        var = tk.StringVar()
        entry = ctk.CTkEntry(pathrow, textvariable=var, height=32, border_width=1,
                             fg_color=CARD, border_color=BORDER, text_color=INK)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.controls.append(entry)
        self.button(pathrow, "File…", lambda: self.chon_nguon(kind, False), width=54).grid(row=0, column=1, padx=(0, 5))
        self.button(pathrow, "GDB…", lambda: self.chon_nguon(kind, True), secondary=True, width=54).grid(row=0, column=2)
        combo = self.combo(frame, values=[], height=32, state="disabled", command=lambda _: self.tai_truong(kind))
        combo.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 3))
        hint = self.label(frame, "Layer · Chưa chọn nguồn", 10, height=18, wraplength=350, justify="left")
        hint.configure(text_color=MUTED)
        hint.grid(row=4, column=0, sticky="w", padx=10, pady=(0, 8))
        self.sources[kind] = dict(path=var, entry=entry, layer=combo, hint=hint,
                                  fields=[], layers=[], generation=0, pending=None, ready=False)
        var.trace_add("write", lambda *_: self.doi_nguon(kind))

    def dung_nguon_thua(self):
        path = self.sources["thua"]["path"].get().strip()
        if path:
            self.sources["duong"]["path"].set(path)

    def nap_lai(self):
        for kind in self.sources:
            if self.sources[kind]["path"].get().strip():
                self.doi_nguon(kind)

    def chon_nguon(self, kind, gdb):
        if gdb:
            path = filedialog.askdirectory(title="Chọn File Geodatabase (.gdb)")
            if path and not la_gdb(path):
                messagebox.showerror("Sai dữ liệu", "Hãy chọn thư mục có phần mở rộng .gdb.")
                return
        else:
            path = filedialog.askopenfilename(title="Chọn dữ liệu GIS", filetypes=[
                ("Dữ liệu GIS", "*.shp *.gpkg *.geojson"), ("Tất cả", "*.*")])
        if path:
            self.sources[kind]["path"].set(path)

    def cua_so_noi_dung(self, title, subtitle):
        window = ctk.CTkToplevel(self)
        window.withdraw()
        window.title(f"HAPGIS · {title}")
        window.configure(fg_color=BG)
        window.transient(self)
        scale = window._get_window_scaling()
        width = min(650, int((self.winfo_screenwidth() - 60) / scale))
        height = min(620, int((self.winfo_screenheight() - 100) / scale))
        window.geometry(f"{width}x{height}")
        window.minsize(min(480, width), min(380, height))
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)
        self.label(window, title, 23, True).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 2))
        note = self.label(window, subtitle, 12, wraplength=540, justify="left")
        note.configure(text_color=MUTED)
        note.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))
        content = StableScrollableFrame(window, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))
        content.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(window, text="Đã hiểu", width=110, height=34, fg_color=ACCENT,
                      hover_color=HOVER, command=window.destroy).grid(row=3, column=0, sticky="e", padx=24, pady=(0, 18))
        window.deiconify()
        window.lift()
        return window, content

    def hien_quy_tac(self):
        if self.rules_window and self.rules_window.winfo_exists():
            self.rules_window.lift()
            return
        self.rules_window, content = self.cua_so_noi_dung(
            "Quy tắc dữ liệu", "Các điều kiện đầu vào của HAPGIS · Kiểm tra trước khi đánh số")
        for row, (number, title, description) in enumerate(RULES):
            frame = self.card(content, row, number, title, description)
            # The rules need readable full paragraphs, not shortened captions.
            for child in frame.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(font=ctk.CTkFont(family="Segoe UI", size=13), wraplength=510)
                    frame.bind("<Configure>", lambda e, label=child: label.configure(
                        wraplength=max(260, e.width / self._get_widget_scaling() - 36)), add="+")

    def doi_gia_tri(self):
        self.check_generation += 1
        self.check_loading = False
        self.check_report = None
        if hasattr(self, "check_label"):
            self.check_label.configure(text="○  Chưa kiểm tra dữ liệu", text_color=MUTED)
        if hasattr(self, "route_hint"):
            selected = self.entry_tuyen.selected_items()
            value = self.entry_tuyen.get_manual_text()
            if len(selected) == 1:
                text = route_preview(selected[0]["alley"] if selected[0]["alley"] else selected[0]["parent"])
            elif selected:
                text = f"{len(selected)} tuyến · Nhận diện chi tiết trong Kiểm tra dữ liệu."
            else:
                exact = any(value.casefold() == str(item).casefold() for item in self.entry_tuyen.cget("values"))
                text = ("Nhiều tuyến · Xem nhận diện hẻm trong Kiểm tra dữ liệu."
                        if ";" in value and not exact else route_preview(value))
            self.route_hint.configure(text=text)
            self.hien_the_tuyen()
        self.cap_nhat_san_sang()

    def hien_the_tuyen(self):
        if not hasattr(self, "route_chips"):
            return
        for child in self.route_chips.winfo_children():
            child.destroy()
        items = self.entry_tuyen.selected_items()
        visible = items[:1] if len(items) > 3 else items
        for col, item in enumerate(visible):
            text = item["alley"] or item["parent"]
            chip = ctk.CTkButton(
                self.route_chips, text=f"{text}  ×", height=25, width=20,
                fg_color=SOFT, hover_color=BORDER, text_color=PINK_INK,
                corner_radius=12, command=lambda key=item["key"]: self.entry_tuyen.remove_key(key),
                font=ctk.CTkFont(family="Segoe UI", size=10),
            )
            chip.grid(row=0, column=col, padx=(0, 5), pady=2)
        if len(items) > 3:
            more = ctk.CTkButton(
                self.route_chips, text=f"+{len(items) - 1} tuyến khác · Xem/sửa", height=25, width=20,
                fg_color="transparent", hover_color=SOFT, text_color=PINK_INK,
                command=self.entry_tuyen.open_popup,
                font=ctk.CTkFont(family="Segoe UI", size=10, underline=True),
            )
            more.grid(row=0, column=1, padx=2)

    def cau_hinh_kiem_tra(self):
        house, road = self.sources["thua"], self.sources["duong"]
        return dict(house_path=house["path"].get().strip(), house_layer=house["layer"].get(),
                    road_path=road["path"].get().strip(), road_layer=road["layer"].get(),
                    tuyen=self.entry_tuyen.get_manual_text(),
                    route_keys=self.entry_tuyen.get_route_keys())

    def kiem_tra(self):
        if self.dang_chay or self.check_loading or not self.truong_hop_le():
            return
        self.check_generation += 1
        self.check_loading = True
        params = self.cau_hinh_kiem_tra()
        self.check_label.configure(text="Đang kiểm tra CRS và dữ liệu…", text_color=PINK_INK)
        self.chay_nen("check", self.check_generation, lambda: kiem_tra_nguon(**params))
        self.cap_nhat_san_sang()

    def hien_bao_cao(self, report):
        if self.report_window and self.report_window.winfo_exists():
            self.report_window.destroy()
        self.report_window, content = self.cua_so_noi_dung(
            "Kiểm tra dữ liệu", "Kết quả phạm vi đường–hẻm và tuyến cha cần tham chiếu")
        routes = report.get("alley_routes", [])
        if routes:
            self.label(content, "Nhận diện hẻm và chiều đánh số", 14, True).grid(
                row=0, column=0, sticky="w", padx=6, pady=(0, 6))
            self.route_table = StableScrollableFrame(content, height=165, fg_color=CARD,
                                                       corner_radius=10)
            self.route_table.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 10))
            for col, weight in enumerate((2, 1, 2, 3)):
                self.route_table.grid_columnconfigure(col, weight=weight, uniform="route_table")
            entries = [["Tuyến", "Số hẻm", "Đường gốc", "Chiều / kiểm tra"]]
            entries += [[r["route"], r["prefix"], r["parent"], r["status"]] for r in routes]
            for row, values in enumerate(entries):
                for col, value in enumerate(values):
                    cell = self.label(self.route_table, value, 11, bold=row == 0,
                                       width=1, wraplength=(115, 60, 115, 190)[col], justify="left",
                                       fg_color=SOFT if row == 0 else CARD)
                    cell.grid(row=row, column=col, sticky="nsew", padx=3, pady=4)
        text = self.label(content, format_report(report), 13, wraplength=540, justify="left")
        text.grid(row=2, column=0, sticky="nw", padx=6, pady=6)
        content.bind("<Configure>", lambda e: text.configure(
            wraplength=max(260, e.width / self._get_widget_scaling() - 24)), add="+")

    def luu_nhat_ky(self):
        path = filedialog.asksaveasfilename(title="Lưu nhật ký phiên", defaultextension=".log",
                                           initialfile=f"HAPGIS_{datetime.now():%Y%m%d_%H%M%S}.log",
                                           filetypes=[("Nhật ký", "*.log"), ("Văn bản", "*.txt")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("\n".join(self.log_lines) + "\n")
                self.ghi_log(f"Đã lưu nhật ký: {path}")
            except OSError as exc:
                messagebox.showerror("Không lưu được nhật ký", str(exc))

    def chay_nen(self, event, token, task):
        def work():
            try:
                self.hang_doi.put((event, token, task(), None))
            except Exception as exc:
                self.hang_doi.put((event, token, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def doi_nguon(self, kind):
        source = self.sources[kind]
        source["generation"] += 1
        if source["pending"]:
            self.after_cancel(source["pending"])
        source["ready"] = False
        source["fields"] = []
        source["layers"] = []
        for name in ("layer",):
            source[name].configure(values=[], state="normal")
            source[name].set("")
            source[name].configure(state="disabled")
        source["hint"].configure(text="Đang chờ đọc nguồn…")
        self.xoa_gia_tri()
        source["pending"] = self.after(450, lambda: self.tai_nguon(kind))

    def tai_nguon(self, kind):
        source = self.sources[kind]
        source["pending"] = None
        path = source["path"].get().strip()
        if not path:
            source["hint"].configure(text="Chưa chọn nguồn dữ liệu")
            return
        if co_nhieu_layer(path):
            source["hint"].configure(text="Đang đọc danh sách layer…")
            self.chay_nen("layers", (kind, source["generation"]), lambda: liet_ke_layer(path))
        else:
            self.tai_truong(kind)

    def tai_truong(self, kind):
        source = self.sources[kind]
        source["generation"] += 1
        source["ready"] = False
        source["fields"] = []
        self.xoa_gia_tri()
        path, layer = source["path"].get().strip(), source["layer"].get()
        if co_nhieu_layer(path) and not layer:
            source["hint"].configure(text="Hãy chọn layer trong danh sách.")
            return
        source["hint"].configure(text="Đang kiểm tra trường tenDuong…")
        self.chay_nen("fields", (kind, source["generation"]),
                      lambda: (liet_ke_truong(path, layer), mo_ta_kieu_lop(path, layer)))

    def xoa_gia_tri(self):
        self.value_generation += 1
        self.value_loading = False
        self.schema_hierarchical = None
        self.entry_tuyen.configure(values=[], state="disabled")
        self.entry_tuyen.set("")
        self.field_hint.configure(text="Chọn đủ hai lớp có tenDuong.")
        self.cap_nhat_san_sang()

    def tai_gia_tri(self):
        self.xoa_gia_tri()
        if not self.truong_hop_le():
            return
        self.value_loading = True
        self.entry_tuyen.configure(state="normal")
        self.field_hint.configure(text="Đang lập cây đường chính và hẻm có ở cả hai lớp…")
        house, road = self.sources["thua"], self.sources["duong"]
        params = (house["path"].get().strip(), house["layer"].get(),
                  road["path"].get().strip(), road["layer"].get())
        self.chay_nen("values", self.value_generation,
                      lambda: lap_danh_muc_tuyen(*params))
        self.cap_nhat_san_sang()

    def truong_hop_le(self):
        # Whether tenHem is usable depends on its values (a blank column in only
        # one layer is ignored), so that is decided when the catalog loads.
        return all(s["ready"] and FIELD_ROUTE in s["fields"] for s in self.sources.values())

    def cap_nhat_tom_tat(self):
        if not hasattr(self, "summary") or self.dang_chay:
            return
        hierarchical = getattr(self, "schema_hierarchical", None)
        if self.truong_hop_le() and hierarchical is not None:
            schema = f"{FIELD_ROUTE} + {FIELD_ALLEY}" if hierarchical else FIELD_ROUTE
            self.summary.configure(text=f"Khóa tuyến: {schema}\nHai lớp đã có schema đồng nhất.\n\nPhạm vi: {self.value_var.get().strip() or 'Tất cả giá trị'}")
        else:
            self.summary.configure(text="1. Chọn hai lớp có tenDuong\n2. Chọn giá trị tuyến\n3. Chọn nơi lưu kết quả")

    def cap_nhat_san_sang(self):
        if not hasattr(self, "btn_run") or self.dang_chay:
            return
        valid = self.truong_hop_le()
        route_ready = self.entry_tuyen.get_route_keys() != []
        ready = valid and route_ready and bool(self.output_var.get().strip()) and not self.value_loading and not self.check_loading
        self.btn_run.configure(state="normal" if ready else "disabled")
        self.btn_check.configure(state="normal" if valid and not self.check_loading and not self.value_loading else "disabled")
        self.btn_all.configure(state="normal" if valid else "disabled")
        self.status_label.configure(text="Sẵn sàng" if ready else "Đang tải giá trị" if self.value_loading else "Chờ cấu hình")
        self.cap_nhat_tom_tat()

    def doc_hang_doi(self):
        try:
            while True:
                event, token, data, error = self.hang_doi.get_nowait()
                if event == "log":
                    self.ghi_log(data)
                elif event == "run":
                    self.ket_thuc(data, error)
                elif event == "check":
                    if token != self.check_generation:
                        continue
                    self.check_loading = False
                    if error:
                        self.check_label.configure(text="!  Không đọc được dữ liệu", text_color=ERROR)
                        self.ghi_log(error)
                        messagebox.showerror("Kiểm tra dữ liệu", error)
                    else:
                        self.check_report = data
                        if data["errors"]:
                            text = f"!  {len(data['errors'])} lỗi cần sửa"
                        else:
                            text = f"✓  {data['matched_count']:,}/{data['house_count']:,} thửa khớp tuyến"
                            if data["warnings"]:
                                text += f" · {len(data['warnings'])} lưu ý"
                        self.check_label.configure(text=text, text_color=ERROR if data["errors"] else SUCCESS)
                        self.ghi_log(text)
                        self.hien_bao_cao(data)
                    self.cap_nhat_san_sang()
                elif event == "values":
                    if token != self.value_generation:
                        continue
                    self.value_loading = False
                    if error:
                        self.field_hint.configure(text=f"Không tải được danh sách tuyến: {error}")
                        self.ghi_log(error)
                    else:
                        self.schema_hierarchical = data["hierarchical"]
                        self.entry_tuyen.configure(catalog=data)
                        self.entry_tuyen.select_all()
                        count = len(data["items"])
                        schema = "tenDuong + tenHem" if data["hierarchical"] else "tenDuong (dữ liệu cũ)"
                        self.field_hint.configure(text=f"{count} tuyến chung · Schema {schema}." if count else "Không có khóa tuyến chung. Hãy kiểm tra lại tên ở hai lớp.")
                    self.cap_nhat_san_sang()
                else:
                    kind, generation = token
                    source = self.sources[kind]
                    if generation != source["generation"]:
                        continue
                    if error:
                        source["hint"].configure(text=f"Không đọc được dữ liệu: {error}")
                        self.ghi_log(error)
                    elif event == "layers":
                        source["layers"] = data
                        source["layer"].configure(values=data, state="readonly" if data else "disabled")
                        keys = ("thua", "parcel") if kind == "thua" else ("duong", "road")
                        matches = [name for name in data if any(key in name.casefold() for key in keys)]
                        selected = data[0] if len(data) == 1 else matches[0] if len(matches) == 1 else ""
                        source["layer"].set(selected)
                        source["hint"].configure(text="Hãy chọn layer trong danh sách." if data else "Không đọc được layer. Kiểm tra đường dẫn và định dạng dữ liệu.")
                        if selected:
                            self.tai_truong(kind)
                    elif event == "fields":
                        data, geometry_text = data
                        source["fields"] = data
                        source["ready"] = FIELD_ROUTE in data
                        if source["ready"]:
                            suffix = " + tenHem" if FIELD_ALLEY in data else ""
                            kind_text = f" · {geometry_text}" if geometry_text else ""
                            source["hint"].configure(text=f"Layer sẵn sàng · Có tenDuong{suffix}{kind_text}")
                        else:
                            message = "Thiếu trường bắt buộc 'tenDuong'. Hãy chuẩn hóa dữ liệu trước khi chạy."
                            source["hint"].configure(text=message)
                            self.field_hint.configure(text=message)
                            self.ghi_log(f"Lớp {'thửa' if kind == 'thua' else 'đường'}: {message}")
                        if self.truong_hop_le():
                            self.tai_gia_tri()
                    self.cap_nhat_san_sang()
        except queue.Empty:
            pass
        self.queue_after = self.after(100, self.doc_hang_doi)

    def chon_output(self):
        path = filedialog.asksaveasfilename(title="Lưu kết quả đánh số nhà", defaultextension=".gpkg",
                                           filetypes=[("GeoPackage", "*.gpkg"), ("Shapefile", "*.shp")])
        if path:
            self.output_var.set(path)

    def bat_dau(self):
        if self.dang_chay or self.value_loading or self.check_loading:
            return
        if not self.truong_hop_le():
            messagebox.showerror("Thiếu cấu hình", "Hãy chọn hai lớp có trường bắt buộc 'tenDuong'.")
            return
        house, road = self.sources["thua"], self.sources["duong"]
        params = dict(
            house_path=house["path"].get().strip(), house_layer=house["layer"].get(),
            road_path=road["path"].get().strip(), road_layer=road["layer"].get(),
            tuyen=self.entry_tuyen.get_manual_text(),
            route_keys=self.entry_tuyen.get_route_keys(),
            out_path=self.output_var.get().strip(),
        )
        out = params["out_path"]
        if os.path.splitext(out)[1].lower() not in (".shp", ".gpkg"):
            messagebox.showerror("Sai nơi lưu", "Chọn file kết quả .gpkg hoặc .shp.")
            return
        normalize = lambda path: os.path.normcase(os.path.realpath(path))
        for kind in ("house", "road"):
            source_path = params[f"{kind}_path"]
            if not os.path.exists(source_path):
                messagebox.showerror("Sai dữ liệu", f"Không tìm thấy dữ liệu:\n{source_path}")
                return
            if normalize(out) == normalize(source_path) or (la_gdb(source_path) and normalize(out).startswith(normalize(source_path) + os.sep)):
                messagebox.showerror("Sai nơi lưu", "File kết quả không được ghi đè hoặc nằm trong nguồn đầu vào.")
                return
        if normalize(params["house_path"]) == normalize(params["road_path"]) and params["house_layer"] == params["road_layer"]:
            messagebox.showerror("Chọn sai layer", "Lớp thửa và lớp đường đang trỏ đến cùng một layer.")
            return
        self.dang_chay = True
        self.btn_run.configure(state="disabled", text="Đang xử lý…")
        self.btn_check.configure(state="disabled")
        self.status_label.configure(text="Đang đánh số")
        self.btn_open.configure(state="disabled")
        self.saved_states = [(w, w.cget("state")) for w in self.controls + [self.entry_tuyen] +
                             [s["layer"] for s in self.sources.values()]]
        for widget, _ in self.saved_states:
            widget.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        schema = f"{FIELD_ROUTE} + {FIELD_ALLEY}" if FIELD_ALLEY in house["fields"] else FIELD_ROUTE
        self.ghi_log(f"Trường chuẩn: {schema} ở cả hai lớp")
        self.ghi_log(f"Phạm vi: {self.value_var.get().strip() or 'Tất cả'}")
        def run():
            chay_danh_so(**params, log=lambda text: self.hang_doi.put(("log", None, text, None)))
            return out
        self.chay_nen("run", None, run)

    def ket_thuc(self, out_path, error):
        self.dang_chay = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0 if error else 1)
        for widget, state in self.saved_states:
            widget.configure(state=state)
        self.btn_run.configure(text="Bắt đầu đánh số  →")
        self.cap_nhat_san_sang()
        self.status_label.configure(text="Cần kiểm tra" if error else "Hoàn thành")
        if error:
            self.ghi_log(f"Lỗi: {error}")
            messagebox.showerror("Lỗi xử lý", error)
        else:
            self.output_hien_tai = out_path
            self.btn_open.configure(state="normal")
            self.ghi_log(f"Đã lưu: {out_path}")
            messagebox.showinfo("Hoàn thành", "Đã đánh số nhà và xuất dữ liệu thành công.")

    def ghi_log(self, text):
        line = f"{datetime.now():%H:%M:%S}  {text}"
        self.log_lines.append(line)
        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, line + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")

    def mo_thu_muc_ket_qua(self):
        if self.output_hien_tai:
            try:
                os.startfile(os.path.dirname(os.path.abspath(self.output_hien_tai)))
            except OSError as exc:
                messagebox.showerror("Không mở được thư mục", str(exc))

    def destroy(self):
        if getattr(self, "queue_after", None):
            self.after_cancel(self.queue_after)
            self.queue_after = None
        for source in self.sources.values():
            if source["pending"]:
                self.after_cancel(source["pending"])
                source["pending"] = None
        super().destroy()


if __name__ == "__main__":
    AppDanhSoNha().mainloop()
