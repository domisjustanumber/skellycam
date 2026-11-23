# 6RVC — Choices of the first propose: the other-systems rule

**Status:** proposed, 2026-11-23 (agent; waits for the user).

## Decision

An agent made these choices when it sent the other-systems rule to the kit
([ADR-0AMX](0AMX-propose-from-skellycam-and-review-in-the-kit.md)).

1. **Citations.** The kit text cites no entry of a repository. The tool and its test cite no entry
   now. The repository text after the block `AGENTS.md#other-systems` cites ADR-VV4Q, ADR-K3BX,
   ADR-C307 and ADR-K9B7.
2. **The hook** `other-systems` is in the block `.pre-commit-config.yaml#local-hooks`, after the hook
   `line-ends`.
3. **A test leaves the kit file.** `test_the_real_spec_has_check_names` fails in a repository with no
   certify spec. `test_repo_values.py` keeps the stronger `test_the_real_spec_holds_check_names_only`.
4. **Values.** `--fill CERTIFY_REPO` and `--fill SELF_TEST`: in the four units, "skellycertify" and
   `skellycam.certify` are values of this repository. `--literal CERTIFY_SPEC` (the supervisor's
   command): `specs/certify.md` stays plain text, also as the default of the tool and in the links
   of the skill. A repository with another spec path sets `certify_spec` in `kit.toml`, but the
   skill text still names `specs/certify.md`.

## Reason

Items 1 to 3 let the units pass the kit tests (no repository entry, no repository name, a pass in
each repository) with no change of the behaviour of the tool. Item 4 keeps the links of the skill
valid in the kit.

## Open work

See [open-work.md](../open-work.md).
