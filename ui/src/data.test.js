import {describe,it,expect} from 'vitest';
import {apiError,consumeSSE,csvFor,evidenceFrom,graphFrom,normaliseShape,rupees} from './data.js';

describe('financial evidence presentation',()=>{
 it('renders integer paise as rupees without losing minor units',()=>{expect(rupees(82031500)).toBe('₹8,20,315.00');expect(rupees(101)).toBe('₹1.01');});
 it('keeps money direction and shared identifiers on the same path',()=>{const r={tool:'rs_shared_identifiers',rows:[{path_ids:['ACC-1','DEV-2','ACC-3'],edges:[{type:'USES_DEVICE'},{type:'USES_DEVICE'}]},{path_ids:['ACC-3','ACC-4'],edges:[{id:'TX-1',amount:12001,ts:1792100000,rail:'UPI',source:'ACC-3',target:'ACC-4'}]}]};const graph=graphFrom([r]);expect(graph.nodes.map(n=>n.id)).toEqual(['ACC-1','DEV-2','ACC-3','ACC-4']);expect(graph.links.find(l=>l.id==='TX-1')).toMatchObject({source:'ACC-3',target:'ACC-4',type:'TX'});expect(evidenceFrom([r])[0]).toMatchObject({id:'TX-1',amount:12001,from:'ACC-3',to:'ACC-4',tool:'rs_shared_identifiers'});});
 it('does not relabel a timeout as an evidence-backed answer',()=>{expect(normaliseShape({outcome:'tool_error'})).toBe('not_in_graph');expect(apiError({reason:'timeout'})).toContain('narrower window');});
 it('quotes CSV fields, with dates explicitly in IST and amounts in rupees',()=>{const csv=csvFor([{id:'TX-1',amount:12345,ts:1792100000,from:'ACC-1',to:'ACC-2',rail:'UPI',tool:'rs_path_between'}]);expect(csv).toContain('"123.45"');expect(csv).toContain('IST');expect(csv).toContain('ACC-1');});
});
describe('streamed trace',()=>{
 it('preserves tool-before-answer ordering across split SSE chunks',async()=>{const events=[],encoder=new TextEncoder();const body=new ReadableStream({start(c){c.enqueue(encoder.encode('event: tool\ndata: {"tool":"rs_cycles","rows_total":1}\n'));c.enqueue(encoder.encode('\nevent: answer\ndata: {"shape":"answered_with_path","text":"Evidence exists."}\n\n'));c.close();}});await consumeSSE(new Response(body,{headers:{'content-type':'text/event-stream'}}),(type,data)=>events.push({type,data}));expect(events.map(e=>e.type)).toEqual(['tool','answer']);expect(events[1].data.shape).toBe('answered_with_path');});
 it('turns typed budget errors into the actionable manual-tool message',async()=>{const response=new Response(JSON.stringify({reason:'daily_cap'}),{status:429,headers:{'content-type':'application/json'}});await expect(consumeSSE(response,()=>{})).rejects.toThrow('tool console still works');});
});
