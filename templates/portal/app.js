(() => {
  'use strict';
  const $ = s => document.querySelector(s), esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const PAGE=50, CACHE=6, pending=new Map(), cache=new Map();
  const STATES={new:'Not started',reviewed:'Reviewed locally',sent:'User-reported sent',uncertain:'Uncertain submission',replied:'User-reported reply',hold:'On hold'};
  let manifest, storageKey, progress={version:1,campaign_id:'',cases:{}}, current=null, filter={search:'',status:'all'}, locations=null, page=0, token=0, importValue, timer;
  const appearance=matchMedia('(prefers-color-scheme: dark)');let theme='system';
  function applyTheme(value){theme=['system','light','dark'].includes(value)?value:'system';document.documentElement.dataset.theme=theme==='system'?(appearance.matches?'dark':'light'):theme;$('#theme').value=theme;}
  applyTheme('system');appearance.addEventListener('change',()=>{if(theme==='system')applyTheme('system');});
  $('#theme').onchange=e=>{applyTheme(e.target.value);if(storageKey){try{localStorage.setItem(storageKey+'-theme',theme);}catch{toast('Theme could not be saved in this browser.');}}};
  function safeUrl(value, relative=false) {
    if(typeof value!=='string'||/[\u0000-\u0020\\]/.test(value))return '';
    if(relative && /^(?:documents\/[a-f0-9]{64}\.(?:md|pdf|docx))$/.test(value))return value;
    try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:'';}catch{return '';}
  }
  function link(value,label,classes='button',relative=false){const href=safeUrl(value,relative);return href?`<a class="${classes}" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`:'';}
  function localPath(key) {if(key==='manifest')return 'data/manifest';if(/^index-\d+$/.test(key))return 'data/'+key;if(/^(?:detail|document|interview)-[a-f0-9]{64}$/.test(key))return 'data/'+key;throw Error('Invalid data path');}
  window.CareerPortalData={accept(key,value){if(pending.has(key))pending.get(key).resolve(value);}};
  async function load(key){
    if(cache.has(key)){const value=cache.get(key);cache.delete(key);cache.set(key,value);return value;}
    if(pending.has(key))return pending.get(key).promise;
    let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});pending.set(key,{promise,resolve,reject});
    const path=localPath(key);let script,deadline;
    (async()=>{try{
      if(location.protocol!=='file:'){const response=await fetch(path+'.json');if(!response.ok)throw Error('Data unavailable: '+key);resolve(await response.json());}
      else {script=document.createElement('script');script.src=path+'.js';script.onerror=()=>reject(Error('Local data unavailable: '+key));document.body.append(script);}
    }catch(error){reject(error);}})();
    deadline=setTimeout(()=>reject(Error('Data loading timed out: '+key)),10000);
    try{const value=await promise;cache.set(key,value);while(cache.size>CACHE)cache.delete(cache.keys().next().value);return value;}
    finally{clearTimeout(deadline);script?.remove();pending.delete(key);}
  }
  function entry(id){return progress.cases[id]||{status:'new',notes:'',next:'',edits:{}};}
  function validate(raw){
    if(!raw||raw.version!==1||raw.campaign_id!==manifest.campaign_id||!raw.cases||Array.isArray(raw.cases)||typeof raw.cases!=='object')throw Error('Different campaign or invalid progress format');
    const cases=Object.create(null), entries=Object.entries(raw.cases);if(entries.length>200000)throw Error('Progress is too large');
    for(const [id,row] of entries){
      if(!/^[a-f0-9]{64}$/.test(id)||!row||typeof row!=='object'||Array.isArray(row)||!Object.hasOwn(STATES,row.status))throw Error('Invalid case progress');
      const edits=Object.create(null);for(const [slot,text] of Object.entries(row.edits||{})){if(!['resume','cover-letter','dossier','form-answers'].includes(slot)||typeof text!=='string'||text.length>100000)throw Error('Invalid document edit');edits[slot]=text;}
      if(typeof row.notes!=='string'||row.notes.length>50000||typeof row.next!=='string'||row.next&&!/^\d{4}-\d{2}-\d{2}$/.test(row.next))throw Error('Invalid notes/date');
      cases[id]={status:row.status,notes:row.notes,next:row.next,edits};
    }return {version:1,campaign_id:manifest.campaign_id,cases};
  }
  function warn(){ $('#storageWarning').hidden=false;$('#storageWarning').textContent='Browser storage is unavailable. Export progress before closing. The campaign ledger has not changed.';$('#saveState').textContent='Not saved';}
  function save(id,change){const row=entry(id);change(row);progress.cases[id]=row;try{localStorage.setItem(storageKey,JSON.stringify(progress));$('#saveState').textContent='Saved in this browser';$('#storageWarning').hidden=true;}catch{warn();}}
  function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),2500);}
  function download(value,name){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
  async function copy(text){try{await navigator.clipboard.writeText(text);toast('Copied');}catch{const el=$('#message');el?.select();toast('Select the text and press Ctrl/Cmd+C.');}}
  function side(){ $('.nav-home').classList.toggle('active',!current);$('#sideList').innerHTML=manifest.recent.map(d=>`<a href="#/case/${d.id}" ${current?.id===d.id?'class="active" aria-current="page"':''}><span class="side-dot" aria-hidden="true"></span>${esc(d.company)}</a>`).join('');}
  function monogram(s){return [...s.replace(/[^\p{L}\p{N}]/gu,'')].slice(0,2).join('').toUpperCase();}
  async function rowAt(position){const block=await load('index-'+Math.floor(position/manifest.chunk_size));return block[position%manifest.chunk_size];}
  function total(){return locations===null?manifest.count:locations.length;}
  async function renderPage(expected=token){
    const start=page*PAGE, count=total(), selected=Array.from({length:Math.max(0,Math.min(PAGE,count-start))},(_,i)=>locations===null?start+i:locations[start+i]);
    const rows=await Promise.all(selected.map(rowAt));if(expected!==token||current)return;
    $('#cards').innerHTML='<div class="table-head"><span>Company / role</span><span>Contact / packet</span><span>Browser progress</span><span>Next step</span><span></span></div>'+rows.map(d=>{
      const v=entry(d.id);return `<article class="company-card"><a class="card-link" href="#/case/${d.id}" aria-label="${esc(d.company+' — '+d.role)}"><div class="row-company"><span class="monogram">${esc(monogram(d.company))}</span><div><div class="card-title">${esc(d.company)}</div><div class="card-sub">${esc(d.role)}</div></div></div><div class="row-contact"><span>${esc(d.person||'Application route')}</span><small>${esc(d.packet_status)}</small></div><div class="row-status"><span class="status-dot gray"></span>${STATES[v.status]}</div><div class="row-date">${esc(v.next||'—')}</div><span class="row-chevron" aria-hidden="true">›</span></a></article>`;
    }).join('')+(rows.length?'':'<p class="empty">No matching cases.</p>');
    $('#resultCount').textContent=`${count?start+1:0}–${Math.min(start+PAGE,count)} of ${count} cases`;
    $('#previous').disabled=page===0;$('#next').disabled=start+PAGE>=count;$('#pageNumber').textContent=`Page ${page+1} / ${Math.max(1,Math.ceil(count/PAGE))}`;
  }
  async function search(){
    const expected=++token;page=0;const q=filter.search.trim().toLocaleLowerCase();
    if(!q&&filter.status==='all'){locations=null;$('#loading').textContent='';await renderPage(expected);return;}
    locations=[];$('#loading').textContent='Searching all pages…';let first=false;
    for(let i=0;i<manifest.chunks;i++){
      const rows=await load('index-'+i);if(expected!==token||current)return;
      rows.forEach((row,j)=>{if((!q||[row.company,row.role,row.person,row.focus].join(' ').toLocaleLowerCase().includes(q))&&(filter.status==='all'||entry(row.id).status===filter.status))locations.push(i*manifest.chunk_size+j);});
      if(!first&&locations.length>=PAGE){first=true;await renderPage(expected);}
      if(i%4===0){$('#loading').textContent=`Searching: ${Math.min((i+1)*manifest.chunk_size,manifest.count)} / ${manifest.count}`;await new Promise(resolve=>setTimeout(resolve,0));}
    }
    if(expected===token&&!current){$('#loading').textContent='Search complete';await renderPage(expected);}
  }
  async function home(){
    current=null;side();$('#breadcrumb').textContent='Private campaign / Cases';
    $('#main').innerHTML=`<div class="page-head"><div><h1>All cases</h1><p class="lead">${manifest.count} cases<span class="separator">·</span>${manifest.ready} verified review packets<span class="separator">·</span>${manifest.incomplete} incomplete / blocked</p></div></div><div class="toolbar"><label class="search"><span aria-hidden="true">⌕</span><input id="search" type="search" aria-label="Search all cases" placeholder="Search" value="${esc(filter.search)}"></label><select id="statusFilter" aria-label="Browser progress"><option value="all">All browser statuses</option>${Object.entries(STATES).map(([id,label])=>`<option value="${id}" ${filter.status===id?'selected':''}>${label}</option>`).join('')}</select></div><div class="load-status" id="loading" role="status"></div><section class="company-grid" id="cards" aria-label="Cases"></section><div class="list-meta"><span id="resultCount"></span><span>Generated snapshot · ${esc(manifest.generated_at)}</span></div><div class="pagination"><button id="previous" class="button">Previous</button><span id="pageNumber"></span><button id="next" class="button">Next</button></div>`;
    $('#search').oninput=e=>{filter.search=e.target.value;clearTimeout(timer);timer=setTimeout(()=>search().catch(fail),180);};$('#statusFilter').onchange=e=>{filter.status=e.target.value;search().catch(fail);};
    $('#previous').onclick=()=>{page--;renderPage().catch(fail);};$('#next').onclick=()=>{page++;renderPage().catch(fail);};await search();
  }
  function conceptText(text,terms=[]){
    const available=terms.filter(x=>safeUrl(x.url));if(!available.length)return esc(text);
    const quote=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const pattern=new RegExp('(^|[^\\p{L}\\p{N}_])('+available.map(x=>quote(x.term)).sort((a,b)=>b.length-a.length).join('|')+')(?=$|[^\\p{L}\\p{N}_])','giu');
    let result='',last=0;for(const match of String(text).matchAll(pattern)){const start=match.index+match[1].length;result+=esc(String(text).slice(last,start));const source=available.find(x=>x.term.toLocaleLowerCase()===match[2].toLocaleLowerCase());result+=`<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer" title="${esc(source.kind+' · checked '+source.checked_at)}">${esc(match[2])}</a>`;last=start+match[2].length;}return result+esc(String(text).slice(last));
  }
  async function detail(id){
    const expected=++token;const d=await load('detail-'+id);if(expected!==token)return;if(d.id!==id)throw Error('Case identity mismatch');current=d;side();
    $('#breadcrumb').textContent='Cases / '+d.company;const v=entry(id), resume=d.documents.find(x=>x.slot==='resume');
    $('#main').innerHTML=`<div class="detail-top"><a href="#/">← All cases</a></div><div class="page-head"><div><div class="eyebrow">${esc(d.kind)} · ${esc(d.opportunity_id)}</div><div class="detail-title"><div class="monogram">${esc(monogram(d.company))}</div><div><h1>${esc(d.company)}</h1><div class="detail-sub">${esc(d.role)}</div></div></div><div class="pill-stack"><span class="pill gray packet-state">${esc(d.packet_status)}</span></div></div></div><div class="detail-grid"><div class="stack"><section class="panel"><div class="panel-label">Contact / application route</div><div class="person">${esc(d.person||'Observed application route')}</div><div class="action-row">${d.links.map(x=>link(x.url,x.label)).join('')}</div><p>${esc(d.fit)}</p><div class="notice"><strong>Review state</strong>${esc(d.concerns.join(' · ')||'Ready for review; preparation does not authorize submission.')}</div></section><section class="panel"><div class="section-head"><h2>Packet</h2></div><div class="tabs" role="tablist" aria-label="Packet documents">${d.documents.map((x,i)=>`<button role="tab" data-slot="${x.slot}" aria-selected="${i===0}">${esc(x.label)}</button>`).join('')}</div><label class="panel-label" for="message">Private working copy · edits do not change the approved artifact</label><textarea class="message-editor" id="message" maxlength="100000" aria-describedby="editorHint"></textarea><div class="editor-meta"><span id="editorHint">Loading selected document…</span><span id="charCount"></span></div><div class="editor-actions"><button class="button primary" id="copyMessage">Copy text</button><span id="documentLink"></span></div></section><section class="panel cv"><div class="section-head"><h2>Resume for ${esc(d.company)}</h2><span class="pill gray">${esc(resume?.language||'Not prepared')}</span></div><p>Selected immutable version. Browser edits above do not replace its reviewed bytes.</p><div class="action-row">${resume?link(resume.path,'Open original resume','button primary',true):''}</div>${resume?'<details id="resumePreview"><summary>View the original resume here</summary><pre id="resumeText" class="cv-preview">Open to load this version.</pre></details>':'<div class="notice">Resume preparation is incomplete.</div>'}<p class="mini-note">Only selected documents should be shared. Private notes and assessment are not employer attachments.</p></section><section class="panel"><h2>Interview preparation</h2><p>${esc(d.interview_status||'Saved materials, not a live drill')}</p><details id="interviewPreview"><summary>Open preparation dialogue</summary><div class="prep-dialogue" id="interviewDialogue" aria-label="Saved interviewer questions and candidate answer outlines"></div></details></section><section class="panel"><h2>Observed form fields</h2><p>${esc(d.form_status)}</p>${d.fields.map(x=>`<div class="fact"><span>${esc(x.label)}${x.required?' · Required':''}</span><strong>${esc(x.answer)}</strong></div>`).join('')}</section></div><div class="stack"><section class="panel"><h2>Your progress</h2><div class="field"><span>Browser note, not provider evidence</span><select id="caseStatus">${Object.entries(STATES).map(([id,label])=>`<option value="${id}" ${v.status===id?'selected':''}>${label}</option>`).join('')}</select></div><label class="field"><span>Next action date</span><input id="nextDate" type="date" value="${esc(v.next)}"></label><label class="field"><span>Private notes</span><textarea id="notes" rows="6" maxlength="50000">${esc(v.notes)}</textarea></label><p class="mini-note">Opening links, copying text and reviewing materials never mark an application sent. Ask the agent to reconcile exported notes before updating canonical state.</p></section><section class="panel"><h2>Sources and limits</h2><p>${esc(d.source_date)}</p>${d.sources.map(x=>link(x.url,x.label,'button quiet')).join('')}<p class="mini-note">Snapshot revision ${manifest.revision}. Ask the agent to refresh current facts and packet readiness.</p></section></div></div>`;
    $('#caseStatus').onchange=e=>save(id,row=>row.status=e.target.value);$('#nextDate').onchange=e=>save(id,row=>row.next=e.target.value);$('#notes').oninput=e=>save(id,row=>row.notes=e.target.value);
    let selectedSlot,documentToken=0;async function choose(slot){
      selectedSlot=slot;const n=++documentToken;document.querySelectorAll('[data-slot]').forEach(el=>el.setAttribute('aria-selected',String(el.dataset.slot===slot)));
      const doc=d.documents.find(x=>x.slot===slot);$('#message').value='';$('#editorHint').textContent='Loading selected document…';$('#documentLink').innerHTML='';
      if(!doc)return;const body=await load('document-'+doc.sha256);if(current?.id!==id||n!==documentToken)return;
      $('#message').value=entry(id).edits[slot]??body.text;$('#editorHint').textContent='Browser edits are unreviewed; original immutable artifact stays unchanged.';$('#charCount').textContent=$('#message').value.length+' characters';$('#documentLink').innerHTML=link(doc.path,'Original · '+doc.label,'button quiet',true);
    }
    document.querySelectorAll('[data-slot]').forEach(el=>el.onclick=()=>choose(el.dataset.slot).catch(fail));$('#message').oninput=e=>{if(!selectedSlot)return;save(id,row=>row.edits[selectedSlot]=e.target.value);$('#charCount').textContent=e.target.value.length+' characters';};$('#copyMessage').onclick=()=>copy($('#message').value);
    $('#interviewPreview').ontoggle=async e=>{if(!e.target.open)return;try{const prep=await load(d.interview_key||'interview-'+id);if(current?.id!==id)return;$('#interviewDialogue').innerHTML=prep.items.length?prep.items.map(x=>`<article class="prep-pair"><div class="prep-bubble interviewer"><small>Interviewer · ${esc(x.classification)}</small><p>${conceptText(x.question,x.terms)}</p></div><div class="prep-bubble candidate"><small>Candidate · suggested answer outline${x.review_required?' · review required':''}</small><p>${conceptText(x.answer,x.terms)}</p></div>${x.unknowns.length?'<p class="prep-note">To clarify: '+esc(x.unknowns.join(' · '))+'</p>':''}${x.pressure_points.length?'<p class="prep-note">Possible follow-ups: '+esc(x.pressure_points.map(v=>typeof v==='string'?v:JSON.stringify(v)).join(' · '))+'</p>':''}${x.employer_questions.length?'<p class="prep-note">Ask the company: '+esc(x.employer_questions.map(v=>typeof v==='string'?v:JSON.stringify(v)).join(' · '))+'</p>':''}<p class="prep-note">Evidence: ${esc(x.fact_ids.join(', '))}; sources: ${esc(x.source_ids.join(', '))}. Hypotheses are not promised company questions.</p></article>`).join(''):'<p class="prep-note">No preparation dialogue saved. Ask the agent to prepare it from the available profile/role evidence. Missing sources stay explicit; no live drill has started.</p>';}catch(error){fail(error);}};
    if(resume)$('#resumePreview').ontoggle=async e=>{if(e.target.open){try{const body=await load('document-'+resume.sha256);if(current?.id===id)$('#resumeText').textContent=body.text;}catch(error){fail(error);}}};
    if(d.documents.length)await choose(d.documents[0].slot);else{$('#message').value='No packet prepared. Ask the agent to prepare Markdown documents or resolve the listed blocker.';$('#message').readOnly=true;$('#editorHint').textContent='Incomplete discovery; not a ready application.';}
  }
  function fail(error){toast(error.message);const el=$('#loading');if(el)el.textContent=error.message;}
  async function route(){try{const match=location.hash.match(/^#\/case\/([a-f0-9]{64})$/);if(match)await detail(match[1]);else await home();window.scrollTo(0,0);$('#main').focus({preventScroll:true});}catch(error){$('#main').textContent='Unable to load this case: '+error.message;}}
  $('#export').onclick=()=>download({...progress,exported_at:new Date().toISOString()},'Career-progress.json');$('#import').onclick=()=>$('#importFile').click();
  $('#importFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>10000000)throw Error('Progress exceeds 10 MB');importValue=validate(JSON.parse(await file.text()));$('#importDialog').showModal();}catch(error){fail(error);}e.target.value='';};
  $('#cancelImport').onclick=()=>$('#importDialog').close();$('#confirmImport').onclick=()=>{progress=importValue;try{localStorage.setItem(storageKey,JSON.stringify(progress));}catch{warn();}$('#importDialog').close();route();};window.addEventListener('hashchange',route);window.addEventListener('storage',e=>{if(e.key===storageKey&&e.newValue){try{progress=validate(JSON.parse(e.newValue));route();}catch{toast('Unable to read browser progress from another tab.');}}});
  window.CareerPortal={debug:()=>({cache_entries:cache.size,pending:pending.size,page_size:PAGE,rendered_rows:document.querySelectorAll('.company-card').length})};
  load('manifest').then(async data=>{manifest=data;progress.campaign_id=data.campaign_id;storageKey='career-agent-portal-'+data.campaign_id;try{applyTheme(localStorage.getItem(storageKey+'-theme')||'system');}catch{applyTheme('system');}$('#campaignTitle').textContent=data.title;$('#navCount').textContent=data.count;$('#snapshotInfo').textContent=`Snapshot revision ${data.revision} · ${data.generated_at} · No automatic sending`;try{const saved=localStorage.getItem(storageKey);if(saved)progress=validate(JSON.parse(saved));}catch{warn();}await route();}).catch(error=>{$('#main').textContent='Unable to load local snapshot. Extract the complete folder first. '+error.message;});
})();
