// Unit coverage of the served workbench helpers, not browser/layout acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const zlib = require('node:zlib');
const source = fs.readFileSync(path.join(__dirname, '../invest/web/workbench.js'), 'utf8');
const helpers = source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='), source.indexOf('function action('));
const archive = source.slice(source.indexOf('async function loadDocuments('), source.indexOf("action('refresh-documents'"));
const id = 'a'.repeat(64), newerId = 'b'.repeat(64);
const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

// An actual decodable 1200 x 900 RGBA PNG, independently built for byte-integrity tests.
const nativePixels = zlib.deflateSync(Buffer.alloc(900 * (1 + 1200 * 4)));
function chunk(type, data = Buffer.alloc(0)) {
  const contents = Buffer.concat([Buffer.from(type), data]);
  let crc = 0xffffffff;
  for (const byte of contents) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  const length = Buffer.alloc(4), checksum = Buffer.alloc(4);
  length.writeUInt32BE(data.length); checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
  return Buffer.concat([length, contents, checksum]);
}
function pngParts() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(1200, 0); header.writeUInt32BE(900, 4); header[8] = 8; header[9] = 6;
  return {header, data: nativePixels};
}
function png() {
  const {header, data} = pngParts();
  return Buffer.concat([signature, chunk('IHDR', header), chunk('IDAT', data), chunk('IEND')]);
}
function response(body = png(), type = 'image/png', status = 200) {
  return new Response(body, {status, headers: {'Content-Type': type}});
}
function harness(fetcher = () => response()) {
  const calls = {requests: [], downloads: [], messages: [], tables: []};
  const elements = {};
  const node = (tag, text, cls) => ({tag, text, cls, children: [], events: {}, disabled: false,
    append(...children) {this.children.push(...children);},
    addEventListener(event, callback) {this.events[event] = callback;},
    remove() {this.removed = true;}});
  const context = {Blob, AbortSignal, Uint8Array, encodeURIComponent, csrf: 'token', node,
    $: key => elements[key] || (elements[key] = node('div')),
    fetch: async (...args) => {calls.requests.push(args); return fetcher(...args);},
    download: (...args) => calls.downloads.push(args), tell: (...args) => calls.messages.push(args),
    table: (target, headers, rows) => calls.tables.push({target, headers, rows})};
  vm.createContext(context); vm.runInContext(helpers + '\n' + archive, context);
  return {context, calls, elements};
}

function assertRecovered(button, calls, error) {
  assert.equal(button.disabled, false);
  assert.equal(calls.downloads.length, 0);
  assert.match(calls.messages[0][0], error);
  assert.equal(calls.messages[0][1], true);
}

test('native PNG uses an encoded saved ID, GET only, MIME and unchanged binary bytes', async () => {
  const bytes = png(), {context, calls} = harness(() => response(bytes, 'image/png; charset=binary'));
  await context.nativeChartDownload('a/b?c', 'saved-native.png');
  assert.equal(calls.requests[0][0], '/api/workbench/native-chart?id=a%2Fb%3Fc');
  assert.equal(calls.requests[0][1].method, undefined);
  assert.equal(calls.requests[0][1].body, undefined);
  const [blob, filename] = calls.downloads[0];
  assert.ok(blob instanceof Blob); assert.equal(blob.type, 'image/png');
  assert.deepEqual(Buffer.from(await blob.arrayBuffer()), bytes);
  assert.equal(filename, 'saved-native.png');
});

