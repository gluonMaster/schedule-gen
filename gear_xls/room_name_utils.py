"""Helpers for normalizing room identifiers across Excel and web layers."""

from __future__ import annotations


_BUILDING_PREFIXES = {
    "Villa": "V",
    "Kolibri": "K",
}


def normalize_room_name(room, building=None):
    """Strip the building prefix from a room identifier when it is redundant.

    Examples:
    - Villa + ``V2.03`` -> ``2.03``
    - Villa + ``VK.07`` -> ``K.07``
    - Kolibri + ``K3.1`` -> ``3.1``
    - Villa + ``K.07`` -> ``K.07`` (basement room, already normalized)
    """

    normalized_room = str(room or "").strip()
    building_name = str(building or "").strip()
    prefix = _BUILDING_PREFIXES.get(building_name)

    if not normalized_room or not prefix:
        return normalized_room
    if (
        len(normalized_room) > len(prefix)
        and normalized_room[: len(prefix)].upper() == prefix
    ):
        return normalized_room[len(prefix) :].strip()
    return normalized_room


def normalize_room_fields(block):
    """Return a shallow-copied block with normalized room-related fields."""

    if not isinstance(block, dict):
        return block

    normalized = dict(block)
    normalized_room = normalize_room_name(
        normalized.get("room"), normalized.get("building")
    )
    normalized_room_display = normalize_room_name(
        normalized.get("room_display"), normalized.get("building")
    )

    if normalized_room:
        normalized["room"] = normalized_room

    if "room_display" in normalized:
        normalized["room_display"] = normalized_room_display or normalized_room
    elif normalized_room:
        normalized["room_display"] = normalized_room

    return normalized
