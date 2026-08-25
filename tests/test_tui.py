from __future__ import annotations

import unittest

from hugin_council.tui import (
    COUNCIL,
    MODE_COUNCIL,
    MODE_SERIAL,
    SERIAL,
    MemberLine,
    Shell,
    Status,
    humanise,
)


def a_status(**kwargs) -> Status:
    base = dict(
        mode=COUNCIL,
        slug="2026-08-25-a-question",
        where="hugin-council",
        rounds=2,
        secretary_context=38_400,
        secretary_window=1_000_000,
        cost_usd=1.234,
        calls={"claude": 5, "codex": 2, "agy": 1},
        members=[],
    )
    base.update(kwargs)
    return Status(**base)


class HumaniseTests(unittest.TestCase):
    def test_scales(self) -> None:
        self.assertEqual(humanise(512), "512")
        self.assertEqual(humanise(38_400), "38k")
        self.assertEqual(humanise(1_000_000), "1.0M")


class StatusTests(unittest.TestCase):
    def test_first_line_carries_mode_slug_where_rounds_and_context(self) -> None:
        line = a_status().lines()[0]
        self.assertIn("COUNCIL", line)
        self.assertIn("2026-08-25-a-question", line)
        self.assertIn("hugin-council", line)
        self.assertIn("38k/1.0M", line)
        self.assertIn("$", line)

    def test_mode_is_coloured_differently_per_mode(self) -> None:
        self.assertIn(MODE_COUNCIL, a_status(mode=COUNCIL).lines()[0])
        self.assertIn(MODE_SERIAL, a_status(mode=SERIAL).lines()[0])

    def test_dismissed_council_says_solo_regardless_of_mode(self) -> None:
        line = a_status(mode=COUNCIL, dismissed=True).lines()[0]
        self.assertIn("SOLO", line)
        self.assertNotIn("COUNCIL", line)

    def test_quota_cell_names_agy_because_that_is_the_scarce_one(self) -> None:
        line = a_status().lines()[0]
        self.assertIn("agy", line)
        self.assertLess(line.index("agy"), line.index("codex"))

    def test_quota_cell_omits_providers_that_were_not_called(self) -> None:
        line = a_status(calls={"claude": 3}, cost_usd=0.0).lines()[0]
        self.assertNotIn("agy", line)
        self.assertNotIn("$", line)

    def test_no_calls_yet_is_said_rather_than_shown_as_zeroes(self) -> None:
        self.assertIn("no calls yet", a_status(calls={}, cost_usd=0.0).lines()[0])

    def test_absent_window_shows_the_count_without_a_denominator(self) -> None:
        line = a_status(secretary_window=None).lines()[0]
        self.assertIn("38k", line)
        self.assertNotIn("/", line.split("sec")[-1])

    def test_second_line_is_one_compact_cell_per_member(self) -> None:
        members = [
            MemberLine(anon="Participant A", name="opus-5", context=42_000, window=1_000_000, turns=2),
            MemberLine(anon="Participant B", name="gpt-5.6-sol", context=0, window=None, turns=0),
        ]
        lines = a_status(members=members).lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("opus-5", lines[1])
        self.assertIn("42k/1.0M", lines[1])
        self.assertIn("gpt-5.6-sol", lines[1])
        # A member that has not answered yet shows a dash, not a fake zero.
        self.assertIn("-", lines[1])

    def test_member_line_warns_when_the_window_is_nearly_full(self) -> None:
        from hugin_council.tui import OK, WARN

        nearly = MemberLine(anon="A", name="m", context=900_000, window=1_000_000, turns=1)
        roomy = MemberLine(anon="A", name="m", context=100_000, window=1_000_000, turns=1)
        self.assertIn(WARN, nearly.render())
        self.assertIn(OK, roomy.render())

    def test_no_member_line_when_there_are_no_members(self) -> None:
        self.assertEqual(len(a_status(members=[]).lines()), 1)


class ShellTests(unittest.TestCase):
    def test_toggle_is_wired_to_the_callback(self) -> None:
        calls = []

        def toggle(current: str) -> str:
            calls.append(current)
            return SERIAL if current == COUNCIL else COUNCIL

        shell = Shell(status=lambda mode: a_status(mode=mode), toggle=toggle)
        self.assertEqual(shell.mode, COUNCIL)
        shell.mode = shell.toggle(shell.mode)
        self.assertEqual(shell.mode, SERIAL)
        self.assertEqual(calls, [COUNCIL])


if __name__ == "__main__":
    unittest.main()


class FallbackTests(unittest.TestCase):
    def test_a_non_tty_stdin_falls_back_to_input(self) -> None:
        from unittest.mock import patch

        import hugin_council.tui as tui

        with patch.object(tui.sys, "stdin") as stdin:
            stdin.isatty.return_value = False
            shell = Shell(status=lambda mode: a_status(mode=mode), toggle=lambda c: c)
        self.assertIsNone(shell.session)
        with patch("builtins.input", return_value="typed") as fake:
            self.assertEqual(shell.prompt(), "typed")
        self.assertTrue(fake.called)
