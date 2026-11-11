"""Candidate-only image-to-shape bridge; isolated from print and approval code."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from . import core


def toolchain():
    return {
        "python": core.ROOT / "Runtime/image3d/venv/bin/python",
        "worker": core.ROOT / "Harness/image3d_worker.py",
        "source": core.ROOT / "Runtime/vendor/hunyuan3d-swift/printlab-source.json",
        "weights": core.ROOT / "Runtime/models/hunyuan3d-shape-small/model.fp16.safetensors",
    }


def doctor(verify_weights=False):
    paths = toolchain()
    checks = {key: {"path": str(value), "exists": value.is_file()} for key, value in paths.items()}
    result = {"status": "available" if all(v["exists"] for v in checks.values()) else "incomplete",
              "checks": checks, "capability": "appearance mesh candidate only", "print_authorized": False}
    if checks["python"]["exists"]:
        p = subprocess.run([str(paths["python"]), "-c",
                            "import json,mlx.core as mx; print(json.dumps({'gpu_available':mx.metal.is_available(),'device':str(mx.default_device())}))"],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            result.update(status="unavailable", runtime_error=p.stderr[-1200:])
        else:
            result["runtime"] = json.loads(p.stdout)
            if not result["runtime"]["gpu_available"]:
                result["status"] = "unavailable"
    if verify_weights and checks["weights"]["exists"]:
        actual = core.digest(paths["weights"])
        expected = "3cc66f3bea33e4062b7dbc875ffe1d70c4888914aec3e91b60f94e9bd01b522b"
        result["weight_sha256"] = actual
        result["weights_verified"] = actual == expected
        if actual != expected:
            result["status"] = "unavailable"
    return result


def generate(project, reference, candidate, crop, height_mm, steps, resolution, seed, quantize):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", candidate):
        raise core.WorkflowError("Candidate must use lowercase letters, digits, _ or - (max 80 characters)")
    pp = core.project_path(project)
    ref = core.safe_path(pp, reference)
    from . import design
    design.require_if_configured(project, "input", reference=reference)
    target = core.read_json(pp / design.CONTRACT, {}).get("appearance_primary", {})
    if reference == target.get("path") and target.get("layout") == "multiple_views" and not crop:
        raise core.WorkflowError("The selected concept contains multiple views; crop one object before single-image generation")
    if ref.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise core.WorkflowError("Use a single-object PNG/JPEG/WebP reference")
    output = core.safe_path(pp, "Design/Candidates/" + candidate, require_file=False)
    paths = toolchain()
    if not all(p.is_file() for p in paths.values()):
        raise core.WorkflowError("Image3D environment incomplete; run image3d doctor")
    command = [str(paths["python"]), "-u", str(paths["worker"]), "--reference", str(ref),
               "--output", str(output), "--height-mm", str(height_mm), "--steps", str(steps),
               "--resolution", str(resolution), "--seed", str(seed), "--quantize", str(quantize)]
    if crop:
        command += ["--crop", *map(str, crop)]
    # One ML inference at a time. Preserve diagnostics and clean JSON stdout.
    try:
        with core.lock("image3d"):
            if output.exists():
                raise core.WorkflowError("Candidate already exists; use a new ID, existing evidence is immutable")
            run = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        if output.is_dir():
            def decoded(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
            (output / "inference.log").write_text(decoded(exc.stdout) + decoded(exc.stderr))
            m = core.read_json(output / "manifest.json", {})
            m.update(status="generation_timed_out", error="Worker exceeded 900 seconds")
            core.write_json(output / "manifest.json", m)
        raise core.WorkflowError("Image3D generation timed out; this candidate remains incomplete, inspect before a new attempt") from exc
    if output.is_dir():
        (output / "inference.log").write_text(run.stdout + run.stderr)
    if run.returncode:
        raise core.WorkflowError(f"Image3D worker failed ({run.returncode}); inspect candidate manifest, never retry into the same directory")
    blender = core.config().get("blender_path")
    if not blender or not Path(blender).is_file():
        raise core.WorkflowError("Shape generated but Blender unavailable for actual geometry previews")
    try:
        with (output / "render.log").open("w") as log:
            render = subprocess.run([blender, "--background", "--factory-startup", "--python-exit-code", "1",
                                     "--python", str(core.ROOT / "Harness/image3d_render.py"), "--", str(output)],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=240)
    except subprocess.TimeoutExpired as exc:
        m = core.read_json(output / "manifest.json", {})
        m.update(status="render_timed_out", error="Blender exceeded 240 seconds")
        core.write_json(output / "manifest.json", m)
        raise core.WorkflowError("Shape generated but render timed out; candidate remains unreviewed") from exc
    if render.returncode:
        m = core.read_json(output / "manifest.json", {})
        m.update(status="render_failed", error="Blender returned nonzero; see render.log")
        core.write_json(output / "manifest.json", m)
        raise core.WorkflowError("Shape generated but actual model render failed; see render.log")
    comparison(output)
    return inspect(project, candidate)


def comparison(folder):
    """Evidence contact sheet: original conditioning pixels beside actual mesh renders."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    canvas = Image.new("RGB", (1500, 950), "#f5f5f3")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except OSError:
        font = small = ImageFont.load_default()
    inputs = {}
    for i, (title, filename) in enumerate((("Selected concept", "conditioning.png"),
                                         ("Actual mesh - front", "gray-front.png"),
                                         ("Actual mesh - side", "gray-right.png"))):
        draw.text((i * 500 + 18, 22), title, font=font, fill="#222222")
        original = Image.open(folder / filename).convert("RGBA")
        bounds = original.getchannel("A").getbbox()
        if bounds:
            original = original.crop(bounds)
        white = Image.new("RGBA", original.size, "white")
        white.alpha_composite(original)
        picture = ImageOps.contain(white.convert("RGB"), (470, 810))
        canvas.paste(picture, (i * 500 + 15 + (470 - picture.width)//2, 65 + (810 - picture.height)//2))
        inputs[filename] = core.digest(folder / filename)
    draw.text((18, 905), "Local image-to-shape | Approximate camera match | NOT functional CAD / NOT print-ready", font=small, fill="#444444")
    canvas.save(folder / "comparison.jpg", quality=94)
    core.write_json(folder / "comparison-record.json", {"inputs": inputs, "sha256": core.digest(folder / "comparison.jpg")})


def inspect(project, candidate):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", candidate):
        raise core.WorkflowError("Invalid candidate ID")
    pp = core.project_path(project)
    folder = core.safe_path(pp, "Design/Candidates/" + candidate, require_file=False)
    manifest = core.read_json(folder / "manifest.json")
    if not manifest:
        raise core.WorkflowError("Candidate manifest not found")
    if not isinstance(manifest.get("reference"), dict) or not isinstance(manifest.get("conditioning"), dict):
        return {"integrity": "failed", "issues": ["Incomplete generation manifest"],
                "candidate": str(folder), "appearance": "not assessed by integrity check",
                "functional_scope": "untested", "print_ready": False, "print_authorized": False}
    issues = []
    def verify(base, path, expected):
        try:
            f = core.safe_path(base, path)
            if not expected or core.digest(f) != expected:
                issues.append(f"Changed artifact: {path}")
        except (OSError, core.WorkflowError):
            issues.append(f"Missing or unsafe artifact: {path}")
    reference = manifest["reference"]
    try:
        relative = str(Path(reference["path"]).relative_to(pp))
        verify(pp, relative, reference["sha256"])
    except ValueError:
        issues.append("Reference is outside the current project")
    verify(folder, manifest["conditioning"]["path"], manifest["conditioning"]["sha256"])
    if manifest.get("worker_sha256"):
        verify(folder, "worker.snapshot.py", manifest["worker_sha256"])
    for artifact in ("raw-normalized.glb", "shape-mm.ply", "shape-mm.stl", "candidate-geometry-only.3mf"):
        verify(folder, artifact, manifest.get("artifacts", {}).get(artifact))
    renders = core.read_json(folder / "render-record.json", {})
    if renders.get("mesh_sha256") != manifest.get("artifacts", {}).get("shape-mm.ply"):
        issues.append("Rendered mesh is not bound to this candidate")
    if renders.get("render_script_sha256"):
        verify(folder, "render.snapshot.py", renders["render_script_sha256"])
    if renders.get("blend_sha256"):
        verify(folder, "candidate.blend", renders["blend_sha256"])
    for view in ("front", "right", "back", "quarter", "top"):
        verify(folder, f"gray-{view}.png", renders.get("views", {}).get(view, {}).get("sha256"))
    if renders.get("view_schema") == "eight-view-v2":
        for view in ("left", "bottom", "back_quarter"):
            verify(folder, f"gray-{view}.png", renders.get("views", {}).get(view, {}).get("sha256"))
    contact = core.read_json(folder / "comparison-record.json")
    if contact:
        for filename, expected in contact.get("inputs", {}).items():
            verify(folder, filename, expected)
        verify(folder, "comparison.jpg", contact.get("sha256"))
    if manifest.get("status") != "generated_unreviewed":
        issues.append("Generation did not complete")
    return {"integrity": "passed" if not issues else "failed", "issues": issues,
            "candidate": str(folder), "manifest": str(folder / "manifest.json"),
            "comparison": str(folder / "comparison.jpg") if contact else None,
            "appearance": "not assessed by integrity check",
            "design_review": str(folder / "design-review.json") if (folder / "design-review.json").is_file() else None,
            "functional_scope": "untested",
            "geometry": manifest.get("geometry"), "print_ready": False, "print_authorized": False}
