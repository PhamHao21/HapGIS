# -*- coding: utf-8 -*-
"""Entrance-oriented alley numbering on a rooted medial network in metres.

No nearest-road fallback: a named/structured parent must be identified. The
medial graph keeps real branches and orders them from the entrance; cycles and
disconnected routes remain blocked because they have no unique rooted tree.
"""
from dataclasses import dataclass
import math
import re

import pandas as pd
from shapely import voronoi_polygons
from shapely.affinity import translate
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiPoint, Point
from shapely.ops import unary_union, nearest_points

from core_housenumber import (
    FIELD_ROUTE, COL_BEN, COL_STT, COL_SONHA, COL_HUONG,
    GT_TRAI, GT_PHAI, STEP, MAT_TIEN_TIM_BAND_M, khoa_ten, lay_cac_line,
)
from route_catalog import (
    FIELD_ALLEY, normalize_name, route_key_series, route_label,
    validate_route_schema,
)

EPS = 1e-7  # Numerical geometry tolerance only.
GEOMETRY_TOLERANCE_M = 0.10  # Controlled digitizing tolerance in projected metres.


@dataclass(frozen=True)
class AlleyName:
    is_alley: bool
    prefix: str = ""
    parent_hint: str = ""


@dataclass
class AlleyRoute:
    name: str
    prefix: str
    parent_name: str
    polygon: object
    line: LineString
    network_edges: tuple = ()
    branch_count: int = 0
    warnings: tuple = ()


@dataclass(frozen=True)
class NetworkEdge:
    """One medial-axis edge oriented away from the alley entrance."""

    line: LineString
    offset: float


def parse_alley_name(value):
    text = "" if pd.isna(value) else str(value).strip()
    match = re.match(r"^(?:hẻm|hem)(?:\s+|$)(.*)$", text, re.IGNORECASE)
    if not match:
        return AlleyName(False)
    tail = match.group(1).strip()
    if tail and re.match(r"^[+-]?\d", tail):
        token, *rest = tail.split(maxsplit=1)
        if not re.fullmatch(r"[0-9]+", token):
            raise ValueError(f"{text}: số hẻm '{token}' chưa hỗ trợ; chuẩn hóa số nguyên, không dùng chữ cái hoặc hẻm nhiều cấp.")
        return AlleyName(True, token, rest[0].strip() if rest else "")
    return AlleyName(True, "", tail)


def route_preview(value):
    if not str(value or "").strip():
        return "Tất cả tuyến · Xem nhận diện hẻm trong Kiểm tra dữ liệu."
    try:
        parsed = parse_alley_name(value)
    except ValueError as exc:
        return str(exc)
    if not parsed.is_alley:
        return "Tuyến thường · Mẫu số: 1, 2, 3…"
    if parsed.prefix:
        return f"Hẻm {parsed.prefix} · Mẫu số: {parsed.prefix}/1, {parsed.prefix}/2…"
    return "Hẻm không có số · Mẫu số: 1, 2, 3…"


def _parent_key(value):
    text = " ".join(str(value).casefold().split())
    return re.sub(r"^(?:đường|duong)\s+", "", text)


def _components(geometry):
    if geometry.is_empty:
        return []
    if hasattr(geometry, "geoms"):
        return [part for child in geometry.geoms for part in _components(child)]
    return [geometry]


def _label_is_alley(value):
    """Recognize both legacy labels and ``parent › alley`` catalog labels."""
    text = str(value or "").split(" › ", 1)[-1]
    try:
        return parse_alley_name(text).is_alley
    except ValueError:
        return True


def _thin_polygon_overlap(geometry, tolerance=GEOMETRY_TOLERANCE_M):
    """True only for polygonal slivers whose thickness is at most 2*tolerance.

    Line/point contacts are deliberately excluded: at the middle of an alley
    they can represent a real secondary-alley connection.
    """
    polygonal = [part for part in _components(geometry)
                 if part.geom_type in ("Polygon", "MultiPolygon") and part.area > EPS]
    if not polygonal:
        return False
    overlap = unary_union(polygonal)
    return overlap.buffer(-tolerance).is_empty


def _medial_topology(polygon):
    """Return a stable, pruned medial graph in source coordinates."""
    x, y = polygon.bounds[:2]
    local = translate(polygon, -x, -y)
    graph, spacing = _medial_graph_local(local)
    shifted = {
        (node[0] + x, node[1] + y): {
            (neighbour[0] + x, neighbour[1] + y) for neighbour in links
        }
        for node, links in graph.items()
    }
    return shifted, spacing


