from __future__ import annotations

import base64
import json
import shlex
import subprocess
import textwrap
from typing import Optional
from urllib.parse import urlparse

import logging
from app.config import settings
from app.utils.medium_remote_browser import remote_medium_fetch_html

logger = logging.getLogger("remote_fetch")


def remote_fetch_html(url: str) -> Optional[str]:
    if not settings.remote_fetch_enabled:
        return None
    if not settings.remote_fetch_host:
        return None

    max_bytes = max(10000, settings.remote_fetch_max_bytes)

    host = (urlparse(url).netloc or "").lower()
    is_medium = host.endswith("medium.com")

    if is_medium:
        # Canonical Medium path: remote human-driven Chromium session over CDP.
        return remote_medium_fetch_html(url, max_bytes=max_bytes)
    else:
        remote_script = textwrap.dedent(
            """
            import os, json, base64, urllib.request, urllib.error

            url = os.environ.get("URL")
            ua = os.environ.get("UA", "Mozilla/5.0")
            max_bytes = int(os.environ.get("MAX_BYTES", "5000000"))

            if not url:
                print(json.dumps({"ok": False, "error": "missing_url"}))
                raise SystemExit(0)

            req = urllib.request.Request(url, headers={"User-Agent": ua})
            status = None
            data = b""
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    status = resp.getcode()
                    data = resp.read(max_bytes + 1)
            except urllib.error.HTTPError as e:
                status = e.code
                data = e.read(max_bytes + 1) or b""
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)}))
                raise SystemExit(0)

            if len(data) > max_bytes:
                print(json.dumps({"ok": False, "error": "too_large"}))
                raise SystemExit(0)

            print(
                json.dumps(
                    {
                        "ok": True,
                        "status": status,
                        "body_b64": base64.b64encode(data).decode("ascii"),
                    }
                )
            )
            """
        ).strip()

        remote_cmd = (
            f"URL={shlex.quote(url)} "
            f"UA={shlex.quote(settings.user_agent)} "
            f"MAX_BYTES={max_bytes} "
            "python3 - <<'PY'\n"
            f"{remote_script}\n"
            "PY"
        )

    cmd = [
        "ssh",
        "-i",
        settings.remote_fetch_key_path,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/root/.ssh/known_hosts",
        "-p",
        str(settings.remote_fetch_port),
        f"{settings.remote_fetch_user}@{settings.remote_fetch_host}",
        remote_cmd,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.remote_fetch_timeout,
        )
    except Exception:
        logger.exception("remote_fetch ssh failed", extra={"url": url})
        return None

    if result.returncode != 0:
        logger.warning(
            "remote_fetch ssh nonzero",
            extra={"url": url, "code": result.returncode, "stderr": result.stderr[:200]},
        )
        return None

    try:
        payload = json.loads(result.stdout.strip())
    except Exception:
        logger.warning("remote_fetch bad json", extra={"url": url})
        return None

    if not payload.get("ok"):
        logger.info("remote_fetch not ok", extra={"url": url, "payload": payload})
        return None

    body_b64 = payload.get("body_b64") or ""
    try:
        data = base64.b64decode(body_b64)
    except Exception:
        logger.warning("remote_fetch bad b64", extra={"url": url})
        return None

    if len(data) > max_bytes:
        logger.warning("remote_fetch too large", extra={"url": url})
        return None
    try:
        logger.info("remote_fetch ok", extra={"url": url, "bytes": len(data)})
        return data.decode("utf-8", errors="ignore")
    except Exception:
        logger.warning("remote_fetch decode fail", extra={"url": url})
        return None
