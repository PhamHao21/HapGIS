# -*- coding: utf-8 -*-

"""
Self-test cho HAPGIS Core 1.0.

Tach rieng regression test khoi core production.
Khong thay doi thuat toan; chi doi ten bai test theo chuc nang.
"""

import geopandas as gpd
from shapely.geometry import Point

from core_housenumber import (
    COL_BEN,
    COL_HUONG,
    COL_SONHA,
    COL_STT,
    GT_PHAI,
    GT_TRAI,
    chia_cum_thua_theo_mat_duong,
    tangent_bien_duong,
    thu_tu_thua_theo_bien_duong,
    hau_kiem_ben_theo_tiep_giap,
    tao_do_thi_tiep_giap_thua,
    hau_kiem_thu_tu_theo_tiep_giap,
    hau_kiem_cap_terminal_hoan_doi,
    hau_kiem_hoan_doi_cap_cuoi_sau_danh_so,
    gan_thua_vao_manh,
    diem_giua_mat_tien_dai,
)

def run_tests():
    from shapely.geometry import box

    print("=== TEST THU TU THEO BIEN DUONG ===")

    # D-T: diem x lon phai dung truoc.
    # _measure co tinh sai: 10,30,20,50,40 -> thu tu bien duong van phai dung.
    g = gpd.GeoDataFrame(
        {
            "_manhDuong": [0, 0, 0, 0, 0],
            "_vongBien": [0, 0, 0, 0, 0],
            "_viTriBien": [10, 20, 30, 40, 50],
            "_chuViBien": [200, 200, 200, 200, 200],
            "_measure": [10, 30, 20, 50, 40],
            "_dist_line": [1, 1, 1, 1, 1],
            "_xMatDuong": [100, 90, 80, 70, 60],
            "_yMatDuong": [0, 0, 0, 0, 0],
        },
        index=[1, 2, 3, 4, 5],
        geometry=[Point(x, 0) for x in [100, 90, 80, 70, 60]],
        crs="EPSG:3857",
    )

    order, info = thu_tu_thua_theo_bien_duong(g, "D-T")
    assert order == [1, 2, 3, 4, 5], order
    print("Order:", order)
    print("=> KHONG BI _MEASURE DAO PASS")

    print("\n=== TEST RING WRAP 0/L ===")

    # Vi tri tren ring: 95,98,2,5 la mot day lien tuc qua moc 0.
    g2 = gpd.GeoDataFrame(
        {
            "_manhDuong": [0, 0, 0, 0],
            "_vongBien": [0, 0, 0, 0],
            "_viTriBien": [95, 98, 2, 5],
            "_chuViBien": [100, 100, 100, 100],
            "_measure": [1, 2, 3, 4],
            "_dist_line": [1, 1, 1, 1],
            "_xMatDuong": [100, 90, 80, 70],
            "_yMatDuong": [0, 0, 0, 0],
        },
        index=[10, 11, 12, 13],
        geometry=[Point(x, 0) for x in [100, 90, 80, 70]],
        crs="EPSG:3857",
    )

    order2, info2 = thu_tu_thua_theo_bien_duong(g2, "D-T")
    assert order2 == [10, 11, 12, 13], order2
    print("Order:", order2)
    print("=> RING WRAP PASS")

    print("\n=== TEST TACH GAP LON, GIU GAP GIAO LO ===")

    xs = [0, 10, 20, 60, 70, 80, 900, 910]
    group = gpd.GeoDataFrame(
        {
            COL_HUONG: ["D-T"] * len(xs),
            "_xMatDuong": xs,
            "_yMatDuong": [0.0] * len(xs),
        },
        geometry=[Point(x, 0) for x in xs],
        crs="EPSG:3857",
    )

    mapping, threshold, cuts = chia_cum_thua_theo_mat_duong(group)
    assert len({mapping[i] for i in range(6)}) == 1
    assert mapping[6] == mapping[7]
    assert mapping[6] != mapping[0]
    print("=> GAP CLUSTER PASS")

    print("\n=== TEST TRAI/PHAI BIEN ROAD ===")

    poly = box(0, -5, 100, 5)

    p_top = Point(50, 5)
    dx, dy = tangent_bien_duong(
        poly,
        p_top,
        tangent_tham_chieu=(-1.0, 0.0),
    )
    cross_top = dx * 10.0 - dy * 0.0
    assert cross_top < 0

    p_bottom = Point(50, -5)
    dx2, dy2 = tangent_bien_duong(
        poly,
        p_bottom,
        tangent_tham_chieu=(-1.0, 0.0),
    )
    cross_bottom = dx2 * (-10.0) - dy2 * 0.0
    assert cross_bottom > 0

    print("=> SIDE PASS")

    print("\n=== TEST SUA SIDE OUTLIER THEO DAY THUA ===")

    boxes = [box(i * 10, 0, (i + 1) * 10, 10) for i in range(5)]

    g3 = gpd.GeoDataFrame(
        {
            "_cumThua": [1, 1, 1, 1, 1],
            COL_BEN: [
                GT_PHAI,
                GT_PHAI,
                GT_TRAI,
                GT_PHAI,
                GT_PHAI,
            ],
        },
        geometry=boxes,
        crs="EPSG:3857",
    )

    g3_fix, adj3, sua3 = hau_kiem_ben_theo_tiep_giap(
        g3,
        verbose=False,
    )

    assert g3_fix.iloc[2][COL_BEN] == GT_PHAI
    assert len(sua3) == 1
    print("=> SIDE OUTLIER PASS")

    print("\n=== TEST CHUOI TIEP GIAP SUA 7-11-9 ===")

    g4 = gpd.GeoDataFrame(
        {COL_BEN: [GT_TRAI] * 5},
        geometry=boxes,
        crs="EPSG:3857",
    )

    adj4 = tao_do_thi_tiep_giap_thua(g4)

    # Thu tu co so co tinh sai: 0,2,1,3,4
    base4 = [0, 2, 1, 3, 4]

    order4, info4 = hau_kiem_thu_tu_theo_tiep_giap(
        g4,
        base4,
        adj4,
    )

    assert order4 == [0, 1, 2, 3, 4], order4
    print("Order:", order4)
    print("=> TOPOLOGY ORDER PASS")

    print("\n=== TEST CAP THUA CUOI DOI BEN DOI XUNG ===")

    # 2 day on dinh song song theo huong D-T.
    # Candidate A dang TRAI nhung nam sat endpoint PHAI.
    # Candidate B dang PHAI nhung nam sat endpoint TRAI.
    geoms = []
    sides = []
    cum_thua = []

    # Day TRAI y=20, cac thua noi ranh that:
    # 92-100 | 84-92 | 76-84 | 68-76
    for x0 in [92, 84, 76, 68]:
        geoms.append(box(x0, 18, x0 + 8, 22))
        sides.append(GT_TRAI)
        cum_thua.append(1)

    # Day PHAI y=0, cung cau truc.
    for x0 in [92, 84, 76, 68]:
        geoms.append(box(x0, -2, x0 + 8, 2))
        sides.append(GT_PHAI)
        cum_thua.append(1)

    # A: nam noi tiep day PHAI nhung cach endpoint 1m,
    # graph tiep giap khong noi (nguong gap chi 0.25m).
    # Side co tinh gan sai = TRAI.
    geoms.append(box(59, -2, 67, 2))
    sides.append(GT_TRAI)
    cum_thua.append(1)

    # B: nam noi tiep day TRAI, cung cach 1m.
    # Side co tinh gan sai = PHAI.
    geoms.append(box(59, 18, 67, 22))
    sides.append(GT_PHAI)
    cum_thua.append(1)

    g5 = gpd.GeoDataFrame(
        {
            COL_BEN: sides,
            COL_HUONG: ["D-T"] * len(geoms),
            "_cumThua": cum_thua,
            "_xMatDuong": [float(g.representative_point().x) for g in geoms],
            "_yMatDuong": [float(g.representative_point().y) for g in geoms],
            "_suaBen": [False] * len(geoms),
        },
        geometry=geoms,
        crs="EPSG:3857",
    )

    # Tao graph tiep giap + gan cumTiep/bac qua hau kiem side.
    g5a, adj5, _ = hau_kiem_ben_theo_tiep_giap(
        g5,
        verbose=False,
    )

    # Hai candidate terminal phai chua bi hau kiem side sua.
    assert g5a.iloc[-2][COL_BEN] == GT_TRAI
    assert g5a.iloc[-1][COL_BEN] == GT_PHAI

    g5b, sua_cap = hau_kiem_cap_terminal_hoan_doi(
        g5a,
        adj5,
        verbose=False,
    )

    assert g5b.iloc[-2][COL_BEN] == GT_PHAI
    assert g5b.iloc[-1][COL_BEN] == GT_TRAI
    assert len(sua_cap) == 1

    print(
        "A:",
        GT_TRAI,
        "->",
        g5b.iloc[-2][COL_BEN],
        "| B:",
        GT_PHAI,
        "->",
        g5b.iloc[-1][COL_BEN],
    )
    print("=> TERMINAL PAIR SWAP PASS")

    print("\n=== TEST CAP CUOI DAY BI GAN CHEO ===")

    # Tao 2 day song song.
    # Day TRAI that o y=20, day PHAI that o y=0.
    geoms = []
    sides = []
    so_nha = []
    cum_thua = []

    # TRAI dung: 1,3,5,7
    for i, x0 in enumerate([40, 30, 20, 10]):
        geoms.append(box(x0, 18, x0 + 8, 22))
        sides.append(GT_TRAI)
        so_nha.append(2 * i + 1)
        cum_thua.append(1)

    # PHAI dung: 2,4,6,8
    for i, x0 in enumerate([40, 30, 20, 10]):
        geoms.append(box(x0, -2, x0 + 8, 2))
        sides.append(GT_PHAI)
        so_nha.append(2 * i + 2)
        cum_thua.append(1)

    # Tail vat ly PHAI nhung gan nham TRAI -> so le.
    geoms.append(box(0, -2, 8, 2))
    sides.append(GT_TRAI)
    so_nha.append(9)
    cum_thua.append(1)

    # Tail vat ly TRAI nhung gan nham PHAI -> so chan.
    geoms.append(box(0, 18, 8, 22))
    sides.append(GT_PHAI)
    so_nha.append(10)
    cum_thua.append(1)

    g6 = gpd.GeoDataFrame(
        {
            COL_BEN: sides,
            COL_SONHA: so_nha,
            COL_STT: [10 * (i + 1) for i in range(len(geoms))],
            COL_HUONG: ["D-T"] * len(geoms),
            "_cumThua": cum_thua,
            "_xMatDuong": [float(g.representative_point().x) for g in geoms],
            "_yMatDuong": [float(g.representative_point().y) for g in geoms],
            "_suaBen": [False] * len(geoms),
        },
        geometry=geoms,
        crs="EPSG:3857",
    )

    g6_fix, sua6 = hau_kiem_hoan_doi_cap_cuoi_sau_danh_so(
        g6,
        verbose=False,
    )

    assert len(sua6) == 1
    assert g6_fix.iloc[-2][COL_BEN] == GT_PHAI
    assert g6_fix.iloc[-1][COL_BEN] == GT_TRAI

    print(
        "tail le:",
        GT_TRAI,
        "->",
        g6_fix.iloc[-2][COL_BEN],
        "| tail chan:",
        GT_PHAI,
        "->",
        g6_fix.iloc[-1][COL_BEN],
    )
    print("=> FINAL TAIL CROSS-SWAP PASS")

    print("\n=== TEST THUA KEP GIUA HAI MANH ROAD ===")

    # Duong chinh (3 thua ro rang) va hem nho cung tuyen (1 thua ro rang).
    # 4 thua kep o giua cham CA HAI manh (khoang cach 0, representative point
    # cach deu): phai cung vao manh co nhieu thua ro rang hon.
    duong_chinh = box(-20, -100, 0, 100)
    hem_nho = box(20, -100, 22, 100)
    polys = [hem_nho, duong_chinh]
    hinh = [box(-10, y, -1, y + 10) for y in (-90, -75, -60)]
    hinh += [box(0, y, 20, y + 10) for y in (-30, -15, 0, 15)]
    hinh += [box(23, 50, 30, 60)]
    gg = gpd.GeoDataFrame(geometry=hinh, crs="EPSG:3857")
    gan, _, dem = gan_thua_vao_manh(polys, gg)
    assert [gan[i] for i in range(3, 7)] == [1, 1, 1, 1], gan
    assert dem == [1, 7], dem
    print("Gan:", gan)
    print("=> THUA KEP KHONG BI TACH DOI PASS")

    print("\n=== TEST HAI THUA CUNG CHAM 1 DINH BIEN DUONG ===")

    # Cung vi_tri_bien: thu tu phai theo lech than thua, khong theo id.
    g7 = gpd.GeoDataFrame(
        {
            "_manhDuong": [0, 0, 0],
            "_vongBien": [0, 0, 0],
            "_viTriBien": [10.0, 20.0, 20.0],
            "_lechBien": [0.0, 4.0, -4.0],
            "_chuViBien": [200, 200, 200],
            "_measure": [1, 2, 3],
            "_dist_line": [1, 1, 1],
            "_xMatDuong": [100, 90, 90],
            "_yMatDuong": [0, 0, 0],
        },
        index=[1, 2, 3],
        geometry=[Point(x, 0) for x in [100, 94, 86]],
        crs="EPSG:3857",
    )
    order, _ = thu_tu_thua_theo_bien_duong(g7, "D-T")
    assert order.index(3) < order.index(2), order
    print("Order:", order)
    print("=> THU TU CHAINAGE HOA KHONG THEO ID PASS")

    print("\n=== TEST DIEM GIUA MAT TIEN DAI ===")

    duong = box(-20, 0, 0, 200)
    lon = box(0, 10, 30, 110)  # mat tien thang 100 m
    p = diem_giua_mat_tien_dai(lon, duong)
    assert p is not None and abs(p.y - 60) < 0.5, p
    nho = box(0, 10, 5, 20)  # mat tien 10 m: giu cach chon cu
    assert diem_giua_mat_tien_dai(nho, duong) is None
    # thua goc ngoai: mat tien gap khuc quanh goc, khong lay diem giua
    goc_duong = box(-20, -20, 40, 0).union(box(-20, -20, 0, 200))
    goc = box(0, 0, 40, 40)
    assert diem_giua_mat_tien_dai(goc, goc_duong) is None
    print("=> DIEM GIUA CHI AP DUNG MAT TIEN THANG VA DAI PASS")

    print("\n=== SELF TEST HAPGIS CORE: PASS ===")

if __name__ == "__main__":
    run_tests()
