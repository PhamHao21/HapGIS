# -*- coding: utf-8 -*-

"""
HAPGIS Core 1.2
---------------
Thuật toán đánh số nhà tự động trên dữ liệu GIS.

Nguyên tắc chính:
- xác định hướng tuyến theo 4 hướng quy ước;
- xác định điểm mặt đường của từng thửa;
- phân loại TRAI / PHAI;
- sắp thứ tự theo biên đường và topology tiếp giáp thửa;
- hậu kiểm các trường hợp outlier và cặp thửa cuối bị gán chéo;
- đánh số TRAI lẻ, PHAI chẵn.

Lưu ý:
- Core yêu cầu hai lớp cùng CRS projected, đơn vị mét.
- Các hàm public được app_service.py sử dụng được giữ ổn định.
"""

CORE_NAME = "HAPGIS"
CORE_VERSION = "1.2"

import heapq
import math

import numpy as np
import os

import pandas as pd
import geopandas as gpd

import shapely
from shapely.geometry import Point, LineString, MultiPoint
from shapely.ops import linemerge, nearest_points, substring

# ============================================================
# CAU HINH
# ============================================================

HOUSE_SHP = r"D:\thorw\Documents\GIS\ArcGIS\haha\haha.gdb"
HOUSE_LAYER = "ranhthua_demo_pdien__Project1"

ROAD_SHP = r"D:\thorw\Documents\GIS\ArcGIS\haha\haha.gdb"
ROAD_LAYER = "duonggiaothong_demo_pdien_Project"

OUTPUT_SHP = r"D:\thorw\Documents\GIS\Output\PhongDien_demo1.shp"

DEBUG_LINE_SHP = r"D:\thorw\Documents\GIS\Output\PhongDien_duong_tham_chieu_v13_5.shp"
DEBUG_ACCESS_SHP = r"D:\thorw\Documents\GIS\Output\PhongDien_diem_tiep_can_v13_5.shp"

# De "" neu muon chay tat ca.
# Co the nhap nhieu tuyen, cach nhau bang dau ;
TUYEN = "Đường số 5"

FIELD_ROUTE = "tenDuong"
FIELD_HOUSE_ROAD = FIELD_ROUTE
FIELD_ROAD_NAME = FIELD_ROUTE

# 4 field output chinh
COL_BEN = "traiPhai"
COL_STT = "thuTuDiaChi"
COL_SONHA = "soNhaHienThi"
COL_HUONG = "huong"

GT_TRAI = "TRAI"
GT_PHAI = "PHAI"

STEP = 10
MATCH_EXACT = False


# ============================================================
# DOC / KIEM TRA DU LIEU
# ============================================================


def doc_lop(path, layer=None):
    if str(path).lower().endswith(".gdb"):
        if not layer:
            raise ValueError(f"Du lieu GDB can khai bao layer: {path}")
        return gpd.read_file(path, layer=layer)
    return gpd.read_file(path, **({"layer": layer} if layer else {}))


def khoa_ten(v):
    if pd.isna(v):
        return ""
    s = str(v).strip()
    return s if MATCH_EXACT else s.casefold()


def kiem_tra_he_toa_do(houses, roads):
    if houses.crs is None or roads.crs is None:
        raise ValueError("Thiếu CRS ở lớp thửa hoặc lớp đường.")

    if houses.crs != roads.crs:
        raise ValueError(
            "Hai lớp đang khác CRS. Hãy dùng Project/Reproject "
            "để đưa hai lớp về cùng hệ tọa độ trước."
        )

    try:
        if not houses.crs.is_projected:
            raise ValueError(
                "CRS hiện tại không phải hệ tọa độ phẳng (projected). "
                "Cần chuyển sang hệ tọa độ phẳng đơn vị mét trước khi chạy."
            )
    except AttributeError:
        pass

    axes = houses.crs.axis_info[:2]
    if len(axes) != 2 or any(
        not math.isclose(axis.unit_conversion_factor, 1.0, rel_tol=0, abs_tol=1e-12)
        for axis in axes
    ):
        raise ValueError(
            "Hai lớp phải dùng đơn vị mét (meter/metre), không phải feet hay độ. "
            "Hãy Project/Reproject dữ liệu sang hệ tọa độ phẳng đơn vị mét."
        )


def xoa_shapefile_cu(path):
    base, _ = os.path.splitext(path)
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx"]:
        p = base + ext
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def ten_truong_an_toan_shp(gdf, duong_dan_output):
    """
    Rut gon ten field khi xuat ESRI Shapefile.

    Shapefile gioi han ten field 10 ky tu. Neu output khong phai .shp,
    GeoDataFrame duoc giu nguyen ten field.
    """
    if not str(duong_dan_output).lower().endswith(".shp"):
        return gdf

    doi_ten = {}
    da_dung = set(gdf.columns)

    for c in gdf.columns:
        if c == "geometry" or len(c) <= 10:
            continue

        ten_moi = c[:10]
        i = 1

        while ten_moi in da_dung and ten_moi != c:
            hau_to = str(i)
            ten_moi = c[: 10 - len(hau_to)] + hau_to
            i += 1

        doi_ten[c] = ten_moi
        da_dung.add(ten_moi)

    if doi_ten:
        print("\nXuat .shp -> field >10 ky tu se bi rut gon:")
        for cu, moi in doi_ten.items():
            print(f"   {cu} -> {moi}")
        gdf = gdf.rename(columns=doi_ten)

    return gdf


# ============================================================
# POLYGON -> REFERENCE LINE
# ============================================================


def truc_dai_tu_polygon(geom):
    """Lay truc dai cua minimum rotated rectangle."""
    if geom is None or geom.is_empty:
        raise ValueError("Geometry rong")

    rect = geom.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)[:-1]

    if len(coords) != 4:
        raise ValueError("Khong tao duoc minimum rotated rectangle 4 dinh")

    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    edges.sort(key=lambda e: math.dist(e[0], e[1]))

    (a1, b1), (a2, b2) = edges[0], edges[1]

    mid1 = ((a1[0] + b1[0]) / 2.0, (a1[1] + b1[1]) / 2.0)
    mid2 = ((a2[0] + b2[0]) / 2.0, (a2[1] + b2[1]) / 2.0)

    line = LineString([mid1, mid2])

    if line.length == 0:
        raise ValueError("Truc tham chieu co do dai 0")

    return line


def tach_polygon_components(geo_series):
    """Tach Polygon/MultiPolygon thanh danh sach Polygon don."""
    polys = []

    for geom in geo_series:
        if geom is None or geom.is_empty:
            continue

        if geom.geom_type == "Polygon":
            polys.append(geom)

        elif geom.geom_type == "MultiPolygon":
            polys.extend([p for p in geom.geoms if p is not None and not p.is_empty])

    return polys


def lay_cac_line(intersection_geom):
    """Rut cac LineString tu ket qua giao hinh."""
    if intersection_geom is None or intersection_geom.is_empty:
        return []

    gt = intersection_geom.geom_type

    if gt == "LineString":
        return [intersection_geom]

    if gt == "MultiLineString":
        return [g for g in intersection_geom.geoms if g is not None and not g.is_empty]

    if gt == "GeometryCollection":
        out = []
        for g in intersection_geom.geoms:
            out.extend(lay_cac_line(g))
        return out

    return []


def sap_xep_diem_theo_mst_diameter(points):
    """
    Giu nguyen y tuong tot cua ban cu:
    center point -> MST -> tree diameter -> thu tu line.
    """
    pts = []

    for x, y in points:
        keep = True

        for px, py in pts[-5:]:
            if math.hypot(x - px, y - py) < 1e-9:
                keep = False
                break

        if keep:
            pts.append((float(x), float(y)))

    n = len(pts)

    if n < 2:
        return pts

    if n == 2:
        return pts

    in_tree = [False] * n
    best = [float("inf")] * n
    parent = [-1] * n
    best[0] = 0.0

    for _ in range(n):
        u = -1
        u_best = float("inf")

        for i in range(n):
            if not in_tree[i] and best[i] < u_best:
                u = i
                u_best = best[i]

        if u == -1:
            break

        in_tree[u] = True
        ux, uy = pts[u]

        for v in range(n):
            if in_tree[v]:
                continue

            vx, vy = pts[v]
            d = math.hypot(vx - ux, vy - uy)

            if d < best[v]:
                best[v] = d
                parent[v] = u

    adj = [[] for _ in range(n)]

    for v in range(1, n):
        u = parent[v]

        if u >= 0:
            d = math.hypot(
                pts[v][0] - pts[u][0],
                pts[v][1] - pts[u][1],
            )
            adj[u].append((v, d))
            adj[v].append((u, d))

    def farthest(start):
        stack = [(start, -1, 0.0)]
        far_node = start
        far_dist = 0.0
        par = {start: -1}

        while stack:
            u, p, dist = stack.pop()

            if dist > far_dist:
                far_node = u
                far_dist = dist

            for v, w in adj[u]:
                if v == p:
                    continue

                par[v] = u
                stack.append((v, u, dist + w))

        return far_node, far_dist, par

    a, _, _ = farthest(0)
    b, _, par_from_a = farthest(a)

    idx_path = []
    cur = b

    while cur != -1:
        idx_path.append(cur)

        if cur == a:
            break

        cur = par_from_a.get(cur, -1)

    idx_path.reverse()
    ordered = [pts[i] for i in idx_path]

    # Neu MST diameter bo qua qua nhieu diem thi giu thu tu quet cu.
    if len(ordered) < max(2, int(n * 0.55)):
        return pts

    return ordered


def truc_cong_tu_polygon(poly, so_mau=120):
    """
    Polygon -> reference line cong:
    MRR -> huong quet -> mat cat -> midpoint -> MST.
    """
    if poly is None or poly.is_empty:
        return None

    axis = truc_dai_tu_polygon(poly)
    coords = list(axis.coords)

    if len(coords) < 2:
        return None

    x1, y1 = coords[0]
    x2, y2 = coords[-1]

    dx = x2 - x1
    dy = y2 - y1

    axis_len = math.hypot(dx, dy)

    if axis_len == 0:
        return None

    ux, uy = dx / axis_len, dy / axis_len
    vx, vy = -uy, ux

    boundary_coords = list(poly.exterior.coords)

    if len(boundary_coords) < 4:
        return None

    t_values = [(x - x1) * ux + (y - y1) * uy for x, y in boundary_coords]

    t_min = min(t_values)
    t_max = max(t_values)

    minx, miny, maxx, maxy = poly.bounds
    bbox_diag = math.hypot(maxx - minx, maxy - miny)

    cut_half = max(bbox_diag * 1.5, axis_len)
    n = max(40, min(240, int(so_mau)))

    center_pts = []
    prev_mid = None

    for i in range(n):
        if n == 1:
            t = (t_min + t_max) / 2.0
        else:
            t = t_min + (t_max - t_min) * i / (n - 1)

        cx = x1 + ux * t
        cy = y1 + uy * t

        cut = LineString(
            [
                (cx - vx * cut_half, cy - vy * cut_half),
                (cx + vx * cut_half, cy + vy * cut_half),
            ]
        )

        inter = poly.intersection(cut)
        parts = [g for g in lay_cac_line(inter) if g.length > 0]

        if not parts:
            continue

        if prev_mid is None:
            chosen = max(parts, key=lambda g: g.length)
        else:
            chosen = min(
                parts,
                key=lambda g: (g.interpolate(0.5, normalized=True).distance(prev_mid)),
            )

        mid = chosen.interpolate(0.5, normalized=True)

        if prev_mid is None or mid.distance(prev_mid) > 1e-9:
            center_pts.append((mid.x, mid.y))
            prev_mid = mid

    if len(center_pts) < 2:
        return None

    ordered_pts = sap_xep_diem_theo_mst_diameter(center_pts)

    if len(ordered_pts) < 2:
        return None

    line = LineString(ordered_pts)

    tol = max(line.length * 0.001, 0.01)
    line = line.simplify(tol, preserve_topology=False)

    if line.is_empty or line.geom_type != "LineString" or line.length == 0:
        return None

    # Mat cat vuong goc 1 truc MRR chi di het duong "gan thang".
    # Duong chu L: neu truc MRR trung 1 canh L thi mat cat chay doc canh kia,
    # line bo sot ca 1 canh -> lech TRAI/PHAI. Khi line phu kem, thu truc xuong.
    khong_phu = ty_le_khong_phu_truc(poly, line)

    if khong_phu > NGUONG_TRUC_KHONG_PHU:
        try:
            xuong = truc_xuong_tu_polygon(poly)
        except Exception:
            xuong = None

        # chuan_hoa_chieu_line dinh chieu theo 2 dau mut: chi nhan truc xuong
        # di tien doc day cung (L: co; moc/U: khong -> giu line cu, tranh lat ben).
        if (
            xuong is not None
            and ty_le_khong_phu_truc(poly, xuong) <= khong_phu * 0.5
            and do_lui_doc_day_cung(xuong) <= uoc_luong_be_rong_duong(poly)
        ):
            return xuong

    return line


# Ty le dien tich polygon nam ngoai vung 1.5 x be rong quanh reference line.
NGUONG_TRUC_KHONG_PHU = 0.10


def ty_le_khong_phu_truc(poly, line):
    """Ty le dien tich polygon road ma reference line khong di qua."""
    if line is None or line.is_empty or poly.area <= 0:
        return 1.0

    w = uoc_luong_be_rong_duong(poly)

    return float(poly.difference(line.buffer(1.5 * w)).area / poly.area)


def do_lui_doc_day_cung(line):
    """Tong chieu dai line di NGUOC huong day cung (dau mut dau -> dau mut cuoi)."""
    cs = list(line.coords)
    dx = cs[-1][0] - cs[0][0]
    dy = cs[-1][1] - cs[0][1]
    L = math.hypot(dx, dy)

    if L <= 1e-9:
        return float(line.length)

    ux, uy = dx / L, dy / L

    return sum(
        max(0.0, -((b[0] - a[0]) * ux + (b[1] - a[1]) * uy))
        for a, b in zip(cs[:-1], cs[1:])
    )


def truc_xuong_tu_polygon(poly):
    """
    Polygon -> reference line theo truc xuong (medial axis xap xi):
    Voronoi cua diem day tren bien -> giu canh nam trong polygon
    -> duong di dai nhat tren do thi. Khong phu thuoc goc xoay.
    """
    w = uoc_luong_be_rong_duong(poly)
    dense = shapely.segmentize(poly, max(w / 3.0, poly.length / 4000.0))
    pts = shapely.multipoints(shapely.get_coordinates(dense.boundary))
    edges = shapely.get_parts(shapely.voronoi_polygons(pts, only_edges=True))

    adj = {}

    for e in edges:
        if not dense.contains(e):
            continue

        a, b = (tuple(round(v, 6) for v in c) for c in e.coords)
        d = math.dist(a, b)
        adj.setdefault(a, []).append((b, d))
        adj.setdefault(b, []).append((a, d))

    if not adj:
        return None

    def xa_nhat(goc):
        dist = {goc: 0.0}
        par = {goc: None}
        heap = [(0.0, goc)]

        while heap:
            d, u = heapq.heappop(heap)

            if d > dist[u]:
                continue

            for v, w_uv in adj[u]:
                if d + w_uv < dist.get(v, math.inf):
                    dist[v] = d + w_uv
                    par[v] = u
                    heapq.heappush(heap, (d + w_uv, v))

        return max(dist, key=dist.get), par

    a, _ = xa_nhat(next(iter(adj)))
    b, par = xa_nhat(a)

    path = []

    while b is not None:
        path.append(b)
        b = par[b]

    if len(path) < 2:
        return None

    line = LineString(path)
    line = line.simplify(max(line.length * 0.001, 0.01), preserve_topology=False)

    if line.is_empty or line.geom_type != "LineString" or line.length == 0:
        return None

    return line


# ============================================================
# GAN THUA -> MANH ROAD
# ============================================================


def gan_thua_vao_manh(polys, group):
    """
    Moi thua chi gan vao 1 polygon road gan nhat.

    Thua tiep giap duy nhat 1 manh -> gan vao manh do.

    Thua tiep giap >= 2 manh (vd. thua kep giua duong chinh va hem nho
    cung tenDuong, hai dau thua deu cham polygon road) khong duoc chon theo
    khoang cach: hai khoang cach bang nhau va representative point cung
    cach deu, ket qua phu thuoc sai so so hoc nen day thua bi tach doi
    giua hai manh (chan/le xen ke). Cac thua nay duoc gan CHUNG vao manh
    co nhieu thua tiep giap ro rang nhat.
    """
    nguong_cham = 0.05

    def khoang_cach(geom, p_rep):
        d_geom, d_rep = [], []
        for poly in polys:
            try:
                d_geom.append(float(geom.distance(poly)))
            except Exception:
                d_geom.append(float("inf"))
            try:
                d_rep.append(float(p_rep.distance(poly)))
            except Exception:
                d_rep.append(float("inf"))
        return d_geom, d_rep

    thong_tin = {}
    dem_ro_rang = [0] * len(polys)

    for idx, geom in zip(group.index, group.geometry):
        if geom is None or geom.is_empty:
            continue

        try:
            p_rep = geom.representative_point()
        except Exception:
            p_rep = geom.centroid

        d_geom, d_rep = khoang_cach(geom, p_rep)
        ung_vien = [i for i, d in enumerate(d_geom) if d <= nguong_cham]
        if not ung_vien:
            # Only actual/near contacts share the dominant-piece rule. A
            # detached parcel still belongs to its nearest road component.
            ung_vien = [min(range(len(polys)), key=lambda k: (d_geom[k], d_rep[k], k))]

        if len(ung_vien) == 1:
            dem_ro_rang[ung_vien[0]] += 1

        thong_tin[idx] = (ung_vien, d_geom, d_rep)

    gan_manh = {}
    thua_theo_manh = {i: [] for i in range(len(polys))}
    dem_thua = [0] * len(polys)

    for idx, (ung_vien, d_geom, d_rep) in thong_tin.items():
        i = min(
            ung_vien,
            key=lambda k: (
                -dem_ro_rang[k],
                -float(polys[k].area),
                d_geom[k],
                d_rep[k],
                k,
            ),
        )

        gan_manh[idx] = i
        dem_thua[i] += 1
        thua_theo_manh[i].append(idx)

    return gan_manh, thua_theo_manh, dem_thua


# ============================================================
# 4 HUONG
# ============================================================


def goc_truc_tu_hai_diem(p1, p2):
    dx = p2.x - p1.x
    dy = p2.y - p1.y

    if math.hypot(dx, dy) <= 1e-12:
        return None

    return math.degrees(math.atan2(dy, dx)) % 180.0


