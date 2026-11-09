/* CutSceneAI Studio — real project discovery, planning, execution and result evidence.
   Advanced research console remains accessible through ?advanced=1. */
(() => {
  'use strict';
  const $ = q => document.querySelector(q);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const short = v => String(v || '').split(/[\\/]/).pop();
  const norm = v => String(v || '').replaceAll('\\','/').toLowerCase();
  const state = {screen:'home', phase:'IDLE', busy:false, info:'', error:'', status:null,
    discovery:null, folders:{unity:'',unreal:''}, unrealProject:'', csir:'', level:'',
    sourceRights:false, allowPartial:false, aiAgentsEnabled:false, agentStatus:null, candidate:null, job:null, verification:null,
    diagnosis:null, feedback:null, releaseReadiness:null, running:false, detailsOpen:false, menuOpen:false,
    censusOptions:[], censusPath:'', censusSelection:null, censusIssue:false};
  const pathRoot = () => String(state.status?.repo_root||'').replaceAll('\\','/');
  const connection = () => state.status?.connection;
  const worker = () => state.status?.unreal_worker || {};
  const readiness = () => state.status?.destination_readiness || {};
  const terminal = job => job && !['RUNNING','QUEUED'].includes(job.status);
  const generated = () => Boolean(state.job &&
    state.job.generation_status === 'GENERATED_UNVERIFIED' &&
    ['GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED',
      'GENERATED_DIAGNOSTIC_INCOMPLETE'].includes(state.job.status));
  const ico = name => ({check:'✓',folder:'▱',link:'↔',arrow:'➜',menu:'☰',alert:'!',down:'↓',layers:'▤',report:'▧'}[name]||'●');
  const button = (label,name,disabled=false,variant='primary') =>
    '<button type="button" class="button '+variant+'" data-action="'+name+'" '+(disabled?'disabled':'')+'>'+label+'</button>';
  function validEditor(){
    const c=connection(),d=readiness(),w=worker();
    return Boolean(c&&w.connected&&norm(w.project)===norm(c.target_project)&&
      (w.level===c.level_path||(c.auto_create_level&&d.status==='NEW_LEVEL_REQUIRED')));
  }
  function canAutoSetup(){
    const a=state.candidate?.automatic_setup||{},d=readiness();
    const collisions=['wrong_actor_types','wrong_asset_types','duplicate_actors']
      .some(k=>(d[k]||[]).length>0);
    return Boolean(a.available&&a.ready&&!collisions&&
      (d.status==='NEW_LEVEL_REQUIRED'||d.candidate_id===state.candidate.candidate_id)&&
      ['READY','SCENE_SETUP_REQUIRED','ASSETS_REQUIRED','NEW_LEVEL_REQUIRED'].includes(d.status));
  }
  function canExecute(){
    const d=readiness();return Boolean(validEditor()&&state.candidate&&!state.job&&
      ((d.ready&&d.candidate_id===state.candidate.candidate_id)||canAutoSetup()));
  }
  function progress(){
    const selected=state.screen==='results'?3:state.screen==='transfer'?2:state.candidate?1:0;
    return '<div class="steps" aria-label="Transfer workflow">'+
      ['Connect','Plan','Import','Results'].map((label,i)=>
        '<div class="step '+(i===selected?'active':i<selected?'done':'')+
        '"><span class="circle">'+(i<selected?ico('check'):i+1)+'</span><span>'+label+'</span></div>').join('')+'</div>';
  }
  function header(){
    return '<header class="topbar"><a href="/" class="brand">CUTSCENE AI <em>Studio</em></a>'+
      '<nav class="main-nav" aria-label="Main navigation">'+
      ['Home','Projects','About','Account'].map(n=>'<button data-action="'+n.toLowerCase()+'">'+n+'</button>').join('')+
      '<button class="hamburger" data-action="menu" aria-label="More options" aria-expanded="'+state.menuOpen+'">'+ico('menu')+'</button></nav></header>'+
      (state.menuOpen?'<div class="menu-pop"><a href="?advanced=1">Advanced research tools</a><button data-action="results">Results</button></div>':'');
  }
  function toast(){
    // Blocked errors are already presented with their full diagnostics in
    // the main content. Avoid a duplicate transient toast covering the UI.
    if(state.screen==='transfer'&&state.phase==='BLOCKED')return '';
    if(!state.error&&!state.info)return '';
    return '<div class="toast '+(state.error?'bad':'')+'" role="'+(state.error?'alert':'status')+'"><b>'+
      (state.error?ico('alert'):ico('check'))+'</b><span>'+esc(state.error||state.info)+
      '</span><button data-action="clear" aria-label="Dismiss message">×</button></div>';
  }
  function people(){
    return '<div class="horizon" aria-hidden="true">'+Array.from({length:12},(_,i)=>
      '<svg viewBox="0 0 24 70" width="25" height="'+(48+(i*13)%27)+'" class="person">'+
      '<circle cx="12" cy="8" r="6" fill="currentColor"/>'+
      '<path d="M7 18Q12 12 17 18L20 37 16 39 16 54 21 68 16 69 12 47 9 68 4 68 8 38 4 36Z" fill="currentColor"/>'+
      '<path d="m7 20-6 19m16-19 6 19" stroke="currentColor" stroke-width="4"/></svg>').join('')+'</div>';
  }
  function home(){
    return '<section class="landing"><div class="landing-center"><h1>CUTSCENE AI</h1>'+
      '<div class="studio-title"><i></i><span>STUDIO</span><i></i></div>'+
      '<p>Reconstruct editable cinematic sequences across game engines.</p>'+
      button('▶ &nbsp; Start Transfer','projects')+
      (state.job?(terminal(state.job)?
        '<div class="landing-previous">'+button('View Previous Transfer Report','results',false,'secondary')+'</div>':
        '<div class="landing-previous">'+button('View Active Transfer','resume-transfer',false,'secondary')+'</div>'):'')+
      '</div>'+people()+'</section>';
  }
  function card(kind,folder,ready){
    const name=kind==='unity'?'Unity':'Unreal Engine';
    return '<div class="engine-card '+(ready?'validated':'')+'"><div class="engine-heading"><span class="engine-icon">'+
      (kind==='unity'?'⬡':'Ⓤ')+'</span><strong>'+name+'</strong>'+
      (ready?'<span class="valid">'+ico('check')+'</span>':'')+'</div>'+
      '<small>'+esc(short(folder)||'Not selected')+'</small><label>Select '+name+' Project Folder</label>'+
      '<div class="folder-picker"><span title="'+esc(folder)+'">'+esc(folder||'Select a folder')+'</span>'+
      '<button type="button" data-action="browse-'+kind+'" aria-label="Browse '+name+'">'+ico('folder')+'</button></div></div>';
  }
  function line(active){
    return '<div class="connector '+(active?'connected':'')+'" aria-hidden="true"><div class="connector-line"></div>'+
      '<span class="connector-center">'+ico(active?'check':'link')+'</span></div>';
  }
  function select(name,title,options,picked,placeholder){
    return '<label class="choice"><span>'+title+'</span><select name="'+name+'" '+(!options.length?'disabled':'')+'>'+
      '<option value="">'+placeholder+'</option>'+
      options.map(row=>{const value=typeof row==='string'?row:row.path;
        const title=typeof row==='string'?short(row):(row.name||short(row.path));
        return '<option value="'+esc(value)+'" '+(value===picked?'selected':'')+'>'+esc(title)+'</option>';
      }).join('')+'</select></label>';
  }
  function projectForm(){
    const d=state.discovery||{},u=d.unity||{},r=d.unreal||{};
    const cutscenes=u.cutscenes||[],levels=r.levels||[],sources=d.unity_projects||[],
      unrealRoots=d.unreal_projects||[],projects=r.project_options||[];
    const csir=state.csir||(cutscenes.length===1?cutscenes[0].path:'');
    const level=state.level||r.active_level||(levels.length===1?levels[0]:'');
    const chosenU=u.folder||state.folders.unity,chosenR=r.folder||state.folders.unreal;
    const connected=Boolean(connection());
    const selectionChanged=connected&&(csir!==connection().csir||level!==connection().level_path);
    const activeJob=Boolean(state.job&&!terminal(state.job));
    // An approved candidate without a queued Unreal job is NOT an active
    // engine transfer. It must never leave Start Transfer silently disabled.
    const pendingCandidate=Boolean(connected&&state.running&&state.candidate&&!state.job);
    const matchingCensuses=state.censusOptions.filter(x=>x.project_identity_proven &&
      x.source_scope_matched && x.state!=='INVALID');
    let choices='';
    if(sources.length>1&&!u.folder)choices+=select('unity-project','Unity project',sources,state.folders.unity,'Choose project');
    if(unrealRoots.length>1&&!r.folder)choices+=select('unreal-project-root','Unreal project folder',unrealRoots,state.folders.unreal,'Choose Unreal project');
    if(projects.length>1)choices+=select('unreal-project-file','Unreal project file',projects,state.unrealProject,'Choose project');
    if(chosenU)choices+='<div class="project-choices">'+
      select('csir','Unity CSIR Export',cutscenes.map(x=>({...x,
        name:(x.name||'Cutscene')+' — '+short(x.path)})),csir,'Select a CSIR file')+
      select('level','Unreal Destination Level',levels,level,'Choose level')+
      (connected?'<section class="source-census-panel" aria-label="Source Census selection">'+
        select('census','Unity Source Census',matchingCensuses.map(x=>({...x,
        name:x.name+(x.strict_ready?' — source complete':
          ' — '+x.unresolved_components+' findings')})),state.censusPath,
        'Select a matching Source Census')+
        '<p class="subnote">Choose the exact CSIR and Source Census for this transfer. They must represent the same Unity project and cutscene.</p>'+
        (state.censusSelection?'<p class="subnote">Selected census: '+esc(short(state.censusPath))+
          ' · '+esc(state.censusSelection.unresolved_components)+' unresolved source findings, '+
          esc(state.censusSelection.source_snapshot_partial_count||0)+' partially captured components (Unreal fidelity unverified).</p>':
          '<p class="warning">Select a matching Source Census before starting the transfer.</p>')+
        (!matchingCensuses.length?'<p class="subnote">No compatible census found. In Unity run Discover Installed Feature Surface, then Refresh exports.</p>':'')+
        (state.censusOptions.length>matchingCensuses.length?
          '<p class="subnote">Other census files were excluded because their project or cutscene scope does not match.</p>':'')+
        '</section>':'')+
      '<div class="export-refresh-row">'+
      button('Refresh CSIR &amp; Census exports','refresh-exports',state.busy,'secondary')+
      (selectionChanged?'<p class="warning" role="status">CSIR or destination changed. Reconnect projects before starting a new transfer.</p>':'')+
      '</div></div>';
    const action=activeJob?
      button('View Active Transfer '+ico('arrow'),'resume-transfer',state.busy,'secondary'):
      connected&&(terminal(state.job)||selectionChanged)?
      button('Reconnect for a fresh transfer '+ico('link'),'connect',
        state.busy||!state.sourceRights||!d.ready||!csir||!level):
      pendingCandidate?
      button('Start New Transfer '+ico('arrow'),'start-fresh',
        state.busy||!state.sourceRights||!state.censusSelection):
      connected?button('Start Transfer '+ico('arrow'),'start',
        state.busy||!state.sourceRights||!state.censusSelection):
      button('Connect Projects '+ico('link'),'connect',state.busy||!d.ready||!csir||!level||!state.sourceRights);
    return progress()+'<main class="projects-view"><h1>'+(!chosenU?'Select Unity Project':!chosenR?'Select Unreal Project':'Connect Unity &amp; Unreal')+'</h1>'+
      '<form id="project-form"><div class="engine-pair">'+card('unity',chosenU,Boolean(u.folder))+
      (chosenU?line(connected):'')+(chosenU?card('unreal',chosenR,Boolean(r.folder||r.project)):'')+'</div>'+
      choices+(chosenU?'<div class="permissions"><label><input type="checkbox" name="source-rights" '+
      (state.sourceRights?'checked':'')+' /> I have permission to import the source assets</label>'+
      '<label><input type="checkbox" name="allow-partial" '+(state.allowPartial?'checked':'')+
      ' /> Allow best-effort conversion when source components are unsupported (reported as incomplete)</label>'+
      '<div class="ai-agents-option"><label><input type="checkbox" name="ai-agents" '+
      (state.aiAgentsEnabled?'checked':'')+
      ' /> Enable AI agents</label>'+
      '<p class="subnote">Optional LangGraph diagnosis and guarded repairs only if normal transfer is incomplete. Requires local agent dependencies and an API key; usage may incur model charges.</p></div></div>':'')+
      (Object.values(d.errors||{})).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+
      '<div class="center-actions">'+(chosenU?action:'')+'</div></form>'+
      (activeJob?'<p class="subnote">An Unreal job is already queued or running. View its progress before starting another transfer.</p>':
       pendingCandidate?'<p class="subnote">A previous candidate was prepared but no Unreal job was submitted. Start New Transfer safely creates a fresh candidate and preserves the earlier files; it does not replay the old one.</p>':
       connected?'<p class="subnote">Connected successfully. Start Transfer prepares, imports, generates, and inspects the result.</p>':'')+
      '</main>';
  }
  function research(){
    const c=state.candidate,v=state.verification;
    return '<details class="research" '+(state.detailsOpen?'open':'')+'><summary>Detailed report · CED, CineTwin and unresolved features</summary>'+
      (c?'<div class="fact">Planned actions <b>'+esc(c.action_total||0)+'</b></div>'+
      '<div class="fact">Planned imports <b>'+esc(c.automatic_setup?.planned_imports??'Unknown')+'</b></div>'+
      '<div class="fact">Planned actors <b>'+esc(c.automatic_setup?.planned_actors??'Unknown')+'</b></div>'+
      '<div class="fact">Unresolved source components <b>'+esc(c.source_unresolved_components??'Not assessed')+'</b></div>'+
      ((c?.source_snapshot_partial_count||state.censusSelection?.source_snapshot_partial_count)?
        '<div class="fact">Source-captured partial components <b>'+
        esc(c?.source_snapshot_partial_count||state.censusSelection?.source_snapshot_partial_count)+'</b></div>'+
        '<p class="subnote">These source components are recorded but full Unreal behavior remains unverified.</p>':'')+
      (c.automatic_setup?.blockers||[]).map(x=>'<p class="warning">'+esc(x)+'</p>').join('')+
      (c.automatic_setup?.warnings||[]).map(x=>'<p class="subnote">'+esc(x)+'</p>').join('')+
      (c.review_flags||[]).map(x=>'<p class="subnote">'+esc(x)+'</p>').join(''):'<p>Plan not prepared.</p>')+
      (state.job?'<div class="fact">Job status <b>'+esc(state.job.status)+'</b></div>':'')+
      (state.agentStatus?.enabled?'<div class="fact">LangGraph AI agents <b>'+esc(state.agentStatus.status||'WAITING')+'</b></div>'+
        '<div class="fact">Agent repair rounds <b>'+esc(state.agentStatus.iterations??0)+'</b></div>'+
        (state.agentStatus.failure?'<p class="warning">'+esc(state.agentStatus.failure)+'</p>':'')+
        (state.agentStatus.reasoning?'<p class="subnote">'+esc(state.agentStatus.reasoning)+'</p>':''):'')+
      (state.feedback?'<div class="fact">CineTwin/visual feedback <b>'+esc(state.feedback.status)+'</b></div>'+
        (state.feedback.issues||[]).map(row=>'<p class="warning">'+esc(row.category)+': '+
        esc(row.code||row.source||row.detail||row.status)+'</p>').join(''):'')+
      (state.releaseReadiness?.available?'<div class="fact">Independent release gate <b>'+
        esc(state.releaseReadiness.status)+'</b></div>'+
        (state.releaseReadiness.failed||[]).map(k=>'<p class="warning">Failed: '+esc(k)+
        ' — '+esc(state.releaseReadiness.checks?.[k]?.explanation||'')+'</p>').join('')+
        (state.releaseReadiness.incomplete||[]).map(k=>'<p class="subnote">Incomplete: '+esc(k)+
        ' — '+esc(state.releaseReadiness.checks?.[k]?.explanation||'')+'</p>').join(''):'')+
      (v?'<div class="fact">Native structure <b>'+esc(v.persistence?.native_structure||'Not verified')+'</b></div>'+
        '<div class="fact">Visual inspection <b>'+esc(v.visual?.status||'Not verified')+'</b></div>':'')+
      '<p class="subnote">Rendering, complete skeletal pose, signals, shaders and audio timing require independent source comparison. No perfect-transfer claim is made from generation alone.</p>'+
      '<a href="?advanced=1" class="report-link">Open advanced research controls and audits</a></details>';
  }
  function movement(){
    // Small original vector silhouettes, purely decorative. These are not
    // assertions that the named assets exist in the source cutscene.
    const silhouettes = [
      '<circle cx="16" cy="5" r="4"/><path d="M10 11h12l2 10h-4l-2-7v16h-4V20l-3 10H7l3-17z"/>',
      '<path d="M8 29h19v-4l-5-4 1-5-7-11-5-2-5 8 6 4-3 5 4 4-5 2z"/><circle cx="17" cy="12" r="1" fill="#080a09"/>',
      '<path d="M6 5l5 6 5-3 6 3 5-6-1 9 4 7-4 1-1 7h-6l-3-5-3 5H7l-1-7-4-1 4-7z"/><circle cx="12" cy="16" r="2" fill="#080a09"/><circle cx="21" cy="16" r="2" fill="#080a09"/>',
      '<path d="M11 16c0-9 10-9 10 0z"/><ellipse cx="16" cy="20" rx="15" ry="5"/><path d="M9 25l-3 6m10-6v6m7-6 3 6" stroke="currentColor" stroke-width="2"/>'
    ];
    return '<div class="movement" aria-hidden="true"><div class="movement-line"></div>'+
      silhouettes.map((shape,i)=>'<span class="asset '+['a','b','c','d'][i]+'">'+
      '<svg viewBox="0 0 32 32" width="22" height="22" fill="currentColor">'+shape+'</svg></span>').join('')+'</div>';
  }
  function transfer(){
    const phase=state.phase,d=readiness(),j=state.job||{};
    const activelyWorking=phase==='PREPARING'||phase==='READY_TO_QUEUE'||['RUNNING','QUEUED'].includes(j.status);
    const label=phase==='PREPARING'?'Preparing and validating transfer plan…':
      phase==='WAITING_FOR_EDITOR'?'Connect Unreal Editor to continue automatically':
      phase==='READY_TO_QUEUE'?'Checking destination readiness…':
      ['RUNNING','QUEUED'].includes(j.status)?'Transferring Assets and Generating Sequence…':
      phase==='BLOCKED'?'Transfer blocked':'Checking transfer…';
    const command='import sys; sys.path.insert(0, r"'+pathRoot()+
      '/integrations/unreal"); import studio_local_editor_worker as w; w.start()';
    return progress()+'<main class="transfer-view"><div class="engine-pair">'+
      card('unity',connection()?.unity_project||state.folders.unity,true)+line(true)+
      card('unreal',connection()?.target_project||state.folders.unreal,true)+'</div>'+
      (['RUNNING','QUEUED'].includes(j.status)?movement():'')+
      '<h2>'+esc(label)+'</h2>'+
      (state.censusSelection?.source_snapshot_partial_count?
        '<p class="subnote">'+esc(state.censusSelection.source_snapshot_partial_count)+
        ' native source snapshots recorded; collision, URP and signal behavior remains Unreal-unverified. See Detailed report.</p>':'')+
      (phase==='WAITING_FOR_EDITOR'?'<div class="editor-instructions"><p>Open your backed-up Unreal project with the selected saved level. In Unreal Python Console, run the companion command once. Studio will then continue without a second transfer click.</p>'+
        '<pre id="worker-command">'+esc(command)+'</pre>'+button('Copy Unreal companion command','copy-worker',false,'secondary')+
        '<p class="subnote">'+esc(d.next_action||'Waiting for the editor')+'</p></div>':'')+
      (phase==='BLOCKED'?'<p class="warning" role="alert">'+esc(state.error||j.error||d.next_action||'Read the diagnostic report')+'</p>':'')+
      (phase==='BLOCKED'&&state.censusIssue&&state.censusSelection?
        '<section class="census-blocker"><h3>'+esc(state.censusSelection.unresolved_components)+
        ' source features need review</h3><p>This is a source-coverage issue, not a failed Unreal import. The following features cannot yet be guaranteed to transfer:</p>'+
        '<div class="census-findings">'+(state.censusSelection.unresolved_findings||[])
          .map(f=>'<div class="census-finding"><strong>'+esc(f.native_type||'Unknown component')+
          '</strong><span>'+esc(f.object_path||f.scene_path||'Source object unknown')+
          '</span><small>'+esc(f.state||'UNRESOLVED')+'</small></div>').join('')+'</div>'+
        (state.censusSelection.findings_truncated?'<p class="subnote">Additional source findings are available in the advanced report.</p>':'')+
        '<p class="subnote">Recommended: improve the source extraction/adapters before transfer. To run a separate research-only best-effort candidate, explicitly accept that the missing source behavior will NOT be fidelity-verified.</p>'+
        button('Run labelled best-effort trial','best-effort',state.busy,'secondary')+
        '</section>':'')+
      '<div class="transfer-progress"><div class="indeterminate '+(activelyWorking?'working':'')+
      '" role="progressbar" aria-label="Transfer state" aria-valuetext="'+esc(label)+'"><i></i></div>'+
      '<span>'+esc(['RUNNING','QUEUED'].includes(j.status)?j.status:phase)+'</span></div>'+
      (terminal(state.job)?button('View Results '+ico('arrow'),'results'):'')+research()+'</main>';
  }
  function resultRow(name,value){
    return '<div class="result-row"><span>'+name+'</span><strong>'+esc(value)+'</strong></div>';
  }
  function failureDetails(){
    const j=state.job||{};
    if(!terminal(j)||generated())return '';
    const stage=j.failure_stage||j.execution_stage||'UNKNOWN_NATIVE_STAGE';
    const reason=j.error||j.setup_error||
      'No native error message was recorded. Open Unreal Editor Output Log and inspect the saved job JSON.';
    const step=j.setup_failed_step;
    const operation=step&&typeof step==='object'?
      [step.phase,step.name||step.kind||step.path||step.level].filter(Boolean).join(' — '):
      typeof step==='string'?step:'';
    const partial=j.status==='PARTIAL_SETUP_MUST_INSPECT'||
      j.setup_status==='PARTIAL_SETUP_MUST_INSPECT';
    const recovery=partial?
      'Unreal may already contain imported assets or newly created actors. Do not rerun this candidate. Inspect the staging level and import receipt, then create a fresh candidate after correcting the problem.':
      j.setup_recovery||
      'Inspect the Unreal Editor Output Log for this job, correct the reported issue, and start a new transfer using a fresh candidate. Do not overwrite any existing sequence.';
    return '<section class="transfer-failure" role="alert" aria-label="Native transfer error">'+
      '<h2>Transfer stopped before sequence generation</h2>'+
      '<p><strong>Execution stage:</strong> '+esc(stage)+'</p>'+
      '<p><strong>Native error:</strong> '+esc(reason)+'</p>'+
      (j.setup_status?'<p><strong>Asset setup:</strong> '+esc(j.setup_status)+'</p>':'')+
      (operation?'<p><strong>Failed operation:</strong> '+esc(operation)+'</p>':'')+
      '<p class="failure-recovery"><strong>What to do next:</strong> '+esc(recovery)+'</p>'+
      '<div class="failure-actions">'+button('Copy failure details','copy-failure',false,'secondary')+'</div>'+
      '<p class="subnote">Job '+esc(j.job_id||'unknown')+
      (j.created_at?' · Created '+esc(j.created_at):'')+
      ' · This is an execution failure, not a CineTwin fidelity comparison.</p></section>';
  }
  function results(){
    const j=state.job||{},v=state.verification||{},ok=generated(),candidate=state.candidate||{};
    const gate=state.releaseReadiness||{status:'INCOMPLETE',release_ready:false,incomplete:[]};
    const imports=Number.isInteger(j.assets_imported_count)?j.assets_imported_count:'Not independently verified';
    const bindings=Number.isInteger(j.bindings_created_count)?j.bindings_created_count:'Not independently verified';
    return progress()+'<main class="results-view"><div class="results-card '+(gate.release_ready?'ok':'')+'">'+
      '<h1>'+(gate.release_ready?'<span class="success-check">✓</span> Verified Release Transfer':
        ok?'Editable Sequence Generated — Fidelity Unverified':'Transfer Results')+'</h1>'+
      resultRow('Generated Sequence',ok?short(j.generated_sequence||j.sequence_path):'Not generated')+
      resultRow('Assets Imported',imports)+resultRow('Bindings Created',bindings)+
      '<div class="result-row"><span>Transfer Report</span><button class="report-link" data-action="view-report">View Report</button></div>'+
      '<p class="subnote">'+esc(j.status||'Not started')+' — '+(ok?'generation succeeded; fidelity is not certified':'no success claim')+'</p></div>'+
      failureDetails()+
      '<div class="verification"><p>Native structure: '+esc(ok?(v.persistence?.native_structure||'Not verified'):
        'Not verified — sequence generation did not finish')+'</p>'+
      '<p>Persistence after reopen: '+esc(!ok?'Not applicable until an editable sequence has been generated and saved':
        v.persistence?.restart_verified?'Verified in a different Unreal process':
        'Not verified — reopen the saved map in a new Unreal Editor process')+'</p>'+
      '<p>CineTwin behavioral parity: '+(state.diagnosis?'Measured — not full fidelity':'Not verified')+'</p>'+
      '<p>Visual fidelity: '+esc(v.visual?.status||'Not verified')+'</p>'+
      '<p><strong>Release readiness: '+esc(gate.release_ready?'VERIFIED':gate.status)+
      '</strong> · '+esc((gate.failed||[]).length)+' failed, '+
      esc((gate.incomplete||[]).length)+' incomplete checks</p>'+
      (state.agentStatus?.enabled?'<p>AI agents: '+esc(state.agentStatus.status)+
      ' · repair rounds '+esc(state.agentStatus.iterations??0)+'</p>':'')+'</div>'+
      research()+'<div class="center-actions">'+button('New Transfer','projects',false,'secondary')+'</div></main>';
  }
  function about(){return '<main class="about-view"><h1>CutSceneAI Studio</h1>'+
    '<p>This local system analyzes Unity cutscenes, plans native Unreal reconstruction, and measures known source-to-target differences. CineTwin and CED provide evidence and conversion strategies; unsupported effects are explicitly reported.</p>'+
    '<p>For full CED coverage, editing options, native audits and reports, use the <a href="?advanced=1">Advanced research workspace</a>.</p></main>';}
  // Reconcile the browser DOM, rather than replacing every node after each
  // two-second poll. This keeps ongoing CSS animations, focus, open details,
  // and the compositor layers alive while a status label changes.
  let lastMarkup = null;
  function reconcile(parent, freshParent){
    const original=Array.from(parent.childNodes);
    const incoming=Array.from(freshParent.childNodes);
    for(let i=0;i<incoming.length;i++){
      const next=incoming[i], old=original[i];
      if(!old){parent.appendChild(next.cloneNode(true));continue;}
      if(old.nodeType!==next.nodeType || old.nodeName!==next.nodeName){
        parent.replaceChild(next.cloneNode(true),old);continue;
      }
      if(old.nodeType===3 || old.nodeType===8){
        if(old.nodeValue!==next.nodeValue)old.nodeValue=next.nodeValue;
        continue;
      }
      if(old.nodeType!==1)continue;
      for(const attr of Array.from(old.attributes)){
        if(!next.hasAttribute(attr.name))old.removeAttribute(attr.name);
      }
      for(const attr of Array.from(next.attributes)){
        if(old.getAttribute(attr.name)!==attr.value)old.setAttribute(attr.name,attr.value);
      }
      if(old.tagName==='DETAILS' && old.hasAttribute('class') &&
        old.classList.contains('research')){
        // The browser's native details open state is authoritative.
        // The existing toggle listener remembers the user's preference.
        if(state.detailsOpen)old.setAttribute('open','');
        else old.removeAttribute('open');
      }
      if(old.tagName==='SELECT' && old===document.activeElement){
        // Preserve an actively open native dropdown until change/blur.
        continue;
      }
      if(old.tagName==='INPUT' && old===document.activeElement)continue;
      reconcile(old,next);
    }
    for(let i=original.length-1;i>=incoming.length;i--)parent.removeChild(original[i]);
  }
  function render(){
    const contents=state.screen==='home'?home():state.screen==='projects'?projectForm():
      state.screen==='transfer'?transfer():state.screen==='results'?results():about();
    const markup=header()+'<div class="page '+state.screen+'">'+contents+'</div>'+toast();
    if(markup===lastMarkup)return;
    const app=$('#app');
    lastMarkup=markup;
    if(typeof document.createElement==='function' &&
       typeof app.childNodes!=='undefined'){
      const fragment=document.createElement('template');
      fragment.innerHTML=markup;
      reconcile(app,fragment.content);
    }else{
      // Minimal DOM harness used by dependency-free Node regression tests.
      app.innerHTML=markup;
    }
  }
  async function api(route,data){
    const resp=await fetch('/api/'+route,{method:data===undefined?'GET':'POST',cache:'no-store',
      headers:data===undefined?{}:{'Content-Type':'application/json','X-CSAI-Token':state.status?.token||''},
      body:data===undefined?undefined:JSON.stringify(data)});
    let obj={};try{obj=await resp.json();}catch{throw Error('Invalid Studio server response.');}
    if(!resp.ok)throw Error(obj.error||'Request failed: '+resp.status);
    return obj;
  }
  async function scan(){
    const d=await api('discover',{unity_folder:state.folders.unity,unreal_folder:state.folders.unreal,
      unreal_project:state.unrealProject});
    state.discovery=d;
    if(d.unity?.folder)state.folders.unity=d.unity.folder;
    if(d.unreal?.folder)state.folders.unreal=d.unreal.folder;
    const sources=d.unity?.cutscenes||[],levels=d.unreal?.levels||[];
    if(!sources.some(x=>x.path===state.csir))state.csir=sources.length===1?sources[0].path:'';
    if(!levels.includes(state.level))state.level=d.unreal?.active_level||(levels.length===1?levels[0]:'');
    // Census choices must always be audited against the connected CSIR.
    if(connection() && state.csir===connection().csir)await loadCensuses();
    else{state.censusOptions=[];state.censusPath='';state.censusSelection=null;}
  }
  async function loadCensuses(){
    const response=await api('source-surfaces');
    state.censusOptions=response.options||[];
    const selected=state.censusOptions.find(x=>x.path===state.censusPath &&
      x.project_identity_proven && x.source_scope_matched && x.state!=='INVALID');
    state.censusSelection=selected||null;
    if(!selected)state.censusPath='';
  }
  async function connectProjects(){
    if(!state.discovery?.ready||!state.csir||!state.level||!state.sourceRights)
      throw Error('Choose a detected cutscene and level, and approve asset-copy rights.');
    const info=await api('connect-projects',{unity_folder:state.folders.unity,
      unreal_folder:state.folders.unreal,unreal_project:state.unrealProject,
      csir:state.csir,level:state.level,source_rights_confirmed:state.sourceRights});
    state.status.connection=info;state.candidate=null;state.job=null;state.verification=null;state.diagnosis=null;state.feedback=null;state.releaseReadiness=null;state.agentStatus=null;state.running=false;
    state.censusOptions=[];state.censusPath='';state.censusSelection=null;
    state.phase='CONNECTED';state.info='Projects connected. Choose a Source Census to start a transfer.';
    state.error='';state.censusIssue=false;
    await loadCensuses();
  }
  async function refresh(){
    const s=await api('status');state.status=s;
    if(!state.running)state.candidate=s.candidate||null;
    if(s.active_job)state.job=await api('jobs/'+s.active_job);
    if(state.aiAgentsEnabled||state.job?.ai_agents_enabled){
      try{state.agentStatus=await api('agents');}catch(e){
        state.agentStatus={enabled:true,status:'AGENT_STATUS_UNAVAILABLE',failure:String(e.message||e)};
      }
    }
    if(terminal(state.job)){
      state.phase=generated()?'COMPLETE':'BLOCKED';
      try{state.verification=await api('verification');}catch{}
      if(state.job?.diagnostic_file&&!state.diagnosis){
        try{state.diagnosis=await api('diagnostic/'+state.job.job_id);}catch{}
      }
      if(!state.feedback) {
        try{const feedback=await api('closed-loop');if(feedback.available)state.feedback=feedback;}catch{}
      }
      try{state.releaseReadiness=await api('release-readiness');}catch(e){
        state.releaseReadiness={status:'INCOMPLETE',release_ready:false,
          incomplete:['Release evidence unavailable: '+String(e.message||e)]};
      }
    }
  }
  async function prepare(){
    state.phase='PREPARING';render();
    const opts={enable_fbx_embedded_material_import:true,enable_actor_visibility_fallback:false};
    const chosen=state.censusPath;
    if(!chosen)throw Error('Choose a Source Census for this transfer before continuing.');
    // Revalidate the exact explicit choice. Do not switch to another census.
    await loadCensuses();
    if(!state.censusSelection||state.censusSelection.path!==chosen){
      throw Error('Selected Source Census is missing or does not match the connected CSIR. Refresh exports, select a matching census, and reconnect if the CSIR changed.');
    }
    opts.source_feature_surface_path=chosen;
    opts.require_complete_source_features=!state.allowPartial;
    if(!state.allowPartial && state.censusSelection &&
       !state.censusSelection.strict_ready){
      state.censusIssue=true;
      throw Error('Strict source census blocked: ' +
        state.censusSelection.unresolved_components +
        ' source component/scope findings. Review the exact findings below before choosing how to continue. No Unreal assets were modified.');
    }
    state.censusIssue=false;
    state.candidate=await api('prepare',opts);
    // An existing, independently ready Unreal level may not require imports.
    // Never treat an import blocker as permission to bypass editor readiness.
    state.phase='READY_TO_QUEUE';
    await api('approve-one-click',{candidate_id:state.candidate.candidate_id,
      enable_ai_agents:state.aiAgentsEnabled});
  }
  async function advance(){
    if(!state.running||state.busy||state.job||!state.candidate)return;
    if(!validEditor()){state.phase='WAITING_FOR_EDITOR';render();return;}
    const d=readiness();
    if(!d.ready && state.candidate.automatic_setup?.blockers?.length){
      throw Error('Unresolved source assets: '+state.candidate.automatic_setup.blockers.join('; '));
    }
    if(!canExecute()){
      if(['WRONG_TARGET','TARGET_EXISTS','UPGRADE_COMPANION','INSPECTION_FAILED'].includes(d.status))
        throw Error(d.next_action||d.status);
      state.phase='READY_TO_QUEUE';render();return;
    }
    // Start Transfer is the user approval for one guarded, non-overwriting
    // candidate. The backend revalidates source hashes, exact editor, level,
    // readiness, and non-overwrite requirements before accepting the job.
    state.busy=true;render();
    try{
      state.job=await api('execute',{candidate_id:state.candidate.candidate_id});
      state.phase='RUNNING';state.error='';
    }finally{state.busy=false;render();}
  }
  async function startFresh(){
    // User explicitly requested a new candidate instead of reusing the
    // restored approval. The backend refuses reconnect if an Unreal job
    // was queued while this screen was open.
    if(!connection()||state.job||!state.running||!state.candidate)
      throw Error('There is no unsubmitted candidate to replace. Inspect the active job or reconnect.');
    const chosenCSIR=state.csir,chosenLevel=state.level,chosenCensus=state.censusPath;
    if(!chosenCensus||!state.censusSelection)
      throw Error('Choose a matching Source Census before starting a fresh transfer.');
    await connectProjects();
    if(state.csir!==chosenCSIR||state.level!==chosenLevel)
      throw Error('Connected source or destination changed. Select the correct CSIR and level again.');
    const selected=state.censusOptions.find(x=>x.path===chosenCensus &&
      x.project_identity_proven&&x.source_scope_matched&&x.state!=='INVALID');
    if(!selected)
      throw Error('The selected Source Census is no longer valid. Refresh exports and select it again; no transfer was prepared.');
    state.censusPath=chosenCensus;
    state.censusSelection=selected;
    await start();
  }
  async function start(){
    if(!connection()||!state.sourceRights)throw Error('Connect projects and confirm asset-copy rights.');
    if(state.csir!==connection().csir||state.level!==connection().level_path)
      throw Error('Selected CSIR or level changed. Reconnect projects before transferring.');
    if(!state.censusPath||!state.censusSelection)
      throw Error('Select a matching Source Census before starting this transfer.');
    if(state.running||state.job)throw Error('A candidate is already active; inspect it before creating another.');
    state.screen='transfer';state.running=true;
    await prepare();await refresh();
    state.phase='WAITING_FOR_EDITOR';render();await advance();
  }
  async function restore(){
    try{
      await refresh();
      if(connection()){
        state.folders.unity=connection().unity_project||'';
        state.folders.unreal=String(connection().target_project||'').replace(/[\\/][^\\/]+$/,'');
        state.csir=connection().csir;state.level=connection().level_path;
        state.unrealProject=connection().target_project;
        state.sourceRights=Boolean(connection().source_rights_confirmed);
        state.aiAgentsEnabled=state.job?Boolean(state.job.ai_agents_enabled):
          Boolean(state.status.one_click_approval?.enable_ai_agents);
        // A browser restart always lands on Home. Preserve server-side
        // transfer/report state, but never auto-navigate to the last report.
        state.screen='home';
        const approval=state.status.one_click_approval;
        state.running=Boolean(state.job||(approval?.candidate_id&&
          approval.candidate_id===state.candidate?.candidate_id&&
          approval.source_csir===connection().csir));
        if(!terminal(state.job)&&state.job)state.phase='RUNNING';
        else if(state.running&&!state.job){state.phase='WAITING_FOR_EDITOR';}
        try{await scan();}catch{}
      }
    }catch(e){state.error=e.message;}render();
  }
  let polling=false;
  async function tick(){
    // Don't allow overlapping /api/status or /api/execute requests: stale
    // responses must not replace a more recent or user-selected screen.
    if(polling||state.busy||!state.status)return;
    polling=true;
    try{
      await refresh();
      if(state.running&&state.phase!=='BLOCKED'&&!state.job&&state.candidate)await advance();
      if(state.running&&terminal(state.job)&&state.screen==='transfer')state.screen='results';
      render();
    }catch(e){state.error=e.message;state.phase='BLOCKED';state.running=false;render();}
    finally{polling=false;}
  }
  async function action(name){
    if(name==='clear'){state.info='';state.error='';render();return;}
    if(name==='menu'){state.menuOpen=!state.menuOpen;render();return;}
    if(['home','projects','results','about'].includes(name)){
      state.screen=name;state.menuOpen=false;
      if(name==='projects'&&!state.discovery&&state.folders.unity)try{await scan();}catch{}
      render();return;
    }
    if(name==='refresh-exports'){
      if(state.busy)return;
      state.busy=true;render();
      try{
        await scan();
        state.info='Export list refreshed. Confirm your CSIR and Source Census selections.';
        state.error='';
      }catch(e){state.error=e.message;}
      finally{state.busy=false;render();}
      return;
    }
    if(name==='resume-transfer'){
      if((state.job&&!terminal(state.job))||
         (state.running&&state.candidate&&!state.job)){
        state.screen='transfer';render();
      }
      return;
    }
    if(name==='account'){state.info='Account management is not implemented in this local Studio build.';render();return;}
    if(name==='best-effort'){
      if(!state.censusIssue || !state.censusSelection ||
         !state.censusSelection.project_identity_proven ||
         !state.censusSelection.source_scope_matched ||
         state.job || !connection() || !state.sourceRights)return;
      state.allowPartial=true;
      state.censusIssue=false;
      state.error='';state.busy=true;state.running=true;state.screen='transfer';
      render();
      try{
        await prepare();
        await refresh();
        state.phase='WAITING_FOR_EDITOR';
        await advance();
      }catch(e){state.error=e.message;state.phase='BLOCKED';state.running=false;}
      finally{state.busy=false;render();}
      return;
    }
    if(name==='view-report'){state.detailsOpen=true;render();$('.research')?.scrollIntoView({behavior:'smooth'});return;}
    if(name==='copy-failure'){
      const j=state.job||{},step=j.setup_failed_step;
      const operation=step&&typeof step==='object'?
        [step.phase,step.name||step.kind||step.path||step.level].filter(Boolean).join(' — '):
        typeof step==='string'?step:'';
      const report=[
        'CutSceneAI Studio — Native transfer failure',
        'Job: '+(j.job_id||'unknown'),
        'Candidate: '+(j.candidate_id||'unknown'),
        'Created: '+(j.created_at||'unknown'),
        'Status: '+(j.status||'unknown'),
        'Generation: '+(j.generation_status||'unknown'),
        'Stage: '+(j.failure_stage||j.execution_stage||'unknown'),
        'Cause: '+(j.error||j.setup_error||'No error recorded'),
        'Asset setup: '+(j.setup_status||'not recorded'),
        operation?'Failed operation: '+operation:'',
        j.setup_recovery?'Recovery: '+j.setup_recovery:'',
      ].filter(Boolean).join('\n');
      try{
        await navigator.clipboard.writeText(report);
        state.info='Native failure details copied. Review for sensitive local paths before sharing.';
        state.error='';
      }catch{state.error='Could not copy the failure details. Read the error above or inspect the saved job JSON.';}
      render();return;
    }
    if(name==='copy-worker'){
      try{await navigator.clipboard.writeText($('#worker-command').textContent);
        state.info='Unreal Editor companion command copied.';}
      catch{state.error='Copy the command manually from the box.';}render();return;
    }
    if(name==='browse-unity'||name==='browse-unreal'){
      state.busy=true;render();
      try{
        const kind=name.slice(7),choice=await api('pick-folder',{kind});
        if(!choice.cancelled){
          state.folders[kind]=choice.path;
          if(kind==='unreal')state.unrealProject='';
          state.discovery=null;state.csir='';state.level='';
          state.censusOptions=[];state.censusPath='';state.censusSelection=null;
          await scan();state.error='';
        }
      }catch(e){state.error=e.message;}finally{state.busy=false;render();}return;
    }
    if(name==='connect'||name==='start'||name==='start-fresh'){
      if(state.busy)return;
      state.busy=true;render();
      try{
        if(name==='connect')await connectProjects();
        else if(name==='start-fresh')await startFresh();
        else await start();
      }
      catch(e){state.error=e.message;state.phase='BLOCKED';state.running=false;}
      finally{state.busy=false;render();}return;
    }
  }
  $('#app').addEventListener('click',e=>{
    const node=e.target.closest('[data-action]');if(node)void action(node.dataset.action);
  });
  $('#app').addEventListener('change',async e=>{
    const n=e.target?.name,v=e.target?.value;
    if(n==='source-rights'){state.sourceRights=e.target.checked;render();return;}
    if(n==='allow-partial'){state.allowPartial=e.target.checked;render();return;}
    if(n==='ai-agents'){state.aiAgentsEnabled=e.target.checked;render();return;}
    if(n==='csir'){
      state.csir=v;state.censusOptions=[];state.censusPath='';state.censusSelection=null;
      render();return;
    }
    if(n==='census'){
      const selected=state.censusOptions.find(x=>x.path===v&&
        x.project_identity_proven&&x.source_scope_matched&&x.state!=='INVALID');
      state.censusSelection=selected||null;
      state.censusPath=selected?selected.path:'';
      state.censusIssue=false;render();return;
    }
    if(n==='level'){state.level=v;render();return;}
    if(['unity-project','unreal-project-root','unreal-project-file'].includes(n)){
      if(n==='unity-project')state.folders.unity=v;
      else if(n==='unreal-project-root'){state.folders.unreal=v;state.unrealProject='';}
      else state.unrealProject=v;
      state.busy=true;render();try{await scan();}catch(e){state.error=e.message;}
      finally{state.busy=false;render();}
    }
  });
  $('#app').addEventListener('toggle',e=>{if(e.target.matches('.research'))state.detailsOpen=e.target.open;},true);
  void restore();
  setInterval(()=>{if(document.visibilityState==='visible')void tick();},2000);
})();
