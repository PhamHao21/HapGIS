# -*- coding: utf-8 -*-

import os
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from alley_numbering import prepare_alleys
from route_catalog import (
    FIELD_ALLEY,
    build_route_catalog,
    display_name,
    normalize_selected_keys,
    resolve_manual_selection,
    route_key_series,
    selection_text,
    validate_route_schema,
)

from core_housenumber import (
    process,
    doc_lop,
    khoa_ten,
    ten_truong_an_toan_shp,
    xoa_shapefile_cu,
    FIELD_ROUTE,
    KIEU_LAN,
    KIEU_POLYGON,
    KIEU_TIM,
    LOAI_POLYGON,
    LOAI_TIM,
    TIM_DUNG_SAI_NOI_M,
    kieu_hinh_hoc_tuyen,
    kiem_tra_he_toa_do,
    phan_tich_tim_duong,
)


def la_gdb(path):
    return bool(path) and str(path).lower().endswith(".gdb")


def co_nhieu_layer(path):
    return bool(path) and str(path).lower().endswith((".gdb", ".gpkg"))


def liet_ke_layer(path):
    """
    Liệt kê layer trong File Geodatabase hoặc GeoPackage.
    """
    if not path:
        return []

    if not os.path.exists(path):
        return []

    if not co_nhieu_layer(path):
        return []

    try:
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

    return doc_lop(path, layer)


def mo_ta_kieu_lop(path, layer=None):
    """Kiểu hình học của layer để hiển thị (chỉ đọc metadata); '' nếu không xác định."""
    try:
        geometry_type = pyogrio.read_info(path, **({"layer": layer} if layer else {}))["geometry_type"] or ""
    except Exception:
        return ""
    if "Polygon" in geometry_type:
        return "Polygon"
    if "LineString" in geometry_type:
        return "Polyline (tim đường)"
    return geometry_type


def liet_ke_truong(path, layer=None):
    """Read the schema without loading geometries or all attribute rows."""
    if la_gdb(path) and not layer:
        raise ValueError("Hãy chọn layer trong File Geodatabase.")
    info = pyogrio.read_info(path, **({"layer": layer} if layer else {}))
    return [str(field) for field in info["fields"]]


def liet_ke_gia_tri(path, layer=None):
    """Read tenDuong only; do not infer another route field."""
    if FIELD_ROUTE not in liet_ke_truong(path, layer):
        raise ValueError(f"Lớp đã chọn thiếu trường bắt buộc '{FIELD_ROUTE}'.")
    table = pyogrio.read_dataframe(
        path, columns=[FIELD_ROUTE], read_geometry=False,
        **({"layer": layer} if layer else {}),
    )
    values = {}
    for value in table[FIELD_ROUTE].dropna().unique():
        key = khoa_ten(value)
        if key:
            values.setdefault(key, str(value).strip())
    return values


def gia_tri_chung(house_values, road_values):
    return sorted(
        (road_values[key] for key in house_values.keys() & road_values.keys()),
        key=str.casefold,
    )


def lap_danh_muc_tuyen(house_path, house_layer, road_path, road_layer):
    """Load route attributes only and build the common road/alley tree."""
    def read(path, layer):
        fields = liet_ke_truong(path, layer)
        columns = [FIELD_ROUTE] + ([FIELD_ALLEY] if FIELD_ALLEY in fields else [])
        return pyogrio.read_dataframe(
            path, columns=columns, read_geometry=False,
            **({"layer": layer} if layer else {}),
        )
    return build_route_catalog(read(house_path, house_layer), read(road_path, road_layer))


