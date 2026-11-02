# -*- coding: utf-8 -*-
"""Centerline mode: numbering direction follows the centerline, not the parcel spread."""
import unittest

import geopandas as gpd
from shapely.geometry import LineString, box

from core_housenumber import COL_SONHA, process, xac_dinh_huong

CRS = "EPSG:3405"


class TimDirectionTests(unittest.TestCase):
    def setUp(self):
        # Real case (H106, shifted to the origin): lane runs north ~265 m and hooks
        # west at the top. A wide parcel east of the mouth and a big lot north-west
        # of the hook pull the parcel axis to ~113 deg, just past the B-N limit.
        self.line = LineString([(0, 0), (5, 265), (-76, 267)])
        east = [box(3, 0, 60, 20)] + [box(3, y, 20, y + 20) for y in range(30, 250, 30)]
        west = [box(-20, y, -3, y + 20) for y in range(10, 250, 30)]
        big = box(-130, 280, -70, 360)
        self.parcels = east + west + [big]
        self.houses = gpd.GeoDataFrame(
            {"tenDuong": ["A"] * len(self.parcels), "ten": list(range(len(self.parcels)))},
            geometry=self.parcels, crs=CRS)

    def test_parcel_spread_alone_would_tip_the_axis(self):
        huong, goc = xac_dinh_huong(self.houses, [self.line])
        self.assertEqual(huong, "DN-TB", goc)

    def test_centerline_lane_is_numbered_north_to_south(self):
        self.assertEqual(xac_dinh_huong(self.houses, [self.line], theo_tim=True)[0], "B-N")
        roads = gpd.GeoDataFrame({"tenDuong": ["A"]}, geometry=[self.line], crs=CRS)
        out = process(self.houses, roads, verbose=False)
        self.assertEqual(set(out["huong"]), {"B-N"})
        so = dict(zip(out["ten"], out[COL_SONHA].astype(int)))
        # East row: southernmost (index 0) must come after the northernmost (index 8).
        self.assertGreater(so[0], so[8])
        self.assertLess(so[len(self.parcels) - 1], so[0])


if __name__ == "__main__":
    unittest.main()
