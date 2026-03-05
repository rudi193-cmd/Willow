# DS=42
"""
app_scaffold.py -- SAFE App Scaffolding Tool for Kart

Single entry point: scaffold_app(name, description, scopes, ...)
Threads together: scaffold.py + opauth + manifest generation.
"""

import json
import os
import sys
import re
import tempfile
from pathlib import Path
from datetime import datetime

WILLOW_ROOT = Path(r"C:/Users/Sean/Documents/GitHub/Willow")
APPS_ROOT = Path(r"C:/Users/Sean/Documents/GitHub")

PERMISSION_TYPES = [
    "local_llm", "cloud_llm_free", "image_ocr",
    "pattern_storage", "file_read", "file_write", "network_fetch",
]

SCOPE_TO_STREAM = {
    "local_llm": {
        "id": "llm_queries", "purpose": "AI processing",
        "retention": "session", "description": "Local LLM inference requests",
    },
    "cloud_llm_free": {
        "id": "cloud_llm_queries", "purpose": "AI processing via free cloud tier",
        "retention": "session", "description": "Cloud LLM API calls",
    },
    "image_ocr": {
        "id": "ocr_data", "purpose": "Image text extraction",
        "retention": "session", "description": "OCR processed image data",
    },
    "pattern_storage": {
        "id": "patterns", "purpose": "Behavioral pattern storage",
        "retention": "permanent", "description": "User pattern data",
    },
    "file_read": {
        "id": "file_reads", "purpose": "File system access",
        "retention": "session", "description": "Files read by app",
    },
    "file_write": {
        "id": "file_writes", "purpose": "File system writes",
        "retention": "permanent", "description": "Files written by app",
    },
    "network_fetch": {
        "id": "network_requests", "purpose": "Network data fetching",
        "retention": "session", "description": "Outbound network requests",
    },
}

SCAFFOLD_TOOL = {
    "name": "scaffold_app",
    "description": (
        "Scaffold a new SAFE app from willow-seed template. "
        "Creates directory, manifest, agent profile, and registers opauth scopes."
    ),
    "parameters": {
        "name": "App name in kebab-case (e.g. reading-tracker). Do NOT include safe-app- prefix.",
        "description": "One-line description of what the app does.",
        "scopes": (
            "List of required permissions from: "
            "local_llm, cloud_llm_free, image_ocr, pattern_storage, "
            "file_read, file_write, network_fetch"
        ),
        "data_streams": (
            "Optional list of data stream dicts. "
            "Auto-generated from scopes if not provided."
        ),
        "author": "Author name (default: Sean Campbell)",
        "privacy_tier": "client_only|hybrid|cloud_optional (default: client_only)",
    },
}


