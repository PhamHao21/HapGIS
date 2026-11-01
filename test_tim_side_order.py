# -*- coding: utf-8 -*-
"""Centerline mode: side at digitizing kinks and dead ends, cluster order on U roads, isolated parcels."""
import unittest

import geopandas as gpd
from shapely.geometry import LineString, Polygon, box

from core_housenumber import COL_BEN, COL_SONHA, chuan_hoa_chieu_line, do_thua_theo_tim, process

CRS = "EPSG:3405"


def run(parcels, line, names=None):
    houses = gpd.GeoDataFrame({"tenDuong": ["A"] * len(parcels), "ten": names or list(range(len(parcels)))},
                              geometry=parcels, crs=CRS)
    roads = gpd.GeoDataFrame({"tenDuong": ["A"]}, geometry=[line], crs=CRS)
    out = process(houses, roads, verbose=False)
    return {row.ten: (int(row[COL_SONHA]), row[COL_BEN]) for _, row in out.iterrows()}


class TimSideOrderTests(unittest.TestCase):
    def test_parcel_at_digitizing_kink_takes_side_of_the_road(self):
        # Real case (X12, shifted to the origin): the centerline steps back ~2 m at
        # (34.6, 40.6) and the small parcel's nearest point is that kink. The local
        # tangent there points the wrong way; both parcels lie on the same side.
        line = chuan_hoa_chieu_line(LineString([
            (9.9, 4.6), (26.8, 29.3), (34.6, 40.6), (32.5, 42.1), (32.8, 42.7), (43.0, 61.9),
            (44.9, 65.6), (77.1, 51.9), (69.0, 38.5), (57.7, 33.9), (49.7, 38.5)]), "B-N")
        small = Polygon([(38.9, 38.4), (33.5, 29.9), (29.9, 32.2), (35.3, 40.6)])
        neighbour = Polygon([(49.5, 41.1), (48.2, 38.1), (41.4, 41.6), (41.1, 41.7), (38.9, 38.4),
                             (35.3, 40.6), (33.6, 41.6), (38.8, 51.8), (44.2, 48.6), (42.2, 44.9)])
        self.assertEqual(do_thua_theo_tim(small, line, "B-N")["side"],
                         do_thua_theo_tim(neighbour, line, "B-N")["side"])

    def test_dead_end_parcel_keeps_its_side_against_wrapping_neighbours(self):
        # Short lane heading south; one parcel east, three parcels west that wrap
        # round the dead end and touch it. Neighbour vote must not flip it.
        line = LineString([(0, 60), (0, 0)])
        east = box(2, 5, 20, 40)
        west = [box(-20, 25, -2, 40), box(-20, 5, -2, 25), Polygon([(-20, 5), (20, 5), (20, -10), (-20, -10)])]
        res = run([east] + west, line, ["east", "w0", "w1", "end"])
        self.assertNotEqual(res["east"][0] % 2, res["w0"][0] % 2)
        self.assertEqual(res["w0"][0] % 2, res["w1"][0] % 2)

    def test_clusters_on_u_road_follow_the_road(self):
        # Hairpin: east along y=0, back west along y=40. Three far-apart clusters,
        # all on the outside (same side): A and B on the first leg, C on the way back.
        line = LineString([(0, 0), (1000, 0), (1000, 40), (0, 40)])
        cluster = lambda x0, y0, y1: [box(x, y0, x + 10, y1) for x in range(x0, x0 + 40, 10)]
        a, b, c = cluster(100, -16, -4), cluster(800, -16, -4), cluster(450, 44, 56)
        res = run(a + b + c, line, [f"a{i}" for i in range(4)] + [f"b{i}" for i in range(4)] + [f"c{i}" for i in range(4)])
        self.assertEqual({side for _, side in res.values()}, {next(iter(res.values()))[1]})
        mean = lambda p: sum(res[f"{p}{i}"][0] for i in range(4)) / 4
        self.assertTrue(mean("a") < mean("b") < mean("c") or mean("a") > mean("b") > mean("c"),
                        (mean("a"), mean("b"), mean("c")))

    def test_isolated_parcel_inside_a_touching_row_keeps_its_place(self):
        # Row along a straight road; a narrow parcel drawn with gaps to both
        # neighbours (touches nobody) sits between r1 and r2, which are linked
        # through a back lot. It must be numbered between them, not after the row.
        line = LineString([(-5, 0), (80, 0)])
        r0, r1 = box(0, 4, 10, 20), box(10, 4, 20, 20)
        sliver = box(20.5, 4, 21.5, 16)
        back = box(10, 20, 32, 30)
        r2, r3 = box(22, 4, 32, 20), box(32, 4, 42, 20)
        res = run([r0, r1, sliver, back, r2, r3], line, ["r0", "r1", "s", "back", "r2", "r3"])
        lo, hi = sorted((res["r1"][0], res["r2"][0]))
        self.assertTrue(lo < res["s"][0] < hi, res)


if __name__ == "__main__":
    unittest.main()
