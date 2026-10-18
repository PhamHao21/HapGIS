"""Entrance geometry, numbering, parsing and real GIS export regression tests."""
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from alley_numbering import parse_alley_name
from app_service import chay_danh_so, kiem_tra_du_lieu, luu_ket_qua
from core_housenumber import process, COL_SONHA, COL_BEN


def alley_fixture(name="Hẻm 236 đường A", angle=0, bent=False, path=None, samples=None):
    if path is None:
        path = LineString([(0, 0), (0, 30), (30, 30)]) if bent else LineString([(0, 0), (0, 60)])
    alley = path.buffer(2, cap_style=2, join_style=2)
    samples = [8, 18, 42, 52] if samples is None else samples
    geometries, expected, sides, ids = [], [], [], []
    parsed = parse_alley_name(name)
    for rank, distance in enumerate(samples, 1):
        p = path.interpolate(distance)
        a, b = path.interpolate(distance - .1), path.interpolate(distance + .1)
        dx, dy = b.x - a.x, b.y - a.y
        norm = (dx * dx + dy * dy) ** .5
        for side, sign in (("TRAI", 1), ("PHAI", -1)):
            cx, cy = p.x - sign * dy / norm * 4, p.y + sign * dx / norm * 4
            geometries.append(box(cx - 2, cy - 2, cx + 2, cy + 2))
            number = 2 * rank - 1 if side == "TRAI" else 2 * rank
            expected.append(f"{parsed.prefix}/{number}" if parsed.prefix else str(number))
            sides.append(side)
            ids.append(f"{side}-{rank}")
    houses = gpd.GeoDataFrame({"tenDuong": [name] * len(geometries), "parcel_id": ids,
                              "expected": expected, "side": sides},
                             geometry=geometries, crs="EPSG:3857")
    roads = gpd.GeoDataFrame({"tenDuong": [name, "Đường A"]},
                            geometry=[alley, box(-20, -8, 20, 0)], crs=houses.crs)
    if angle:
        houses.geometry = houses.geometry.map(lambda g: rotate(g, angle, origin=(0, 0)))
        roads.geometry = roads.geometry.map(lambda g: rotate(g, angle, origin=(0, 0)))
    return houses, roads