def _medial_graph_local(polygon):
    if polygon.geom_type != "Polygon":
        raise ValueError("hẻm bị rời đoạn; cần một hành lang liên thông")
    if polygon.interiors:
        raise ValueError("hẻm có vòng/đảo; chưa xác định được một chiều duy nhất")
    spacing = max(.25, polygon.length / 2500)
    boundary = polygon.exterior.segmentize(spacing)
    edges = voronoi_polygons(MultiPoint(list(boundary.coords)[:-1]), only_edges=True)
    graph = {}
    # Computation in a local coordinate system keeps graph nodes stable in VN-2000.
    inside = polygon.buffer(EPS)
    for edge in edges.geoms:
        if edge.length <= EPS or not inside.covers(edge):
            continue
        a, b = [tuple(round(v, 8) for v in c[:2]) for c in (edge.coords[0], edge.coords[-1])]
        if a == b:
            continue
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    if not graph:
        raise ValueError("không trích được tim hẻm từ polygon")

    # Rectangular caps generate two diagonal leaf spurs, each sqrt(2)*radius.
    # Remove only short terminal arms relative to the junction's local radius.
    while True:
        remove = set()
        for leaf in [node for node in graph if len(graph[node]) == 1]:
            path = [leaf]
            length = 0.0
            previous, current = None, leaf
            while True:
                following = [n for n in graph[current] if n != previous]
                if not following:
                    break
                nxt = following[0]
                length += math.dist(current, nxt)
                previous, current = current, nxt
                path.append(current)
                if len(graph[current]) != 2:
                    break
            radius = Point(current).distance(polygon.boundary)
            if len(graph[current]) >= 3 and length <= 1.8 * radius + 2 * spacing:
                remove.update(path[:-1])
        if not remove:
            break
        for node in remove:
            for neighbour in graph.pop(node, set()):
                if neighbour in graph:
                    graph[neighbour].discard(node)
        graph = {n: links for n, links in graph.items() if links}

    if not graph:
        raise ValueError("hẻm quá ngắn/rộng để xác định chiều chắc chắn")
    ends = [node for node in graph if len(graph[node]) == 1]
    if len(ends) < 2:
        raise ValueError("tim hẻm có vòng; chưa xác định được chiều từ miệng hẻm")

    visited = set()
    stack = [next(iter(graph))]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph[node] - visited)
    if len(visited) != len(graph):
        raise ValueError("tim hẻm có đoạn rời; cần kiểm tra hình học")
    edge_count = sum(len(links) for links in graph.values()) // 2
    if edge_count != len(graph) - 1:
        raise ValueError("tim hẻm có vòng; chưa xác định được chiều từ miệng hẻm")
    return graph, spacing


def _ordered_line(graph, spacing):
    """Turn a non-branching medial graph into the historical LineString."""
    if any(len(links) > 2 for links in graph.values()):
        raise ValueError("tim hẻm là mạng phân nhánh")
    ends = [node for node in graph if len(graph[node]) == 1]
    ordered = [min(ends)]
    previous = None
    while True:
        current = ordered[-1]
        following = [n for n in graph[current] if n != previous]
        if not following:
            break
        previous = current
        ordered.append(following[0])
        if len(ordered) > len(graph):
            raise ValueError("tim hẻm tạo vòng")
    if len(ordered) != len(graph):
        raise ValueError("tim hẻm có đoạn rời/vòng chưa xử lý được")
    return LineString(ordered).simplify(spacing / 4, preserve_topology=True)


def _endpoint_records(graph):
    records = []
    for node, links in graph.items():
        if len(links) != 1:
            continue
        neighbour = next(iter(links))
        records.append(dict(node=node, point=Point(node), inside=Point(neighbour)))
    return records


def _orient_network(graph, root, mouth):
    """Root a tree at the chosen mouth and return directed weighted edges."""
    root_point = Point(root)
    connector = float(mouth.distance(root_point))
    edges = []
    if connector > EPS:
        edges.append(NetworkEdge(LineString([mouth, root_point]), 0.0))

    parent = {root: None}
    distance = {root: connector}
    stack = [root]
    order = []
    while stack:
        node = stack.pop()
        order.append(node)
        for neighbour in sorted(graph[node]):
            if neighbour == parent[node]:
                continue
            if neighbour in parent:
                raise ValueError("tim hẻm có vòng; chưa xác định được chiều từ miệng hẻm")
            parent[neighbour] = node
            distance[neighbour] = distance[node] + math.dist(node, neighbour)
            stack.append(neighbour)
    if len(parent) != len(graph):
        raise ValueError("tim hẻm có đoạn rời; cần kiểm tra hình học")

    # Collapse degree-2 runs into branch segments. This preserves topology and
    # distance while avoiding thousands of 25 cm Voronoi edges at projection.
    for node in order:
        if node != root and len(graph[node]) == 2:
            continue
        for neighbour in sorted(graph[node]):
            if parent.get(neighbour) != node:
                continue
            coordinates = [node, neighbour]
            current = neighbour
            while len(graph[current]) == 2:
                children = [candidate for candidate in graph[current]
                            if parent.get(candidate) == current]
                if not children:
                    break
                current = children[0]
                coordinates.append(current)
            edges.append(NetworkEdge(LineString(coordinates), distance[node]))

    leaves = [node for node, links in graph.items() if len(links) == 1 and node != root]
    farthest = max(leaves or [root], key=lambda node: distance[node])
    path = []
    current = farthest
    while current is not None:
        path.append(current)
        current = parent[current]
    path.reverse()
    coordinates = [mouth.coords[0]] if connector > EPS else []
    coordinates.extend(path)
    trunk = LineString(coordinates)
    return trunk, tuple(edges)


