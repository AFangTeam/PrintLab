"""Shared non-printable parts ledger. CLI writes, Studio reads; never places orders."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlparse

from . import core

STORE = "Library/Shopping/list.json"


def load():
    path = core.safe_path(core.ROOT, STORE, require_file=False)
    return core.read_json(path, {"schema_version": 1, "version": 0, "projects": {}, "items": {}, "history": []})


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise core.WorkflowError(f"{label} must be non-empty text")
    return value.strip()


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def count(value, label, unknown=False):
    if unknown and value is None:
        return None
    if type(value) is not int or value < 0:
        raise core.WorkflowError(f"{label} must be a non-negative integer" + (" or null" if unknown else ""))
    return value


def project_id(ref):
    # Shared restocking requests do not imply a new printable object/project.
    if ref == "general":
        return "general"
    return core.read_json(core.project_path(ref) / "project.json")["id"]


def change(expected, action, callback):
    with core.lock("shop"):
        data = load()
        if type(expected) is not int or data["version"] != expected:
            raise core.WorkflowError("Shop List changed; read shop list and merge against its current version")
        callback(data)
        data["version"] += 1
        data["updated_at"] = core.now()
        data["history"].append({"version": data["version"], "at": data["updated_at"], **action})
        core.write_json(core.safe_path(core.ROOT, STORE, require_file=False), data)
        return view(data=data)


def confirm(ref, quote, source, expected):
    pid = project_id(ref)
    decision = {"quote": text(quote, "User confirmation"), "source": text(source, "Conversation source"), "at": core.now()}
    def apply(data):
        project = data["projects"].setdefault(pid, {"requirements": [], "parts_reviewed": False})
        if not project.get("decision"):
            project["decision"] = decision
    return change(expected, {"action": "confirm_make", "project_id": pid, "decision": decision}, apply)


def requirement(pid, value):
    if not isinstance(value, dict):
        raise core.WorkflowError("Each requirement must be an object")
    rid = text(value.get("id"), "Stable requirement ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", rid):
        raise core.WorkflowError("Requirement ID must contain only letters, digits, _ or -")
    name = text(value.get("name"), "Part name")
    category = text(value.get("category"), "Part category")
    unit = text(value.get("unit"), "Unit")
    spec = value.get("specification", {})
    if not isinstance(spec, dict) or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip() for k, v in spec.items()):
        raise core.WorkflowError("Specification must map explicit dimension/property names to text with units")
    verified = value.get("spec_verified", False)
    if type(verified) is not bool or (verified and not spec):
        raise core.WorkflowError("Verified specification requires explicit properties")
    quantity = count(value.get("quantity"), "Quantity", unknown=True)
    if quantity == 0:
        raise core.WorkflowError("Remove unneeded requirements from the full sync instead of using zero")
    canonical = {norm(k): norm(v) for k, v in spec.items()}
    if len(canonical) != len(spec):
        raise core.WorkflowError("Duplicate specification properties")
    identity = [norm(category), norm(unit), canonical] if verified else [pid, rid, canonical, norm(category), norm(unit)]
    key = "S" + hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    req = {"id": rid, "item_id": key, "quantity": quantity, "note": str(value.get("note", ""))}
    item = {"id": key, "name": name, "category": category, "unit": unit, "specification": spec,
            "spec_verified": verified, "existing": None, "purchased": 0,
            "supplier": {"status": "unverified", "url": None}}
    return req, item


def sync(ref, requirements, expected, source):
    pid = project_id(ref)
    source = text(source, "Requirement source")
    if not isinstance(requirements, list):
        raise core.WorkflowError("Supply the complete current requirements array")
    prepared = [requirement(pid, r) for r in requirements]
    if len({r["id"] for r, _ in prepared}) != len(prepared):
        raise core.WorkflowError("Requirement IDs must be unique within the project")
    def apply(data):
        project = data["projects"].get(pid)
        if not project or not project.get("decision"):
            raise core.WorkflowError("Record the user's explicit decision to make this project before syncing parts")
        if project.get("fulfilled_at"):
            raise core.WorkflowError("This project's parts were consumed; create a new project for a new batch")
        for _, item in prepared:
            data["items"].setdefault(item["id"], item)
        project.update(requirements=[r for r, _ in prepared], parts_reviewed=True, updated_at=core.now(), source=source)
    return change(expected, {"action": "sync", "project_id": pid, "requirements": requirements, "source": source}, apply)


def stock(item_id, existing, purchased, note, expected):
    existing = count(existing, "Existing quantity", unknown=True)
    purchased = count(purchased, "Purchased quantity")
    note = text(note, "Stock evidence")
    def apply(data):
        if item_id not in data["items"]:
            raise core.WorkflowError("Unknown Shop item")
        item = data["items"][item_id]
        if not item["spec_verified"]:
            raise core.WorkflowError("Verify the exact specification before recording matching stock")
        item.update(existing=existing, purchased=purchased, stock_note=note, stock_updated_at=core.now())
    return change(expected, {"action": "stock", "item_id": item_id, "existing": existing, "purchased": purchased, "note": note}, apply)


def supplier(item_id, status, url, evidence, expected):
    if status not in {"available", "unavailable", "unverified"}:
        raise core.WorkflowError("Invalid Maker's Supply availability")
    evidence = text(evidence, "Supplier verification evidence")
    if status == "available":
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise core.WorkflowError("Verified availability needs a direct HTTPS product URL")
        # A general storefront/search/category URL is not evidence of a matching SKU.
        jd = parsed.hostname == "item.jd.com" and re.fullmatch(r"/\d+\.html", parsed.path)
        bambu = (parsed.hostname == "bambulab.com" or parsed.hostname.endswith(".bambulab.com")) and "/products/" in parsed.path
        if not (jd or bambu):
            raise core.WorkflowError("Use a verified specific JD item or official Bambu product page, not a storefront")
    elif url:
        raise core.WorkflowError("Only verified available items may show a purchase link")
    def apply(data):
        item = data["items"].get(item_id)
        if not item:
            raise core.WorkflowError("Unknown Shop item")
        if status == "available" and not item["spec_verified"]:
            raise core.WorkflowError("Verify specification before linking a matching product")
        item["supplier"] = {"status": status, "url": url or None, "evidence": evidence, "checked_at": core.now()}
    return change(expected, {"action": "supplier", "item_id": item_id, "status": status, "url": url, "evidence": evidence}, apply)


def fulfill(ref, note, expected):
    """Explicit physical use consumes stock once, so completed projects cannot reuse it."""
    pid = project_id(ref)
    note = text(note, "Physical receipt/use evidence")
    def apply(data):
        project = data["projects"].get(pid)
        if not project or not project.get("parts_reviewed"):
            raise core.WorkflowError("Review project parts first")
        if project.get("fulfilled_at"):
            raise core.WorkflowError("Parts already consumed; not deducting twice")
        totals = {}
        for req in project["requirements"]:
            item = data["items"][req["item_id"]]
            if req["quantity"] is None or not item["spec_verified"] or item["existing"] is None:
                raise core.WorkflowError("Resolve quantities, specifications and stock before consumption")
            totals[item["id"]] = totals.get(item["id"], 0) + req["quantity"]
        for key, quantity in totals.items():
            item = data["items"][key]
            if item["existing"] + item["purchased"] < quantity:
                raise core.WorkflowError("Not enough recorded stock")
            used = min(item["existing"], quantity)
            item["existing"] -= used
            item["purchased"] -= quantity - used
        project.update(fulfilled_at=core.now(), fulfillment_note=note)
    return change(expected, {"action": "fulfill", "project_id": pid, "note": note}, apply)


def view(ref=None, data=None):
    data = data if data is not None else load()
    pid = project_id(ref) if ref else None
    projects, groups = {}, {}
    for key, project in data["projects"].items():
        try:
            name = "通用采购" if key == "general" else core.read_json(core.project_path(key) / "project.json")["name"]
        except core.WorkflowError:
            name = key + "（项目文件待恢复）"
        projects[key] = {**project, "id": key, "name": name}
        for req in project["requirements"]:
            item = data["items"][req["item_id"]]
            row = groups.setdefault(item["id"], {**item, "sources": [], "required": 0, "unknown_quantities": 0})
            active = not project.get("fulfilled_at")
            row["sources"].append({"project_id": key, "project_name": name, "requirement_id": req["id"], "quantity": req["quantity"], "active": active, "note": req["note"]})
            if active:
                if req["quantity"] is None:
                    row["unknown_quantities"] += 1
                else:
                    row["required"] += req["quantity"]
    # Keep unallocated/leftover inventory visible after a requirement was removed.
    for key, item in data["items"].items():
        if key not in groups and ((item["existing"] or 0) + item["purchased"] > 0):
            groups[key] = {**item, "sources": [], "required": 0, "unknown_quantities": 0}
    rows = []
    for row in groups.values():
        active = any(s["active"] for s in row["sources"])
        uncertain = row["unknown_quantities"] > 0 or not row["spec_verified"] or row["existing"] is None
        row["to_buy"] = None if active and uncertain else max(0, row["required"] - (row["existing"] or 0) - row["purchased"])
        row["status"] = "settled" if not active else "unverified" if uncertain else "needed" if row["to_buy"] else "owned" if row["existing"] >= row["required"] else "purchased"
        if not pid or any(s["project_id"] == pid for s in row["sources"]):
            rows.append(row)
    return {"version": data["version"], "updated_at": data.get("updated_at"), "items": rows,
            "projects": {k: v for k, v in projects.items() if not pid or k == pid}, "project_id": pid,
            "counts": {status: sum(r["status"] == status for r in rows) for status in ["unverified", "needed", "owned", "purchased", "settled"]}}


def project_summary(pid):
    project = load()["projects"].get(pid)
    return {"confirmed": bool(project and project.get("decision")),
            "parts_reviewed": bool(project and project.get("parts_reviewed")),
            "count": len(project["requirements"]) if project else 0,
            "fulfilled": bool(project and project.get("fulfilled_at"))}
