"""Synthetic target/view provenance. No visual acceptance or printer calls are made."""
import copy
from pathlib import Path
import pytest
from printlab import core, design, image3d, project3mf, cli


@pytest.fixture
def locked(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ROOT", tmp_path)
    core.new_project("Synthetic target")
    p = core.project_path("P001")
    def asset(name):
        f = p / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(("synthetic " + name).encode())
        return {"path": name, "sha256": core.digest(f)}
    primary = asset("Preview/concept.png")
    old = asset("Sources/inspiration.png")
    d = {"schema_version": 2, "appearance_primary": primary,
         "selection": {"status": "confirmed", "quote": "Synthetic confirmation, not real user permission", "source": "offline test"},
         "features": [{"id": name, "requirement": name} for name in ["silhouette", "palm", "ribs"]],
         "inspiration": [old], "concept_views": {}, "unresolved_conflicts": [],
         "view_consistency_review": {"status": "accepted", "primary_sha256": primary["sha256"], "reviewer": "synthetic test", "findings": ["test provenance only"]}}
    for name in design.VIEWS:
        d["concept_views"][name] = {**asset(f"Preview/{name}.png"), "primary_sha256": primary["sha256"], "review_status": "accepted"}
    core.write_json(p / design.CONTRACT, d)
    return p, d, asset


def test_confirmed_concept_is_input_and_inspiration_is_not(locked):
    _, d, _ = locked
    assert design.check("P001", "input", reference=d["appearance_primary"]["path"])["status"] == "passed"
    assert design.check("P001", "input", reference=d["inspiration"][0]["path"])["status"] == "blocked"


def test_accepted_derivative_must_be_bound_to_master(locked):
    p, d, asset = locked
    derived = asset("Preview/derived.png")
    d["modeling_inputs"] = [{**derived, "primary_sha256": "wrong", "review_status": "accepted", "reviewer": "test", "notes": "test"}]
    core.write_json(p / design.CONTRACT, d)
    assert design.check("P001", "input", reference=derived["path"])["status"] == "blocked"
    d["modeling_inputs"][0]["primary_sha256"] = d["appearance_primary"]["sha256"]
    core.write_json(p / design.CONTRACT, d)
    assert design.check("P001", "input", reference=derived["path"])["status"] == "passed"


@pytest.mark.parametrize("change", ["replace_primary", "unconfirmed", "missing_view", "pending_review", "conflict", "relabel_same_image"])
def test_missing_stale_or_inconsistent_views_are_blocked(locked, change):
    p, d, _ = locked
    if change == "replace_primary":
        (p / d["appearance_primary"]["path"]).write_bytes(b"different concept")
    elif change == "unconfirmed":
        d["selection"]["status"] = "pending"
    elif change == "missing_view":
        del d["concept_views"]["bottom"]
    elif change == "pending_review":
        d["view_consistency_review"]["status"] = "pending"
    elif change == "conflict":
        d["unresolved_conflicts"] = ["view count is not visual consistency"]
    else:
        d["concept_views"]["right"] = copy.deepcopy(d["concept_views"]["front"])
    core.write_json(p / design.CONTRACT, d)
    assert design.check("P001", "views")["status"] == "blocked"


def make_release(locked):
    p, d, asset = locked
    model = asset("Exports/v003/model.stl")
    review = {"target_contract_sha256": core.digest(p / design.CONTRACT), "primary_sha256": d["appearance_primary"]["sha256"],
              "model": model, "reviewer": "synthetic review only", "appearance": "accepted", "findings": ["test"],
              "features": {f["id"]: {"result": "pass", "evidence": ["synthetic evidence"]} for f in d["features"]},
              "renders": {name: {**asset(f"Preview/v003/{name}.png"), "model_sha256": model["sha256"]} for name in design.VIEWS}}
    core.write_json(p / "Review/design-gates/v003.json", review)
    return p, d, review


def test_review_pass_is_not_print_permission(locked):
    make_release(locked)
    result = design.check("P001", "release", "v003")
    assert result["status"] == "passed"
    assert result["print_authorized"] is False


@pytest.mark.parametrize("change", ["model", "target_contract", "render", "stale_render_binding", "feature"])
def test_release_cannot_use_old_target_mesh_or_preview(locked, change):
    p, d, review = make_release(locked)
    if change == "model":
        (p / review["model"]["path"]).write_bytes(b"new geometry")
    elif change == "target_contract":
        d["features"][0]["requirement"] = "new requirement"
        core.write_json(p / design.CONTRACT, d)
    elif change == "render":
        (p / review["renders"]["right"]["path"]).write_bytes(b"new render")
    elif change == "stale_render_binding":
        review["renders"]["right"]["model_sha256"] = "different model"
    else:
        review["features"]["palm"]["result"] = "unknown"
    core.write_json(p / "Review/design-gates/v003.json", review)
    assert design.check("P001", "release", "v003")["status"] == "blocked"


def test_wrong_image_rejected_before_inference(locked):
    _, d, _ = locked
    with pytest.raises(core.WorkflowError, match="inspiration cannot replace"):
        image3d.generate("P001", d["inspiration"][0]["path"], "new", None, 60, 30, 256, 42, 8)


def test_changed_protected_mechanical_source_blocks_check(locked):
    p, d, asset = locked
    mechanical = asset("Sources/interface.3mf")
    d["mechanical_sources"] = [mechanical]
    core.write_json(p / design.CONTRACT, d)
    assert design.check("P001", "views")["status"] == "passed"
    (p / mechanical["path"]).write_bytes(b"interface changed")
    assert design.check("P001", "views")["status"] == "blocked"


def test_release_gate_runs_before_formal_export_or_slicing(locked):
    with pytest.raises(core.WorkflowError, match="Design target check blocked"):
        project3mf.export("P001", "v003", "none", "none", ["none"], "Textured PEI Plate")
    with pytest.raises(core.WorkflowError, match="Design target check blocked"):
        core.slice_project("P001", "none", "none", ["none"], "v003")


def test_cli_returns_nonzero_when_views_need_revision(locked, capsys):
    p, d, _ = locked
    d["view_consistency_review"]["status"] = "needs_revision"
    core.write_json(p / design.CONTRACT, d)
    assert cli.main(["design-check", "P001"]) == 2


def test_unconfigured_legacy_project_is_not_retroactively_blocked(locked):
    p, _, _ = locked
    (p / design.CONTRACT).unlink()
    design.require_if_configured("P001", "release", "v001")
    assert design.check("P001")["status"] == "not_configured"


def three_view_contract(locked):
    p, d, _ = locked
    d.update(schema_version=3, required_concept_views=["front", "right", "top"], required_model_views=["front", "right", "top"])
    d["three_view_sets"] = {str(i): {"primary_sha256": d["appearance_primary"]["sha256"], "views": {name: copy.deepcopy(d["concept_views"][name]) for name in d["required_concept_views"]}} for i in range(1, 5)}
    d["view_set_selection"] = {"status": "confirmed", "set_id": "3", "quote": "Synthetic choice 3", "source": "offline test"}
    core.write_json(p / design.CONTRACT, d)
    return p, d


def test_v3_accepts_three_views_after_two_user_choices(locked):
    three_view_contract(locked)
    assert design.check("P001", "views")["status"] == "passed"


@pytest.mark.parametrize("change", ["unselected", "only_three_sets", "wrong_primary", "missing_selected_view"])
def test_v3_cannot_skip_whole_set_selection_or_mix_old_views(locked, change):
    p, d = three_view_contract(locked)
    if change == "unselected":d["view_set_selection"]["status"] = "pending"
    elif change == "only_three_sets":del d["three_view_sets"]["4"]
    elif change == "wrong_primary":d["three_view_sets"]["3"]["primary_sha256"] = "another shape"
    else:del d["three_view_sets"]["3"]["views"]["right"]
    core.write_json(p / design.CONTRACT, d)
    assert design.check("P001", "views")["status"] == "blocked"


def test_formal_build_cannot_skip_user_three_view_choice(locked):
    p, d = three_view_contract(locked)
    d["view_set_selection"]["status"] = "pending"
    core.write_json(p / design.CONTRACT, d)
    with pytest.raises(core.WorkflowError, match="User has not selected"):
        core.build("P001", "v003", "blender")
