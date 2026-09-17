"""SQLite storage: products queue, posted pins, logs."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,              -- amazon | meesho | flipkart | other
    url           TEXT NOT NULL,              -- original product url
    affiliate_url TEXT NOT NULL DEFAULT '',   -- monetized link that goes on the pin
    title         TEXT NOT NULL,
    price         TEXT NOT NULL DEFAULT '',
    currency      TEXT NOT NULL DEFAULT 'INR',
    image_url     TEXT NOT NULL DEFAULT '',
    image_path    TEXT NOT NULL DEFAULT '',   -- local downloaded/generated pin image
    pin_image     TEXT NOT NULL DEFAULT '',   -- generated designed pin graphic
    video_url     TEXT NOT NULL DEFAULT '',
    video_path    TEXT NOT NULL DEFAULT '',   -- locally downloaded product video
    variant       INTEGER NOT NULL DEFAULT 0, -- pin variation # for same product
    category      TEXT NOT NULL DEFAULT '',
    seo_text      TEXT NOT NULL DEFAULT '',   -- final description for pinterest
    status        TEXT NOT NULL DEFAULT 'queued',  -- queued|posted|failed|skipped
    error         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL,
    pin_id         TEXT NOT NULL DEFAULT '',
    board_id       TEXT NOT NULL DEFAULT '',
    scheduled_for  TEXT NOT NULL DEFAULT '',
    posted_at      TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'pending', -- pending|posted|failed
    error          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    ts         TEXT NOT NULL,
    ua         TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS subscribers (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    ts    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
"""

MIGRATIONS = [
    "ALTER TABLE products ADD COLUMN variant INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN video_path TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE posts ADD COLUMN ig_post_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE posts ADD COLUMN ig_error TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE products ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN score INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN discount INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE products ADD COLUMN template TEXT NOT NULL DEFAULT ''",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            for stmt in MIGRATIONS:  # upgrade older DBs; ignore if column exists
                try:
                    c.execute(stmt)
                except sqlite3.OperationalError:
                    pass

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ------------------------------------------------------------------ logs
    def log(self, level: str, message: str) -> None:
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO logs(ts, level, message) VALUES(?,?,?)",
                (utcnow(), level.upper(), message),
            )

    def recent_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- products
    def add_product(self, **fields: Any) -> int:
        fields.setdefault("status", "queued")
        fields.setdefault("created_at", utcnow())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with _lock, self._conn() as c:
            cur = c.execute(
                f"INSERT INTO products({cols}) VALUES({marks})", list(fields.values())
            )
            return int(cur.lastrowid)

    def url_exists(self, url: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM products WHERE url=? AND variant=0 LIMIT 1", (url,)
            ).fetchone()
        return row is not None

    def pending_products(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM products WHERE status='queued'
                   ORDER BY score DESC, id ASC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_products(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM products ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_product(self, pid: int, **fields: Any) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with _lock, self._conn() as c:
            c.execute(
                f"UPDATE products SET {sets} WHERE id=?",
                [*fields.values(), pid],
            )

    def stats(self) -> dict[str, Any]:
        with self._conn() as c:
            q = c.execute(
                "SELECT status, COUNT(*) n FROM products GROUP BY status"
            ).fetchall()
            total = sum(r["n"] for r in q)
            by_status = {r["status"]: r["n"] for r in q}
        return {
            "total": total,
            "queued": by_status.get("queued", 0),
            "posted": by_status.get("posted", 0),
            "failed": by_status.get("failed", 0),
            "skipped": by_status.get("skipped", 0),
        }

    # ----------------------------------------------------------------- posts
    def add_post(self, **fields: Any) -> int:
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with _lock, self._conn() as c:
            cur = c.execute(
                f"INSERT INTO posts({cols}) VALUES({marks})", list(fields.values())
            )
            return int(cur.lastrowid)

    def update_post(self, post_id: int, **fields: Any) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with _lock, self._conn() as c:
            c.execute(f"UPDATE posts SET {sets} WHERE id=?", [*fields.values(), post_id])

    def recent_posts(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT p.*, pr.title, pr.source, pr.affiliate_url, pr.pin_image,
                          (SELECT COUNT(*) FROM clicks cl WHERE cl.product_id=p.product_id) AS clicks
                   FROM posts p JOIN products pr ON pr.id=p.product_id
                   ORDER BY p.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- reshare
    def reshare_candidates(self, min_clicks: int = 3, rest_days: int = 7,
                           max_shares: int = 3, limit: int = 5) -> list[dict]:
        """Proven winners worth re-pinning with FRESH designs.

        Top-0.1% trick: Pinterest rewards NEW pins, and winners earn more
        each round — so rotate them (new template, new keywords, same deal).
        """
        sql = """
        SELECT p.*,
          (SELECT COUNT(*) FROM posts po WHERE po.product_id=p.id
             AND po.status='posted') AS shares,
          (SELECT MAX(po.posted_at) FROM posts po WHERE po.product_id=p.id
             AND po.status='posted') AS last_post,
          (SELECT COUNT(*) FROM clicks cl WHERE cl.product_id=p.id) AS clicks
        FROM products p WHERE p.status='posted'
        """
        rows: list[dict] = []
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(sql).fetchall()]
        now = datetime.now(timezone.utc)
        out = []
        for r in rows:
            if r["clicks"] < min_clicks or r["shares"] >= max_shares:
                continue
            lp = r.get("last_post") or ""
            if lp:
                try:
                    if (now - datetime.fromisoformat(lp)).days < rest_days:
                        continue
                except ValueError:
                    pass
            out.append(r)
        out.sort(key=lambda r: r["clicks"], reverse=True)
        return out[:limit]

    # --------------------------------------------------------------- clicks
    def log_click(self, product_id: int, ua: str = "") -> None:
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO clicks(product_id, ts, ua) VALUES(?,?,?)",
                (product_id, utcnow(), ua[:200]),
            )

    def click_counts(self) -> dict[int, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT product_id, COUNT(*) n FROM clicks GROUP BY product_id"
            ).fetchall()
        return {r["product_id"]: r["n"] for r in rows}

    def template_clicks(self) -> dict[str, int]:
        """Clicks per pin template — feeds the CTR learning loop."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT pr.template, COUNT(*) n FROM clicks cl
                   JOIN products pr ON pr.id = cl.product_id
                   WHERE pr.template != '' GROUP BY pr.template"""
            ).fetchall()
        return {r["template"]: r["n"] for r in rows}

    def click_hours(self) -> dict[int, int]:
        """Clicks per IST hour-of-day — the scheduler learns YOUR best hours."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT CAST(substr(ts, 12, 2) AS INT) h, COUNT(*) n "
                "FROM clicks GROUP BY h"
            ).fetchall()
        return {r["h"]: r["n"] for r in rows}

    # ---------------------------------------------------------- subscribers
    def add_subscriber(self, email: str) -> bool:
        with _lock, self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO subscribers(email, ts) VALUES(?,?)",
                    (email.lower(), utcnow()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def subscriber_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) n FROM subscribers").fetchone()["n"]