def loc_tuyen(
    houses,
    roads,
    tuyen="",
    route_keys=None,
):
    """
    Ví dụ:
        ""                  -> tất cả
        "H9"                -> một tuyến
        "H9;Đường số 5"     -> nhiều tuyến
    """
    hierarchical = validate_route_schema(houses, roads)
    catalog = build_route_catalog(houses, roads)
    house_keys = route_key_series(houses, hierarchical)
    road_keys = route_key_series(roads, hierarchical)
    common = set(catalog["keys"])
    if not common:
        fields = "(tenDuong, tenHem)" if hierarchical else "tenDuong"
        raise ValueError(f"Khóa tuyến {fields} của hai lớp không có giá trị chung. Hãy kiểm tra lại tên tuyến.")

    tuyen = (tuyen or "").strip()
    if route_keys is None and not tuyen:
        return houses, roads

    selected = (normalize_selected_keys(catalog, route_keys) if route_keys is not None
                else resolve_manual_selection(catalog, tuyen))
    selected = set(selected or common)
    houses = houses[house_keys.isin(selected)].copy()
    roads = roads[road_keys.isin(selected)].copy()

    if houses.empty:
        raise ValueError(f"Không tìm thấy thửa thuộc tuyến: {tuyen}")

    if roads.empty:
        raise ValueError(f"Không tìm thấy đường thuộc tuyến: {tuyen}")

    return houses, roads


# Thửa lấn lên mặt đường cùng tuyến quá tỷ lệ này (theo diện tích thửa) thì cảnh báo.
ROAD_OVERLAP_WARNING_RATIO = 0.25
# Mảnh thửa nhỏ hơn tỷ lệ này sau khi trừ mặt đường được coi là sai số digitize, không tính là bị cắt.
ROAD_CUT_MIN_PART_RATIO = 0.01
OVERLAP_EXAMPLE_LIMIT = 5


def _so_manh_dang_ke(geometries, areas):
    """Count polygon parts of each geometry whose area is at least ROAD_CUT_MIN_PART_RATIO of `areas`."""
    parts, owner = shapely.get_parts(geometries, return_index=True)
    big = shapely.area(parts) >= ROAD_CUT_MIN_PART_RATIO * areas[owner]
    return np.bincount(owner[big], minlength=len(geometries))


def kiem_tra_chong_lan_duong(houses, roads, house_keys, road_keys, common):
    """
    So từng thửa với union mặt đường cùng khóa (tenDuong, tenHem).
    Trả về (errors, warnings); không thay đổi dữ liệu nguồn.
    """
    def usable(table):
        geometry = table.geometry
        return (geometry.notna() & ~geometry.is_empty & geometry.is_valid
                & geometry.geom_type.isin(["Polygon", "MultiPolygon"])).to_numpy()

    road_ok = usable(roads) & road_keys.isin(common).to_numpy()
    if not road_ok.any():
        return [], []
    codes, uniques = pd.factorize(road_keys[road_ok])
    road_geoms = roads.geometry.to_numpy()[road_ok]
    unions = np.array([shapely.union_all(road_geoms[codes == code]) for code in range(len(uniques))],
                      dtype=object)
    shapely.prepare(unions)
    lookup = {key: code for code, key in enumerate(uniques)}

    house_code = house_keys.map(lambda key: lookup.get(key, -1)).to_numpy()
    house_ok = usable(houses) & (house_code >= 0)
    if not house_ok.any():
        return [], []
    positions = np.flatnonzero(house_ok)
    parcels = houses.geometry.to_numpy()[positions]
    road = unions[house_code[positions]]
    touching = shapely.intersects(road, parcels)
    positions, parcels, road = positions[touching], parcels[touching], road[touching]
    if not len(positions):
        return [], []

    areas = shapely.area(parcels)
    overlap = shapely.area(shapely.intersection(parcels, road)) / np.where(areas > 0, areas, 1)
    center_in_road = shapely.intersects(road, shapely.point_on_surface(parcels))
    cut_through = (_so_manh_dang_ke(shapely.difference(parcels, road), areas)
                   > _so_manh_dang_ke(parcels, areas))
    too_much = (overlap > ROAD_OVERLAP_WARNING_RATIO) & ~center_in_road & ~cut_through

    def examples(mask):
        labels = []
        for pos, ratio in zip(positions[mask][:OVERLAP_EXAMPLE_LIMIT], overlap[mask]):
            row = houses.iloc[pos]
            route = " › ".join(filter(None, (display_name(row.get(field)) for field in (FIELD_ROUTE, FIELD_ALLEY))))
            labels.append(f"dòng #{houses.index[pos]} ({route or 'không tên'}, {ratio:.0%} trên đường)")
        return "; ".join(labels)

    errors, warnings = [], []
    if center_in_road.any():
        errors.append(
            f"Thửa: {int(center_in_road.sum()):,} thửa có tâm (representative point) nằm trong polygon "
            f"đường cùng tuyến; tool sẽ xếp sai bên TRÁI/PHẢI và lệch số các thửa lân cận. "
            f"Cần sửa ranh thửa hoặc ranh mặt đường. Ví dụ: {examples(center_in_road)}.")
    if (cut_through & ~center_in_road).any():
        mask = cut_through & ~center_in_road
        errors.append(
            f"Thửa: {int(mask.sum()):,} thửa vẽ cắt ngang polygon đường cùng tuyến (bị đường chia thành "
            f"từ 2 phần trở lên); tool không xác định được thửa nằm bên nào. Ví dụ: {examples(mask)}.")
    if too_much.any():
        warnings.append(
            f"Thửa: {int(too_much.sum()):,} thửa lấn lên mặt đường cùng tuyến quá "
            f"{ROAD_OVERLAP_WARNING_RATIO:.0%} diện tích thửa; nên kiểm tra lại ranh. "
            f"Ví dụ: {examples(too_much)}.")
    return errors, warnings