def _entrances(polygon, line, road_groups, own_key, tolerant_parent_keys=None,
               endpoints=None, sibling_keys=None):
    candidates, warnings = [], []
    tolerant_parent_keys = set(tolerant_parent_keys or ())
    sibling_keys = set(sibling_keys or ())
    if endpoints is None:
        endpoints = [
            dict(node=tuple(line.coords[0]), point=Point(line.coords[0]),
                 inside=Point(line.coords[min(1, len(line.coords) - 1)])),
            dict(node=tuple(line.coords[-1]), point=Point(line.coords[-1]),
                 inside=Point(line.coords[max(0, len(line.coords) - 2)])),
        ]
    for key, (name, geometry) in road_groups.items():
        if key == own_key:
            continue
        exact_contact = polygon.intersects(geometry)
        gap = polygon.distance(geometry) if key in tolerant_parent_keys else math.inf
        if not exact_contact and gap > GEOMETRY_TOLERANCE_M + EPS:
            continue
        # Only valid polygon references participate. Invalid touching references
        # are errors, not silently ignored when looking for an entrance.
        if geometry.geom_type in ("LineString", "MultiLineString"):
            raise ValueError(f"đường tham chiếu '{name}' là tim đường (polyline); "
                             "hẻm chỉ đánh được khi đường cha là polygon")
        if not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"đường tham chiếu '{name}' có hình học không hợp lệ")

        digitizing_warning = ""
        if exact_contact:
            contact = polygon.intersection(geometry)
            if _label_is_alley(name) and _thin_polygon_overlap(contact):
                warnings.append(
                    f"Sai số digitize được chấp nhận · Bỏ qua dải chồng mỏng với '{name}' (≤ 10 cm)"
                )
                continue
            if key in sibling_keys:
                warnings.append(
                    f"Tiếp giáp '{name}' cùng đường cha · Không dùng làm miệng hẻm"
                )
                continue
            parts = [
                part for part in _components(contact)
                if part.length > EPS or part.area > EPS
                or ((key in tolerant_parent_keys or _label_is_alley(name))
                    and part.geom_type == "Point")
            ]
            if (key in tolerant_parent_keys and parts
                    and all(part.geom_type == "Point" for part in parts)):
                digitizing_warning = (
                    "Sai số digitize được chấp nhận · Miệng hẻm chỉ tiếp giáp đường cha tại một điểm"
                )
        else:
            alley_point, parent_point = nearest_points(polygon, geometry)
            contact = LineString([alley_point, parent_point])
            parts = [alley_point]
            digitizing_warning = (
                "Sai số digitize được chấp nhận · "
                f"Dùng dung sai miệng hẻm: {gap * 100:.1f} cm".replace(".", ",")
            )
        # Merge adjacent contact fragments before counting openings.
        groups = []
        for part in parts:
            merged = part
            remaining = []
            for other in groups:
                if merged.distance(other) <= EPS:
                    merged = unary_union([merged, other])
                else:
                    remaining.append(other)
            groups = remaining + [merged]
        for contact in groups:
            mouth = contact.centroid
            distances = [record["point"].distance(mouth) for record in endpoints]
            end_index = min(range(len(endpoints)), key=lambda i: distances[i])
            endpoint = endpoints[end_index]
            radius = endpoint["point"].distance(polygon.boundary)
            if distances[end_index] > max(2.5 * radius, .5):
                raise ValueError(f"giao với '{name}' ở giữa hẻm; chưa xác định được miệng hẻm")
            ordered_distances = sorted(distances)
            if len(ordered_distances) > 1 and abs(ordered_distances[0] - ordered_distances[1]) <= EPS:
                raise ValueError(f"không phân biệt được đầu hẻm giáp '{name}'")
            candidates.append(dict(key=key, name=name, geometry=geometry,
                                   contact=contact, mouth=mouth, end=endpoint["node"],
                                   inside=endpoint["inside"],
                                   warning=digitizing_warning))
    return candidates, warnings


