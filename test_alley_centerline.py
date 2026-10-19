# -*- coding: utf-8 -*-
"""Alleys and their parent roads given as centerlines (LineString)."""
import unittest

import geopandas as gpd
from shapely.affinity import rotate
from shapely.geometry import LineString, MultiLineString, box

from app_service import kiem_tra_du_lieu
from core_housenumber import COL_BEN, COL_SONHA, process
from test_alley_numbering import alley_fixture
from test_route_hierarchy import hierarchy_fixture

MAIN_TIM = LineString([(-20, -4), (20, -4)])  # centerline of box(-20, -8, 20, 0)
STRAIGHT = LineString([(0, 0), (0, 60)])


def as_centerlines(roads, alley_tim, main_tim=MAIN_TIM, angle=0):
    """Replace alley_fixture's polygons (row 0 alley, row 1 main road) with centerlines."""
    roads = roads.copy()
    roads.loc[0, "geometry"] = rotate(alley_tim, angle, origin=(0, 0))
    roads.loc[1, "geometry"] = rotate(main_tim, angle, origin=(0, 0))
    return roads


def errors_of(houses, roads):
    return kiem_tra_du_lieu(houses, roads)["errors"]


class AlleyCenterlineTests(unittest.TestCase):
    def assert_expected(self, houses, roads):
        self.assertEqual(errors_of(houses, roads), [])
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())
        self.assertEqual(out[COL_BEN].tolist(), houses.side.tolist())

    def test_all_entrance_directions_match_polygon_expectations(self):
        for angle in (0, 90, 180, 270, 37):
            with self.subTest(angle=angle):
                houses, roads = alley_fixture(angle=angle)
                self.assert_expected(houses, as_centerlines(roads, STRAIGHT, angle=angle))

    def test_bent_and_u_bend_alleys(self):
        houses, roads = alley_fixture(bent=True)
        self.assert_expected(houses, as_centerlines(roads, LineString([(0, 0), (0, 30), (30, 30)])))
        path = LineString([(0, 0), (0, 40), (30, 40), (30, 10)])
        houses, roads = alley_fixture(path=path, samples=[8, 20, 32, 48, 58, 78, 90])
        self.assert_expected(houses, as_centerlines(roads, path))

    def test_centerline_alley_with_polygon_parent(self):
        houses, roads = alley_fixture()
        roads.loc[0, "geometry"] = STRAIGHT
        self.assert_expected(houses, roads)

    def test_tenhem_schema(self):
        houses, roads = hierarchy_fixture()
        roads = as_centerlines(roads, STRAIGHT)
        self.assertEqual(errors_of(houses, roads), [])
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())

    def test_branched_alley_network(self):
        name = "Hẻm 8 đường A"
        alley = MultiLineString([[(0, 0), (0, 30)], [(-20, 30), (20, 30)]])
        roads = gpd.GeoDataFrame({"tenDuong": [name, "Đường A"]},
                                 geometry=[alley, MAIN_TIM], crs="EPSG:3857")
        geometries = [box(-6, 8, -2, 12), box(2, 8, 6, 12),
                      box(-12, 32, -8, 36), box(-12, 24, -8, 28),
                      box(12, 32, 16, 36), box(12, 24, 16, 28)]
        houses = gpd.GeoDataFrame({"tenDuong": [name] * len(geometries)},
                                  geometry=geometries, crs=roads.crs)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("Mạng hẻm phân nhánh" in w for w in report["warnings"]))
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_BEN].tolist(), ["TRAI", "PHAI", "PHAI", "TRAI", "TRAI", "PHAI"])
        numbers = out[COL_SONHA].str.split("/").str[-1].astype(int)
        self.assertTrue(out[COL_SONHA].str.startswith("8/").all())
        self.assertTrue(all((n % 2 == 1) == (side == "TRAI") for n, side in zip(numbers, out[COL_BEN])))

    def test_unresolvable_entrances_are_errors(self):
        cases = (
            (LineString([(0, 30), (0, 60)]), "không tìm thấy miệng hẻm"),            # 34 m from parent
            (LineString([(-10, 0), (-10, 30), (10, 30), (10, 0)]), "nhiều đầu tim"),  # both ends at parent
            (MultiLineString([[(0, 0), (0, 25)], [(0, 35), (0, 60)]]), "đoạn rời"),
        )
        for tim, text in cases:
            with self.subTest(text=text):
                houses, roads = alley_fixture()
                errors = errors_of(houses, as_centerlines(roads, tim))
                self.assertTrue(any(text in e for e in errors), errors)

    def test_centerline_crossing_alley_parcel_is_error(self):
        houses, roads = alley_fixture()
        errors = errors_of(houses, as_centerlines(roads, LineString([(4, 0), (4, 60)])))
        self.assertTrue(any("cắt qua" in e for e in errors), errors)

    def test_polygon_alley_needs_polygon_parent(self):
        houses, roads = hierarchy_fixture()
        roads.loc[1, "geometry"] = MAIN_TIM
        errors = errors_of(houses, roads)
        self.assertTrue(any("cần đường cha polygon" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
