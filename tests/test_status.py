from __future__ import annotations

import io
import unittest

from hugin_council.status import StatusLine


def lines(stream: io.StringIO) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line.strip()]


class PlainTests(unittest.TestCase):
    def test_display_name_replaces_the_spec(self) -> None:
        status = StatusLine(stream=io.StringIO())
        status.add("claude:claude-opus-5:high", "A opus-5")
        with status:
            status.start("claude:claude-opus-5:high")
            status.done("claude:claude-opus-5:high", "195 words")
        self.assertEqual(lines(status.stream)[0], "A opus-5: thinking")

    def test_summary_counts_a_failure_apart(self) -> None:
        status = StatusLine(stream=io.StringIO())
        status.add("a", "A opus-5")
        status.add("b", "B sol")
        with status:
            status.start("a")
            status.start("b")
            status.done("a", "195 words")
            status.failed("b", "boom")
        self.assertRegex(lines(status.stream)[-1], r"^1/2 answered in \d+s, 1 failed$")

    def test_summary_names_who_is_still_out(self) -> None:
        status = StatusLine(stream=io.StringIO())
        status.add("a", "A opus-5")
        status.add("b", "B sol")
        status.start("a")
        status.start("b")
        status.done("a")
        summary = status._summary(list(status.rows.values()))
        self.assertIn("1/2 answered", summary)
        self.assertIn("waiting on B sol", summary)

    def test_a_single_row_has_no_summary(self) -> None:
        # Gathering and synthesis are one row; a footer would just repeat it.
        status = StatusLine(stream=io.StringIO())
        status.add("gathering")
        status.start("gathering")
        self.assertIsNone(status._summary(list(status.rows.values())))


if __name__ == "__main__":
    unittest.main()