def _cross_section_width(candidate, line):
    """Measure the parent-road cross section along the alley approach.

    Only near-perpendicular approaches are accepted; oblique/ambiguous shapes
    do not provide a defensible width comparison and must be checked by user.
    """
    mouth = candidate["mouth"]
    p = candidate["inside"]
    dx, dy = mouth.x - p.x, mouth.y - p.y
    norm = math.hypot(dx, dy)
    if norm <= EPS:
        raise ValueError("không xác định được hướng đo mặt cắt đường")
    dx, dy = dx / norm, dy / norm
    parent = candidate["geometry"]
    minx, miny, maxx, maxy = parent.bounds
    span = math.hypot(maxx - minx, maxy - miny) + line.length
    cut = LineString([(mouth.x - dx * span, mouth.y - dy * span),
                      (mouth.x + dx * span, mouth.y + dy * span)])
    parts = [part for part in lay_cac_line(parent.intersection(cut)) if part.distance(mouth) <= EPS]
    if len(parts) != 1:
        raise ValueError("không xác định được mặt cắt đường tại miệng hẻm")
    # Two small parallel samples must agree, rejecting intersections and taper.
    width = parts[0].length
    for offset in (-.25 * width, .25 * width):
        shifted = LineString([(x - dy * offset, y + dx * offset) for x, y in cut.coords])
        nearby = [part for part in lay_cac_line(parent.intersection(shifted))
                  if part.distance(parts[0]) < abs(offset) + EPS]
        if len(nearby) != 1 or abs(nearby[0].length - width) > .1 * width:
            raise ValueError("mặt cắt đường không ổn định; cần xác định đường gốc")
    # Shared mouth should be parallel to parent boundary, perpendicular to cut.
    contacts = lay_cac_line(candidate["contact"])
    if not contacts:
        raise ValueError("polygon chồng lấn; chưa so sánh được mặt cắt đường")
    longest = max(contacts, key=lambda segment: segment.length)
    a, b = longest.coords[0], longest.coords[-1]
    length = math.dist(a, b)
    if length <= EPS or abs((b[0] - a[0]) * dx + (b[1] - a[1]) * dy) / length > .17:
        raise ValueError("miệng hẻm giao xiên; chưa so sánh được mặt cắt đường")
    return width


