# hugin-council

Ask a question once, get answers from two or three model instances that do not
see each other, and get them folded into one map of the possible paths.

Part of the Hugin stack. Reads `~/.config/hugin/hugin.yaml` plus
`~/.config/hugin/council.yaml` and honours `~/projs/hugin/CONVENTIONS.md`.

## Why

Running Codex, Claude and Antigravity side by side by hand has three costs:
pasting the same question into each, re-explaining the same clarification in
every follow-up, and reading three answers that overlap by roughly 80%. This
tool removes all three without removing the disagreement, which is the part
worth having.

## Shape

| Phase | Who | What |
|-------|-----|------|
| 1 (optional) | secretary | Gather: find relevant vault files, past conversations, web sources. Summarise and link. No analysis, no conclusions. |
| 2 | members | Same question and same background to each, in parallel. Each knows it is part of a council and what that means. May look up more on its own. |
| 2b | secretary | Synthesis: fold the answers into the map. |
| 3 | secretary | `solo`: dismiss the members, keep the secretary, switch it to general assistant with its context intact. |

Rounds repeat 2 and 2b. Your turn goes to every member verbatim.

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

Two consequences:

- **Stable ids survive without a schema.** Numbering the options in the
  synthesis (V1, V2, V3, never reused across rounds) is a prompt convention, not
  a schema requirement. It is what lets a turn be broadcast verbatim, so it is
  the one formatting rule the synthesis prompt insists on.
- **`council stats` is not a feature, it is a later pass** over the archive.
  Probably better that way: what to count can be decided once it is known what
  mattered. The question it eventually answers is whether Fable 5 earns its seat
  next to Opus 5, or 3.7 Flash next to 3.1 Pro.

### It is organised by path, not by agreement

Disagreement between members is real but rare, and it is not the axis. Usually
there are simply several possible ways forward, sometimes clearly separable and
sometimes not. So the map sorts on path, and an objection is an attribute of a
path rather than a section of its own. Criticism is the user's job and arrives
naturally once a track is picked.

Round 1 must therefore ask for **breadth, not a recommendation.** Ask three good
models what to do and they converge on the same obvious answer; ask for several
distinct paths with trade-offs and they do not.

Synthesis is clustering, not comparison: the hard part is seeing that one
member's "briefing skill" and another's "shared context file" are the same path
under two names, while both members' "consortium" mean different things. Cluster
on mechanism, not on wording. The secretary may classify and compress but may
**not** resolve a disagreement or invent a middle position nobody proposed.

### Path ids are stable across rounds

V1, V2, V3 keep their numbers for the life of the council, so they become shared
vocabulary between you and every member. That is what lets your turn be
broadcast verbatim: "go with V2 but skip fzf" lands correctly in three threads
that each framed the problem differently. A new path in round three takes the
next free number and keeps it.

This replaced an earlier design where the secretary rewrote your turn per
member to resolve referents. Stable numbering solves the same problem for free.

### The secretary holds a session; members hold sessions; only the map is on disk

The secretary is not a judge or a chair. It is one instance doing serial jobs:
gather, cluster, synthesise, write files. It does hold a session, because
context continuity makes those jobs better: clustering in round three is much
easier if it remembers why V2's boundary was drawn where it was, and gathering
can skip what it already rejected. It having continuity does not make it own the
conversation, because it has no opinions to own it with.

The map file stays on disk anyway, as a **checkpoint** rather than as the
secretary's state: it is needed for the diffs and for the `.md` deliverable, so
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
  does the file writing and the phase 3 role inversion.

### Phase 3 is a role inversion, and that is the risk

By phase 3 the secretary has spent several rounds under "no analysis, no
conclusions, you are not a judge". Models are sticky about a role they have held
that long, and the failure mode is quiet: an assistant that keeps hedging and
will not recommend. So the transition turn must explicitly lift the restraint,
not just add a new job.

It has to be sent as a **turn**, not a system prompt change: no CLI can change
the system prompt of a live session, and `--append-system-prompt` applies at
invocation only. Default is to mutate in place. `--fork` is available
(`codex exec fork`, `claude --fork-session`) for when the council should stay
reconvenable without the secretary carrying opinion mode back into it.

### Members are read-only, the secretary writes

`codex -s read-only`, `claude --permission-mode plan`, `agy --mode plan
--sandbox`. Otherwise three agents can write the same file without knowing about
each other, which is an unpleasant class of bug to diagnose afterwards.

### Roster, not one member per provider

Members are `provider[:model[:effort]]` triples and several may share a
provider. Two generations of one family (Opus 5 and Fable 5, 3.1 Pro and 3.7
Flash) differ enough to be worth separate seats, and the older or smaller one is
sometimes right.

Named rosters keep flag surgery out of daily use, and put the scarce agy quota
where it belongs, in the wide roster and nowhere else:

