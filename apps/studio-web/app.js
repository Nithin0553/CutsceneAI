/* CutSceneAI Studio. All status comes from the local Python companion.
   Images are decorative; no generated image is represented as source evidence. */
(() => {
  'use strict';
  const $ = sel => document.querySelector(sel);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { page:'overview', loading:true, busy:false, error:'', info:'', status:null,
    candidate:null, job:null, report:null, source:null, detailsOpen:false, evidencePath:'',
    selectedFolders:{unity:'',unreal:''}, discovery:null, selectedCutscene:'', selectedLevel:'' };
  const steps = [['connect','Connect'],['select','Select'],['review','Review'],['transfer','Transfer'],['results','Results']];
  const mark = `<svg viewBox="0 0 36 36" fill="currentColor" aria-hidden="true"><path d="M18 2 3 30h11l4-7h-5l7-14zM23 18l10 12H19l-4-4h8l-4-5z"/></svg>`;
  const icons = {
    home:'<path d="m3 10 9-7 9 7v10H4zM9 21v-8h6v8"/>',
    folder:'<path d="M3 7h7l2 3h9v11H3z"/>',
    layers:'<path d="m12 3 9 5-9 5-9-5 9-5zm-9 10 9 5 9-5M3 17l9 5 9-5"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    shield:'<path d="m12 2 9 4v6c0 5-4 8-9 10-5-2-9-5-9-10V6z"/>',
    film:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M8 3l4 6m2-6 4 6"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    bolt:'<path d="m14 2-9 11h7l-2 9 9-11h-7z"/>',
    plug:'<path d="M8 2v6m8-6v6M6 8h12v5a6 6 0 0 1-12 0V8zm6 11v3"/>',
    alert:'<path d="M12 3 2 21h20zM12 9v5m0 3v.1"/>',
    search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    refresh:'<path d="M20 6v5h-5M4 18v-5h5M5 10a8 8 0 0 1 14-3l1 4M4 13l1 4a8 8 0 0 0 14-3"/>',
    external:'<path d="M12 4h8v8M20 4 9 15M20 15v5H4V4h6"/>',
    camera:'<rect x="2" y="6" width="15" height="12" rx="2"/><path d="m17 10 5-3v10l-5-3"/>',
    chevron:'<path d="m7 10 5 5 5-5"/>'
  };
  const icon = key => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[key]||icons.film}</svg>`;
  const normPath = x => String(x || '').replaceAll('\\','/').toLowerCase();
  const connected = () => Boolean(state.status?.connection);
  const worker = () => state.status?.unreal_worker || {};
  const sceneName = () => state.status?.connection?.scene_name || 'No cutscene connected';
  const progress = () => state.job?.status?.startsWith('GENERATED') ? 4 : state.job ? 3 : state.candidate ? 2 : connected() ? 1 : 0;
  const size = n => n!==null && n!==undefined && Number.isFinite(Number(n)) ? Number(n).toLocaleString() : '—';
  const duration = n => n!==null && n!==undefined && Number.isFinite(Number(n)) ? Number(n).toFixed(2) + ' s' : '—';
  const statusLabel = (text,tone='neutral') => `<span class="status ${tone}"><span class="dot"></span>${esc(text)}</span>`;
  const navLink = (page,label,ico) => `<button class="nav-item ${state.page===page?'active':''}" data-page="${page}">${icon(ico)}<span>${label}</span></button>`;
  const btn = (label,action,variant='primary',disabled=false) => `<button type="button" class="button ${variant}" data-action="${action}" ${disabled?'disabled':''}>${label}</button>`;
  const item = (label,value) => `<div class="detail"><span>${esc(label)}</span><strong title="${esc(value)}">${esc(value)}</strong></div>`;
  const banner = () => state.error ? `<div class="notice error" role="alert">${icon('alert')}<span>${esc(state.error)}</span><button data-action="clear" aria-label="Dismiss">×</button></div>` : state.info ? `<div class="notice" role="status">${icon('check')}<span>${esc(state.info)}</span><button data-action="clear" aria-label="Dismiss">×</button></div>` : '';
  function layout(){
    const c=state.status?.connection;
    const healthy=worker().connected && (!c || (normPath(worker().project)===normPath(c.target_project) && worker().level===c.level_path));
    const unrealWorking=state.job?.status==='RUNNING';
    return `<div class="shell"><aside class="sidebar"><div class="brand-icon" title="CutSceneAI Studio">${mark}</div><nav aria-label="Primary navigation">${navLink('overview','Overview','home')}${navLink('connect','Projects','folder')}${navLink('review','Transfer','bolt')}${navLink('results','Results','search')}</nav><div class="side-bottom">${icon('film')}</div></aside><div class="workspace"><header class="topbar"><button class="wordmark" data-page="overview">CutSceneAI<small>STUDIO</small></button><div class="top-actions">${statusLabel(connected()?'Local project linked':'Not connected',connected()?'good':'neutral')}${statusLabel(healthy?'Unreal ready':unrealWorking?'Unreal working':'Unreal offline',healthy?'good':'warning')}<button class="project-menu" data-page="connect">${icon('folder')}<span>${esc(c?.scene_name||'Connect project')}</span>${icon('chevron')}</button></div></header><main id="content">${banner()}${page()}</main><footer class="footer">LOCAL RESEARCH PREVIEW <span>·</span> Unity → Unreal Engine <span>·</span> Engine-generated does not mean fidelity-verified</footer></div></div>`;
  }
  function stageRail(){
    const active=Math.max(0,steps.findIndex(([key])=>key===state.page));const done=progress();return `<section class="stage-rail" aria-label="Transfer workflow">${steps.map(([key,label],i)=>{const complete=i<active&&i<=done;return `<button data-page="${key}" class="stage ${i===active?'current':''} ${complete?'complete':''}"><span class="stage-number">${complete?icon('check'):String(i+1).padStart(2,'0')}</span><strong>${label}</strong></button>`}).join('')}</section>`;
  }
  function overview(){const c=state.status?.connection;
    return `<section class="hero"><div class="hero-copy"><div class="eyebrow">CROSS-ENGINE CINEMATICS</div><h1>The same scene.<br>Another engine.</h1><p>Connect, reconstruct, and inspect editable cinematic sequences in one workspace.</p><div class="hero-actions">${btn(c?'Continue transfer '+icon('arrow'):'Connect local projects '+icon('arrow'),c?'continue':'connect','primary')}${btn('View workflow','review','secondary')}</div><div class="hero-foot">Independent source evidence · Guarded Unreal generation</div></div><div class="hero-image" role="img" aria-label="Decorative cinematic environment"><span>ILLUSTRATIVE ARTWORK</span></div></section>${stageRail()}<div class="section-head"><h2>Workspace</h2><span class="muted">Current connection</span></div><div class="stat-cards"><article class="panel stat-card">${icon('folder')}<small>UNITY SOURCE</small><h3>${esc(c?.scene_name||'Not connected')}</h3><p>${c?`${size(c.source_track_count)} source tracks · ${duration(c.source_duration_seconds)}`:'Connect a real exported CSIR file to start'}</p></article><article class="panel stat-card">${icon('layers')}<small>UNREAL TARGET</small><h3>${esc(c?c.target_project.split(/[\\/]/).pop():'Not connected')}</h3><p>${esc(c?.level_path||'Select a staging .uproject and level')}</p></article><article class="panel stat-card">${icon('shield')}<small>TRANSFER STATE</small><h3>${esc(state.job?.status || (state.candidate?'Prepared for Unreal':'Not started'))}</h3><p>${state.candidate?`${size(state.candidate.action_total)} planned actions · fidelity not verified`:'Prepare source evidence before generating'}</p></article></div><div class="split-panels"><article class="panel pad"><div class="section-head"><h2>How Studio works</h2><span class="small muted">Five clear steps</span></div><div class="workflow-list">${[['01','Connect an exported Unity cutscene and target Unreal project'],['02','Select the source cutscene and inspect extracted tracks'],['03','Review the immutable transfer plan and coverage gaps'],['04','Generate a new Unreal Level Sequence with the editor companion'],['05','Import observations and review the unverified results']].map(([n,t])=>`<div><span class="mono">${n}</span><span>${esc(t)}</span></div>`).join('')}</div></article><article class="panel pad"><div class="section-head"><h2>Scope of this build</h2></div><p class="body-copy">This local Studio connects to the existing CSIR planner and guarded Unreal generator. Unity folder scanning, universal asset import, automatic project setup, and complete playback fidelity are <strong>not implemented as one-click operations yet</strong>.</p><div class="slim-note">Already generated a sequence manually? You can attach its CineTwin target observation under Results without regenerating anything.</div></article></div>`;
  }
  const field=(name,label,value='',placeholder='',required=true)=>`<label class="field"><span>${label}${required?' <em>*</em>':''}</span><input name="${name}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${required?'required':''} autocomplete="off" spellcheck="false"></label>`;
  function connect(){
    const c=state.status?.connection||{};
    // The local Python service opens a native Windows folder picker. Browsers
    // cannot reveal full local directory paths from webkitdirectory inputs.
    const folders=state.selectedFolders;
    const d=state.discovery||{};
    const source=d.unity||{};
    const target=d.unreal||{};
    const cutscenes=source.cutscenes||[];
    const levels=target.levels||[];
    const pickedSource=state.selectedCutscene||cutscenes[0]?.path||'';
    const pickedLevel=state.selectedLevel||target.active_level||(levels.length===1?levels[0]:'');
    const folderRow=(kind,label,path,description)=>`<div class="project-picker"><div class="project-folder-info"><strong>${esc(label)}</strong><span>${esc(path?path.split(/[\\/]/).pop():'Not selected')}</span><small title="${esc(path)}">${esc(path||description)}</small></div>${btn(path?'Change folder':'Browse folder',kind==='unity'?'browse-unity':'browse-unreal','secondary',state.busy)}</div>`;
    const selectHtml=(name,items,selected,labelField,valueField)=>`<label class="field"><span>${name==='csir'?'Detected Unity cutscene':'Destination level'}</span><select name="${name}" required>${items.map(x=>`<option value="${esc(typeof x==='string'?x:x[valueField])}" ${selected===(typeof x==='string'?x:x[valueField])?'selected':''}>${esc(typeof x==='string'?x:x[labelField])}</option>`).join('')}</select></label>`;
    return `<div class="page-heading"><div class="eyebrow">01 / CONNECT</div><h1>Choose your projects</h1><p>Select two project folders. Studio will discover the exported timelines, Unreal project and level, and prepare the mapping automatically.</p></div>${stageRail()}<form id="project-folders-form" class="connect-layout"><section class="panel pad"><div class="form-heading">${icon('folder')} <h2>Project folders</h2>${statusLabel(d.ready?'DISCOVERED':'SELECT FOLDERS',d.ready?'good':'warning')}</div>
    ${folderRow('unity','Unity project',folders.unity,'Folder containing Assets and ProjectSettings')}
    ${folderRow('unreal','Unreal project',folders.unreal,'Folder containing a .uproject file')}
    ${source.message?`<p class="hint">${esc(source.message)}</p>`:''}${target.message?`<p class="hint">${esc(target.message)}</p>`:''}
    ${cutscenes.length?`<div class="rule"></div><h3>Detected cutscenes</h3>${selectHtml('csir',cutscenes,pickedSource,'name','path')}${cutscenes.length===1?'<p class="hint">One cutscene detected — already selected.</p>':''}`:''}
    ${levels.length?`${selectHtml('level',levels,pickedLevel)}${levels.length===1?'<p class="hint">One target level detected — already selected.</p>':''}`:''}
    <label class="checkbox"><input type="checkbox" name="source_rights_confirmed" ${c.source_rights_confirmed?'checked':''}><span>I have permission to copy the Unity project assets into the Unreal project</span></label>
    <div class="form-actions"><button class="button primary" type="submit" ${!d.ready||state.busy?'disabled':''}>${state.busy?'Checking projects…':'Connect projects '+icon('arrow')}</button>${folders.unity&&folders.unreal?btn('Scan again','scan-folders','secondary',state.busy):''}</div>
    </section><aside><div class="panel pad sidebar-panel"><h2>Detected automatically</h2>${item('Unity source',cutscenes.length?`${cutscenes.length} exported cutscene(s)`:'Not exported or not scanned')}${item('Unreal project',target.project?target.project.split(/[\\/]/).pop():'Not selected')}${item('Saved maps',size(levels.length))}${item('Asset scope',source.source_scope||'Waiting for Unity folder')}${item('Asset mapping',d.ready?'Auto-generated on connection':'Not generated')}${item('CineTwin capture','Auto-attached if an exact match exists')}<div class="rule"></div><p class="hint">Project discovery is read-only. The Generate action still requires Unreal Editor to be open, and it never overwrites an existing sequence.</p></div><div class="callout">${icon('shield')}<p>When multiple cutscenes or levels exist, select from the detected list. No JSON paths or manual mapping files are needed.</p></div></aside></form>`;
  }
  function select(){const c=state.status?.connection;
    if(!c)return missing('Select cutscene','Connect an existing Unity CSIR before selecting a cutscene.','connect');
    return `<div class="page-heading"><div class="eyebrow">02 / SELECT</div><h1>Select a cutscene</h1><p>Studio currently reads one exported CSIR at a time.</p></div>${stageRail()}<div class="selection-layout"><aside class="panel pad"><h2>Available cutscenes <span class="muted small">01</span></h2><div class="cutscene-selected">${icon('film')}<div><strong>${esc(c.scene_name)}</strong><small>Exported Unity CSIR · Selected</small></div>${icon('check')}</div><div class="rule"></div>${item('Source tracks',size(c.source_track_count))}${item('Source entities',size(c.source_entity_count))}${item('Duration',duration(c.source_duration_seconds))}${item('Frame rate',`${esc(c.source_fps||'—')} fps`)}</aside><section class="panel preview-card"><img src="assets/source-frame.webp" alt="Decorative example scene, not connected source footage"><div class="preview-caption"><span>ILLUSTRATIVE · NOT AN ENGINE CAPTURE</span><h2>${esc(c.scene_name)}</h2><p>Source timeline data is real; cinematic artwork is a visual placeholder.</p></div></section><aside class="panel pad"><h2>Extracted track groups</h2>${Object.keys(c.track_types||{}).length?Object.entries(c.track_types).map(([k,v])=>item(k,size(v))).join(''):'<p class="muted">No declared tracks found.</p>'}<div class="rule"></div>${statusLabel(c.source_capture_available?'Source behavior available':'Behavior capture missing',c.source_capture_available?'good':'warning')}<div class="bottom-action">${btn('Review transfer '+icon('arrow'),'review')}</div></aside></div>`;
  }
  function review(){const c=state.status?.connection;
    if(!c)return missing('Review transfer','Connect existing Unity source data and Unreal target first.','connect');
    const p=state.candidate;return `<div class="page-heading"><div class="eyebrow">03 / REVIEW</div><h1>Review the transfer</h1><p>Generate an independently verifiable transfer plan before opening Unreal.</p></div>${stageRail()}<div class="review-layout"><section class="panel pad"><div class="section-head"><h2>Prepared actions</h2>${statusLabel(p?'PLAN VERIFIED':'NOT PREPARED',p?'good':'warning')}</div>${p?`<div class="big-number">${size(p.action_total)}<small>planned actions</small></div><div class="action-grid">${Object.entries(p.action_counts||{}).map(([k,v])=>`<div><span>${esc(k.replaceAll('_',' '))}</span><strong>${size(v)}</strong></div>`).join('')}</div>`:`<div class="empty-state">${icon('layers')}<h3>No transfer plan yet</h3><p>Read your source CSIR and mapping, then create the immutable plan and coverage report.</p></div>`}<div class="rule"></div><h3>Source track coverage</h3>${p?Object.entries(p.track_coverage||{}).map(([k,v])=>item(k,size(v))).join(''): '<p class="muted">Coverage appears after preparation.</p>'}<div class="form-actions">${btn(state.busy?'Preparing…':'Prepare transfer plan', 'prepare','primary',state.busy)}${btn('Connect different files','connect','secondary')}</div></section><aside><section class="panel pad sidebar-panel"><h2>Transfer destination</h2>${item('Source cutscene',c.scene_name)}${item('Target level',c.level_path)}${item('Selected mapping JSON',c.mapping)}${item('Mapping base sequence',c.base_sequence)}${item('New target sequence',p?.sequence_path||'Created on preparation')}${item('CED preflight',String(p?.ced_preflight||'Not evaluated'))}<div class="rule"></div><div class="slim-note">${p?'This plan did not modify the Unreal project.':'A verified plan is required before generating.'}</div>${p?.review_flags?.length?`<div class="callout" role="alert">${icon('alert')}<div><strong>Review mapping and target assets before generation</strong>${p.review_flags.map(x=>`<p>${esc(x)}</p>`).join('')}</div></div>`:''}${p?`<div class="bottom-action">${btn('Continue to Unreal '+icon('arrow'),'transfer')}</div>`:''}</section><section class="callout">${icon('alert')}<p>Incomplete animation, audio, hierarchy, and other CED features remain explicit. A prepared plan is not a proof of fidelity.</p></section></aside></div>`;
  }
  function transfer(){
    const c=state.status?.connection;
    const p=state.candidate;
    const w=worker();
    const d=state.status?.destination_readiness||{status:'CHECKING',ready:false,next_action:'Checking the target scene.'};
    const repoPath=String(state.status?.repo_root||'').replaceAll('\\','/').replaceAll('"','');
    const workerCommand=`import sys; sys.path.insert(0, r"${repoPath}/integrations/unreal"); import studio_local_editor_worker as w; w.start()`;
    const connectedTarget=w.connected&&normPath(w.project)===normPath(c?.target_project)&&w.level===c?.level_path;
    const auto=p?.automatic_setup||{};
    const autoCanRun=Boolean(auto.available&&auto.ready&&
      ['READY','SCENE_SETUP_REQUIRED','ASSETS_REQUIRED'].includes(d.status)&&
      !(d.wrong_actor_types||[]).length&&!(d.wrong_asset_types||[]).length&&!(d.duplicate_actors||[]).length);
    const canGenerate=Boolean(connectedTarget&&(d.ready||autoCanRun)&&p&&d.candidate_id===p.candidate_id&&!state.busy&&!state.job);
    if(!c)return missing('Unreal transfer','Connect your Unity source and target Unreal project first.','connect');
    if(!p)return missing('Unreal transfer','Prepare a transfer plan before generating a new sequence.','review');
    const missingActors=d.missing_actors||[];
    const missingAssets=d.missing_assets||[];
    const wrongTypes=[...(d.wrong_actor_types||[]),...(d.duplicate_actors||[]),...(d.wrong_asset_types||[])];
    const readinessLabel=d.ready?'READY TO GENERATE':d.status==='SCENE_SETUP_REQUIRED'?'SCENE SETUP NEEDED':d.status==='ASSETS_REQUIRED'?'ASSET IMPORT NEEDED':d.status==='WRONG_TARGET'?'WRONG PROJECT / LEVEL':d.status==='TARGET_EXISTS'?'SEQUENCE ALREADY EXISTS':d.status==='UPGRADE_COMPANION'?'UPDATE EDITOR COMPANION':'CHECKING DESTINATION';
    return `<div class="page-heading"><div class="eyebrow">04 / TRANSFER</div><h1>Generate in Unreal</h1><p>Studio checks the real target scene before allowing generation. Missing project setup never becomes a failed transfer job.</p></div>${stageRail()}<div class="review-layout"><section class="panel pad"><div class="section-head"><h2>Destination readiness</h2>${statusLabel(readinessLabel,d.ready?'good':'warning')}</div><p class="body-copy">${esc(d.next_action||'Connect the Unreal editor companion to inspect this project.')}</p>${item('Scene actors',d.expected_actor_count===undefined?'Checking…':`${size(d.found_actor_count)} / ${size(d.expected_actor_count)} found`)}${item('Mapped assets',d.required_asset_count===undefined?'Checking…':`${size(d.required_asset_count-missingAssets.length)} / ${size(d.required_asset_count)} available`)}${missingActors.length?`<div class="readiness-issues"><strong>Missing mapped actors (${missingActors.length})</strong><p>These actors are not in the loaded Unreal level. The sequence cannot safely bind them.</p><ul>${missingActors.slice(0,10).map(row=>`<li><code>${esc(row.entity_name)}</code><span>${esc(row.actor_label)}</span></li>`).join('')}</ul>${missingActors.length>10?`<p>And ${missingActors.length-10} more.</p>`:''}</div>`:''}${missingAssets.length?`<div class="readiness-issues"><strong>Missing imported assets (${missingAssets.length})</strong><p>The target asset paths in the selected mapping are not present in this project.</p><ul>${missingAssets.slice(0,10).map(row=>`<li><code>${esc(row.expected_class)}</code><span>${esc(row.asset_path)}</span></li>`).join('')}</ul></div>`:''}${wrongTypes.length?`<div class="readiness-issues"><strong>Incorrect or ambiguous bindings (${wrongTypes.length})</strong><p>Correct the listed actor or asset mappings before generating.</p>${wrongTypes.slice(0,10).map(row=>item(row.actor_label||row.asset_path,`Expected ${row.expected||row.expected_class||'one unique actor'}; actual ${row.actual||row.actual_class||'multiple actors'}`)).join('')}</div>`:''}${auto.available?`<div class="readiness-issues"><strong>Automatic Unity asset and actor setup</strong>${auto.ready?`<p>${size(auto.planned_imports)} source files and ${size(auto.planned_actors)} actors will be transferred/created before generating the sequence. Unsupported source features remain explicitly reported.</p>`:`<p>Automatic setup cannot start:</p><ul>${(auto.blockers||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`}${(auto.warnings||[]).slice(0,6).map(x=>`<p class="hint">${esc(x)}</p>`).join('')}</div>`:`<div class="slim-note">Connect the Unity project folder and Assets scope to enable automatic import and actor creation.</div>`}<div class="rule"></div><div class="section-head"><h2>Editor companion</h2>${statusLabel(connectedTarget?'CONNECTED TO TARGET':w.connected?'WRONG PROJECT / LEVEL':'OFFLINE',connectedTarget?'good':'warning')}</div><p class="body-copy">Open the backed-up Unreal staging project with the correct level loaded, then start the companion in the <strong>Unreal Python Console</strong>:</p><pre class="command" id="worker-command">${esc(workerCommand)}</pre>${btn('Copy Python command','copy-command','secondary')}${item('Loaded project',w.project||'Not detected')}${item('Loaded level',w.level||'Not detected')}${item('Target sequence',p.sequence_path)}${p?.review_flags?.length?`<div class="callout" role="alert">${icon('alert')}<div><strong>Mapping review:</strong>${p.review_flags.map(x=>`<p>${esc(x)}</p>`).join('')}</div></div>`:''}<div class="form-actions">${btn(state.busy?'Submitting…':auto.available?'Import Unity assets & generate sequence '+icon('arrow'):'Generate new Level Sequence '+icon('arrow'),'execute','primary',!canGenerate)}${btn('Recheck destination','refresh','secondary')}${state.job?btn('Prepare a fresh attempt','review','secondary'):''}</div>${!canGenerate?'<p class="hint">Generation requires a verified destination or a complete source-backed automatic setup plan; missing/ambiguous Unity files are reported before any Unreal changes.</p>':''}</section><aside><section class="panel pad sidebar-panel"><h2>Execution report</h2>${item('Job status',state.job?.status||'Not started')}${item('Engine generation',state.job?.generation_status||'Not started')}${state.job?.setup_status?item('Source setup',state.job.setup_status):''}${item('Output',state.job?.generated_sequence||p.sequence_path)}${item('Fidelity','Not established')}${state.job?.error?`<p class="notice-inline">${esc(state.job.error)}</p>`:''}<div class="rule"></div><p class="hint">After successful generation: Save All in Unreal, reopen the sequence, and audit its persisted tracks before trusting playback.</p><div class="bottom-action">${btn('View results '+icon('arrow'),'results','secondary')}</div></section><section class="callout">${icon('shield')}<p>Studio never overwrites an existing sequence. A failed run must be investigated rather than replayed blindly.</p></section></aside></div>`;
  }
  function results(){const r=state.report,j=state.job,c=state.status?.connection;
    return `<div class="page-heading"><div class="eyebrow">05 / RESULTS</div><h1>Transfer results</h1><p>Inspectable evidence from Unreal, not a simulated success score.</p></div>${stageRail()}<div class="results-layout"><section class="panel pad"><div class="section-head"><h2>Unreal generation</h2>${statusLabel(j?.generation_status==='GENERATED_UNVERIFIED'?'GENERATED · UNVERIFIED':j?.status||'NOT RUN',j?.generation_status==='GENERATED_UNVERIFIED'?'good':'warning')}</div>${item('Sequence',j?.generated_sequence||state.candidate?.sequence_path||'Not generated in this session')}${item('Job status',j?.status||'Not started')}${item('Saved-level readback','Not verified by this UI')}${item('Fidelity','Not established')}${j?.receipt_file?item('Runtime receipt',j.receipt_file):''}${j?.error?`<p class="notice-inline">${esc(j.error)}</p>`:''}<div class="rule"></div><h3>Independent CineTwin diagnostics</h3>${state.jobDiagnostic?`<div class="diagnostic-table">${Object.entries(state.jobDiagnostic.entities||{}).map(([k,v])=>item(`${k} · actor max`,v.actor_max_cm==null?'Not measured':`${Number(v.actor_max_cm).toFixed(2)} cm`)).join('')}</div>`:'<p class="muted">No run-specific world-position comparison is available yet.</p>'}</section><aside><section class="panel pad"><div class="section-head"><h2>Attach existing CineTwin capture</h2>${icon('layers')}</div><p class="body-copy">Already completed Stage 7 manually? Attach the <strong>Unreal target observation JSON</strong> you generated. This only reads and summarizes the file; it does not regenerate anything.</p><form id="observation-form"><label class="field"><span>Existing target observation JSON</span><input name="path" value="${esc(state.evidencePath)}" placeholder="D:\\...\\stage7_target_observation.json" required autocomplete="off" spellcheck="false"></label><button class="button secondary full" type="submit">Inspect existing observation</button></form>${r?`<div class="rule"></div>${statusLabel('TARGET CAPTURE COMPLETE','good')}${item('Samples',`${size(r.sample_count)} measured`)}${item('Mapped actors',`${size(r.mapped_actor_count)} / ${size(r.source_entity_count)}`)}${item('Skeletal rigs',size(r.skeletal_rig_count))}${item('Unmapped source entities',size(r.unmapped_count))}${item('Comparison','Target only · no parity claim')}<div class="rule"></div><h3>Measured target actor motion (cm)</h3>${Object.entries(r.actor_motion_cm||{}).map(([k,v])=>item(k.split('_').pop(),v+' cm')).join('')}<div class="rule"></div><h3>Target skeletal motion</h3>${Object.entries(r.skeletal_bone_motion_cm||{}).map(([k,v],i)=>item('Rig '+(i+1),v+' cm'+(v<0.1?' · STATIC OBSERVED':''))).join('')}`:''}</section><section class="callout">${icon('alert')}<p>Matching-time Unity observations are still required to quantify source-to-target errors. Skeletal pose equivalence, audio output, and rendered-frame fidelity remain unverified.</p></section></aside></div>`;
  }
  function missing(title,msg,destination){return `<div class="page-heading"><h1>${esc(title)}</h1><p>${esc(msg)}</p></div><section class="panel pad empty-large">${icon('folder')}<h2>Complete the previous step</h2>${btn(`Go to ${destination} `+icon('arrow'),destination)}</section>`}
  function page(){return ({overview,connect,select,review,transfer,results}[state.page]||overview)()}
  function render(){ $('#app').innerHTML=layout(); }
  async function api(path,payload){
    const response=await fetch('/api/'+path,{method:payload===undefined?'GET':'POST',cache:'no-store',headers:payload===undefined?{}:{'Content-Type':'application/json','X-CSAI-Token':state.status?.token||''},body:payload===undefined?undefined:JSON.stringify(payload)});
    let body={};try{body=await response.json()}catch{throw new Error('The local backend returned an invalid response.')}if(!response.ok)throw new Error(body.error||`Local API error ${response.status}`);return body;
  }
  async function refresh(quiet=false){try{let oldId=state.status?.active_job;const status=await api('status');state.status=status;
      state.candidate=status.candidate||null;
      if(status.connection && !state.selectedFolders.unity && !state.selectedFolders.unreal){
        state.selectedFolders.unity=status.connection.unity_project||'';
        state.selectedFolders.unreal=String(status.connection.target_project||'').replace(/[\\/][^\\/]+$/,'');
      }
      if(status.connection && !state.discovery && state.selectedFolders.unity && state.selectedFolders.unreal){
        try{
          state.discovery=await api('discover',{unity_folder:state.selectedFolders.unity,unreal_folder:state.selectedFolders.unreal});
          state.selectedCutscene=status.connection.csir||'';
          state.selectedLevel=status.connection.level_path||'';
        }catch{} // Project folders may have moved; allow Browse Folder again.
      }
      if(status.observation)state.report=status.observation;
      if(status.active_job && (!state.job || status.active_job!==oldId || state.job.job_id!==status.active_job))state.job=await api('jobs/'+status.active_job);
      else if(status.active_job)state.job=await api('jobs/'+status.active_job);
      if(state.job?.diagnostic_file&&!state.jobDiagnostic){try{state.jobDiagnostic=await api('diagnostic/'+state.job.job_id)}catch{}}
      state.loading=false;if(!quiet)state.info='Workspace refreshed.';render();
    }catch(err){state.loading=false;if(!quiet){state.error=err.message;render()}}}
  function notice(text,isError=false){state.error=isError?text:'';state.info=isError?'':text;render()}
  function navigate(page){state.page=page;state.error='';state.info='';render();window.scrollTo({top:0,behavior:'smooth'})}
  async function action(name){if(state.busy)return;const c=state.status?.connection;
    if(['connect','select','review','transfer','results'].includes(name)){navigate(name);return}
    if(name==='continue'){navigate(state.job?'results':state.candidate?'transfer':c?'select':'connect');return}
    if(name==='clear'){state.error='';state.info='';render();return}
    if(name==='refresh'){await refresh();return}
    if(name==='copy-command'){try{await navigator.clipboard.writeText($('#worker-command').textContent);notice('Unreal Python Console command copied.')}catch{notice('Copy the command manually from the box.',true)}return}
    if(name==='browse-unity'||name==='browse-unreal'||name==='scan-folders'){
      state.busy=true;render();
      try{
        if(name!=='scan-folders'){
          const kind=name==='browse-unity'?'unity':'unreal';
          const picked=await api('pick-folder',{kind});
          if(picked.cancelled)return;
          state.selectedFolders[kind]=picked.path;
          state.selectedCutscene='';state.selectedLevel='';
        }
        state.discovery=await api('discover',{unity_folder:state.selectedFolders.unity,unreal_folder:state.selectedFolders.unreal});
        const src=state.discovery.unity?.cutscenes||[];
        const maps=state.discovery.unreal?.levels||[];
        state.selectedCutscene=src.length?src[0].path:'';
        state.selectedLevel=state.discovery.unreal?.active_level||(maps.length===1?maps[0]:'');
        if(!state.discovery.ready)state.info='Folders selected. Review any missing exports or maps below.';
        else state.info='Both projects inspected. Confirm the cutscene and level, then connect.';
        state.error='';
      }catch(err){state.error=err.message;state.info='';}
      finally{state.busy=false;render()}
      return;
    }
    if(name==='prepare'){
      state.busy=true;render();try{state.candidate=await api('prepare',{});state.job=null;state.jobDiagnostic=null;notice('Source-authenticated transfer plan prepared. Unreal assets remain unchanged.')}catch(err){notice('Plan blocked: '+err.message,true)}finally{state.busy=false;render()}return;
    }
    if(name==='execute'){
      if(!state.candidate){notice('Prepare a verified transfer first.',true);return}
      const d=state.status?.destination_readiness;
      const auto=state.candidate?.automatic_setup;
      const autoReady=Boolean(auto?.available&&auto?.ready&&['READY','SCENE_SETUP_REQUIRED','ASSETS_REQUIRED'].includes(d?.status)&&!(d?.wrong_actor_types||[]).length&&!(d?.wrong_asset_types||[]).length&&!(d?.duplicate_actors||[]).length);
      if((!d?.ready&&!autoReady) || d.candidate_id!==state.candidate.candidate_id){notice('Destination setup is not ready. Review the missing scene actors or assets on this page.',true);return}
      const flags=state.candidate.review_flags||[];const prompt=(autoReady?'Import the verified Unity assets, create mapped actors and generate ONE new editable Level Sequence in this backed-up Unreal project?':'Generate ONE new editable Level Sequence in the backed-up Unreal project?')+' Existing sequences are not overwritten.'+(flags.length?'\n\nREVIEW FLAGS:\n'+flags.join('\n')+'\n\nOnly continue if you have confirmed the mapping and target assets.':'');if(!confirm(prompt))return;
      state.busy=true;render();try{state.job=await api('execute',{candidate_id:state.candidate.candidate_id});notice('Job queued. Unreal will verify inputs before generation.')}catch(err){notice('Unreal generation blocked: '+err.message,true)}finally{state.busy=false;render()}return;
    }
  }
  $('#app').addEventListener('click',e=>{const link=e.target.closest('[data-page]');if(link){navigate(link.dataset.page);return}const button=e.target.closest('[data-action]');if(button)void action(button.dataset.action)});
  $('#app').addEventListener('submit',async e=>{
    const form=e.target.closest('form');if(!form)return;e.preventDefault();if(state.busy)return;
    state.busy=true;state.error='';state.info='';
    const body=Object.fromEntries(new FormData(form).entries());
    try{
      if(form.id==='project-folders-form'){
        state.selectedCutscene=body.csir;
        state.selectedLevel=body.level;
        const result=await api('connect-projects',{
          unity_folder:state.selectedFolders.unity,
          unreal_folder:state.selectedFolders.unreal,
          csir:body.csir,level:body.level,
          source_rights_confirmed:!!form.querySelector('[name=source_rights_confirmed]').checked
        });
        state.status.connection=result;state.candidate=null;state.job=null;
        state.jobDiagnostic=null;state.report=null;state.evidencePath='';
        navigate('select');notice('Projects connected. Cutscene and mapping detected automatically.');
      }else if(form.id==='connect-form'){
        body.skeletal_root_world_lock=!!form.querySelector('[name=skeletal_root_world_lock]').checked;
        body.source_rights_confirmed=!!form.querySelector('[name=source_rights_confirmed]').checked;
        const result=await api('connect',body);
        state.status.connection=result;state.candidate=null;state.job=null;state.jobDiagnostic=null;state.report=null;state.evidencePath='';navigate('select');notice('Project files verified. Select your exported cutscene.');
      }else if(form.id==='observation-form'){
        state.evidencePath=body.path;state.report=await api('observation',{path:body.path});notice('Real target observations verified and attached. Fidelity remains unverified.');
      }
    }catch(err){notice(err.message,true)}finally{state.busy=false;render()}
  });
  void refresh(true);
  setInterval(()=>{if(!state.busy && document.visibilityState==='visible' && state.status && !document.activeElement?.matches('input,textarea,select')){void refresh(true)}},5000);
})();
