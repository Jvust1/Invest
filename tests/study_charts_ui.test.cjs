// Small unit harness for the actual browser helper; not browser/layout evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness(response) {
  const source = fs.readFileSync(path.join(__dirname, '../invest/web/workbench.js'), 'utf8');
  const helper = source.slice(source.indexOf('function chartPicker('), source.indexOf('const pct='));
  const calls = {requests: [], downloads: [], messages: []};
  const node = (tag, text, cls) => ({tag, text, cls, children: [], options: [], events: {}, value: '',
    append(...children) { this.children.push(...children); },
    add(option) { this.options.push(option); if (this.options.length === 1) this.value = option.value; },
    addEventListener(event, callback) { this.events[event] = callback; }});
  const context = {node, Option: function(text, value) { Object.assign(this, {text, value}); },
    crypto: {randomUUID: () => 'unique'}, encodeURIComponent,
    api: async route => { calls.requests.push(route); return response(); },
    download: (...args) => calls.downloads.push(args), tell: (...args) => calls.messages.push(args)};
  vm.createContext(context);
  vm.runInContext(helper + '\nthis.chartPicker = chartPicker;', context);
  return {calls, create: context.chartPicker};
}

const record = {id: 'a'.repeat(64), payload: {results: [
  {status: 'FAILED', period: 'failed', candidate: 'first', cost: 'low'},
  {status: 'PASS', period: '<period>', candidate: '$candidate$', cost: 'high'},
  {status: 'PASS', period: 'second', candidate: 'other', cost: 'low'},
]}};

test('only successful curves are selectable, retaining original result indices and literal labels', () => {
  const {create} = harness(() => 'png');
  const [label, select, button] = create(record).children;
  assert.equal(label.htmlFor, select.id);
  assert.equal(select.options.length, 2);
  assert.equal(select.options[0].value, '1');
  assert.match(select.options[0].text, /<period>.*\$candidate\$/);
  assert.equal(button.disabled, false);
});

test('click uses a stable case snapshot, disables during request and recovers after success', async () => {
  let resolve;
  const {create, calls} = harness(() => new Promise(r => {resolve = r;}));
  const [, select, button] = create(record).children;
  const pending = button.events.click();
  assert.equal(button.disabled, true);
  select.value = '2';
  resolve('png bytes');
  await pending;
  assert.match(calls.requests[0], /&case=1$/);
  assert.equal(calls.downloads[0][0], 'png bytes');
  assert.match(calls.downloads[0][1], /-case-1\.png$/);
  assert.equal(button.disabled, false);
});

test('missing renderer surfaces its error without a fake download and permits retry', async () => {
  const {create, calls} = harness(() => {throw new Error('install charts');});
  const button = create(record).children[2];
  await button.events.click();
  assert.equal(button.disabled, false);
  assert.equal(calls.downloads.length, 0);
  assert.equal(calls.messages[0][0], 'install charts');
  assert.equal(calls.messages[0][1], true);
});

test('all-failed study exposes no invented chart option', () => {
  const {create} = harness(() => 'unused');
  const [, select, button] = create({id: record.id, payload: {results: [record.payload.results[0]]}}).children;
  assert.equal(select.options.length, 0);
  assert.equal(button.disabled, true);
});
