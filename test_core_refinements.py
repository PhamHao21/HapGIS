"""Regression cases for the recent ordinary-road frontage refinements."""
import unittest

import geopandas as gpd
from shapely.geometry import Point, box

from core_housenumber import gan_thua_vao_manh, thu_tu_thua_theo_bien_duong, process, COL_SONHA


def boundary_rows(xs, stations, offsets=None, order_scores=None):
    n = len(xs)
    data = dict(_manhDuong=[0]*n, _vongBien=[0]*n,
                _viTriBien=stations, _chuViBien=[200]*n,
                _measure=list(range(n)), _dist_line=[1]*n,
                _xMatDuong=xs, _yMatDuong=[0]*n)
    if offsets is not None:
        data['_lechBien'] = offsets
    if order_scores is not None:
        data['_scoreThuTu'] = order_scores
    return gpd.GeoDataFrame(data, geometry=[Point(x, 0) for x in xs], crs='EPSG:3857')


class CoreRefinementTests(unittest.TestCase):
    def test_non_touching_parcel_uses_nearest_not_largest_polygon(self):
        small = box(-2, -10, 0, 10)
        large = box(20.04, -100, 40, 100)
        houses = gpd.GeoDataFrame(geometry=[box(5, 0, 15, 5)], crs='EPSG:3857')
        mapping, _, _ = gan_thua_vao_manh([small, large], houses)
        self.assertEqual(mapping[0], 0)  # 5 m versus 5.04 m; touches neither.

    def test_small_groups_reverse_to_the_requested_direction(self):
        for xs in ([10, 20], [10, 20, 30]):
            rows = boundary_rows(xs, list(range(10, 10 + len(xs))))
            order, _ = thu_tu_thua_theo_bien_duong(rows, 'D-T')
            self.assertEqual(order, list(reversed(range(len(xs)))))

    def test_coincident_access_points_still_choose_direction(self):
        rows = boundary_rows([90, 90], [20, 20], offsets=[4, -4])
        rows.geometry = [Point(94, 0), Point(86, 0)]
        order, _ = thu_tu_thua_theo_bien_duong(rows, 'D-T')
        self.assertEqual(order, [0, 1])  # East parcel comes first, independent of ring winding.

    def test_long_frontage_midpoint_controls_order_direction(self):
        # Positions already use frontage midpoints; side-classification points
        # still refer to the old access points and must not override this order.
        rows = boundary_rows([100, 90], [10, 20], order_scores=[25, 40])
        order, _ = thu_tu_thua_theo_bien_duong(rows, 'D-T')
        self.assertEqual(order, [1, 0])

    def test_long_frontage_pipeline_has_no_internal_columns_in_output(self):
        houses = gpd.GeoDataFrame({'tenDuong': ['A', 'A']},
                                  geometry=[box(0, 10, 10, 110), box(0, 120, 10, 130)], crs='EPSG:3857')
        roads = gpd.GeoDataFrame({'tenDuong': ['A']}, geometry=[box(-10, 0, 0, 150)], crs=houses.crs)
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), ['3', '1'])
        self.assertFalse(any(str(column).startswith('_') for column in out.columns))


if __name__ == '__main__':
    unittest.main()
