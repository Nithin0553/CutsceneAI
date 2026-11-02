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
    sourceRights:false, allowPartial:false, candidate:null, job:null, verification:null,
    diagnosis:null, feedback:null, running:false, detailsOpen:false, menuOpen:false};
  const pathRoot = () => String(state.status?.repo_root||'').replaceAll('\\','/');
  const connection = () => state.status?.connection;
  const worker = () => state.status?.unreal_worker || {};
  const readiness = () => state.status?.destination_readiness || {};
  const terminal = job => job && !['RUNNING','QUEUED'].includes(job.status);
  const generated = () => state.job && (state.job.generation_status === 'GENERATED_UNVERIFIED' ||
    String(state.job.status||'').startsWith('GENERATED'));
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
      button('▶ &nbsp; Start Transfer','projects')+'</div>'+people()+'</section>';
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
    let choices='';
    if(sources.length>1&&!u.folder)choices+=select('unity-project','Unity project',sources,state.folders.unity,'Choose project');
    if(unrealRoots.length>1&&!r.folder)choices+=select('unreal-project-root','Unreal project folder',unrealRoots,state.folders.unreal,'Choose Unreal project');
    if(projects.length>1)choices+=select('unreal-project-file','Unreal project file',projects,state.unrealProject,'Choose project');
    if(chosenU)choices+='<div class="project-choices">'+select('csir','Unity Timeline',cutscenes,csir,'Choose exported timeline')+
      select('level','Unreal Destination Level',levels,level,'Choose level')+'</div>';
    const connected=Boolean(connection());
    const action=connected&&terminal(state.job)?button('Reconnect for a fresh transfer '+ico('link'),'connect',state.busy||!state.sourceRights):
      connected?button('Start Transfer '+ico('arrow'),'start',state.busy||!state.sourceRights||state.running):
      button('Connect Projects '+ico('link'),'connect',state.busy||!d.ready||!csir||!level||!state.sourceRights);
    return progress()+'<main class="projects-view"><h1>'+(!chosenU?'Select Unity Project':!chosenR?'Select Unreal Project':'Connect Unity &amp; Unreal')+'</h1>'+
      '<form id="project-form"><div class="engine-pair">'+card('unity',chosenU,Boolean(u.folder))+
      (chosenU?line(connected):'')+(chosenU?card('unreal',chosenR,Boolean(r.folder||r.project)):'')+'</div>'+
      choices+(chosenU?'<div class="permissions"><label><input type="checkbox" name="source-rights" '+
      (state.sourceRights?'checked':'')+' /> I have permission to import the source assets</label>'+
      '<label><input type="checkbox" name="allow-partial" '+(state.allowPartial?'checked':'')+
      ' /> Allow best-effort conversion when source components are unsupported (reported as incomplete)</label></div>':'')+
      (Object.values(d.errors||{})).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+
      '<div class="center-actions">'+(chosenU?action:'')+'</div></form>'+
      (connected?'<p class="subnote">Connected successfully. Start Transfer automatically prepares, imports, generates, and inspects the result.</p>':'')+
      '</main>';
  }
  function research(){
    const c=state.candidate,v=state.verification;
    return '<details class="research" '+(state.detailsOpen?'open':'')+'><summary>Detailed report · CED, CineTwin and unresolved features</summary>'+
      (c?'<div class="fact">Planned actions <b>'+esc(c.action_total||0)+'</b></div>'+
      '<div class="fact">Planned imports <b>'+esc(c.automatic_setup?.planned_imports??'Unknown')+'</b></div>'+
      '<div class="fact">Planned actors <b>'+esc(c.automatic_setup?.planned_actors??'Unknown')+'</b></div>'+
      '<div class="fact">Unresolved source components <b>'+esc(c.source_unresolved_components??'Not assessed')+'</b></div>'+
      (c.automatic_setup?.blockers||[]).map(x=>'<p class="warning">'+esc(x)+'</p>').join('')+
      (c.automatic_setup?.warnings||[]).map(x=>'<p class="subnote">'+esc(x)+'</p>').join('')+
      (c.review_flags||[]).map(x=>'<p class="subnote">'+esc(x)+'</p>').join(''):'<p>Plan not prepared.</p>')+
      (state.job?'<div class="fact">Job status <b>'+esc(state.job.status)+'</b></div>':'')+
      (state.feedback?'<div class="fact">CineTwin/visual feedback <b>'+esc(state.feedback.status)+'</b></div>'+
        (state.feedback.issues||[]).map(row=>'<p class="warning">'+esc(row.category)+': '+
        esc(row.code||row.source||row.detail||row.status)+'</p>').join(''):'')+
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
      (phase==='WAITING_FOR_EDITOR'?'<div class="editor-instructions"><p>Open your backed-up Unreal project with the selected saved level. In Unreal Python Console, run the companion command once. Studio will then continue without a second transfer click.</p>'+
        '<pre id="worker-command">'+esc(command)+'</pre>'+button('Copy Unreal companion command','copy-worker',false,'secondary')+
        '<p class="subnote">'+esc(d.next_action||'Waiting for the editor')+'</p></div>':'')+
      (phase==='BLOCKED'?'<p class="warning" role="alert">'+esc(state.error||j.error||d.next_action||'Read the diagnostic report')+'</p>':'')+
      '<div class="transfer-progress"><div class="indeterminate '+(activelyWorking?'working':'')+
      '" role="progressbar" aria-label="Transfer state" aria-valuetext="'+esc(label)+'"><i></i></div>'+
      '<span>'+esc(['RUNNING','QUEUED'].includes(j.status)?j.status:phase)+'</span></div>'+
      (terminal(state.job)?button('View Results '+ico('arrow'),'results'):'')+research()+'</main>';
  }
  function resultRow(name,value){
    return '<div class="result-row"><span>'+name+'</span><strong>'+esc(value)+'</strong></div>';
  }
  function results(){
    const j=state.job||{},v=state.verification||{},ok=generated(),candidate=state.candidate||{};
    const imports=Number.isInteger(j.assets_imported_count)?j.assets_imported_count:'Not independently verified';
    const bindings=Number.isInteger(j.bindings_created_count)?j.bindings_created_count:'Not independently verified';
    return progress()+'<main class="results-view"><div class="results-card '+(ok?'ok':'')+'">'+
      '<h1>'+(ok?'<span class="success-check">✓</span> Sequence Generated Successfully':'Transfer Results')+'</h1>'+
      resultRow('Generated Sequence',ok?short(j.generated_sequence||j.sequence_path):'Not generated')+
      resultRow('Assets Imported',imports)+resultRow('Bindings Created',bindings)+
      '<div class="result-row"><span>Transfer Report</span><button class="report-link" data-action="view-report">View Report</button></div>'+
      '<p class="subnote">'+esc(j.status||'Not started')+' — '+(ok?'generation succeeded; fidelity is not certified':'no success claim')+'</p></div>'+
      '<div class="verification"><p>Native structure: '+esc(v.persistence?.native_structure||'Not verified')+'</p>'+
      '<p>Persistence after reopen: '+esc(v.persistence?.status||'Not verified')+'</p>'+
      '<p>CineTwin behavioral parity: '+(state.diagnosis?'Measured — not full fidelity':'Not verified')+'</p>'+
      '<p>Visual fidelity: '+esc(v.visual?.status||'Not verified')+'</p></div>'+
      research()+'<div class="center-actions">'+button('New Transfer','projects',false,'secondary')+'</div></main>';
  }
  function about(){return '<main class="about-view"><h1>CutSceneAI Studio</h1>'+
    '<p>This local system analyzes Unity cutscenes, plans native Unreal reconstruction, and measures known source-to-target differences. CineTwin and CED provide evidence and conversion strategies; unsupported effects are explicitly reported.</p>'+
    '<p>For full CED coverage, editing options, native audits and reports, use the <a href="?advanced=1">Advanced research workspace</a>.</p></main>';}
  // A full innerHTML replacement tears down focus, restarts CSS animations,
  // and makes the screen flash at every 2-second editor heartbeat. Retain
  // the current DOM until the *visible* application state actually changes.
  let lastMarkup = null;
  function render(){
    const contents=state.screen==='home'?home():state.screen==='projects'?projectForm():
      state.screen==='transfer'?transfer():state.screen==='results'?results():about();
    const markup=header()+'<div class="page '+state.screen+'">'+contents+'</div>'+toast();
    if (markup===lastMarkup) return;
    // Focused selects/inputs, open reports and native folder dialogs must not
    // be destroyed by routine background polling. Queue their refresh until
    // the user finishes the interaction; explicit event handlers still render.
    const app=$('#app');
    lastMarkup=markup;
    app.innerHTML=markup;
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
  }
  async function connectProjects(){
    if(!state.discovery?.ready||!state.csir||!state.level||!state.sourceRights)
      throw Error('Choose a detected cutscene and level, and approve asset-copy rights.');
    const info=await api('connect-projects',{unity_folder:state.folders.unity,
      unreal_folder:state.folders.unreal,unreal_project:state.unrealProject,
      csir:state.csir,level:state.level,source_rights_confirmed:state.sourceRights});
    state.status.connection=info;state.candidate=null;state.job=null;state.verification=null;state.diagnosis=null;state.feedback=null;state.running=false;
    state.phase='CONNECTED';state.info='Projects connected successfully!';state.error='';
  }
  async function refresh(){
    const s=await api('status');state.status=s;
    if(!state.running)state.candidate=s.candidate||null;
    if(s.active_job)state.job=await api('jobs/'+s.active_job);
    if(terminal(state.job)){
      state.phase=generated()?'COMPLETE':'BLOCKED';
      try{state.verification=await api('verification');}catch{}
      if(state.job?.diagnostic_file&&!state.diagnosis){
        try{state.diagnosis=await api('diagnostic/'+state.job.job_id);}catch{}
      }
      if(!state.feedback) {
        try{const feedback=await api('closed-loop');if(feedback.available)state.feedback=feedback;}catch{}
      }
    }
  }
  async function prepare(){
    state.phase='PREPARING';render();
    const opts={enable_fbx_embedded_material_import:true,enable_actor_visibility_fallback:false};
    const surfaces=await api('source-surfaces');
    const matches=(surfaces.options||[]).filter(x=>x.project_identity_proven);
    if(matches.length){
      opts.source_feature_surface_path=matches[0].path;
      opts.require_complete_source_features=!state.allowPartial;
    }
    state.candidate=await api('prepare',opts);
    // An existing, independently ready Unreal level may not require imports.
    // Never treat an import blocker as permission to bypass editor readiness.
    state.phase='READY_TO_QUEUE';
    await api('approve-one-click',{candidate_id:state.candidate.candidate_id});
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
  async function start(){
    if(!connection()||!state.sourceRights)throw Error('Connect projects and confirm asset-copy rights.');
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
        state.screen=state.job?(terminal(state.job)?'results':'transfer'):'projects';
        const approval=state.status.one_click_approval;
        state.running=Boolean(state.job||(approval?.candidate_id&&
          approval.candidate_id===state.candidate?.candidate_id&&
          approval.source_csir===connection().csir));
        if(!terminal(state.job)&&state.job)state.phase='RUNNING';
        else if(state.running&&!state.job){state.screen='transfer';state.phase='WAITING_FOR_EDITOR';}
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
    if(name==='account'){state.info='Account management is not implemented in this local Studio build.';render();return;}
    if(name==='view-report'){state.detailsOpen=true;render();$('.research')?.scrollIntoView({behavior:'smooth'});return;}
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
          await scan();state.error='';
        }
      }catch(e){state.error=e.message;}finally{state.busy=false;render();}return;
    }
    if(name==='connect'||name==='start'){
      if(state.busy)return;
      state.busy=true;render();
      try{if(name==='connect')await connectProjects();else await start();}
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
    if(n==='csir'){state.csir=v;render();return;}
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
