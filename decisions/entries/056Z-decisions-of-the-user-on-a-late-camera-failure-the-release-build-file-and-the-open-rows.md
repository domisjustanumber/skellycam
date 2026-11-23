# 056Z — Decisions of the user on a late camera failure, the release build file and the open rows

**Status:** absorbed into
[`specs/certify.md#352-addition-1-the-commit-and-the-tree-state-u-q557`](../../specs/certify.md#352-addition-1-the-commit-and-the-tree-state-u-q557),
[`specs/certify.md#361-rules-of-the-rows`](../../specs/certify.md#361-rules-of-the-rows),
[`specs/certify.md#362-the-check-catalogue-for-each-level`](../../specs/certify.md#362-the-check-catalogue-for-each-level),
[`specs/certify.md#368-rows-and-bytes-today-and-after`](../../specs/certify.md#368-rows-and-bytes-today-and-after),
2026-11-23 (commit to dom/certify-build; was accepted, 2026-11-23 (user, relayed by the supervisor; questions Q646 to Q648)).

## Decision

The user answered three questions of the review of the certify build with "Q646-Q648 agree".

1. Q646: "A camera that dies after the take's checks have passed leaves almost no trace today. Its model still gets
   `pass`. Should certify look once more after the take rows and after the close, and give that camera a `fail`
   row?" Yes. Certify looks once more after the take rows and after the close. A camera that leaves there gets a
   `fail` row. The user did not decide which row; the agent chose it in
   [ADR-0Z6Q](0Z6Q-choices-of-the-certify-report-shape-build.md) (`<label>:live-at-close`).
2. Q647: "The report's commit field is filled only for one kind of local build. The installer that people actually
   run gets none, so every real report would say 'commit unknown' and 'tree modified'. Should the release build (CI
   and the installer) write the commit file too?" Yes. The release build (CI and the installer) carries
   `skellycam/build_info.json`. The agent reads "the release build" as also the sdist and a wheel built from the
   sdist ([ADR-0Z6Q](0Z6Q-choices-of-the-certify-report-shape-build.md) item 6).
3. Q648: "Such a camera keeps three rows (`opens`, `rate`, `modes:granted`), because the three are announced
   together. The spec's row count assumed two rows. Should it keep the three rows, with the spec's count
   corrected?" Yes. A camera that fails at the open keeps the three rows and one `not-reached` row. The count of
   [`certify.md`](../../specs/certify.md) 3.6.8 changes.

## Reason

1. Before, a camera that died after its take checks left only a cleanup row or nothing, and its model got `pass`.
2. Without the file, each report of a release is not valid as evidence ("commit unknown", "tree modified").
3. The three checks of the open start together in one apply, and each has a progress message.
