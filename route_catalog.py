# -*- coding: utf-8 -*-
"""Route identity, schema validation and parent/alley catalog helpers."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

FIELD_ROUTE = "tenDuong"
FIELD_ALLEY = "tenHem"
ROUTE_SEPARATOR = " › "


def normalize_name(value):
    """Normalize identity without changing accents, spelling or inner spaces."""
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value).strip()).casefold()


def display_name(value):
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value).strip())


def validate_route_schema(houses, roads):
    for table, label in ((houses, "thửa"), (roads, "đường")):
        if FIELD_ROUTE not in table.columns:
            raise ValueError(f"Lớp {label} thiếu trường bắt buộc '{FIELD_ROUTE}'.")
    house_alley = FIELD_ALLEY in houses.columns
    road_alley = FIELD_ALLEY in roads.columns
    if house_alley != road_alley:
        present = houses if house_alley else roads
        # A tenHem column left entirely blank in only one layer carries no
        # alley information: fall back to the tenDuong-only schema.
        if not present[FIELD_ALLEY].map(normalize_name).astype(bool).any():
            return False
        missing = "đường" if house_alley else "thửa"
        raise ValueError(
            f"Schema tenHem không đồng nhất: lớp {missing} thiếu trường '{FIELD_ALLEY}' trong khi lớp kia "
            "có giá trị tenHem. Hãy thêm tenHem vào cả hai lớp, hoặc bỏ/để trống trường này ở lớp kia."
        )
    return house_alley


def route_key(parent, alley=""):
    return normalize_name(parent), normalize_name(alley)


def route_key_series(table, hierarchical):
    parents = table[FIELD_ROUTE].map(normalize_name)
    if hierarchical:
        alleys = table[FIELD_ALLEY].map(normalize_name)
    else:
        alleys = pd.Series("", index=table.index, dtype="object")
    return pd.Series(list(zip(parents, alleys)), index=table.index, dtype="object")


def route_label(parent, alley=""):
    parent = display_name(parent)
    alley = display_name(alley)
    return f"{parent}{ROUTE_SEPARATOR}{alley}" if alley else parent


def _natural_key(value):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", normalize_name(value))]


def build_route_catalog(houses, roads):
    """Return common leaf routes grouped by parent road."""
    hierarchical = validate_route_schema(houses, roads)
    house_keys = route_key_series(houses, hierarchical)
    road_keys = route_key_series(roads, hierarchical)
    common = (set(house_keys) & set(road_keys)) - {("", "")}

    displays = {}
    for table, keys in ((roads, road_keys), (houses, house_keys)):
        for key, parent, alley in zip(
            keys,
            table[FIELD_ROUTE],
            table[FIELD_ALLEY] if hierarchical else [""] * len(table),
        ):
            if key in common:
                displays.setdefault(key, (display_name(parent), display_name(alley)))

    grouped = {}
    for key in common:
        parent, alley = displays[key]
        group = grouped.setdefault(key[0], {"parent": parent, "items": []})
        group["items"].append({
            "key": key,
            "parent": parent,
            "alley": alley,
            "label": route_label(parent, alley),
            "is_main": not bool(key[1]),
        })

    groups = []
    for parent_key, group in grouped.items():
        group["items"].sort(key=lambda item: (not item["is_main"], _natural_key(item["alley"])))
        groups.append({"key": parent_key, **group})
    groups.sort(key=lambda group: _natural_key(group["parent"]))
    items = [item for group in groups for item in group["items"]]
    return {
        "hierarchical": hierarchical,
        "groups": groups,
        "items": items,
        "keys": [item["key"] for item in items],
    }


def resolve_manual_selection(catalog, text):
    """Resolve legacy semicolon text or the qualified ``parent › alley`` form."""
    text = str(text or "").strip()
    if not text:
        return None
    known = {tuple(item["key"]): item for item in catalog["items"]}
    by_label = {normalize_name(item["label"]): tuple(item["key"]) for item in catalog["items"]}

    # A plain parent in the two-field schema means its main road and all alleys.
    if catalog["hierarchical"] and "›" not in text:
        parent_match = [tuple(key) for key in known if key[0] == normalize_name(text)]
        if parent_match:
            return parent_match
    # Preserve old values which contain a semicolon when the exact label exists.
    if normalize_name(text) in by_label:
        return [by_label[normalize_name(text)]]
    tokens = [token.strip() for token in text.split(";") if token.strip()]
    if not tokens:
        raise ValueError("Hãy chọn ít nhất một tuyến hoặc để trống để chạy tất cả.")

    selected = []
    missing = []
    for token in tokens:
        if catalog["hierarchical"] and "›" in token:
            parent, alley = [part.strip() for part in token.split("›", 1)]
            key = route_key(parent, alley)
            if key in known:
                selected.append(key)
            else:
                missing.append(token)
            continue
        parent_key = normalize_name(token)
        matches = [key for key in known if key[0] == parent_key]
        if matches:
            selected.extend(matches)
        else:
            missing.append(token)
    if missing:
        raise ValueError(
            "Tuyến không có trong cả hai lớp: " + "; ".join(missing)
            + (f". Với schema {FIELD_ALLEY}, nhập theo dạng Đường cha › Hẻm." if catalog["hierarchical"] else "")
        )
    return list(dict.fromkeys(selected))


def normalize_selected_keys(catalog, selected):
    if selected is None:
        return None
    known = {tuple(key) for key in catalog["keys"]}
    result = []
    for value in selected:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            key = route_key(value[0], value[1])
        else:
            key = route_key(value)
        if key not in known:
            raise ValueError(f"Tuyến đã chọn không còn tồn tại trong cả hai lớp: {value}")
        result.append(key)
    result = list(dict.fromkeys(result))
    if not result:
        raise ValueError("Chưa chọn tuyến nào. Hãy chọn ít nhất một tuyến.")
    return result


def selection_text(catalog, keys):
    if keys is None:
        return "Tất cả tuyến"
    lookup = {tuple(item["key"]): item["label"] for item in catalog["items"]}
    labels = [lookup.get(tuple(key), route_label(*key)) for key in keys]
    return labels[0] if len(labels) == 1 else f"{len(labels)} tuyến đã chọn"