def resolve_alley(name, parsed, road_groups, own_key=None, explicit_parent_key=None,
                   tolerant_parent_keys=None):
    key = own_key if own_key is not None else khoa_ten(name)
    polygon = road_groups[key][1]
    if not polygon.is_valid or polygon.is_empty:
        raise ValueError("polygon hẻm không hợp lệ hoặc rỗng")
    graph, spacing = _medial_topology(polygon)
    endpoints = _endpoint_records(graph)
    if not endpoints:
        raise ValueError("tim hẻm không có đầu tuyến để xác định miệng")

    if explicit_parent_key is not None:
        sibling_keys = {
            candidate for candidate in road_groups
            if (isinstance(candidate, tuple) and len(candidate) == 2
                and candidate[0] == explicit_parent_key[0] and candidate[1]
                and candidate != key)
        }
    elif parsed.parent_hint:
        sibling_keys = set()
        expected_parent = _parent_key(parsed.parent_hint)
        for candidate, (candidate_name, _) in road_groups.items():
            if candidate == key or not _label_is_alley(candidate_name):
                continue
            try:
                candidate_parsed = parse_alley_name(candidate_name)
            except ValueError:
                continue
            if candidate_parsed.parent_hint and _parent_key(candidate_parsed.parent_hint) == expected_parent:
                sibling_keys.add(candidate)
    else:
        sibling_keys = set()

    # A representative line is only needed for two-road width comparison.
    # Branched routes use the rooted network for the actual numbering.
    if any(len(links) > 2 for links in graph.values()):
        a = endpoints[0]["node"]
        b = max((record["node"] for record in endpoints[1:]),
                key=lambda node: math.dist(a, node), default=a)
        line = LineString([a, b])
    else:
        line = _ordered_line(graph, spacing)
    candidates, warnings = _entrances(
        polygon, line, road_groups, key, tolerant_parent_keys=tolerant_parent_keys,
        endpoints=endpoints, sibling_keys=sibling_keys)
    if not candidates:
        raise ValueError("không tìm thấy miệng hẻm tiếp giáp đường chính; kiểm tra polygon tham chiếu")
    if len(candidates) > 2 or len({c["end"] for c in candidates}) != len(candidates):
        raise ValueError("có nhiều miệng/đường gốc phù hợp; cần chuẩn hóa hình học")
    named = ([c for c in candidates if c["key"] == explicit_parent_key]
             if explicit_parent_key is not None else
             [c for c in candidates if parsed.parent_hint and _parent_key(c["name"]) == _parent_key(parsed.parent_hint)])
    if len(named) > 1:
        raise ValueError("cả hai đầu cùng nối đường mang tên; chưa xác định được đầu hẻm")
    if len(candidates) == 1:
        chosen = candidates[0]
        if explicit_parent_key is not None and not named:
            raise ValueError("polygon hẻm không tiếp giáp polygon đường cha")
        if parsed.parent_hint and not named and explicit_parent_key is None:
            # A named alley (e.g. Hẻm Hoa Mai) can have its own name. But if the
            # suffix names an existing parent elsewhere, it is a mismatch.
            if (parsed.prefix or re.match(r"^(?:đường|duong)\s+", parsed.parent_hint, re.IGNORECASE)
                    or any(_parent_key(n) == _parent_key(parsed.parent_hint) for n, _ in road_groups.values())):
                raise ValueError("đường gốc trong tên hẻm không tiếp giáp miệng hẻm")
    elif named:
        chosen = named[0]
    elif parsed.parent_hint:
        raise ValueError("hẻm thông hai đường nhưng chưa khớp được đường gốc trong tên")
    else:
        widths = [_cross_section_width(c, line) for c in candidates]
        if abs(widths[0] - widths[1]) <= max(.1, .05 * max(widths)):
            raise ValueError("hai đường có mặt cắt bằng/gần nhau; chưa xác định được đường lớn hơn")
        chosen = candidates[0 if widths[0] > widths[1] else 1]
    if parse_alley_name(chosen["name"]).is_alley:
        raise ValueError("hẻm nối vào hẻm khác; hẻm nhiều cấp chưa được hỗ trợ")
    mouth = chosen["mouth"]
    root = chosen["end"]
    entrance_segment = LineString([mouth, Point(root)])
    if not polygon.buffer(EPS).covers(entrance_segment):
        raise ValueError("không nối được miệng hẻm với tim hẻm trong polygon")
    line, network_edges = _orient_network(graph, root, mouth)
    branch_count = max(0, len(endpoints) - 1) if len(endpoints) > 2 else 0
    if branch_count:
        warnings.append(
            f"Mạng hẻm phân nhánh · Đánh số theo khoảng cách từ miệng trên {branch_count} nhánh"
        )
    if chosen.get("warning"):
        warnings.append(chosen["warning"])
    return AlleyRoute(
        name=name, prefix=parsed.prefix, parent_name=chosen["name"],
        polygon=polygon, line=line, network_edges=network_edges,
        branch_count=branch_count, warnings=tuple(dict.fromkeys(warnings)),
    )


LINE_TYPES = ("LineString", "MultiLineString")
# Đầu tim hẻm cách tim (hoặc mép) đường cha tối đa bao nhiêu mét thì được nhận là miệng hẻm.
MIENG_HEM_TIM_TOI_DA_M = 20.0


def _tim_graph(geometry):
    """Tree graph {node: {neighbours}} from an alley centerline (no spur trimming)."""
    from core_housenumber import phan_tich_tim_duong

    tim = phan_tich_tim_duong([geometry], rau_toi_da=0)
    lines = tim["lines"]
    if not lines:
        raise ValueError("tim hẻm rỗng hoặc có độ dài 0")
    if len(set(tim["cum"])) > 1:
        raise ValueError("tim hẻm có đoạn rời (khe hở lớn hơn 10 cm); cần nối lại tim")
    if tim["vong"]:
        raise ValueError("tim hẻm có vòng; chưa xác định được chiều từ miệng hẻm")
    graph = {}
    for line in lines:
        coords = [tuple(c[:2]) for c in line.coords]
        for a, b in zip(coords, coords[1:]):
            if a != b:
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set()).add(a)
    edge_count = sum(len(links) for links in graph.values()) // 2
    if edge_count != len(graph) - 1:
        raise ValueError("tim hẻm có vòng; chưa xác định được chiều từ miệng hẻm")
    return graph


