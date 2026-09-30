'use strict';
const $=id=>document.getElementById(id);
let csrf='',dataset=null,lastStudy=null;
let eventRetry=null,reviewKey=crypto.randomUUID();
function tell(message,error=false){const el=$('message');el.hidden=false;el.textContent=message;el.classList.toggle('error',error);}
function node(tag,value,cls){const e=document.createElement(tag);if(value!==undefined)e.textContent=String(value);if(cls)e.className=cls;return e;}
function view(name){document.querySelectorAll('[data-panel]').forEach(e=>e.hidden=e.dataset.panel!==name);document.querySelectorAll('.sidebar [data-view]').forEach(e=>e.classList.toggle('active',e.dataset.view===name));if(name==='archive')loadDocuments().catch(e=>tell(e.message,true));}
document.querySelectorAll('[data-view]').forEach(e=>e.addEventListener('click',()=>view(e.dataset.view)));
async function api(path,payload){const opts={headers:{},signal:AbortSignal.timeout(60000)};if(payload!==undefined){opts.method='POST';opts.headers={'Content-Type':'application/json','X-Invest-CSRF':csrf};opts.body=JSON.stringify(payload);}const response=await fetch(path,opts);const type=response.headers.get('Content-Type')||'';const data=type.includes('json')?await response.json():await response.blob();if(!response.ok)throw new Error(data.error||`请求失败 (${response.status})`);return data;}
function action(id,fn,event='click'){$(id).addEventListener(event,async ev=>{ev.preventDefault();const el=ev.currentTarget;const button=el.tagName==='FORM'?el.querySelector('[type=submit]'):el;button.disabled=true;try{await fn(ev);}catch(e){tell(e.message||String(e),true);}finally{button.disabled=false;}});}
function table(target,headers,rows){const wrapper=node('div',undefined,'table-wrap'),t=node('table'),head=node('thead'),hr=node('tr');headers.forEach(h=>hr.append(node('th',h)));head.append(hr);t.append(head);const body=node('tbody');rows.forEach(row=>{const r=node('tr');row.forEach(cell=>{const td=node('td');cell instanceof Node?td.append(cell):td.textContent=String(cell??'—');r.append(td);});body.append(r);});t.append(body);wrapper.append(t);target.replaceChildren(wrapper);}
function pretty(target,value){target.replaceChildren(node('pre',JSON.stringify(value,null,2)));}
function metrics(target,items){const wrap=node('div',undefined,'metrics');items.forEach(([label,value])=>{const m=node('div',undefined,'metric');m.append(node('small',label),node('strong',value??'—'));wrap.append(m);});target.replaceChildren(wrap);}
function download(value,name){const blob=value instanceof Blob?value:new Blob([JSON.stringify(value,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function chartPicker(record){
  const panel=node('div'),label=node('label','导出已保存实验的净值与回撤图'),select=node('select'),button=node('button','下载 PNG 图表','secondary');
  const selectorId='chart-case-'+record.id+'-'+crypto.randomUUID();select.id=selectorId;label.htmlFor=selectorId;
  record.payload.results.forEach((row,index)=>{if(row.status==='PASS')select.add(new Option(`${index+1} · ${row.period} · ${row.candidate} · ${row.cost}`,String(index)));});
  button.type='button';button.disabled=select.options.length===0;
  button.addEventListener('click',async()=>{const selected=select.value;button.disabled=true;try{download(await api('/api/workbench/study-chart?id='+encodeURIComponent(record.id)+'&case='+encodeURIComponent(selected)),'Invest-study-'+record.id.slice(0,12)+'-case-'+selected+'.png');tell('图表已从保存记录生成。完整身份写入 PNG；合成或未核验来源仍保留标记。');}catch(e){tell(e.message,true);}finally{button.disabled=select.options.length===0;}});
  panel.append(label,select,button,node('p','需要可选 charts 扩展；图表是保存曲线的视图，不重新运行实验。失败记录继续保存在完整 JSON 中。','muted'));return panel;
}
function archiveControls(record){
  const panel=node('div'),note=node('p'),button=node('button','核对 / 重试本地归档','secondary');
  note.setAttribute('role','status');note.setAttribute('aria-live','polite');button.type='button';
  function show(status){
    const state=status&&typeof status==='object'?status.status:'unknown';
    if(state==='archived'){note.textContent='本地归档已完成'+(status.reused?'，已复用同一记录，没有重复追加。':'。');button.textContent='再次核对本地归档';}
    else if(state==='disabled'){note.textContent='本地归档当前关闭；完整研究仍已保存在本机。源码启动时可安装 mlflow 扩展并加 --track-experiments 启用。';}
    else if(state==='failed'){
      const reasons={archive_timeout:'归档超时',archive_busy:'另一归档正在占用本机目录',local_archive_unavailable:'本机归档暂不可用',mlflow_extra_required:'未安装可选 MLflow 扩展',unsupported_mlflow_version:'MLflow 版本不匹配',source_python_required:'需要源码 Python 环境'};
      note.textContent=(reasons[status.reason]||'归档未完成')+'；研究记录已保存，可以稍后重试。';
    }else note.textContent='研究已保存；本地归档状态尚未核对。';
  }
  show(record.tracking);
  button.addEventListener('click',async()=>{button.disabled=true;try{
    const response=await api('/api/workbench/track-study',{study_id:record.id});
    if(response.study_id!==record.id)throw new Error('归档响应身份不匹配；原研究记录保留。');
    show(response.tracking);
  }catch(e){note.textContent='归档核对未完成：'+e.message+'。原研究记录保留。';}finally{button.disabled=false;}});
  panel.append(node('h4','本地研究归档'),note,button);return panel;
}
const pct=x=>x===null||x===undefined?'—':(Number(x)*100).toFixed(2)+'%';
async function loadDatasets(selected){const r=await api('/api/datasets');const keep=selected||$('dataset').value;$('dataset').replaceChildren(new Option('请选择数据集',''));r.datasets.forEach(d=>$('dataset').add(new Option(`${d.meta.source_kind==='demo'?'[合成] ':''}${d.start} → ${d.end} · ${d.rows}行 · ${d.id.slice(0,8)}`,d.id)));if(r.datasets.some(d=>d.id===keep))$('dataset').value=keep;if($('dataset').value)await chooseDataset();}
async function chooseDataset(){if(!$('dataset').value){dataset=null;return; }dataset=await api('/api/datasets/'+$('dataset').value);const symbols=[...new Set(dataset.bars.map(b=>b.symbol))];$('study-symbol').replaceChildren(...symbols.map(s=>new Option(s,s)));$('source-banner').textContent=(dataset.meta.source_kind==='demo'?'合成演示 · 不是真实行情。 ':'导入数据 · 来源真实性与许可未独立核验。 ')+dataset.meta.source;pretty($('audit-output'),dataset.audit);}
function needDataset(){if(!dataset)throw new Error('请先载入或选择数据集');return dataset.id;}
action('dataset',chooseDataset,'change');
action('demo',async()=>{const d=await api('/api/datasets/demo',{});await loadDatasets(d.id);tell('合成演示已载入。数据与结果不代表真实投资表现。');});
action('receipt',async()=>{const d=await api('/api/workbench/receipt',{dataset_id:needDataset(),declaration:{license_note:$('license').value}});pretty($('receipt-output'),d);tell('审计回执已保存，未把来源声明提升为独立核验。');});
action('study-mode',async()=>{const disabled=$('study-mode').value!=='walk-forward';$('walk-forward-settings').hidden=disabled;$('study-gap').disabled=disabled;},'change');
action('study-form',async()=>{
  const specification={symbol:$('study-symbol').value,initial_cash:Number($('study-cash').value),candidates:JSON.parse($('candidates').value),cost_model_acknowledged:$('cost-ack').checked};
  if($('study-mode').value==='walk-forward')specification.walk_forward={n_splits:3,gap:Number($('study-gap').value)};
  const r=await api('/api/workbench/study',{dataset_id:needDataset(),specification});
  lastStudy=r;const p=r.payload;
  metrics($('study-output'),[['计划评价',p.summary.planned],['算术回放通过',p.summary.succeeded],['保留的失败',p.summary.failed]]);
  const out=node('div');
  table(out,['样本段','候选','成本','状态','收益','买入持有','相对基准 / 失败原因'],p.results.map(row=>[row.period,row.candidate,row.cost,row.status==='PASS'?'通过':'失败',pct(row.result?.metrics.total_return),pct(row.result?.metrics.benchmark_return),row.reason||pct(row.excess_vs_buy_hold)]));
  $('study-output').append(out);
  if(p.protocol.mode==='EXPLORATORY_WALK_FORWARD'){
    $('study-output').append(node('h4','先训练选候选，再独立评价'));
    const windows=node('div');
    table(windows,['折','训练窗口','间隔交易日','评价窗口'],p.protocol.folds.map(f=>[f.fold,`${f.train.start} → ${f.train.end}`,f.gap_sessions,`${f.test.start} → ${f.test.end}`]));
    const details=node('details'),training=node('div');
    details.append(node('summary','查看全部训练候选（含失败）'));
    table(training,['折','成本','候选','训练相对基准','状态 / 原因'],p.results.flatMap(row=>row.training.map(t=>[row.fold,row.cost,t.candidate,pct(t.excess_vs_buy_hold),t.reason||t.status])));
    details.append(training);$('study-output').append(windows,details);
  }
  $('study-output').append(node('p',p.limitations.join('；')),chartPicker(r),archiveControls(r));$('study-export').hidden=false;
  tell(`已保存 ${p.summary.planned} 项评价，失败 ${p.summary.failed} 项。未打开冻结留出集。`);
},'submit');
action('study-export',async()=>download(lastStudy,'Invest-study-'+lastStudy.id.slice(0,12)+'.json'));
async function loadReviews(selected){const r=await api('/api/workbench/documents?kind=review');const keep=selected||$('review-select').value;$('review-select').replaceChildren(new Option('请选择复盘账户',''));r.documents.forEach(d=>$('review-select').add(new Option(d.name,d.id)));if(r.documents.some(d=>d.id===keep))$('review-select').value=keep;if($('review-select').value)await refreshReview();}
function showReview(r){const s=r.state;metrics($('review-output'),[['现金 / 元',s.cash],['按末次价格净资产',s.net_assets_on_last_marks],['观测点时间加权收益',pct(s.time_weighted_return)]]);const detail=node('div');table(detail,['资金净流入','股息','累计费用','估值口径利润'],[[s.net_external_flows,s.cash_dividends,s.total_fees,s.profit_on_last_marks]]);$('review-output').append(detail,node('p',s.warnings.join('；')));if(s.positions.length){const ps=node('div');table(ps,['标的','股数','末次估值价格','估值时间'],s.positions.map(p=>[p.symbol,p.quantity,p.marked_price,p.marked_at]));$('review-output').append(ps);}table($('events-output'),['序号','事件','发生时间','服务器记录时间','哈希'],r.events.map(e=>[e.sequence,e.event.type,e.event.occurred_at,e.recorded_at,e.hash.slice(0,16)]));}
async function refreshReview(){if(!$('review-select').value)return;showReview(await api('/api/workbench/review?id='+$('review-select').value));}
action('review-select',refreshReview,'change');
action('review-form',async()=>{const d=await api('/api/workbench/reviews',{name:$('review-name').value,initial_cash:$('review-cash').value,manual_record_acknowledged:$('manual-ack').checked,client_key:reviewKey});reviewKey=crypto.randomUUID();await loadReviews(d.id);tell('人工复盘账户已创建。');},'submit');
const eventDefaults={DEPOSIT:{amount:'1000.00'},WITHDRAWAL:{amount:'1000.00'},FEE:{amount:'5.00'},DIVIDEND:{symbol:'600000.SH',amount:'10.00'},BUY:{symbol:'600000.SH',quantity:100,price:'10.00',fee:'5.00'},SELL:{symbol:'600000.SH',quantity:100,price:'11.00',fee:'5.00'},MARK:{prices:{'600000.SH':'10.50'}},DECISION:{reason:'记录支持证据、反证与判断失效条件',evidence_at:'2024-01-01T16:00:00+08:00'},FAILURE:{reason:'数据更新失败，未生成替代结果'},RETRY:{reason:'记录重试对象、原因和结果'}};
$('event-type').addEventListener('change',()=>{$('event-fields').value=JSON.stringify(eventDefaults[$('event-type').value],null,2);});
action('event-form',async()=>{const review_id=$('review-select').value;if(!review_id)throw new Error('先创建或选择复盘账户');const event={...JSON.parse($('event-fields').value),type:$('event-type').value,occurred_at:$('event-time').value,source:$('event-source').value};const signature=JSON.stringify({review_id,event});if(!eventRetry||eventRetry.signature!==signature)eventRetry={signature,key:crypto.randomUUID()};const result=await api('/api/workbench/event',{review_id,event_key:eventRetry.key,event});showReview(result);eventRetry=null;tell('事件已校验并追加。哈希链与现金余额已重新核对。');},'submit');
async function loadDocuments(){const kind=$('document-kind').value;const r=await api('/api/workbench/documents?kind='+kind);table($('documents-output'),['身份 / 名称','保存时间','操作'],r.documents.map(d=>{const b=node('button','导出 JSON','secondary');b.addEventListener('click',async()=>{try{download(await api('/api/workbench/document?id='+d.id),'Invest-'+kind+'-'+d.id.slice(0,12)+'.json');}catch(e){tell(e.message,true);}});const operations=node('div');operations.append(b);if(kind==='study'){const charts=node('button','图表 / 本地归档','secondary');charts.type='button';charts.addEventListener('click',async()=>{charts.disabled=true;try{const record=await api('/api/workbench/document?id='+encodeURIComponent(d.id));operations.append(chartPicker(record),archiveControls(record));charts.remove();}catch(e){charts.disabled=false;tell(e.message,true);}});operations.append(charts);}return[d.name,d.recorded_at,operations];}));}
action('refresh-documents',loadDocuments);action('document-kind',loadDocuments,'change');
action('backup',async()=>{if(!$('backup-ack').checked)throw new Error('请先确认备份包含私人账本和笔记');download(await api('/api/private-backup',{confirm_private_export:true}),'Invest-complete-private-backup.zip');tell('完整备份已生成。请妥善保存私人数据。');});
const sampleFacts={source_name:'合成财务事实样例，不对应真实公司披露',source_text:'虚构指标：2023年末利润；2024-03-01首次披露10，2024-05-01修订为8。仅测试时点过滤。',license_note:'人工合成测试，不含真实公告数据',facts:[{symbol:'600000.SH',metric:'net_profit',period_end:'2023-12-31',available_at:'2024-03-01T16:00:00+08:00',revision:1,value:'10',unit:'CNY million'},{symbol:'600000.SH',metric:'net_profit',period_end:'2023-12-31',available_at:'2024-05-01T16:00:00+08:00',revision:2,value:'8',unit:'CNY million'}]};
action('facts-example',async()=>{$('facts-json').value=JSON.stringify(sampleFacts,null,2);tell('已填入明确标注的合成事实样例，尚未保存。');});
async function loadFacts(selected){const r=await api('/api/workbench/documents?kind=facts');const keep=selected||$('facts-select').value;$('facts-select').replaceChildren(new Option('请选择事实包',''));r.documents.forEach(d=>$('facts-select').add(new Option(d.name,d.id)));if(r.documents.some(d=>d.id===keep))$('facts-select').value=keep;}
action('facts-import',async()=>{const d=await api('/api/workbench/facts',{enabled:$('facts-enabled').checked,bundle:JSON.parse($('facts-json').value)});await loadFacts(d.id);tell('事实包已校验保存。来源和可见时间仍属于声明信息。');});
action('facts-query',async()=>{const r=await api('/api/workbench/as-of',{enabled:$('facts-enabled').checked,bundle_id:$('facts-select').value,symbol:$('facts-symbol').value,as_of:$('facts-time').value});pretty($('facts-output'),r);tell(r.enabled?`选中当时已可见的 ${r.facts.length} 条事实。`:'扩展已关闭，未读取事实包，核心研究不受影响。');});
async function loadVersion(){const r=await api('/api/workbench/status');if(typeof r.version!=='string'||!r.version)throw new Error('版本信息不可用');$('app-version').textContent=r.version;}
(async()=>{try{csrf=(await api('/api/config')).csrf_token;await Promise.all([loadVersion(),loadDatasets(),loadReviews(),loadFacts()]);}catch(e){tell('初始化未完成：'+e.message,true);}})();