test('button captures identity and filename at creation across mutation, pending clicks and repeats', async () => {
  let resolve;
  const {context, calls} = harness(() => new Promise(r => {resolve = r;}));
  const record = {id, payload: {transient: 'must not be sent'}};
  const button = context.nativeChartButton(record);
  assert.equal(button.type, 'button'); assert.match(button.text, /原生.*PNG/);
  record.id = newerId;
  const pending = button.events.click();
  assert.equal(button.disabled, true);
  button.disabled = false; // The in-flight guard must not depend solely on DOM state.
  await button.events.click();
  assert.equal(calls.requests.length, 1);
  record.id = 'c'.repeat(64);
  resolve(response()); await pending;
  assert.equal(button.disabled, false);
  assert.equal(calls.requests[0][0], '/api/workbench/native-chart?id=' + id);
  assert.equal(calls.downloads[0][1], 'Invest-native_research-' + id.slice(0, 12) + '.png');
  assert.equal(calls.messages[0][1], undefined);
  const repeated = button.events.click(); resolve(response()); await repeated;
  assert.equal(calls.requests.length, 2);
  assert.equal(calls.requests[1][0], calls.requests[0][0]);
  assert.equal(calls.downloads[1][1], calls.downloads[0][1]);
});

test('native archive column is distinct while JSON and cash-study controls are retained', async () => {
  const {context, calls} = harness(() => response(JSON.stringify({documents: [{id, name: 'Saved native', recorded_at: 'now'}]}), 'application/json'));
  context.$('document-kind').value = 'native_research'; await context.loadDocuments();
  const native = calls.tables[0];
  assert.equal(native.headers.length, 4); assert.equal(native.headers[3], '原生研究图表');
  assert.equal(native.rows[0][2].children.length, 2);
  assert.equal(native.rows[0][2].children[1].text, '下载收益统计诊断');
  assert.equal(native.rows[0][2].children[0].text, '导出 JSON');
  assert.equal(native.rows[0][3].text, '下载原生研究 PNG');
  context.$('document-kind').value = 'study'; await context.loadDocuments();
  const study = calls.tables[1];
  assert.equal(study.headers.length, 3); assert.equal(study.rows[0].length, 3);
  assert.equal(study.rows[0][2].children.length, 2);
  assert.equal(study.rows[0][2].children[1].text, '图表 / 本地归档');
  context.$('document-kind').value = 'facts'; await context.loadDocuments();
  assert.equal(calls.tables[2].rows[0].length, 3);
  assert.equal(calls.tables[2].rows[0][2].children.length, 1);
});

test('archive reload during download keeps the old and new controls tied to their own records', async () => {
  const first = {id, name: 'First', recorded_at: 'then'};
  let documents = [first], resolve;
  const {context, calls} = harness(route => route.includes('/documents?')
    ? response(JSON.stringify({documents}), 'application/json')
    : new Promise(r => {resolve = r;}));
  context.$('document-kind').value = 'native_research'; await context.loadDocuments();
  const oldButton = calls.tables[0].rows[0][3], pending = oldButton.events.click();
  first.id = newerId; documents = [{id: newerId, name: 'Second', recorded_at: 'now'}];
  await context.loadDocuments();
  const newButton = calls.tables[1].rows[0][3];
  assert.notEqual(oldButton, newButton); assert.equal(newButton.disabled, false);
  resolve(response()); await pending;
  assert.equal(calls.downloads[0][1], 'Invest-native_research-' + id.slice(0, 12) + '.png');
  const next = newButton.events.click(); resolve(response()); await next;
  assert.equal(calls.downloads[1][1], 'Invest-native_research-' + newerId.slice(0, 12) + '.png');
  assert.equal(calls.requests[1][0], '/api/workbench/native-chart?id=' + id);
  assert.equal(calls.requests[3][0], '/api/workbench/native-chart?id=' + newerId);
});