def resolve_alley_tim(name, parsed, geometry, parents):
    """
    Alley drawn as a centerline: the mouth is the alley end nearest the parent.

    The nearest end must lie within MIENG_HEM_TIM_TOI_DA_M of the parent and be
    clearly nearer than every other end; otherwise the entrance is ambiguous.
    """
    graph = _tim_graph(geometry)
    ends = [node for node, links in graph.items() if len(links) == 1]
    if not parents:
        raise ValueError(f"không tìm thấy đường chính trong phạm vi {MIENG_HEM_TIM_TOI_DA_M:.0f} m "
                         "quanh tim hẻm; ghi đường cha trong tên hẻm hoặc tenHem")
    for parent_name, parent_geometry in parents.values():
        if parent_geometry is None or parent_geometry.is_empty:
            raise ValueError(f"đường cha '{parent_name}' có hình học rỗng")

    matches = sorted(
        ((Point(end).distance(parent_geometry), end, parent_name, parent_geometry)
         for end in ends
         for parent_name, parent_geometry in parents.values()),
        key=lambda item: (item[0], item[1]),
    )
    distance, root, parent_name, parent_geometry = matches[0]
    if distance > MIENG_HEM_TIM_TOI_DA_M:
        raise ValueError(f"không tìm thấy miệng hẻm: đầu tim hẻm gần nhất cách '{parent_name}' "
                         f"{distance:.1f} m (tối đa {MIENG_HEM_TIM_TOI_DA_M:.0f} m)")
    others = [m for m in matches[1:] if m[1] != root and m[0] <= MIENG_HEM_TIM_TOI_DA_M]
    if others and others[0][0] <= 2 * distance + 2.0:
        raise ValueError(f"có nhiều đầu tim hẻm gần đường cha ('{parent_name}' và '{others[0][2]}'); "
                         "chưa xác định được miệng hẻm")
    mouth = nearest_points(parent_geometry, Point(root))[0]
    line, network_edges = _orient_network(graph, root, mouth)
    branch_count = max(0, len(ends) - 1) if len(ends) > 2 else 0
    warnings = []
    if branch_count:
        warnings.append(
            f"Mạng hẻm phân nhánh · Đánh số theo khoảng cách từ miệng trên {branch_count} nhánh")
    return AlleyRoute(
        name=name, prefix=parsed.prefix, parent_name=parent_name,
        polygon=None, line=line, network_edges=network_edges,
        branch_count=branch_count, warnings=tuple(warnings),
    )


