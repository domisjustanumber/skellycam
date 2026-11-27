// A fake server for T-APP-06 (specs/recorder.md 9.3): 105 MiB to stdout, then 105 MiB to stderr, then the
// bind-error line, then it waits until its parent ends it. The old exec start killed a child at 100 MiB.
const MIB = Buffer.alloc(1024 * 1024, 'x');
const LINE = "ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 53117): end\n";

function write(stream, mib, done) {
    let left = mib;
    const next = () => {
        while (left > 0) {
            left -= 1;
            if (!stream.write(MIB)) { stream.once('drain', next); return; }
        }
        done();
    };
    next();
}

write(process.stdout, 105, () => write(process.stderr, 105, () => process.stderr.write(LINE)));
setInterval(() => {}, 1000);
