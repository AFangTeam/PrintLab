"""Isolated MLX image-to-shape worker. Never slices or operates a printer."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Runtime/vendor/hunyuan3d-swift"
WEIGHTS = ROOT / "Runtime/models/hunyuan3d-shape-small"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare(reference, crop, out):
    im = Image.open(reference).convert("RGBA")
    if crop:
        l, t, r, b = crop
        if not (0 <= l < r <= im.width and 0 <= t < b <= im.height):
            raise ValueError("Crop must be left,top,right,bottom within the original image")
        im = im.crop(crop)
    rgba = np.array(im)
    if np.all(rgba[:, :, 3] == 255):
        # White-background conditioning only; preserve original RGB pixels.
        rgb = rgba[:, :, :3]
        low = rgb.min(axis=2)
        border = np.concatenate([low[0], low[-1], low[:, 0], low[:, -1]])
        if (border > 235).mean() < 0.65:
            raise ValueError("Conditioning supports white-background or transparent single-object images; remove complex background first")
        mask = np.full(low.shape, cv2.GC_PR_FGD, dtype=np.uint8)
        mask[low > 248] = cv2.GC_BGD
        mask[low < 205] = cv2.GC_FGD
        mask[[0, -1], :] = cv2.GC_BGD
        mask[:, [0, -1]] = cv2.GC_BGD
        cv2.setRNGSeed(0)
        cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, None,
                    np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64),
                    5, cv2.GC_INIT_WITH_MASK)
        alpha = np.isin(mask, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
        if n < 2:
            raise ValueError("No foreground found; supply a transparent single-object image")
        keep = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        rgba[:, :, 3] = (labels == keep).astype(np.uint8) * 255
    Image.fromarray(rgba).save(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--crop", nargs=4, type=int)
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--resolution", type=int, choices=[128, 256, 384], default=256)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--quantize", type=int, choices=[4, 8], default=8)
    p.add_argument("--height-mm", type=float, required=True)
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    if not (1 <= a.steps <= 60 and 0 < a.height_mm <= 1000):
        p.error("Steps must be 1..60 and chosen height 0..1000 mm")
    a.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, a.output / "worker.snapshot.py")
    input_path = a.output / "conditioning.png"
    prepare(a.reference, a.crop, input_path)
    manifest = {
        "schema": "printlab.image3d-candidate.v1", "status": "conditioning_ready",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reference": {"path": str(a.reference.resolve()), "sha256": digest(a.reference)},
        "conditioning": {"path": input_path.name, "sha256": digest(input_path),
                         "crop_ltrb": a.crop, "method": "original RGB + alpha/white-background GrabCut largest component"},
        "model_source": json.loads((WEIGHTS / "printlab-model-source.json").read_text()),
        "code_source": json.loads((SOURCE / "printlab-source.json").read_text()),
        "worker_sha256": digest(__file__),
        "parameters": {"steps": a.steps, "resolution": a.resolution, "seed": a.seed,
                       "quantize_bits": a.quantize, "dtype": "float16", "octree_decode": True,
                       "height_mm": a.height_mm, "height_source": "explicit chosen scale, not inferred dimensions"},
        "functional_scope": "untested", "appearance_review": "pending",
        "print_ready": False, "print_authorized": False,
        "limitations": ["Hidden surfaces are inferred", "Assembly parts in the reference may be fused",
                       "Magnet, cable, clips, holes and tolerances are not functional CAD"],
    }
    mp = a.output / "manifest.json"
    def save():
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    save()
    if a.prepare_only:
        return
    t0 = time.monotonic()
    try:
        if digest(WEIGHTS / "model.fp16.safetensors") != "3cc66f3bea33e4062b7dbc875ffe1d70c4888914aec3e91b60f94e9bd01b522b":
            raise ValueError("Model weight checksum mismatch")
        sys.path.insert(0, str(SOURCE / "python/shape"))
        import mlx.core as mx
        from hy3dmlx.pipeline import Hunyuan3DShapePipeline
        manifest["status"] = "generating"
        save()
        pipeline = Hunyuan3DShapePipeline.from_pretrained(str(WEIGHTS), dtype=mx.float16, quantize=a.quantize)
        mesh = pipeline.generate(str(input_path), num_inference_steps=a.steps,
                                 octree_resolution=a.resolution, seed=a.seed,
                                 octree_decode=True, num_chunks=8192)
        mesh.export(a.output / "raw-normalized.glb")
        # Hunyuan is Y-up. Convert to PrintLab Z-up in millimetres.
        transform = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
        mesh.apply_transform(transform)
        mesh.apply_scale(a.height_mm / mesh.extents[2])
        mesh.apply_translation([-mesh.bounds.mean(axis=0)[0], -mesh.bounds.mean(axis=0)[1], -mesh.bounds[0, 2]])
        mesh.metadata["units"] = "mm"
        mesh.export(a.output / "shape-mm.ply")
        mesh.export(a.output / "shape-mm.stl")
        mesh.export(a.output / "candidate-geometry-only.3mf")
        import trimesh
        reloaded = trimesh.load(a.output / "candidate-geometry-only.3mf", force="mesh")
        if not np.allclose(mesh.extents, reloaded.extents, atol=0.001, rtol=0):
            raise ValueError("3MF millimetre round-trip mismatch")
        parts = mesh.split(only_watertight=False)
        manifest.update(status="generated_unreviewed", elapsed_seconds=round(time.monotonic() - t0, 2),
                        peak_mlx_gb=round(mx.get_peak_memory() / 1e9, 3),
                        geometry={"vertices": len(mesh.vertices), "faces": len(mesh.faces),
                                  "finite": bool(np.isfinite(mesh.vertices).all()),
                                  "watertight": bool(mesh.is_watertight), "components": len(parts),
                                  "geometry_3mf_mm_roundtrip": True,
                                  "bounds_mm": mesh.bounds.tolist(), "extents_mm": mesh.extents.tolist()},
                        artifacts={f.name: digest(f) for f in a.output.iterdir() if f.suffix in {".ply", ".stl", ".glb", ".3mf"}})
        save()
        print(json.dumps({"status": manifest["status"], "manifest": str(mp), "elapsed_seconds": manifest["elapsed_seconds"], "geometry": manifest["geometry"]}), flush=True)
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}", elapsed_seconds=round(time.monotonic() - t0, 2))
        save()
        raise


if __name__ == "__main__":
    main()
