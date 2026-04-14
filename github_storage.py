"""
GitHub image storage backend.

Images are committed to a PUBLIC GitHub repo so they can be served
directly via raw.githubusercontent.com without authentication.

Required env vars:
  GITHUB_STORAGE_TOKEN  — personal access token with repo write scope
  GITHUB_STORAGE_REPO   — "username/repo-name" (must be public)
  GITHUB_STORAGE_BRANCH — branch to commit to (default: main)
"""

import os
import base64
import requests

TOKEN  = os.environ.get("GITHUB_STORAGE_TOKEN", "")
REPO   = os.environ.get("GITHUB_STORAGE_REPO", "")
BRANCH = os.environ.get("GITHUB_STORAGE_BRANCH", "main")

_API = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def upload(file_bytes: bytes, path: str) -> str | None:
    """
    Upload raw bytes to `path` in the configured repo.
    Returns the public raw CDN URL, or None on failure.
    """
    if not TOKEN or not REPO:
        return None

    url = f"{_API}/repos/{REPO}/contents/{path}"

    # Fetch existing file SHA (needed to overwrite)
    sha = None
    resp = requests.get(url, headers=_headers(), params={"ref": BRANCH}, timeout=10)
    if resp.status_code == 200:
        sha = resp.json().get("sha")

    body = {
        "message": f"spotilist: upload {path}",
        "content": base64.b64encode(file_bytes).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(url, json=body, headers=_headers(), timeout=15)
    if resp.ok:
        return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}"

    return None


def is_configured() -> bool:
    return bool(TOKEN and REPO)
