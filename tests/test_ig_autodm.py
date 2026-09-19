"""R47: ManyChat-style comment → private DM flow (official private replies).

Everything runs against a fake Instagram API, so we can prove EXACTLY what
would be sent: which comment id gets a DM, what text it carries, and that the
same person is never messaged twice.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.config import Config
from bot.db import DB
from bot.engine import Engine
from bot.instagram import InstagramAPI, InstagramError


class FakeIG:
    """Records every call the way the real API would receive it."""

    enabled = True
    configured = True

    def __init__(self, comments=None, conversations=None, fail_dm=False,
                 fail_comment=False, cfg=None, ig_user_id="12345"):
        self.cfg = cfg                      # real methods read config
        self.ig_user_id = ig_user_id
        self.comments = comments if comments is not None else []
        self.conversations = conversations or []
        self.fail_dm = fail_dm
        self.fail_comment = fail_comment
        self.private_replies = []      # (comment_id, text)
        self.public_replies = []       # (media_id, text)
        self.dms_sent = []             # (user_id, text)

    # --- API surface used by auto_reply_links / auto_dm ----------------
    def _get(self, path, **kw):
        if path.endswith("/media"):
            return {"data": [{"id": "media-1"}]}
        if path.endswith("/comments"):
            return {"data": self.comments}
        if path.endswith("/conversations"):
            return {"data": self.conversations}
        return {"data": []}

    def _post(self, path, **kw):
        if self.fail_comment:
            raise InstagramError("comments API blocked")
        self.public_replies.append((path, kw.get("message", "")))
        return {"id": "reply-1"}

    def _post_json(self, path, body):
        rec = body.get("recipient", {})
        text = (body.get("message") or {}).get("text", "")
        if "comment_id" in rec:
            if self.fail_dm:
                raise InstagramError("token lacks instagram_manage_messages")
            self.private_replies.append((rec["comment_id"], text))
        else:
            if self.fail_dm:
                raise InstagramError("24h window closed")
            self.dms_sent.append((rec.get("id"), text))
        return {"message_id": f"m{len(self.private_replies)}"}

    def private_reply_to_comment(self, comment_id, text):
        try:
            self._post_json("messages", {"recipient": {"comment_id": comment_id},
                                         "message": {"text": text}})
            return True
        except InstagramError:
            return False

    def message_user(self, user_id, text):
        try:
            self._post_json("messages", {"recipient": {"id": user_id},
                                         "message": {"text": text}})
            return True
        except InstagramError:
            return False

    def auto_reply_links(self, **kw):
        return InstagramAPI.auto_reply_links(self, **kw)

    def auto_dm(self, **kw):
        return InstagramAPI.auto_dm(self, **kw)


def _engine(tmp: Path) -> Engine:
    cfg = Config(raw={
        "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
        "instagram": {
            "enabled": True, "private_dm": True, "public_reply": True,
            "reply_delay_seconds": 0,        # keep tests fast
            "triggers": {"link": "🔥 {title} — only {price}!",
                         "price": "💰 {title} is just {price}.",
                         "buy": "🛒 Here is {title} — official store link.",
                         "chahiye": "😍 Sending {title} — link below!"},
        },
        "affiliate": {"meesho_affid": "affid123"},
        "posting": {"platform_order": ["instagram"]},
    })
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return Engine(cfg, DB(cfg.db_path))


def _seed_posted(eng: Engine, title="Kitchen Storage Organizer Rack",
                 price="399") -> int:
    pid = eng.db.add_product(source="meesho", url=f"https://m/{title[:5]}/p/1k1b6",
                             affiliate_url="https://m/x?affid123", title=title,
                             price=price, status="posted")
    eng.db.add_post(product_id=pid, board_id="b", pin_id="pin1",
                    ig_post_id="media-1", status="posted",
                    posted_at=datetime.now(timezone.utc).isoformat(
                        timespec="seconds"))
    return pid


class TestCommentToDM(unittest.TestCase):
    def test_comment_triggers_private_dm_with_real_link(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg,
                          comments=[{"id": "c1", "text": "LINK please 🙏",
                                     "username": "buyer1"}])
            eng.ig = fake
            answered = fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                            dm_for=eng._ig_comment_dm,
                                            is_answered=eng.db.ig_comment_seen,
                                            mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(answered, 1)
            self.assertEqual(len(fake.private_replies), 1)
            cid, text = fake.private_replies[0]
            self.assertEqual(cid, "c1")
            self.assertIn("Kitchen Storage Organizer Rack", text)
            self.assertIn("399", text)
            self.assertTrue(text.lower().count("http") >= 1)   # a real link
            self.assertIn("affid123", text)                    # our tracking
            self.assertEqual(len(fake.public_replies), 1)      # engagement too

    def test_same_comment_is_never_messaged_twice(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg,
                          comments=[{"id": "c1", "text": "link",
                                     "username": "buyer1"}])
            eng.ig = fake
            for _ in range(3):     # three polling cycles over the same comment
                fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                      dm_for=eng._ig_comment_dm,
                                      is_answered=eng.db.ig_comment_seen,
                                      mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(len(fake.private_replies), 1)

    def test_ledger_persists_across_processes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            eng = _engine(tmp)
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c9", "text": "price?"}])
            eng.ig = fake
            fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                  dm_for=eng._ig_comment_dm,
                                  is_answered=eng.db.ig_comment_seen,
                                  mark_answered=eng.db.mark_ig_comment)
            self.assertTrue(DB(eng.cfg.db_path).ig_comment_seen("c9"))

    def test_dm_scope_missing_falls_back_to_public_reply(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c1", "text": "link"}], fail_dm=True)
            eng.ig = fake
            answered = fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                            dm_for=eng._ig_comment_dm,
                                            is_answered=eng.db.ig_comment_seen,
                                            mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(answered, 1)                 # still answered
            self.assertEqual(fake.private_replies, [])
            self.assertEqual(len(fake.public_replies), 1)  # via the comment

    def test_private_dm_can_be_switched_off(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            eng.cfg.raw["instagram"]["private_dm"] = False
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c1", "text": "link"}])
            eng.ig = fake
            fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                  dm_for=eng._ig_comment_dm,
                                  is_answered=eng.db.ig_comment_seen,
                                  mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(fake.private_replies, [])
            self.assertEqual(len(fake.public_replies), 1)

    def test_public_reply_can_be_switched_off_dm_still_goes(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            eng.cfg.raw["instagram"]["public_reply"] = False
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c1", "text": "link"}])
            eng.ig = fake
            fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                  dm_for=eng._ig_comment_dm,
                                  is_answered=eng.db.ig_comment_seen,
                                  mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(len(fake.private_replies), 1)
            self.assertEqual(fake.public_replies, [])

    def test_non_trigger_comment_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c1", "text": "nice post 😍"}])
            eng.ig = fake
            answered = fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                            dm_for=eng._ig_comment_dm,
                                            is_answered=eng.db.ig_comment_seen,
                                            mark_answered=eng.db.mark_ig_comment)
            self.assertEqual(answered, 0)
            self.assertEqual(fake.private_replies, [])

    def test_hindi_trigger_words_work(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            for word in ("link chahiye", "price kitna hai", "buy karna hai"):
                fake = FakeIG(cfg=eng.cfg, comments=[{"id": f"c-{word}", "text": word}])
                eng.ig = fake
                fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                      dm_for=eng._ig_comment_dm,
                                      is_answered=eng.db.ig_comment_seen,
                                      mark_answered=eng.db.mark_ig_comment)
                self.assertEqual(len(fake.private_replies), 1, word)
                self.assertIn("Buy here", fake.private_replies[0][1], word)

    def test_api_errors_never_raise(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, comments=[{"id": "c1", "text": "link"}],
                          fail_dm=True, fail_comment=True)
            eng.ig = fake
            self.assertEqual(
                fake.auto_reply_links(reply_for=eng._ig_reply_for,
                                      dm_for=eng._ig_comment_dm,
                                      is_answered=eng.db.ig_comment_seen,
                                      mark_answered=eng.db.mark_ig_comment), 0)

    def test_dm_text_uses_product_behind_that_media(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng, title="Women Cotton Kurta Set", price="599")
            text = eng._ig_comment_dm("media-1", "price")
            self.assertIn("Women Cotton Kurta Set", text)
            self.assertIn("599", text)
            self.assertIn("Buy here", text)

    def test_dm_for_unknown_media_is_honest(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            self.assertEqual(eng._ig_comment_dm("ghost-media", "link"), "")


class TestKeywordDMs(unittest.TestCase):
    def test_dm_answer_matches_product_words(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            _seed_posted(eng)
            fake = FakeIG(cfg=eng.cfg, conversations=[{
                "messages": {"data": [
                    {"from": {"id": "user-77"},
                     "text": "kitchen organizer price?"},
                ]}}])
            eng.ig = fake
            sent = fake.auto_dm(reply_for=eng._ig_dm_for)
            self.assertEqual(sent, 1)
            uid, text = fake.dms_sent[0]
            self.assertEqual(uid, "user-77")
            self.assertIn("Kitchen Storage Organizer", text)
            self.assertIn("http", text.lower())

    def test_our_own_last_message_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            eng = _engine(Path(d))
            fake = FakeIG(cfg=eng.cfg, conversations=[{
                "messages": {"data": [
                    {"from": {"id": "12345"}, "text": "link"},
                ]}}])
            eng.ig = fake
            fake.auto_dm(reply_for=eng._ig_dm_for)
            self.assertEqual(fake.dms_sent, [])


if __name__ == "__main__":
    unittest.main()
