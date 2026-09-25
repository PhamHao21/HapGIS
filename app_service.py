# -*- coding: utf-8 -*-

import os
import geopandas as gpd

from core_housenumber import (
    process,
    doc_lop,
    khoa_ten,
    ten_truong_an_toan_shp,
    xoa_shapefile_cu,
    FIELD_HOUSE_ROAD,
    FIELD_ROAD_NAME,
)


def la_gdb(path):
    return bool(path) and str(path).lower().endswith(".gdb")


def liet_ke_layer(path):
    """
    Liệt kê layer trong File Geodatabase.
    """
    if not path:
        return []

    if not os.path.exists(path):
        return []

    if not la_gdb(path):
        return []

    try:
        import pyogrio

        ds = pyogrio.list_layers(path)

        return [str(row[0]) for row in ds]

    except Exception:
        pass

    try:
        bang = gpd.list_layers(path)

        if "name" in bang.columns:
            return bang["name"].astype(str).tolist()

    except Exception:
        pass

    return []


def doc_nguon(path, layer=None):
    """
    Đọc SHP/GPKG/GEOJSON hoặc GDB.
    GDB bắt buộc phải chọn layer.
    """
    if not path:
        raise ValueError("Chưa chọn dữ liệu.")

    if not os.path.exists(path):
        raise ValueError(f"Không tìm thấy dữ liệu:\n{path}")

    if la_gdb(path):
        if not layer:
            raise ValueError("File Geodatabase cần chọn layer.")

        return doc_lop(
            path,
            layer,
        )

    return doc_lop(path)


def loc_tuyen(
    houses,
    roads,
    tuyen,
):
    """
    Ví dụ:
        ""                  -> tất cả
        "H9"                -> một tuyến
        "H9;Đường số 5"     -> nhiều tuyến
    """
    tuyen = (tuyen or "").strip()

    if not tuyen:
        return houses, roads

    ds = [s.strip() for s in tuyen.split(";") if s.strip()]

    khoa_can = {khoa_ten(s) for s in ds}

    if FIELD_HOUSE_ROAD not in houses.columns:
        raise ValueError(f"Lớp thửa thiếu trường " f"'{FIELD_HOUSE_ROAD}'.")

    if FIELD_ROAD_NAME not in roads.columns:
        raise ValueError(f"Lớp đường thiếu trường " f"'{FIELD_ROAD_NAME}'.")

    houses = houses[houses[FIELD_HOUSE_ROAD].map(khoa_ten).isin(khoa_can)].copy()

    roads = roads[roads[FIELD_ROAD_NAME].map(khoa_ten).isin(khoa_can)].copy()

    if houses.empty:
        raise ValueError(f"Không tìm thấy thửa thuộc tuyến: {tuyen}")

    if roads.empty:
        raise ValueError(f"Không tìm thấy đường thuộc tuyến: {tuyen}")

    return houses, roads


def luu_ket_qua(
    out_gdf,
    out_path,
):
    if not out_path:
        raise ValueError("Chưa chọn nơi lưu kết quả.")

    thu_muc = os.path.dirname(out_path)

    if thu_muc:
        os.makedirs(
            thu_muc,
            exist_ok=True,
        )

    ext = os.path.splitext(out_path)[1].lower()

    # --------------------------------
    # SHAPEFILE
    # --------------------------------
    if ext == ".shp":
        xoa_shapefile_cu(out_path)

        out_xuat = ten_truong_an_toan_shp(
            out_gdf,
            out_path,
        )

        out_xuat.to_file(
            out_path,
            encoding="UTF-8",
        )

        return

    # --------------------------------
    # GEOPACKAGE
    # --------------------------------
    if ext == ".gpkg":
        if os.path.exists(out_path):
            os.remove(out_path)

        out_gdf.to_file(
            out_path,
            layer="DanhSoNha",
            driver="GPKG",
        )

        return

    raise ValueError("Đầu ra chỉ hỗ trợ .shp hoặc .gpkg")


def chay_danh_so(
    house_path,
    house_layer,
    road_path,
    road_layer,
    tuyen,
    out_path,
    log=None,
):
    """
    Hàm chính mà app_gui.py sẽ gọi.
    """

    def ghi(text):
        if log:
            log(str(text))

    # ================================
    # ĐỌC THỬA
    # ================================

    ghi("Đang đọc lớp thửa...")

    houses = doc_nguon(
        house_path,
        house_layer,
    )

    ghi(f"Đã đọc {len(houses)} thửa.")

    # ================================
    # ĐỌC ĐƯỜNG
    # ================================

    ghi("Đang đọc lớp đường...")

    roads = doc_nguon(
        road_path,
        road_layer,
    )

    ghi(f"Đã đọc {len(roads)} " f"đối tượng đường.")

    # ================================
    # LỌC TUYẾN
    # ================================

    houses, roads = loc_tuyen(
        houses,
        roads,
        tuyen,
    )

    if tuyen:
        ghi(
            f"Sau khi lọc tuyến: "
            f"{len(houses)} thửa / "
            f"{len(roads)} đối tượng đường."
        )

    # ================================
    # CHẠY CORE V13.5
    # ================================

    ghi("Đang chạy thuật toán " "đánh số nhà...")

    out = process(
        houses,
        roads,
        verbose=False,
    )

    ghi(f"Đã xử lý {len(out)} đối tượng.")

    # ================================
    # LƯU
    # ================================

    ghi("Đang ghi dữ liệu kết quả...")

    luu_ket_qua(
        out,
        out_path,
    )

    ghi("Hoàn thành.")

    return out