def scaffold_app(
    name: str,
    description: str,
    scopes: list,
    data_streams: list = None,
    author: str = "Sean Campbell",
    privacy_tier: str = "client_only",
    local_processing: float = 0.96,
    username: str = "Sweet-Pea-Rudi19",
) -> dict:
    """
    Scaffold a new safe-app-{name}.

    Returns:
        {
            "success": bool,
            "app_id": str,
            "app_dir": str,
            "steps": [{"step": str, "status": "ok"|"skip"|"error", "detail": str}],
            "checklist": [str],
            "manifest_path": str,
            "errors": [str],
        }
    """
    steps = []
    errors = []
    app_id = "safe-app-" + name
    manifest_path = ""

    # Step 1: Validate name
    if not re.match(r"^[a-z][a-z0-9-]*$", name):
        return {
            "success": False, "app_id": app_id, "app_dir": "",
            "steps": [{"step": "validate", "status": "error",
                        "detail": "Name must be kebab-case (lowercase letters, digits, hyphens)"}],
            "checklist": [], "manifest_path": "", "errors": ["Invalid name format"],
        }
    if name.startswith("safe-app-"):
        return {
            "success": False, "app_id": app_id, "app_dir": "",
            "steps": [{"step": "validate", "status": "error",
                        "detail": "Do not include safe-app- prefix -- it is added automatically"}],
            "checklist": [], "manifest_path": "", "errors": ["Name includes prefix"],
        }
    app_dir = APPS_ROOT / app_id
    if app_dir.exists():
        return {
            "success": False, "app_id": app_id, "app_dir": str(app_dir),
            "steps": [{"step": "validate", "status": "error",
                        "detail": "Directory already exists: " + str(app_dir)}],
            "checklist": [], "manifest_path": "", "errors": ["App already exists"],
        }
    steps.append({"step": "validate", "status": "ok", "detail": "Name " + repr(name) + " is valid"})

    # Step 2: Create directories
    try:
        for sub in ("", "src", "tests", "docs"):
            (app_dir / sub).mkdir(parents=True, exist_ok=True)
        steps.append({"step": "create_dirs", "status": "ok", "detail": str(app_dir)})
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "create_dirs", "status": "error", "detail": detail})
        errors.append(detail)
        return {
            "success": False, "app_id": app_id, "app_dir": str(app_dir),
            "steps": steps, "checklist": [], "manifest_path": "", "errors": errors,
        }

    # Step 3: Generate manifest
    manifest_path = str(app_dir / "safe-app-manifest.json")
    try:
        streams = data_streams
        if streams is None:
            streams = [SCOPE_TO_STREAM[s] for s in scopes if s in SCOPE_TO_STREAM]
        manifest = {
            "app_id": app_id,
            "name": name,
            "version": "1.0.0",
            "safe_version": ">=2.0.0",
            "description": description,
            "author": author,
            "data_streams": streams,
            "permissions": scopes,
            "privacy_tier": privacy_tier,
            "local_processing": local_processing,
            "entry_point": "app.main:run",
            "license": "MIT",
            "repository": "https://github.com/rudi193-cmd/" + app_id,
        }
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        steps.append({"step": "manifest", "status": "ok", "detail": manifest_path})
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "manifest", "status": "error", "detail": detail})
        errors.append("manifest: " + detail)

    # Step 4: Run scaffold.py (non-fatal)
    try:
        scaffold_dir = str(WILLOW_ROOT / "templates" / "new_agent")
        if scaffold_dir not in sys.path:
            sys.path.insert(0, scaffold_dir)
        from scaffold import scaffold as _scaffold  # noqa: PLC0415
        agent_name = name.replace("-", "_")
        config = {
            "agent_name": agent_name,
            "template_user": "__template__" + name + "__",
            "domains": [],
        }
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as tf:
            json.dump(config, tf)
            tf_path = tf.name
        _scaffold(tf_path)
        try:
            os.unlink(tf_path)
        except OSError:
            pass
        steps.append({
            "step": "scaffold_agent", "status": "ok",
            "detail": "Agent " + repr(agent_name) + " scaffolded in Willow",
        })
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "scaffold_agent", "status": "error", "detail": detail})
        errors.append("scaffold: " + detail)

    # Step 5: Register opauth scopes (non-fatal)
    try:
        opauth_dir = str(WILLOW_ROOT / "apps" / "opauth" / "core")
        if opauth_dir not in sys.path:
            sys.path.insert(0, opauth_dir)
        from scope_registry import ScopeRegistry  # noqa: PLC0415
        ScopeRegistry().grant(service=app_id, scope=scopes, granted_by="human")
        steps.append({
            "step": "opauth_scopes", "status": "ok",
            "detail": "Granted " + str(len(scopes)) + " scope(s) for " + app_id,
        })
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "opauth_scopes", "status": "error", "detail": detail})
        errors.append("opauth: " + detail)

    # Step 6: Write README stub (non-fatal)
    try:
        readme = (
            "# " + app_id + "\n\n" + description + "\n\n"
            "## Install\n\n    pip install " + app_id + "\n"
        )
        (app_dir / "README.md").write_text(readme, encoding="utf-8")
        steps.append({"step": "readme", "status": "ok", "detail": "README.md written"})
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "readme", "status": "error", "detail": detail})
        errors.append("readme: " + detail)

    # Step 7: Write pyproject.toml stub (non-fatal)
    try:
        pyproject = (
            "[project]\n"
            "name = \"" + app_id + "\"\n"
            "version = \"1.0.0\"\n"
            "description = \"" + description + "\"\n"
            "requires-python = \">=3.10\"\n"
        )
        (app_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        steps.append({"step": "pyproject", "status": "ok", "detail": "pyproject.toml written"})
    except Exception as exc:
        detail = str(exc)
        steps.append({"step": "pyproject", "status": "error", "detail": detail})
        errors.append("pyproject: " + detail)

    # Step 8: Build checklist and return
    checklist = [
        "[ ] Create GitHub repo: gh repo create rudi193-cmd/" + app_id + " --public",
        "[ ] Push: cd " + app_id + " && git init && git add . && git commit -m init && git push",
        "[ ] Add to SAFE/apps/REGISTRY.yaml under community_apps",
        "[ ] Implement src/ app logic",
        "[ ] Run opauth grant if scopes not auto-registered",
    ]
    return {
        "success": len(errors) == 0,
        "app_id": app_id,
        "app_dir": str(app_dir),
        "steps": steps,
        "checklist": checklist,
        "manifest_path": manifest_path,
        "errors": errors,
    }


def get_scaffold_status(name: str) -> dict:
    """Check what exists for safe-app-{name}. Returns dict of what is present."""
    app_id = "safe-app-" + name
    app_dir = APPS_ROOT / app_id
    return {
        "app_id": app_id,
        "exists": app_dir.exists(),
        "components": {
            "app_dir": app_dir.exists(),
            "manifest": (app_dir / "safe-app-manifest.json").exists(),
            "readme": (app_dir / "README.md").exists(),
            "pyproject": (app_dir / "pyproject.toml").exists(),
            "src": (app_dir / "src").exists(),
        },
    }
