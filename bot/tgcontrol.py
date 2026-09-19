"""Telegram CONTROL bot — phone nunchi machine ni control cheyyadam (R74).

The deals channel already broadcasts one-way. This turns the SAME Telegram bot
into a two-way remote: the owner sends a command from his phone and the
machine answers/acts. Nothing here reaches CUSTOMERS (that rule stands: no
Telegram/WhatsApp outreach) — it is the owner's own control room.

Commands:
  /help              ee list
  /status            queue / posted / failed / clicks + surfacing status
  /deals [n]         last n posted products with their affiliate links
  /link <url>        build every per-surface affiliate link for a product
  /post <url>        queue a product URL (autopilot will post it)
  /surfaces          which platforms are configured right now
  /pause [hours]     stop posting (safety switch)
  /resume            start posting again

Security: only the configured TELEGRAM_CHAT_ID may talk to it. Every other
chat is ignored (and logged), so a leaked bot username cannot drive the bot.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("pindrop.tgcontrol")

HELP = (
    "🤖 Gharvanaa control bot\n"
    "/status — queue, posts, clicks\n"
    "/deals [n] — last posted deals + links\n"
    "/link <product-url> — build affiliate links\n"
    "/post <product-url> — queue a product\n"
    "/surfaces — which platforms are live\n"
    "/pause [hours] — stop posting\n"
    "/resume — start posting\n"
    "/help — ee list"
)


def parse_command(text: str) -> tuple[str, list[str]]:
    """'/link  https://x  y' -> ('link', ['https://x', 'y'])."""
    parts = str(text or "").strip().split()
    if not parts:
        return "", []
    cmd = parts[0].lstrip("/").split("@")[0].lower()
    return cmd, parts[1:]


def env_set(path, key: str, value: str) -> bool:
    """Surgically set KEY=value in a .env file (comments preserved)."""
    import re as _re
    p = Path(path)
    try:
        text = p.read_text()
    except OSError:
        text = ""
    line = f"{key}={value}"
    if _re.search(rf"^{_re.escape(key)}=", text, _re.M):
        text = _re.sub(rf"^{_re.escape(key)}=.*$", line, text, flags=_re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    p.write_text(text)
    try:
        import os as _os
        _os.chmod(path, 0o600)
    except OSError:
        pass
    return True


class TelegramControl:
    """Two-way controller. `reply()` is pure logic; `serve()` is the loop."""

    def __init__(self, cfg, db=None, engine=None, notifier=None):
        from .notify import Notifier
        self.cfg = cfg
        self.db = db
        self.engine = engine
        self.notify = notifier or Notifier()
        self.owner = str(os.getenv("TELEGRAM_CHAT_ID", "") or
                         cfg.get("telegram.owner_chat_id", "") or "").strip()
        self.offset_path = Path(str(cfg.get("storage.db_path", "data/bot.db"))
                                ).parent / "telegram_offset.json"

    # ------------------------------------------------------------- helpers
    def _surfaces(self) -> list[tuple[str, bool, str]]:
        from .affiliate import AffiliateLinker
        from .facebook import FacebookAPI
        from .instagram import InstagramAPI
        from .youtube import YouTubeAPI
        rows: list[tuple[str, bool, str]] = []
        pin_ok = bool(os.getenv("PINTEREST_ACCESS_TOKEN") or
                      self.cfg.get("pinterest.access_token"))
        rows.append(("Pinterest", pin_ok, "pins + video pins (MAIN)"))
        try:
            ig = InstagramAPI(self.cfg)
            rows.append(("Instagram", bool(ig.enabled and ig.configured),
                         "carousel/reel/story/bio/auto-DM"))
        except Exception:  # noqa: BLE001
            rows.append(("Instagram", False, "module error"))
        try:
            fb = FacebookAPI(self.cfg)
            rows.append(("Facebook", bool(fb.enabled and fb.configured),
                         "Page photo/link post"))
        except Exception:  # noqa: BLE001
            rows.append(("Facebook", False, "module error"))
        try:
            yt = YouTubeAPI(self.cfg)
            rows.append(("YouTube", bool(yt.enabled and yt.configured),
                         "Shorts + pinned comment"))
        except Exception:  # noqa: BLE001
            rows.append(("YouTube", False, "module error"))
        rows.append(("Telegram channel",
                     bool(self.notify.token and self.notify.deals_channel),
                     "every deal broadcast"))
        _ = AffiliateLinker  # (kept imported: surface list stays in one place)
        return rows

    def _link_block(self, url: str) -> str:
        from .affiliate import AffiliateLinker, price_label
        lk = AffiliateLinker(self.cfg)
        out = [f"🔗 {url[:90]}"]
        links = lk.meesho_link_for(url, platform="pinterest") if "meesho" in url else ""
        if links:
            out.append(f"• Pinterest/IG: {links}")
        for plat in ("instagram", "facebook", "youtube"):
            try:
                built = lk.convert(url, plat)[0]
            except Exception:  # noqa: BLE001
                built = ""
            if built:
                out.append(f"• {plat.title()}: {built}")
        if len(out) == 1:
            out.append("⚠️ ee URL ki affiliate link build avvaledu "
                       "(Meesho/Amazon/Flipkart product URL ivvandi)")
        return "\n".join(out[:6])

    # -------------------------------------------------------------- replies
    def reply(self, text: str) -> str:
        """Answer a command. Never raises — the phone always gets a reply."""
        cmd, args = parse_command(text)
        try:
            return self._reply(cmd, args)
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram command failed: %s", exc)
            return f"❌ {type(exc).__name__}: {str(exc)[:200]}"

    def _reply(self, cmd: str, args: list[str]) -> str:
        if cmd in ("", "help", "start"):
            return HELP
        if cmd == "status":
            return self._status()
        if cmd == "surfaces":
            lines = ["📡 SURFACES:"]
            for name, ok, what in self._surfaces():
                lines.append(f"{'✅' if ok else '⚪'} {name} — {what}")
            return "\n".join(lines)
        if cmd == "deals":
            n = int(args[0]) if args and args[0].isdigit() else 5
            return self._deals(min(20, max(1, n)))
        if cmd == "link":
            if not args:
                return "Usage: /link <product-url>"
            return self._link_block(args[0])
        if cmd == "post":
            if not args:
                return "Usage: /post <product-url>"
            return self._queue(args[0])
        if cmd == "pause":
            return self._pause(args)
        if cmd == "resume":
            from . import control
            control.resume(self.db)
            return "▶️ Posting resumed."
        return f"❓ Teliyani command: /{cmd}. /help chudandi."

    def _status(self) -> str:
        stats = self.db.stats() if self.db else {}
        clicks = 0
        try:
            clicks = int(self.db.clicks_total()) if self.db else 0
        except Exception:  # noqa: BLE001
            clicks = 0
        from . import control
        paused = control.is_paused(self.db) if self.db else {}
        head = "⏸ PAUSED" if paused.get("paused") else "▶️ running"
        lines = [f"{head} — queue {stats.get('queued', 0)} | posted "
                 f"{stats.get('posted', 0)} | failed {stats.get('failed', 0)} | "
                 f"clicks {clicks}"]
        for name, ok, _what in self._surfaces():
            lines.append(f"{'✅' if ok else '⚪'} {name}")
        return "\n".join(lines)

    def _deals(self, n: int) -> str:
        rows = [p for p in self.db.all_products(limit=400)
                if p.get("status") == "posted"][:n]
        if not rows:
            return "Inka emi post avvaledu — /post <url> tho start cheyyandi."
        out = [f"🛍 Last {len(rows)} deal(s):"]
        for p in rows:
            out.append(f"• {str(p.get('title', ''))[:60]}\n  {p.get('affiliate_url', '')}")
        return "\n".join(out)[:3800]

    def _queue(self, url: str) -> str:
        if not str(url).startswith("http"):
            return "❌ URL http... tho start avvali."
        pid = self.engine.ingest_url(url)
        if not pid or pid < 0:
            return ("⚠️ Ingest avvaledu (link check / media download / duplicate). "
                    "Konni seconds tarvata malli try cheyyandi.")
        return (f"✅ Queued (id {pid}). Autopilot post chestundi.\n"
                f"{self._link_block(url)}")

    def _pause(self, args: list[str]) -> str:
        from . import control
        hours = 0.0
        if args:
            try:
                hours = float(args[0])
            except ValueError:
                hours = 0.0
        until = time.time() + hours * 3600 if hours > 0 else None
        control.pause(self.db, "telegram /pause", until_ts=until)
        return (f"⏸ Paused{'' if not hours else f' for {hours:g}h'} — "
                "/resume tho malli start.")

    def discover_chats(self, drop_pending: bool = True) -> list[tuple[str, str]]:
        """Who has messaged this bot? → [(chat_id, name)].

        Telegram only reveals a chat id AFTER that person messages the bot, so
        the owner sends any message and this finds him. Used by
        `python -m bot telegram --whoami`, which also writes TELEGRAM_CHAT_ID.
        """
        import requests
        if not self.notify.token:
            raise RuntimeError("TELEGRAM_TOKEN ledu")
        resp = requests.get(
            f"https://api.telegram.org/bot{self.notify.token}/getUpdates",
            params={"offset": -20, "timeout": 0,
                    "allowed_updates": '["message","channel_post"]'},
            timeout=20)
        data = resp.json() if resp.status_code == 200 else {}
        if not data.get("ok"):
            raise RuntimeError(str(data.get("description") or
                                   f"HTTP {resp.status_code}"))
        found: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for upd in data.get("result", []) or []:
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = str(chat.get("id", ""))
            if not cid:
                continue
            name = (chat.get("title") or chat.get("username")
                    or " ".join(x for x in (chat.get("first_name"),
                                            chat.get("last_name")) if x)
                    or chat.get("type", "?"))
            if cid in seen_ids:
                continue                      # one entry per chat, best name
            seen_ids.add(cid)
            found.append((cid, name))
        if drop_pending:
            try:
                self._write_offset(max(int(u.get("update_id", 0))
                                       for u in data.get("result", [])))
            except ValueError:
                pass
        return found

    # ---------------------------------------------------------------- loop
    def _read_offset(self) -> int:
        try:
            import json
            return int(json.loads(self.offset_path.read_text()).get("offset", 0))
        except Exception:  # noqa: BLE001
            return 0

    def _write_offset(self, offset: int) -> None:
        try:
            import json
            self.offset_path.parent.mkdir(parents=True, exist_ok=True)
            self.offset_path.write_text(json.dumps({"offset": int(offset)}))
        except OSError:
            pass

    def poll_once(self, timeout: int = 25) -> int:
        """One getUpdates round. Returns how many messages were answered."""
        import requests
        if not self.notify.token:
            return 0
        offset = self._read_offset()
        resp = requests.get(
            f"https://api.telegram.org/bot{self.notify.token}/getUpdates",
            params={"offset": offset + 1, "timeout": timeout,
                    "allowed_updates": '["message"]'},
            timeout=timeout + 10)
        data = resp.json() if resp.status_code == 200 else {}
        if not data.get("ok"):
            # a bad token / blocked network must not spin: caller decides
            raise RuntimeError(str(data.get("description") or resp.status_code))
        answered = 0
        for upd in data.get("result", []) or []:
            self._write_offset(int(upd.get("update_id", offset)))
            msg = upd.get("message") or {}
            chat = str((msg.get("chat") or {}).get("id", ""))
            text = msg.get("text") or ""
            if not text.startswith("/"):
                continue
            if self.owner and chat != self.owner:
                log.warning("telegram: ignoring command from chat %s", chat)
                continue
            self.notify.send_to(chat, self.reply(text))
            answered += 1
        return answered

    def serve(self, poll: int = 25) -> None:
        """Blocking loop — run it in the scheduler or a terminal."""
        if not self.notify.token:
            print("❌ TELEGRAM_TOKEN ledu — .env lo pettandi.")
            return
        if not self.owner:
            print("⚠️  TELEGRAM_CHAT_ID ledu — evaru commands pampakoodadu "
                  "(safe default: anni ignore avutayi).")
        print(f"🤖 Telegram control live (owner chat: {self.owner or 'UNSET'})")
        while True:
            try:
                self.poll_once(poll)
            except KeyboardInterrupt:
                print("\n→ control bot stopped")
                return
            except Exception as exc:  # noqa: BLE001 — never die on a bad night
                log.warning("telegram poll failed: %s", exc)
                time.sleep(15)
