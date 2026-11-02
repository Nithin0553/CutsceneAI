/* Mock-backend UI integration regression, using only Node's built-in vm/assert. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const src = fs.readFileSync('apps/studio-web/cinematic.js', 'utf8');

function boot({editorReady = true, censusUnresolved = false} = {}) {
  const listeners = {}, calls = [], requests = [];
  let html = '', writes = 0;
  const app = {
    get innerHTML() {return html;},
    set innerHTML(value) {html=value;writes++;},
    addEventListener(name, fn) { listeners[name] = fn; },
  };
  let poll;
  let connected = null;
  let candidate = null;
  let currentJob = null;
  let done = false;
  const unity = 'D:/CutSceneAI_Unity';
  const unreal = 'D:/CutSceneAI_Unreal';
  const csir = unity + '/CutSceneAI/Exports/Benchmark002.csir.json';
  const level = '/Game/CutSceneAI/L_Trial01';
  const file = unreal + '/CutSceneAI.uproject';
  const fake = {
    document: {querySelector(sel) {
      if (sel === '#app') return app;
      return null;
    }, visibilityState: 'visible'},
    navigator: {clipboard: {writeText: async () => {}}},
    setInterval(fn) { poll = fn; },
    fetch: async (url, opts = {}) => {
      calls.push(url);
      const body = opts.body ? JSON.parse(opts.body) : {};
      requests.push({url,body});
      let result = {};
      if (url === '/api/status') {
        result = {token: 'stubtoken', repo_root: 'B:/Research/CutSceneAI/CutsceneAI',
          connection: connected, candidate, active_job: currentJob?.job_id || null,
          unreal_worker: {connected: editorReady, project: file, level, worker_version: 'studio-editor-v0.5'},
          destination_readiness: candidate && editorReady ?
            {status: 'READY', ready:true, candidate_id:candidate.candidate_id} :
            {status: 'WAITING_FOR_UNREAL', ready:false, next_action:'Open Unreal Editor'}};
      } else if (url === '/api/pick-folder') {
        result = {cancelled:false, path:body.kind==='unity'?unity:unreal};
      } else if (url === '/api/discover') {
        result = {ready: Boolean(body.unity_folder && body.unreal_folder),
          unity:{folder:body.unity_folder||'',cutscenes:[{name:'Benchmark002',path:csir}]},
          unreal:{folder:body.unreal_folder||'',project:file,levels:[level],active_level:level}};
      } else if (url === '/api/connect-projects') {
        connected = {unity_project:unity,target_project:file,level_path:level,
          csir,scene_name:'Benchmark002',source_rights_confirmed:true};
        result = connected;
      } else if (url === '/api/source-surfaces') {
        result = {options:censusUnresolved?[{
          name:'feature-surface-unity-Benchmark001.json',
          path:unity+'/CutSceneAI/Exports/feature-surface-unity-Benchmark001.json',
          project_identity_proven:true, source_scope_matched:true,
          strict_ready:false, state:'REVIEW_REQUIRED',
          unresolved_components:7,
          unresolved_findings:[{
            native_type:'UnityEngine.Playables.DirectorWrapMode',
            object_path:'Benchmark001/Director',state:'NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED'
          }]
        }]:[]};
      } else if (url === '/api/prepare') {
        candidate = {candidate_id:'candidate001',action_total:29,
          automatic_setup:{available:true,ready:true,blockers:[],planned_imports:18,planned_actors:10}};
        result = candidate;
      } else if (url === '/api/approve-one-click') {
        assert.equal(body.candidate_id,'candidate001');
        result={approved:true,candidate_id:body.candidate_id};
      } else if (url === '/api/execute') {
        assert.equal(body.candidate_id,'candidate001');
        currentJob = {job_id:'a'.repeat(32),status:'QUEUED',generation_status:'NOT_STARTED'};
        result=currentJob;
      } else if (url.startsWith('/api/jobs/')) {
        result=done ? {...currentJob,status:'GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED',
          generation_status:'GENERATED_UNVERIFIED',generated_sequence:'/Game/Trial/LS_Benchmark002',
          setup_status:'SETUP_SAVED_UNVERIFIED',assets_imported_count:18,
          bindings_created_count:12,diagnostic_file:'real-native-evidence.json'} : currentJob;
      } else if (url === '/api/verification') {
        result={persistence:{native_structure:'PASS',status:'PERSISTENCE_NOT_REOPENED'},
          visual:{status:'VISUAL_COMPLETENESS_REVIEW_REQUIRED'}};
      } else if (url === '/api/diagnostic/'+'a'.repeat(32)) {
        result={entities:{A:{actor_max_cm:10}}};
      } else if (url === '/api/agents') {
        result={enabled:true,status:'UNRESOLVED_NO_SAFE_STRATEGY',
          iterations:0,reasoning:'No source-backed repair for remaining issues'};
      } else if (url === '/api/release-readiness') {
        result={available:true,status:'INCOMPLETE',release_ready:false,
          failed:[],incomplete:['rendered_frame_parity','heldout_project_validation'],
          checks:{rendered_frame_parity:{status:'INCOMPLETE',explanation:'Frames unverified'},
            heldout_project_validation:{status:'INCOMPLETE',explanation:'Held-out test missing'}}};
      } else if (url === '/api/closed-loop') {
        result={available:true,status:'REVIEW_REQUIRED',issues:[{category:'VISUAL_NATIVE_READBACK',code:'NO_DIRECTIONAL_LIGHT_FOUND'}]};
      } else {
        throw new Error('Unexpected API request '+url);
      }
      return {ok:true,status:200,json:async()=>result};
    },
    console, Promise,
  };
  vm.runInNewContext(src,fake,{filename:'cinematic.js'});
  const pause = () => new Promise(resolve => setTimeout(resolve, 0));
  async function click(action) {
    listeners.click({target:{closest(selector) {
      return selector === '[data-action]' ? {dataset:{action}} : null;
    }}});
    await pause();
  }
  async function change(name, value, checked=false) {
    listeners.change({target:{name,value,checked}});
    await pause();
  }
  return {app,calls,requests,click,change,poll:async()=>{poll();await pause();await pause();},
    writes:()=>writes, pause,finish:()=>{done=true;}};
}

async function testOneClick() {
  const x=boot({editorReady:true});
  await x.pause();
  assert.match(x.app.innerHTML,/CUTSCENE AI/);
  await x.click('projects');
  assert.match(x.app.innerHTML,/Select Unity Project/);
  await x.click('browse-unity');
  await x.click('browse-unreal');
  assert.match(x.app.innerHTML,/Unity Timeline/);
  assert.match(x.app.innerHTML,/Enable AI agents/);
  assert.doesNotMatch(x.app.innerHTML.match(/name="ai-agents"([^>]*)>/)[1],/checked/,
    'agent mode must default to off');
  await x.change('ai-agents',null,true);
  assert.match(x.app.innerHTML.match(/name="ai-agents"([^>]*)>/)[1],/checked/,
    'checkbox must react to user opt-in');
  await x.change('ai-agents',null,false);
  assert.doesNotMatch(x.app.innerHTML.match(/name="ai-agents"([^>]*)>/)[1],/checked/);
  await x.change('ai-agents',null,true);
  await x.change('source-rights',null,true);
  await x.click('connect');
  assert.ok(x.calls.includes('/api/connect-projects'));
  assert.match(x.app.innerHTML,/Start Transfer/);
  await x.click('start');
  await x.poll();
  assert.deepEqual(x.calls.filter(v=>v==='/api/execute').length,1);
  assert.ok(x.calls.indexOf('/api/prepare')<x.calls.indexOf('/api/approve-one-click'));
  assert.ok(x.calls.indexOf('/api/approve-one-click')<x.calls.indexOf('/api/execute'));
  const preparation=x.requests.find(req=>req.url==='/api/prepare');
  assert.ok(preparation);
  assert.equal(Object.hasOwn(preparation.body,'enable_ai_agents'),false,
    'normal source preparation remains deterministic');
  const approval=x.requests.find(req=>req.url==='/api/approve-one-click');
  assert.equal(approval.body.enable_ai_agents,true,
    'explicit opt-in must be bound to one candidate approval');
  assert.ok(x.calls.some(url=>url==='/api/agents'),
    'enabled UI should show actual agent status');
  x.finish();
  await x.poll();
  assert.match(x.app.innerHTML,/Sequence Generated Successfully/);
  assert.match(x.app.innerHTML,/18/);
  assert.match(x.app.innerHTML,/12/);
  assert.match(x.app.innerHTML,/not certified/);
  assert.match(x.app.innerHTML,/Release readiness: INCOMPLETE/);
  assert.ok(x.calls.includes('/api/release-readiness'),
    'a generated sequence must be independently checked for release readiness');
  assert.ok(!x.app.innerHTML.includes('72%'));
  const writes=x.writes();
  await x.poll();
  assert.equal(x.writes(),writes,'unchanged heartbeat must not reset the DOM');
}

async function testOfflineDoesNotExecute() {
  const x=boot({editorReady:false});
  await x.pause();
  await x.click('projects');
  await x.click('browse-unity');
  await x.click('browse-unreal');
  await x.change('source-rights',null,true);
  await x.click('connect');
  await x.click('start');
  await x.poll();
  assert.equal(x.calls.filter(v=>v==='/api/execute').length,0);
  assert.match(x.app.innerHTML,/Copy Unreal companion command/);
  assert.match(x.app.innerHTML,/WAITING_FOR_EDITOR/);
}

async function testStrictCensusBlockAndExplicitRecovery() {
  const x=boot({editorReady:true,censusUnresolved:true});
  await x.pause();
  await x.click('projects');
  await x.click('browse-unity');
  await x.click('browse-unreal');
  await x.change('source-rights',null,true);
  await x.click('connect');
  await x.click('start');
  assert.equal(x.calls.filter(v=>v==='/api/execute').length,0,
    'strict incomplete source census cannot queue engine execution');
  assert.match(x.app.innerHTML,/7 source features need review/);
  assert.match(x.app.innerHTML,/Benchmark001\/Director/);
  assert.match(x.app.innerHTML,/Run labelled best-effort trial/);
  await x.click('best-effort');
  await x.poll();
  assert.equal(x.calls.filter(v=>v==='/api/execute').length,1,
    'only explicit best-effort opt-in may submit a separate candidate');
}

(async()=>{
  await testOneClick();
  await testOfflineDoesNotExecute();
  await testStrictCensusBlockAndExplicitRecovery();
  console.log('Cinematic UI backend contract: 3 integration paths and optional AI checkbox checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
