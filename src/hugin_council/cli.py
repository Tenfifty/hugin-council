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
from pathlib import Path

from hugin.session import SessionError

from . import archive as arc
from . import context
from .config import CouncilConfig, load
from .council import Council

COUNCIL, SERIAL = "council", "serial"

HELP = """\
Modes
  /council, /c        talk to the members (broadcast, then synthesis)
  /serial, /s         talk to the secretary only; never reaches the members
  > <text>            one-shot to the secretary without leaving council mode

Commands
  /promote <text>     carry something from serial into the next broadcast
  /solo [text]        dismiss the members for good; text records the outcome
  /brief              print the gathered brief
  /map                print the latest synthesis
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


def _build(cfg: CouncilConfig, archive: arc.Archive, args: argparse.Namespace) -> Council:
    ctx = context.resolve(cfg, Path.cwd())
    council = Council(cfg=cfg, ctx=ctx, archive=archive, on_note=lambda t: print(f"  ({t})"))
    specs, secretary = _resolve(cfg, args)
    council.attach(specs, secretary)
    return council


def _print_block(title: str, body: str | None) -> None:
    if not body:
        print(f"(no {title} yet)")
        return
    print(f"\n=== {title} ===\n")
    print(body.rstrip())
    print()


def _loop(council: Council) -> int:
    mode = SERIAL if council.dismissed else COUNCIL
    if council.dismissed:
        print("This council was adjourned; continuing in serial.")
    print(f"{council.archive.slug}  ({len(council.members)} members)   /help for commands")

    while True:
        try:
            line = input(f"\n{mode}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
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
            mode = COUNCIL
            continue
        if line in ("/serial", "/s"):
            mode = SERIAL
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
                print("Which option did you take, and briefly why?")
                try:
                    outcome = input("outcome> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    continue
            if not outcome:
                print("  nothing recorded, council left open")
                continue
            council.solo(outcome)
            mode = SERIAL
            print("  members dismissed, outcome recorded, continuing in serial")
            continue
        if line.startswith("/"):
            print(f"  unknown command: {line.split()[0]}  (/help)")
            continue

        one_shot = line.startswith(">")
        text = line[1:].strip() if one_shot else line
        target = SERIAL if (one_shot or mode == SERIAL) else COUNCIL
        try:
            if target == SERIAL:
                print()
                print(council.serial(text))
            else:
                print(council.round(text))
        except SessionError as exc:
            print(f"  failed: {exc}", file=sys.stderr)
    return 0


def _cmd_ask(cfg: CouncilConfig, args: argparse.Namespace) -> int:
    question = " ".join(args.question).strip()
    if not question:
        print("nothing to ask", file=sys.stderr)
        return 2
    archive = arc.Archive.create(cfg.state_dir, question)
    council = _build(cfg, archive, args)
    print(f"council {archive.slug}")
    print(f"  {council.ctx.describe()}\n")

    want_gather = cfg.gather if args.gather is None else args.gather
    if want_gather:
        try:
            council.gather()
        except SessionError as exc:
            print(f"  gathering failed: {exc}", file=sys.stderr)
            print("  continuing without a brief")
    try:
        print(council.round(question))
    except SessionError as exc:
        print(f"  first round failed: {exc}", file=sys.stderr)
        return 1
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

    ask = sub.add_parser("ask", help="start a new council")
    ask.add_argument("question", nargs="+")
    gather = ask.add_mutually_exclusive_group()
    gather.add_argument("--gather", dest="gather", action="store_true", default=None)
    gather.add_argument("--no-gather", dest="gather", action="store_false")
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
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    for attr in ("roster", "member", "secretary", "secretary_model", "secretary_effort", "gather"):
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
