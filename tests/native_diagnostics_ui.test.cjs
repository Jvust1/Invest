const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),test=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../invest/web/workbench.js'),'utf8');
const helpers=source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action('));
const archive=source.slice(source.indexOf('async function loadDocuments('),source.indexOf("action('refresh-documents'"));
const id='a'.repeat(64),raw='{"record_id":"'+id+'","value":1.0,"schema":"invest-native-diagnostics-v1"}';
function harness(fetcher=()=>new Response(raw,{headers:{'Content-Type':'application/json'}})){
 const calls={requests:[],downloads:[],messages:[],tables:[]},elements={};
 const node=(tag,text)=>({tag,text,children:[],events:{},disabled:false,append(...x){this.children.push(...x)},addEventListener(k,f){this.events[k]=f}});
 const context={Blob,AbortSignal,encodeURIComponent,csrf:'',node,$:k=>elements[k]||(elements[k]=node('div')),
 fetch:async(...args)=>{calls.requests.push(args);return fetcher(...args)},download:(...x)=>calls.downloads.push(x),tell:(...x)=>calls.messages.push(x),table:(...x)=>calls.tables.push(x)};
 vm.createContext(context);vm.runInContext(helpers+'\n'+archive,context);return {context,calls};
}
test('diagnostics uses encoded saved ID and exact bounded raw JSON bytes',async()=>{
 const {context,calls}=harness();await context.nativeDiagnosticsDownload('a/b?c','diagnostics.json');
 assert.equal(calls.requests[0][0],'/api/workbench/native-diagnostics?id=a%2Fb%3Fc');
 assert.equal(calls.requests[0][1].method,undefined);assert.equal(calls.requests[0][1].body,undefined);
 assert.equal(await calls.downloads[0][0].text(),raw);assert.equal(calls.downloads[0][1],'diagnostics.json');
});
test('captures original identity, suppresses repeated clicks, and reenables',async()=>{
 let resolve;const {context,calls}=harness(()=>new Promise(r=>resolve=r));const record={id};const button=context.nativeDiagnosticsButton(record);
 record.id='b'.repeat(64);const pending=button.events.click();assert.equal(button.disabled,true);
 button.disabled=false;await button.events.click();assert.equal(calls.requests.length,1);
 resolve(new Response(raw,{headers:{'Content-Type':'application/json'}}));await pending;
 assert.equal(button.disabled,false);assert.equal(calls.requests[0][0],'/api/workbench/native-diagnostics?id='+id);
 assert.equal(calls.downloads[0][1],'Invest-native-diagnostics-'+id.slice(0,12)+'.json');assert.match(calls.messages[0][0],/探索性/);
});
test('dependency errors preserve retry without inventing output',async()=>{
 let ok=false;const {context,calls}=harness(()=>new Response(ok?raw:'{"error":"需要 diagnostics 扩展"}',{status:ok?200:503,headers:{'Content-Type':'application/json'}}));
 const button=context.nativeDiagnosticsButton({id});await button.events.click();assert.equal(button.disabled,false);assert.equal(calls.downloads.length,0);assert.match(calls.messages[0][0],/diagnostics/);
 ok=true;await button.events.click();assert.equal(calls.downloads.length,1);
});
test('wrong type and oversized responses do not create a diagnostic file',async()=>{
 for(const response of [new Response('x',{headers:{'Content-Type':'image/png'}}),new Response('{}',{headers:{'Content-Type':'application/json','Content-Length':String(9*1024*1024)}})]){
  const {context,calls}=harness(()=>response);await assert.rejects(context.nativeDiagnosticsDownload(id,'d.json'));assert.equal(calls.downloads.length,0);
 }
});
test('archive retains JSON and PNG and adds native-only diagnostics',async()=>{
 const {context,calls}=harness(()=>new Response(JSON.stringify({documents:[{id,name:'Saved',recorded_at:'now'}]}),{headers:{'Content-Type':'application/json'}}));
 context.$('document-kind').value='native_research';await context.loadDocuments();const row=calls.tables[0][2][0];
 assert.equal(row[2].children[0].text,'导出 JSON');assert.equal(row[2].children[1].text,'下载收益统计诊断');assert.equal(row[3].text,'下载原生研究 PNG');
 context.$('document-kind').value='facts';await context.loadDocuments();assert.equal(calls.tables[1][2][0][2].children.length,1);
});
