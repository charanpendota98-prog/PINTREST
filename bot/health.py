"""Money-path health: are the affiliate links ALIVE and still MONETIZED?

A dead or un-tagged link is silent money loss: the pin still posts, clicks
still register, and the owner earns zero. This module answers the question
directly:

* `check_link(url)`      — follows redirects, reports final status + whether
  the landing URL still carries our tracking (tag / af_invite / template).
* `audit_links(cfg, db)` — checks the queued + recently posted products.
* `audit_secrets(cfg)`   — .env / token file permissions (world-readable
  secrets are how channels get hijacked).

Network calls are best-effort and bounded; every function is safe to call from
the panel, the CLI and the doctor.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from urllib.parse import urlparse

TIMEOUT = 15


def _tracking_tokens(cfg) -> list[str]:
    toks = []
    for key in ("affiliate.meesho_affid", "affiliate.earnkaro_prefix",
                "affiliate.cuelinks_template"):
        val = str(cfg.get(key, "") or "")
        if val:
            toks.append(val.split("{")[0].split("?")[0][:40])
    if cfg.amazon_tag:
        toks.append(str(cfg.amazon_tag))
    return [t for t in toks if t]


def check_link(cfg, url: str, session=None) -> dict:
    """Is this link reachable AND still monetized? Never raises."""
    out = {"url": str(url or "")[:300], "ok": False, "status": 0,
           "final": "", "monetized": False, "note": ""}
    if not url or urlparse(url).scheme not in ("http", "https"):
        out["note"] = "not a http(s) link"
        return out
    try:
        import requests
        s = session or requests.Session()
        resp = s.get(url, timeout=TIMEOUT, allow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (PinDrop link check)"})
        out["status"] = int(resp.status_code)
        out["final"] = str(resp.url)[:300]
        out["ok"] = 200 <= resp.status_code < 400
        haystack = (out["final"] + " " + url).lower()
        out["monetized"] = any(t.lower() in haystack
                               for t in _tracking_tokens(cfg))
        if out["ok"] and not out["monetized"]:
            out["note"] = "reachable but tracking token missing — check .env"
        elif not out["ok"]:
            out["note"] = f"HTTP {resp.status_code} — link may be dead"
    except Exception as exc:  # noqa: BLE001 — a check must never crash a run
        out["note"] = f"check failed: {str(exc)[:120]}"
    return out


def audit_links(cfg, db, limit: int = 10, session=None,
                statuses: tuple[str, ...] = ("queued", "posted")) -> list[dict]:
    """Check the links the bot is about to use (queued first = money first)."""
    rows = [p for p in (db.all_products(limit=200) or [])
            if p.get("status") in statuses]
    rows.sort(key=lambda p: 0 if p.get("status") == "queued" else 1)
    results = []
    for p in rows[:max(1, int(limit))]:
        link = p.get("affiliate_url") or p.get("url") or ""
        res = check_link(cfg, link, session=session)
        res.update({"product_id": p.get("id"), "title": (p.get("title") or "")[:70],
                    "source": p.get("source", "")})
        results.append(res)
    return results


def audit_secrets(cfg, root: Path | None = None) -> list[dict]:
    """Permissions + presence of the files that hold real credentials."""
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    findings = []
    for path, label in ((root / ".env", ".env"),
                        (cfg.token_path, "pinterest_token.json"),
                        (root / "data" / "dashboard_password.txt",
                         "dashboard_password.txt"),
                        (root / "data" / "dashboard_secret.txt",
                         "dashboard_secret.txt")):
        p = Path(path)
        if not p.exists():
            findings.append({"file": label, "exists": False, "ok": True,
                             "note": "absent (fine)"})
            continue
        try:
            mode = stat.S_IMODE(os.stat(p).st_mode)
        except OSError as exc:
            findings.append({"file": label, "exists": True, "ok": False,
                             "note": f"stat failed: {exc}"})
            continue
        world = bool(mode & (stat.S_IRGRP | stat.S_IROTH))
        findings.append({
            "file": label, "exists": True, "mode": oct(mode), "ok": not world,
            "note": ("group/world readable — run: chmod 600 " + str(p))
                    if world else "private (600)",
        })
    return findings


def secrets_ok(findings: list[dict]) -> bool:
    return all(f.get("ok", True) for f in findings)


def summary(results: list[dict]) -> str:
    """One line for logs/panel: '3/4 links healthy, 1 broken'."""
    if not results:
        return "no links to check"
    good = sum(1 for r in results if r["ok"] and r["monetized"])
    dead = sum(1 for r in results if not r["ok"])
    untagged = sum(1 for r in results if r["ok"] and not r["monetized"])
    return f"{good}/{len(results)} links healthy, {dead} unreachable, {untagged} untagged"