```yaml
secretary: claude:opus-5:high
rosters:
  default: [claude:opus-5:high, claude:fable-5:high, codex:gpt-5.6-sol:high]
  wide:    [claude:opus-5:high, claude:fable-5:high, codex:gpt-5.6-sol:high,
            codex:gpt-5.5:xhigh, agy:gemini-3.1-pro-high, agy:gemini-3.7-flash-high]
  cheap:   [claude:fable-5:medium, codex:gpt-5.4-mini:medium]
```

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

**v1 has no data structure at all.** Not paths, not items, not typed relations:
the synthesis is markdown and nothing else. Every field that was drafted here was
a guess about output that has never once been produced. The archive is what makes
that safe, and stable option numbering is what makes it usable, so those are the
two things v1 does insist on.

**v1 measures its own need**, but by reading rather than by counting. Ten or
twenty councils in the archive answer three questions that no amount of design
could: whether the full map causes members to stop contributing anything of
their own, whether the synthesis gets unreadable as options accumulate, and what
a data structure would have to hold if one is wanted. Two upgrades, two separate
triggers, not to be bundled:

| Symptom | Upgrade |
|---------|---------|
| a member stops saying anything the others did not | a per-member diff, or harder framing first |
| the synthesis gets hard to read as options accumulate | some structure, informed by the archive |

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
- **Rewriting the user's turn per member.** Made unnecessary by stable option
  numbering in the synthesis.
- **The `gemini` binary as the third voice.** `agy` replaced it in the stack, and
  it resumes on a stable id where `gemini --resume` takes a positional index.

## Naming

`council` because the members advise and nobody votes. Phase 3 is `solo`, which
says what you get; `adjourn` is the right word for it and lives in the help text.
Rejected: `thing` (þing is etymologically right, ungreppable in practice),
`counsel` (homophone, bad in a command you type), `quorum` (implies a minimum for
validity), `chorus` (unison, precisely wrong), `synod` (settles doctrine, too
heavy), `panel` (collides with UI vocabulary).

The unified cross-engine session index discussed alongside this belongs in a
separate repo, `hugin-munin`: Huginn is thought, Muninn is memory.

## TODO

- [x] `hugin.session.Session`: persistent multi-turn sessions for codex, claude
      and agy, resumed by id, with normalised usage. On branch
      `session-abstraction` in `~/projs/hugin`.
- [x] Diff deferred out of v1, in favour of the full map plus independence
      framing. See "Scope of v1".
- [ ] Synthesis prompt. Free-text markdown, and the only hard formatting rule is
      stable numbering of the options so a turn can be broadcast verbatim. Plus
      the constraint that the secretary may classify and compress but not resolve
      a disagreement or invent a middle position nobody proposed.
- [ ] Archive layout as above, with raw answers kept verbatim. This is the one
      part that has to be right from the start, because it is what makes a
      structure extractable later at all.
- [ ] After 10 to 20 real councils: read the archive and see what a data
      structure would actually need to hold. Not before.
- [ ] **cwd-aware context resolution.** The command must run from anywhere. Under
      a `~/projs` subdirectory phase 1 should look at that repo *and* the general
      hugin directories. Anywhere else, the hugin vault is the default, with the
      current directory available as a weak hint for finding files the question
      refers to.
- [ ] Phase 1 gatherer. Writes pointers, not prose: path or URL, a paragraph on
      what the source says, a line on why it is relevant. Plus a short list of
      what it looked at and **rejected**, so a member can pull a thread the
      secretary dropped. That list is what makes one model's relevance judgement
      an acceptable price.
- [ ] Broadcast with the status line: who is still thinking, for how long, and who
      died. Nothing more.
- [ ] Phase 2b synthesis prompt, with the may-not-resolve constraint.
- [ ] Phase 3 `solo`, including the restraint-lifting transition turn and
      `--fork`. `solo` also **records the outcome**: which option was taken and
      briefly why, in prose, at the end of the council. One line, and it is what
      turns the archive from a pile of transcripts into a labelled record. Every
      later analysis pass depends on it, so it is not optional.
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
      - Roster suggestion. Not learned routing: twenty councils over five
        question types is four observations per cell, with an outcome label
        confounded by ordering, cost and habit. Render the record honestly
        instead ("six similar councils, you took Opus 5's option three times")
        and leave the judgement with the user, on the same grounds as having no
        judge model. The part that does work without learning is quota: agy is
        the scarce resource, so a suggestion that knows the week's agy use is
        deterministic and useful.
- [ ] Secretary session rotation at a round boundary.
- [ ] Resolve agy's `--effort` versus model-slug precedence by experiment, and
      decide how to surface agy quota use.
- [ ] Measure whether `claude -p` gets the 5-minute or the 1-hour cache TTL. It
      changes nothing structural, only expectations.
