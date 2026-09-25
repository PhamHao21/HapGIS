# -*- coding: utf-8 -*-
APP_NAME = "HAPGIS"
APP_VERSION = "1.0.0"
APP_FULL_NAME = f"{APP_NAME} v{APP_VERSION}"

import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app_service import (
    chay_danh_so,
    liet_ke_layer,
    la_gdb,
)

# ============================================================
# CAU HINH GUI
# ============================================================

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def resource_path(relative_path):
    """Tra ve duong dan resource khi chay source hoac PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


class AppDanhSoNha(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Icon cua so / taskbar. Neu resource bi thieu thi app van chay binh thuong.
        try:
            self.iconbitmap(resource_path(os.path.join("assets", "hapgis.ico")))
        except Exception:
            pass

        # ----------------------------------------------------
        # CUA SO
        # ----------------------------------------------------
        self.title(f"{APP_FULL_NAME} - Công cụ đánh số nhà tự động")

        self.geometry("900x760")
        self.minsize(850, 740)

        # Cho phép resize ngang/dọc.
        self.resizable(True, True)

        # ----------------------------------------------------
        # BIEN TRANG THAI
        # ----------------------------------------------------
        self.hang_doi = queue.Queue()

        self.dang_chay = False
        self.output_hien_tai = ""

        # ----------------------------------------------------
        # GRID ROOT
        # ----------------------------------------------------
        self.grid_columnconfigure(
            0,
            weight=1,
        )

        self.grid_rowconfigure(
            6,
            weight=1,
        )

        # ----------------------------------------------------
        # TAO UI
        # ----------------------------------------------------
        self.tao_giao_dien()

        # Main thread doc message tu worker.
        self.after(
            100,
            self.doc_hang_doi,
        )

    # ========================================================
    # TAO GIAO DIEN
    # ========================================================

    def tao_giao_dien(self):

        # ====================================================
        # TITLE
        # ====================================================

        self.lbl_title = ctk.CTkLabel(
            self,
            text=f"{APP_FULL_NAME} - CÔNG CỤ ĐÁNH SỐ NHÀ TỰ ĐỘNG",
            font=ctk.CTkFont(
                size=22,
                weight="bold",
            ),
        )

        self.lbl_title.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 12),
            sticky="ew",
        )

        # ====================================================
        # FRAME THUA
        # ====================================================

        self.frame_thua = ctk.CTkFrame(self)

        self.frame_thua.grid(
            row=1,
            column=0,
            padx=20,
            pady=6,
            sticky="ew",
        )

        self.frame_thua.grid_columnconfigure(
            1,
            weight=1,
        )

        self.lbl_thua_title = ctk.CTkLabel(
            self.frame_thua,
            text="DỮ LIỆU THỬA",
            font=ctk.CTkFont(
                size=14,
                weight="bold",
            ),
        )

        self.lbl_thua_title.grid(
            row=0,
            column=0,
            columnspan=4,
            padx=12,
            pady=(10, 5),
            sticky="w",
        )

        # ----------------------------------------------------
        # THUA - NGUON
        # ----------------------------------------------------

        self.lbl_thua_path = ctk.CTkLabel(
            self.frame_thua,
            text="Nguồn:",
            width=80,
            anchor="w",
        )

        self.lbl_thua_path.grid(
            row=1,
            column=0,
            padx=(12, 5),
            pady=6,
        )

        self.entry_thua = ctk.CTkEntry(
            self.frame_thua,
            placeholder_text=("Chọn SHP / GPKG / GeoJSON " "hoặc File Geodatabase"),
        )

        self.entry_thua.grid(
            row=1,
            column=1,
            padx=5,
            pady=6,
            sticky="ew",
        )

        self.btn_file_thua = ctk.CTkButton(
            self.frame_thua,
            text="Chọn file",
            width=90,
            command=self.chon_file_thua,
        )

        self.btn_file_thua.grid(
            row=1,
            column=2,
            padx=5,
            pady=6,
        )

        self.btn_gdb_thua = ctk.CTkButton(
            self.frame_thua,
            text="Chọn GDB",
            width=90,
            command=self.chon_gdb_thua,
        )

        self.btn_gdb_thua.grid(
            row=1,
            column=3,
            padx=(5, 12),
            pady=6,
        )

        # ----------------------------------------------------
        # THUA - LAYER
        # ----------------------------------------------------

        self.lbl_layer_thua = ctk.CTkLabel(
            self.frame_thua,
            text="Layer:",
            width=80,
            anchor="w",
        )

        self.lbl_layer_thua.grid(
            row=2,
            column=0,
            padx=(12, 5),
            pady=(4, 12),
        )

        self.combo_layer_thua = ctk.CTkComboBox(
            self.frame_thua,
            values=[""],
            state="readonly",
        )

        self.combo_layer_thua.grid(
            row=2,
            column=1,
            columnspan=3,
            padx=(5, 12),
            pady=(4, 12),
            sticky="ew",
        )

        # ====================================================
        # FRAME DUONG
        # ====================================================

        self.frame_duong = ctk.CTkFrame(self)

        self.frame_duong.grid(
            row=2,
            column=0,
            padx=20,
            pady=6,
            sticky="ew",
        )

        self.frame_duong.grid_columnconfigure(
            1,
            weight=1,
        )

        self.lbl_duong_title = ctk.CTkLabel(
            self.frame_duong,
            text="DỮ LIỆU ĐƯỜNG",
            font=ctk.CTkFont(
                size=14,
                weight="bold",
            ),
        )

        self.lbl_duong_title.grid(
            row=0,
            column=0,
            columnspan=4,
            padx=12,
            pady=(10, 5),
            sticky="w",
        )

        # ----------------------------------------------------
        # DUONG - NGUON
        # ----------------------------------------------------

        self.lbl_duong_path = ctk.CTkLabel(
            self.frame_duong,
            text="Nguồn:",
            width=80,
            anchor="w",
        )

        self.lbl_duong_path.grid(
            row=1,
            column=0,
            padx=(12, 5),
            pady=6,
        )

        self.entry_duong = ctk.CTkEntry(
            self.frame_duong,
            placeholder_text=("Chọn SHP / GPKG / GeoJSON " "hoặc File Geodatabase"),
        )

        self.entry_duong.grid(
            row=1,
            column=1,
            padx=5,
            pady=6,
            sticky="ew",
        )

        self.btn_file_duong = ctk.CTkButton(
            self.frame_duong,
            text="Chọn file",
            width=90,
            command=self.chon_file_duong,
        )

        self.btn_file_duong.grid(
            row=1,
            column=2,
            padx=5,
            pady=6,
        )

        self.btn_gdb_duong = ctk.CTkButton(
            self.frame_duong,
            text="Chọn GDB",
            width=90,
            command=self.chon_gdb_duong,
        )

        self.btn_gdb_duong.grid(
            row=1,
            column=3,
            padx=(5, 12),
            pady=6,
        )

        # ----------------------------------------------------
        # DUONG - LAYER
        # ----------------------------------------------------

        self.lbl_layer_duong = ctk.CTkLabel(
            self.frame_duong,
            text="Layer:",
            width=80,
            anchor="w",
        )

        self.lbl_layer_duong.grid(
            row=2,
            column=0,
            padx=(12, 5),
            pady=(4, 12),
        )

        self.combo_layer_duong = ctk.CTkComboBox(
            self.frame_duong,
            values=[""],
            state="readonly",
        )

        self.combo_layer_duong.grid(
            row=2,
            column=1,
            columnspan=3,
            padx=(5, 12),
            pady=(4, 12),
            sticky="ew",
        )

        # ====================================================
        # FRAME OPTION
        # ====================================================

        self.frame_option = ctk.CTkFrame(self)

        self.frame_option.grid(
            row=3,
            column=0,
            padx=20,
            pady=6,
            sticky="ew",
        )

        self.frame_option.grid_columnconfigure(
            1,
            weight=1,
        )

        # ----------------------------------------------------
        # TUYEN
        # ----------------------------------------------------

        self.lbl_tuyen = ctk.CTkLabel(
            self.frame_option,
            text="Tuyến:",
            width=80,
            anchor="w",
        )

        self.lbl_tuyen.grid(
            row=0,
            column=0,
            padx=(12, 5),
            pady=10,
        )

        self.entry_tuyen = ctk.CTkEntry(
            self.frame_option,
            placeholder_text=("Để trống = chạy tất cả. " "VD: H9 hoặc H9;Đường số 5"),
        )

        self.entry_tuyen.grid(
            row=0,
            column=1,
            columnspan=2,
            padx=(5, 12),
            pady=10,
            sticky="ew",
        )

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        self.lbl_output = ctk.CTkLabel(
            self.frame_option,
            text="Kết quả:",
            width=80,
            anchor="w",
        )

        self.lbl_output.grid(
            row=1,
            column=0,
            padx=(12, 5),
            pady=(5, 12),
        )

        self.entry_output = ctk.CTkEntry(
            self.frame_option,
            placeholder_text=("Khuyến nghị lưu GeoPackage (.gpkg)"),
        )

        self.entry_output.grid(
            row=1,
            column=1,
            padx=5,
            pady=(5, 12),
            sticky="ew",
        )

        self.btn_output = ctk.CTkButton(
            self.frame_option,
            text="Chọn nơi lưu",
            width=120,
            command=self.chon_output,
        )

        self.btn_output.grid(
            row=1,
            column=2,
            padx=(5, 12),
            pady=(5, 12),
        )

        # ====================================================
        # BUTTON RUN
        # ====================================================

        self.btn_run = ctk.CTkButton(
            self,
            text="BẮT ĐẦU ĐÁNH SỐ NHÀ",
            height=46,
            font=ctk.CTkFont(
                size=15,
                weight="bold",
            ),
            fg_color="#2b8a3e",
            hover_color="#216a2f",
            command=self.bat_dau,
        )

        self.btn_run.grid(
            row=4,
            column=0,
            padx=20,
            pady=(12, 6),
            sticky="ew",
        )

        # ====================================================
        # PROGRESS
        # ====================================================

        self.progress = ctk.CTkProgressBar(
            self,
            mode="indeterminate",
        )

        self.progress.grid(
            row=5,
            column=0,
            padx=20,
            pady=6,
            sticky="ew",
        )

        self.progress.set(0)

        # ====================================================
        # LOG
        # ====================================================

        self.txt_log = ctk.CTkTextbox(
            self,
            height=180,
        )

        self.txt_log.grid(
            row=6,
            column=0,
            padx=20,
            pady=(6, 8),
            sticky="nsew",
        )

        # ====================================================
        # OPEN OUTPUT
        # ====================================================

        self.btn_open = ctk.CTkButton(
            self,
            text="MỞ THƯ MỤC KẾT QUẢ",
            state="disabled",
            command=self.mo_thu_muc_ket_qua,
        )

        self.btn_open.grid(
            row=7,
            column=0,
            padx=20,
            pady=(0, 8),
            sticky="ew",
        )

        # ====================================================
        # FOOTER / BRANDING
        # ====================================================

        self.lbl_version = ctk.CTkLabel(
            self,
            text=(
                f"{APP_FULL_NAME} | House Address Processing GIS  •  "
                "GIS FOR BETTER CITIES"
            ),
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11),
        )

        self.lbl_version.grid(
            row=8,
            column=0,
            padx=20,
            pady=(0, 12),
            sticky="e",
        )

        self.ghi_log(f"{APP_FULL_NAME} sẵn sàng.")

    # ========================================================
    # HELPER
    # ========================================================

    def gan_entry(
        self,
        entry,
        text,
    ):
        entry.delete(
            0,
            tk.END,
        )

        entry.insert(
            0,
            text,
        )

    # ========================================================
    # CHON FILE THUA
    # ========================================================

    def chon_file_thua(self):
        p = filedialog.askopenfilename(
            title="Chọn dữ liệu thửa",
            filetypes=[
                (
                    "GIS Dataset",
                    "*.shp *.gpkg *.geojson",
                ),
                (
                    "Shapefile",
                    "*.shp",
                ),
                (
                    "GeoPackage",
                    "*.gpkg",
                ),
                (
                    "GeoJSON",
                    "*.geojson",
                ),
                (
                    "All Files",
                    "*.*",
                ),
            ],
        )

        if not p:
            return

        self.gan_entry(
            self.entry_thua,
            p,
        )

        self.cap_nhat_layer(
            p,
            self.combo_layer_thua,
            "thua",
        )

    # ========================================================
    # CHON FILE DUONG
    # ========================================================

    def chon_file_duong(self):
        p = filedialog.askopenfilename(
            title="Chọn dữ liệu đường",
            filetypes=[
                (
                    "GIS Dataset",
                    "*.shp *.gpkg *.geojson",
                ),
                (
                    "Shapefile",
                    "*.shp",
                ),
                (
                    "GeoPackage",
                    "*.gpkg",
                ),
                (
                    "GeoJSON",
                    "*.geojson",
                ),
                (
                    "All Files",
                    "*.*",
                ),
            ],
        )

        if not p:
            return

        self.gan_entry(
            self.entry_duong,
            p,
        )

        self.cap_nhat_layer(
            p,
            self.combo_layer_duong,
            "duong",
        )

    # ========================================================
    # CHON GDB THUA
    # ========================================================

    def chon_gdb_thua(self):
        p = filedialog.askdirectory(title="Chọn File Geodatabase (.gdb)")

        if not p:
            return

        if not p.lower().endswith(".gdb"):
            messagebox.showerror(
                "Sai dữ liệu",
                ("Thư mục được chọn không phải " "File Geodatabase (.gdb)."),
            )
            return

        self.gan_entry(
            self.entry_thua,
            p,
        )

        self.cap_nhat_layer(
            p,
            self.combo_layer_thua,
            "thua",
        )

    # ========================================================
    # CHON GDB DUONG
    # ========================================================

    def chon_gdb_duong(self):
        p = filedialog.askdirectory(title="Chọn File Geodatabase (.gdb)")

        if not p:
            return

        if not p.lower().endswith(".gdb"):
            messagebox.showerror(
                "Sai dữ liệu",
                ("Thư mục được chọn không phải " "File Geodatabase (.gdb)."),
            )
            return

        self.gan_entry(
            self.entry_duong,
            p,
        )

        self.cap_nhat_layer(
            p,
            self.combo_layer_duong,
            "duong",
        )

    # ========================================================
    # CAP NHAT DANH SACH LAYER
    # ========================================================

    def cap_nhat_layer(
        self,
        path,
        combo,
        loai,
    ):
        """
        loai:
            "thua"
            "duong"

        Không lấy layer đầu tiên một cách mù quáng.

        Chỉ tự gợi ý nếu tên layer có từ khóa phù hợp.
        Người dùng vẫn có thể chọn lại bằng ComboBox.
        """

        # ----------------------------------------------------
        # KHONG PHAI GDB
        # ----------------------------------------------------

        if not la_gdb(path):
            combo.configure(
                values=[""],
            )

            combo.set("")

            return

        # ----------------------------------------------------
        # GDB
        # ----------------------------------------------------

        try:
            ds = liet_ke_layer(path)

            if not ds:
                raise ValueError(
                    "Không đọc được danh sách layer " "trong File Geodatabase."
                )

            combo.configure(
                values=ds,
            )

            # Không mặc định ds[0].
            goi_y = None

            # -----------------------------------------------
            # GOI Y LAYER THUA
            # -----------------------------------------------

            if loai == "thua":
                tu_khoa = [
                    "ranhthua",
                    "ranh_thua",
                    "thua",
                    "parcel",
                ]

            # -----------------------------------------------
            # GOI Y LAYER DUONG
            # -----------------------------------------------

            else:
                tu_khoa = [
                    "duonggiaothong",
                    "duong_giao_thong",
                    "giaothong",
                    "giao_thong",
                    "road",
                    "duong",
                ]

            for layer in ds:
                ten = str(layer).casefold()

                if any(keyword in ten for keyword in tu_khoa):
                    goi_y = layer
                    break

            # -----------------------------------------------
            # SET COMBO
            # -----------------------------------------------

            if goi_y:
                combo.set(goi_y)

                self.ghi_log(f"Tự gợi ý layer {loai}: " f"{goi_y}")

            else:
                # Không đoán nếu không chắc.
                combo.set("")

                self.ghi_log(
                    f"Không tự xác định được layer {loai}. " f"Hãy chọn thủ công."
                )

            self.ghi_log(f"Đọc được {len(ds)} layer trong GDB.")

        except Exception as e:
            combo.configure(
                values=[""],
            )

            combo.set("")

            messagebox.showerror(
                "Lỗi GDB",
                str(e),
            )

    # ========================================================
    # CHON OUTPUT
    # ========================================================

    def chon_output(self):
        p = filedialog.asksaveasfilename(
            title="Chọn nơi lưu kết quả",
            defaultextension=".gpkg",
            filetypes=[
                (
                    "GeoPackage",
                    "*.gpkg",
                ),
                (
                    "Shapefile",
                    "*.shp",
                ),
            ],
        )

        if not p:
            return

        self.gan_entry(
            self.entry_output,
            p,
        )

    # ========================================================
    # BAT DAU
    # ========================================================

    def bat_dau(self):

        if self.dang_chay:
            return

        # ----------------------------------------------------
        # LAY INPUT
        # ----------------------------------------------------

        house_path = self.entry_thua.get().strip()

        road_path = self.entry_duong.get().strip()

        out_path = self.entry_output.get().strip()

        tuyen = self.entry_tuyen.get().strip()

        # ----------------------------------------------------
        # KIEM TRA DUONG DAN
        # ----------------------------------------------------

        if not house_path:
            messagebox.showerror(
                "Thiếu dữ liệu",
                "Chưa chọn lớp Thửa.",
            )
            return

        if not road_path:
            messagebox.showerror(
                "Thiếu dữ liệu",
                "Chưa chọn lớp Đường.",
            )
            return

        if not os.path.exists(house_path):
            messagebox.showerror(
                "Sai dữ liệu",
                ("Không tìm thấy dữ liệu Thửa:\n\n" f"{house_path}"),
            )
            return

        if not os.path.exists(road_path):
            messagebox.showerror(
                "Sai dữ liệu",
                ("Không tìm thấy dữ liệu Đường:\n\n" f"{road_path}"),
            )
            return

        if not out_path:
            messagebox.showerror(
                "Thiếu dữ liệu",
                "Chưa chọn nơi lưu kết quả.",
            )
            return

        # ----------------------------------------------------
        # LAY LAYER
        # ----------------------------------------------------

        house_layer = ""

        if la_gdb(house_path):
            house_layer = self.combo_layer_thua.get().strip()

            if not house_layer:
                messagebox.showerror(
                    "Thiếu layer",
                    (
                        "Bạn đang dùng File Geodatabase "
                        "cho dữ liệu Thửa.\n\n"
                        "Hãy chọn Layer Thửa."
                    ),
                )
                return

        road_layer = ""

        if la_gdb(road_path):
            road_layer = self.combo_layer_duong.get().strip()

            if not road_layer:
                messagebox.showerror(
                    "Thiếu layer",
                    (
                        "Bạn đang dùng File Geodatabase "
                        "cho dữ liệu Đường.\n\n"
                        "Hãy chọn Layer Đường."
                    ),
                )
                return

        # ----------------------------------------------------
        # CHAN LOI VUA GAP:
        # CUNG GDB + CUNG LAYER
        # ----------------------------------------------------

        if (
            la_gdb(house_path)
            and la_gdb(road_path)
            and os.path.normcase(os.path.abspath(house_path))
            == os.path.normcase(os.path.abspath(road_path))
            and house_layer
            and road_layer
            and house_layer == road_layer
        ):
            messagebox.showerror(
                "Chọn sai dữ liệu",
                (
                    "Lớp Thửa và Lớp Đường đang "
                    "chọn CÙNG MỘT LAYER.\n\n"
                    f"Layer hiện tại:\n"
                    f"{house_layer}\n\n"
                    "Hãy chọn đúng:\n"
                    "- Layer ranh thửa\n"
                    "- Layer đường giao thông"
                ),
            )
            return

        # ----------------------------------------------------
        # CHAN OUTPUT TRUNG INPUT FILE
        # ----------------------------------------------------

        if not la_gdb(house_path) and os.path.abspath(out_path) == os.path.abspath(
            house_path
        ):
            messagebox.showerror(
                "Sai nơi lưu",
                ("File kết quả đang trùng với " "file Thửa đầu vào."),
            )
            return

        if not la_gdb(road_path) and os.path.abspath(out_path) == os.path.abspath(
            road_path
        ):
            messagebox.showerror(
                "Sai nơi lưu",
                ("File kết quả đang trùng với " "file Đường đầu vào."),
            )
            return

        # ----------------------------------------------------
        # LOG INPUT
        # ----------------------------------------------------

        self.ghi_log("----------------------------------------")

        self.ghi_log("Bắt đầu xử lý.")

        self.ghi_log(f"Nguồn Thửa: {house_path}")

        if house_layer:
            self.ghi_log(f"Layer Thửa: {house_layer}")

        self.ghi_log(f"Nguồn Đường: {road_path}")

        if road_layer:
            self.ghi_log(f"Layer Đường: {road_layer}")

        if tuyen:
            self.ghi_log(f"Tuyến: {tuyen}")
        else:
            self.ghi_log("Tuyến: TẤT CẢ")

        self.ghi_log(f"Kết quả: {out_path}")

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.dang_chay = True
        self.output_hien_tai = out_path

        self.btn_run.configure(
            state="disabled",
            text="ĐANG XỬ LÝ... VUI LÒNG CHỜ",
        )

        self.btn_open.configure(
            state="disabled",
        )

        self.progress.set(0)
        self.progress.start()

        # ----------------------------------------------------
        # START WORKER
        # ----------------------------------------------------

        thread = threading.Thread(
            target=self.worker,
            args=(
                house_path,
                house_layer,
                road_path,
                road_layer,
                tuyen,
                out_path,
            ),
            daemon=True,
        )

        thread.start()

    # ========================================================
    # WORKER THREAD
    # ========================================================

    def worker(
        self,
        house_path,
        house_layer,
        road_path,
        road_layer,
        tuyen,
        out_path,
    ):
        """
        Worker tuyệt đối không sửa GUI trực tiếp.

        Chỉ gửi message vào Queue.
        Main thread sẽ lấy Queue để update GUI.
        """

        try:
            chay_danh_so(
                house_path=house_path,
                house_layer=house_layer,
                road_path=road_path,
                road_layer=road_layer,
                tuyen=tuyen,
                out_path=out_path,
                log=lambda text: (
                    self.hang_doi.put(
                        (
                            "log",
                            str(text),
                        )
                    )
                ),
            )

            self.hang_doi.put(
                (
                    "done",
                    out_path,
                )
            )

        except Exception as e:
            self.hang_doi.put(
                (
                    "error",
                    (f"{type(e).__name__}: " f"{e}"),
                )
            )

    # ========================================================
    # DOC QUEUE
    # ========================================================

    def doc_hang_doi(self):

        try:
            while True:
                loai, noi_dung = self.hang_doi.get_nowait()

                if loai == "log":
                    self.ghi_log(noi_dung)

                elif loai == "done":
                    self.ket_thuc_thanh_cong(noi_dung)

                elif loai == "error":
                    self.ket_thuc_loi(noi_dung)

        except queue.Empty:
            pass

        # Lặp lại.
        self.after(
            100,
            self.doc_hang_doi,
        )

    # ========================================================
    # LOG
    # ========================================================

    def ghi_log(
        self,
        text,
    ):
        self.txt_log.insert(
            tk.END,
            f"> {text}\n",
        )

        self.txt_log.see(tk.END)

    # ========================================================
    # THANH CONG
    # ========================================================

    def ket_thuc_thanh_cong(
        self,
        out_path,
    ):
        self.dang_chay = False

        self.progress.stop()
        self.progress.set(1)

        self.btn_run.configure(
            state="normal",
            text="BẮT ĐẦU ĐÁNH SỐ NHÀ",
        )

        self.btn_open.configure(
            state="normal",
        )

        self.ghi_log("HOÀN THÀNH.")

        self.ghi_log(f"Đã lưu: {out_path}")

        messagebox.showinfo(
            "Hoàn thành",
            ("Đã đánh số nhà và xuất " "dữ liệu thành công."),
        )

    # ========================================================
    # LOI
    # ========================================================

    def ket_thuc_loi(
        self,
        loi,
    ):
        self.dang_chay = False

        self.progress.stop()
        self.progress.set(0)

        self.btn_run.configure(
            state="normal",
            text="BẮT ĐẦU ĐÁNH SỐ NHÀ",
        )

        self.btn_open.configure(
            state="disabled",
        )

        self.ghi_log(f"LỖI: {loi}")

        messagebox.showerror(
            "Lỗi xử lý",
            loi,
        )

    # ========================================================
    # MO THU MUC OUTPUT
    # ========================================================

    def mo_thu_muc_ket_qua(self):

        if not self.output_hien_tai:
            return

        folder = os.path.dirname(self.output_hien_tai)

        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)

            except Exception as e:
                messagebox.showerror(
                    "Không mở được thư mục",
                    str(e),
                )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    app = AppDanhSoNha()
    app.mainloop()
