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

    def test_synthesis_effort_is_validated(self) -> None:
        self.assertEqual(build({}).synthesis_effort, "medium")
        self.assertIsNone(build({"council": {"synthesis_effort": None}}).synthesis_effort)
        self.assertEqual(build({"council": {"synthesis_effort": "HIGH"}}).synthesis_effort, "high")
        with self.assertRaises(ValueError):
            build({"council": {"synthesis_effort": "sometimes"}})

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
        # Nothing is packaged, so the tests bring their own house rules. The
        # sentinel is deliberately not a real rule from anyone's machine.
        self.house = root / "house.md"
        self.house.write_text("Chrome only through the wrapper.", encoding="utf-8")
        self.cfg = a_config(
            hugin_dirs=[root], projects_root=root / "projs", house_prompt_path=self.house
        )
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

    def test_synthesis_steps_the_effort_down_and_gathering_does_not(self) -> None:
        self.council.gather()
        secretary = next(s for s in self.made if s.model == "sec")
        self.assertIsNone(secretary.effort)  # "claude:sec" carries no effort
        self.council.round("How should I do this?")
        self.assertEqual(secretary.effort, self.cfg.synthesis_effort)

    def test_synthesis_effort_none_leaves_the_secretary_alone(self) -> None:
        self.council.cfg = a_config(
            hugin_dirs=self.cfg.hugin_dirs,
            projects_root=self.cfg.projects_root,
            synthesis_effort=None,
        )
        self.council.round("How should I do this?")
        secretary = next(s for s in self.made if s.model == "sec")
        self.assertIsNone(secretary.effort)

    def test_the_secretary_is_told_the_house_rules_and_the_members_are_not(self) -> None:
        # The hazards are only reachable from a shell, and only the secretary has
        # one. A member that read them could act on none of them and would pay
        # for the tokens in every round.
        self.council.gather()
        secretary = next(s for s in self.made if s.model == "sec")
        self.assertIn("Chrome only through the wrapper.", secretary.sent[0])

        self.council.round("How should I do this?")
        member_prompt = (self.archive.round_dir(1) / arc.MEMBER_PROMPT).read_text()
        self.assertNotIn("Chrome only through the wrapper.", member_prompt)

    def test_the_serial_channel_gets_them_too(self) -> None:
        self.council.serial("what does this term mean?")
        secretary = next(s for s in self.made if s.model == "sec")
        self.assertIn("Chrome only through the wrapper.", secretary.sent[0])

    def test_no_placeholder_survives_into_a_prompt(self) -> None:
        self.council.gather()
        self.council.serial("hi")
        for session in self.made:
            for prompt in getattr(session, "sent", []):
                self.assertNotIn("{{", prompt)

    def test_an_unconfigured_install_gets_no_house_block_and_no_error(self) -> None:
        # House rules are per-machine, so none are packaged. Someone else's
        # standing facts would read as fact and be wrong, which is worse than
        # silence -- but the tool still has to run.
        self.council.cfg = a_config(
            hugin_dirs=self.cfg.hugin_dirs, projects_root=self.cfg.projects_root
        )
        self.council.gather()
        secretary = next(s for s in self.made if s.model == "sec")
        self.assertNotIn("Chrome only through the wrapper.", secretary.sent[0])
        self.assertNotIn("{{", secretary.sent[0])

    def test_a_configured_house_path_that_is_missing_is_loud(self) -> None:
        # The quiet fallback above must not swallow a typo in council.yaml: that
        # would drop the rules without saying so, which is exactly the failure it
        # is there to prevent.
        self.council.cfg = a_config(
            hugin_dirs=self.cfg.hugin_dirs,
            projects_root=self.cfg.projects_root,
            house_prompt_path=Path(self.tmp.name) / "typo.md",
        )
        with self.assertRaises(FileNotFoundError):
            self.council.gather()

    def test_first_round_asks_for_breadth_and_archives_every_answer_raw(self) -> None:
        self.council.round("How should I do this?")
        round_dir = self.archive.round_dir(1)
        prompt = (round_dir / arc.MEMBER_PROMPT).read_text()
        self.assertIn("without seeing the others", prompt)
        self.assertIn("one of 2 participants", prompt)
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
        self.assertIn("you do not decide", prompt)

    def test_second_round_carries_the_synthesis_and_forbids_deference(self) -> None:
        self.council.round("first")
        self.council.round("second")
        prompt = (self.archive.round_dir(2) / arc.MEMBER_PROMPT).read_text()
        self.assertIn("Hold your own view", prompt)
        self.assertIn("second", prompt)

    def test_previous_synthesis_is_handed_to_the_secretary(self) -> None:
        self.council.round("first")
        self.council.round("second")
        prompt = (self.archive.round_dir(2) / arc.SECRETARY_PROMPT).read_text()
        self.assertIn("## The synthesis so far", prompt)
        # And the members are not told to number or tag anything.
        self.assertNotIn("V1", prompt)
        self.assertNotIn("number", prompt.split("## The synthesis so far")[0].lower().replace("do not number", ""))

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
        self.assertIn("This is not that\nrole", serial.sent[0])
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