def hai_diem_xa_nhat(points):
    pts = [p for p in points if p is not None and not p.is_empty]

    if len(pts) < 2:
        return None, None

    best = None

    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d2 = (pts[i].x - pts[j].x) ** 2 + (pts[i].y - pts[j].y) ** 2

            if best is None or d2 > best[0]:
                best = (d2, pts[i], pts[j])

    return best[1], best[2]


def diem_xa_nhat_tren_tim(lines):
    """
    2 dinh xa nhau nhat cua cac doan tim (chi xet dinh bao loi cho nhanh).
    """
    coords = []

    for line in lines:
        if line is None or line.is_empty:
            continue

        coords.extend(line.coords)

    if len(coords) < 2:
        return []

    hull = MultiPoint(coords).convex_hull

    if hull.geom_type == "Polygon":
        return [Point(c) for c in hull.exterior.coords[:-1]]

    return [Point(c) for c in hull.coords]


def xac_dinh_huong(group, lines, theo_tim=False):
    """
    Uu tien huong tong quat tu 2 diem thua xa nhau nhat.
    Tuyen nhap tim duong: lay theo 2 dinh xa nhat cua chinh tim duong,
    vi thua lon/lech mot ben co the keo nghieng truc qua nguong 4 huong.
    Neu khong du diem thi fallback ve reference line dai nhat.
    """
    points = []

    if theo_tim:
        points = diem_xa_nhat_tren_tim(lines)

    if len(points) < 2:
        points = []

        for geom in group.geometry:
            if geom is None or geom.is_empty:
                continue

            try:
                points.append(geom.representative_point())
            except Exception:
                points.append(geom.centroid)

    p1, p2 = hai_diem_xa_nhat(points)
    goc = None

    if p1 is not None and p2 is not None:
        goc = goc_truc_tu_hai_diem(p1, p2)

    if goc is None:
        line = max(lines, key=lambda l: l.length)
        cs = list(line.coords)
        goc = goc_truc_tu_hai_diem(
            Point(cs[0]),
            Point(cs[-1]),
        )

    if goc is None:
        raise ValueError("Khong xac dinh duoc huong tuyen.")

    if goc < 22.5 or goc >= 157.5:
        huong = "D-T"

    elif goc < 67.5:
        huong = "DB-TN"

    elif goc < 112.5:
        huong = "B-N"

    else:
        huong = "DN-TB"

    return huong, float(goc)


def diem_so_huong(point, huong):
    """
    Score cang lon = cang gan DIEM DAU cua huong danh so.
    """
    x = point.x
    y = point.y

    if huong == "D-T":
        return x

    if huong == "B-N":
        return y

    if huong == "DB-TN":
        return x + y

    if huong == "DN-TB":
        return x - y

    raise ValueError(f"Huong khong hop le: {huong}")


def vector_huong_danh_so(huong):
    """
    Vector CHIEU DI danh so theo 4 quy uoc.

    B-N   : Bac  -> Nam       = ( 0, -1)
    D-T   : Dong -> Tay       = (-1,  0)
    DB-TN : Dong Bac -> Tay Nam = (-1, -1)
    DN-TB : Dong Nam -> Tay Bac = (-1,  1)

    Vector chi dung de:
    - ep tangent cuc bo cung CHIEU di;
    - khong dung de ve geometry.
    """
    if huong == "B-N":
        return 0.0, -1.0

    if huong == "D-T":
        return -1.0, 0.0

    if huong == "DB-TN":
        s = math.sqrt(2.0)
        return -1.0 / s, -1.0 / s

    if huong == "DN-TB":
        s = math.sqrt(2.0)
        return -1.0 / s, 1.0 / s

    raise ValueError(f"Huong khong hop le: {huong}")


def chuan_hoa_tangent_theo_huong(dx, dy, huong):
    """
    Chuan hoa tangent de TRAI/PHAI khong bi lat dau giua cac component.

    Reference line cua moi polygon component co the co thu tu vertex nguoc nhau.
    Neu dung truc tiep tangent cua line, cross-product se lat dau:
        cung mot ben vat ly
        -> doan nay TRAI
        -> doan sau PHAI

    Ket qua khong phu thuoc vao chieu vertex cua tung component.

    Neu tangent dang nguoc voi CHIEU DANH SO quy uoc -> dao tangent.
    Sau ham nay, cross-product cua moi component deu duoc tinh theo cung
    mot huong B-N / D-T / DB-TN / DN-TB.
    """
    do = math.hypot(dx, dy)

    if do <= 1e-12:
        return vector_huong_danh_so(huong)

    hx, hy = vector_huong_danh_so(huong)

    dot = dx * hx + dy * hy

    if dot < 0:
        dx = -dx
        dy = -dy
        dot = -dot

    return dx, dy


def dao_line(line):
    return LineString(list(line.coords)[::-1])


def chuan_hoa_chieu_line(line, huong):
    cs = list(line.coords)

    p_dau = Point(cs[0])
    p_cuoi = Point(cs[-1])

    # Diem dau phai co score lon hon.
    if diem_so_huong(p_dau, huong) < diem_so_huong(p_cuoi, huong):
        return dao_line(line)

    return line


def uoc_luong_be_rong_duong(poly):
    """
    Uoc luong be rong polygon duong.

    Voi polygon dai va hep:
        2 * area / perimeter ~ be rong.

    Chi dung de tao nguong noi qua giao lo, khong dung de danh so.
    """
    if poly is None or poly.is_empty or poly.length <= 0:
        return 5.0

    w = 2.0 * float(poly.area) / float(poly.length)

    return max(1.0, w)