for (const [name, fetchFailure, error] of [
  ['missing renderer', () => response('{"error":"install charts extra"}', 'application/json', 503), /install charts extra/],
  ['HTTP failure', () => response('unavailable', 'text/plain', 503), /503/],
  ['interrupted network', () => {throw new Error('network interrupted');}, /network interrupted/],
  ['aborted request', () => {throw new DOMException('request aborted', 'AbortError');}, /request aborted/],
  ['JSON success', () => response('{"ok":true}', 'application/json'), /不是 PNG/],
  ['wrong image MIME', () => response(png(), 'image/jpeg'), /不是 PNG/],
  ['empty PNG', () => response(Buffer.alloc(0)), /有效 PNG/],
  ['bad signature', () => response(Buffer.from('not a PNG')), /有效 PNG/],
  ['truncated PNG', () => response(png().subarray(0, -1)), /有效 PNG/],
  ['corrupted checksum', () => {const bytes = png(); bytes[32] ^= 1; return response(bytes);}, /有效 PNG/],
  ['trailing bytes', () => response(Buffer.concat([png(), Buffer.from('extra')])), /有效 PNG/],
]) test(name + ' creates no fake download and retry keeps the captured record', async () => {
  let attempt = 0;
  const {context, calls} = harness(() => ++attempt === 1 ? fetchFailure() : response());
  const record = {id}, button = context.nativeChartButton(record);
  await button.events.click(); assertRecovered(button, calls, error);
  record.id = newerId;
  await button.events.click();
  assert.equal(button.disabled, false); assert.equal(calls.downloads.length, 1);
  assert.equal(calls.requests[1][0], '/api/workbench/native-chart?id=' + id);
  assert.equal(calls.downloads[0][1], 'Invest-native_research-' + id.slice(0, 12) + '.png');
});

test('valid checksums cannot hide a missing IHDR, invalid dimensions or missing image data', async () => {
  const {header, data} = pngParts();
  const invalidHeaders = [Buffer.from(header), Buffer.from(header), Buffer.from(header)];
  invalidHeaders[0].writeUInt32BE(0, 0); invalidHeaders[1][8] = 7; invalidHeaders[2][10] = 1;
  const invalidPngs = [
    Buffer.concat([signature, chunk('IDAT', data), chunk('IEND')]),
    Buffer.concat([signature, chunk('IHDR', header), chunk('IEND')]),
    ...invalidHeaders.map(h => Buffer.concat([signature, chunk('IHDR', h), chunk('IDAT', data), chunk('IEND')]))
  ];
  for (const bytes of invalidPngs) {
    const {context, calls} = harness(() => response(bytes));
    await assert.rejects(context.nativeChartDownload(id, 'native.png'), /有效 PNG/);
    assert.equal(calls.downloads.length, 0);
  }
});

test('declared oversized or invalid lengths reject and cancel before reader allocation', async () => {
  for (const declared of [String(8 * 1024 * 1024 + 1), '-1', 'NaN']) {
    let cancelled = false;
    const {context, calls} = harness(() => ({ok: true,
      headers: {get: key => key === 'Content-Type' ? 'image/png' : declared},
      body: {cancel: async () => {cancelled = true;}, getReader() {assert.fail('reader acquired');}}}));
    await assert.rejects(context.nativeChartDownload(id, 'native.png'), /大小限制/);
    assert.equal(cancelled, true); assert.equal(calls.downloads.length, 0);
  }
});

test('streaming PNG enforces its actual byte limit, cancels overflow and releases reader', async () => {
  let cancelled = false, released = false;
  const {context, calls} = harness(() => ({ok: true,
    headers: {get: key => key === 'Content-Type' ? 'image/png' : null},
    body: {getReader: () => ({read: async () => ({done: false, value: new Uint8Array(8 * 1024 * 1024 + 1)}),
      cancel: async () => {cancelled = true;}, releaseLock: () => {released = true;}})}}));
  await assert.rejects(context.nativeChartDownload(id, 'native.png'), /大小限制/);
  assert.equal(cancelled, true); assert.equal(released, true); assert.equal(calls.downloads.length, 0);
});

