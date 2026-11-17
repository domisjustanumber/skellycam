// Which column of one Parquet file fails in hyparquet + hyparquet-compressors (used to locate the LZ4_RAW failure).
//   node probe_lz4_columns.mjs <node project dir with pinned hyparquet> <file.parquet>
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const [nodeDir, path] = process.argv.slice(2);
const load = rel => import(pathToFileURL(join(nodeDir, 'node_modules', rel)).href);
const {parquetMetadata, parquetRead} = await load('hyparquet/src/index.js');
const {compressors} = await load('hyparquet-compressors/src/index.js');
const buf = readFileSync(path);
const file = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
const metadata = parquetMetadata(file);
for (const name of metadata.schema.slice(1).map(e => e.name)) {
    let err = null;
    const onReject = e => { err ??= e; };
    process.on('unhandledRejection', onReject);
    try { await parquetRead({file, metadata, compressors, columns: [name], onComplete: () => {}}); } catch (e) { err ??= e; }
    await new Promise(r => setTimeout(r, 20));
    process.off('unhandledRejection', onReject);
    console.log(name, err ? `FAIL ${err.message}` : 'ok');
}
