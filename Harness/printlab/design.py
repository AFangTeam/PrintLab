"""Bind appearance intent and view evidence. Does not judge visual truth or authorize printing."""
from __future__ import annotations

from pathlib import Path
import re

from . import core

CONTRACT = "Review/design-target.json"
VIEWS = ("front", "back", "left", "right", "top", "bottom", "front_quarter", "back_quarter")


def check(pid, stage="views", revision=None, reference=None):
    pp = core.project_path(pid)
    path = pp / CONTRACT
    if not path.exists():
        return {"status": "not_configured", "issues": ["No locked design target"], "print_authorized": False}
    d = core.read_json(core.safe_path(pp, CONTRACT))
    issues = []
    def asset(a, label):
        try:
            if not isinstance(a, dict):
                raise ValueError("Missing asset record")
            f = core.safe_path(pp, a.get("path", ""))
            if not a.get("sha256") or core.digest(f) != a["sha256"]:
                raise ValueError("Missing or changed checksum")
            return f
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"{label}: {exc}")
            return None
    primary = d.get("appearance_primary", {})
    primary_path = asset(primary, "appearance_primary")
    primary_hash = primary.get("sha256")
    for mechanical in d.get("mechanical_sources", []):
        asset(mechanical, "mechanical_source")
    selection = d.get("selection", {})
    if selection.get("status") != "confirmed" or not selection.get("quote") or not selection.get("source"):
        issues.append("Exact appearance target has not been explicitly selected")
    features = d.get("features", [])
    if len(features) < 3 or any(not isinstance(f, dict) or not f.get("id") or not f.get("requirement") for f in features):
        issues.append("At least three concrete appearance requirements are required")
    if len({f.get('id') for f in features if isinstance(f, dict)}) != len(features):
        issues.append("Appearance requirement IDs must be unique")
    if stage == "input":
        if not reference:
            issues.append("A modeling reference is required")
        else:
            ref = core.safe_path(pp, reference)
            if primary_path is None or ref != primary_path:
                # Only an explicitly reviewed, primary-bound derivative may replace the anchor as input.
                allowed = False
                for derived in d.get("modeling_inputs", []):
                    if derived.get("path") == reference and derived.get("primary_sha256") == primary_hash and derived.get("review_status") == "accepted":
                        f = asset(derived, "modeling_input")
                        allowed = f == ref and bool(derived.get("reviewer")) and bool(derived.get("notes"))
                        if allowed:
                            break
                if not allowed:
                    issues.append("Modeling input is not the selected concept or an accepted derivative; inspiration cannot replace the target")
    if stage in {"views", "release"}:
        required = d.get("required_concept_views", list(VIEWS))
        if not isinstance(required, list) or len(required) < 3 or len(set(required)) != len(required) or any(v not in VIEWS for v in required):
            issues.append("At least three distinct supported view directions are required")
            required = list(VIEWS)
        vr = d.get("view_consistency_review", {})
        if vr.get("primary_sha256") != primary_hash or vr.get("status") != "accepted" or not vr.get("reviewer") or not vr.get("findings"):
            issues.append("Concept view consistency has not been accepted against the locked target")
        if d.get("unresolved_conflicts"):
            issues.append("Unresolved view/geometry conflicts remain")
        views = d.get("concept_views", {})
        if d.get("schema_version", 1) >= 3:
            sets = d.get("three_view_sets", {})
            chosen = d.get("view_set_selection", {})
            if len(sets) != 4:
                issues.append("Four three-view candidate sets must be offered before the final selection")
            if chosen.get("status") != "confirmed" or not chosen.get("quote") or not chosen.get("source") or chosen.get("set_id") not in sets:
                issues.append("User has not selected one complete three-view set")
            selected = sets.get(chosen.get("set_id"), {})
            if selected.get("primary_sha256") != primary_hash:
                issues.append("Selected three-view set belongs to a different appearance target")
            views = selected.get("views", {})
        identities = []
        for name in required:
            v = views.get(name, {})
            asset(v, f"concept_view.{name}")
            if v.get("primary_sha256") != primary_hash or v.get("review_status") != "accepted":
                issues.append(f"concept_view.{name}: not accepted or wrong target")
            identities.append((v.get("sha256"), str(v.get("crop_ltrb"))))
        if len(set(identities)) != len(required):
            issues.append("Different view labels reuse identical image regions")
    if stage == "release":
        if not revision or not re.fullmatch(r"v\d{3,}", revision):
            issues.append("Release requires a vNNN revision")
        else:
            review_path = pp / "Review/design-gates" / f"{revision}.json"
            review = core.read_json(review_path, {})
            if review.get("target_contract_sha256") != core.digest(path) or review.get("primary_sha256") != primary_hash:
                issues.append("Appearance review targets a different or changed design contract")
            model = review.get("model", {})
            asset(model, "release_model")
            if model.get("path") != f"Exports/{revision}/model.stl":
                issues.append("Release review must bind the actual revision model")
            if review.get("appearance") != "accepted" or not review.get("reviewer") or not review.get("findings"):
                issues.append("Actual model appearance has not been accepted")
            findings = review.get("features", {})
            for f in features:
                if not isinstance(f, dict):
                    continue
                if findings.get(f.get("id"), {}).get("result") != "pass" or not findings.get(f.get("id"), {}).get("evidence"):
                    issues.append(f"Appearance feature not passed with evidence: {f.get('id')}")
            model_views = d.get("required_model_views", required)
            if not isinstance(model_views, list) or len(model_views) < 3 or len(set(model_views)) != len(model_views) or any(v not in VIEWS for v in model_views):
                issues.append("Actual model must include at least three distinct supported view directions")
                model_views = required
            for name in model_views:
                r = review.get("renders", {}).get(name, {})
                asset(r, f"actual_render.{name}")
                if r.get("model_sha256") != model.get("sha256"):
                    issues.append(f"actual_render.{name}: not bound to reviewed model")
    return {"status": "passed" if not issues else "blocked", "stage": stage,
            "issues": issues, "target": primary, "contract": CONTRACT,
            "limits": "Checks file roles and review provenance; does not independently prove visual correspondence, fit, strength or printability",
            "print_authorized": False}


def require_if_configured(pid, stage, revision=None, reference=None):
    if not (core.project_path(pid) / CONTRACT).exists():
        return
    result = check(pid, stage, revision, reference)
    if result["status"] != "passed":
        raise core.WorkflowError("Design target check blocked: " + "; ".join(result["issues"][:8]))
