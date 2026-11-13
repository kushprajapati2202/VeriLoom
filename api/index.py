"""Vercel Serverless Function Entrypoint for VeriLoom AI."""

import os
import sys
from pathlib import Path

# Add project root to python path for Vercel Serverless execution
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from veriloom.api.server import app

# Expose app for Vercel Python runtime

