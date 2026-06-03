# VoiceBridge v2 — Solo Translation App
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.ws import router as ws_router

app = FastAPI(title="VoiceBridge", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control: no-cache to CSS/JS files to prevent Cloudflare caching."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(('.css', '.js', '.html')) or path == '/' or path == '':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response


app.add_middleware(NoCacheStaticMiddleware)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/version")
async def version():
    return {"version": "0.2.0", "build": os.getenv("BUILD_COMMIT", "dev")}


BUILD_COMMIT = os.getenv("BUILD_COMMIT", "unknown")


@app.get("/ops/check-update")
async def check_update():
    """Self-diagnostic: compare local BUILD_COMMIT vs ghcr.io latest tag.

    Returns:
    - local_sha: running version in container
    - remote_sha: revision label of ghcr.io latest tag
    - needs_update: whether update is needed
    - pull_error: error if ghcr.io query failed
    - diagnosis: human-readable diagnosis
    """
    import httpx

    result = {
        "ok": True,
        "local_sha": BUILD_COMMIT,
    }

    repo = "immurray/voicebridge"

    try:
        # Step 1 — Anonymous ghcr.io token
        token_resp = await httpx.AsyncClient().get(
            f"https://ghcr.io/token?scope=repository:{repo}:pull&service=ghcr.io",
            timeout=10,
        )
        if token_resp.status_code != 200:
            result["pull_error"] = f"ghcr token: HTTP {token_resp.status_code}"
            result["ok"] = False
            return result

        token = token_resp.json().get("token", "")
        if not token:
            result["pull_error"] = "ghcr returned empty token"
            result["ok"] = False
            return result

        # Step 2 — OCI index for latest
        idx_resp = await httpx.AsyncClient().get(
            f"https://ghcr.io/v2/{repo}/manifests/latest",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.oci.image.index.v1+json",
            },
            timeout=15,
        )
        if idx_resp.status_code != 200:
            result["pull_error"] = f"ghcr manifest: HTTP {idx_resp.status_code}"
            result["ok"] = False
            return result

        idx = idx_resp.json()
        manifests = idx.get("manifests", [])
        amd64 = next(
            (m for m in manifests
             if m.get("platform", {}).get("architecture") == "amd64"),
            None,
        )
        if not amd64:
            result["pull_error"] = "no amd64 manifest in index"
            result["ok"] = False
            return result

        result["remote_amd64_digest"] = amd64["digest"][:40]

        # Step 3 — AMD64 manifest → config digest
        manifest_resp = await httpx.AsyncClient().get(
            f"https://ghcr.io/v2/{repo}/manifests/{amd64['digest']}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.oci.image.manifest.v1+json",
            },
            timeout=15,
        )
        if manifest_resp.status_code != 200:
            result["pull_error"] = f"ghcr amd64 manifest: HTTP {manifest_resp.status_code}"
            result["ok"] = False
            return result

        manifest = manifest_resp.json()
        config_digest = manifest.get("config", {}).get("digest", "")
        if not config_digest:
            result["pull_error"] = "no config digest in manifest"
            result["ok"] = False
            return result

        # Step 4 — Config blob → revision label
        cfg_resp = await httpx.AsyncClient().get(
            f"https://ghcr.io/v2/{repo}/blobs/{config_digest}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            follow_redirects=True,
        )
        if cfg_resp.status_code != 200:
            result["pull_error"] = f"ghcr config blob: HTTP {cfg_resp.status_code}"
            result["ok"] = False
            return result

        cfg = cfg_resp.json()
        labels = cfg.get("config", {}).get("Labels", {})
        remote_sha = labels.get("org.opencontainers.image.revision", "unknown")
        result["remote_sha"] = remote_sha[:40] if remote_sha else "unknown"
        result["needs_update"] = (BUILD_COMMIT != remote_sha)

        if result["needs_update"]:
            result["diagnosis"] = (
                f"Local={BUILD_COMMIT[:8]}, Remote latest={remote_sha[:8]}. "
                "Image pushed but Watchtower not pulled — Docker daemon may have cached old digest. "
                "Fix: docker rmi ghcr.io/immurray/voicebridge:latest on server, "
                "or set container pull policy to 'always' in 1Panel."
            )
        else:
            result["diagnosis"] = "Local is up-to-date."

    except Exception as e:
        result["pull_error"] = str(e)[:500]
        result["ok"] = False

    return result


# Static files — MUST be last to avoid eating API routes
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)

# Explicit routes for cache-busted JS/CSS to bypass nginx cache
from fastapi.responses import FileResponse
import time as _time

@app.get("/app.js")
async def app_js():
    """Serve app.js with aggressive no-cache to defeat proxy caching."""
    return FileResponse(
        static_dir / "app.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "ETag": os.getenv("BUILD_COMMIT", str(int(_time.time()))),
        }
    )

@app.get("/style.css")
async def style_css():
    """Serve style.css with aggressive no-cache."""
    return FileResponse(
        static_dir / "style.css",
        media_type="text/css",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "ETag": os.getenv("BUILD_COMMIT", str(int(_time.time()))),
        }
    )

@app.get("/processor.js")
async def processor_js():
    """Serve processor.js (AudioWorklet) with aggressive no-cache."""
    return FileResponse(
        static_dir / "processor.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