def prepare_alleys(route_keys, reference_roads, hierarchical=None):
    """Resolve only selected alleys and the references they actually require."""
    contexts, rows, errors = {}, [], []
    if hierarchical is None:
        hierarchical = FIELD_ALLEY in reference_roads.columns
    if FIELD_ROUTE not in reference_roads.columns:
        return contexts, rows, [f"Lớp đường thiếu trường bắt buộc '{FIELD_ROUTE}'."]

    ref_keys = route_key_series(reference_roads, hierarchical)
    grouped_indices = {}
    displays = {}
    for index, key in ref_keys.items():
        if key == ("", ""):
            continue
        grouped_indices.setdefault(key, []).append(index)
        row = reference_roads.loc[index]
        displays.setdefault(key, route_label(row[FIELD_ROUTE], row[FIELD_ALLEY] if hierarchical else ""))

    # Old callers may still pass full tenDuong strings.
    normalized = []
    for value in route_keys:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            key = (normalize_name(value[0]), normalize_name(value[1]))
        else:
            key = (normalize_name(value), "")
        if key not in normalized:
            normalized.append(key)

    union_cache = {}
    def union_for(key):
        if key in union_cache:
            return union_cache[key]
        indices = grouped_indices.get(key, [])
        if not indices:
            raise ValueError("không có polygon đường tương ứng")
        try:
            geometry = unary_union(list(reference_roads.loc[indices].geometry))
        except Exception as exc:
            raise ValueError(f"không hợp nhất được hình học ({type(exc).__name__})") from exc
        union_cache[key] = (displays[key], geometry)
        return union_cache[key]

    try:
        spatial_index = reference_roads.sindex
    except Exception:
        spatial_index = None

    for key in normalized:
        parent_key, alley_key = key
        name = displays.get(key, route_label(*key))
        source_name = displays.get(key, name)
        parse_value = source_name.split(" › ", 1)[1] if hierarchical and " › " in source_name else source_name
        try:
            parsed = parse_alley_name(parse_value)
        except ValueError as exc:
            errors.append(str(exc))
            rows.append(dict(route=name, prefix="—", parent="—", status=str(exc), is_alley=True))
            continue
        is_alley = bool(alley_key) if hierarchical else parsed.is_alley
        if not is_alley:
            continue
        row = dict(route=name, prefix=parsed.prefix or "Không số", parent="—", status="", is_alley=True)
        try:
            own = union_for(key)
            if own[1].geom_type in LINE_TYPES:
                if hierarchical:
                    parent_keys = [(parent_key, "")]
                    if parent_keys[0] not in grouped_indices:
                        raise ValueError("thiếu đường chính có tenHem trống để làm đường cha")
                elif parsed.parent_hint:
                    parent_keys = [
                        candidate for candidate, label in displays.items()
                        if candidate != key and not _label_is_alley(label)
                        and _parent_key(label) == _parent_key(parsed.parent_hint)
                    ]
                    if not parent_keys:
                        raise ValueError(f"không tìm thấy đường cha '{parsed.parent_hint}' trong lớp đường")
                else:
                    near = own[1].buffer(MIENG_HEM_TIM_TOI_DA_M)
                    positions = (spatial_index.query(near, predicate="intersects")
                                 if spatial_index is not None else range(len(reference_roads)))
                    parent_keys = sorted({
                        ref_keys.iloc[pos] for pos in positions
                        if ref_keys.iloc[pos] not in (key, ("", ""))
                        and not _label_is_alley(displays.get(ref_keys.iloc[pos], ""))
                    })
                context = resolve_alley_tim(
                    name, parsed, own[1], {candidate: union_for(candidate) for candidate in parent_keys})
            else:
                relevant = {key: own}
                explicit_parent_key = None
                tolerant_parent_keys = set()
                if hierarchical:
                    explicit_parent_key = (parent_key, "")
                    if explicit_parent_key not in grouped_indices:
                        raise ValueError("thiếu polygon đường chính có tenHem trống để làm đường cha")
                    relevant[explicit_parent_key] = union_for(explicit_parent_key)
                    if relevant[explicit_parent_key][1].geom_type not in ("Polygon", "MultiPolygon"):
                        raise ValueError(f"đường cha '{relevant[explicit_parent_key][0]}' là tim đường "
                                         "(polyline); hẻm vẽ bằng polygon cần đường cha polygon, "
                                         "hoặc vẽ cả hẻm bằng tim đường")
                    tolerant_parent_keys.add(explicit_parent_key)
                    # The explicit parent fixes direction, but touching alley
                    # polygons are still inspected to reject real level-2 links
                    # and ignore only sub-tolerance digitizing slivers.
                    if spatial_index is not None:
                        try:
                            neighbours = spatial_index.query(own[1], predicate="intersects")
                        except Exception:
                            neighbours = spatial_index.query(own[1])
                        neighbour_keys = {ref_keys.iloc[pos] for pos in neighbours}
                        for candidate in neighbour_keys - {key, explicit_parent_key, ("", "")}:
                            if candidate[1]:
                                relevant[candidate] = union_for(candidate)
                else:
                    own_geometry = own[1]
                    candidate_indices = []
                    if spatial_index is not None:
                        try:
                            candidate_indices = list(spatial_index.query(
                                own_geometry.buffer(GEOMETRY_TOLERANCE_M), predicate="intersects"))
                        except Exception:
                            candidate_indices = list(spatial_index.query(
                                own_geometry.buffer(GEOMETRY_TOLERANCE_M)))
                    else:
                        candidate_indices = [pos for pos, geom in enumerate(reference_roads.geometry)
                                             if geom is not None and not geom.is_empty
                                             and geom.bounds[2] >= own_geometry.bounds[0]
                                             and geom.bounds[0] <= own_geometry.bounds[2]
                                             and geom.bounds[3] >= own_geometry.bounds[1]
                                             and geom.bounds[1] <= own_geometry.bounds[3]]
                    candidate_keys = {ref_keys.iloc[pos] for pos in candidate_indices}
                    named_keys = set()
                    if parsed.parent_hint:
                        named_keys = {
                            candidate for candidate, label in displays.items()
                            if candidate != key and _parent_key(label) == _parent_key(parsed.parent_hint)
                        }
                        candidate_keys.update(named_keys)
                        tolerant_parent_keys.update(named_keys)
                    for candidate in candidate_keys - {key, ("", "")}:
                        # Bounding-box candidates are cheap; exact contact avoids
                        # validating or unioning unrelated routes. A small gap is
                        # considered only for the parent named by the alley.
                        parts = reference_roads.loc[grouped_indices[candidate]].geometry
                        exact = any(geom is not None and not geom.is_empty and own_geometry.intersects(geom)
                                    for geom in parts)
                        near_named = (candidate in named_keys and any(
                            geom is not None and not geom.is_empty
                            and own_geometry.distance(geom) <= GEOMETRY_TOLERANCE_M + EPS
                            for geom in parts))
                        if exact or near_named:
                            relevant[candidate] = union_for(candidate)
                context = resolve_alley(
                    name, parsed, relevant, key, explicit_parent_key,
                    tolerant_parent_keys=tolerant_parent_keys)
            contexts[key] = context
            warning = " · ".join(context.warnings)
            status = "Từ miệng hẻm vào trong · Trái lẻ / phải chẵn"
            if warning:
                status += " · ⚠ " + warning
            row.update(parent=context.parent_name, status=status, warning=warning)
        except (ValueError, RuntimeError, GEOSException) as exc:
            message = f"{name}: {exc}"
            errors.append(message)
            row["status"] = str(exc)
        rows.append(row)
    return contexts, rows, errors


