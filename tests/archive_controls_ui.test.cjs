// Actual helper state tests; no claim of browser-rendering acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness(response) {
  const source = fs.readFileSync(path.join(__dirname, '../invest/web/workbench.js'), 'utf8');
  const helper = source.slice(source.indexOf('function archiveControls('), source.indexOf('const pct='));
  const requests = [];
  const node = (tag, text) => ({tag, textContent: text, children: [], events: {}, attributes: {},
    append(...children) { this.children.push(...children); },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(event, callback) { this.events[event] = callback; }});
  const context = {node, api: async (...args) => { requests.push(args); return response(); }};
  vm.createContext(context);
  vm.runInContext(helper+'\nthis.create = archiveControls;', context);
  return {requests, create: context.create};
}

const id = 'a'.repeat(64);

test('failed archive explicitly preserves saved-research truth without leaking unknown details', () => {
  const {create} = harness(() => {});
  const panel = create({id, tracking: {status:'failed', reason:'archive_timeout'}});
  assert.match(panel.children[1].textContent, /归档超时.*研究记录已保存/);
  assert.equal(panel.children[1].attributes['aria-live'], 'polite');
  const untrusted = create({id, tracking: {status:'failed', reason:'private path or SDK payload'}});
  assert.doesNotMatch(untrusted.children[1].textContent, /private path/);
});

test('retry uses its saved record identity, disables during flight and displays committed reuse', async () => {
  let resolve;
  const {create, requests} = harness(() => new Promise(r => {resolve = r;}));
  const panel = create({id});
  const note = panel.children[1], button = panel.children[2];
  const pending = button.events.click();
  assert.equal(button.disabled, true);
  assert.equal(requests[0][0], '/api/workbench/track-study');
  assert.equal(requests[0][1].study_id, id);
  resolve({study_id:id,tracking:{status:'archived',reused:true}});
  await pending;
  assert.match(note.textContent, /复用同一记录.*没有重复/);
  assert.equal(button.disabled, false);
});

test('disabled mode remains explicit and never silently enables the archive', async () => {
  const {create, requests} = harness(() => ({study_id:id,tracking:{status:'disabled'}}));
  const panel = create({id});
  await panel.children[2].events.click();
  assert.match(panel.children[1].textContent, /当前关闭.*研究仍已保存/);
  assert.deepEqual(Object.keys(requests[0][1]), ['study_id']);
});

test('mismatched or failed replies cannot claim success and allow another attempt', async () => {
  for (const response of [() => ({study_id:'wrong',tracking:{status:'archived'}}),
                          () => {throw new Error('request interrupted');}]) {
    const {create} = harness(response);
    const panel = create({id});
    await panel.children[2].events.click();
    assert.match(panel.children[1].textContent, /未完成.*原研究记录保留/);
    assert.doesNotMatch(panel.children[1].textContent, /归档已完成/);
    assert.equal(panel.children[2].disabled, false);
  }
});
