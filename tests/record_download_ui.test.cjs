// Actual browser helper byte/state tests, not browser-layout acceptance.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../invest/web/workbench.js'),'utf8');
const helpers=source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action('));
const actionHelper=source.slice(source.indexOf('function action('),source.indexOf('function table('));
const studyAction=source.split('\n').find(line=>line.startsWith("action('study-export'"));
const id='a'.repeat(64);

function harness(fetcher){
  const calls={requests:[],downloads:[],messages:[]};
  const elements={};
  const node=(tag,text)=>({tag,text,children:[],events:{},disabled:false,
    append(...values){this.children.push(...values);},
    addEventListener(event,callback){this.events[event]=callback;}});
  const context={Blob,AbortSignal,Uint8Array,Number,encodeURIComponent,csrf:'token',
    node,$:key=>elements[key]||(elements[key]=node('button')),
    fetch:async(...args)=>{calls.requests.push(args);return fetcher(...args);},
    download:(...args)=>calls.downloads.push(args),tell:(...args)=>calls.messages.push(args)};
  vm.createContext(context);vm.runInContext(helpers+actionHelper,context);
  return {context,calls,elements,node};
}
function response(raw,status=200){return new Response(raw,{status,headers:{'Content-Type':'application/json'}});}

for(const [name,raw] of [
  ['float and large integer','{"value":1.0,"large":9007199254740993,"small":1e-20,"unicode":"行情😀"}'],
  ['historical native report',fs.readFileSync(path.join(__dirname,'fixtures/native_research_v1_synthetic.json'),'utf8')],
])test('raw '+name+' remains byte-identical without JSON parsing',async()=>{
  const {context,calls}=harness(()=>{const r=response(raw);r.json=()=>assert.fail('raw response was parsed');return r;});
  const blob=await context.api('/api/workbench/document?id='+id,undefined,{raw:true});
  assert.ok(blob instanceof Blob);assert.equal(await blob.text(),raw);
  assert.deepEqual(Buffer.from(await blob.arrayBuffer()),Buffer.from(raw));
  assert.equal(calls.requests[0][1].method,undefined);
});

test('saved download requests persisted encoded identity and never exports transient tracking',async()=>{
  const raw='{"id":"saved","payload":{"value":1.0}}';
  const {context,calls}=harness(()=>response(raw));
  await context.savedRecordDownload('a/b?c','saved.json');
  assert.equal(calls.requests[0][0],'/api/workbench/document?id=a%2Fb%3Fc');
  assert.equal(calls.requests[0][1].body,undefined);
  assert.equal(calls.downloads[0][1],'saved.json');
  assert.equal(await calls.downloads[0][0].text(),raw);
});

test('normal JSON and binary API requests retain their behavior',async()=>{
  let attempt=0;
  const {context,calls}=harness(()=>++attempt===1?response('{"ok":true}'):new Response('png/zip',{headers:{'Content-Type':'application/octet-stream'}}));
  assert.equal((await context.api('/normal',{hello:'world'})).ok,true);
  assert.equal(calls.requests[0][1].method,'POST');
  assert.equal(calls.requests[0][1].headers['X-Invest-CSRF'],'token');
  assert.equal(calls.requests[0][1].body,'{"hello":"world"}');
  assert.equal(await (await context.api('/binary')).text(),'png/zip');
});

test('failed raw JSON request reports error without creating a download and can retry',async()=>{
  let attempt=0;
  const {context,calls}=harness(()=>++attempt===1?response('{"error":"校验失败"}',400):response('{"value":1.0}'));
  await assert.rejects(context.savedRecordDownload(id,'record.json'),/校验失败/);
  assert.equal(calls.downloads.length,0);
  await context.savedRecordDownload(id,'record.json');
  assert.equal(calls.downloads.length,1);
  assert.equal(await calls.downloads[0][0].text(),'{"value":1.0}');
});

test('raw document rejects unexpected binary success',async()=>{
  const {context}=harness(()=>new Response('not json',{headers:{'Content-Type':'text/plain'}}));
  await assert.rejects(context.api('/record',undefined,{raw:true}),/不是 JSON/);
});

test('oversized declared body is rejected before reader allocation',async()=>{
  const {context}=harness(()=>({ok:true,headers:{get:key=>key==='Content-Type'?'application/json':String(9*1024*1024)},
    body:{getReader(){assert.fail('oversized body reader acquired');}}}));
  await assert.rejects(context.api('/record',undefined,{raw:true}),/大小限制/);
});

test('streaming body enforces byte limit and cancels overflow',async()=>{
  let cancelled=false;
  const {context}=harness(()=>new Response(new ReadableStream({
    start(controller){controller.enqueue(new Uint8Array(8*1024*1024+4097));},
    cancel(){cancelled=true;}
  }),{headers:{'Content-Type':'application/json'}}));
  await assert.rejects(context.api('/record',undefined,{raw:true}),/大小限制/);
  assert.equal(cancelled,true);
});

test('interrupted stream cancels and releases the lock',async()=>{
  let cancelled=false,released=false;
  const {context}=harness(()=>({ok:true,headers:{get:key=>key==='Content-Type'?'application/json':null},body:{getReader:()=>({
    read:async()=>{throw new Error('interrupted stream');},cancel:async()=>{cancelled=true;},releaseLock:()=>{released=true;}
  })}}));
  await assert.rejects(context.api('/record',undefined,{raw:true}),/interrupted stream/);
  assert.equal(cancelled,true);assert.equal(released,true);
});

test('new-study export keeps one captured ID and filename while a newer study arrives',async()=>{
  let resolve;
  const raw='{"id":"'+id+'","payload":{"value":1.0}}';
  const {context,calls,elements}=harness(()=>new Promise(r=>{resolve=r;}));
  context.lastStudy={id,tracking:{status:'archived',secret_transient:'excluded'}};
  vm.runInContext(studyAction,context);
  const button=elements['study-export'];
  const pending=button.events.click({preventDefault(){},currentTarget:button});
  assert.equal(button.disabled,true);
  context.lastStudy={id:'b'.repeat(64)};
  resolve(response(raw));await pending;
  assert.equal(calls.requests[0][0],'/api/workbench/document?id='+id);
  assert.equal(calls.downloads[0][1],'Invest-study-'+id.slice(0,12)+'.json');
  assert.equal(await calls.downloads[0][0].text(),raw);
  assert.equal(button.disabled,false);
});

test('new-study export recovers from download failure without a fake file',async()=>{
  const {context,calls,elements}=harness(()=>response('{"error":"busy"}',409));
  context.lastStudy={id};vm.runInContext(studyAction,context);
  const button=elements['study-export'];await button.events.click({preventDefault(){},currentTarget:button});
  assert.equal(button.disabled,false);assert.equal(calls.downloads.length,0);
  assert.equal(calls.messages[0][0],'busy');
});

test('archive exports use raw saved-record helper and suppress repeated pending clicks',async()=>{
  let resolve;
  const {context,calls,elements}=harness(route=>route.includes('documents?')?response(JSON.stringify({documents:[{id,name:'Native',recorded_at:'now'}]})):new Promise(r=>{resolve=r;}));
  context.$('document-kind').value='native_research';
  let rows;
  context.table=(_target,_headers,value)=>{rows=value;};
  vm.runInContext(source.slice(source.indexOf('async function loadDocuments('),source.indexOf("action('refresh-documents'")),context);
  await context.loadDocuments();
  const button=rows[0][2].children[0];
  const pending=button.events.click();assert.equal(button.disabled,true);
  await button.events.click();assert.equal(calls.requests.length,2);
  elements['document-kind'].value='study';
  resolve(response('{"n":1.0}'));await pending;
  assert.equal(button.disabled,false);
  assert.equal(calls.downloads[0][1],'Invest-native_research-'+id.slice(0,12)+'.json');
  assert.equal(await calls.downloads[0][0].text(),'{"n":1.0}');
  assert.equal(rows[0][2].children.length,1); // No cash chart/archive controls for native records.
});
