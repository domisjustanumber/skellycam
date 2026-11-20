# N2NH — Index limit of 24,000 characters until the clean-up, no shortened rows, binding specs

**Status:** accepted, 2026-11-20 (user; commit to dom/index-limit).

## Decision

The user decided these four items on 2026-11-20.

1. **Index limit.** `INDEX_LIMIT` of `tools/check_decision_log.py` changes from 14,000 to 24,000
   characters. This entry is the entry that the Rules require for a PR that raises a limit. The
   limit goes down again after the clean-up. In the clean-up, the user decides each `proposed`
   entry. Then the small choice entries of the agents are merged into one entry for each step on
   the merged branch.
2. **No shortened rows.** An agent never shortens the index row of an entry that it did not write.
3. **Binding specs.** The specs in `specs/` are binding text. A decision that a spec states in full
   can move to [historical.md](../historical.md). Before an entry moves, a check, entry by entry,
   must show that the spec states each rule of that entry. This changes the rule of item 4 of
   [ADR-S222](S222-bootstrap-answers-of-the-kit-adoption.md), which says that no spec is normative
   ([ADR-2S1P](2S1P-bootstrap-answers-with-binding-specs.md) records the change).
4. **No bigger restructuring now.** The bigger restructurings stay undone unless the index fills
   again: one index for each module, and a move of the Rules text or of the Proposed table out of
   the index.

## Reason

The user decided after a study of the size of the index, with these facts:

- `decisions/README.md` is in the read path of each agent. About half of the file is fixed prose.
- 28 entries are `proposed`.
- The merged index of the integration branch needs about 19,900 characters. The limit was 14,000.
- Agents shortened rows to stay below the limit. The shortened rows lost facts.

## Open work

See [open-work.md](../open-work.md).