test('interrupted body cancels and unlocks, then the same button can retry', async () => {
  let cancelled = false, released = false, attempt = 0;
  const {context, calls} = harness(() => ++attempt > 1 ? response() : ({ok: true,
    headers: {get: key => key === 'Content-Type' ? 'image/png' : null},
    body: {getReader: () => ({read: async () => {throw new Error('body interrupted');},
      cancel: async () => {cancelled = true;}, releaseLock: () => {released = true;}})}}));
  const button = context.nativeChartButton({id}); await button.events.click();
  assertRecovered(button, calls, /body interrupted/);
  assert.equal(cancelled, true); assert.equal(released, true);
  await button.events.click(); assert.equal(calls.downloads.length, 1); assert.equal(button.disabled, false);
});

test('multipart successful body is released and byte-identical with no content length', async () => {
  const bytes = png(); let index = 0, released = false;
  const chunks = [bytes.subarray(0, 4), bytes.subarray(4, 31), bytes.subarray(31)];
  const {context, calls} = harness(() => ({ok: true,
    headers: {get: key => key === 'Content-Type' ? 'image/png' : null},
    body: {getReader: () => ({read: async () => index < chunks.length ? {value: chunks[index++], done: false} : {done: true},
      cancel: async () => {assert.fail('valid stream cancelled');}, releaseLock: () => {released = true;}})}}));
  await context.nativeChartDownload(id, 'native.png');
  assert.equal(released, true);
  assert.deepEqual(Buffer.from(await calls.downloads[0][0].arrayBuffer()), bytes);
});

test('unexpected MIME cancels the unused body instead of saving it as PNG', async () => {
  let cancelled = false;
  const {context, calls} = harness(() => ({ok: true,
    headers: {get: () => 'image/png-bogus'},
    body: {cancel: async () => {cancelled = true;}, getReader() {assert.fail('unexpected body read');}}}));
  await assert.rejects(context.nativeChartDownload(id, 'native.png'), /不是 PNG/);
  assert.equal(cancelled, true); assert.equal(calls.downloads.length, 0);
});

test('missing streaming support fails closed without an unbounded blob fallback', async () => {
  const {context, calls} = harness(() => ({ok: true,
    headers: {get: key => key === 'Content-Type' ? 'image/png' : null},
    blob() {assert.fail('unbounded body read');}}));
  await assert.rejects(context.nativeChartDownload(id, 'native.png'), /有界图表下载/);
  assert.equal(calls.downloads.length, 0);
});

test('browser download failure does not announce success and releases the control for retry', async () => {
  const {context, calls} = harness();
  const save = context.download; let attempt = 0;
  context.download = (...args) => {if (++attempt === 1) throw new Error('download interrupted'); save(...args);};
  const button = context.nativeChartButton({id}); await button.events.click();
  assertRecovered(button, calls, /download interrupted/);
  await button.events.click();
  assert.equal(calls.downloads.length, 1); assert.equal(button.disabled, false);
  assert.equal(calls.downloads[0][1], 'Invest-native_research-' + id.slice(0, 12) + '.png');
});

test('fixed native-chart dimensions reject mismatches and huge compressed-image claims', async () => {
  for (const [width, height] of [[1, 1], [1201, 900], [1200, 899], [900, 1200], [0x7fffffff, 900], [1200, 0xffffffff]]) {
    const {header, data} = pngParts();
    header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4);
    const bytes = Buffer.concat([signature, chunk('IHDR', header), chunk('IDAT', data), chunk('IEND')]);
    const {context, calls} = harness(() => response(bytes));
    await assert.rejects(context.nativeChartDownload(id, 'native.png'), /有效 PNG/);
    assert.equal(calls.downloads.length, 0, `${width} x ${height} cannot produce a download`);
  }
});

test('served helper works with standard VM binary globals without injected constructors', async () => {
  const downloads = [];
  const context = {Blob, AbortSignal, encodeURIComponent, csrf: '', fetch: async () => response(),
    download: (...args) => downloads.push(args)};
  vm.createContext(context); vm.runInContext(helpers, context);
  await context.nativeChartDownload(id, 'native.png');
  assert.equal(downloads.length, 1);
  assert.deepEqual(Buffer.from(await downloads[0][0].arrayBuffer()), png());
});
