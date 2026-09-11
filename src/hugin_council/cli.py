"""The command line, and the two-mode loop.

You tab between council and serial. Serial is for asking the secretary what a
term means or for having it do something with side effects, and it never reaches
the members. The mode is in the prompt itself, not only in a status line,
because a mis-addressed turn is the obvious failure mode of a two-mode
interface: a question meant for the secretary that goes to three members costs
a round, and one meant for the council that goes to the secretary is lost.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from hugin.session import Event, SessionError, Usage

from . import archive as arc
from . import context
from .config import CouncilConfig, load
from .council import SECRETARY_COUNCIL, SECRETARY_SERIAL, Council

CRITIQUE = "critique"
from .markdown import render
from .tui import (
    COUNCIL,
    SERIAL,
    MemberLine,
    Shell,
    Status,
    ask_prompt,
    edit_text,
    event_line,
    notify,
    short_model,
)

HELP = """\
Modes
  Tab                 switch between council and serial
  /council, /c        talk to the members (broadcast, then synthesis)
  /serial, /s         talk to the secretary only; never reaches the members
  > <text>            one-shot to the secretary without leaving council mode

Typing
  Enter               send;  Alt-Enter or Ctrl-J for a new line
  Tab                 completes a half-typed /command; switches mode otherwise
  /edit [text]        write the turn in $EDITOR instead
  Ctrl-C              break off the round in progress; the council survives

Commands
  /critique [focus]   members review each other's last answers, then synthesis
  /promote <text>     carry something from serial into the next broadcast
  /solo [text]        dismiss the members for good; text records the outcome
  /brief              print the gathered brief
  /map                print the latest synthesis
  /answers [N]        print every raw answer of round N (default: latest)
  /answer A [N]       print one member's raw answer, by letter
  /status             roster, rounds, where the archive is
  /help, /quit
