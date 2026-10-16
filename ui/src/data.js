export const SHAPES = {answered_with_path:{label:'Answered with a path',tone:'green'},answered_from_memory:{label:'Answered from memory',tone:'purple'},not_in_graph:{label:'Not in the graph',tone:'amber'},unknown_entity:{label:'Unknown entity',tone:'red'}};
export const labelFor = id => String(id||'').startsWith('ACC')?'Account':String(id||'').startsWith('PER')?'Person':String(id||'').startsWith('DEV')?'Device':String(id||'').startsWith('PH')?'Phone':String(id||'').startsWith('ADD')?'Address':'Entity';
export const rupees = value => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value||0)/100);
export const ist = value => value==null||value===''?'—':new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}).format(new Date(typeof value==='number'?value*1000:value))+' IST';
export function normaliseShape(result={}){let shape=result.shape||result.outcome||'not_in_graph';return SHAPES[shape]?shape:'not_in_graph';}
export function evidenceFrom(results=[]){
 const rows=new Map();
 function walk(value,tool,parent={}){
  if(Array.isArray(value)){value.forEach(x=>walk(x,tool,parent));return;}
  if(!value||typeof value!=='object')return;
  const context={...parent,...value};
  const id=value.tx_id||value.tx||(/^(TX-|TX\d)/.test(value.id||'')?value.id:null);
  if(id&&(value.amount!=null||value.ts!=null))rows.set(`${id}:${tool}`,{id,amount:value.amount,ts:value.ts,from:value.from||value.source||parent.from||parent.account||parent.source,to:value.to||value.target||parent.to||parent.account||parent.gatherer,rail:value.rail||parent.rail||'—',tool,memo:value.memo,guard_hits:value.guard_hits});
  for(const key of Object.keys(value))if(value[key]&&typeof value[key]==='object')walk(value[key],tool,context);
 }
 results.forEach(r=>walk(r,r.tool||r.name||'graph tool'));
 return [...rows.values()];
}
export function graphFrom(results=[]){
 const nodes=new Map(),links=new Map(),paths=[];
 const addNode=n=>{if(typeof n==='string')n={id:n,label:labelFor(n)};if(n?.id&&!nodes.has(n.id)&&nodes.size<1000)nodes.set(n.id,{...n,label:n.label||labelFor(n.id)});};
 const addLink=(edge,src,dst)=>{const source=edge.from||edge.source||src,target=edge.to||edge.target||dst;if(!source||!target)return;addNode(source);addNode(target);const id=edge.id||edge.tx||`${source}:${target}:${edge.type||edge.kind||''}`;if(nodes.has(source)&&nodes.has(target))links.set(id,{...edge,id,source,target,type:edge.type||edge.kind||(edge.amount!=null?'TX':'LINK')});};
 function walk(v){if(Array.isArray(v)){v.forEach(walk);return;}if(!v||typeof v!=='object')return;
  if(v.path_nodes)v.path_nodes.forEach(addNode);
  if(v.path_edges)v.path_edges.forEach(e=>addLink(e));
  const ids=v.path_ids||v.node_ids||(Array.isArray(v.accounts)?v.accounts:null);
  if(ids?.length){paths.push(ids);ids.forEach(addNode);ids.slice(0,-1).forEach((id,i)=>{let e=v.edges?.[i]||{};addLink(e,id,ids[i+1]);});}
  if(v.members)v.members.forEach(addNode);
  if(v.id&&/^(ACC|PER|DEV|PH|ADD|MER)-/.test(v.id))addNode(v);
  if((v.from&&v.to)||(v.source&&v.target))addLink(v);
  Object.entries(v).forEach(([k,val])=>{if(!['path_nodes','path_edges'].includes(k)&&val&&typeof val==='object')walk(val);});
 }
 results.forEach(walk);return {nodes:[...nodes.values()],links:[...links.values()],paths};
}
export function apiError(data={},status=0){
 const reason=data.reason||data.error||data.detail;
 if(data.reseeding)return `Warming up — reseeding, about ${data.eta_s??'a few'} seconds.`;
 if(data.reseed_failed)return 'Graph rebuild stopped. An administrator can retry reseeding.';
 if(data.halted||reason==='halted')return 'Tenant halted — use the read-only tool console.';
 if(reason==='llm_disabled')return 'Model switched off — the tool console still works.';
 if(['daily_cap','budget_exhausted'].includes(reason))return `Demo budget exhausted for today — the tool console still works.${data.resets_at?` Resets ${ist(data.resets_at)}.`:''}`;
 if(data.db==='unavailable'||reason==='db_unavailable')return 'Database unavailable — retry in 30 seconds.';
 if(reason==='timeout'||reason==='wall_clock')return 'Query timed out — try a narrower window or run a tool.';
 if(reason==='model_unavailable')return `Model unavailable — retry in ${data.retry_after||30} seconds. The tool console still works.`;
 if(status===401||status===403)return 'That access key is not authorised for this action.';
 if(status===429)return `Too many requests — retry in ${data.retry_after||15} seconds.`;
 return typeof data.hint==='string'?data.hint:typeof data.detail==='string'?data.detail:typeof reason==='string'?reason.replaceAll('_',' '):'The request could not complete. Please retry.';
}
export async function consumeSSE(response,onEvent){
 if(!response.ok){let d={};try{d=await response.json();}catch{}throw Object.assign(new Error(apiError(d,response.status)),{data:d,status:response.status});}
 if(!(response.headers.get('content-type')||'').includes('text/event-stream')){const d=await response.json();onEvent('answer',d);return;}
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
 while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done}).replaceAll('\r\n','\n');let end;while((end=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2);let event='message',data=[];for(const line of block.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))data.push(line.slice(5).trimStart());}if(data.length){let parsed;try{parsed=JSON.parse(data.join('\n'));}catch{parsed={text:data.join('\n')};}onEvent(event,parsed);}}if(done)break;}
}
export function download(name,body,type='text/plain'){const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([body],{type}));link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}
export function csvFor(rows){return ['Transfer,Date (IST),Amount (INR),From,To,Rail,Tool',...rows.map(r=>[r.id,ist(r.ts),(Number(r.amount||0)/100).toFixed(2),r.from,r.to,r.rail,r.tool].map(x=>'"'+String(x??'').replaceAll('"','""')+'"').join(','))].join('\n');}
