"""Read-only material presentation: telemetry, ledger estimates and history stay distinct.

No spool identity matching by approximate colour, no inventory writes, no totals.
Presence handling follows the pinned Bambuddy ams_slot_presence/getEmptySlotKind
contract: an explicit exists bit takes priority over firmware-specific state.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

PUBLIC_FIELDS = {
    "id", "name", "brand", "material", "subtype", "color_name", "rgba", "label_weight",
    "core_weight", "weight_used", "last_used", "last_scale_weight", "last_weighed_at",
    "data_origin", "archived_at", "storage_location", "material_number",
}


def number(value):
    return value if type(value) in {int, float} and math.isfinite(value) else None


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def english_label(item):
    brand = text(item.get("brand")) or "Brand not identified"
    material = text(item.get("material")) or text(item.get("tray_type")) or "Material not identified"
    subtype = text(item.get("subtype"))
    family = material if not subtype or subtype.lower() in material.lower() else f"{material} {subtype}"
    return f"{brand} {family} — {text(item.get('color_name')) or 'Color not identified'}"


def quantity(spool, baseline=None):
    """Keep ledger estimates available, never represent them as actual material left."""
    label, used = number(spool.get("label_weight")), number(spool.get("weight_used"))
    valid = label is not None and label > 0 and used is not None and used >= 0
    remaining = round(max(0, label - used), 2) if valid else None
    percent = round(remaining / label * 100, 2) if valid else None
    initial = next((s for s in (baseline or {}).get("initial_snapshot", [])
                    if s.get("spool_id") == spool.get("id")), None)
    historical = ({"remaining_percent": initial.get("remaining_percent", 100),
                   "at": (baseline or {}).get("confirmed_at"), "basis": "historical_user_confirmation"}
                  if initial else None)
    gross, core = number(spool.get("last_scale_weight")), number(spool.get("core_weight"))
    measured = ({"net_weight": round(gross - core, 2), "at": spool["last_weighed_at"],
                 "basis": "measured_snapshot"}
                if spool.get("last_weighed_at") and gross is not None and core is not None and gross >= core >= 0 else None)
    return {"remaining_weight": remaining, "remaining_percent": percent,
            "estimated_remaining_weight": remaining, "estimated_remaining_percent": percent,
            "quantity_basis": "inventory_estimate" if valid else "unknown", "measured": False,
            "actual_remaining_weight": None, "actual_remaining_percent": None,
            "quantity_note": "账面估算，实际余量未知；不人工扣减，不将历史满卷记录当当前满卷。",
            "historical_baseline": historical, "measurement": measured}


def inventory_items(rows, baseline=None):
    result = []
    for raw in rows:
        item = {k: raw[k] for k in PUBLIC_FIELDS if k in raw}
        item.update(quantity(raw, baseline))
        item["english_label"] = english_label(item)
        # Colour-unknown RFID and manually entered family records can be the same
        # physical spool. Keep records independent rather than silently adding them.
        candidates = []
        if raw.get("data_origin") == "rfid_auto":
            for other in rows:
                raw_rgba = (text(raw.get("rgba")) or "").lstrip("#").upper()
                other_rgba = (text(other.get("rgba")) or "").lstrip("#").upper()
                if raw_rgba and other_rgba and raw_rgba != other_rgba:
                    continue
                if (other.get("id") != raw.get("id") and other.get("data_origin") == "manual"
                    and (other.get("brand"), other.get("material"), other.get("subtype")) ==
                        (raw.get("brand"), raw.get("material"), raw.get("subtype"))
                    and (not raw.get("color_name") or raw.get("color_name") == other.get("color_name"))):
                    candidates.append(other.get("id"))
        item["possible_duplicate_ids"] = candidates
        item["identity_note"] = "RFID记录可能与同系列手工台账对应同卷；未核实、未合并，不合计可用克数。" if candidates else None
        result.append(item)
    return result


def _stamp(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return number(value)


def slot_state(tray):
    if not tray:
        return "unknown"
    exists, state = tray.get("exists"), tray.get("state")
    if exists is False:
        return "empty"
    if tray.get("reading") is True or tray.get("identifying") is True:
        return "identifying"
    typed = bool(text(tray.get("tray_type")))
    if exists is True:
        return "loaded" if typed else "unidentified"
    if state in {9, 10}:
        return "empty"
    if typed and state in {3, 11}:
        return "loaded"
    return "unknown"


def slot_overview(status, assignments=(), inventory_rows=(), observed_at=None, now=None, printer_model=None):
    """Normalize raw printer status. Returned IDs never include tags or serials."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    source_at = _stamp(status.get("last_ams_update"))
    age = now - source_at if source_at is not None else None
    fresh = status.get("connected") is True and age is not None and -5 <= age <= 60
    spool_by_id = {s.get("id"): s for s in inventory_rows}
    assigned = {(a.get("ams_id"), a.get("tray_id")): a.get("spool_id") for a in assignments
                if type(status.get("id")) is int and a.get("printer_id") == status["id"]}
    modules = []
    mapping = status.get("ams_extruder_map") or {}
    from .machine_profiles import single_nozzle_model
    single_nozzle = single_nozzle_model(printer_model)
    for index, ams in enumerate(status.get("ams") or []):
        aid = ams.get("id")
        trays = {t.get("id"): t for t in ams.get("tray", []) if type(t.get("id")) is int}
        # This workspace has a four-slot AMS. Do not invent four slots for a
        # future single-tray AMS-HT that explicitly says it is HT.
        count = 1 if ams.get("is_ams_ht") is True else 4
        extruder = mapping.get(str(aid), mapping.get(aid))
        extruder = extruder if type(extruder) is int and extruder in {0, 1} else None
        if single_nozzle and extruder is None:
            extruder = 0
        name = "AMS " + chr(ord("A") + aid) if type(aid) is int and 0 <= aid <= 25 else f"AMS {aid}"
        logical_nozzle = {1: 1, 0: 2}.get(extruder)
        nozzle_label = {1: "左主喷嘴 1", 0: "右辅喷嘴 2"}.get(extruder)
        if single_nozzle:
            logical_nozzle = 1 if extruder == 0 else None
            nozzle_label = '单喷嘴 1' if extruder == 0 else '路线冲突，待核实'
        slots = []
        for tid in range(count):
            tray = trays.get(tid, {})
            state = slot_state(tray)
            spool_id = assigned.get((aid, tid))
            spool = spool_by_id.get(spool_id, {})
            # An assignment is a hint, never proof a different live material is loaded.
            matched = bool(spool and tray.get("tray_type") and
                           str(spool.get("material", "")).upper() == str(tray["tray_type"]).upper())
            color = text(tray.get("tray_color"))
            spool_color = text(spool.get("rgba"))
            if matched and (not spool_color or not color or spool_color.lstrip("#").upper() != color.lstrip("#").upper()):
                matched = False
            live_family = text(tray.get("tray_sub_brands")) or text(tray.get("tray_type"))
            if matched:
                live_item = {**spool, "material": tray.get("tray_type"), "rgba": color}
                # A library subtype mismatch cannot add a colour/code to live telemetry.
                if live_family and spool.get("subtype") and spool["subtype"].lower() not in live_family.lower():
                    matched = False
            if not matched:
                live_item = {"brand": None, "material": live_family, "color_name": None, "rgba": color}
            remain = number(tray.get("remain"))
            remain = remain if remain is not None and 0 <= remain <= 100 and state == "loaded" else None
            slots.append({"slot_number": tid + 1, "state": state, "english_label": english_label(live_item) if state not in {"empty", "unknown"} else None,
                          "brand": live_item.get("brand"), "material": live_item.get("material"),
                          "subtype": live_item.get("subtype"), "color_name": live_item.get("color_name"), "rgba": color,
                          "material_number": text(spool.get("material_number")) if matched else None,
                          "spool_id": spool_id if matched else None, "assignment_matches": matched,
                          "reported_remaining_percent": remain, "remaining_basis": "device_report" if remain is not None else "unknown",
                          "actual_remaining_weight": None, "fresh": fresh, "source_timestamp": status.get("last_ams_update"),
                          "route": {"ams_label": name, "nozzle_number": logical_nozzle,
                                    "firmware_extruder_id": extruder,
                                    "text": f"{name} → {nozzle_label}" if nozzle_label else f"{name} → 喷嘴待核实"},
                          "diagnostics": {"ams_id": aid, "tray_id": tid, "physical_extruder_id": extruder,
                                          "reported_state": tray.get("state"), "assigned_spool_id": spool_id}})
        modules.append({"name": name, "slots": slots})
    return {"modules": modules, "observed_at": observed_at, "source_timestamp": status.get("last_ams_update"),
            "age_seconds": age, "fresh": fresh,
            "note": "槽位按1–4显示；单喷嘴可通过换料完成多色。余量是设备报告，可能滞后。" if single_nozzle else "槽位按1–4显示；余量是设备报告，可能滞后。多色不等于使用两个喷嘴。"}
