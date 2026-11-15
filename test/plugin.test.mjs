import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {apply} from '../index.js';
import {loadWorkflowSkill} from '../skill.js';

test('plugin registers real absolute paths, only required env, and long export timeout',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe plugin '));
 fs.writeFileSync(path.join(dir,'server.py'),'# fixture');
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({schemaVersion:3,toolsetVersion:5,engine:'openpyxl',digitizer:'getdata',getdata:{executable:process.execPath},python:process.execPath,env:{DO_NOT_FORWARD:'secret'}}));
 let actual;apply({mcpManager:{register:(...args)=>{actual=args}}},{installDir:dir});
 assert.equal(actual[0],'redframe_digitizer');assert.equal(actual[1].command,process.execPath);
 assert.deepEqual(actual[1].args,[path.join(dir,'server.py')]);assert.equal(actual[1].toolCallTimeoutMs,300000);
 assert.equal(actual[1].env,undefined);
});
test('missing backend and unsupported host fail before registering',()=>{
 assert.throws(()=>apply({}),/mcpManager/);
 assert.throws(()=>apply({mcpManager:{register:()=>assert.fail()}},{installDir:path.join(os.tmpdir(),'redframe-missing-'+Date.now())}),/not installed/);
});
test('old runtime configuration requires migration instead of loading an old exporter',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe legacy '));
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({python:process.execPath,env:{}}));
 assert.throws(()=>apply({mcpManager:{register:()=>assert.fail()}},{installDir:dir}),/0.3 installer/);
});
test('0.2 backend and missing GetData cannot register as a real GetData exporter',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe getdata '));
 const runtime={schemaVersion:2,engine:'openpyxl',python:process.execPath};
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify(runtime));
 const ctx={mcpManager:{register:()=>assert.fail()}};
 assert.throws(()=>apply(ctx,{installDir:dir}),/0.3 installer/);
 Object.assign(runtime,{schemaVersion:3,toolsetVersion:5,digitizer:'getdata',getdata:{executable:path.join(dir,'missing.exe')}});
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify(runtime));
 assert.throws(()=>apply(ctx,{installDir:dir}),/GetData executable is missing/);
});
test('skill registers through optional Cordis injection and resolves packaged references',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe skills '));
 fs.writeFileSync(path.join(dir,'server.py'),'# fixture');
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({schemaVersion:3,toolsetVersion:5,engine:'openpyxl',digitizer:'getdata',getdata:{executable:process.execPath},python:process.execPath}));
 let registered=false,pending,skill;
 apply({mcpManager:{register:()=>{registered=true}},inject:(deps,callback)=>{assert.deepEqual(deps,['skills']);pending=callback}},{installDir:dir});
 assert.equal(registered,true);assert.equal(skill,undefined); // no skills service yet; MCP remains available
 pending({skills:{register:value=>{skill=value;return ()=>{}}}});
 assert.equal(skill.name,'redframe-digitize');assert.equal(skill.source,'runtime');
 assert.deepEqual(skill.invocation,{modelInvocable:true,userInvocable:true});
 assert.equal(fs.existsSync(skill.path),true);assert.equal(path.isAbsolute(skill.resourceBase.path),true);
 const links=[...skill.content.matchAll(/\]\((references\/[^)]+)\)/g)];assert.ok(links.length>0);
 for(const match of links)assert.equal(fs.existsSync(path.join(skill.resourceBase.path,match[1])),true);
 assert.deepEqual(skill,loadWorkflowSkill());
});
test('old nine-tool backend cannot register as a batch backend',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe old batch '));
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({schemaVersion:3,engine:'openpyxl',digitizer:'getdata'}));
 assert.throws(()=>apply({mcpManager:{register:()=>assert.fail()}},{installDir:dir}),/0.5 installer/);
});
