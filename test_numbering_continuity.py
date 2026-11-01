# -*- coding: utf-8 -*-
"""Numbers continue across far-apart parcel clusters: one road, no duplicates."""
import unittest

import geopandas as gpd
from shapely.geometry import LineString, box

from core_housenumber import COL_BEN, COL_SONHA, process

CRS = "EPSG:3405"


def two_clusters(gap=500):
    """Parcels on both sides of a straight road in two groups `gap` metres apart."""
    geoms, xs = [], list(range(0, 80, 10)) + list(range(80 + gap, 160 + gap, 10))
    for x in xs:
        geoms += [box(x, 4, x + 10, 16), box(x, -16, x + 10, -4)]
    houses = gpd.GeoDataFrame({"tenDuong": ["Đường A"] * len(geoms)}, geometry=geoms, crs=CRS)
    length = xs[-1] + 20
    polygon = gpd.GeoDataFrame({"tenDuong": ["Đường A"]}, geometry=[box(-5, -4, length, 4)], crs=CRS)
    line = gpd.GeoDataFrame({"tenDuong": ["Đường A"]}, geometry=[LineString([(-5, 0), (length, 0)])], crs=CRS)
    return houses, polygon, line


class NumberingContinuityTests(unittest.TestCase):
    def test_far_clusters_continue_numbers_without_duplicates(self):
        houses, polygon, line = two_clusters()
        for label, roads in (("polygon", polygon), ("tim", line)):
            with self.subTest(mode=label):
                out = process(houses, roads, verbose=False)
                numbers = out[COL_SONHA].astype(int)
                self.assertFalse(numbers.duplicated().any(), sorted(numbers))
                for side, first in (("TRAI", 1), ("PHAI", 2)):
                    own = sorted(numbers[out[COL_BEN] == side])
                    self.assertEqual(own, list(range(first, first + 2 * len(own), 2)))
                # Order follows the road: the parcels of one cluster are consecutive.
                for side in ("TRAI", "PHAI"):
                    sub = out[out[COL_BEN] == side].assign(x=lambda d: d.geometry.centroid.x)
                    ranks = sub.sort_values("x")[COL_SONHA].astype(int).tolist()
                    self.assertIn(ranks, (sorted(ranks), sorted(ranks, reverse=True)))


if __name__ == "__main__":
    unittest.main()