class AbortTests(unittest.TestCase):
    """Ctrl-C during a round: members cancelled, arrivals kept, council intact."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = a_config(hugin_dirs=[root], projects_root=root / "projs")
        self.archive = arc.Archive.create(root / "state", "How should I do this?")
        self.ctx = context.resolve(self.cfg, root)
        self.council = Council(cfg=self.cfg, ctx=self.ctx, archive=self.archive)
        self.made: list[FakeSession] = []

        def fake_session(spec, read_only, key=None):
            provider, _, rest = spec.partition(":")
            model, _, _ = rest.partition(":")
            session = FakeSession(provider=provider, cwd=self.ctx.primary, model=model, read_only=read_only)
            self.made.append(session)
            return session

        patcher = patch.object(Council, "_session", side_effect=fake_session, autospec=False)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.council.attach(["claude:a", "codex:b"], "claude:sec")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ctrl_c_cancels_the_members_keeps_arrivals_and_marks_the_round(self) -> None:
        fast, slow = self.council.members

        def interrupted(prompt, timeout=900):
            raise KeyboardInterrupt

        with patch.object(slow, "send", side_effect=interrupted), patch.object(
            fast, "cancel"
        ) as cancel_fast, patch.object(slow, "cancel") as cancel_slow:
            with self.assertRaises(KeyboardInterrupt):
                self.council.round("first")
        cancel_fast.assert_called_once()
        cancel_slow.assert_called_once()
        round_dir = self.archive.round_dir(1)
        self.assertTrue((round_dir / arc.answer_filename(fast.label)).exists())
        self.assertFalse((round_dir / arc.answer_filename(slow.label)).exists())
        self.assertIn("1 of 2", (round_dir / arc.ABORTED).read_text())
        self.assertFalse((round_dir / arc.SYNTHESIS).exists())
        # The round counted, and the next one is a fresh directory.
        self.assertEqual(self.archive.rounds, 1)
        self.assertIsNone(self.archive.latest_synthesis())
        self.council.round("second")
        self.assertTrue((self.archive.round_dir(2) / arc.SYNTHESIS).exists())


class NotifyConfigTests(unittest.TestCase):
    def test_notify_after_defaults_and_can_be_switched_off(self) -> None:
        self.assertEqual(build({"vault_path": "/v"}).notify_after, 30)
        self.assertEqual(build({"vault_path": "/v", "council": {"notify_after": 0}}).notify_after, 0)
        self.assertEqual(build({"vault_path": "/v", "council": {"notify_after": 90}}).notify_after, 90)


class AnswersTests(unittest.TestCase):
    def test_answers_are_read_back_lettered_and_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = arc.Archive.create(Path(tmp), "q")
            rd = archive.open_round()
            (rd / arc.answer_filename("codex:b")).write_text(
                "<!-- Participant B = codex:b -->\n\nsecond\n", encoding="utf-8"
            )
            (rd / arc.answer_filename("claude:a")).write_text(
                "<!-- Participant A = claude:a -->\n\nfirst\n", encoding="utf-8"
            )
            answers = archive.answers()
            self.assertEqual([(a.anon, a.label, a.text) for a in answers], [
                ("Participant A", "claude:a", "first"),
                ("Participant B", "codex:b", "second"),
            ])
            self.assertEqual(archive.answers(0), [])
            self.assertEqual(archive.answers(7), [])


class CritiqueTests(CouncilFlowTests):
    """Reuses the flow fixture (two fake members, a fake secretary), which also
    reruns its tests under this name; cheap, and it keeps one fixture."""

    def test_each_member_sees_the_others_answers_and_not_its_own(self) -> None:
        a, b = self.council.members
        a.reply, b.reply = "answer from a", "answer from b"
        self.council.round("first")
        a.reply = b.reply = "a review"
        self.council.critique("the cost estimates")
        prompt_a, prompt_b = a.sent[-1], b.sent[-1]
        self.assertIn("answer from b", prompt_a)
        self.assertNotIn("answer from a", prompt_a)
        self.assertIn("answer from a", prompt_b)
        self.assertNotIn("answer from b", prompt_b)
        self.assertIn("### Participant B", prompt_a)
        self.assertIn("the cost estimates", prompt_a)
        self.assertNotIn("{{", prompt_a)
        rd = self.archive.round_dir(2)
        self.assertTrue((rd / "prompt-members-A.md").exists())
        self.assertTrue((rd / "prompt-members-B.md").exists())
        self.assertTrue((rd / arc.SYNTHESIS).exists())
        secretary_prompt = (rd / arc.SECRETARY_PROMPT).read_text()
        self.assertIn("reviewed each other", secretary_prompt)
        self.assertIn("the cost estimates", secretary_prompt)

    def test_a_critique_needs_two_answers_to_review(self) -> None:
        from hugin.session import SessionError

        with self.assertRaises(SessionError):
            self.council.critique()
        a, _ = self.council.members
        self.council.round("first")
        # Knock one answer out on disk: only one left to review.
        (self.archive.round_dir(1) / arc.answer_filename(a.label)).write_text(
            f"<!-- Participant A = {a.label} -->\n\n(failed: boom)\n"
        )
        with self.assertRaises(SessionError):
            self.council.critique()
