"""Vercel Serverless Function Entrypoint for VeriLoom AI."""

import os
import sys
from pathlib import Path
from starlette.requests import Request
from starlette.responses import Response

# Add project root to python path for Vercel Serverless execution
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from veriloom.api.server import app


@app.middleware("http")
async def vercel_path_normalizer(request: Request, call_next):
    """Normalize paths rewritten by Vercel edge proxy using endpoint param or headers."""
    endpoint = request.query_params.get("endpoint")
    if endpoint:
        # Strip trailing slash if any (except root)
        if len(endpoint) > 1 and endpoint.endswith("/"):
            endpoint = endpoint.rstrip("/")
        request.scope["path"] = endpoint
    else:
        path = request.scope.get("path", "")
        for header in ("x-invoke-path", "x-matched-path", "x-forwarded-uri"):
            val = request.headers.get(header)
            if val and not val.startswith("/api/index"):
                request.scope["path"] = val
                break
        else:
            if path in ("/api/index.py", "/api/index", "/api/index/"):
                request.scope["path"] = "/"
            elif path.startswith("/api/index.py/"):
                request.scope["path"] = path[len("/api/index.py"):]
            elif path.startswith("/api/index/"):
                request.scope["path"] = path[len("/api/index"):]

    return await call_next(request)
