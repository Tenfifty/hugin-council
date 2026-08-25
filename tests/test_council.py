from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hugin.session import Session, Turn, Usage

from hugin_council import archive as arc
from hugin_council import context
from hugin_council.config import CouncilConfig, build
from hugin_council.council import Council, anon_labels, fill


def a_config(**kwargs) -> CouncilConfig:
    return CouncilConfig(**kwargs)


class ConfigTests(unittest.TestCase):
    def test_rosters_and_secretary_come_from_the_council_block(self) -> None:
        cfg = build(
            {
                "language": "sv",
                "vault_path": "/vault",
                "council": {
                    "secretary": "codex:gpt-5.5:xhigh",
                    "rosters": {"wide": ["claude", "agy:gemini-3.1-pro-high"]},
                    "roster": "wide",
                },
            }
        )
        self.assertEqual(cfg.language, "sv")
        self.assertEqual(cfg.secretary, "codex:gpt-5.5:xhigh")
        self.assertEqual(cfg.roster_specs(), ["claude", "agy:gemini-3.1-pro-high"])

    def test_hugin_dirs_default_to_the_vault_alone(self) -> None:
        # Not the parent: on a setup where vault_path is already the top level
        # that would drag in the whole of ~/Documents.
        cfg = build({"vault_path": "/home/x/Documents/hugin"})
        self.assertEqual(cfg.hugin_dirs, [Path("/home/x/Documents/hugin")])

    def test_language_name_is_spelled_out_for_the_prompts(self) -> None:
        self.assertEqual(build({"language": "sv"}).language_name, "Swedish")
        self.assertEqual(build({}).language_name, "English")

    def test_unknown_or_empty_roster_is_an_error(self) -> None:
        cfg = build({"council": {"rosters": {"default": ["claude"], "empty": []}}})
        with self.assertRaises(ValueError):
            cfg.roster_specs("nope")
        with self.assertRaises(ValueError):
            cfg.roster_specs("empty")


class ContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projs = self.root / "projs"
        self.vault = self.root / "hugin" / "memory"
        self.vault.mkdir(parents=True)
        (self.projs / "someproj" / "deep").mkdir(parents=True)
        self.cfg = a_config(
            projects_root=self.projs, hugin_dirs=[self.vault, self.vault.parent]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_inside_a_repo_the_repo_is_primary_and_hugin_rides_along(self) -> None:
        ctx = context.resolve(self.cfg, self.projs / "someproj" / "deep")
        self.assertEqual(ctx.repo, (self.projs / "someproj").resolve())
        self.assertEqual(ctx.primary, ctx.repo)
        self.assertIn(self.vault, ctx.extra)
        self.assertFalse(ctx.hint_only)
        self.assertIn("is the subject", ctx.describe())

    def test_projects_root_itself_is_not_a_repo(self) -> None:
        self.assertIsNone(context.resolve(self.cfg, self.projs).repo)

    def test_elsewhere_hugin_is_primary_and_cwd_is_only_a_hint(self) -> None:
        elsewhere = self.root / "somewhere"
        elsewhere.mkdir()
        ctx = context.resolve(self.cfg, elsewhere)
        self.assertEqual(ctx.primary, self.vault)
        self.assertIn(elsewhere, ctx.extra)
        self.assertIn("weak hint", ctx.describe())


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_slugs_the_question_and_never_collides(self) -> None:
        first = arc.Archive.create(self.state, "Vad ska jag göra?", today=date(2026, 8, 25))
        second = arc.Archive.create(self.state, "Vad ska jag göra?", today=date(2026, 8, 25))
        self.assertEqual(first.slug, "2026-08-25-vad-ska-jag-göra")
        self.assertEqual(second.slug, "2026-08-25-vad-ska-jag-göra-2")
        self.assertEqual(arc.Archive.load(first.root).question, "Vad ska jag göra?")

    def test_rounds_get_their_own_directory_and_are_never_overwritten(self) -> None:
        archive = arc.Archive.create(self.state, "q")
        first = archive.open_round()
        (first / arc.SYNTHESIS).write_text("map one", encoding="utf-8")
        second = archive.open_round()
        (second / arc.SYNTHESIS).write_text("map two", encoding="utf-8")
        self.assertNotEqual(first, second)
        self.assertEqual(archive.rounds, 2)
        self.assertEqual(archive.latest_synthesis(), "map two")
        self.assertTrue((first / arc.SYNTHESIS).exists())

    def test_latest_synthesis_skips_a_round_that_produced_none(self) -> None:
        archive = arc.Archive.create(self.state, "q")
        first = archive.open_round()
        (first / arc.SYNTHESIS).write_text("only map", encoding="utf-8")
        archive.open_round()
        self.assertEqual(archive.latest_synthesis(), "only map")

    def test_sessions_survive_a_reload(self) -> None:
        archive = arc.Archive.create(self.state, "q")
        archive.put_session("member-0", {"provider": "codex", "cwd": "/x", "session_id": "abc"})
        again = arc.Archive.load(archive.root)
        self.assertEqual(again.get_session("member-0")["session_id"], "abc")

    def test_answer_filename_is_filesystem_safe(self) -> None:
        self.assertEqual(
            arc.answer_filename("claude:opus-5:high"), "answer-claude-opus-5-high.md"
        )


class FillTests(unittest.TestCase):
    def test_fill_leaves_braces_and_backticks_alone(self) -> None:
        out = fill("a {b} `c` {{X}}", X="y")
        self.assertEqual(out, "a {b} `c` y")

    def test_anon_labels_are_letters(self) -> None:
        self.assertEqual(anon_labels(3), ["Participant A", "Participant B", "Participant C"])


_FAKE_IDS = iter(range(1, 10_000))


class FakeSession(Session):
    """Records prompts instead of running a CLI."""

    sent: list[str]
    reply: str = "reply"

    def send(self, prompt: str, timeout: int = 900) -> Turn:  # type: ignore[override]
        self.sent = getattr(self, "sent", [])
        self.sent.append(prompt)
        self.session_id = self.session_id or f"id-{next(_FAKE_IDS)}"
        self.turns += 1
        return Turn(text=self.reply, usage=Usage(), session_id=self.session_id)


class CouncilFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = a_config(hugin_dirs=[root], projects_root=root / "projs")
        self.archive = arc.Archive.create(root / "state", "How should I do this?")
        self.ctx = context.resolve(self.cfg, root)
        self.council = Council(cfg=self.cfg, ctx=self.ctx, archive=self.archive)
        self.made: list[FakeSession] = []

        def fake_session(spec, read_only, key=None):
            stored = self.archive.get_session(key) if key else None
            for existing in self.made:
                if stored and existing.session_id == stored.get("session_id"):
                    return existing
            provider, _, rest = spec.partition(":")
            model, _, effort = rest.partition(":")
            session = FakeSession(
                provider=provider or "claude",
                cwd=self.ctx.primary,
                model=model or "default",
                effort=effort or None,
                read_only=read_only,
            )
            self.made.append(session)
            return session

        patcher = patch.object(Council, "_session", side_effect=fake_session, autospec=False)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.council.attach(["claude:a", "codex:b"], "claude:sec")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_round_asks_for_options_and_archives_every_answer_raw(self) -> None:
        self.council.round("How should I do this?")
        round_dir = self.archive.round_dir(1)
        prompt = (round_dir / arc.MEMBER_PROMPT).read_text()
        self.assertIn("Give several distinct options", prompt)
        self.assertIn("council of 2", prompt)
        for label in ("claude:a", "codex:b"):
            body = (round_dir / arc.answer_filename(label)).read_text()
            self.assertIn("reply", body)
            self.assertIn(label, body)
        self.assertTrue((round_dir / arc.SYNTHESIS).exists())

    def test_synthesis_sees_anonymous_participants_not_model_names(self) -> None:
        self.council.round("q")
        prompt = (self.archive.round_dir(1) / arc.SECRETARY_PROMPT).read_text()
        self.assertIn("Participant A", prompt)
        self.assertNotIn("claude:a", prompt)
        self.assertIn("may not decide", prompt)

    def test_second_round_carries_the_synthesis_and_forbids_deference(self) -> None:
        self.council.round("first")
        self.council.round("second")
        prompt = (self.archive.round_dir(2) / arc.MEMBER_PROMPT).read_text()
        self.assertIn("Do not revise your position", prompt)
        self.assertIn("second", prompt)

    def test_previous_map_is_handed_to_the_secretary_to_keep_numbering(self) -> None:
        self.council.round("first")
        self.council.round("second")
        prompt = (self.archive.round_dir(2) / arc.SECRETARY_PROMPT).read_text()
        self.assertIn("numbering you must keep", prompt)

    def test_serial_never_reaches_the_members(self) -> None:
        self.council.round("first")
        member_turns = [len(s.sent) for s in self.made if s.model in ("a", "b")]
        self.council.serial("what does that word mean")
        after = [len(s.sent) for s in self.made if s.model in ("a", "b")]
        self.assertEqual(member_turns, after)

    def test_serial_is_a_separate_session_from_the_council_secretary(self) -> None:
        self.council.round("first")
        self.council.serial("hi")
        self.assertIsNotNone(self.archive.get_session("secretary-council"))
        self.assertIsNotNone(self.archive.get_session("secretary-serial"))
        self.assertNotEqual(
            self.archive.get_session("secretary-council")["session_id"],
            self.archive.get_session("secretary-serial")["session_id"],
        )

    def test_serial_is_seeded_once_then_not_again(self) -> None:
        self.council.serial("first")
        self.council.serial("second")
        serial = [s for s in self.made if s.read_only is False][-1]
        self.assertIn("side channel", serial.sent[0])
        self.assertNotIn("side channel", serial.sent[1])

    def test_promote_is_a_door_not_a_leak(self) -> None:
        self.council.promote("I have decided to go with V2")
        self.council.round("now what")
        prompt = (self.archive.round_dir(1) / arc.MEMBER_PROMPT).read_text()
        self.assertIn("V2", prompt)
        # consumed, so it is not repeated next round
        self.council.round("and now")
        self.assertNotIn("V2", (self.archive.round_dir(2) / arc.MEMBER_PROMPT).read_text())

    def test_a_failed_member_does_not_sink_the_round(self) -> None:
        self.council.round("first")

        def boom(prompt, timeout=900):
            raise __import__("hugin.session", fromlist=["SessionError"]).SessionError("boom")

        broken = self.council.members[0]
        with patch.object(broken, "send", side_effect=boom):
            self.council.round("second")
        body = (self.archive.round_dir(2) / arc.answer_filename(broken.label)).read_text()
        self.assertIn("failed: boom", body)
        self.assertTrue((self.archive.round_dir(2) / arc.SYNTHESIS).exists())

    def test_solo_records_the_outcome_and_dismisses(self) -> None:
        self.council.round("first")
        self.council.solo("Took V2, the archive matters more than the schema.")
        self.assertTrue(self.council.dismissed)
        self.assertIn("Took V2", self.archive.read(arc.OUTCOME_FILE))
        self.assertTrue(arc.Archive.load(self.archive.root).state["dismissed"])

    def test_roster_is_pinned_on_creation_so_a_resume_reattaches_the_same_members(self) -> None:
        self.assertEqual(self.archive.state["roster"], ["claude:a", "codex:b"])
        again = Council(cfg=self.cfg, ctx=self.ctx, archive=arc.Archive.load(self.archive.root))
        with patch.object(Council, "_session", side_effect=lambda *a, **k: FakeSession(
            provider="claude", cwd=self.ctx.primary
        )):
            again.attach(["something:else"], "claude:sec")
        self.assertEqual(len(again.members), 2)


if __name__ == "__main__":
    unittest.main()


class SoloEdgeTests(unittest.TestCase):
    def test_promoted_text_left_pending_at_solo_is_still_on_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = arc.Archive.create(Path(tmp), "q")
            council = Council(
                cfg=a_config(),
                ctx=context.resolve(a_config(hugin_dirs=[Path(tmp)]), Path(tmp)),
                archive=archive,
            )
            council.promote("never sent")
            council.solo("done")
            # solo does not consume it; the CLI warns instead, so nothing is
            # silently dropped from the archive.
            self.assertEqual(archive.state["promoted"], ["never sent"])