def _ten_tuyen(row):
    return " › ".join(filter(None, (display_name(row.get(field)) for field in (FIELD_ROUTE, FIELD_ALLEY))))


def kiem_tra_tim_duong(houses, roads, house_keys, road_keys, common):
    """
    Phân loại kiểu hình học từng tuyến và kiểm tra các tuyến vẽ bằng tim đường.
    Trả về (errors, warnings, so_tuyen_theo_kieu); không thay đổi dữ liệu nguồn.
    """
    vi_tri = {}
    for pos, key in enumerate(road_keys):
        if key in common:
            vi_tri.setdefault(key, []).append(pos)
    geometries = roads.geometry.to_numpy()
    kieu = {key: kieu_hinh_hoc_tuyen(geometries[pos]) for key, pos in vi_tri.items()}
    ten = {key: _ten_tuyen(roads.iloc[pos[0]]) or "không tên" for key, pos in vi_tri.items()}

    def lap(keys):
        keys = sorted(keys, key=lambda k: ten[k].casefold())
        return f"{len(keys):,} tuyến", "; ".join(ten[k] for k in keys[:OVERLAP_EXAMPLE_LIMIT])

    errors, warnings = [], []
    lan = [key for key, value in kieu.items() if value == KIEU_LAN]
    if lan:
        count, examples = lap(lan)
        errors.append(f"Đường: {count} lẫn polygon và polyline; mỗi tuyến chỉ được dùng một kiểu "
                      f"hình học. Ví dụ: {examples}.")

    tim_lines = {}
    nhanh, vong, roi, rong = [], [], [], []
    for key in (key for key, value in kieu.items() if value == KIEU_TIM):
        tim = phan_tich_tim_duong(geometries[vi_tri[key]])
        if not tim["lines"]:
            rong.append(key)
            continue
        tim_lines[key] = shapely.union_all(tim["lines"])
        if tim["nhanh"]:
            nhanh.append(key)
        if tim["vong"]:
            vong.append(key)
        if len(tim["lines"]) > 1:
            roi.append(key)
    for keys, message in (
        (rong, "polyline có độ dài 0"),
        (nhanh, "polyline phân nhánh (một điểm có từ 3 đoạn gặp nhau); chưa hỗ trợ, hãy tách nhánh "
                "thành tuyến riêng hoặc dùng polygon mặt đường"),
        (vong, "polyline khép kín thành vòng (vòng xoay); chưa hỗ trợ"),
    ):
        if keys:
            count, examples = lap(keys)
            errors.append(f"Đường: {count} {message}. Ví dụ: {examples}.")
    if roi:
        count, examples = lap(roi)
        warnings.append(
            f"Đường: {count} polyline gồm nhiều đoạn rời (khe hở lớn hơn {TIM_DUNG_SAI_NOI_M * 100:.0f} cm "
            f"giữa các đầu mút); số nhà vẫn đánh liên tục qua các đoạn, nên nối lại tim. Ví dụ: {examples}.")

    if tim_lines:
        house_geoms = houses.geometry.to_numpy()
        positions = np.array([pos for pos, key in enumerate(house_keys) if key in tim_lines
                              and house_geoms[pos] is not None and not house_geoms[pos].is_empty
                              and house_geoms[pos].geom_type in LOAI_POLYGON], dtype=int)
        if len(positions):
            lines = np.array([tim_lines[house_keys.iloc[pos]] for pos in positions], dtype=object)
            # Tim đi qua phần trong của thửa: không xác định được thửa nằm bên nào.
            crossed = shapely.relate_pattern(house_geoms[positions], lines, "T********")
            if crossed.any():
                rows = houses.iloc[positions[crossed][:OVERLAP_EXAMPLE_LIMIT]]
                examples = "; ".join(f"dòng #{index} ({_ten_tuyen(row) or 'không tên'})"
                                     for index, row in rows.iterrows())
                errors.append(
                    f"Thửa: {int(crossed.sum()):,} thửa bị tim đường cùng tuyến cắt qua; tool không xác "
                    f"định được thửa nằm bên TRÁI hay PHẢI. Cần sửa tim hoặc ranh thửa. Ví dụ: {examples}.")

    counts = {value: sum(1 for k in kieu.values() if k == value) for value in (KIEU_POLYGON, KIEU_TIM)}
    return errors, warnings, counts


