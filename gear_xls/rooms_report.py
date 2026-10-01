import json
import logging
import os
import re
import sys
from html import unescape

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gear_xls.runtime_paths import (
    get_base_schedule_path,
    get_individual_lessons_path,
    get_schedule_html_path,
    get_spiski_dir,
)
from gear_xls.day_constants import DAY_TO_WEEKDAY

try:
    from . import state_manager
except ImportError:
    import state_manager


BASE_SCHEDULE_PATH = get_base_schedule_path()
INDIVIDUAL_LESSONS_PATH = get_individual_lessons_path()
SCHEDULE_HTML_PATH = get_schedule_html_path()
SPISKI_DIR = get_spiski_dir()
SPISKI_ROOM_FILE_MAP = {
    "Villa": "kabinets_Villa.txt",
    "Kolibri": "kabinets_Kolibri.txt",
}
BUILDING_ORDER = ["Villa", "Kolibri"]
DAY_ORDER = dict(DAY_TO_WEEKDAY)


def _load_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logging.warning("Failed to read JSON from %s: %s", path, exc)
        return {}


def _spiski_sort_key(value: str):
    parts = re.findall(r"\d+|\D+", (value or "").strip())
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    return tuple(key)


def _load_configured_rooms() -> dict[str, list[str]]:
    configured = {}
    for building, filename in SPISKI_ROOM_FILE_MAP.items():
        path = os.path.join(SPISKI_DIR, filename)
        seen = set()
        rooms = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    room = line.strip()
                    if not room:
                        continue
                    room_key = room.casefold()
                    if room_key in seen:
                        continue
                    seen.add(room_key)
                    rooms.append(room)
        except FileNotFoundError:
            logging.warning("Configured rooms file not found: %s", path)
        except Exception as exc:
            logging.warning("Failed to read configured rooms from %s: %s", path, exc)
        configured[building] = sorted(rooms, key=_spiski_sort_key)
    return configured


def _sort_building_names(building_names) -> list[str]:
    order_index = {name: index for index, name in enumerate(BUILDING_ORDER)}
    return sorted(
        building_names,
        key=lambda name: (order_index.get(name, len(BUILDING_ORDER)), str(name).casefold()),
    )


def _parse_time(t: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", (t or "").strip())
    if not match:
        return -1
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return -1
    return hour * 60 + minute


def _format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _derive_free_windows(occupied: list[dict], day_start: int, day_end: int) -> list[dict]:
    if not occupied:
        return [{"start": _format_time(day_start), "end": _format_time(day_end)}]
    merged = []
    for slot in sorted(occupied, key=lambda item: item.get("start", -1)):
        start = max(day_start, int(slot.get("start", -1)))
        end = min(day_end, int(slot.get("end", -1)))
        if start < 0 or end <= start:
            continue
        if merged and start <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], end)
        else:
            merged.append({"start": start, "end": end})
    if not merged:
        return [{"start": _format_time(day_start), "end": _format_time(day_end)}]
    free, cursor = [], day_start
    for slot in merged:
        if cursor < slot["start"]:
            free.append({"start": _format_time(cursor), "end": _format_time(slot["start"])})
        cursor = max(cursor, slot["end"])
    if cursor < day_end:
        free.append({"start": _format_time(cursor), "end": _format_time(day_end)})
    return [window for window in free if window["start"] != window["end"]]


