// Read Parquet files the way freemocap-ui's playback-parquet.ts does (hyparquet parquetRead + hyparquet-compressors,
// one parquetRead per row group, onChunk), then hash every column so read_check.py can compare bit for bit.
//
//   node hyparquet_check.mjs <node project dir with pinned hyparquet> <files.json> <out.json>
//
// Float columns: sha256 of the Float64Array (null -> +0) and of the Uint8 null mask. hyparquet returns FLOAT as a JS
// number (exact widening), so a match against the widened float32 source is a bit-exact float32 check.
// Other columns: sha256 of values joined by \x1f (null -> \x00, BigInt -> decimal string).
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const [nodeDir, listPath, outPath] = process.argv.slice(2);
const load = rel => import(pathToFileURL(join(nodeDir, 'node_modules', rel)).href);
const {parquetMetadata, parquetRead} = await load('hyparquet/src/index.js');
const {compressors} = await load('hyparquet-compressors/src/index.js');
const versions = Object.fromEntries(['hyparquet', 'hyparquet-compressors', 'fzstd', 'hysnappy'].map(name =>
    [name, JSON.parse(readFileSync(join(nodeDir, 'node_modules', name, 'package.json'), 'utf8')).version]));

const results = {node: process.version, versions, files: {}};
let record = {};
// hyparquet emits onChunk without awaiting, so a decode error can surface as an unhandled rejection
process.on('unhandledRejection', error => { record.error ??= String(error && error.stack || error).split('\n').slice(0, 3).join(' | '); });
for (const path of JSON.parse(readFileSync(listPath, 'utf8'))) {
    record = {};
    results.files[path] = record;
    try {
        const buf = readFileSync(path);
        const file = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
        const started = performance.now();
        const metadata = parquetMetadata(file);
        const leaves = metadata.schema.slice(1);
        const names = leaves.map(e => e.name);
        const total = Number(metadata.num_rows);
        const columns = Object.fromEntries(leaves.map(e => [e.name, {type: e.type, values: new Array(total)}]));
        let rowStart = 0;
        for (const group of metadata.row_groups) {
            const rowEnd = rowStart + Number(group.num_rows);
            await parquetRead({file, metadata, compressors, columns: names, rowStart, rowEnd, onChunk: chunk => {
                const target = columns[chunk.columnName].values;
                for (let row = Math.max(chunk.rowStart, rowStart); row < Math.min(chunk.rowEnd, rowEnd); row++) {
                    target[row] = chunk.columnData[row - chunk.rowStart];
                }
            }});
            rowStart = rowEnd;
        }
        record.decode_ms = performance.now() - started;
        record.codecs = [...new Set(metadata.row_groups.flatMap(g => g.columns.map(c => c.meta_data.codec)))];
        record.value_encodings = [...new Set(metadata.row_groups.flatMap(g => g.columns.filter(c => c.meta_data.path_in_schema[0].startsWith('value')).flatMap(c => c.meta_data.encodings)))];
        record.columns = {};
        for (const [name, {type, values}] of Object.entries(columns)) {
            if (values.some(v => v === undefined)) throw new Error(`rows missing in column ${name}`);
            if (type === 'FLOAT' || type === 'DOUBLE') {
                const data = new Float64Array(total), mask = new Uint8Array(total);
                values.forEach((v, i) => { if (v === null) mask[i] = 1; else data[i] = v; });
                record.columns[name] = {type, js_types: [...new Set(values.map(v => v === null ? 'null' : typeof v))],
                    values: createHash('sha256').update(new Uint8Array(data.buffer)).digest('hex'),
                    nulls: createHash('sha256').update(mask).digest('hex')};
            } else {
                record.columns[name] = {type, js_types: [...new Set(values.map(v => v === null ? 'null' : typeof v))],
                    values: createHash('sha256').update(values.map(v => v === null ? '\x00' : String(v)).join('\x1f'), 'utf8').digest('hex')};
            }
        }
    } catch (error) {
        record.error ??= String(error && error.stack || error).split('\n').slice(0, 3).join(' | ');
    }
    await new Promise(resolve => setTimeout(resolve, 20)); // let pending rejections land on this file's record
    if (record.error) delete record.columns;
    console.log(path, record.error ?? `ok ${record.decode_ms?.toFixed(0)} ms`);
}
writeFileSync(outPath, JSON.stringify(results, null, 1));