def kiem_tra_du_lieu(houses, roads, tuyen="", route_keys=None):
    """Inspect the selected scope without modifying source geometries/attributes."""
    report = dict(errors=[], warnings=[], details=[], house_count=len(houses),
                  road_count=len(roads), matched_count=0, common_count=0)
    crs_ok = True
    try:
        kiem_tra_he_toa_do(houses, roads)
    except ValueError as exc:
        crs_ok = False
        report["errors"].append(str(exc))
    for table, label in ((houses, "Thửa"), (roads, "Đường")):
        crs = table.crs
        units = ", ".join(dict.fromkeys(axis.unit_name for axis in crs.axis_info[:2])) if crs else "không xác định"
        report["details"].append(f"{label} · CRS: {crs.name if crs else 'Chưa có CRS'} · {units}")
    if houses.crs:
        datum = houses.crs.geodetic_crs
        datum_name = "".join(c for c in (datum.name if datum else "").casefold() if c.isalnum())
        if "vn2000" not in datum_name and "vietnam2000" not in datum_name:
            report["warnings"].append("CRS chưa được nhận diện là VN-2000. Với dữ liệu địa chính, nên dùng VN-2000 đúng múi chiếu/kinh tuyến trục của khu vực.")
    try:
        catalog = build_route_catalog(houses, roads)
        selected_h, selected_r = loc_tuyen(houses, roads, tuyen, route_keys)
    except ValueError as exc:
        report["errors"].append(str(exc))
        return report
    report["house_count"], report["road_count"] = len(selected_h), len(selected_r)
    hierarchical = catalog["hierarchical"]
    house_keys = route_key_series(selected_h, hierarchical)
    road_keys = route_key_series(selected_r, hierarchical)
    common = (set(house_keys) & set(road_keys)) - {("", "")}
    report["common_count"] = len(common)
    report["matched_count"] = int(house_keys.isin(common).sum())
    report["details"] += [
        f"Trường chuẩn: {FIELD_ROUTE}" + (f" + {FIELD_ALLEY}" if hierarchical else "") + " ở cả hai lớp",
        f"Phạm vi: {selection_text(catalog, route_keys) if route_keys is not None else tuyen.strip() or 'Tất cả giá trị'}",
        f"{len(selected_h):,} thửa · {len(selected_r):,} đối tượng đường · {len(common):,} giá trị chung",
        f"{report['matched_count']:,}/{len(selected_h):,} thửa có tuyến tương ứng.",
    ]
    for table, keys, label, types in ((selected_h, house_keys, "Thửa", LOAI_POLYGON),
                                      (selected_r, road_keys, "Đường", LOAI_POLYGON + LOAI_TIM)):
        empty = table.geometry.isna() | table.geometry.is_empty
        wrong = ~empty & ~table.geometry.geom_type.isin(types)
        invalid = ~empty & ~table.geometry.is_valid
        type_text = ("Polygon/MultiPolygon" if label == "Thửa"
                     else "Polygon/MultiPolygon hoặc LineString/MultiLineString")
        for count, message in ((int(empty.sum()), "hình học rỗng"),
                               (int(wrong.sum()), f"hình học không phải {type_text}"),
                               (int(invalid.sum()), "hình học không hợp lệ")):
            if count:
                report["errors"].append(f"{label}: {count:,} đối tượng có {message}.")
        blanks = int(keys.map(lambda key: key == ("", "")).sum())
        if blanks:
            report["warnings"].append(f"{label}: {blanks:,} giá trị đối chiếu trống.")
    unmatched = set(house_keys) - set(road_keys) - {("", "")}
    if unmatched:
        examples = "; ".join(" › ".join(part for part in key if part) for key in sorted(unmatched)[:5])
        count = int(house_keys.isin(unmatched).sum())
        report["warnings"].append(f"{count:,} thửa không khớp đường, được giữ lại nhưng không có số nhà mới. Ví dụ: {examples}.")
    if crs_ok:
        overlap_errors, overlap_warnings = kiem_tra_chong_lan_duong(
            selected_h, selected_r, house_keys, road_keys, common)
        report["errors"].extend(overlap_errors)
        report["warnings"].extend(overlap_warnings)
        tim_errors, tim_warnings, counts = kiem_tra_tim_duong(
            selected_h, selected_r, house_keys, road_keys, common)
        report["errors"].extend(tim_errors)
        report["warnings"].extend(tim_warnings)
        report["road_kinds"] = counts
        report["details"].append(
            f"Kiểu đường: {counts[KIEU_POLYGON]:,} tuyến polygon (mặt đường) · "
            f"{counts[KIEU_TIM]:,} tuyến polyline (tim đường, thử nghiệm)")
    report["alley_routes"] = []
    report["_alley_contexts"] = {}
    if not report["errors"]:
        selected_keys = list(dict.fromkeys(key for key in house_keys if key in common))
        contexts, rows, errors = prepare_alleys(selected_keys, roads, hierarchical=hierarchical)
        report["alley_routes"] = rows
        report["_alley_contexts"] = contexts
        report["errors"].extend(errors)
        report["warnings"].extend(
            f"{row['route']}: {row['warning']}"
            for row in rows if row.get("warning")
        )
        parent_refs = {context.parent_name for context in contexts.values()}
        report["parent_count"] = len({key[0] for key in selected_keys})
        report["alley_count"] = sum(bool(key[1]) for key in selected_keys) if hierarchical else sum(
            row.get("is_alley", True) for row in rows)
        report["reference_count"] = len(parent_refs)
        report["details"].append(
            f"{report['parent_count']:,} đường cha · {report['alley_count']:,} hẻm đã chọn · "
            f"{report['reference_count']:,} tuyến tham chiếu thực sự dùng."
        )
    return report


def kiem_tra_nguon(house_path, house_layer, road_path, road_layer, tuyen="", route_keys=None):
    return kiem_tra_du_lieu(doc_nguon(house_path, house_layer),
                            doc_nguon(road_path, road_layer), tuyen, route_keys)


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
    route_keys=None,
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

    ghi("Kiểm tra CRS, đơn vị mét, hình học và giá trị đối chiếu...")
    all_roads = roads
    report = kiem_tra_du_lieu(houses, roads, tuyen, route_keys)
    if report["errors"]:
        raise ValueError("\n".join(report["errors"]))
    for warning in report["warnings"]:
        ghi(f"Lưu ý: {warning}")
    so_tuyen_tim = report.get("road_kinds", {}).get(KIEU_TIM, 0)
    if so_tuyen_tim:
        ghi(f"{so_tuyen_tim:,} tuyến dùng tim đường (polyline) · chế độ thử nghiệm, nên rà kết quả trên bản đồ.")

    # ================================
    # LỌC TUYẾN
    # ================================

    houses, roads = loc_tuyen(
        houses,
        roads,
        tuyen,
        route_keys,
    )

    if tuyen or route_keys is not None:
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
        reference_roads=all_roads,
        alley_contexts=report["_alley_contexts"],
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
