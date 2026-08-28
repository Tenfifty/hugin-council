from __future__ import annotations

import unittest
from unittest.mock import patch

from hugin_council import tui
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
        secretary_read=38_400,
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
    def test_first_line_carries_mode_slug_where_rounds_and_tokens_read(self) -> None:
        line = a_status().lines()[0]
        self.assertIn("COUNCIL", line)
        self.assertIn("2026-08-25-a-question", line)
        self.assertIn("hugin-council", line)
        self.assertIn("38k", line)
        self.assertIn("$", line)

    def test_tokens_read_is_never_shown_over_a_window(self) -> None:
        # An agentic turn reads many times its own context, so there is no
        # honest denominator; see hugin.session.Usage.read_tokens.
        line = a_status(secretary_read=2_290_000).lines()[0]
        self.assertIn("2.3M", line)
        self.assertNotIn("/", line.split("read")[-1])

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

    def test_second_line_is_one_compact_cell_per_member(self) -> None:
        members = [
            MemberLine(anon="Participant A", name="opus-5", read=42_000, turns=2),
            MemberLine(anon="Participant B", name="gpt-5.6-sol", read=0, turns=0),
        ]
        lines = a_status(members=members).lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("opus-5", lines[1])
        self.assertIn("42k", lines[1])
        self.assertIn("gpt-5.6-sol", lines[1])
        # A member that has not answered yet shows a dash, not a fake zero.
        self.assertIn("-", lines[1])

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


class EventLineTests(unittest.TestCase):
    def test_one_line_always(self) -> None:
        line = tui.event_line("tool", "Bash", "x " * 400, colour=False)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertTrue(line.endswith("…"))

    def test_newlines_in_a_command_are_flattened(self) -> None:
        line = tui.event_line("tool", "Bash", "ls foo\n  && cat bar", colour=False)
        self.assertEqual(line, "  · Bash  ls foo && cat bar")

    def test_a_denial_is_coloured_as_a_warning(self) -> None:
        self.assertIn(tui.WARN, tui.event_line("notice", "denied", "Write"))
        self.assertNotIn(tui.WARN, tui.event_line("tool", "Read", "x"))


class AskPromptTests(unittest.TestCase):
    def test_falls_back_to_input_off_a_terminal(self) -> None:
        with patch.object(tui.sys, "stdin") as stdin:
            stdin.isatty.return_value = False
            with patch("builtins.input", return_value="  why is this slow?  ") as read:
                self.assertEqual(tui.ask_prompt("hugin").strip(), "why is this slow?")
        self.assertIn("ask", read.call_args.args[0])


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