"""


def _resolve(cfg: CouncilConfig, args: argparse.Namespace) -> tuple[list[str], str]:
    specs = cfg.roster_specs(args.roster)
    for extra in args.member or []:
        specs.append(extra)
    secretary = args.secretary or cfg.secretary
    parts = secretary.split(":")
    provider = parts[0]
    model = args.secretary_model or (parts[1] if len(parts) > 1 else "")
    effort = args.secretary_effort or (parts[2] if len(parts) > 2 else "")
    secretary = ":".join([p for p in (provider, model, effort) if p])
    return specs, secretary


def _watch(event: Event) -> None:
    print(event_line(event.kind, event.name, event.detail, colour=_colour()), flush=True)


def _build(
    cfg: CouncilConfig,
    archive: arc.Archive,
    args: argparse.Namespace,
    ctx: context.WorkContext | None = None,
) -> Council:
    ctx = ctx or context.resolve(cfg, Path.cwd())
    council = Council(
        cfg=cfg,
        ctx=ctx,
        archive=archive,
        on_note=lambda t: print(f"  ({t})", flush=True),
        on_event=_watch,
    )
    specs, secretary = _resolve(cfg, args)
    council.attach(specs, secretary)
    return council


def _colour() -> bool:
    return sys.stdout.isatty()


def _show(body: str) -> None:
    print(render(body.rstrip(), colour=_colour()))


def _print_block(title: str, body: str | None) -> None:
    if not body:
        print(f"(no {title} yet)")
        return
    print()
    _show(body)
    print()


def _print_answers(council: Council, words: list[str]) -> None:
    """``/answers [N]`` and ``/answer A [N]``.

    The synthesis is the secretary's reading of the answers; this is the way
    to check it against what a member actually wrote, which is the point of
    archiving the answers raw.
    """
    letter = None
    number = None
    for word in words:
        if word.isdigit():
            number = int(word)
        elif len(word) == 1 and word.isalpha():
            letter = word.upper()
        else:
            print("  /answers [N]   /answer A [N]")
            return
    number = number or council.archive.rounds
    answers = council.archive.answers(number)
    if letter:
        answers = [a for a in answers if a.anon.endswith(letter)]
    if not answers:
        who = f"from {letter} " if letter else ""
        print(f"  no answers {who}in round {number}" if number else "  no rounds yet")
        return
    for answer in answers:
        anon = answer.anon or "?"
        print()
        _show(f"## {anon} · {short_model(answer.label)} · round {number}\n\n{answer.text}")
    print()


def _where(ctx: context.WorkContext) -> str:
    return ctx.primary.name or str(ctx.primary)


def _status(council: Council, mode: str) -> Status:
    states = council.session_states()
    key = SECRETARY_SERIAL if mode == SERIAL else SECRETARY_COUNCIL
    active = states.get(key) or states.get(SECRETARY_COUNCIL) or {}
    usage = Usage.from_dict(active["last_usage"]) if active.get("last_usage") else None

    members = []
    for session in council.members:
        member_usage = session.last_usage
        members.append(
            MemberLine(
                anon=council.anon_map[session.label],
                name=short_model(session.model),
                read=member_usage.read_tokens if member_usage else 0,
                turns=session.turns,
            )
        )
    return Status(
        mode=mode,
        slug=council.archive.slug,
        where=_where(council.ctx),
        rounds=council.archive.rounds,
        secretary_read=usage.read_tokens if usage else 0,
        cost_usd=council.total_cost_usd(),
        calls=council.calls_by_provider(),
        members=members,
        dismissed=council.dismissed,
    )


def _loop(council: Council) -> int:
    if council.dismissed:
        print("This council was adjourned; continuing in serial.")
    print(f"{council.archive.slug}  ({len(council.members)} members)   Tab switches mode, /help")

    def toggle(current: str) -> str:
        if council.dismissed:
            return SERIAL
        return SERIAL if current == COUNCIL else COUNCIL

    shell = Shell(status=lambda mode: _status(council, mode), toggle=toggle)
    shell.mode = SERIAL if council.dismissed else COUNCIL

    while True:
        try:
            line = shell.prompt().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        mode = shell.mode
        if not line:
            continue

        if line in ("/quit", "/q", "/exit"):
            return 0
        if line in ("/help", "/h", "/?"):
            print(HELP)
            continue
        if line in ("/council", "/c"):
            if council.dismissed:
                print("The members were dismissed. Start a new council.")
                continue
            shell.mode = COUNCIL
            continue
        if line in ("/serial", "/s"):
            shell.mode = SERIAL
            continue
        if line == "/status":
            print(f"  archive:   {council.archive.root}")
            print(f"  rounds:    {council.archive.rounds}")
            print(f"  secretary: {council.secretary_spec}")
            for session in council.members:
                anon = council.anon_map[session.label]
                print(f"  member:    {session.label:<32} {anon}  turns={session.turns}")
            continue
        if line == "/brief":
            _print_block("brief", council.archive.brief)
            continue
        if line == "/map":
            _print_block("synthesis", council.archive.latest_synthesis())
            continue
        if line == "/answers" or line.startswith("/answers ") or line.startswith("/answer "):
            _print_answers(council, line.split()[1:])
            continue
        if line == "/critique" or line.startswith("/critique "):
            if council.dismissed:
                print("The members were dismissed. Start a new council.")
                continue
            _run_turn(council, CRITIQUE, line[len("/critique"):].strip())
            continue
        if line.startswith("/promote"):
            text = line[len("/promote"):].strip()
            if not text:
                print("  /promote <text>  (what should the members be told?)")
                continue
            council.promote(text)
            print("  will be carried into the next broadcast")
            continue
        if line.startswith("/solo"):
            outcome = line[len("/solo"):].strip()
            if not outcome:
                print("What did you land on, and briefly why?")
                try:
                    outcome = input("outcome> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    continue
            if not outcome:
                print("  nothing recorded, council left open")
                continue
            pending = council.archive.state.get("promoted") or []
            if pending:
                # Otherwise the promoted text is orphaned in silence: the
                # members it was meant for are about to be dismissed.
                print(f"  note: {len(pending)} promoted item(s) will never be broadcast")
            council.solo(outcome)
            shell.mode = SERIAL
            print("  members dismissed, outcome recorded, continuing in serial")
            continue
        if line == "/edit" or line.startswith("/edit "):
            line = edit_text(line[len("/edit"):].strip())
            if not line:
                print("  nothing written, nothing sent")
                continue
        elif line.startswith("/"):
            print(f"  unknown command: {line.split()[0]}  (/help)")
            continue

        one_shot = line.startswith(">")
        text = line[1:].strip() if one_shot else line
        target = SERIAL if (one_shot or mode == SERIAL) else COUNCIL
        _run_turn(council, target, text)
    return 0


def _run_turn(council: Council, target: str, text: str) -> bool:
    """One turn to the secretary or the council, with the two exits a long
    wait needs: Ctrl-C brings the prompt back with the council intact, and a
    wait long enough to have looked away from ends with a notification."""
    started = time.monotonic()
    if target == SERIAL:
        what = "secretary"
    elif target == CRITIQUE:
        what = f"critique (round {council.archive.rounds + 1})"
    else:
        what = f"round {council.archive.rounds + 1}"
    try:
        if target == SERIAL:
            print()
            _show(council.serial(text))
        elif target == CRITIQUE:
            _show(council.critique(text))
        else:
            _show(council.round(text))
    except SessionError as exc:
        print(f"  failed: {exc}", file=sys.stderr)
        _notify(council, f"{what} failed", started)
        return False
    except KeyboardInterrupt:
        print(f"\n  {what} broken off after {time.monotonic() - started:.0f}s; the council is intact")
        return False
    _notify(council, f"{what} done", started)
    return True


def _notify(council: Council, text: str, started: float) -> None:
    after = council.cfg.notify_after
    elapsed = time.monotonic() - started
    if after and elapsed >= after:
        notify(f"{text} in {elapsed:.0f}s  ({council.archive.slug})")


def _cmd_ask(cfg: CouncilConfig, args: argparse.Namespace) -> int:
    ctx = context.resolve(cfg, Path.cwd())
    question = " ".join(args.question or []).strip()
    if not question:
        try:
            question = ask_prompt(_where(ctx)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
    if not question:
        print("nothing to ask", file=sys.stderr)
        return 2
    archive = arc.Archive.create(cfg.state_dir, question)
    council = _build(cfg, archive, args, ctx)
    print(f"council {archive.slug}")
    print(f"  {council.ctx.describe()}\n")

    # Phase 1 always runs. The prompt tells the secretary the material may not
    # exist, so an empty brief that says where it looked is a valid outcome; a
    # failure is not, and is reported rather than swallowed.
    try:
        council.gather()
    except SessionError as exc:
        print(f"  gathering failed: {exc}", file=sys.stderr)
        print("  continuing without a brief")
    except KeyboardInterrupt:
        # The question is on disk; the first council> turn broadcasts it.
        print("\n  gathering broken off; continuing without a brief")
        return _loop(council)
    if not _run_turn(council, COUNCIL, question):
        # A failed or broken-off first round is not the end: the council is
        # created and `resume` would find it, so stay in it.
        print("  the question is archived; a council> turn broadcasts it")
    return _loop(council)


def _cmd_resume(cfg: CouncilConfig, args: argparse.Namespace) -> int:
    if args.slug:
        root = Path(args.slug)
        if not root.exists():
            root = cfg.state_dir / args.slug
        archive = arc.Archive.load(root)
    else:
        archive = arc.Archive.latest(cfg.state_dir)
    council = _build(cfg, archive, args)
    _print_block("synthesis", archive.latest_synthesis())
    return _loop(council)


def _cmd_list(cfg: CouncilConfig, args: argparse.Namespace) -> int:
    found = arc.Archive.find_all(cfg.state_dir)
    if not found:
        print(f"no councils under {cfg.state_dir}")
        return 0
    for root in found:
        try:
            archive = arc.Archive.load(root)
        except (OSError, ValueError):
            continue
        mark = "adjourned" if archive.state.get("dismissed") else f"{archive.rounds} rounds"
        print(f"{root.name:<52} {mark:<12} {archive.question[:60]}")
    return 0


def _normalise(argv: list[str]) -> list[str]:
    """Insert the implicit ``ask``.

    Starting a council is what the tool is for, so bare ``hugin-council`` means
    ``ask`` and the TUI reads the question. A question given on the command line
    still works, at the cost of one ambiguity: one opening with a subcommand
    word ("list the trade-offs of ...") would be parsed as that subcommand, so a
    leading word only counts as one when what follows it fits — ``list`` takes
    nothing, ``resume`` takes at most a slug.
    """
    if argv and argv[0] in ("-h", "--help"):
        return argv
    if not argv or argv[0].startswith("-"):
        return ["ask", *argv]
    head, rest = argv[0], argv[1:]
    positional = [a for a in rest if not a.startswith("-")]
    if head == "ask":
        return argv
    if head == "list" and not positional:
        return argv
    if head == "resume" and len(positional) <= 1:
        return argv
    return ["ask", *argv]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hugin-council",
        description="Ask one question, get answers from several models, folded into one map.",
    )
    sub = parser.add_subparsers(dest="command")

    def add_roster_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--roster", help="named roster from config (default: default)")
        p.add_argument(
            "--member",
            action="append",
            metavar="PROVIDER[:MODEL[:EFFORT]]",
            help="append one member for this run; repeatable",
        )
        p.add_argument("--secretary", metavar="PROVIDER[:MODEL[:EFFORT]]")
        p.add_argument("--secretary-model")
        p.add_argument("--secretary-effort", choices=("low", "medium", "high", "xhigh", "max"))

    ask = sub.add_parser("ask", help="start a new council (the default)")
    ask.add_argument("question", nargs="*", help="optional; asked in the TUI if omitted")
    add_roster_flags(ask)
    ask.set_defaults(func=_cmd_ask)

    resume = sub.add_parser("resume", help="resume the latest council, or one by slug")
    resume.add_argument("slug", nargs="?")
    add_roster_flags(resume)
    resume.set_defaults(func=_cmd_resume)

    listing = sub.add_parser("list", help="list councils")
    listing.set_defaults(func=_cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(_normalise(list(argv if argv is not None else sys.argv[1:])))
    for attr in ("question", "roster", "member", "secretary", "secretary_model", "secretary_effort"):
        if not hasattr(args, attr):
            setattr(args, attr, None)
    try:
        cfg = load()
    except (OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    try:
        return int(args.func(cfg, args))
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