def tao_do_thi_manh_duong(polys):
    """
    Tao graph lien ket CAC POLYGON ROAD.

    Hai manh duoc coi la cung cum lien tuc neu khoang cach polygon <=
    nguong noi tu dong.

    Muc tieu:
    - gap nho do nga 3/nga 4: VAN la cung cum;
    - gap rat lon (vd H9 tung thay ~802m): KHONG ep thanh 1 route.

    Tra ve:
        adj, nguong_noi, bang_khoang_cach
    """
    if not polys:
        return {}, 25.0, {}

    be_rong = sorted(
        uoc_luong_be_rong_duong(p) for p in polys if p is not None and not p.is_empty
    )

    if be_rong:
        trung_vi = be_rong[len(be_rong) // 2]
    else:
        trung_vi = 5.0

    # Qua giao lo co the bi cat boi polygon duong khac.
    # Cho phep gap bang nhieu lan be rong, nhung gioi han de khong noi xa.
    nguong_noi = max(
        25.0,
        min(80.0, trung_vi * 5.0),
    )

    adj = {i: [] for i in range(len(polys))}
    bang_kc = {}

    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            try:
                d = float(polys[i].distance(polys[j]))
            except Exception:
                d = float("inf")

            bang_kc[(i, j)] = d
            bang_kc[(j, i)] = d

            if d <= nguong_noi:
                adj[i].append(j)
                adj[j].append(i)

    return adj, float(nguong_noi), bang_kc


def tim_cac_cum_manh(adj):
    """Connected components cua graph polygon road."""
    da_xem = set()
    cac_cum = []

    for start in sorted(adj.keys()):
        if start in da_xem:
            continue

        stack = [start]
        da_xem.add(start)
        cum = []

        while stack:
            u = stack.pop()
            cum.append(u)

            for v in adj.get(u, []):
                if v not in da_xem:
                    da_xem.add(v)
                    stack.append(v)

        cac_cum.append(sorted(cum))

    return cac_cum


def sap_xep_manh_trong_cum(
    manh_ids,
    adj,
    lines_theo_manh,
    huong,
    bang_kc,
):
    """
    Sap thu tu polygon component TRONG MOT CUM GAN NHAU.

    Nguyen tac sap component trong mot cum lien tuc:
    - khong noi endpoint tren toan tuyen neu cac manh cach qua xa;
    - khong sort midpoint toan bo neu co the chen manh xa vao giua 2 manh
      dang lien tuc qua giao lo.

    Chi noi logic TRONG CUNG connected-component polygon.

    Neu graph trong cum la chuoi:
        degree <= 2
    thi traverse dung topology polygon.

    Neu co nhanh:
        dung greedy CHI tren canh graph gan, khong nhay ra ngoai cum.
        Log CANH_BAO de de kiem tra.
    """
    nodes = [i for i in manh_ids if i in lines_theo_manh]

    if not nodes:
        return [], False

    if len(nodes) == 1:
        i = nodes[0]
        line = chuan_hoa_chieu_line(
            lines_theo_manh[i],
            huong,
        )

        return [
            {
                "manh": i,
                "line": line,
                "khoangHoTruoc": 0.0,
            }
        ], False

    tap = set(nodes)

    bac = {i: len([j for j in adj.get(i, []) if j in tap]) for i in nodes}

    co_nhanh = any(v > 2 for v in bac.values())

    # --------------------------------------------------------
    # Chon START component.
    # Neu graph la chain, uu tien endpoint graph.
    # --------------------------------------------------------
    dau_mut = [i for i in nodes if bac[i] <= 1]

    ung_vien_dau = dau_mut if dau_mut else nodes

    def score_manh(i):
        line = lines_theo_manh[i]
        p = line.interpolate(0.5, normalized=True)
        return float(diem_so_huong(p, huong))

    start = max(
        ung_vien_dau,
        key=score_manh,
    )

    # --------------------------------------------------------
    # Traverse topology.
    # Chain: di tu dau nay sang dau kia.
    # Branch: greedy theo neighbor gan, nhung KHONG nhay qua component xa.
    # --------------------------------------------------------
    thu_tu = []
    da_dung = set()
    hien_tai = start
    truoc = None

    while hien_tai is not None:
        thu_tu.append(hien_tai)
        da_dung.add(hien_tai)

        neighbors = [j for j in adj.get(hien_tai, []) if j in tap and j not in da_dung]

        if not neighbors:
            # Neu branch traversal bo sot node trong cung,
            # chon node CHUA DUNG co khoang polygon gan nhat voi tap da dung.
            con_lai = [j for j in nodes if j not in da_dung]

            if not con_lai:
                break

            ung_vien = []

            for j in con_lai:
                d = min(bang_kc.get((j, u), float("inf")) for u in da_dung)
                ung_vien.append(
                    (
                        d,
                        -score_manh(j),
                        j,
                    )
                )

            d, _, nxt = min(
                ung_vien,
                key=lambda z: (z[0], z[1], z[2]),
            )

            # Vẫn trong cùng connected-component nên tồn tại đường graph,
            # nhưng có thể phải đi qua branch node đã dùng.
            hien_tai = nxt
            truoc = None
            continue

        if len(neighbors) == 1:
            nxt = neighbors[0]
        else:
            # Nhanh: uu tien canh polygon ngan nhat,
            # sau do moi den score huong.
            nxt = min(
                neighbors,
                key=lambda j: (
                    bang_kc.get(
                        (hien_tai, j),
                        float("inf"),
                    ),
                    -score_manh(j),
                    j,
                ),
            )

        truoc = hien_tai
        hien_tai = nxt

    # --------------------------------------------------------
    # Orient line lien tuc theo END -> START,
    # NHUNG chi trong cum da duoc chung minh gan nhau.
    # --------------------------------------------------------
    ket_qua = []

    for k, manh_idx in enumerate(thu_tu):
        line = lines_theo_manh[manh_idx]

        if k == 0:
            line = chuan_hoa_chieu_line(
                line,
                huong,
            )
            gap = 0.0

        else:
            line_truoc = ket_qua[-1]["line"]
            p_cuoi = Point(list(line_truoc.coords)[-1])

            cs = list(line.coords)
            p0 = Point(cs[0])
            p1 = Point(cs[-1])

            d0 = float(p_cuoi.distance(p0))
            d1 = float(p_cuoi.distance(p1))

            if d0 <= d1:
                gap = d0
            else:
                line = dao_line(line)
                gap = d1

        ket_qua.append(
            {
                "manh": manh_idx,
                "line": line,
                "khoangHoTruoc": float(gap),
            }
        )

    return ket_qua, co_nhanh


def tao_cac_cum_danh_so(
    polys,
    manh_co_thua,
    lines_theo_manh,
    huong,
):
    """
    Chia 1 tenDuong thanh cac CUM LIEN TUC ve geometry.

    Moi cum:
    - co the gom nhieu polygon bi cat boi giao lo;
    - danh so LIEN TUC xuyen cac polygon trong cum;
    - cum tach roi qua xa -> RESET 1/2, khong ep lien tuc.

    Tra ve:
        cac_cum_danh_so, nguong_noi
    """
    adj, nguong_noi, bang_kc = tao_do_thi_manh_duong(polys)
    cac_cum_all = tim_cac_cum_manh(adj)

    tap_co_thua = set(manh_co_thua)

    # Chi giu connected-component co it nhat 1 polygon co thua.
    cac_cum_co_thua = [cum for cum in cac_cum_all if any(i in tap_co_thua for i in cum)]

    ket_qua = []

    for cum_id, cum in enumerate(cac_cum_co_thua, start=1):
        # Chi cac manh co reference line moi tham gia route.
        # Manh khong co thua van co the nam trong graph de tao connectivity,
        # nhung khong bat buoc phai co line.
        manh_route = [i for i in cum if i in lines_theo_manh]

        if not manh_route:
            continue

        thu_tu, co_nhanh = sap_xep_manh_trong_cum(
            manh_route,
            adj,
            lines_theo_manh,
            huong,
            bang_kc,
        )

        if not thu_tu:
            continue

        # Chỉ cần cum nào chứa house component.
        if not any(item["manh"] in tap_co_thua for item in thu_tu):
            continue

        # score cum chi dung de debug/sap cum cho de nhin.
        p0 = thu_tu[0]["line"].interpolate(
            0.5,
            normalized=True,
        )

        ket_qua.append(
            {
                "cum": cum_id,
                "thuTu": thu_tu,
                "coNhanh": bool(co_nhanh),
                "score": float(
                    diem_so_huong(
                        p0,
                        huong,
                    )
                ),
            }
        )

    # Cum nao gan diem dau quy uoc hon in/debug truoc.
    # NUMBERING RESET theo cum nen thu tu cac cum khong anh huong so.
    ket_qua.sort(
        key=lambda z: z["score"],
        reverse=True,
    )

    # Danh lai cum 1..N sau sort.
    for i, cum in enumerate(ket_qua, start=1):
        cum["cum"] = i

    return ket_qua, nguong_noi


def sap_thu_tu_cac_manh(lines_theo_manh, huong):
    """
    KHONG noi geometry.
    Chi sap thu tu cac reference line theo vi tri khong gian cua midpoint.
    """
    items = []

    for manh_idx, line in lines_theo_manh.items():
        p_giua = line.interpolate(0.5, normalized=True)
        score = diem_so_huong(p_giua, huong)

        items.append(
            {
                "manh": manh_idx,
                "line": line,
                "score": float(score),
            }
        )

    # Score lon -> gan diem dau hon.
    items.sort(key=lambda z: z["score"], reverse=True)

    return items


# ============================================================
# THU TU DAY THUA TRUC TIEP TU DIEM MAT DUONG
# ============================================================


def _mst_tu_diem(diem_theo_id):
    """
    Tao Minimum Spanning Tree Euclid cho cac diem.

    diem_theo_id: {id: Point}

    Tra ve:
        adj: {id: [(id2, khoang_cach), ...]}
        edges: [(do_dai, id1, id2), ...]

    MST chi dung de phat hien cau truc/gap lon cua day diem mat duong,
    thay vi doan topology cac polygon road.
    """
    ids = list(diem_theo_id.keys())

    if not ids:
        return {}, []

    adj = {i: [] for i in ids}

    if len(ids) == 1:
        return adj, []

    in_tree = {i: False for i in ids}
    best = {i: float("inf") for i in ids}
    parent = {i: None for i in ids}

    start = ids[0]
    best[start] = 0.0

    for _ in range(len(ids)):
        u = min(
            (i for i in ids if not in_tree[i]),
            key=lambda i: best[i],
            default=None,
        )

        if u is None:
            break

        in_tree[u] = True
        pu = diem_theo_id[u]

        for v in ids:
            if in_tree[v]:
                continue

            d = float(pu.distance(diem_theo_id[v]))

            if d < best[v]:
                best[v] = d
                parent[v] = u

    edges = []

    for v in ids:
        u = parent[v]

        if u is None:
            continue

        d = float(diem_theo_id[u].distance(diem_theo_id[v]))

        adj[u].append((v, d))
        adj[v].append((u, d))
        edges.append((d, u, v))

    return adj, edges


def _nguong_tach_cum_tu_mst(edges):
    """
    Tim nguong tach cum tu do dai canh MST.

    Muc tieu:
    - gap giao lo 20-60m: KHONG tach;
    - gap rat lon hang tram met: tach cum va reset 1/2.

    Khong dung polygon road de tach cum nua.
    """
    if not edges:
        return float("inf")

    ds = sorted(float(e[0]) for e in edges)
    n = len(ds)

    if n % 2 == 1:
        trung_vi = ds[n // 2]
    else:
        trung_vi = (ds[n // 2 - 1] + ds[n // 2]) / 2.0

    # Floor 120m de giao lo rong van nam cung cum.
    # Median*8 de tu thich nghi mat do thua.
    # Cap 450m de gap ~800m chac chan bi tach.
    return max(120.0, min(450.0, trung_vi * 8.0))


def _cac_cum_sau_khi_cat_mst(adj, edges, nguong):
    """Cat cac canh MST qua dai roi lay connected components."""
    adj_cat = {i: [] for i in adj}

    for d, u, v in edges:
        if d <= nguong:
            adj_cat[u].append((v, d))
            adj_cat[v].append((u, d))

    da_xem = set()
    cac_cum = []

    for start in adj_cat:
        if start in da_xem:
            continue

        stack = [start]
        da_xem.add(start)
        comp = []

        while stack:
            u = stack.pop()
            comp.append(u)

            for v, _ in adj_cat[u]:
                if v not in da_xem:
                    da_xem.add(v)
                    stack.append(v)

        cac_cum.append(comp)

    return cac_cum, adj_cat


def la_che_do_tim(group):
    """Nhom thua duoc do theo tim duong (polyline), khong theo polygon mat duong."""
    return "_cachChieu" in group.columns and bool((group["_cachChieu"] == "TIM_DUONG").all())


def chia_cum_thua_theo_mat_duong(group):
    """
    Chia cum bang CHINH diem mat duong cua cac thua.

    Nguyen tac tach cum:
    - khong con dung khoang cach polygon component de quyet dinh reset;
    - giao lo chi tao mot khoang trong nho -> van cung cum;
    - cum that su xa hang tram met -> tach.

    Yeu cau group da co _xMatDuong / _yMatDuong.

    Tra ve:
        map_index_to_cum, nguong, cac_canh_bi_cat
    """
    diem = {}

    for idx, row in group.iterrows():
        x = row.get("_xMatDuong")
        y = row.get("_yMatDuong")

        if pd.isna(x) or pd.isna(y):
            continue

        diem[idx] = Point(float(x), float(y))

    if not diem:
        return {}, float("inf"), []

    adj, edges = _mst_tu_diem(diem)
    nguong = _nguong_tach_cum_tu_mst(edges)
    cac_cum, _ = _cac_cum_sau_khi_cat_mst(adj, edges, nguong)

    # Sap cum theo huong tong quat chi de ID on dinh/de doc log.
    # Numbering reset theo cum, nen ID cum khong lam doi logic trong cum.
    def score_cum(comp):
        return max(diem_so_huong(diem[idx], group.loc[idx, COL_HUONG]) for idx in comp)

    cac_cum.sort(key=score_cum, reverse=True)

    # Cac cum cung nam chu yeu tren MOT reference line: doi cho voi nhau theo
    # chainage (cung chieu thu tu trong cum), giu nguyen vi tri so voi cum
    # cua manh khac. Huong tong quat sai voi tuyen uon chu U.
    def vi_tri_doc_tuyen(comp):
        manh = group.loc[comp, "_manhDuong"].dropna()
        if manh.empty:
            return None, None
        chinh = manh.mode().iloc[0]
        do = group.loc[comp][group.loc[comp, "_manhDuong"] == chinh]["_measure"].dropna()
        return chinh, (float(do.median()) if len(do) else None)

    if len(cac_cum) > 1 and la_che_do_tim(group):
        vi_tri = [vi_tri_doc_tuyen(comp) for comp in cac_cum]
        theo_manh = {}
        for i, (manh, do) in enumerate(vi_tri):
            if manh is not None and do is not None:
                theo_manh.setdefault(manh, []).append(i)
        moi = list(cac_cum)
        for slots in theo_manh.values():
            for slot, i in zip(slots, sorted(slots, key=lambda k: vi_tri[k][1])):
                moi[slot] = cac_cum[i]
        cac_cum = moi

    mapping = {}

    for cum_id, comp in enumerate(cac_cum, start=1):
        for idx in comp:
            mapping[idx] = cum_id

    cat = [(float(d), u, v) for d, u, v in edges if d > nguong]

    return mapping, float(nguong), cat


def _trung_vi_so(ds):
    ds = sorted(float(v) for v in ds)

    if not ds:
        return float("-inf")

    n = len(ds)

    if n % 2 == 1:
        return ds[n // 2]

    return (ds[n // 2 - 1] + ds[n // 2]) / 2.0


def thu_tu_thua_theo_reference_line(nhom, huong):
    """
    SAP THU TU NHA KHONG DUNG MST TREE-DISTANCE.

    MST van duoc giu o ham chia_cum_thua_theo_mat_duong()
    de tim GAP LON va tach cum.

    Con THU TU SO NHA thi bat buoc bam vao chainage reference line:

    1. Nhom thua theo _manhDuong.
    2. Moi component da duoc orient theo huong chung.
    3. Trong component:
           sort _measure tang dan.
       -> khong the co 7 -> 11 -> 9 neu 9 nam truoc 11 tren line.
    4. Giua cac component TRONG CUNG CUM:
       dung diem mat duong cua CHINH cac thua de xep component theo 4 huong.
       Khong greedy endpoint, khong MST tree-distance.

    Tra ve:
        ordered_indices,
        thong_tin_component
    """
    if len(nhom) <= 1:
        return list(nhom.index), []

    hop_le = nhom[
        nhom["_manhDuong"].notna()
        & nhom["_measure"].notna()
        & nhom["_xMatDuong"].notna()
        & nhom["_yMatDuong"].notna()
    ].copy()

    thieu = [idx for idx in nhom.index if idx not in hop_le.index]

    if len(hop_le) == 0:
        return list(nhom.index), []

    thong_tin = []

    for manh_value, sub in hop_le.groupby("_manhDuong"):
        manh_idx = int(manh_value)
        sub = sub.copy()

        score_theo_idx = {}

        for idx, row in sub.iterrows():
            p = Point(
                float(row["_xMatDuong"]),
                float(row["_yMatDuong"]),
            )

            score_theo_idx[idx] = float(
                diem_so_huong(
                    p,
                    huong,
                )
            )

        sub["_scoreHuongTmp"] = [score_theo_idx[idx] for idx in sub.index]

        sub["_idxTmp"] = sub.index

        # QUAN TRONG:
        # Trong CUNG component, _measure la chainage chinh.
        sub = sub.sort_values(
            [
                "_measure",
                "_scoreHuongTmp",
                "_dist_line",
                "_idxTmp",
            ],
            ascending=[True, False, True, True],
        )

        idx_order = list(sub.index)

        # Xep CAC COMPONENT bang day nha that, khong bang midpoint polygon.
        k = min(3, len(idx_order))

        score_dau = _trung_vi_so(score_theo_idx[idx] for idx in idx_order[:k])

        score_giua = _trung_vi_so(score_theo_idx.values())

        score_cuoi = _trung_vi_so(score_theo_idx[idx] for idx in idx_order[-k:])

        thong_tin.append(
            {
                "manh": manh_idx,
                "idx_order": idx_order,
                "scoreDau": float(score_dau),
                "scoreGiua": float(score_giua),
                "scoreCuoi": float(score_cuoi),
                "soThua": len(idx_order),
            }
        )

    # Gan DIEM DAU quy uoc hon -> component dung truoc.
    thong_tin.sort(
        key=lambda z: (
            z["scoreDau"],
            z["scoreGiua"],
            z["scoreCuoi"],
            -z["manh"],
        ),
        reverse=True,
    )

    ordered = []

    for item in thong_tin:
        ordered.extend(item["idx_order"])

    # Khong bo record neu thieu du lieu.
    ordered.extend(thieu)

    return ordered, thong_tin


def vi_tri_diem_tren_bien_duong(poly, p_road):
    """
    Tra ve vi tri chainage cua p_road tren vong bien polygon duong.

    p_road duoc tao tu nearest_points(..., poly.boundary), nen ve ly thuyet
    no nam tren mot trong cac ring cua polygon.

    Tra ve:
        vi_tri_bien, chu_vi_vong, ma_vong

    ma_vong:
        0  = exterior
        1+ = interior ring (neu co)
    """
    if poly is None or poly.is_empty or p_road is None or p_road.is_empty:
        return float("nan"), float("nan"), -1

    rings = []

    try:
        rings.append(LineString(poly.exterior.coords))
    except Exception:
        pass

    try:
        for ring in poly.interiors:
            rings.append(LineString(ring.coords))
    except Exception:
        pass

    if not rings:
        return float("nan"), float("nan"), -1

    ung_vien = []

    for ma_vong, ring in enumerate(rings):
        L = float(ring.length)
        if L <= 1e-12:
            continue

        try:
            s = float(ring.project(p_road))
            q = ring.interpolate(s)
            d = float(q.distance(p_road))
        except Exception:
            continue

        ung_vien.append((d, s, L, ma_vong))

    if not ung_vien:
        return float("nan"), float("nan"), -1

    _, s, L, ma_vong = min(
        ung_vien,
        key=lambda z: (z[0], z[3]),
    )

    return float(s), float(L), int(ma_vong)


def vi_tri_lech_phu_tren_bien(poly, ma_vong, geom, vi_tri_bien, chu_vi_vong):
    """
    Do lech (m, co dau) doc bien duong cua THAN thua so voi diem mat duong.

    Hai thua ke nhau co the cung cham 1 dinh cua bien duong (p_road trung
    nhau, vi_tri_bien bang nhau). Khi do thu tu chi con lai id nen bi dao
    ngau nhien; do lech nay dung lam khoa phu phan biet chung.
    """
    try:
        rings = [poly.exterior] + list(poly.interiors)
        ring = LineString(rings[ma_vong].coords)
        s2 = float(ring.project(geom.centroid))
    except Exception:
        return 0.0

    if not chu_vi_vong or chu_vi_vong <= 0:
        return 0.0

    return ((s2 - vi_tri_bien + chu_vi_vong / 2.0) % chu_vi_vong) - chu_vi_vong / 2.0


def _score_thu_tu_frontage(row, huong):
    """Use the ordering frontage point without moving the side-classification point."""
    score = row.get("_scoreThuTu")
    if score is not None and not pd.isna(score):
        return float(score)
    return float(
        diem_so_huong(Point(float(row["_xMatDuong"]), float(row["_yMatDuong"])), huong)
    )


def _sap_xep_vong_bien(sub, huong):
    """
    Sap thua tren CUNG polygon component + CUNG ring boundary.

    Ring la duong KIN, vi tri 0 cua ring chi la diem bat ky do du lieu luu.
    Neu sort truc tiep _viTriBien se co the bi vo tai diem wrap 0/L.

    Cach xu ly:
    1. sort vi tri s tren [0, L)
    2. tim GAP LON NHAT tren vong
    3. cat vong tai gap do -> tao day tuyen tinh
    4. chon forward/reverse sao cho dau day gan DIEM DAU quy uoc hon
       theo B-N / D-T / DB-TN / DN-TB.
    """
    if len(sub) <= 1:
        return list(sub.index), {
            "gapCat": 0.0,
            "daoChieu": False,
        }

    rows = []

    for idx, row in sub.iterrows():
        s = row.get("_viTriBien")
        L = row.get("_chuViBien")
        x = row.get("_xMatDuong")
        y = row.get("_yMatDuong")
        s_phu = row.get("_lechBien")
        s_phu = 0.0 if s_phu is None or pd.isna(s_phu) else float(s_phu)

        if pd.isna(s) or pd.isna(L) or pd.isna(x) or pd.isna(y):
            continue

        rows.append(
            {
                "idx": idx,
                "s": float(s),
                "sPhu": s_phu,
                "L": float(L),
                "score": _score_thu_tu_frontage(row, huong),
            }
        )

    if len(rows) <= 1:
        hop_le = [r["idx"] for r in rows]
        thieu = [idx for idx in sub.index if idx not in hop_le]
        return hop_le + thieu, {
            "gapCat": 0.0,
            "daoChieu": False,
        }

    # Cung ring nen chu vi phai gan nhau. Median de on dinh sai so nho.
    Ls = sorted(r["L"] for r in rows)
    nL = len(Ls)
    L = Ls[nL // 2] if nL % 2 else (Ls[nL // 2 - 1] + Ls[nL // 2]) / 2.0

    if L <= 1e-12:
        # Fallback cuoi cung ve _measure neu ring hong.
        tmp = sub.copy()
        tmp["_idxTmp"] = tmp.index
        tmp = tmp.sort_values(
            ["_measure", "_dist_line", "_idxTmp"],
            ascending=[True, True, True],
        )
        return list(tmp.index), {
            "gapCat": 0.0,
            "daoChieu": False,
        }

    rows.sort(key=lambda r: (round(r["s"], 3), r["sPhu"], r["idx"]))

    # Tim gap giua s[i] -> s[i+1], ke ca wrap last -> first+L.
    gaps = []
    n = len(rows)

    for i in range(n - 1):
        gaps.append((rows[i + 1]["s"] - rows[i]["s"], i))

    gap_wrap = rows[0]["s"] + L - rows[-1]["s"]
    gaps.append((gap_wrap, n - 1))

    gap_max, i_gap = max(
        gaps,
        key=lambda z: (z[0], -z[1]),
    )

    # Bat dau SAU gap lon nhat.
    bat_dau = (i_gap + 1) % n
    ordered_rows = rows[bat_dau:] + rows[:bat_dau]

    # Chon chieu toan day. Dung median 1..3 diem dau/cuoi de tranh 1 diem le.
    # k <= n//2 de nhom dau/cuoi khong trung nhau; voi n <= 3 neu k = n thi
    # hai median bang nhau va khong bao gio dao chieu.
    k = min(3, max(1, len(ordered_rows) // 2))
    score_dau = _trung_vi_so(r["score"] for r in ordered_rows[:k])
    score_cuoi = _trung_vi_so(r["score"] for r in ordered_rows[-k:])

    if math.isclose(score_dau, score_cuoi, rel_tol=0, abs_tol=1e-7):
        # Two parcels can share exactly the same access vertex. The offset
        # sorts along the ring but cannot choose the route direction by itself.
        def body_score(item):
            geom = sub.loc[item["idx"], "geometry"]
            if geom is None or geom.is_empty:
                return item["score"]
            return diem_so_huong(geom.representative_point(), huong)

        score_dau = _trung_vi_so(body_score(r) for r in ordered_rows[:k])
        score_cuoi = _trung_vi_so(body_score(r) for r in ordered_rows[-k:])

    dao = False

    # score lon = gan diem dau quy uoc hon.
    if score_dau < score_cuoi:
        ordered_rows.reverse()
        dao = True

    ordered = [r["idx"] for r in ordered_rows]
    thieu = [idx for idx in sub.index if idx not in ordered]
    ordered.extend(thieu)

    return ordered, {
        "gapCat": float(gap_max),
        "daoChieu": bool(dao),
    }


def thu_tu_thua_theo_bien_duong(nhom, huong):
    """
    THU TU DANH SO DUA TREN BIEN MAT DUONG.

    Khong dung _measure projection lam khoa chinh nua.

    Trong tung manh road:
        p_road -> chainage tren boundary ring -> unwrap ring -> chon chieu.

    Giua cac manh road trong CUNG cum thua:
        sap cac block bang vi tri dau cua CHINH day frontage theo 4 huong.

    _measure chi con la debug/fallback, khong quyet dinh 9 truoc 11 nua.
    """
    if len(nhom) <= 1:
        return list(nhom.index), []

    hop_le = nhom[
        nhom["_manhDuong"].notna()
        & nhom["_xMatDuong"].notna()
        & nhom["_yMatDuong"].notna()
    ].copy()

    thieu = [idx for idx in nhom.index if idx not in hop_le.index]

    if len(hop_le) == 0:
        return list(nhom.index), []

    thong_tin = []

    # Tach them theo ring de phong polygon co hole.
    for (manh_value, vong_value), sub in hop_le.groupby(
        ["_manhDuong", "_vongBien"],
        dropna=False,
    ):
        manh_idx = int(manh_value)
        vong_idx = -1 if pd.isna(vong_value) else int(vong_value)
        sub = sub.copy()

        idx_order, meta = _sap_xep_vong_bien(sub, huong)

        # Score block bang 1-3 diem dau/cuoi SAU khi da co thu tu frontage.
        score_theo_idx = {}

        for idx, row in sub.iterrows():
            score_theo_idx[idx] = _score_thu_tu_frontage(row, huong)

        idx_hop_le = [idx for idx in idx_order if idx in score_theo_idx]

        if idx_hop_le:
            k = min(3, len(idx_hop_le))
            score_dau = _trung_vi_so(score_theo_idx[idx] for idx in idx_hop_le[:k])
            score_giua = _trung_vi_so(score_theo_idx.values())
            score_cuoi = _trung_vi_so(score_theo_idx[idx] for idx in idx_hop_le[-k:])
        else:
            score_dau = score_giua = score_cuoi = float("-inf")

        thong_tin.append(
            {
                "manh": manh_idx,
                "vong": vong_idx,
                "idx_order": idx_order,
                "scoreDau": float(score_dau),
                "scoreGiua": float(score_giua),
                "scoreCuoi": float(score_cuoi),
                "soThua": len(idx_order),
                "gapCat": float(meta.get("gapCat", 0.0)),
                "daoChieu": bool(meta.get("daoChieu", False)),
            }
        )

    # Block gan diem dau quy uoc hon dung truoc.
    thong_tin.sort(
        key=lambda z: (
            z["scoreDau"],
            z["scoreGiua"],
            z["scoreCuoi"],
            -z["manh"],
            -z["vong"],
        ),
        reverse=True,
    )

    ordered = []
    da_co = set()

    for item in thong_tin:
        for idx in item["idx_order"]:
            if idx not in da_co:
                ordered.append(idx)
                da_co.add(idx)

    for idx in thieu:
        if idx not in da_co:
            ordered.append(idx)
            da_co.add(idx)

    return ordered, thong_tin


def tangent_bien_duong(poly, p_road, tangent_tham_chieu=None):
    """
    Lay tangent tai BIEN POLYGON DUONG gan p_road.

    Vector phan loai ben:
        tangent bien duong x (diem trong thua - p_road)

    Tangent bien duong bam dung mat duong thuc te hon tangent centerline khi
    reference line bi lech o giao lo/cua gap.

    tangent_tham_chieu chi dung de quyet dinh chieu +/- cua tangent bien.
    """
    if poly is None or poly.is_empty or p_road is None or p_road.is_empty:
        return tangent_tham_chieu if tangent_tham_chieu else (0.0, 0.0)

    try:
        ring = LineString(poly.exterior.coords)
    except Exception:
        return tangent_tham_chieu if tangent_tham_chieu else (0.0, 0.0)

    L = float(ring.length)

    if L <= 0:
        return tangent_tham_chieu if tangent_tham_chieu else (0.0, 0.0)

    m = float(ring.project(p_road))
    cua_so = max(
        1.0,
        min(
            8.0,
            uoc_luong_be_rong_duong(poly) * 0.8,
        ),
    )

    def noi_suy_vong(s):
        return ring.interpolate(s % L)

    p1 = noi_suy_vong(m - cua_so)
    p2 = noi_suy_vong(m + cua_so)

    dx = p2.x - p1.x
    dy = p2.y - p1.y

    if math.hypot(dx, dy) <= 1e-12:
        return tangent_tham_chieu if tangent_tham_chieu else (0.0, 0.0)

    if tangent_tham_chieu:
        tx, ty = tangent_tham_chieu

        if math.hypot(tx, ty) > 1e-12 and dx * tx + dy * ty < 0:
            dx = -dx
            dy = -dy

    return dx, dy


# ============================================================
# ACCESS POINT / MEASURE / TRAI PHAI
# ============================================================


def _cos_song_song(dx1, dy1, dx2, dy2):
    """|cos(goc)| giua 2 vector. 1=song song, 0=vuong goc."""
    n1 = math.hypot(dx1, dy1)
    n2 = math.hypot(dx2, dy2)

    if n1 <= 1e-12 or n2 <= 1e-12:
        return 0.0

    return abs((dx1 * dx2 + dy1 * dy2) / (n1 * n2))


def _tangent_reference_tai_diem(line, p):
    """
    Tangent reference-line gan 1 diem boundary road.
    Khong quan tam dau +/- khi kiem tra song song.
    """
    if (
        line is None
        or line.is_empty
        or line.geom_type != "LineString"
        or line.length <= 0
        or p is None
        or p.is_empty
    ):
        return 0.0, 0.0

    try:
        m = float(line.project(p))
        return tangent_cuc_bo_on_dinh(line, m)
    except Exception:
        return 0.0, 0.0


MAT_TIEN_DAI_MIN = 30.0
MAT_TIEN_DAI_THANG_MIN = 0.85


def diem_giua_mat_tien_dai(geom, poly):
    """
    Diem giua doan mat tien THANG va DAI (>= MAT_TIEN_DAI_MIN m) cua thua.

    Thua lon sat bien duong co moi diem doc mat tien deu cach 0 nen p_road
    chon theo "canh dau tien" la ngau nhien: co the trung vi tri voi thua
    nho ke ben va dung sai cho trong day so. Diem giua chi dung de tinh VI TRI
    THU TU tren bien duong; p_road/TRAI-PHAI/chi phi topology giu nguyen.

    Doan cong gap khuc (thua goc ngoai, do thang < MAT_TIEN_DAI_THANG_MIN)
    khong ap dung vi diem giua nam o goc.
    Tra ve Point tren bien duong hoac None.
    """
    try:
        if geom is None or geom.is_empty or geom.geom_type == "Point":
            return None

        chung = geom.boundary.intersection(poly.boundary.buffer(0.3))
        cac_doan = lay_cac_line(chung)

        if not cac_doan:
            return None

        gop = lay_cac_line(linemerge(cac_doan))

        if not gop:
            return None

        dai_nhat = max(gop, key=lambda g: g.length)

        if dai_nhat.length < MAT_TIEN_DAI_MIN:
            return None

        a, b = dai_nhat.coords[0], dai_nhat.coords[-1]

        if math.dist(a, b) < MAT_TIEN_DAI_THANG_MIN * dai_nhat.length:
            return None

        p_giua = dai_nhat.interpolate(0.5, normalized=True)
        _, p_road = nearest_points(p_giua, poly.boundary)
        return p_road
    except Exception:
        return None


def lay_diem_mat_tien(geom, poly, line=None):
    """
    TIM MAT TIEN THEO CANH ROAD SONG SONG VOI TUYEN.

    Han che cua cach nearest-boundary don gian:
        nearest_points(thua.boundary, poly.boundary)
    co the bat vao END-CAP cua polygon road tai giao lo.

    Cach xu ly:
    - tach boundary road thanh tung segment;
    - voi tung segment:
        + tim cap diem thua-road gan nhat;
        + lay tangent segment;
        + lay tangent reference-line gan candidate;
        + tinh do song song;
    - uu tien candidate co tangent road SONG SONG reference-line.

    Tra ve:
        p_thua,
        p_road,
        do_song_song,
        chi_so_canh,
        cach_chon

    cach_chon:
        DOC_TUYEN  : canh frontage hop le, song song tuyen
        GAN_NHAT   : fallback nearest boundary cu
        DIEM       : input geometry la Point
        LOI        : khong tim duoc
    """
    if geom is None or geom.is_empty or poly is None or poly.is_empty:
        return None, None, 0.0, -1, "LOI"

    try:
        boundary_house = geom if geom.geom_type == "Point" else geom.boundary
    except Exception:
        boundary_house = geom

    if boundary_house is None or boundary_house.is_empty:
        return None, None, 0.0, -1, "LOI"

    # --------------------------------------------------------
    # Tao danh sach segment cua exterior + interior rings.
    # --------------------------------------------------------
    segments = []

    try:
        rings = [list(poly.exterior.coords)]

        for ring in poly.interiors:
            rings.append(list(ring.coords))
    except Exception:
        rings = []

    stt_canh = 0

    for coords in rings:
        for a, b in zip(coords[:-1], coords[1:]):
            seg = LineString([a, b])

            if seg.length <= 1e-9:
                continue

            segments.append((stt_canh, seg))
            stt_canh += 1

    ung_vien = []

    for chi_so_canh, seg in segments:
        try:
            p_thua, p_road = nearest_points(
                boundary_house,
                seg,
            )
        except Exception:
            continue

        if p_thua is None or p_thua.is_empty or p_road is None or p_road.is_empty:
            continue

        kc = float(p_thua.distance(p_road))

        cs = list(seg.coords)
        dx_canh = cs[-1][0] - cs[0][0]
        dy_canh = cs[-1][1] - cs[0][1]

        dx_ref, dy_ref = _tangent_reference_tai_diem(
            line,
            p_road,
        )

        song_song = _cos_song_song(
            dx_canh,
            dy_canh,
            dx_ref,
            dy_ref,
        )

        # Uu tien canh co tangent gan song song voi tuyen.
        # 0.55 ~ lech toi da khoang 56 do.
        # Dat tuong doi rong de khong loai canh duong cong.
        hop_le = song_song >= 0.55

        ung_vien.append(
            {
                "hopLe": hop_le,
                "kc": kc,
                "songSong": float(song_song),
                "pThua": p_thua,
                "pRoad": p_road,
                "canh": int(chi_so_canh),
            }
        )

    # --------------------------------------------------------
    # Neu co canh doc tuyen hop le:
    # khoang cach la khoa chinh, song song la tie-break.
    # --------------------------------------------------------
    hop_le = [u for u in ung_vien if u["hopLe"]]

    if hop_le:
        best = min(
            hop_le,
            key=lambda u: (
                u["kc"],
                -u["songSong"],
                u["canh"],
            ),
        )

        return (
            best["pThua"],
            best["pRoad"],
            best["songSong"],
            best["canh"],
            "DOC_TUYEN",
        )

    # --------------------------------------------------------
    # Fallback: nearest boundary neu khong tim duoc canh mat tien phu hop.
    # --------------------------------------------------------
    try:
        p_thua, p_road = nearest_points(
            boundary_house,
            poly.boundary,
        )

        if (
            p_thua is not None
            and not p_thua.is_empty
            and p_road is not None
            and not p_road.is_empty
        ):
            dx_ref, dy_ref = _tangent_reference_tai_diem(
                line,
                p_road,
            )

            dx_b, dy_b = tangent_bien_duong(
                poly,
                p_road,
                tangent_tham_chieu=(dx_ref, dy_ref),
            )

            song_song = _cos_song_song(
                dx_b,
                dy_b,
                dx_ref,
                dy_ref,
            )

            return (
                p_thua,
                p_road,
                float(song_song),
                -1,
                "GAN_NHAT",
            )
    except Exception:
        pass

    try:
        p_thua = geom.representative_point()
    except Exception:
        try:
            p_thua = geom.centroid
        except Exception:
            return None, None, 0.0, -1, "LOI"

    try:
        _, p_road = nearest_points(
            p_thua,
            poly.boundary,
        )
    except Exception:
        p_road = None

    return p_thua, p_road, 0.0, -1, "GAN_NHAT"


def chieu_diem_vao_line_theo_long_duong(line, poly, diem_duong):
    """
    Chieu diem tren bien road polygon vao reference line NHUNG co rang buoc
    "duong noi tu bien road vao reference line phai nam trong long road".

    Day la fix quan trong cua V3.

    V2:
        m = line.project(access_point)
    => chi tim doan line gan nhat theo Euclid.
       O khuc cua gap, no co the nhay sang mot nhanh gan ve khong gian
       nhung sai ve thu tu dọc tuyen.

    V3:
        1. Xet tung segment lien tiep cua reference line.
        2. Tim projection tren segment do.
        3. Noi diem boundary road -> projection.
        4. Uu tien segment ma connector nam trong polygon road.
        5. Moi sau do moi lay chainage tren line.

    Tra ve:
        m, projection_point, cach_chieu, chi_so_segment
    """
    if (
        line is None
        or line.is_empty
        or line.geom_type != "LineString"
        or line.length <= 0
        or diem_duong is None
        or diem_duong.is_empty
    ):
        return None, None, "LOI", -1

    coords = list(line.coords)

    if len(coords) < 2:
        return None, None, "LOI", -1

    # Buffer rat nho de chap nhan sai so toa do tai boundary.
    # CRS da duoc bat buoc projected; du lieu hien tai dung VN2000.
    sai_so = 0.20
    try:
        vung_duong = poly.buffer(sai_so)
    except Exception:
        vung_duong = poly

    ung_vien_tot = []
    ung_vien_du_phong = []

    tich_luy = 0.0

    for i in range(len(coords) - 1):
        a = coords[i]
        b = coords[i + 1]

        seg = LineString([a, b])
        L = float(seg.length)

        if L <= 1e-12:
            continue

        m_seg = float(seg.project(diem_duong))
        q = seg.interpolate(m_seg)
        kc = float(diem_duong.distance(q))

        m_toan = tich_luy + m_seg

        # Connector tu BIEN ROAD toi reference line.
        connector = LineString(
            [
                (diem_duong.x, diem_duong.y),
                (q.x, q.y),
            ]
        )

        # Test nhieu diem ben trong connector thay vi chi test 1 midpoint.
        # Dung covers de boundary cung duoc chap nhan.
        hop_le = True

        try:
            for ti_le in (0.20, 0.40, 0.60, 0.80):
                p_test = connector.interpolate(ti_le, normalized=True)

                if not vung_duong.covers(p_test):
                    hop_le = False
                    break
        except Exception:
            hop_le = False

        item = (kc, m_toan, q, i)

        if hop_le:
            ung_vien_tot.append(item)

        ung_vien_du_phong.append(item)

        tich_luy += L

    if ung_vien_tot:
        kc, m, q, i = min(
            ung_vien_tot,
            key=lambda z: (z[0], z[1], z[3]),
        )
        return float(m), q, "TRONG_DUONG", int(i)

    # Neu polygon xau / reference line lech nhe lam khong co connector hop le,
    # moi fallback ve nearest segment thong thuong.
    if ung_vien_du_phong:
        kc, m, q, i = min(
            ung_vien_du_phong,
            key=lambda z: (z[0], z[1], z[3]),
        )
        return float(m), q, "DU_PHONG", int(i)

    m = float(line.project(diem_duong))
    q = line.interpolate(m)

    return m, q, "PROJECT", -1


def tangent_cuc_bo_on_dinh(line, m):
    """
    Dung cua so 1..5 m de tangent on dinh hon ban cu
    nhung van bam duong cong.
    """
    L = float(line.length)

    if L <= 0:
        return 0.0, 0.0

    cua_so = max(1.0, min(5.0, L * 0.01))

    m1 = max(0.0, m - cua_so)
    m2 = min(L, m + cua_so)

    p1 = line.interpolate(m1)
    p2 = line.interpolate(m2)

    dx = p2.x - p1.x
    dy = p2.y - p1.y

    if math.hypot(dx, dy) <= 1e-12:
        cs = list(line.coords)
        dx = cs[-1][0] - cs[0][0]
        dy = cs[-1][1] - cs[0][1]

    return dx, dy


def vi_tri_sap_xep_endpoint(line, diem, m):
    """
    line.project() se kep cac diem nam qua START/END vao endpoint.
    Chi khi bi kep sat endpoint moi ngoai suy de pha hoa thu tu.
    """
    L = float(line.length)

    if L <= 0:
        return float(m)

    nguong_kep = max(0.05, L * 0.002)
    cua_so = max(1.0, min(5.0, L * 0.02))

    # Qua START
    if m <= nguong_kep:
        p0 = line.interpolate(0.0)
        p1 = line.interpolate(min(cua_so, L))

        vx = p1.x - p0.x
        vy = p1.y - p0.y
        do = math.hypot(vx, vy)

        if do > 1e-12:
            ux = vx / do
            uy = vy / do

            t = (diem.x - p0.x) * ux + (diem.y - p0.y) * uy

            if t < 0:
                return float(t)

    # Qua END
    if m >= L - nguong_kep:
        p1 = line.interpolate(L)
        p0 = line.interpolate(max(0.0, L - cua_so))

        vx = p1.x - p0.x
        vy = p1.y - p0.y
        do = math.hypot(vx, vy)

        if do > 1e-12:
            ux = vx / do
            uy = vy / do

            t = (diem.x - p1.x) * ux + (diem.y - p1.y) * uy

            if t > 0:
                return float(L + t)

    return float(m)


# ============================================================
# PROCESS
# ============================================================


# ============================================================
# TOPOLOGY / TIEP GIAP THUA
# ============================================================


def tao_do_thi_tiep_giap_thua(nhom, nguong_ranh_chung=0.05, nguong_gap=0.25):
    """
    Tao graph tiep giap GIUA CAC THUA trong cung tenDuong.

    Edge manh:
        2 thua co do dai ranh chung >= nguong_ranh_chung.

    Edge du phong:
        2 thua co gap rat nho 0 < distance <= nguong_gap.
        Khong noi neu chi cham 1 DIEM (distance=0 nhung shared length=0),
        de tranh noi nham qua goc.

    Tra ve:
        adj[idx] = [(idx_ke, trong_so, loai), ...]
    """
    ids = list(nhom.index)
    adj = {idx: [] for idx in ids}

    for i in range(len(ids)):
        idx1 = ids[i]
        g1 = nhom.at[idx1, "geometry"]

        if g1 is None or g1.is_empty:
            continue

        for j in range(i + 1, len(ids)):
            idx2 = ids[j]
            g2 = nhom.at[idx2, "geometry"]

            if g2 is None or g2.is_empty:
                continue

            try:
                shared = float(g1.boundary.intersection(g2.boundary).length)
            except Exception:
                shared = 0.0

            co_noi = False
            trong_so = 0.0
            loai = ""

            if shared >= nguong_ranh_chung:
                co_noi = True
                trong_so = max(shared, nguong_ranh_chung)
                loai = "RANH_CHUNG"
            else:
                try:
                    kc = float(g1.distance(g2))
                except Exception:
                    kc = float("inf")

                # distance == 0 ma shared == 0 thuong chi cham goc -> bo.
                if 1e-8 < kc <= nguong_gap:
                    co_noi = True
                    # gap edge yeu hon ranh chung that.
                    trong_so = max(0.01, nguong_gap - kc)
                    loai = "GAP_NHO"

            if co_noi:
                adj[idx1].append((idx2, float(trong_so), loai))
                adj[idx2].append((idx1, float(trong_so), loai))

    return adj


def _thanh_phan_tiep_giap(adj, ids=None):
    """Connected components cua graph tiep giap."""
    tap = set(adj.keys()) if ids is None else set(ids)
    da_xem = set()
    comps = []

    for start in tap:
        if start in da_xem:
            continue

        stack = [start]
        da_xem.add(start)
        comp = []

        while stack:
            u = stack.pop()
            comp.append(u)

            for v, _, _ in adj.get(u, []):
                if v in tap and v not in da_xem:
                    da_xem.add(v)
                    stack.append(v)

        comps.append(comp)

    return comps


def hau_kiem_ben_theo_tiep_giap(group, verbose=True, tin_cay_giu_ben=None):
    """
    PASS 2A - SUA TRAI/PHAI LAC DAN.

    Nguyen tac:
    - chi xu ly trong CUNG _cumThua;
    - mot connected-component thua tiep giap >= 3 thua thuong la 1 day vat ly;
    - neu da so ben rat ro va mot thua lac dan co hang xom truc tiep ung ho
      ben da so, sua thua do ve ben da so;
    - component 1-2 thua hoac ty le mo ho -> KHONG sua.

    Day KHONG phai "thay so le roi ep qua ben chan".
    Sua FIELD side truoc, sau do danh so lai.

    tin_cay_giu_ben: neu co, thua co _tinCayBen >= nguong nay giu nguyen ben
    hinh hoc (che do tim: ben do bang dien tich hai phia tim da du tin cay,
    con hang xom o cuoi duong cut thuong nam vong qua dau tim). Thua goc giua
    hai doan tim (_gocNhanh) van theo hang xom: ben cua no so voi nhanh re
    khong phai ben so voi tim chinh.
    """
    group = group.copy()

    group["_benHinhHoc"] = group[COL_BEN]
    group["_suaBen"] = False
    group["_cumTiepGiap"] = -1
    group["_bacTiepGiap"] = 0

    adj = tao_do_thi_tiep_giap_thua(group)

    for idx in group.index:
        group.at[idx, "_bacTiepGiap"] = len(adj.get(idx, []))

    sua = []
    cum_topo_id = 0

    cac_cum = [int(v) for v in group["_cumThua"].dropna().unique().tolist()]

    for cum_id in cac_cum:
        ids_cum = set(group.index[group["_cumThua"] == cum_id].tolist())

        comps = _thanh_phan_tiep_giap(
            adj,
            ids=ids_cum,
        )

        for comp in comps:
            cum_topo_id += 1

            for idx in comp:
                group.at[idx, "_cumTiepGiap"] = cum_topo_id

            sides = [
                group.at[idx, COL_BEN]
                for idx in comp
                if group.at[idx, COL_BEN] in (GT_TRAI, GT_PHAI)
            ]

            if len(comp) < 3 or len(sides) < 3:
                continue

            dem_trai = sum(1 for s in sides if s == GT_TRAI)
            dem_phai = sum(1 for s in sides if s == GT_PHAI)

            if dem_trai == dem_phai:
                continue

            ben_da_so = GT_TRAI if dem_trai > dem_phai else GT_PHAI

            ty_le_da_so = max(
                dem_trai,
                dem_phai,
            ) / max(1, len(sides))

            # Neu component gan 50/50 thi co the graph noi nham/phan nhanh.
            if ty_le_da_so < 0.67:
                continue

            for idx in comp:
                ben_hien_tai = group.at[idx, COL_BEN]

                if ben_hien_tai not in (GT_TRAI, GT_PHAI):
                    continue

                if ben_hien_tai == ben_da_so:
                    continue

                if (
                    tin_cay_giu_ben is not None
                    and float(group.at[idx, "_tinCayBen"]) >= tin_cay_giu_ben
                    and not bool(group.at[idx, "_gocNhanh"])
                ):
                    continue

                # Vote CHI TU HANG XOM TRUC TIEP.
                w_da_so = 0.0
                w_khac = 0.0
                so_hang_xom_hop_le = 0

                for v, w, _ in adj.get(idx, []):
                    if v not in ids_cum:
                        continue

                    ben_v = group.at[v, COL_BEN]

                    if ben_v not in (GT_TRAI, GT_PHAI):
                        continue

                    so_hang_xom_hop_le += 1

                    if ben_v == ben_da_so:
                        w_da_so += float(w)
                    else:
                        w_khac += float(w)

                tong_w = w_da_so + w_khac

                if so_hang_xom_hop_le == 0 or tong_w <= 0:
                    continue

                ty_le_hang_xom = w_da_so / tong_w

                # Hai che do:
                # - da so component rat manh >= 80% + hang xom >= 55%;
                # - hoac hang xom truc tiep ung ho rat manh >= 75%.
                du_bang_chung = (
                    ty_le_da_so >= 0.80 and ty_le_hang_xom >= 0.55
                ) or ty_le_hang_xom >= 0.75

                if not du_bang_chung:
                    continue

                group.at[idx, COL_BEN] = ben_da_so
                group.at[idx, "_suaBen"] = True

                sua.append(
                    (
                        idx,
                        ben_hien_tai,
                        ben_da_so,
                        ty_le_da_so,
                        ty_le_hang_xom,
                    )
                )

    if verbose:
        print(
            "Hau kiem topology - sua TRAI/PHAI:",
            len(sua),
            "thua",
        )

        for idx, cu, moi, r1, r2 in sua[:20]:
            print(
                f"  idx={idx}: {cu} -> {moi} | "
                f"daSo={round(r1, 2)} | "
                f"hangXom={round(r2, 2)}"
            )

        if len(sua) > 20:
            print(f"  ... con {len(sua) - 20} thua da sua")

    return group, adj, sua


def _thong_ke_cum_tiep_giap(group):
    """Thong ke size + majority side cho _cumTiepGiap."""
    out = {}

    for cum_value, sub in group.groupby("_cumTiepGiap"):
        try:
            cum_id = int(cum_value)
        except Exception:
            continue

        if cum_id < 0:
            continue

        sides = [s for s in sub[COL_BEN].tolist() if s in (GT_TRAI, GT_PHAI)]

        if not sides:
            continue

        n_trai = sum(1 for s in sides if s == GT_TRAI)
        n_phai = sum(1 for s in sides if s == GT_PHAI)

        if n_trai > n_phai:
            ben = GT_TRAI
            ty_le = n_trai / len(sides)
        elif n_phai > n_trai:
            ben = GT_PHAI
            ty_le = n_phai / len(sides)
        else:
            ben = None
            ty_le = 0.5

        out[cum_id] = {
            "size": int(len(sub)),
            "ben": ben,
            "tyLe": float(ty_le),
            "ids": list(sub.index),
        }

    return out


def _diem_mat_duong_cua_idx(group, idx):
    """Lay Point frontage da duoc tinh o buoc hinh hoc."""
    try:
        x = group.at[idx, "_xMatDuong"]
        y = group.at[idx, "_yMatDuong"]

        if pd.isna(x) or pd.isna(y):
            return None

        return Point(float(x), float(y))
    except Exception:
        return None


def _endpoint_on_dinh_theo_ben(group, adj):
    """
    Lay CAC ENDPOINT cua day topology on dinh.

    Chi dung component:
      - size >= 3
      - majority >= 80%
      - co side majority ro rang

    Moi endpoint phai co degree noi bo <= 1.
    Neu component khong phai chain ro rang thi khong dung lam moc.
    """
    thong_ke = _thong_ke_cum_tiep_giap(group)
    endpoints = []

    for cum_tiep, info in thong_ke.items():
        if (
            info["size"] < 3
            or info["ben"] not in (GT_TRAI, GT_PHAI)
            or info["tyLe"] < 0.80
        ):
            continue

        tap = set(info["ids"])

        bac_noi_bo = {}

        for idx in tap:
            bac_noi_bo[idx] = sum(1 for v, _, _ in adj.get(idx, []) if v in tap)

        # Day on dinh phai gan dang chain:
        # khong node nao degree > 2.
        if any(d > 2 for d in bac_noi_bo.values()):
            continue

        dau_mut = [idx for idx, d in bac_noi_bo.items() if d <= 1]

        if len(dau_mut) != 2:
            continue

        for idx in dau_mut:
            p = _diem_mat_duong_cua_idx(group, idx)

            if p is None:
                continue

            cum_thua = group.at[idx, "_cumThua"]

            if pd.isna(cum_thua):
                continue

            huong = group.at[idx, COL_HUONG]
            score = float(
                diem_so_huong(
                    p,
                    huong,
                )
            )

            endpoints.append(
                {
                    "idx": idx,
                    "cumThua": int(cum_thua),
                    "cumTiep": int(cum_tiep),
                    "ben": info["ben"],
                    "p": p,
                    "score": score,
                }
            )

    return endpoints


def _de_xuat_doi_ben_terminal(group, idx, endpoints):
    """
    De xuat 1 candidate terminal doi sang ben doi dien.

    RAT BAO THU:
    - candidate chi duoc la component 1-2 thua / degree <= 1;
    - chi so voi ENDPOINT day on dinh;
    - phai cung _cumThua;
    - endpoint ben DOI DIEN phai:
        + gan <= 18m
        + gan hon endpoint ben hien tai it nhat 4m
        + va <= 55% khoang cach ben hien tai
    - chenh score doc tuyen voi endpoint doi dien <= 30m.

    Ham CHI de xuat, CHUA sua side.
    """
    row = group.loc[idx]

    ben_cu = row[COL_BEN]

    if ben_cu not in (GT_TRAI, GT_PHAI):
        return None

    cum_tiep = int(row["_cumTiepGiap"]) if not pd.isna(row["_cumTiepGiap"]) else -1

    # Candidate terminal/component nho.
    size_comp = int((group["_cumTiepGiap"] == cum_tiep).sum()) if cum_tiep >= 0 else 1

    bac = int(row["_bacTiepGiap"]) if not pd.isna(row["_bacTiepGiap"]) else 0

    if size_comp > 2 and bac > 1:
        return None

    p = _diem_mat_duong_cua_idx(group, idx)

    if p is None or pd.isna(row["_cumThua"]):
        return None

    cum_thua = int(row["_cumThua"])
    huong = row[COL_HUONG]
    score = float(diem_so_huong(p, huong))

    ben_moi = GT_PHAI if ben_cu == GT_TRAI else GT_TRAI

    ep_cu = [
        ep for ep in endpoints if ep["cumThua"] == cum_thua and ep["ben"] == ben_cu
    ]

    ep_moi = [
        ep for ep in endpoints if ep["cumThua"] == cum_thua and ep["ben"] == ben_moi
    ]

    if not ep_cu or not ep_moi:
        return None

    def best(ds):
        items = []

        for ep in ds:
            d = float(p.distance(ep["p"]))
            ds_score = abs(score - ep["score"])

            items.append(
                (
                    d,
                    ds_score,
                    ep,
                )
            )

        return min(
            items,
            key=lambda z: (
                z[0],
                z[1],
                z[2]["idx"],
            ),
        )

    d_cu, score_cu, ref_cu = best(ep_cu)
    d_moi, score_moi, ref_moi = best(ep_moi)

    # Dieu kien cuc chat.
    if d_moi > 18.0:
        return None

    if score_moi > 30.0:
        return None

    if not (d_moi + 4.0 <= d_cu and d_moi <= 0.55 * max(d_cu, 1e-9)):
        return None

    return {
        "idx": idx,
        "cu": ben_cu,
        "moi": ben_moi,
        "cumThua": cum_thua,
        "p": p,
        "score": score,
        "dCu": float(d_cu),
        "dMoi": float(d_moi),
        "scoreCu": float(score_cu),
        "scoreMoi": float(score_moi),
        "refCu": ref_cu["idx"],
        "refMoi": ref_moi["idx"],
    }


def hau_kiem_cap_terminal_hoan_doi(
    group,
    adj,
    verbose=True,
):
    """
    HAU KIEM CAP THUA CUOI DOI BEN DOI XUNG.

    Chi sua khi co MOT CAP DE XUAT DOI BEN DOI XUNG:

        A: TRAI -> PHAI
        B: PHAI -> TRAI

    va:
    - cung _cumThua;
    - vi tri doc tuyen gan nhau (<= 35m);
    - 2 candidate frontage khong cach nhau qua 45m.

    Neu chi co 1 candidate le loi -> KHONG SUA.
    Neu khong co cap doi xung -> KHONG SUA.

    Khong quet va sua hang loat terminal neu bang chung khong du manh.
    """
    group = group.copy()

    group["_suaCap"] = False
    group["_benTruocCap"] = group[COL_BEN]
    group["_lyDoCap"] = ""

    endpoints = _endpoint_on_dinh_theo_ben(
        group,
        adj,
    )

    proposals = []

    for idx in group.index:
        de_xuat = _de_xuat_doi_ben_terminal(
            group,
            idx,
            endpoints,
        )

        if de_xuat is not None:
            proposals.append(de_xuat)

    trai_sang_phai = [
        p for p in proposals if p["cu"] == GT_TRAI and p["moi"] == GT_PHAI
    ]

    phai_sang_trai = [
        p for p in proposals if p["cu"] == GT_PHAI and p["moi"] == GT_TRAI
    ]

    cap_ung_vien = []

    for a in trai_sang_phai:
        for b in phai_sang_trai:
            if a["cumThua"] != b["cumThua"]:
                continue

            ds_score = abs(a["score"] - b["score"])
            kc_cap = float(a["p"].distance(b["p"]))

            if ds_score > 35.0:
                continue

            if kc_cap > 45.0:
                continue

            # Loi ich doi side: tong khoang cach giam duoc bao nhieu.
            loi_ich = (a["dCu"] - a["dMoi"]) + (b["dCu"] - b["dMoi"])

            cap_ung_vien.append(
                (
                    -loi_ich,
                    ds_score,
                    kc_cap,
                    a,
                    b,
                )
            )

    cap_ung_vien.sort(
        key=lambda z: (
            z[0],
            z[1],
            z[2],
        )
    )

    da_dung = set()
    da_sua = []

    for _, ds_score, kc_cap, a, b in cap_ung_vien:
        if a["idx"] in da_dung or b["idx"] in da_dung:
            continue

        # DOI CAP CUNG LUC.
        for item in (a, b):
            idx = item["idx"]

            group.at[idx, "_benTruocCap"] = item["cu"]
            group.at[idx, COL_BEN] = item["moi"]
            group.at[idx, "_suaCap"] = True
            group.at[idx, "_suaBen"] = True
            group.at[idx, "_lyDoCap"] = "CAP_TERMINAL"

            da_dung.add(idx)

        da_sua.append(
            {
                "a": a,
                "b": b,
                "scoreGap": float(ds_score),
                "kcCap": float(kc_cap),
            }
        )

    if verbose:
        print(
            "Hau kiem cap thua cuoi:",
            len(da_sua),
            "cap",
        )

        for cap in da_sua[:10]:
            a = cap["a"]
            b = cap["b"]

            print(
                f"  CAP idx={a['idx']} {a['cu']}->{a['moi']} "
                f"& idx={b['idx']} {b['cu']}->{b['moi']} | "
                f"dMoi=({round(a['dMoi'],2)}, {round(b['dMoi'],2)}) | "
                f"dCu=({round(a['dCu'],2)}, {round(b['dCu'],2)}) | "
                f"scoreGap={round(cap['scoreGap'],2)}"
            )

    return group, da_sua


# ============================================================
# HAU KIEM CAP CUOI DAY SAU KHI DA DANH SO
# ============================================================


def _chi_phi_lien_tuc_hai_thua(group, idx_a, idx_b):
    """
    Chi phi cang nho = 2 thua cang co kha nang nam noi tiep cung 1 day.

    Uu tien:
    1. co RANH CHUNG -> rat manh;
    2. khoang cach polygon;
    3. khoang cach representative point de pha hoa.

    Khong dung so nha de tinh chi phi.
    """
    try:
        ga = group.at[idx_a, "geometry"]
        gb = group.at[idx_b, "geometry"]
    except Exception:
        return float("inf")

    if ga is None or gb is None or ga.is_empty or gb.is_empty:
        return float("inf")

    try:
        shared = float(ga.boundary.intersection(gb.boundary).length)
    except Exception:
        shared = 0.0

    try:
        d_poly = float(ga.distance(gb))
    except Exception:
        d_poly = float("inf")

    try:
        pa = ga.representative_point()
        pb = gb.representative_point()
        d_rep = float(pa.distance(pb))
    except Exception:
        d_rep = float("inf")

    if math.isinf(d_poly) or math.isinf(d_rep):
        return float("inf")

    # Chi phi nen:
    # - polygon distance la chinh;
    # - representative distance chi la tie-break mem.
    cost = d_poly + 0.15 * d_rep

    # Neu co ranh chung that, ha chi phi manh.
    if shared >= 0.05:
        cost *= 0.12

    return float(cost)


def _score_idx_theo_huong(group, idx):
    """
    Vi tri tong quat cua thua theo 4 huong danh so.
    Chi dung de kiem tra 2 tail co nam cung mot dau tuyen hay khong.
    """
    try:
        row = group.loc[idx]
        huong = row[COL_HUONG]

        x = row.get("_xMatDuong")
        y = row.get("_yMatDuong")

        if pd.isna(x) or pd.isna(y):
            p = row.geometry.representative_point()
        else:
            p = Point(float(x), float(y))

        return float(
            diem_so_huong(
                p,
                huong,
            )
        )
    except Exception:
        return float("nan")


def _diem_frontage_idx(group, idx):
    """
    Lấy đúng điểm mặt đường đã tính ở PASS 1.
    Không dùng centroid/representative point của cả thửa nếu không cần.
    """
    try:
        x = group.at[idx, "_xMatDuong"]
        y = group.at[idx, "_yMatDuong"]

        if not pd.isna(x) and not pd.isna(y):
            return Point(float(x), float(y))
    except Exception:
        pass

    try:
        return group.at[idx, "geometry"].representative_point()
    except Exception:
        return None


def _trung_vi_ds_so(ds):
    ds = sorted(float(v) for v in ds if not pd.isna(v))

    if not ds:
        return 0.0

    n = len(ds)

    if n % 2:
        return ds[n // 2]

    return (ds[n // 2 - 1] + ds[n // 2]) / 2.0


def _median_num(ds):
    ds = sorted(float(v) for v in ds if v is not None and not pd.isna(v))

    if not ds:
        return 0.0

    n = len(ds)

    if n % 2:
        return ds[n // 2]

    return (ds[n // 2 - 1] + ds[n // 2]) / 2.0


def _chi_phi_noi_tiep_cuc_bo(group, idx_candidate, lich_su_idx):
    """
    Chi phi NOI TIEP CUC BO.

    Nguyen tac:
    - không lấy vector từ điểm đầu cửa sổ -> điểm cuối;
    - dùng chủ yếu 2-3 điểm CUỐI của dãy;
    - vì ngay gần giao lộ/khúc cong, hướng local mới quan trọng.

    Cost:
    - khoảng cách candidate tới tail hiện tại;
    - lệch nhịp so với bước gần nhất;
    - góc ngoặt so với segment cuối;
    - phạt cực mạnh nếu candidate quay ngược.
    """
    p_cand = _diem_frontage_idx(group, idx_candidate)

    hist = [idx for idx in lich_su_idx if _diem_frontage_idx(group, idx) is not None]

    if p_cand is None or not hist:
        return float("inf"), {}

    hist = hist[-4:]
    pts = [_diem_frontage_idx(group, idx) for idx in hist]

    p_last = pts[-1]

    vx = p_cand.x - p_last.x
    vy = p_cand.y - p_last.y
    dist = math.hypot(vx, vy)

    if len(pts) == 1:
        return dist, {
            "dist": float(dist),
            "goc": 0.0,
            "forward": float(dist),
            "step": float(dist),
        }

    # Vector segment cuối của dãy.
    p_prev = pts[-2]
    ux = p_last.x - p_prev.x
    uy = p_last.y - p_prev.y
    norm_u = math.hypot(ux, uy)

    # Nếu 2 điểm cuối trùng, lùi dần tìm segment hợp lệ.
    if norm_u <= 1e-9:
        for i in range(len(pts) - 3, -1, -1):
            ux = p_last.x - pts[i].x
            uy = p_last.y - pts[i].y
            norm_u = math.hypot(ux, uy)
            if norm_u > 1e-9:
                break

    if norm_u <= 1e-9:
        return dist, {
            "dist": float(dist),
            "goc": 0.0,
            "forward": float(dist),
            "step": float(dist),
        }

    uxn = ux / norm_u
    uyn = uy / norm_u

    forward = vx * uxn + vy * uyn
    lateral = abs(uxn * vy - uyn * vx)

    # Góc đổi hướng 0..180.
    if dist > 1e-9:
        cosang = max(
            -1.0,
            min(
                1.0,
                (ux * vx + uy * vy) / (norm_u * dist),
            ),
        )
        goc = math.degrees(math.acos(cosang))
    else:
        goc = 0.0

    ds_buoc = []

    for a, b in zip(pts[:-1], pts[1:]):
        d = float(a.distance(b))
        if d > 1e-6:
            ds_buoc.append(d)

    step = _median_num(ds_buoc)

    if step <= 1e-6:
        step = max(1.0, dist)

    # Cost local.
    cost = abs(dist - step) + 1.8 * lateral + step * (goc / 90.0) * 1.5 + 0.15 * dist

    # Quay ngược = gần như chắc chắn không phải tiếp diễn.
    if forward <= 0:
        cost += 100.0 + 8.0 * abs(forward)

    return float(cost), {
        "dist": float(dist),
        "goc": float(goc),
        "forward": float(forward),
        "lateral": float(lateral),
        "step": float(step),
    }


def _hai_duong_noi_co_cat_nhau(p1, p2, q1, q2):
    """
    Kiểm tra 2 connector hiện tại có cắt nhau hay không.
    Chỉ dùng như bằng chứng bổ sung, không tự quyết định swap.
    """
    try:
        a = LineString([(p1.x, p1.y), (p2.x, p2.y)])
        b = LineString([(q1.x, q1.y), (q2.x, q2.y)])

        inter = a.intersection(b)

        if inter.is_empty:
            return False

        # Nếu chỉ chung đúng endpoint thì không xem là "cắt chéo".
        endpoints = [p1, p2, q1, q2]

        if inter.geom_type == "Point":
            for ep in endpoints:
                if inter.distance(ep) <= 1e-8:
                    return False

        return True

    except Exception:
        return False


def hau_kiem_hoan_doi_cap_cuoi_sau_danh_so(
    group,
    verbose=True,
):
    """
    Hau kiem cap cuoi bi gan cheo giua hai ben.

    Chỉ xét:
        tail TRAI
        tail PHAI

    So:
        hiện tại:
            tail TRAI nối dãy TRAI
            tail PHAI nối dãy PHAI

        đổi chéo:
            tail TRAI nối dãy PHAI
            tail PHAI nối dãy TRAI

    Quyết định chủ yếu bằng:
    - hướng local của 2-3 frontage cuối;
    - góc ngoặt;
    - nhịp khoảng cách;
    - connector current có cắt chéo hay không.

    Không đụng thửa giữa tuyến.
    """
    group = group.copy()

    group["_suaDuoi"] = False
    group["_benTruocDuoi"] = group[COL_BEN]
    group["_lyDoDuoi"] = ""

    da_sua = []

    cac_cum = [int(v) for v in group["_cumThua"].dropna().unique().tolist()]

    for cum_id in cac_cum:
        sub = group[group["_cumThua"] == cum_id]

        trai = sub[(sub[COL_BEN] == GT_TRAI) & sub[COL_SONHA].notna()].sort_values(
            COL_SONHA,
            ascending=True,
        )

        phai = sub[(sub[COL_BEN] == GT_PHAI) & sub[COL_SONHA].notna()].sort_values(
            COL_SONHA,
            ascending=True,
        )

        if len(trai) < 3 or len(phai) < 3:
            continue

        idx_tc = trai.index[-1]
        idx_pc = phai.index[-1]

        hist_t = list(trai.index[:-1])
        hist_p = list(phai.index[:-1])

        # 4 chi phí local.
        c_tt, m_tt = _chi_phi_noi_tiep_cuc_bo(group, idx_tc, hist_t)
        c_pp, m_pp = _chi_phi_noi_tiep_cuc_bo(group, idx_pc, hist_p)
        c_tp, m_tp = _chi_phi_noi_tiep_cuc_bo(group, idx_tc, hist_p)
        c_pt, m_pt = _chi_phi_noi_tiep_cuc_bo(group, idx_pc, hist_t)

        if any(math.isinf(v) for v in (c_tt, c_pp, c_tp, c_pt)):
            continue

        hien_tai = c_tt + c_pp
        doi_cheo = c_tp + c_pt

        # Connector từ predecessor cuối -> tail.
        idx_t_prev = hist_t[-1]
        idx_p_prev = hist_p[-1]

        p_t_prev = _diem_frontage_idx(group, idx_t_prev)
        p_p_prev = _diem_frontage_idx(group, idx_p_prev)
        p_tc = _diem_frontage_idx(group, idx_tc)
        p_pc = _diem_frontage_idx(group, idx_pc)

        current_cross = False
        cross_cross = False

        if all(p is not None for p in (p_t_prev, p_p_prev, p_tc, p_pc)):
            current_cross = _hai_duong_noi_co_cat_nhau(
                p_t_prev,
                p_tc,
                p_p_prev,
                p_pc,
            )

            cross_cross = _hai_duong_noi_co_cat_nhau(
                p_t_prev,
                p_pc,
                p_p_prev,
                p_tc,
            )

        if verbose:
            so_t = int(group.at[idx_tc, COL_SONHA])
            so_p = int(group.at[idx_pc, COL_SONHA])

            print(
                f"Tail check cum={cum_id}: "
                f"TRAI={so_t} idx={idx_tc} | "
                f"PHAI={so_p} idx={idx_pc}"
            )
            print(
                "   cost current:",
                f"TT={round(c_tt,2)}",
                f"PP={round(c_pp,2)}",
                f"sum={round(hien_tai,2)}",
            )
            print(
                "   cost cross  :",
                f"TP={round(c_tp,2)}",
                f"PT={round(c_pt,2)}",
                f"sum={round(doi_cheo,2)}",
            )
            print(
                "   angle current/cross:",
                f"TT={round(m_tt.get('goc',0),1)}°",
                f"TP={round(m_tp.get('goc',0),1)}°",
                f"PP={round(m_pp.get('goc',0),1)}°",
                f"PT={round(m_pt.get('goc',0),1)}°",
            )
            print(
                "   connector:",
                f"currentCross={current_cross}",
                f"crossCross={cross_cross}",
            )

        # ====================================================
        # QUYET DINH SWAP 2 TAIL
        # ====================================================
        #
        # Nhánh 1 - bình thường:
        # cả 2 tail đều tự chứng minh rằng dãy đối diện hợp hơn.
        #
        # Nhánh 2 - crossing override:
        # dùng cho trường hợp kiểu Đường số 5:
        #   currentCross=True
        #   crossCross=False
        #   tổng chi phí đổi chéo giảm rất mạnh
        #   nhưng 1 thửa lớn/bất thường (ví dụ 60) tự nó không có metric đẹp.
        #
        # Khi đó KHÔNG bắt buộc cả 2 tail cùng thích cross.
        # Chỉ cần:
        #   - connector hiện tại cắt chéo;
        #   - đổi chéo hết cắt;
        #   - tổng chi phí giảm ít nhất 30%;
        #   - ít nhất 1 tail thích dãy đối diện CỰC MẠNH;
        #   - tail còn lại không tệ quá mức (<= 2 lần hoặc +50m).
        # ====================================================

        # Ưu tiên cross mức bình thường.
        t_pref_cross = c_tp + 0.5 < c_tt and c_tp <= 0.90 * max(c_tt, 1e-9)

        p_pref_cross = c_pt + 0.5 < c_pp and c_pt <= 0.90 * max(c_pp, 1e-9)

        total_pref_cross = doi_cheo + 1.0 < hien_tai and doi_cheo <= 0.85 * max(
            hien_tai,
            1e-9,
        )

        normal_swap = t_pref_cross and p_pref_cross and total_pref_cross

        # Một tail thích cross "cực mạnh".
        t_pref_cross_manh = c_tp + 2.0 < c_tt and c_tp <= 0.50 * max(c_tt, 1e-9)

        p_pref_cross_manh = c_pt + 2.0 < c_pp and c_pt <= 0.50 * max(c_pp, 1e-9)

        # Tail còn lại được phép xấu hơn metric hiện tại,
        # nhưng không được phi lý / quá tệ.
        p_khong_qua_te = c_pt <= max(
            2.0 * c_pp,
            c_pp + 50.0,
        )

        t_khong_qua_te = c_tp <= max(
            2.0 * c_tt,
            c_tt + 50.0,
        )

        mot_ben_manh_ben_kia_chap_nhan = (t_pref_cross_manh and p_khong_qua_te) or (
            p_pref_cross_manh and t_khong_qua_te
        )

        # Override chỉ mở khi hình học connector cho bằng chứng rất mạnh.
        crossing_override = (
            current_cross
            and not cross_cross
            and doi_cheo + 2.0 < hien_tai
            and doi_cheo
            <= 0.70
            * max(
                hien_tai,
                1e-9,
            )
            and mot_ben_manh_ben_kia_chap_nhan
        )

        swap = normal_swap or crossing_override

        if verbose:
            print(
                "   quyetDinh:",
                f"normalSwap={normal_swap}",
                f"crossingOverride={crossing_override}",
                f"Tmanh={t_pref_cross_manh}",
                f"Pmanh={p_pref_cross_manh}",
            )

        if not swap:
            if verbose:
                print("   => GIU NGUYEN")
            continue

        group.at[idx_tc, "_benTruocDuoi"] = GT_TRAI
        group.at[idx_pc, "_benTruocDuoi"] = GT_PHAI

        group.at[idx_tc, COL_BEN] = GT_PHAI
        group.at[idx_pc, COL_BEN] = GT_TRAI

        for idx in (idx_tc, idx_pc):
            group.at[idx, "_suaDuoi"] = True
            group.at[idx, "_suaBen"] = True
            group.at[idx, "_lyDoDuoi"] = "SWAP_DUOI_LOCAL"

        da_sua.append(
            {
                "cum": cum_id,
                "traiCuoi": idx_tc,
                "phaiCuoi": idx_pc,
                "cHienTai": float(hien_tai),
                "cDoiCheo": float(doi_cheo),
                "currentCross": bool(current_cross),
                "crossCross": bool(cross_cross),
            }
        )

        if verbose:
            print("   => SWAP 2 TAIL")

    if verbose:
        print(
            "Hau kiem cap cuoi day:",
            len(da_sua),
            "cap",
        )

    return group, da_sua


def danh_so_lai_theo_logic_chinh(
    group,
    huong,
    adj_tiep_giap,
    verbose=False,
):
    """
    Danh so lai bang logic chinh:
    - boundary order lam co so;
    - topology chain sua dao cuc bo;
    - TRAI le, PHAI chan.
    """
    group = group.copy()

    group[COL_STT] = None
    group[COL_SONHA] = None

    cac_cum_id = sorted(int(v) for v in group["_cumThua"].dropna().unique().tolist())

    # So nha dem tiep qua cac cum (cum da sap theo chieu tuyen): mot tuyen
    # khong duoc co hai thua cung so. Cum chi con dung de sap thu tu.
    da_danh = {GT_TRAI: 0, GT_PHAI: 0}

    for cum_id in cac_cum_id:
        nhom_cum = group[group["_cumThua"] == cum_id].copy()

        if len(nhom_cum) == 0:
            continue

        if verbose:
            print(f"  Cum thua {cum_id}: {len(nhom_cum)} thua")

        for ben, la_trai in (
            (GT_TRAI, True),
            (GT_PHAI, False),
        ):
            nhom = nhom_cum[nhom_cum[COL_BEN] == ben].copy()

            if len(nhom) == 0:
                continue

            thu_tu_co_so, thong_tin_manh = thu_tu_thua_theo_bien_duong(
                nhom,
                huong,
            )

            thu_tu_idx, thong_tin_topo = hau_kiem_thu_tu_theo_tiep_giap(
                nhom,
                thu_tu_co_so,
                adj_tiep_giap,
            )

            if verbose:
                so_chuoi = sum(
                    1
                    for item in thong_tin_topo
                    if item["laChuoi"] and item["soThua"] >= 2
                )

                print(
                    f"    {ben}: {len(nhom)} thua | "
                    f"blockBien="
                    f"{[(item['manh'] + 1, item['vong']) for item in thong_tin_manh]} | "
                    f"chuoiTopo={so_chuoi}"
                )

            for hang, idx in enumerate(
                thu_tu_idx,
                start=da_danh[ben] + 1,
            ):
                group.at[
                    idx,
                    COL_STT,
                ] = (
                    STEP * hang
                )

                group.at[
                    idx,
                    COL_SONHA,
                ] = (
                    2 * hang - 1 if la_trai else 2 * hang
                )

            da_danh[ben] += len(thu_tu_idx)

    return group


def _thu_tu_chuoi_tiep_giap(comp, adj, rank_co_so):
    """
    Neu connected-component la 1 CHUOI:
        degree <= 2 va co 2 endpoint
    thi tra ve thu tu topo chinh xac.

    Huong cua chuoi:
        endpoint nao dung truoc trong thu tu co so thi lam START.

    Neu graph co nhanh/cycle/mo ho:
        return None -> fallback thu tu co so.
    """
    tap = set(comp)

    if len(comp) <= 1:
        return list(comp)

    bac = {}

    for u in comp:
        bac[u] = sum(1 for v, _, _ in adj.get(u, []) if v in tap)

    if any(d > 2 for d in bac.values()):
        return None

    endpoints = [u for u, d in bac.items() if d == 1]

    if len(comp) == 2:
        endpoints = list(comp)

    if len(endpoints) != 2:
        return None

    start = min(
        endpoints,
        key=lambda idx: rank_co_so.get(
            idx,
            10**12,
        ),
    )

    ordered = []
    prev = None
    cur = start

    while cur is not None:
        ordered.append(cur)

        nxts = [v for v, _, _ in adj.get(cur, []) if v in tap and v != prev]

        if not nxts:
            break

        # Chain dung thi chi co 1 next.
        # Neu do gap edge tao 2 candidate, uu tien rank co so gan hon.
        nxt = min(
            nxts,
            key=lambda idx: rank_co_so.get(
                idx,
                10**12,
            ),
        )

        prev, cur = cur, nxt

        if cur in ordered:
            return None

    if len(ordered) != len(comp):
        return None

    return ordered


def hau_kiem_thu_tu_theo_tiep_giap(
    nhom,
    thu_tu_co_so,
    adj,
):
    """
    PASS 2B - SUA DAO CUC BO THU TU.

    Thu tu bien duong van quyet dinh THU TU CO SO cua cac block.
    Topology chi thay thu tu NOI BO cua component thua tiep giap neu component
    la mot CHUOI ro rang.

    Vi du thu tu co so:
        7, 11, 9, 13
    topology:
        7 -- 9 -- 11 -- 13
    -> sau hau kiem topology:
        7, 9, 11, 13

    Neu graph phan nhanh / cycle / mo ho:
        giu nguyen thu tu co so.
    """
    ids = list(nhom.index)
    tap = set(ids)

    base = [idx for idx in thu_tu_co_so if idx in tap]

    # Bao toan record neu thu_tu_co_so thieu.
    for idx in ids:
        if idx not in base:
            base.append(idx)

    rank = {idx: i for i, idx in enumerate(base)}

    comps = _thanh_phan_tiep_giap(
        adj,
        ids=tap,
    )

    blocks = []

    for comp in comps:
        comp_sorted_base = sorted(
            comp,
            key=lambda idx: rank.get(
                idx,
                10**12,
            ),
        )

        topo = _thu_tu_chuoi_tiep_giap(
            comp,
            adj,
            rank,
        )

        if topo is None:
            order = comp_sorted_base
            la_chuoi = False
        else:
            order = topo
            la_chuoi = True

        vi_tri_block = min(rank.get(idx, 10**12) for idx in comp)

        blocks.append(
            {
                "viTri": vi_tri_block,
                "order": order,
                "laChuoi": la_chuoi,
                "soThua": len(comp),
            }
        )

    blocks.sort(key=lambda z: z["viTri"])

    if not la_che_do_tim(nhom):
        ordered = []

        for block in blocks:
            ordered.extend(block["order"])

        return ordered, blocks

    # Che do tim: block nhieu thua van lien nhau; thua DON LE (khong tiep giap
    # thua nao, vd. thua manh ve chong ranh) chen dung vi tri doc mat duong,
    # sau thua cuoi cung dung truoc no trong thu tu co so, thay vi bi day ra
    # sau ca block ma no nam xen giua.
    ordered = []
    don_le = []

    for block in blocks:
        if block["soThua"] == 1:
            don_le.extend(block["order"])
        else:
            ordered.extend(block["order"])

    for idx in sorted(don_le, key=lambda k: rank.get(k, 10**12)):
        r = rank.get(idx, 10**12)
        vi_tri = 0
        for i, khac in enumerate(ordered):
            if rank.get(khac, 10**12) < r:
                vi_tri = i + 1
        ordered.insert(vi_tri, idx)

    return ordered, blocks


# ============================================================
# TIM DUONG (CENTERLINE) - CHI DUONG CHINH
# ============================================================

LOAI_POLYGON = ("Polygon", "MultiPolygon")
LOAI_TIM = ("LineString", "MultiLineString")
KIEU_POLYGON = "polygon"
KIEU_TIM = "tim"
KIEU_LAN = "lan"

# Dau mut hai doan tim cung tuyen lech <= nguong nay (m) duoc coi la noi nhau.
TIM_DUNG_SAI_NOI_M = 0.10
# Nhanh cut ngan hon nguong nay (m) noi vao diem re nhanh la rau cua cong cu sinh tim, bi bo.
TIM_RAU_TOI_DA_M = 15.0
# Phan bien thua cach tim <= khoang cach gan nhat + nguong nay (m) la mat tien.
MAT_TIEN_TIM_BAND_M = 0.5
# Ben TRAI/PHAI o che do tim: so dien tich thua trong dai dem mot phia cua tim,
# rong = khoang cach thua-tim + nguong nay (m).
BEN_TIM_DAI_DEM_M = 8.0
# Thua co do tin cay ben tu nguong nay tro len khong bi hau kiem tiep giap lat ben.
BEN_TIM_TIN_CAY_GIU = 0.5
# Thua cach mot doan tim khac khong qua (khoang cach toi doan cua no + nguong nay, m)
# la thua goc o diem re nhanh.
TIM_THUA_GOC_M = 1.0


def kieu_hinh_hoc_tuyen(geometries):
    """KIEU_POLYGON / KIEU_TIM / KIEU_LAN (lan kieu, hoac kieu khac) / None (rong)."""
    types = {g.geom_type for g in geometries if g is not None and not g.is_empty}
    if not types:
        return None
    if types <= set(LOAI_POLYGON):
        return KIEU_POLYGON
    if types <= set(LOAI_TIM):
        return KIEU_TIM
    return KIEU_LAN


def _khoa_dinh(xy):
    return (round(xy[0], 6), round(xy[1], 6))


def _bac_dinh(lines):
    """So dau mut tai moi nut (bo qua manh khep kin)."""
    bac = {}
    for line in lines:
        if line.is_closed:
            continue
        for xy in (line.coords[0], line.coords[-1]):
            khoa = _khoa_dinh(xy)
            bac[khoa] = bac.get(khoa, 0) + 1
    return bac


def _gop_tim(lines):
    merged = shapely.line_merge(shapely.union_all(lines))
    return [line for line in shapely.get_parts(merged) if line.length > 0]


def _cum_lien_thong(lines):
    """Chi so cum lien thong (0..n) cho tung manh, noi qua dau mut chung."""
    cha = {}

    def goc(khoa):
        cha.setdefault(khoa, khoa)
        while cha[khoa] != khoa:
            cha[khoa] = cha[cha[khoa]]
            khoa = cha[khoa]
        return khoa

    for line in lines:
        a = goc(_khoa_dinh(line.coords[0]))
        b = goc(_khoa_dinh(line.coords[-1]))
        cha[a] = b

    ma = {}
    return [ma.setdefault(goc(_khoa_dinh(line.coords[0])), len(ma)) for line in lines]


def phan_tich_tim_duong(geometries, dung_sai=TIM_DUNG_SAI_NOI_M, rau_toi_da=TIM_RAU_TOI_DA_M):
    """
    Noi cac doan tim cua 1 tuyen thanh cac LineString va bo rau.

    Tim sinh tu dong tu polygon (vd. Polygon To Centerline) co cac nhanh cut
    ngan dam vao mieng giao lo. Nhanh cut ngan hon `rau_toi_da` noi vao diem
    re nhanh duoc bo lap lai, giong cong cu Trim Line cua ArcGIS.

    Tra ve dict:
        lines    : list LineString sau khi noi (moi phan tu = 1 manh)
        cum      : chi so cum lien thong cua tung manh
        nut_nhanh: chi so cum cua tung nut co >= 3 doan gap nhau
        nhanh    : so nut re nhanh
        vong     : so manh khep kin
        so_rau   : so rau da bo
    """
    parts = [
        part
        for g in geometries
        if g is not None and not g.is_empty and g.geom_type in LOAI_TIM
        for part in shapely.get_parts(g)
        if part.length > 0
    ]

    # Gom dau mut gan nhau ve 1 diem dai dien de line_merge noi duoc.
    dai_dien = []

    def bat_dinh(xy):
        for q in dai_dien:
            if math.dist(q, xy) <= dung_sai:
                return q
        dai_dien.append(xy)
        return xy

    snapped = []
    for part in parts:
        coords = list(part.coords)
        coords[0] = bat_dinh(coords[0])
        coords[-1] = bat_dinh(coords[-1])
        if len(coords) >= 2 and LineString(coords).length > 0:
            snapped.append(LineString(coords))

    if not snapped:
        return dict(lines=[], cum=[], nut_nhanh=[], nhanh=0, vong=0, so_rau=0)

    lines = _gop_tim(snapped)
    so_rau = 0

    while True:
        bac = _bac_dinh(lines)
        rau = set()
        for i, line in enumerate(lines):
            if line.is_closed or line.length >= rau_toi_da:
                continue
            bac_hai_dau = sorted(
                (bac[_khoa_dinh(line.coords[0])], bac[_khoa_dinh(line.coords[-1])])
            )
            if bac_hai_dau[0] == 1 and bac_hai_dau[1] >= 3:
                rau.add(i)
        if not rau or len(rau) == len(lines):
            break
        so_rau += len(rau)
        lines = _gop_tim([line for i, line in enumerate(lines) if i not in rau])

    cum = _cum_lien_thong(lines)
    bac = _bac_dinh(lines)
    cum_cua_nut = {}
    for line, c in zip(lines, cum):
        for xy in (line.coords[0], line.coords[-1]):
            cum_cua_nut[_khoa_dinh(xy)] = c
    nut_nhanh = [cum_cua_nut[khoa] for khoa, n in bac.items() if n >= 3]

    return dict(
        lines=lines,
        cum=cum,
        nut_nhanh=nut_nhanh,
        nhanh=len(nut_nhanh),
        vong=sum(1 for line in lines if line.is_closed),
        so_rau=so_rau,
    )


def noi_chieu_cac_cum_tim(lines_theo_manh, cum, dem_thua):
    """
    Dinh huong lai cac cum tim roi nhau (moi cum 1 manh co thua) cho noi tiep.

    Moi manh da duoc dinh huong rieng theo 4 huong; tuyen cong bi dut tim
    (vd. qua giao lo) co the co doan sau bi lat chieu, lam dao TRAI/PHAI ca
    doan. Lay manh nhieu thua nhat lam goc, noi dan cac manh con lai vao dau
    hoac cuoi chuoi theo khoang cach dau mut. Cum co nhieu manh (phan nhanh)
    giu huong rieng tung manh.
    """
    so_manh = {}
    for i in lines_theo_manh:
        so_manh[cum[i]] = so_manh.get(cum[i], 0) + 1
    don = [i for i in lines_theo_manh if so_manh[cum[i]] == 1]

    if len(don) < 2:
        return lines_theo_manh

    goc = max(don, key=lambda i: (dem_thua[i], lines_theo_manh[i].length, -i))
    dau = Point(lines_theo_manh[goc].coords[0])
    cuoi = Point(lines_theo_manh[goc].coords[-1])
    con_lai = set(don) - {goc}

    def khoang_cach(i):
        line = lines_theo_manh[i]
        a, b = Point(line.coords[0]), Point(line.coords[-1])
        return min(a.distance(cuoi), b.distance(cuoi), a.distance(dau), b.distance(dau))

    while con_lai:
        i = min(con_lai, key=lambda k: (khoang_cach(k), k))
        con_lai.remove(i)
        line = lines_theo_manh[i]
        a, b = Point(line.coords[0]), Point(line.coords[-1])

        if min(a.distance(cuoi), b.distance(cuoi)) <= min(a.distance(dau), b.distance(dau)):
            # Noi vao cuoi chuoi: dau manh phai gan cuoi chuoi.
            if b.distance(cuoi) < a.distance(cuoi):
                line = dao_line(line)
            cuoi = Point(line.coords[-1])
        else:
            # Noi vao dau chuoi: cuoi manh phai gan dau chuoi.
            if a.distance(dau) < b.distance(dau):
                line = dao_line(line)
            dau = Point(line.coords[0])

        lines_theo_manh[i] = line

    return lines_theo_manh


def ben_theo_dai_dem_tim(geom, line, m_tim, d_min):
    """
    Ben TRAI/PHAI cua thua theo dien tich nam trong dai dem mot phia cua tim.

    Dung doan tim quanh thua (khong chi tiep tuyen tai diem gan nhat) nen
    on dinh o khuc gap va dinh goc nhon, noi huong tiep tuyen doi dot ngot.
    Tra ve (ben, tin_cay) voi tin_cay = |trai - phai| / (trai + phai);
    (None, 0) neu thua khong cham dai dem nao (vd. nam sau dau tim).
    """
    rong = d_min + BEN_TIM_DAI_DEM_M
    minx, miny, maxx, maxy = geom.bounds
    ban_kinh = math.hypot(maxx - minx, maxy - miny) + rong
    doan = substring(line, max(0.0, m_tim - ban_kinh), min(line.length, m_tim + ban_kinh))
    if doan.is_empty or doan.length <= 0:
        return None, 0.0
    try:
        trai = geom.intersection(doan.buffer(rong, single_sided=True)).area
        phai = geom.intersection(doan.buffer(-rong, single_sided=True)).area
    except Exception:
        return None, 0.0
    tong = trai + phai
    if tong <= 1e-9:
        return None, 0.0
    return (GT_TRAI if trai > phai else GT_PHAI), abs(trai - phai) / tong


def do_thua_theo_tim(geom, line, huong):
    """
    Do 1 thua so voi tim duong da dinh huong.

    Ghi ra dung cac cot ma che do polygon dung de sap thu tu:
    - diem mat duong (_xMatDuong) = diem cua thua gan tim nhat, tuong duong
      diem tiep giap mep duong o che do polygon;
    - _viTriBien = chainage giua mat tien tren tim, _chuViBien = inf
      (chuoi ho: _sap_xep_vong_bien cat tai khe wrap nen thu tu tuyen tinh).
    """
    p, p_tim = nearest_points(geom, line)
    m_tim = float(line.project(p_tim))

    # Mat tien = phan bien thua gan tim nhat.
    d_min = float(geom.distance(line))
    try:
        mat_tien = geom.boundary.intersection(
            line.buffer(d_min + MAT_TIEN_TIM_BAND_M)
        )
        cac_doan = lay_cac_line(mat_tien)
    except Exception:
        cac_doan = []

    diem_giua = p
    do_song_song = 1.0

    if cac_doan:
        gop = shapely.MultiLineString(cac_doan)
        diem_giua = gop.centroid
        if diem_giua.is_empty:
            diem_giua = p
        dai_nhat = max(cac_doan, key=lambda g: g.length)
        a, b = dai_nhat.coords[0], dai_nhat.coords[-1]
        tx, ty = tangent_cuc_bo_on_dinh(line, m_tim)
        if math.dist(a, b) > 1e-9:
            do_song_song = _cos_song_song(b[0] - a[0], b[1] - a[1], tx, ty)

    m_giua = float(line.project(diem_giua))
    vi_tri_bien = vi_tri_sap_xep_endpoint(line, diem_giua, m_giua)
    m_sap = vi_tri_sap_xep_endpoint(line, p, m_tim)

    side, tin_cay_ben = ben_theo_dai_dem_tim(geom, line, m_tim, d_min)
    if side is None:
        dx, dy = tangent_cuc_bo_on_dinh(line, m_tim)

        try:
            side_probe = geom.representative_point()
        except Exception:
            side_probe = geom.centroid

        wx = side_probe.x - p_tim.x
        wy = side_probe.y - p_tim.y
        cross = dx * wy - dy * wx

        norm_t = math.hypot(dx, dy)
        norm_w = math.hypot(wx, wy)
        if norm_t > 1e-12 and norm_w > 1e-12:
            tin_cay_ben = min(1.0, abs(cross) / (norm_t * norm_w))
        else:
            tin_cay_ben = 0.0
        tin_cay_ben *= 0.55 + 0.45 * max(0.0, min(1.0, float(do_song_song)))

        side = GT_TRAI if cross > 0 else GT_PHAI

    try:
        lech_bien = float(line.project(geom.centroid)) - m_giua
    except Exception:
        lech_bien = 0.0

    return dict(
        side=side,
        measure=m_sap,
        dist=d_min,
        x=float(p.x),
        y=float(p.y),
        vi_tri_bien=float(vi_tri_bien),
        lech_bien=lech_bien,
        score=diem_so_huong(diem_giua, huong),
        chu_vi_bien=float("inf"),
        vong_bien=0,
        song_song=float(do_song_song),
        canh_mat_tien=-1,
        cach_mat_tien="TIM_DUONG",
        tin_cay_ben=float(tin_cay_ben),
        cach_chieu="TIM_DUONG",
        doan_tham=-1,
    )


# Gia tri do cua thua khong gan duoc vao manh co reference line.
DO_THUA_LOI = dict(
    side=None, manh=None, measure=float("nan"), dist=float("nan"),
    x=float("nan"), y=float("nan"), vi_tri_bien=float("nan"), lech_bien=0.0,
    score=float("nan"), chu_vi_bien=float("nan"), vong_bien=-1, song_song=0.0,
    canh_mat_tien=-1, cach_mat_tien="LOI", tin_cay_ben=0.0, cach_chieu="LOI",
    doan_tham=-1,
)

# Cot noi bo cua group <- khoa trong dict do thua.
COT_DO_THUA = {
    COL_BEN: "side",
    "_manhDuong": "manh",
    "_measure": "measure",
    "_dist_line": "dist",
    "_xMatDuong": "x",
    "_yMatDuong": "y",
    "_viTriBien": "vi_tri_bien",
    "_lechBien": "lech_bien",
    "_scoreThuTu": "score",
    "_chuViBien": "chu_vi_bien",
    "_vongBien": "vong_bien",
    "_songSong": "song_song",
    "_canhMatTien": "canh_mat_tien",
    "_cachMatTien": "cach_mat_tien",
    "_tinCayBen": "tin_cay_ben",
    "_cachChieu": "cach_chieu",
    "_doanTham": "doan_tham",
}


def do_thua_theo_polygon(geom, poly, line, huong):
    """
    Do 1 thua so voi 1 manh polygon road va reference line cua manh do:
    diem mat tien tren bien road, ben TRAI/PHAI, chainage tren vong bien.
    """
    # MAT TIEN phai nam tren CANH DOC TUYEN,
    # tranh bat nham end-cap/canh ngang tai giao lo.
    (
        p,
        p_road,
        do_song_song,
        canh_mat_tien,
        cach_mat_tien,
    ) = lay_diem_mat_tien(
        geom,
        poly,
        line=line,
    )

    if p is None or p.is_empty:
        try:
            p = geom.representative_point()
        except Exception:
            p = geom.centroid

    if p_road is None or p_road.is_empty:
        try:
            _, p_road = nearest_points(
                p,
                poly.boundary,
            )
        except Exception:
            p_road = p

    # V3: khong dung line.project(p) truc tiep o khuc cua gap.
    # Chieu p_road vao segment co "loi di" nam trong polygon road.
    m_thuc, proj_point, cach_chieu, chi_so_seg = (
        chieu_diem_vao_line_theo_long_duong(
            line,
            poly,
            p_road,
        )
    )

    if m_thuc is None or proj_point is None:
        m_thuc = float(line.project(p))
        proj_point = line.interpolate(m_thuc)
        cach_chieu = "PROJECT"
        chi_so_seg = -1

    # Chi de SAP THU TU khi bi kep endpoint.
    # Dung diem thua p de giu thong tin vi tri doc mat tien khi nam qua endpoint.
    m_sap = vi_tri_sap_xep_endpoint(
        line,
        p,
        m_thuc,
    )

    # Tangent reference line chi dung de dinh CHIEU tangent bien road.
    dx_ref, dy_ref = tangent_cuc_bo_on_dinh(
        line,
        m_thuc,
    )

    # Nguyen tac:
    # - tangent boundary tot khi p_road nam tren canh doc tuyen;
    # - neu tangent boundary lech qua nhieu voi reference tangent,
    #   dung reference tangent de tranh lat TRAI/PHAI o end-cap/giao lo.
    dx_bien, dy_bien = tangent_bien_duong(
        poly,
        p_road,
        tangent_tham_chieu=(dx_ref, dy_ref),
    )

    song_song_tangent = _cos_song_song(
        dx_bien,
        dy_bien,
        dx_ref,
        dy_ref,
    )

    if song_song_tangent >= 0.55:
        dx, dy = dx_bien, dy_bien
    else:
        dx, dy = dx_ref, dy_ref

    try:
        side_probe = geom.representative_point()
    except Exception:
        side_probe = geom.centroid

    wx = side_probe.x - p_road.x
    wy = side_probe.y - p_road.y

    if math.hypot(wx, wy) <= 1e-9:
        cp = geom.centroid
        wx = cp.x - p_road.x
        wy = cp.y - p_road.y

    cross = dx * wy - dy * wx

    # Tin cay side = |sin(goc)| giua tangent va vector vao thua,
    # ket hop chat luong frontage.
    norm_t = math.hypot(dx, dy)
    norm_w = math.hypot(wx, wy)

    if norm_t > 1e-12 and norm_w > 1e-12:
        tin_cay_ben = min(
            1.0,
            abs(cross) / (norm_t * norm_w),
        )
    else:
        tin_cay_ben = 0.0

    tin_cay_ben *= 0.55 + 0.45 * max(
        0.0,
        min(1.0, float(do_song_song)),
    )

    if cach_mat_tien != "DOC_TUYEN":
        tin_cay_ben *= 0.75

    if cross > 0:
        side = GT_TRAI

    elif cross < 0:
        side = GT_PHAI

    else:
        cp = geom.centroid

        wx2 = cp.x - p_road.x
        wy2 = cp.y - p_road.y

        cross2 = dx * wy2 - dy * wx2

        side = GT_TRAI if cross2 > 0 else GT_PHAI

    kc = float(p_road.distance(proj_point))

    # Vi tri MAT DUONG tren boundary polygon la khoa thu tu chinh.
    vi_tri_bien, chu_vi_bien, vong_bien = vi_tri_diem_tren_bien_duong(
        poly,
        p_road,
    )

    # Thua co mat tien dai: vi tri thu tu lay o GIUA mat tien.
    p_giua = diem_giua_mat_tien_dai(geom, poly)

    if p_giua is not None:
        vi_tri_bien, chu_vi_bien, vong_bien = vi_tri_diem_tren_bien_duong(
            poly,
            p_giua,
        )

    return dict(
        side=side,
        measure=m_sap,
        dist=kc,
        x=float(p_road.x),
        y=float(p_road.y),
        vi_tri_bien=vi_tri_bien,
        lech_bien=vi_tri_lech_phu_tren_bien(
            poly,
            vong_bien,
            geom,
            vi_tri_bien,
            chu_vi_bien,
        ),
        score=diem_so_huong(p_giua if p_giua is not None else p_road, huong),
        chu_vi_bien=chu_vi_bien,
        vong_bien=vong_bien,
        song_song=float(do_song_song),
        canh_mat_tien=int(canh_mat_tien),
        cach_mat_tien=cach_mat_tien,
        tin_cay_ben=float(tin_cay_ben),
        cach_chieu=cach_chieu,
        doan_tham=int(chi_so_seg),
    )


def process(houses, roads, verbose=True, reference_roads=None, alley_contexts=None):
    from route_catalog import (
        FIELD_ALLEY, route_key_series, route_label, validate_route_schema,
    )
    hierarchical = validate_route_schema(houses, roads)

    houses = houses.copy()
    roads = roads.copy()

    kiem_tra_he_toa_do(houses, roads)

    from alley_numbering import prepare_alleys, number_alley, format_house_numbers

    if alley_contexts is None:
        reference_roads = roads if reference_roads is None else reference_roads
        kiem_tra_he_toa_do(houses, reference_roads)
        reference_hierarchical = validate_route_schema(houses, reference_roads)
        if reference_hierarchical != hierarchical:
            raise ValueError("Schema tenHem của dữ liệu chạy và dữ liệu tham chiếu không đồng nhất.")
        candidate_house_keys = route_key_series(houses, hierarchical)
        candidate_road_keys = set(route_key_series(roads, hierarchical))
        names = list(dict.fromkeys(key for key in candidate_house_keys if key in candidate_road_keys))
        alley_contexts, _, errors = prepare_alleys(names, reference_roads, hierarchical)
        if errors:
            raise ValueError("\n".join(errors))

    house_keys = route_key_series(houses, hierarchical)
    road_keys = route_key_series(roads, hierarchical)
    route_names = {}
    alley_values = houses[FIELD_ALLEY] if hierarchical else [""] * len(houses)
    for key, parent, alley in zip(house_keys, houses[FIELD_ROUTE], alley_values):
        if key != ("", ""):
            route_names.setdefault(key, route_label(parent, alley))

    houses[COL_BEN] = None
    houses[COL_STT] = None
    houses[COL_SONHA] = None
    houses[COL_HUONG] = None

    houses["_khoa"] = house_keys
    roads["_khoa"] = road_keys

    results = []
    debug_lines = []
    debug_access = []

    for road_key, group in houses.groupby("_khoa", dropna=False):
        group = group.copy()

        road_name = route_names.get(road_key, "(KHONG CO GIA TRI DOI CHIEU)")

        if verbose:
            print("\n" + "=" * 70)
            print("DANG XU LY:", road_name)
            print("So thua:", len(group))

        if road_key == ("", ""):
            if verbose:
                print(f">> Khong co gia tri {FIELD_ROUTE} -> giu nguyen")
            results.append(group)
            continue

        road = roads[roads["_khoa"] == road_key]

        if verbose:
            print("So doi tuong duong:", len(road))

        if road.empty:
            if verbose:
                print(">> Khong tim thay duong tuong ung")
            results.append(group)
            continue

        if road_key in alley_contexts:
            results.append(number_alley(group, alley_contexts[road_key]))
            continue

        kieu = kieu_hinh_hoc_tuyen(road.geometry)

        if kieu == KIEU_LAN:
            if verbose:
                print(">> Tuyen lan Polygon va LineString -> giu nguyen")
            results.append(group)
            continue

        if kieu == KIEU_TIM:
            tim = phan_tich_tim_duong(road.geometry)

            if not tim["lines"]:
                if verbose:
                    print(">> Tim duong rong -> giu nguyen")
                results.append(group)
                continue

            # Che do tim: moi "manh" la 1 doan tim giua hai nut, cung la
            # reference line. Nhanh re duoc danh nhu manh polygon rieng.
            polys = tim["lines"]
        else:
            polys = tach_polygon_components(road.geometry)

        if not polys:
            if verbose:
                print(">> Khong co Polygon/MultiPolygon")
            results.append(group)
            continue

        gan_manh, thua_theo_manh, dem_thua = gan_thua_vao_manh(
            polys,
            group,
        )

        manh_co_thua = [i for i, n in enumerate(dem_thua) if n > 0]

        if kieu == KIEU_TIM and any(polys[i].is_closed for i in manh_co_thua):
            if verbose:
                print(">> Tim khep vong co thua -> giu nguyen")
            results.append(group)
            continue

        if verbose:
            print("Tong polygon road:", len(polys))
            print(
                "Polygon co thua:",
                [i + 1 for i in manh_co_thua],
            )

        # ----------------------------------------------------
        # Tao reference line RIENG cho tung manh co thua.
        # ----------------------------------------------------
        lines_theo_manh = {}

        for manh_idx in manh_co_thua:
            if kieu == KIEU_TIM:
                lines_theo_manh[manh_idx] = polys[manh_idx]
                continue

            poly = polys[manh_idx]

            try:
                line = truc_cong_tu_polygon(poly)

                if (
                    line is None
                    or line.is_empty
                    or line.geom_type != "LineString"
                    or line.length <= 0
                ):
                    line = truc_dai_tu_polygon(poly)

            except Exception as e:
                if verbose:
                    print(
                        f">> Manh {manh_idx + 1} loi reference line:",
                        type(e).__name__,
                        e,
                    )
                continue

            if line is not None and line.length > 0:
                lines_theo_manh[manh_idx] = line

        if not lines_theo_manh:
            if verbose:
                print(">> Khong tao duoc reference line cho tuyen")
            results.append(group)
            continue

        # Neu co thua gan vao manh khong tao duoc line -> khong duoc bo thua.
        manh_loi = [i for i in manh_co_thua if i not in lines_theo_manh]

        if manh_loi:
            if verbose:
                print(
                    ">> CANH BAO: manh co thua nhung khong tao duoc line:",
                    [i + 1 for i in manh_loi],
                    "-> giu nguyen ca tuyen de tranh danh sai",
                )
            results.append(group)
            continue

        # ----------------------------------------------------
        # Xac dinh 4 huong CHUNG cua tuyen.
        # ----------------------------------------------------
        try:
            huong, goc = xac_dinh_huong(
                group,
                list(lines_theo_manh.values()),
                theo_tim=(kieu == KIEU_TIM),
            )
        except Exception as e:
            if verbose:
                print(">> Loi xac dinh huong:", e)
            results.append(group)
            continue

        # ====================================================
        # KHONG SAP TOPOLOGY POLYGON DE DANH SO
        # ====================================================
        #
        # Khong de thu tu so nha phu thuoc vao:
        #     cum polygon -> thuTuDoan -> measure
        #
        # O giao lo, polygon road bi cat phuc tap nen thuTuDoan co the sai.
        #
        # Nguyen tac:
        # - moi reference line CHI phuc vu projection/tangent cuc bo;
        # - KHONG dung polygon component de quyet dinh thu tu so;
        # - thu tu cuoi cung se duoc tao tu DAY DIEM MAT DUONG cua chinh cac thua.
        # ====================================================

        # Orient moi reference line mot lan theo 4 huong de tangent tham chieu
        # co chieu on dinh. Khong suy component nao noi component nao.
        for manh_idx in list(lines_theo_manh.keys()):
            lines_theo_manh[manh_idx] = chuan_hoa_chieu_line(
                lines_theo_manh[manh_idx],
                huong,
            )

        if kieu == KIEU_TIM:
            lines_theo_manh = noi_chieu_cac_cum_tim(lines_theo_manh, tim["cum"], dem_thua)

        if verbose:
            print(
                "HUONG:",
                huong,
                "| goc:",
                round(goc, 2),
            )
            print(
                "Thu tu nha tao tu diem mat duong cua cac thua; "
                "khong dung thuTuDoan polygon de danh so."
            )

        # Debug reference line: giu tung manh rieng, khong noi gia.
        for tt, manh_idx in enumerate(
            sorted(lines_theo_manh.keys()),
            start=1,
        ):
            line_dbg = lines_theo_manh[manh_idx]

            debug_lines.append(
                {
                    "tenDuong": road_name,
                    "huong": huong,
                    "manhDuong": manh_idx + 1,
                    "soThua": dem_thua[manh_idx],
                    "doDai": round(float(line_dbg.length), 3),
                    "geometry": line_dbg,
                }
            )

        # ----------------------------------------------------
        # Tinh cho tung thua.
        # ----------------------------------------------------
        do_list = []

        for idx, geom in zip(group.index, group.geometry):
            manh_idx = gan_manh.get(idx)

            if manh_idx not in lines_theo_manh:
                do_list.append(dict(DO_THUA_LOI))
                continue

            if kieu == KIEU_TIM:
                do = do_thua_theo_tim(geom, lines_theo_manh[manh_idx], huong)
            else:
                do = do_thua_theo_polygon(
                    geom,
                    polys[manh_idx],
                    lines_theo_manh[manh_idx],
                    huong,
                )
            do["manh"] = int(manh_idx)
            do_list.append(do)

        da_do = [do for do in do_list if do["manh"] is not None]
        dem_chieu_trong_duong = sum(do["cach_chieu"] == "TRONG_DUONG" for do in da_do)
        dem_chieu_du_phong = len(da_do) - dem_chieu_trong_duong

        for cot, khoa in COT_DO_THUA.items():
            group[cot] = [do[khoa] for do in do_list]

        group["_gocNhanh"] = False
        if kieu == KIEU_TIM and len(polys) > 1:
            geoms = group.geometry.to_numpy()
            khoang = np.column_stack([shapely.distance(geoms, line) for line in polys])
            for vi_tri, idx in enumerate(group.index):
                manh_idx = gan_manh.get(idx)
                if manh_idx is None or not np.isfinite(khoang[vi_tri, manh_idx]):
                    continue
                khac = np.delete(khoang[vi_tri], manh_idx)
                group.at[idx, "_gocNhanh"] = bool(
                    len(khac) and np.nanmin(khac) <= khoang[vi_tri, manh_idx] + TIM_THUA_GOC_M
                )

        group[COL_HUONG] = huong

        # ----------------------------------------------------
        # Nguyen tac: chia cum bang DIEM MAT DUONG CUA THUA, khong bang polygon road.
        # ----------------------------------------------------
        map_cum, nguong_tach, canh_bi_cat = chia_cum_thua_theo_mat_duong(group)

        group["_cumThua"] = [map_cum.get(idx) for idx in group.index]

        # ====================================================
        # HAU KIEM TRAI/PHAI BANG TIEP GIAP THUA
        # ====================================================
        group, adj_tiep_giap, ds_sua_ben = hau_kiem_ben_theo_tiep_giap(
            group,
            verbose=verbose,
            tin_cay_giu_ben=BEN_TIM_TIN_CAY_GIU if kieu == KIEU_TIM else None,
        )

        # ====================================================
        # HAU KIEM CAP THUA CUOI CUC BAO THU:
        # CHI SUA CAP TERMINAL DOI BEN DOI XUNG (KIEU 23/60)
        # ====================================================
        group, ds_sua_cap = hau_kiem_cap_terminal_hoan_doi(
            group,
            adj_tiep_giap,
            verbose=verbose,
        )

        if verbose:
            print(
                "Nguong tach cum thua:",
                "INF" if math.isinf(nguong_tach) else round(nguong_tach, 2),
                "m",
            )
            if canh_bi_cat:
                print(
                    "Gap lon tach cum:",
                    [round(d, 2) for d, _, _ in canh_bi_cat],
                )

        chua_xu_ly = int(group[COL_BEN].isna().sum())

        if verbose:
            print(
                f"Ben {GT_TRAI}:",
                int((group[COL_BEN] == GT_TRAI).sum()),
                "|",
                f"Ben {GT_PHAI}:",
                int((group[COL_BEN] == GT_PHAI).sum()),
                "| chua xu ly:",
                chua_xu_ly,
            )
            print(
                "Chieu frontage -> reference line:",
                dem_chieu_trong_duong,
                "TRONG_DUONG |",
                dem_chieu_du_phong,
                "DU_PHONG/PROJECT",
            )

        # Thua chua xu ly van nam trong group va se duoc append 1 lan o cuoi.
        # Khong append rieng de tranh trung record.

        # ====================================================
        # HAU KIEM TOPOLOGY THUA
        # ====================================================
        #
        # 1. MST chi dung de tach cum khi gap thua rat lon.
        # 2. Trong tung ben:
        #       component/ring -> chainage tren BIEN polygon road.
        # 3. _measure reference line chi con la debug/fallback.
        # 4. Khong cho projection centerline dao 9/11, 17/19 nua.
        # ====================================================

        # ====================================================
        # DANH SO LAN 1 BANG LOGIC CHINH
        # ====================================================
        group = danh_so_lai_theo_logic_chinh(
            group,
            huong,
            adj_tiep_giap,
            verbose=verbose,
        )

        # ====================================================
        # HAU KIEM SAU KHI DA CO SO:
        # neu 2 TAIL bi GAN CHÉO ro rang, swap DUNG CAP TAIL.
        # ====================================================
        group, ds_sua_duoi = hau_kiem_hoan_doi_cap_cuoi_sau_danh_so(
            group,
            verbose=verbose,
        )

        # Neu co swap side -> danh so lai 1 lan.
        if ds_sua_duoi:
            if verbose:
                print(">> Co swap cap cuoi day -> danh so lai")

            group = danh_so_lai_theo_logic_chinh(
                group,
                huong,
                adj_tiep_giap,
                verbose=False,
            )

        # Debug access SAU KHI da biet cum va so nha.
        for idx, row in group.iterrows():
            if pd.isna(row.get("_xMatDuong")) or pd.isna(row.get("_yMatDuong")):
                continue

            debug_access.append(
                {
                    "tenDuong": road_name,
                    "cumThua": (
                        int(row["_cumThua"]) if not pd.isna(row["_cumThua"]) else -1
                    ),
                    "manhDuong": (
                        int(row["_manhDuong"] + 1)
                        if not pd.isna(row["_manhDuong"])
                        else -1
                    ),
                    "traiPhai": row[COL_BEN],
                    "benGoc": (
                        row["_benHinhHoc"]
                        if "_benHinhHoc" in row.index
                        else row[COL_BEN]
                    ),
                    "suaBen": 1 if bool(row["_suaBen"]) else 0,
                    "suaCap": (
                        1 if ("_suaCap" in row.index and bool(row["_suaCap"])) else 0
                    ),
                    "suaDuoi": (
                        1 if ("_suaDuoi" in row.index and bool(row["_suaDuoi"])) else 0
                    ),
                    "benTruoc": (
                        row["_benTruocDuoi"]
                        if "_benTruocDuoi" in row.index
                        else (
                            row["_benTruocCap"]
                            if "_benTruocCap" in row.index
                            else row[COL_BEN]
                        )
                    ),
                    "lyDoSua": (
                        row["_lyDoDuoi"]
                        if "_lyDoDuoi" in row.index and row["_lyDoDuoi"]
                        else (row["_lyDoCap"] if "_lyDoCap" in row.index else "")
                    ),
                    "cumTiep": (
                        int(row["_cumTiepGiap"])
                        if not pd.isna(row["_cumTiepGiap"])
                        else -1
                    ),
                    "bacTiep": (
                        int(row["_bacTiepGiap"])
                        if not pd.isna(row["_bacTiepGiap"])
                        else 0
                    ),
                    "tinCayBen": (
                        round(float(row["_tinCayBen"]), 3)
                        if not pd.isna(row["_tinCayBen"])
                        else 0.0
                    ),
                    "thuTuDia": int(row[COL_STT]) if not pd.isna(row[COL_STT]) else -1,
                    "soNha": int(row[COL_SONHA]) if not pd.isna(row[COL_SONHA]) else -1,
                    "viTriDoan": (
                        round(float(row["_measure"]), 3)
                        if not pd.isna(row["_measure"])
                        else -1.0
                    ),
                    "viTriBien": (
                        round(float(row["_viTriBien"]), 3)
                        if not pd.isna(row["_viTriBien"])
                        else -1.0
                    ),
                    "vongBien": (
                        int(row["_vongBien"]) if not pd.isna(row["_vongBien"]) else -1
                    ),
                    "songSong": (
                        round(float(row["_songSong"]), 3)
                        if not pd.isna(row["_songSong"])
                        else -1.0
                    ),
                    "canhMat": (
                        int(row["_canhMatTien"])
                        if not pd.isna(row["_canhMatTien"])
                        else -1
                    ),
                    "cachMat": row["_cachMatTien"],
                    "khoangCach": (
                        round(float(row["_dist_line"]), 3)
                        if not pd.isna(row["_dist_line"])
                        else -1.0
                    ),
                    "cachChieu": row["_cachChieu"],
                    "doanTham": int(row["_doanTham"]),
                    "geometry": Point(
                        float(row["_xMatDuong"]),
                        float(row["_yMatDuong"]),
                    ),
                }
            )

        # Append 1 lan ca group, tranh tach/ghep lai lam kho debug.
        results.append(group)

    if not results:
        raise ValueError("Khong co ket qua de ghep.")

    out = pd.concat(results, ignore_index=True)

    drop_cols = [
        c
        for c in [
            "_khoa",
            "_cumThua",
            "_manhDuong",
            "_measure",
            "_dist_line",
            "_xMatDuong",
            "_yMatDuong",
            "_viTriBien",
            "_lechBien",
            "_scoreThuTu",
            "_chuViBien",
            "_vongBien",
            "_songSong",
            "_canhMatTien",
            "_cachMatTien",
            "_tinCayBen",
            "_gocNhanh",
            "_benHinhHoc",
            "_suaBen",
            "_suaCap",
            "_benTruocCap",
            "_lyDoCap",
            "_suaDuoi",
            "_benTruocDuoi",
            "_lyDoDuoi",
            "_cumTiepGiap",
            "_bacTiepGiap",
            "_cachChieu",
            "_doanTham",
            "_thuTuNguon",
        ]
        if c in out.columns
    ]

    if drop_cols:
        out = out.drop(columns=drop_cols)

    out_gdf = gpd.GeoDataFrame(
        out,
        geometry="geometry",
        crs=houses.crs,
    )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------
    if verbose and debug_lines:
        try:
            dbg = gpd.GeoDataFrame(
                debug_lines,
                geometry="geometry",
                crs=houses.crs,
            )

            xoa_shapefile_cu(DEBUG_LINE_SHP)
            dbg.to_file(
                DEBUG_LINE_SHP,
                encoding="UTF-8",
            )

            print(
                "\nDEBUG reference line:",
                DEBUG_LINE_SHP,
            )

        except Exception as e:
            print(
                "CANH BAO: khong xuat duoc debug reference line:",
                type(e).__name__,
                e,
            )

    if verbose and debug_access:
        try:
            dbg = gpd.GeoDataFrame(
                debug_access,
                geometry="geometry",
                crs=houses.crs,
            )

            xoa_shapefile_cu(DEBUG_ACCESS_SHP)
            dbg.to_file(
                DEBUG_ACCESS_SHP,
                encoding="UTF-8",
            )

            print(
                "DEBUG access point:",
                DEBUG_ACCESS_SHP,
            )

        except Exception as e:
            print(
                "CANH BAO: khong xuat duoc debug access point:",
                type(e).__name__,
                e,
            )

    return format_house_numbers(out_gdf, alley_contexts)


# ============================================================
# MAIN
# ============================================================


def main():
    print("=" * 72)
    print(f"{CORE_NAME} CORE {CORE_VERSION} - DANH SO NHA")
    print(f"Output: {COL_BEN} | {COL_STT} | " f"{COL_SONHA} | {COL_HUONG}")
    print("=" * 72)

    houses = doc_lop(
        HOUSE_SHP,
        HOUSE_LAYER,
    )

    roads = doc_lop(
        ROAD_SHP,
        ROAD_LAYER,
    )

    print("So thua:", len(houses))
    print("So doi tuong duong:", len(roads))
    print(
        "Geometry duong:",
        roads.geometry.geom_type.value_counts().to_dict(),
    )
    print(
        "He toa do:",
        houses.crs.name if houses.crs is not None else "KHONG CO",
    )

    if TUYEN:
        ds = [t.strip() for t in TUYEN.split(";") if t.strip()]

        khoa_can = {khoa_ten(t) for t in ds}

        loc_nha = houses[FIELD_HOUSE_ROAD].map(khoa_ten).isin(khoa_can)

        loc_duong = roads[FIELD_ROAD_NAME].map(khoa_ten).isin(khoa_can)

        print(f"\nCHI chay tuyen: {', '.join(ds)}")

        print(f"  -> {loc_nha.sum()} thua, " f"{loc_duong.sum()} doi tuong duong")

        if loc_duong.sum() == 0:
            co_san = sorted(roads[FIELD_ROAD_NAME].dropna().astype(str).unique())

            raise ValueError(
                f"Khong tim thay tuyen '{TUYEN}'.\n"
                f"Ten duong co trong du lieu: {co_san[:30]}"
            )

        houses = houses[loc_nha].copy()
        roads = roads[loc_duong].copy()

    out = process(
        houses,
        roads,
        verbose=True,
    )

    thu_muc = os.path.dirname(OUTPUT_SHP)

    if thu_muc and not os.path.isdir(thu_muc):
        os.makedirs(
            thu_muc,
            exist_ok=True,
        )

    print("\n" + "=" * 70)
    print("KET QUA")
    print("=" * 70)

    print("Tong doi tuong:", len(out))
    print(
        f"Co {COL_BEN}:",
        int(out[COL_BEN].notna().sum()),
    )
    print(
        f"Co {COL_SONHA}:",
        int(out[COL_SONHA].notna().sum()),
    )
    print(
        f"Co {COL_HUONG}:",
        int(out[COL_HUONG].notna().sum()),
    )

    print("\n30 dong da danh:")

    co_so = out[COL_SONHA].notna()

    if co_so.any():
        print(
            out.loc[
                co_so,
                [
                    FIELD_HOUSE_ROAD,
                    COL_HUONG,
                    COL_BEN,
                    COL_STT,
                    COL_SONHA,
                ],
            ]
            .sort_values(
                [
                    FIELD_HOUSE_ROAD,
                    COL_BEN,
                    COL_STT,
                ]
            )
            .head(30)
            .to_string(index=False)
        )
    else:
        print("Khong co thua nao duoc danh so.")

    out_xuat = ten_truong_an_toan_shp(
        out,
        OUTPUT_SHP,
    )

    xoa_shapefile_cu(OUTPUT_SHP)

    out_xuat.to_file(
        OUTPUT_SHP,
        encoding="UTF-8",
    )

    print("\nDa luu:", OUTPUT_SHP)


if __name__ == "__main__":
    main()
