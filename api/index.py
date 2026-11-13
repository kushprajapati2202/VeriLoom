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
    """Normalize paths rewritten by Vercel edge proxy."""
    for header in ("x-invoke-path", "x-matched-path", "x-forwarded-uri", "x-original-path"):
        val = request.headers.get(header)
        if val and not val.startswith("/api/index"):
            request.scope["path"] = val
            break
    else:
        path = request.scope.get("path", "")
        for prefix in ("/api/index.py", "/api/index"):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                request.scope["path"] = remainder if (remainder and remainder.startswith("/")) else ("/" + remainder if remainder else "/")
                break

    return await call_next(request)