class AlleyTests(unittest.TestCase):
    def test_name_recognition_and_no_accidental_number_extraction(self):
        for name, prefix, hint in [
            ("Hẻm 1 đường A", "1", "đường A"), ("Hẻm 1 A", "1", "A"),
            (" HEM 236 đường A ", "236", "đường A"),
            ("Hẻm 1 đường số 236", "1", "đường số 236"),
            ("Hẻm Hoa Mai", "", "Hoa Mai"), ("Hẻm đường số 236", "", "đường số 236"),
            ("Hẻm", "", ""),
        ]:
            with self.subTest(name=name):
                result = parse_alley_name(name)
                self.assertTrue(result.is_alley)
                self.assertEqual((result.prefix, result.parent_hint), (prefix, hint))
        for name in ("Đường số 236", "Lê Lợi", "H9", "HẻmX", None):
            self.assertFalse(parse_alley_name(name).is_alley)
        for name in ("Hẻm 1A", "Hẻm 236/5", "Hem 1.5 A", "Hẻm -1"):
            with self.assertRaisesRegex(ValueError, "chuẩn hóa"):
                parse_alley_name(name)

    def test_all_entrance_directions_and_parity(self):
        for angle in (0, 90, 180, 270, 37):
            houses, roads = alley_fixture(angle=angle)
            before_h, before_r = houses.copy(), roads.copy()
            with self.subTest(angle=angle):
                out = process(houses, roads, verbose=False)
                self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())
                self.assertEqual(out[COL_BEN].tolist(), houses.side.tolist())
                self.assertEqual(out.tenDuong.tolist(), houses.tenDuong.tolist())
                assert_geodataframe_equal(houses, before_h)
                assert_geodataframe_equal(roads, before_r)

    def test_bent_alley_uses_local_tangent_and_distance(self):
        houses, roads = alley_fixture(bent=True)
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())
        self.assertEqual(out[COL_BEN].tolist(), houses.side.tolist())

    def test_large_projected_coordinates_and_segmented_polygon(self):
        houses, roads = alley_fixture()
        for frame in (houses, roads):
            frame.geometry = frame.geometry.map(lambda geom: translate(geom, 580000, 1150000))
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())

    def test_u_bend_does_not_shortcut_or_reverse_local_sides(self):
        path = LineString([(0, 0), (0, 40), (30, 40), (30, 10)])
        houses, roads = alley_fixture(path=path, samples=[8, 20, 32, 48, 58, 78, 90])
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())
        self.assertEqual(out[COL_BEN].tolist(), houses.side.tolist())
        houses, roads = alley_fixture()
        roads.loc[0, "geometry"] = box(-2, 0, 2, 30)
        roads.loc[2] = [roads.tenDuong.iloc[0], box(-2, 30, 2, 60)]
        roads.set_crs(houses.crs, inplace=True)
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())

    def test_unnumbered_alley_and_ordinary_road_remain_plain_text(self):
        for name in ("Hẻm Hoa Mai", "Hẻm đường A", "Đường số 236"):
            houses, roads = alley_fixture(name)
            out = process(houses, roads, verbose=False)
            self.assertTrue(all(isinstance(v, str) and v.isdigit() for v in out[COL_SONHA]))
            if name.startswith("Hẻm"):
                self.assertEqual(out[COL_SONHA].tolist(), houses.expected.tolist())

    def test_two_roads_named_parent_controls_direction(self):
        houses, roads = alley_fixture("Hẻm 236 B")
        roads.loc[2] = ["Đường B", box(-20, 60, 20, 68)]
        roads.set_crs(houses.crs, inplace=True)
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), ["236/8", "236/7", "236/6", "236/5", "236/4", "236/3", "236/2", "236/1"])
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["alley_routes"][0]["parent"], "Đường B")

    def test_two_roads_unnamed_uses_wider_cross_section(self):
        houses, roads = alley_fixture("Hẻm")
        roads.loc[2] = ["Đường B", box(-20, 60, 20, 74)]
        roads.set_crs(houses.crs, inplace=True)
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_SONHA].tolist(), ["8", "7", "6", "5", "4", "3", "2", "1"])
        roads.loc[2, "geometry"] = box(-20, 60, 20, 68)
        self.assertTrue(any("mặt cắt" in e for e in kiem_tra_du_lieu(houses, roads)["errors"]))

    def test_missing_ambiguous_loop_and_disconnected_block_but_branch_runs(self):
        houses, original = alley_fixture()
        variants = []
        variants.append(original.iloc[:1].copy())
        wrong = original.copy()
        wrong.loc[1, "geometry"] = box(-20, -8, 20, -.101)  # Beyond the fixed 10 cm tolerance.
        variants.append(wrong)
        same_parent = original.copy()
        same_parent.loc[1, "geometry"] = unary_union([box(-20, -8, 20, 0), box(-20, 60, 20, 68)])
        variants.append(same_parent)
        for polygon in (
            box(-20, 0, 20, 60).difference(box(-16, 4, 16, 56)),
            unary_union([box(-2, 0, 2, 20), box(-2, 25, 2, 60)]),
        ):
            roads = original.copy()
            roads.loc[0, "geometry"] = polygon
            variants.append(roads)
        for n, roads in enumerate(variants):
            with self.subTest(case=n):
                report = kiem_tra_du_lieu(houses, roads)
                self.assertTrue(report["errors"], report)
                with self.assertRaises(ValueError):
                    process(houses, roads, verbose=False)

        branched = original.copy()
        branched.loc[0, "geometry"] = unary_union([
            box(-2, 0, 2, 60), box(-2, 28, 30, 32)
        ])
        report = kiem_tra_du_lieu(houses, branched)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("Mạng hẻm phân nhánh" in warning
                            for warning in report["warnings"]))
        out = process(houses, branched, verbose=False)
        self.assertEqual(out[COL_SONHA].notna().sum(), len(houses))

    def test_controlled_parent_gap_tolerance_and_warning(self):
        for gap, accepted in ((.05, True), (.10, True), (.101, False)):
            houses, roads = alley_fixture()
            roads.loc[1, "geometry"] = box(-20, -8, 20, -gap)
            report = kiem_tra_du_lieu(houses, roads)
            with self.subTest(gap=gap):
                self.assertEqual(not report["errors"], accepted, report)
                digitizing = [warning for warning in report["warnings"] if "digitize" in warning]
                self.assertEqual(bool(digitizing), accepted)
                if accepted:
                    self.assertIn(f"{gap * 100:.1f}".replace(".", ","), digitizing[0])

    def test_parent_point_contact_at_entrance_is_accepted_but_middle_is_blocked(self):
        houses, roads = alley_fixture()
        roads.loc[1, "geometry"] = Polygon([(-20, -8), (20, -8), (0, 0), (-20, -8)])
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("tiếp giáp đường cha tại một điểm" in warning
                            for warning in report["warnings"]))

        roads.loc[1, "geometry"] = Polygon([(2, 30), (10, 20), (10, 40), (2, 30)])
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(any("ở giữa hẻm" in error for error in report["errors"]))

    def test_sibling_alley_contact_warns_but_unrelated_middle_connection_blocks(self):
        houses, roads = alley_fixture()
        roads.loc[2] = ["Hẻm 99 đường A", box(1.95, 20, 6, 40)]
        roads.set_crs(houses.crs, inplace=True)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("Bỏ qua dải chồng mỏng" in warning
                            for warning in report["warnings"]))

        roads.loc[2, "geometry"] = box(1.5, 20, 6, 40)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("cùng đường cha" in warning for warning in report["warnings"]))

        roads.loc[2, "tenDuong"] = "Hẻm 99 đường B"
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(any("ở giữa hẻm" in error for error in report["errors"]))

    def test_branched_network_numbers_from_mouth_with_local_side_parity(self):
        name = "Hẻm 8 đường A"
        alley = unary_union([box(-2, 0, 2, 32), box(-22, 28, 22, 32)])
        roads = gpd.GeoDataFrame(
            {"tenDuong": [name, "Đường A"]},
            geometry=[alley, box(-20, -8, 20, 0)], crs="EPSG:3857",
        )
        geometries = [
            box(-6, 8, -2, 12), box(2, 8, 6, 12),
            box(-12, 32, -8, 36), box(-12, 24, -8, 28),
            box(12, 32, 16, 36), box(12, 24, 16, 28),
        ]
        expected_sides = ["TRAI", "PHAI", "PHAI", "TRAI", "TRAI", "PHAI"]
        houses = gpd.GeoDataFrame(
            {"tenDuong": [name] * len(geometries), "expected_side": expected_sides},
            geometry=geometries, crs=roads.crs,
        )
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("Mạng hẻm phân nhánh" in warning
                            for warning in report["warnings"]))
        out = process(houses, roads, verbose=False)
        self.assertEqual(out[COL_BEN].tolist(), expected_sides)
        self.assertTrue(out[COL_SONHA].str.startswith("8/").all())
        numbers = out[COL_SONHA].str.split("/").str[-1].astype(int)
        self.assertTrue(all((number % 2 == 1) == (side == "TRAI")
                            for number, side in zip(numbers, out[COL_BEN])))

    def test_nearby_unnamed_road_is_never_used_as_parent_fallback(self):
        houses, roads = alley_fixture("Hẻm 236 đường A")
        roads.loc[1, "geometry"] = box(-20, -8, 20, -.2)
        roads.loc[2] = ["Đường B", box(-20, -8, 20, -.05)]
        roads.set_crs(houses.crs, inplace=True)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(report["errors"])
        self.assertFalse(any("Dùng dung sai" in warning for warning in report["warnings"]))

    def test_bad_names_wrong_parent_and_side_contact_are_reported(self):
        for name in ("Hẻm 1A", "Hẻm 236/5", "Hẻm 236 đường không tồn tại"):
            houses, roads = alley_fixture()
            houses["tenDuong"] = name
            roads.loc[0, "tenDuong"] = name
            with self.subTest(name=name):
                report = kiem_tra_du_lieu(houses, roads)
                self.assertTrue(report["errors"])
                self.assertEqual(len(report["alley_routes"]), 1)
                self.assertEqual(report["alley_routes"][0]["route"], name)
        houses, roads = alley_fixture()
        roads.loc[1, "geometry"] = box(2, 10, 10, 40)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(report["errors"], "A long side boundary is not an entrance")

    def test_two_unnamed_oblique_roads_do_not_guess_width(self):
        houses, roads = alley_fixture("Hẻm")
        # Overlapping polygons obscure the actual mouth cross section.
        roads.loc[1, "geometry"] = box(-20, -8, 20, 1)
        roads.loc[2] = ["Đường B", box(-20, 59, 20, 74)]
        roads.set_crs(houses.crs, inplace=True)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertTrue(report["errors"])
        self.assertTrue(any("mặt cắt" in message for message in report["errors"]))

    def test_selected_alley_retains_parent_reference_and_export(self):
        houses, roads = alley_fixture("Hẻm 1 A")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gpkg"
            houses.to_file(source, layer="parcels", driver="GPKG")
            roads.to_file(source, layer="roads", driver="GPKG")
            output = Path(tmp) / "out.gpkg"
            out = chay_danh_so(str(source), "parcels", str(source), "roads", "Hẻm 1 A", str(output))
            reread = gpd.read_file(output)
            self.assertEqual(reread[COL_SONHA].tolist(), houses.expected.tolist())
            shp = Path(tmp) / "out.shp"
            luu_ket_qua(out, str(shp))
            reread = gpd.read_file(shp)
            # Field aliases are written by the existing Shapefile exporter.
            self.assertTrue(any(reread[column].tolist() == houses.expected.tolist()
                                for column in reread.columns if column not in ("geometry", "expected")))
            roads = roads.iloc[:1]
            roads.to_file(source, layer="roads", driver="GPKG")
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                chay_danh_so(str(source), "parcels", str(source), "roads", "Hẻm 1 A", str(output))
            self.assertEqual(output.read_bytes(), before)

    def test_le_loi_sketch_alley_and_named_street_from_same_main_road(self):
        """Hẻm 1 và Đường 236 cùng nối vào đường Lê Lợi (theo hình phác thảo)."""
        lle, hem, d236 = "Đường Lê Lợi", "Hẻm 1 đường Lê Lợi", "Đường 236 đường Lê Lợi"
        roads = gpd.GeoDataFrame({"tenDuong": [lle, hem, d236]}, geometry=[
            box(0, 0, 92, 15), box(38, -55, 44, 0), box(73, -55, 79, 0)], crs="EPSG:3857")
        names, geoms, tags = [], [], []
        for k in range(4):
            y1 = -(k * 8 + 4)
            for name, x0, tag in ((hem, 44, "H-east"), (hem, 28, "H-west"),
                                  (d236, 79, "D-east"), (d236, 63, "D-west")):
                names.append(name)
                geoms.append(box(x0, y1 - 8, x0 + 10, y1))
                tags.append(f"{tag}-{k + 1}")
        for i in range(4):
            names.append(lle)
            geoms.append(box(i * 9, 15, i * 9 + 9, 27))
            tags.append(f"L-north-{i + 1}")
        for tag, box_ in (("L-south-W", box(0, -12, 28, 0)), ("L-south-M", box(54, -8, 63, 0)),
                          ("L-south-E", box(89, -8, 92, 0))):
            names.append(lle)
            geoms.append(box_)
            tags.append(tag)
        houses = gpd.GeoDataFrame({"tenDuong": names, "tag": tags}, geometry=geoms, crs=roads.crs)
        report = kiem_tra_du_lieu(houses, roads)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["alley_routes"][0]["parent"], lle)
        out = process(houses, roads, verbose=False).set_index("tag")
        # Hẻm 1: từ miệng hẻm đi vào, trái (phía đông) lẻ, phải (phía tây) chẵn.
        for k in range(4):
            self.assertEqual(out.loc[f"H-east-{k + 1}", COL_SONHA], f"1/{2 * k + 1}")
            self.assertEqual(out.loc[f"H-west-{k + 1}", COL_SONHA], f"1/{2 * k + 2}")
        # Đường 236 là đường thường: không có tiền tố hẻm.
        for k in range(4):
            self.assertEqual(out.loc[f"D-east-{k + 1}", COL_SONHA], str(2 * k + 1))
            self.assertEqual(out.loc[f"D-west-{k + 1}", COL_SONHA], str(2 * k + 2))
        # Đường Lê Lợi: đi từ đông sang tây, bên nam (trái) lẻ, bên bắc (phải) chẵn;
        # chỉ 3 thửa một bên vẫn phải đúng chiều.
        self.assertEqual([out.loc[f"L-south-{s}", COL_SONHA] for s in "EMW"], ["1", "3", "5"])
        self.assertEqual([out.loc[f"L-north-{i}", COL_SONHA] for i in (4, 3, 2, 1)], ["2", "4", "6", "8"])
        # Chọn riêng một hẻm vẫn dùng đường chính làm tham chiếu.
        chosen = houses[houses.tenDuong == hem]
        alone = process(chosen, roads[roads.tenDuong == hem], verbose=False, reference_roads=roads)
        self.assertEqual(alone[COL_SONHA].tolist(), [f"1/{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8)])

    def test_mixed_plain_prefix_and_null_output(self):
        from test_field_mapping import fixtures
        houses, roads = alley_fixture()
        plain_h, plain_r = fixtures()
        plain_h.geometry = plain_h.geometry.map(lambda g: translate(g, 1000, 1000))
        plain_r.geometry = plain_r.geometry.map(lambda g: translate(g, 1000, 1000))
        import pandas as pd
        combined_h = gpd.GeoDataFrame(pd.concat([houses, plain_h], ignore_index=True), crs=houses.crs)
        combined_r = gpd.GeoDataFrame(pd.concat([roads, plain_r], ignore_index=True), crs=roads.crs)
        out = process(combined_h, combined_r, verbose=False)
        self.assertEqual(set(out.loc[out.tenDuong.eq("Hẻm 236 đường A"), COL_SONHA]), set(houses.expected))
        self.assertTrue(out.loc[out.tenDuong.isna(), COL_SONHA].isna().all())
        self.assertTrue(out[COL_SONHA].dropna().map(lambda v: isinstance(v, str)).all())


if __name__ == "__main__":
    unittest.main()
