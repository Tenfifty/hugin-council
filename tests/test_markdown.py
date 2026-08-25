from __future__ import annotations

import unittest

from hugin_council.markdown import RESET, THEME, render


class RenderTests(unittest.TestCase):
    def test_colour_off_is_the_identity(self) -> None:
        text = "# H\n\n**bold** and `code`\n"
        self.assertEqual(render(text, colour=False), text)

    def test_headings_get_their_level_colour_and_lose_the_hashes(self) -> None:
        out = render("## Karta", colour=True)
        self.assertEqual(out, f"{THEME.h2}Karta{RESET}")

    def test_heading_renders_inline_spans_and_keeps_its_colour(self) -> None:
        out = render("### V1 - pad to `runda-01.md`", colour=True)
        self.assertIn(THEME.code, out)
        self.assertNotIn("`", out)
        # The colour is re-armed after the code span, so the tail is not plain.
        self.assertTrue(out.endswith(RESET))
        self.assertGreater(out.count(THEME.h3), 1)

    def test_emphasis_inside_a_code_span_is_left_alone(self) -> None:
        out = render("use `a**b**c` here", colour=True)
        self.assertIn("a**b**c", out)
        self.assertNotIn(THEME.bold, out)

    def test_fenced_block_is_not_parsed_as_markdown(self) -> None:
        out = render("```\n# not a heading\n- not a bullet\n```", colour=True)
        self.assertIn("# not a heading", out)
        self.assertNotIn(THEME.h1, out)
        self.assertNotIn("•", out)

    def test_bullets_and_numbered_options_keep_their_indent(self) -> None:
        out = render("  - one\n1. two", colour=True)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("  "))
        self.assertIn("•", lines[0])
        self.assertIn("1.", lines[1])

    def test_link_shows_text_and_target(self) -> None:
        out = render("see [docs](http://x/y)", colour=True)
        self.assertIn("docs", out)
        self.assertIn("http://x/y", out)

    def test_rule_becomes_a_line(self) -> None:
        self.assertIn("─", render("---", colour=True))

    def test_no_placeholder_leaks_into_the_output(self) -> None:
        out = render("`a` **b** `c` [d](e)", colour=True)
        self.assertNotIn("\x00", out)


if __name__ == "__main__":
    unittest.main()
