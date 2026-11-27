# 590X — Choices of the UI messages lane

**Status:** proposed, 2026-11-27 (agent: the UI messages lane on `dom/ui-saving-port`, Q954).

## Decision

The user decided the work: Q925 and Q927 of
[ADR-9V4Y](9V4Y-decisions-of-the-user-on-the-shutdown-lane-q924-to-q928.md), and Q954 ("start the UI lane for Q925
and Q927, spec and tests first"). [`recorder.md`](../../specs/recorder.md) 9.2 states the rules. These choices fill
gaps.

1. **The spec.** No spec owned the Electron side of the end of the server. The rules go in a new section 9.2 of
   `recorder.md`, after 9.1, which cites Q925.
2. **A native box, not a window.** Both messages are a `dialog.showMessageBox` of the main process. After the close
   of the last window no renderer is left, so the main process must show the "saving" message; the "port in use"
   message uses the same means.
3. **The delay.** "About 10 s" is 10 s from the start of the wait of the quit. Only a quit shows the box; the
   "Stop server" and "Reset" buttons do not.
4. **The "saving" box.** No parent window. One button, the system "OK". A close removes the box only; it does not
   come back; the wait goes on. The box closes itself when the wait ends. Two quits in one wait show one box.
5. **The "port in use" rule.** A non-zero exit code and the bind error of `loop.create_server` with errno 10048, 98
   or 48 in the last 4096 characters of stderr, at the `close` event. The exit code (3) alone is not enough: other
   faults end with 3 or 1. A bind refusal of another kind (for example 10013 on Windows, a port in a reserved
   range) shows nothing new.
6. **The "port in use" box.** On the main window if it exists. One button, the system "OK"; no retry button and no
   quit: the app stays open, and "Launch server" of the connection menu is the retry, as after each other start
   failure. The port is 53117 (`DEFAULT_PORT`), filled in by the renderer.
7. **`isRunning` after the exit.** `PythonServer.isRunning()` is false after an exit code or a signal. Before, it
   stayed true, and the connection menu showed "Stop server" in place of the "Launch server" that the message names.
   This changes no start or stop.
8. **The texts.** The renderer sends the four texts with the menu labels (the way that the main process gets its
   texts today), with `{{port}}` filled. English until then. English plus `es`, `zh-CN` and `ar` (Q948). "Launch
   server" stays in English, because the button is not translated. The translations are the lane's: es "Todavía se
   están guardando las grabaciones." / "SkellyCam se cerrará solo cuando termine." / "SkellyCam no puede iniciar su
   servidor: el puerto {{port}} está en uso." / "Otro programa, u otra copia de SkellyCam, usa este puerto.
   Ciérrelo y luego haga clic en “Launch server” en el menú de conexión, o reinicie SkellyCam."; zh-CN
   "录像仍在保存中。" / "保存完成后，SkellyCam 会自动关闭。" / "SkellyCam 无法启动其服务器：端口 {{port}} 已被占用。" /
   "另一个程序或另一个 SkellyCam 副本正在使用此端口。请将其关闭，然后在连接菜单中点击“Launch server”，或重新启动
   SkellyCam。"; ar "لا يزال حفظ التسجيلات جاريًا." / "سيُغلق SkellyCam تلقائيًا عند انتهاء الحفظ." / "لا يستطيع
   SkellyCam تشغيل الخادم الخاص به: المنفذ {{port}} قيد الاستخدام." / "برنامج آخر، أو نسخة أخرى من SkellyCam، يستخدم
   هذا المنفذ. أغلقه، ثم انقر على “Launch server” في قائمة الاتصال، أو أعد تشغيل SkellyCam.". No native speaker
   checked them.
9. **The tests.** T-APP-01 to T-APP-04 are unit tests of one pure module,
   `skellycam-ui/electron/main/services/server-messages.ts`. `test:player:unit` gets the glob
   `electron/main/**/*.test.ts`, so CI runs them. The boxes and the wiring are not tested: the repository has no
   harness for the main process of the app, and this lane builds none.

## Reason

The words of the user give the two messages and no bound. Each choice is the smallest that works when no window
is left and that matches how the app handles a failed start today.

## Consequences

- Questions for the user (a yes accepts each recommendation): (a) Items 1 to 9 as written? (b) The "saving" box
  shows only at a quit, not at "Stop server"? (c) No retry button in the "port in use" box? (d) A port in a
  reserved range (10013) shows nothing new for now?
- Two faults outside this lane, found by code reading, not changed: the server starts through `exec` with a
  `maxBuffer` of 100 MB, and Node kills a child whose stdout or stderr passes that size (a kill of the server
  during a long run); and when the shutdown request fails, the app stays with no window and no way to quit except
  the task manager.

## Open work

See [open-work.md](../open-work.md).