def _parse_html_block(attrs_text: str, body: str) -> dict | None:
    attrs = dict(re.findall(r"data-([\w-]+)=['\"]([^'\"]*)['\"]", attrs_text))
    lesson_type = attrs.get("lesson-type", "group")
    if lesson_type != "group":
        return None
    lines = [
        line.strip()
        for line in re.sub(r"<br\s*/?>", "\n", body, flags=re.I).splitlines()
        for line in [re.sub(r"<[^>]+>", "", line)]
        if line.strip()
    ]
    lines = [unescape(line) for line in lines]
    time_index = -1
    time_match = None
    for index in range(len(lines) - 1, -1, -1):
        time_match = re.fullmatch(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", lines[index])
        if time_match:
            time_index = index
            break
    if time_index < 1:
        return None
    room = lines[time_index - 1].strip()
    return {
        "day": attrs.get("day", "").strip(),
        "building": attrs.get("building", "").strip(),
        "room": room,
        "start_time": time_match.group(1),
        "end_time": time_match.group(2),
        "subject": lines[0] if lines else "",
        "teacher": lines[1] if len(lines) > 1 else "",
        "students": lines[2] if len(lines) > 2 else "",
        "lesson_type": lesson_type,
    }


def _load_base_blocks() -> list[dict]:
    base_data = _load_json_safe(BASE_SCHEDULE_PATH)
    blocks = base_data.get("blocks", [])
    if base_data.get("published_at") is not None:
        return blocks if isinstance(blocks, list) else []
    if not os.path.exists(SCHEDULE_HTML_PATH):
        logging.warning("Fallback schedule HTML not found: %s", SCHEDULE_HTML_PATH)
        return []
    try:
        with open(SCHEDULE_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as exc:
        logging.warning("Failed to read fallback schedule HTML %s: %s", SCHEDULE_HTML_PATH, exc)
        return []
    found = []
    pattern = re.compile(
        r"<div(?P<attrs>[^>]*class=['\"][^'\"]*activity-block[^'\"]*['\"][^>]*)>(?P<body>.*?)</div>",
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        block = _parse_html_block(match.group("attrs"), match.group("body"))
        if block:
            found.append(block)
    if not found:
        logging.warning("No fallback base blocks parsed from %s", SCHEDULE_HTML_PATH)
    return found


def compute_availability() -> dict:
    base_blocks = _load_base_blocks()
    ind_data = state_manager.get_individual_lessons()
    ind_blocks = ind_data.get("blocks", []) if isinstance(ind_data.get("blocks"), list) else []
    combined = list(base_blocks) + list(ind_blocks)
    configured_rooms = _load_configured_rooms()
    buildings, spans = {}, []
    for building, rooms in configured_rooms.items():
        bucket = buildings.setdefault(building, {"rooms": set(), "days": {}})
        bucket["rooms"].update(rooms)
    for block in combined:
        if not isinstance(block, dict):
            continue
        building = str(block.get("building", "")).strip()
        day = str(block.get("day", "")).strip()
        room = str(block.get("room", "")).strip()
        start_text = str(block.get("start_time", "")).strip()
        end_text = str(block.get("end_time", "")).strip()
        if not all([building, day, room, start_text, end_text]):
            continue
        start_min, end_min = _parse_time(start_text), _parse_time(end_text)
        if start_min < 0 or end_min <= start_min:
            continue
        spans.append((start_min, end_min))
        bucket = buildings.setdefault(building, {"rooms": set(), "days": {}})
        bucket["rooms"].add(room)
        room_slots = bucket["days"].setdefault(day, {}).setdefault(room, [])
        room_slots.append(
            {
                "start": start_text,
                "end": end_text,
                "subject": str(block.get("subject", "")).strip(),
                "students": str(block.get("students", "")).strip(),
                "teacher": str(block.get("teacher", "")).strip(),
                "lesson_type": str(block.get("lesson_type", "")).strip(),
            }
        )
    if spans:
        grid_start = min(start for start, _ in spans)
        grid_end = max(end for _, end in spans)
        grid_start -= grid_start % 15
        grid_end += (15 - grid_end % 15) % 15
        grid_end = max(grid_end, 1200)
    else:
        grid_start, grid_end = 480, 1200
    sorted_buildings = {}
    sorted_building_names = _sort_building_names(buildings.keys())
    for building in sorted_building_names:
        day_map = {}
        for day in sorted(buildings[building]["days"], key=lambda value: (DAY_ORDER.get(value, 99), value)):
            room_map = {}
            for room, slots in buildings[building]["days"][day].items():
                room_map[room] = sorted(slots, key=lambda slot: _parse_time(slot["start"]))
            day_map[day] = room_map
        sorted_buildings[building] = {
            "rooms": sorted(buildings[building]["rooms"], key=_spiski_sort_key),
            "days": day_map,
        }
    return {
        "buildings": sorted_buildings,
        "building_order": sorted_building_names,
        "grid_start": _format_time(grid_start),
        "grid_end": _format_time(grid_end),
    }
