# -*- coding: utf-8 -*-
"""Main roads given as centerlines (LineString) instead of road-surface polygons."""
import math
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import substring

from app_service import chay_danh_so, kiem_tra_du_lieu
from core_housenumber import COL_BEN, COL_SONHA, process
from test_route_hierarchy import hierarchy_fixture

CRS = "EPSG:3405"  # VN-2000 projected, metres.
STRAIGHT = LineString([(0, 0), (120, 0)])
ELL = LineString([(0, 0), (80, 0), (80, 80)])
U_TURN = LineString([(0, 0), (100, 0), (100, 80), (0, 80)])
CURVE = LineString([(x, 15 * math.sin(x / 25)) for x in range(0, 161, 4)])


def street(path, angle=0, half=4, depth=12, width=8, gap=0.0):
    """
    Parcels on both sides of `path`, cut from offset curves so they never overlap.
    Returns (houses, road polygon, centerline); houses carry `ben` (+1/-1) and `hang`
    (rank along their side) as ground truth.
    """
    road = path.buffer(half, cap_style=2, join_style=2)
    rows = []
    for sign in (1, -1):
        inner = path.offset_curve(sign * (half + gap), join_style=2)
        outer = path.offset_curve(sign * (half + gap + depth), join_style=2)
        n = max(1, int(inner.length // width))
        for i in range(n):
            a = substring(inner, i / n, (i + 1) / n, normalized=True)
            b = substring(outer, i / n, (i + 1) / n, normalized=True)
            parcel = Polygon(list(a.coords) + list(b.coords)[::-1])
            if parcel.is_valid and parcel.area > 1:
                rows.append((sign, i, parcel))
    if gap >= 0:  # Drop the corner parcels that the offset construction makes overlap.
        kept = []
        for row in rows:
            if row[2].intersection(road).area < 1e-6 and all(
                    row[2].intersection(other[2]).area < 1e-6 for other in kept):
                kept.append(row)
        rows = kept
    geoms = [rotate(g, angle, origin=(0, 0)) for _, _, g in rows]
    houses = gpd.GeoDataFrame({"tenDuong": ["Đường A"] * len(rows), "ben": [r[0] for r in rows],
                               "hang": [r[1] for r in rows]}, geometry=geoms, crs=CRS)
    return houses, rotate(road, angle, origin=(0, 0)), rotate(path, angle, origin=(0, 0))


def roads_of(*geometries, names=None):
    return gpd.GeoDataFrame({"tenDuong": names or ["Đường A"] * len(geometries)},
                            geometry=list(geometries), crs=CRS)


def numbering(houses, roads):
    out = process(houses, roads, verbose=False)
    return list(zip(out[COL_BEN], out[COL_SONHA]))


class CenterlineNumberingTests(unittest.TestCase):
    def assert_follows_sides(self, houses, out):
        """Each generated side gets one TRAI/PHAI label; numbers run monotonically along it."""
        labels = {}
        for sign in (1, -1):
            side = houses.assign(ben_out=[b for b, _ in out], so=[int(n) for _, n in out])
            side = side[side.ben == sign].sort_values("hang")
            self.assertEqual(side.ben_out.nunique(), 1, side.ben_out.tolist())
            numbers = side.so.tolist()
            self.assertIn(numbers, (sorted(numbers), sorted(numbers, reverse=True)), numbers)
            parity = {n % 2 for n in numbers}
            self.assertEqual(parity, {1} if side.ben_out.iloc[0] == "TRAI" else {0})
            labels[sign] = side.ben_out.iloc[0]
        self.assertNotEqual(labels[1], labels[-1])

    def test_straight_and_curved_roads_match_polygon_mode(self):
        for path in (STRAIGHT, CURVE):
            for angle in (0, 30, 135, 290):
                for reverse in (False, True):
                    with self.subTest(path=path.length, angle=angle, reverse=reverse):
                        houses, road, line = street(path, angle)
                        if reverse:
                            line = LineString(line.coords[::-1])
                        polygon_out = numbering(houses, roads_of(road))
                        line_out = numbering(houses, roads_of(line))
                        self.assertEqual(line_out, polygon_out)
                        self.assert_follows_sides(houses, line_out)

    def test_l_shaped_centerline_keeps_each_side_in_order(self):
        for angle in (0, 30, 90, 200):
            with self.subTest(angle=angle):
                houses, _, line = street(ELL, angle)
                self.assert_follows_sides(houses, numbering(houses, roads_of(line)))

    def test_split_centerline_pieces_are_joined(self):
        houses, _, line = street(STRAIGHT)
        pieces = [LineString([(0, 0), (40, 0)]), LineString([(40.05, 0), (80, 0)]),
                  LineString([(120, 0), (80, 0.03)])]
        self.assertEqual(numbering(houses, roads_of(*pieces)), numbering(houses, roads_of(line)))
        self.assertEqual(numbering(houses, roads_of(MultiLineString(pieces))),
                         numbering(houses, roads_of(line)))
        report = kiem_tra_du_lieu(houses, roads_of(*pieces))
        self.assertEqual(report["errors"], [])
        self.assertFalse(any("nhiều cụm" in w for w in report["warnings"]))

    def test_broken_bending_centerline_keeps_sides_across_gap(self):
        # Like H9: a bending (here U-turn) route whose centerline breaks for 16 m. Each
        # piece used to be oriented on its own, flipping TRAI/PHAI on the far piece.
        for angle in (0, 30, 90, 135, 200, 290):
            with self.subTest(angle=angle):
                houses, _, _ = street(U_TURN, angle)
                pieces = [LineString([(0, 0), (100, 0), (100, 32)]), LineString([(100, 48), (100, 80), (0, 80)])]
                pieces = [rotate(p, angle, origin=(0, 0)) for p in pieces]
                self.assert_follows_sides(houses, numbering(houses, roads_of(*pieces)))

    def test_short_spurs_are_trimmed(self):
        # Polygon-to-centerline tools leave short dangles into junction mouths.
        houses, _, line = street(STRAIGHT)
        spurs = [LineString([(60, 0), (60, -10)]), LineString([(100, 0), (104, 9)])]
        roads = roads_of(line, *spurs)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertTrue(any("bỏ qua 2 râu" in d for d in report["details"]), report["details"])
        self.assertEqual(numbering(houses, roads), numbering(houses, roads_of(line)))

    def test_t_branch_is_numbered_with_warning(self):
        houses, _, _ = street(STRAIGHT)
        roads = roads_of(LineString([(0, 0), (150, 0)]), LineString([(124, 0), (124, 40)]))
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("phân nhánh ở đoạn có thửa" in w for w in report["warnings"]), report["warnings"])
        out = numbering(houses, roads)
        self.assertTrue(all(n is not None for _, n in out))
        self.assert_follows_sides(houses, out)

    def test_parcels_drawn_over_road_surface_still_numbered(self):
        # Parcels start 1 m from the centerline: 75% of each lies on the 8 m road surface.
        houses, road, line = street(STRAIGHT, gap=-3, depth=4)
        self.assertTrue(kiem_tra_du_lieu(houses, roads_of(road))["errors"])
        report = kiem_tra_du_lieu(houses, roads_of(line))
        self.assertEqual(report["errors"], [])
        self.assert_follows_sides(houses, numbering(houses, roads_of(line)))


class CenterlineValidationTests(unittest.TestCase):
    def setUp(self):
        self.houses, self.road, self.line = street(STRAIGHT)

    def report(self, roads, houses=None):
        return kiem_tra_du_lieu(self.houses if houses is None else houses, roads)

    def test_report_names_road_kind(self):
        report = self.report(roads_of(self.line))
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertTrue(any("0 tuyến polygon" in d and "1 tuyến polyline" in d for d in report["details"]))

    def test_disconnected_pieces_warn_but_still_number(self):
        pieces = [LineString([(0, 0), (55, 0)]), LineString([(60, 0), (120, 0)])]
        report = self.report(roads_of(*pieces))
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("nhiều cụm có thửa" in w for w in report["warnings"]))
        out = process(self.houses, roads_of(*pieces), verbose=False)
        self.assertTrue(out[COL_SONHA].notna().all())

    def test_centerline_crossing_parcel_is_error(self):
        houses = self.houses.copy()
        houses.loc[0, "geometry"] = translate(houses.geometry[0], yoff=-10)  # straddles y = 0
        errors = self.report(roads_of(self.line), houses)["errors"]
        self.assertTrue(any("cắt qua" in e and "dòng #0" in e for e in errors), errors)

    def test_closed_and_mixed_routes_are_errors(self):
        ring = roads_of(LineString([(0, 0), (120, 0), (120, 60), (0, 60), (0, 0)]))
        mixed = roads_of(LineString([(0, 0), (60, 0)]), self.road)
        for roads, text in ((ring, "khép kín"), (mixed, "lẫn polygon và polyline")):
            with self.subTest(text=text):
                errors = self.report(roads)["errors"]
                self.assertTrue(any(text in e for e in errors), errors)
                # The engine itself never numbers these routes either.
                self.assertTrue(process(self.houses, roads, verbose=False)[COL_SONHA].isna().all())

    def test_network_parts_without_parcels_are_ignored(self):
        # A loop and a branch far from every parcel of the route (H9 in testPD.gdb).
        far_ring = LineString([(0, 500), (60, 500), (60, 560), (0, 560), (0, 500)])
        far_branch = [LineString([(300, 0), (400, 0)]), LineString([(350, 0), (350, 50)])]
        roads = roads_of(self.line, far_ring, *far_branch)
        report = self.report(roads)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(numbering(self.houses, roads), numbering(self.houses, roads_of(self.line)))

    def test_alley_and_alley_parent_must_stay_polygons(self):
        houses, roads = hierarchy_fixture()
        main_line = LineString([(-20, -4), (20, -4)])
        with_line_parent = roads.copy()
        with_line_parent.loc[1, "geometry"] = main_line
        errors = kiem_tra_du_lieu(houses, with_line_parent)["errors"]
        self.assertTrue(any("đường cha" in e and "polyline" in e for e in errors), errors)

        line_alley = roads.copy()
        line_alley.loc[0, "geometry"] = LineString([(0, 0), (0, 60)])
        errors = kiem_tra_du_lieu(houses, line_alley)["errors"]
        self.assertTrue(any("hẻm phải vẽ bằng polygon" in e for e in errors), errors)


class CenterlineFileTests(unittest.TestCase):
    def test_run_from_gpkg_and_shapefile_line_layers(self):
        houses, road, line = street(STRAIGHT)
        expected = numbering(houses, roads_of(road))
        with tempfile.TemporaryDirectory() as tmp:
            gpkg = Path(tmp) / "data.gpkg"
            houses.to_file(gpkg, layer="parcels", driver="GPKG")
            roads_of(line).to_file(gpkg, layer="roads", driver="GPKG")
            shp = Path(tmp) / "tim.shp"
            roads_of(line).to_file(shp, encoding="UTF-8")
            for road_path, road_layer in ((gpkg, "roads"), (shp, None)):
                with self.subTest(source=road_path.suffix):
                    log = []
                    output = Path(tmp) / f"out_{road_path.stem}.gpkg"
                    chay_danh_so(str(gpkg), "parcels", str(road_path), road_layer, "", str(output),
                                 log=log.append)
                    saved = gpd.read_file(output)
                    self.assertEqual(list(zip(saved[COL_BEN], saved[COL_SONHA])), expected)
                    self.assertTrue(any("thử nghiệm" in line for line in log), log)


if __name__ == "__main__":
    unittest.main()
