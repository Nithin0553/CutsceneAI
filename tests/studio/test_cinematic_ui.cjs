/* Mock-backend UI integration regression, using only Node's built-in vm/assert. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const src = fs.readFileSync('apps/studio-web/cinematic.js', 'utf8');

function boot({editorReady = true} = {}) {
  const listeners = {}, calls = [];
  const app = {
    innerHTML: '',
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
        result = {options:[]};
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
  return {app,calls,click,change,poll:async()=>{poll();await pause();await pause();},
    pause,finish:()=>{done=true;}};
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
  await x.change('source-rights',null,true);
  await x.click('connect');
  assert.ok(x.calls.includes('/api/connect-projects'));
  assert.match(x.app.innerHTML,/Start Transfer/);
  await x.click('start');
  await x.poll();
  assert.deepEqual(x.calls.filter(v=>v==='/api/execute').length,1);
  assert.ok(x.calls.indexOf('/api/prepare')<x.calls.indexOf('/api/approve-one-click'));
  assert.ok(x.calls.indexOf('/api/approve-one-click')<x.calls.indexOf('/api/execute'));
  x.finish();
  await x.poll();
  assert.match(x.app.innerHTML,/Sequence Generated Successfully/);
  assert.match(x.app.innerHTML,/18/);
  assert.match(x.app.innerHTML,/12/);
  assert.match(x.app.innerHTML,/not certified/);
  assert.ok(!x.app.innerHTML.includes('72%'));
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

(async()=>{
  await testOneClick();
  await testOfflineDoesNotExecute();
  console.log('Cinematic UI backend contract: 2 integration paths passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
