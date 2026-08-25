from __future__ import annotations

import unittest

from hugin_council.cli import _normalise


class NormaliseTests(unittest.TestCase):
    def test_bare_invocation_is_ask(self) -> None:
        self.assertEqual(_normalise([]), ["ask"])

    def test_flags_only_is_ask(self) -> None:
        self.assertEqual(_normalise(["--roster", "wide"]), ["ask", "--roster", "wide"])

    def test_help_stays_top_level(self) -> None:
        self.assertEqual(_normalise(["--help"]), ["--help"])

    def test_question_on_the_command_line_still_works(self) -> None:
        self.assertEqual(_normalise(["should I?"]), ["ask", "should I?"])

    def test_explicit_subcommands_are_left_alone(self) -> None:
        for argv in (["ask", "x"], ["list"], ["resume"], ["resume", "slug-1"]):
            with self.subTest(argv=argv):
                self.assertEqual(_normalise(argv), argv)

    def test_a_question_opening_with_a_subcommand_word_is_a_question(self) -> None:
        # "list the trade-offs" is not the list subcommand, which takes nothing.
        self.assertEqual(
            _normalise(["list", "the", "trade-offs"]),
            ["ask", "list", "the", "trade-offs"],
        )
        self.assertEqual(
            _normalise(["resume", "the", "old", "thread?"]),
            ["ask", "resume", "the", "old", "thread?"],
        )


if __name__ == "__main__":
    unittest.main()
