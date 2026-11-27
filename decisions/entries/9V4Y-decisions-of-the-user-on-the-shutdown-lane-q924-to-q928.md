# 9V4Y — Decisions of the user on the shutdown lane, Q924 to Q928

**Status:** accepted, 2026-11-27 (user, Q924 to Q928).

## Decision

The user wrote on 2026-11-27: "yes to all". Each answer accepts the recommendation of its question.

1. **Q924.** The choices of the shutdown lane are accepted, subject to the review: the cancel of the join of the log
   queue, the DEBUG line, and the 5 s limit. The limit comes only in the order of Q928.
2. **Q925.** The Electron app gets no bound on its wait for the exit of the server. At most, it shows a "saving"
   message after about 10 s, in a later UI lane.
3. **Q926.** The exit hang on the log queue is fixed once in skellylogs (`_cleanup_log_queue` cancels the join
   instead of joining), on a branch of that repository, with no push without a yes of the user.
4. **Q927.** A later UI lane makes the app show "port in use" when the server ends with that error.
5. **Q928.** First the take start and the take stop are protected from a cancel (`asyncio.shield`), with a test that
   Ctrl-C or SIGTERM during a slow stop ends with the manifest `finished`. Only then the 5 s shutdown limit comes.

## Reason

The words of the user, above. A review found that the limit can leave a take unfinished on each path other than the
shutdown endpoint ([evidence](../evidence/cancelled-take-stop-at-a-shutdown-limit-20261127.md)). The first rule of
the user is that no recording is lost.
