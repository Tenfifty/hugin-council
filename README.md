# hugin-council

Ask a question once, get answers from two or three model instances that do not
see each other, and get them folded into one synthesis. Then talk on, with all
of them at once.

Part of the Hugin stack. Reads `~/.config/hugin/hugin.yaml` plus
`~/.config/hugin/council.yaml` and honours the conventions in
[`hugin`](https://github.com/Tenfifty/hugin).

## Why

Running Codex, Claude and Antigravity side by side by hand has three costs:
pasting the same question into each, re-explaining the same clarification in
every follow-up, and reading three answers that overlap by roughly 80%. This
tool removes all three without removing the disagreement, which is the part
worth having.

## Shape

| Phase | Who | What |
|-------|-----|------|
| 1 (always) | secretary | Gather: find relevant vault files, past conversations, web sources. Pointers, quotes and plain facts, each with its source. No analysis, no conclusions, no resolving contradictions. Told the material may not exist: an empty brief that says where it looked is a valid outcome. |
| 2 | members | Same question and same background to each, in parallel. Each knows it is part of a council and what that means. May look up more on its own. |
| 2b | secretary | Synthesis: fold the answers into the map. |
| serial (any time) | secretary | Tab out of the council to ask the secretary something or to do work with side effects. Never enters the council context. |
| 3 | secretary | `solo`: dismiss the members for good and continue in serial, recording what was landed on. |

Rounds repeat 2 and 2b. Your turn goes to every member verbatim.

The shape is a plain conversation with several models at once: the secretary
gathers, everyone answers, the answers are synthesised, you say what you found
useful and where to go next, everyone gets the synthesis plus your turn, and so
on. Steering is in your words. Nothing is numbered or tagged for reference, and
nobody keeps score.

`/critique` is a round with a different phase 2: each member gets the other
members' raw answers from the last round, lettered as in the synthesis, and is
asked where they are right about something it missed, where they are wrong and
why, and what it now thinks. Their own answer is not resent, since each holds
its own session. The reviews are then synthesised like answers. The members
otherwise never see each other, and this is the one deliberate exception: it is
asked for, and it happens after independent answers exist, so it cannot pull
round one towards consensus.

## Using it

```bash
hugin-council                                    # the normal way in: ask mode, type the question
hugin-council --roster wide                      # ask mode, spending the agy quota
hugin-council --member agy:gemini-3.1-pro-high   # append one member for this run
hugin-council --secretary codex:gpt-5.6-sol --secretary-effort xhigh
hugin-council resume                             # latest council
hugin-council resume 2026-08-25-some-question
hugin-council list
hugin-council "how should I do this?"            # question on argv, for scripts
```

Bare invocation means `ask`. The first question is typed into the TUI rather
than passed on the command line, so starting a council is one keystroke and the
question gets the same line editing as every later turn. Phase 1 then runs
before the members see anything.

Inside a council:

```
council> ...            broadcast to the members, then synthesis
serial>  ...            the secretary only; never reaches the members
/serial /s  /council /c switch mode
> ...                   one-shot to the secretary without leaving council mode
/critique [focus]       members review each other's last answers, then synthesis
/promote <text>         carry something from serial into the next broadcast
/solo [text]            dismiss the members for good, recording the outcome
/brief  /map  /status   print the brief, the latest synthesis, the roster
/answers [N]            every raw answer of round N (default: latest)
/answer A [N]           one member's raw answer, by letter
/edit [text]            write the turn in $EDITOR
```

Enter sends. Alt-Enter or Ctrl-J starts a new line, since a question to a
council is often several paragraphs; pasted text keeps its newlines anyway. Tab
completes a half-typed slash command and switches mode on any other line.
Ctrl-C during a round kills the members' turns, keeps whatever answers had
arrived (in the round directory, next to an `aborted.md`), and brings the
prompt back with the council intact. A turn that took longer than
`notify_after` seconds (default 30) ends with a terminal bell and a desktop
notification where `notify-send` is available.

While the secretary works, its tool calls scroll past as they happen:

```
  (gathering…)
  · Read  memory/projects/migration.md
  · Bash  pdftotext -layout "workshop-report-2026-08.pdf" -
  · Grep  migration
  (gathering done in 94s)
```

The status bar under the prompt carries the mode, the council slug, the primary
context directory, the round count, the active secretary session's context use
against its window, and what can honestly be called quota: claude's reported
cost plus a call count per provider, with agy coloured because its quota is the
scarce one. The second line is one compact cell per member: letter, model,
context against window, turns. A member that has not answered yet shows a dash
rather than a fake zero, and a provider that does not report a context window
shows the count without a denominator.

Config is `~/.config/hugin/council.yaml` over `~/.config/hugin/hugin.yaml`; see
`config.example.yaml`. It runs with no `council.yaml` at all, since the built-in
defaults carry the same rosters.

## House rules

The secretary is the one session with a shell, and it runs in whatever directory
you launched from, so it starts out knowing nothing about your machine. Point
`house_prompt_path` at a markdown file and it is pasted into the secretary's
gather and serial prompts. Nothing is packaged and nothing is guessed: another
person's standing facts would read as fact and be wrong, so an install without
this setting simply has no house block.

```yaml
council:
  house_prompt_path: ~/notes/instructions/council_house.md
```

The file is free-form prose. It is the right home for anything true about your
setup rather than about the question — including who you are, since the
secretary otherwise has no way to know and the serial prompt deliberately does
not name you:

```markdown
## House rules for this machine

You are working with Alex, who writes in Swedish and English.

### Things that break something

- `pkexec`, not `sudo`. You have no tty, so `sudo` hangs.
- Never run `git` in ~/notes: an empty `.git` sits there and fools tooling.

### Where things are

- `~/notes/` — the vault. `projects/` is one file per project.
- `~/src/` — code, one git repo per project.
```

The test for what belongs in it is below. The members never see this file: they
have no shell, so none of the hazards are reachable from where they sit.

## Decisions

### The map is prose. The archive is the structure.

The synthesis is markdown, written for a human to read. There is no schema, and
that is deliberate: designing fields for a workflow that has not been run once
means guessing what these councils actually produce. Ten or twenty real ones are
better evidence than any amount of upfront design, and a structure can be
extracted afterwards from an archive that was kept properly.

So the discipline is on the input side, not the output side. **Every member
answer is archived raw and separate, alongside the exact prompt that was sent.**
Attribution can be recovered from text later; it cannot be recovered from a
synthesis that threw the raw answers away. Filenames carry the metadata that
would otherwise have been fields:

```
~/.council/<slug>/
  question.md
  brief.md                              phase 1, if it ran
  round-01/
    prompt-members.md                   exactly what was broadcast
                                        (prompt-members-A.md etc. in a critique round)
    answer-claude-opus-5-high.md
    answer-claude-fable-5-high.md
    answer-codex-gpt-5.6-sol-high.md
    prompt-secretary.md
    synthesis.md
  round-02/ ...
  sessions.json
```

`sessions.json` stays structured, but that is machine state (provider, model,
effort, session id), not content. Structuring the state is a different thing
from structuring the synthesis.

One consequence: **`council stats` is not a feature, it is a later pass** over the archive.
  Probably better that way: what to count can be decided once it is known what
  mattered. The question it eventually answers is whether Fable 5 earns its seat
  next to Opus 5, or 3.7 Flash next to 3.1 Pro.

### The answers set the structure, not the prompt

Disagreement between members is real but rare, and it is not the axis. Usually
there are simply several possible ways forward, sometimes clearly separable and
sometimes not; sometimes the answers are one answer with variations, or a list
of facts. The synthesis prompt tells the secretary to organise by whatever is
actually there and to impose nothing, and an objection goes next to the thing it
is about, attributed. Criticism is the user's job and arrives naturally once a
track is picked.

Round 1 asks for **breadth where the question is open.** Ask three good models
what to do and they converge on the same obvious answer; ask for the distinct
ways forward with trade-offs and they do not.

Synthesis is merging, not comparison: the hard part is seeing that one member's
"briefing skill" and another's "shared context file" are the same thing under
two names, while both members' "consortium" mean different things. Merge on
mechanism, not on wording. The secretary may classify and compress but may
**not** resolve a disagreement or invent a middle position nobody proposed.

### Steering is in plain words

Your turn goes to every member verbatim, with the latest synthesis in front of
it, and that is the whole referent mechanism: "the second approach, but without
fzf" lands in three threads that framed the problem differently because all
three have just read the same synthesis. An earlier design numbered the options
(V1, V2, V3, stable across rounds) so that a turn could point at one by id. It
was ripped out on 2026-09-11: it made the prompts wordy, it assumed every
council is a choice between options, and in practice the user says what they
liked in words and narrows the questions from there. Members never upgrade or
downgrade a numbered position; they answer the next question.

### The secretary holds a session; members hold sessions; only the synthesis is on disk

The secretary is not a judge or a chair. It is one instance doing serial jobs:
gather, cluster, synthesise, write files. It does hold a session, because
context continuity makes those jobs better: merging in round three is much
easier if it remembers why it drew a boundary where it did, and gathering
can skip what it already rejected. It having continuity does not make it own the
conversation, because it has no opinions to own it with.

The synthesis stays on disk anyway, as a **checkpoint** rather than as the
secretary's state: it is needed for the archive and for the `.md` deliverable, so
it costs nothing extra, and it means a dead session or a swapped secretary model
can be rehydrated at the cost of the soft reasoning layer only.

Two consequences to plan for:

- The secretary is the largest and fastest-growing context in the system. It
  sees every member's raw answer every round plus the gathering; members see
  only their own thread plus a diff. So it hits the context ceiling first, and
  it will do so in the middle of a synthesis. Give it a deliberate **rotation**:
  at a round boundary it starts a fresh session seeded with the map plus a short
  self-written note about what it has been doing. It already writes the map, so
  this is nearly free.
- Pick the secretary model up front and do not swap it mid-council, since
  continuity is the point. Default `claude:opus-5`, chosen on context size
  (1M against the ~258k codex reports in its own session meta) and because it
  holds both secretary sessions and does the file work in the serial one.

### The secretary has two sessions, and solo is a mode not a phase

You tab between **council** and **serial**. Serial is for asking the secretary
what a term means, or for having it do something with side effects, and then
going back. Those exchanges must not enter the council context.

That is best served by giving the secretary two sessions rather than one,
because the two roles have incompatible standing instructions. The council
role's defining constraint is *may not resolve*; the serial role's whole point is
to answer. Holding both in one session means asserting and suspending that
constraint on every tab, which is the stickiness problem below made recurrent
instead of one-off.

- The **council session** does gather and synthesis, and writes only the archive,
  which is its own machine state.
- The **serial session** is a general assistant, seeded from the archive
  (question, brief, latest synthesis) and re-seeded with the newest synthesis
  when tabbed into after further rounds. It does the arbitrary file work, which
  keeps the blast radius legible.

Nothing leaks from serial to council automatically. But a serial exchange
sometimes produces something the council needs ("I have decided X", "the real
constraint is Y"), so there is an explicit command that promotes a chosen passage
into the next broadcast. A door, not a leak.

This dissolves what was going to be the hardest prompt problem in the design.
The original plan had phase 3 mutate the council session into an assistant, which
meant a transition turn strong enough to push a model out of a role it had held
for ten turns: models are sticky about that, and the failure mode is quiet, an
assistant that keeps hedging and will not recommend. The serial session was never
under the restraint, so there is nothing to lift. `solo` becomes trivial:
dismiss the members, retire the council session, the serial session becomes
primary.

Tabbing is not a decision; `solo` is. The outcome line belongs to `solo`, not to
looking in on the secretary.

The obvious failure mode of a two-mode interface is a **mis-addressed turn**: a
question meant for the secretary that goes to three members costs a round, and
one meant for the council that goes to the secretary is simply lost. The mode has
to be visible in the prompt itself, not only in the status line.

### Members are read-only, the secretary writes

`codex -s read-only`, `agy --mode plan --sandbox`, and for claude an explicit
`--tools=Read,Grep,Glob,WebSearch,WebFetch` plus `--strict-mcp-config` with an
empty server list. Otherwise three agents can write the same file without
knowing about each other, which is an unpleasant class of bug to diagnose
afterwards.

Not `--permission-mode plan`, which was the first attempt. Plan mode is Claude
Code's planning workflow rather than a sandbox: a member run under it wrote its
whole answer into `~/.claude/plans/` as a side effect and was primed to produce
an implementation plan instead of an answer. The tool list also closes a wider
hole, since a member otherwise inherits the user's MCP servers and a "read-only"
participant could have posted to Slack.

### Roster, not one member per provider

Members are `provider[:model[:effort]]` triples and several may share a
provider. Two generations of one family (Opus 5 and Fable 5, 3.1 Pro and 3.7
Flash) differ enough to be worth separate seats, and the older or smaller one is
sometimes right.

Named rosters keep flag surgery out of daily use, and put the scarce agy quota
where it belongs, in the wide roster and nowhere else:

```yaml
council:
  secretary: claude:claude-opus-5:high
  roster: default
  rosters:
    default: [claude:claude-fable-5-1:high, codex:gpt-6-astra:high]
    wide:    [claude:claude-fable-5-1:high, codex:gpt-6-astra:high, agy:gemini-3.8-flash-medium]
    cheap:   [claude:claude-haiku-4-5-20251001:medium, codex:gpt-5.4-mini:medium]
```

The secretary is not on any roster. Opus holds the sessions and does the file
work; the members (Fable 5.1, GPT 6 Astra, and in `wide` Gemini 3.8 Flash) do
the hard reasoning, so the two lists do not overlap. Members run at `high`,
which is where the effort belongs; synthesis is stepped down separately via
`synthesis_effort`.

`--roster wide` selects, `--member` appends for a one-off, `--secretary`,
`--secretary-model` and `--secretary-effort` override the default. A flag and a
YAML entry parse through the same grammar (`hugin.session.parse_spec`).

### Three naming layers

As soon as two members share a provider, one name is not enough:

| Layer | Example | Why |
|-------|---------|-----|
| internal id | `claude:fable-5:high` | state dirs, roster keys, session mapping |
| display name | `Fable 5 (high)` | status line, so you can see who is still thinking |
| anonymous letter | `participant B` | in diffs to members: model names trigger priors about who is credible, stable letters still let a position be followed across rounds |

### Sessions, not a pty

Verified 2026-08-25 across all three providers. Prompt caching is server-side
and keyed on the content prefix, so one process per turn keeps the cache and
driving the CLIs through pexpect would buy nothing:

| Provider | resumed-turn cache read | id minted by |
|----------|------------------------|--------------|
| claude | 26665 tokens (630 written) | us, `--session-id` |
| codex | 16768 of 17343 input tokens | CLI, `thread.started.thread_id` |
| agy | 12193 tokens | CLI, `init.conversation_id` |

Process overhead is about 3.2s per turn (14.5s wall against 11.3s API on a
trivial prompt). That is the entire prize pexpect competes for, against the loss
of the structured output the map depends on and the cost of scraping three
repainting TUIs. Implemented in `hugin.session`; see the "Persistent sessions"
section of `CONVENTIONS.md` for the provider traps.

If per-turn startup ever does matter, the honest middle option is
`--input-format stream-json` (claude and agy read one NDJSON message per line
and run a turn per line; codex has no equivalent), not screen scraping.

Caveat: cache TTL. With a human in the loop there are minutes between rounds, so
expect misses on slow rounds. This is identical for every transport because the
cache is server-side, and on subscriptions a miss costs rate-limit budget rather
than money.

### Effort is part of the cache key, so it is set per role and not per turn

This is loosening, model by model. The Claude API has a beta per-message effort
(`mid-conversation-output-config-2026-07-01`) on Fable 5.1, Mythos 5.1 and Opus
5 that leaves the cached prefix intact; Claude Code 2.1.260 (2026-09-03) uses it
for Fable 5.1 only, and its docs still say every other model has one cache per
effort level. GPT-6 Astra accepts a `configuration_update` item that does the
same, and codex 0.154 emits it behind the experimental `reasoning_effort_override`
flag (off by default; it 400s on the 5.6 models). None of that is re-measured
here, and with an Opus 5 secretary the re-read below still applies as of
2026-09-11.

Measured 2026-08-25, four turns on one session at high, high, low, low, with a
~16k-token prefix:

| Turn | Effort | New input | Cached | |
|------|--------|-----------|--------|-|
| 1 | high | 16239 | 16373 | claude, opus-5 |
| 2 | high | 633 | 32610 | the hit |
| 3 | low | 16914 | 16373 | the switch: whole conversation re-read |
| 4 | low | 46 | 33285 | cached again, under the new effort |

codex behaves identically (11592/11008, 346/22272, 11628/11008, 382/22272). agy
was not measured because for gemini the reasoning level is baked into the model
slug, so a change there is a different model, which is a harder invalidation
than this one. Nothing tested tolerates a change for free.

What that means in practice is the opposite of discouraging: the cost is per
*switch*, not per turn, so effort belongs to a role rather than to a turn. The
secretary's council session goes gather, synthesise, synthesise, …, so a lower
synthesis effort costs exactly one re-read, at the first synthesis, and every
round after it hits the cache. `synthesis_effort` defaults to `medium` against a
`high` secretary on that basis: folding answers together is clustering and
compression, and the hard reasoning is the members'. Set it to `high` to undo,
or empty to inherit the secretary's own.

The pattern to avoid is alternating effort turn by turn on one session, which
pays the re-read every time.

### The secretary is watched, the members are not

`Session.send` takes an `on_event` callback, and the council passes one for
every secretary turn: one line per tool call, per piece of text before the
answer, and per permission denial.

The first real gather made this necessary rather than nice. It ran seven
minutes behind a spinner, and a spinner and a hang look identical. Reading the
provider's own transcript afterwards was the only way to find out that it had
spent that time diffing two copies of a PDF.

The members keep the status line instead. They are asked in parallel and their
events would interleave into nonsense, and the useful question about a member
is not what it is doing but whether it has answered.

### The house rules are in the prompt, not discovered

The secretary runs with a shell in whatever directory the command was launched
from, so it never sees the standing instructions in the vault's `AGENTS.md`. The
first consequence was a Chrome started on the real display, which steals the
keyboard focus on every navigation while the user sits there waiting for it.

The file at `house_prompt_path` is pasted into the gather and serial prompts as
`{{HOUSE}}`. The line for what belongs in it: **the cost of not knowing has to
land on the first tool call.** Not knowing where a project directory lives costs
one extra `find`, and can be discovered. Not knowing about the virtual display
cannot, because by the time you could learn it the focus is already gone. Same
for `git log` in a vault that is not a repository, `sudo` without a tty, and a
credentials file whose revoked token looks exactly like an expired login.

The members get none of it. They have no shell, so not one of the hazards is
reachable from where they sit, and the paths are in the brief already.

Nothing ships as a default. House rules are per-machine by definition, and a
packaged set written for whoever wrote the tool would be inherited as fact by
everyone who did not think to look — the failure mode this section exists to
prevent, arriving through the fix. So an unconfigured install gets an empty
block, while a `house_prompt_path` that points at nothing is a hard error: the
quiet fallback must not swallow a typo and drop the rules without saying so.

This does duplicate facts whose source of truth is likely the vault's own
`AGENTS.md`, which is the drift such files spend half a page warning about. Two
mitigations, both conventions for the file rather than code: only invariants go
in, nothing that churns, and the block ends by naming the real source as the
place to read when the question turns out to be about the environment itself.

### State vs output

Per `CONVENTIONS.md`: council state (map checkpoints, session ids, raw answers)
goes in `~/.council/` or a configured `state_dir` and is safe to wipe. The
finished `.md` goes in the vault. Never mixed.

## Scope of v1

Start simple and let the tool tell us what it needs.

**v1 sends the full map to every member each round**, with no diff. The
argument for a diff was partly that it saves context, and that argument is weak
here: three answers of 500 to 1500 tokens make a synthesis of roughly 3k per
round, so ten rounds is ~30k against a 200k to 1M window. A single agentic turn
that reads four files costs more. Context is not the constraint in discussion
work the way it is in programming and verification.

The argument that survives is **preserving independence**, which no token count
shows and which quietly degrades the whole point of paying three models. Most of
that is available from framing rather than from diffing, and framing is free: the
map is sent with an explicit instruction not to revise a position in order to
match the others, and that a disagreement will be recorded as an objection
rather than resolved.

**v1 has no data structure at all.** Not paths, not items, not typed relations,
not numbered options: the synthesis is markdown and nothing else. Every field
that was drafted here was a guess about output that has never once been
produced. The archive is what makes that safe, so it is the one thing v1 does
insist on.

**v1 measures its own need**, but by reading rather than by counting. Ten or
twenty councils in the archive answer three questions that no amount of design
could: whether the full map causes members to stop contributing anything of
their own, whether the synthesis gets unreadable as rounds accumulate, and what
a data structure would have to hold if one is wanted. Two upgrades, two separate
triggers, not to be bundled:

| Symptom | Upgrade |
|---------|---------|
| a member stops saying anything the others did not | a per-member diff, or harder framing first |
| the synthesis gets hard to read as rounds accumulate | some structure, informed by the archive |

## Rejected, with reasons

So these do not get re-argued:

- **A judge that synthesises one answer** (the Karpathy consortium shape). It is
  built for a well-defined question with a right answer. These are trade-offs,
  and a judge flattens exactly the part worth having.
- **`llm-consortium`** (already installed). Goes over API keys, so a separate
  cost next to the subscriptions, and the models get no filesystem access. Fine
  for pure reasoning with no context; wrong for anything grounded in the vault.
- **Driving the CLIs with pexpect.** See above.
- **A stateless secretary.** Considered, then dropped: context continuity helps
  the jobs it actually does, and the "nobody owns the conversation" principle was
  about opinions, which the secretary has none of.
- **Rewriting the user's turn per member.** Unnecessary: every member has just
  read the same synthesis, so a turn written against it lands in every thread.
- **Numbered options (V1, V2, V3) as shared vocabulary.** Built, then ripped
  out; see "Steering is in plain words".
- **The `gemini` binary as the third voice.** `agy` replaced it in the stack, and
  it resumes on a stable id where `gemini --resume` takes a positional index.

## Naming

`council` because the members advise and nobody votes. The two modes are
`council` and `serial`. Ending the council for good is `solo`, which says what you
get; `adjourn` is the right word for it and lives in the help text.
Rejected: `thing` (þing is etymologically right, ungreppable in practice),
`counsel` (homophone, bad in a command you type), `quorum` (implies a minimum for
validity), `chorus` (unison, precisely wrong), `synod` (settles doctrine, too
heavy), `panel` (collides with UI vocabulary).

The unified cross-engine session index discussed alongside this belongs in a
separate repo, `hugin-munin`: Huginn is thought, Muninn is memory.

## TODO

- [x] `hugin.session.Session`: persistent multi-turn sessions for codex, claude
      and agy, resumed by id, with normalised usage. Shipped in `hugin`.
- [x] Diff deferred out of v1, in favour of the full map plus independence
      framing. See "Scope of v1".
- [x] Synthesis prompt. Free-text markdown with no formatting rule, plus the
      constraint that the secretary may classify and compress but not resolve a
      disagreement or invent a middle position nobody proposed.
- [x] Archive layout as above, with raw answers kept verbatim. This is the one
      part that has to be right from the start, because it is what makes a
      structure extractable later at all.
- [ ] After 10 to 20 real councils: read the archive and see what a data
      structure would actually need to hold. Not before.
- [x] **cwd-aware context resolution.** The command must run from anywhere. Under
      a `projects_root` subdirectory phase 1 should look at that repo *and* the general
      hugin directories. Anywhere else, the hugin vault is the default, with the
      current directory available as a weak hint for finding files the question
      refers to.
- [x] Phase 1 gatherer. Per source: path or URL, what it says, a line on why it
      is relevant. Plus a short list of what it looked at and **rejected**, so a
      member can pull a thread the secretary dropped. That list is what makes one
      model's relevance judgement an acceptable price.

      It may extract plain facts, not only point at them, because pointers alone
      mean three members repeat the same lookup, which is what phase 1 exists to
      prevent. The line is not fact versus opinion, which is a phrase that
      stretches: it is **verifiable against the source without judgement**.
      Allowed are verbatim quotes, numbers, dates, versions, paths, command
      output, and "source X says Y" attributed to the source even where the claim
      is contested. Not allowed are ranking credibility, reconciling
      contradictions, implications, "this suggests", or filling gaps by
      inference.

      Three rules follow:

      - **Contradictions are preserved, not resolved.** If the vault says one
        thing and a repo another, report both, attributed. That they disagree is
        itself a fact, and settling it is the analysis that belongs to the
        members. Note the symmetry: the secretary's constant across every phase
        is *may not resolve*. Phase 1 gathers without reconciling, phase 2b
        synthesises without deciding. One rule, two phases, and phase 3 is where
        it is lifted, which is exactly why that inversion is the risky part.
      - **Every fact carries its source inline**, or the brief becomes a layer of
        unsourced assertions that read as authoritative. This is where the real
        risk sits: an error in the brief is **correlated across all members**. A
        member's own mistake gets caught by the others; the brief's mistake gets
        caught by nobody and shows up in three answers at once. Correlated error
        is the worst failure mode a council has, so extraction stays sparse and
        always cited.
      - **Date the extraction.** Vault prose goes stale, and the `gws` entry in
        `AGENTS.md` is that exact failure. An extracted fact is "the document says
        X as of this date", not "X". And quote verbatim for anything load-bearing:
        a paraphrase of a number is a bug.

      Phase 1 is **mandatory for now**, and the prompt says so with the honest
      caveat attached: the material may not exist. Nothing guarantees the vault
      has prior art, that the repo underfoot is relevant, or that the web has
      anything. So an empty brief is a first-class answer — where it looked,
      which searches, which URLs, and the statement that none of it bears on the
      question. That is worth a round trip, because it tells the members the
      ground is empty and stops three of them searching it again. The failure
      mode being designed against is a stretched connection, which is correlated
      error wearing a citation.
- [ ] Reconsider whether phase 1 should be skippable, once there is evidence of
      it being a waste rather than a guess that it might be. It was a flag
      (`--no-gather`) and a config key, both removed while it is mandatory,
      because a knob nobody turns is worse than no knob.
- [x] Broadcast with the status line: who is still thinking, for how long, and who
      died. Nothing more. The members are asked in parallel, so the row is
      labelled with the letter the synthesis will attribute it to, the clock
      ticks per member while it thinks, and a footer names who is still out and
      how long the round has been running. Wall clock, not the sum: a round costs
      the slowest member. A failure is counted apart from the answers rather than
      folded into the numerator, which would read as success.
- [ ] Phase 2b synthesis prompt, with the may-not-resolve constraint.
- [x] Mode toggle between council and serial, with the mode shown in the prompt
      itself, plus the second secretary session behind it and the explicit
      promote-to-broadcast command.
- [x] `solo`: dismiss the members, retire the council session, promote the serial
      session. No transition turn needed, since that session was never
      restrained. `solo` also **records the outcome**: what was landed on and
      briefly why, in prose. One line, and it is what turns the archive from a
      pile of transcripts into a labelled record. Every later analysis pass
      depends on it, so it is not optional.
- [ ] Analysis passes over the archive, once there is an archive worth reading.
      These belong in `hugin-munin`, not here: the corpus that matters is
      already on disk (289 codex rollouts, 68 claude sessions) and the council
      archive is a small clean addition to it. Sketched so far:
      - Stale-assertion detection: claims in `AGENTS.md` that later sessions
        disproved. The `gws` `invalid_grant` entry was wrong for six weeks and
        actively recommended the setting that caused the problem, so this catches
        a failure mode that additions do not. Sibling signals: user corrections
        that recur across sessions, facts rediscovered more than once, dead ends
        entered repeatedly.
      - Bias naming: mine (opening proposal, final decision) pairs for
        *systematic* over- and under-shoot. Two cautions. Optimising towards "say
        early what the user concludes" is optimising for agreement, which defeats
        the point of a council, so separate wasted motion (machinery proposed
        ahead of evidence, context re-derived, questions answerable from the
        repo) from disagreement that simply lost. And measure the proportion of
        an answer that survived rather than turns-to-convergence: in the design
        conversation behind this repo the surviving core arrived in turn two and
        the discarded part was the decoration around it. Output should be a named
        bias with evidence, which can be written into `AGENTS.md` and inspected,
        not an optimised prompt string, which can only drift.
      - Contribution review. Who actually contributed, judged by a model
        reading the record. This is not a statistics problem and the data-sparsity
        objection was the wrong frame: one transcript holds dozens of observable
        moments, so ten councils are not ten observations. It also does not
        violate "no judge": judging the *answer* flattens the disagreement that
        is the point, judging the *answerers* is a different job whose output
        feeds a roster choice the user was making by hand anyway.

        The rubric is what makes the soft question usable. Origination
        (introduced something nobody else had, which survived); load-bearing
        versus decorative; **productive wrongness** (a rejected contribution that
        caused the right answer, e.g. a wrong hypothesis that forced a
        measurement); correction of another member or of a premise;
        **compression** (saying "you don't need that", since deletions were the
        most valuable moves in the design conversation behind this repo and no
        count of additions can see them); padding; and deference versus genuine
        agreement after seeing the synthesis. Four of those seven are
        unreachable by counting, which is the case for a reader over a metric.

        Two design choices decide whether it works. **Blind the judge**: rate
        participants A/B/C from the archive and unmask afterwards, because the
        output is literally "which brand should I use" and this is the one place
        where brand priors contaminate the conclusion directly. And **not the
        secretary**: it wrote the synthesis, so it would be grading its own
        clustering, and if it also sat as a member it would be grading itself. A
        fresh instance with no stake, and one that did not participate.

        Output is prose, not a score. A number invites false precision and
        averaging over incommensurable things. A short written assessment per
        member per council accumulates into what gets read before choosing a
        roster. The judge's assessment is itself a model opinion with systematic
        tastes, probably favouring articulate structured answers over terse
        correct ones, which is exactly why it stays text the user can disagree
        with rather than a number that quietly drives routing.
      - Quota-aware roster suggestion. Needs no learning and works today: agy is
        the scarce resource, so a suggestion that knows the week's agy use is
        deterministic and useful. Note the roster granularity already designed
        (`default`, `wide`, `cheap`) beats learned routing anyway, since a
        one-word choice is the right resolution for this decision.
