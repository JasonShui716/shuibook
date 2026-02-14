from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

OUTPUT = Path("config/medium_storage.json")


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _pick_local_key_path(dotenv: dict[str, str]) -> str:
    # .env uses the container path; for local runs we fall back to common host paths.
    candidates = [
        os.environ.get("REMOTE_FETCH_KEY_PATH"),
        dotenv.get("REMOTE_FETCH_KEY_PATH"),
        str(Path.home() / ".ssh" / "id_ed25519_conknow"),
        str(Path.home() / ".ssh" / "id_ed25519"),
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if p.exists():
            return str(p)
    raise SystemExit("No SSH key found. Set REMOTE_FETCH_KEY_PATH to a local readable private key path.")


def main() -> None:
    dotenv = _load_dotenv(Path(".env"))
    host = os.environ.get("REMOTE_FETCH_HOST") or dotenv.get("REMOTE_FETCH_HOST")
    user = os.environ.get("REMOTE_FETCH_USER") or dotenv.get("REMOTE_FETCH_USER") or "ubuntu"
    port = os.environ.get("REMOTE_FETCH_PORT") or dotenv.get("REMOTE_FETCH_PORT") or "22"
    key_path = _pick_local_key_path(dotenv)

    if not host:
        raise SystemExit("Missing REMOTE_FETCH_HOST (set it in .env or env var).")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    js = textwrap.dedent(
        """
        const { chromium } = require("playwright");

        const cdp = process.env.CDP_URL || "http://127.0.0.1:9222";
        const out = process.env.OUT || "/tmp/medium_storage_state.json";

        (async () => {
          const browser = await chromium.connectOverCDP(cdp);
          const context = browser.contexts()[0];
          if (!context) throw new Error("no_context");

          // Touch medium.com so cookies are in scope.
          const page = await context.newPage();
          try {
            await page.goto("https://medium.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
          } catch {}
          await page.close().catch(() => {});

          await context.storageState({ path: out });
          console.log(JSON.stringify({ ok: true, out }));

          try { await browser.close(); } catch {}
        })().catch((e) => {
          console.log(JSON.stringify({ ok: false, error: String(e) }));
          process.exit(0);
        });
        """
    ).strip()

    with tempfile.TemporaryDirectory() as td:
        local_js = Path(td) / "export_medium_storage_state.js"
        local_js.write_text(js, encoding="utf-8")

        remote_js = "pw-novnc/export_medium_storage_state.js"
        remote_out = "/tmp/medium_storage_state.json"

        scp_base = [
            "scp",
            "-P",
            str(port),
            "-i",
            key_path,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        ssh_base = [
            "ssh",
            "-p",
            str(port),
            "-i",
            key_path,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]

        subprocess.check_call(
            scp_base + [str(local_js), f"{user}@{host}:{remote_js}"],
        )
        subprocess.check_call(
            ssh_base
            + [
                f"{user}@{host}",
                f"cd ~/pw-novnc && OUT={remote_out} CDP_URL=http://127.0.0.1:9222 node ./export_medium_storage_state.js",
            ]
        )
        subprocess.check_call(
            scp_base + [f"{user}@{host}:{remote_out}", str(OUTPUT)],
        )

    print(f"已从远端 CDP 导出 Medium 登录态到: {OUTPUT}")


if __name__ == "__main__":
    main()
