"""Studio server with same-origin, explicitly confirmed prepared-print controls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import asynccontextmanager, suppress
import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, bambuddy, core, shop, history
from .prepared_api import router as prepared_router

@asynccontextmanager
async def lifespan(app):
    from . import workbench
    workbench.recover_operations()
    async def observe():
        while True:
            try:
                await asyncio.to_thread(bambuddy.reconcile_active_jobs)
            except Exception:
                logging.getLogger("printlab").exception("Read-only reconciliation failed")
            await asyncio.sleep(30)
    task = asyncio.create_task(observe())
    async def sync_history():
        while True:
            try:
                await asyncio.to_thread(history.view)
            except Exception:
                logging.getLogger('printlab').exception('Read-only history sync failed')
            await asyncio.sleep(60)
    history_task = asyncio.create_task(sync_history())
    try:
        yield
    finally:
        task.cancel()
        history_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(asyncio.CancelledError):
            await history_task


app = FastAPI(title="PrintLab Studio", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)


@app.exception_handler(core.WorkflowError)
async def workflow_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    # Embedding in the local Bambuddy panel is intentional. Never allow scripts in user documents.
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/prepared") else "no-cache"
    if request.url.path.startswith("/api/prepared"):
        response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "read_only": False,
            "features": ["native-observation-v2", "material-slots-v2", "confirmation-card", "traceable-retry", "print-history-v1", "prepared-print-v1"]}


@app.get('/api/history')
def print_history():
    return history.view()


@app.get("/api/projects")
def projects():
    return {"projects": core.list_projects()}


@app.get("/api/projects/{pid}")
def project(pid: str):
    return core.detail(pid)


@app.get("/api/projects/{pid}/confirmation")
def confirmation_card(pid: str, job: str | None = None):
    from . import confirmation
    card = confirmation.card(pid, job)
    if card.get("job_id"):
        directory = core.job_path(pid, card["job_id"])
        card["validation_alerts"] = core.read_json(directory / "validation-alerts.json", [])
    return card


@app.get("/api/library")
def library():
    return core.library()


@app.get("/api/shop")
def shopping(project: str | None = None):
    return shop.view(project)


@app.get("/api/device")
def device():
    return bambuddy.device()


@app.get("/api/overview")
def overview():
    projects = core.list_projects()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(bambuddy.device), pool.submit(bambuddy.inventory)
        device, inventory = a.result(), b.result()
    counts = {s: sum(p.get("status") == s for p in projects) for s in ("designing", "awaiting_review", "printing", "completed")}
    counts["total"] = len(projects)
    counts["active"] = sum(p.get("status") in {"preparing", "running", "printing", "paused", "dispatching", "submitted"} for p in projects)
    actions = [{"title": p["name"], "detail": "模型待确认" if p["status"] == "awaiting_review" else "打印结束，等待实物检查", "project_id": p["id"]} for p in projects if p.get("status") in {"awaiting_review", "awaiting_physical_review"}]
    if device["state"] != "online" or device.get("stale"):
        actions.append({"title": "设备连接待核验", "detail": device["message"]})
    return {"projects": projects, "counts": counts, "device": device, "inventory": inventory,
            "bambuddy_url": core.config().get("bambuddy_url", "http://127.0.0.1:8017"),
            "updated_at": core.now(), "library_count": len(core.library()["documents"]), "action_items": actions}


def artifact_response(path: Path):
    inline = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".glb": "model/gltf-binary", ".pdf": "application/pdf"}
    if path.suffix.lower() in inline:
        return FileResponse(path, media_type=inline[path.suffix.lower()])
    if path.suffix.lower() in {".md", ".txt", ".json", ".py", ".svg", ".html", ".js"}:
        return FileResponse(path, media_type="text/plain", headers={"Content-Security-Policy": "default-src 'none'; sandbox"})
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@app.get("/api/files/{pid}/{relative:path}")
def project_file(pid: str, relative: str):
    return artifact_response(core.public_project_file(pid, relative))


@app.get("/api/documents/{relative:path}")
def document(relative: str):
    return artifact_response(core.public_document(relative))


app.include_router(prepared_router)

# Mount last so a SPA route cannot shadow an API endpoint.
dist = core.ROOT / "Harness/studio/dist"
if dist.is_dir():
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = core.safe_path(dist, path or "index.html", require_file=False)
        if not target.is_file():
            target = dist / "index.html"
        return FileResponse(target)
