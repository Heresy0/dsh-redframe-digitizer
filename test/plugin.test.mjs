import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {apply} from '../index.js';

test('plugin registers real absolute paths, only required env, and long export timeout',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe plugin '));
 fs.writeFileSync(path.join(dir,'server.py'),'# fixture');
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({schemaVersion:3,engine:'openpyxl',digitizer:'getdata',getdata:{executable:process.execPath},python:process.execPath,env:{DO_NOT_FORWARD:'secret'}}));
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
 Object.assign(runtime,{schemaVersion:3,digitizer:'getdata',getdata:{executable:path.join(dir,'missing.exe')}});
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify(runtime));
 assert.throws(()=>apply(ctx,{installDir:dir}),/GetData executable is missing/);
});