def _network_position(point, edges):
    """Project a frontage onto the rooted tree and return local direction."""
    candidates = []
    for edge_index, edge in enumerate(edges):
        along = edge.line.project(point)
        projected = edge.line.interpolate(along)
        delta = min(.25, max(edge.line.length / 100, EPS))
        before = edge.line.interpolate(max(0, along - delta))
        after = edge.line.interpolate(min(edge.line.length, along + delta))
        dx = after.x - before.x
        dy = after.y - before.y
        candidates.append((
            point.distance(projected), edge.offset + along, edge_index,
            projected, dx, dy,
        ))
    if not candidates:
        raise ValueError("tim mạng hẻm rỗng")
    _, measure, edge_index, projected, dx, dy = min(
        candidates, key=lambda item: (item[0], item[1], item[2]))
    return measure, edge_index, projected, dx, dy


def number_alley(group, context):
    """Order frontage along the entrance-oriented line; use local side signs."""
    group = group.copy()
    line, polygon = context.line, context.polygon
    network = (unary_union([edge.line for edge in context.network_edges] or [line])
               if polygon is None else None)
    numbered = []
    for index, row in group.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"{context.name}: thửa có hình học không hợp lệ")
        if polygon is None:
            # Centerline alley: frontage = parcel boundary nearest the network.
            near = network.buffer(geometry.distance(network) + MAT_TIEN_TIM_BAND_M)
            frontages = lay_cac_line(geometry.boundary.intersection(near))
            front = (max(frontages, key=lambda part: part.length).interpolate(.5, normalized=True)
                     if frontages else nearest_points(geometry, network)[0])
        else:
            shared = geometry.boundary.intersection(polygon.boundary)
            frontages = lay_cac_line(shared)
            if frontages:
                front = max(frontages, key=lambda part: part.length).interpolate(.5, normalized=True)
            else:
                front = nearest_points(polygon.boundary, geometry.representative_point())[0]
        if context.branch_count:
            measure, branch_order, on_line, dx, dy = _network_position(
                front, context.network_edges)
        else:
            measure = line.project(front)
            on_line = line.interpolate(measure)
            delta = min(.25, line.length / 100)
            a = line.interpolate(max(0, measure - delta))
            b = line.interpolate(min(line.length, measure + delta))
            dx, dy = b.x - a.x, b.y - a.y
            branch_order = 0
        interior = geometry.representative_point()
        cross = dx * (interior.y - on_line.y) - dy * (interior.x - on_line.x)
        if abs(cross) <= EPS:
            raise ValueError(f"{context.name}: thửa ở đầu/cuối hẻm chưa xác định được bên trái/phải")
        side = GT_TRAI if cross > 0 else GT_PHAI
        numbered.append((index, side, measure, branch_order))
    for side in (GT_TRAI, GT_PHAI):
        ordered = sorted(
            (item for item in numbered if item[1] == side),
            key=lambda item: (item[2], item[3], str(item[0])),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if not context.branch_count and abs(previous[2] - current[2]) <= EPS:
                raise ValueError(f"{context.name}: hai thửa cùng vị trí dọc hẻm; cần kiểm tra mặt tiền")
        for rank, (index, _, _, _) in enumerate(ordered, 1):
            group.at[index, COL_BEN] = side
            group.at[index, COL_STT] = STEP * rank
            group.at[index, COL_SONHA] = 2 * rank - 1 if side == GT_TRAI else 2 * rank
            group.at[index, COL_HUONG] = "MIENG-HEM"
    return group


def format_house_numbers(out, contexts):
    result = []
    hierarchical = FIELD_ALLEY in out.columns
    keys = route_key_series(out, hierarchical)
    for key, number in zip(keys, out[COL_SONHA]):
        if pd.isna(number):
            result.append(None)
            continue
        context = contexts.get(key)
        # Compatibility for contexts created by versions before structured keys.
        if context is None and not hierarchical:
            context = contexts.get(key[0])
        prefix = context.prefix if context else ""
        result.append(f"{prefix}/{int(number)}" if prefix else str(int(number)))
    out[COL_SONHA] = pd.array(result, dtype="string")
    return out
