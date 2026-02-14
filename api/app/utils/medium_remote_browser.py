from __future__ import annotations

import base64
import json
import shlex
import subprocess
import textwrap
from typing import Optional

import logging

from app.config import settings

logger = logging.getLogger("medium_remote_browser")


def _ssh_run(remote_cmd: str) -> subprocess.CompletedProcess[str] | None:
    if not settings.remote_fetch_host:
        return None

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
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.remote_fetch_timeout,
        )
    except Exception:
        logger.exception("ssh failed")
        return None


def remote_medium_fetch_html(url: str, *, max_bytes: int) -> Optional[str]:
    """
    Fetch Medium HTML via a human-driven Chromium session on the remote machine.
    This is the canonical Medium fetch path: Playwright connects over CDP to the
    existing Chrome profile (login state lives on the remote host).
    """
    if not settings.remote_fetch_enabled:
        return None
    if not settings.remote_fetch_host:
        return None

    remote_script = textwrap.dedent(
        """
        const { chromium } = require("playwright");

        const url = process.env.URL;
        const maxBytes = parseInt(process.env.MAX_BYTES || "5000000", 10);
        const cdp = process.env.CDP_URL || "http://127.0.0.1:9222";
        const navTimeoutMs = parseInt(process.env.NAV_TIMEOUT_MS || "60000", 10);

        if (!url) {
          console.log(JSON.stringify({ ok: false, error: "missing_url" }));
          process.exit(0);
        }

        (async () => {
          try {
            const browser = await chromium.connectOverCDP(cdp);
            const context = browser.contexts()[0];
            if (!context) {
              console.log(JSON.stringify({ ok: false, error: "no_context" }));
              try { await browser.close(); } catch (e) {}
              return;
            }
            const page = await context.newPage();
            page.setDefaultNavigationTimeout(navTimeoutMs);

            await page.route("**/*", (route) => {
              const t = route.request().resourceType();
              if (t === "image" || t === "font" || t === "media") return route.abort();
              return route.continue();
            });

            const resp = await page.goto(url, { waitUntil: "domcontentloaded" });
            try { await page.waitForSelector("article", { timeout: 8000 }); } catch (e) {}
            await page.waitForTimeout(1000);

            const html = await page.content();
            const status = resp ? resp.status() : null;
            const title = await page.title().catch(() => "");
            const finalUrl = page.url();
            const webdriver = await page.evaluate(() => navigator.webdriver).catch(() => null);

            const lower = html.toLowerCase();
            const blocked =
              lower.includes("just a moment") ||
              lower.includes("cf-chl") ||
              lower.includes("challenge-platform") ||
              lower.includes("verify you are human") ||
              lower.includes("access denied");

            if (blocked) {
              console.log(JSON.stringify({ ok: false, error: "blocked", status, title, final_url: finalUrl, webdriver }));
              await page.close().catch(() => {});
              try { await browser.close(); } catch (e) {}
              return;
            }

            const buf = Buffer.from(html, "utf8");
            if (buf.length > maxBytes) {
              console.log(JSON.stringify({ ok: false, error: "too_large", bytes: buf.length, status, final_url: finalUrl }));
              await page.close().catch(() => {});
              try { await browser.close(); } catch (e) {}
              return;
            }

            console.log(
              JSON.stringify({
                ok: true,
                status,
                title,
                final_url: finalUrl,
                webdriver,
                body_b64: buf.toString("base64"),
              })
            );

            await page.close().catch(() => {});
            try { await browser.close(); } catch (e) {}
          } catch (e) {
            console.log(JSON.stringify({ ok: false, error: String(e) }));
          }
        })();
        """
    ).strip()

    remote_cmd = (
        "cd ~/pw-novnc && "
        f"URL={shlex.quote(url)} "
        f"MAX_BYTES={max_bytes} "
        "CDP_URL=http://127.0.0.1:9222 "
        "NAV_TIMEOUT_MS=60000 "
        "/usr/bin/node - <<'NODE'\n"
        f"{remote_script}\n"
        "NODE"
    )

    result = _ssh_run(remote_cmd)
    if result is None:
        return None

    if result.returncode != 0:
        logger.warning(
            "ssh nonzero",
            extra={"url": url, "code": result.returncode, "stderr": (result.stderr or "")[:200]},
        )
        return None

    try:
        payload = json.loads((result.stdout or "").strip())
    except Exception:
        logger.warning("bad json", extra={"url": url, "stdout": (result.stdout or "")[:200]})
        return None

    if not payload.get("ok"):
        logger.info("not ok", extra={"url": url, "payload": payload})
        return None

    body_b64 = payload.get("body_b64") or ""
    try:
        data = base64.b64decode(body_b64)
    except Exception:
        logger.warning("bad b64", extra={"url": url})
        return None

    if len(data) > max_bytes:
        logger.warning("too large", extra={"url": url})
        return None

    try:
        logger.info("ok", extra={"url": url, "bytes": len(data)})
        return data.decode("utf-8", errors="ignore")
    except Exception:
        logger.warning("decode fail", extra={"url": url})
        return None


def remote_medium_healthcheck() -> dict:
    """
    Best-effort remote health check for the CDP-driven Medium browser session.
    Returns a JSON-serializable dict.
    """
    if not settings.remote_fetch_enabled:
        return {"ok": False, "error": "remote_fetch_disabled"}
    if not settings.remote_fetch_host:
        return {"ok": False, "error": "missing_remote_fetch_host"}

    remote_cmd = (
        "python3 - <<'PY'\n"
        "import json, urllib.request\n"
        "url='http://127.0.0.1:9222/json/version'\n"
        "try:\n"
        "  with urllib.request.urlopen(url, timeout=2) as r:\n"
        "    data=json.loads(r.read().decode('utf-8','ignore'))\n"
        "  print(json.dumps({'ok': True, 'webSocketDebuggerUrl': data.get('webSocketDebuggerUrl'), 'Browser': data.get('Browser')}))\n"
        "except Exception as e:\n"
        "  print(json.dumps({'ok': False, 'error': str(e)}))\n"
        "PY"
    )

    result = _ssh_run(remote_cmd)
    if result is None:
        return {"ok": False, "error": "ssh_failed"}
    if result.returncode != 0:
        return {"ok": False, "error": "ssh_nonzero", "stderr": (result.stderr or "")[:200]}
    try:
        return json.loads((result.stdout or "").strip())
    except Exception:
        return {"ok": False, "error": "bad_json", "stdout": (result.stdout or "")[:200]}
