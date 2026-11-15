import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {apply} from '../index.js';

test('plugin registers real absolute paths, only required env, and long export timeout',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redframe plugin '));
 fs.writeFileSync(path.join(dir,'server.py'),'# fixture');
 fs.writeFileSync(path.join(dir,'runtime.json'),JSON.stringify({python:process.execPath,env:{REDFRAME_NODE:process.execPath,REDFRAME_NODE_MODULES:'modules',REDFRAME_ARTIFACT_MARKER:'marker',DO_NOT_FORWARD:'secret'}}));
 let actual;apply({mcpManager:{register:(...args)=>{actual=args}}},{installDir:dir});
 assert.equal(actual[0],'redframe_digitizer');assert.equal(actual[1].command,process.execPath);
 assert.deepEqual(actual[1].args,[path.join(dir,'server.py')]);assert.equal(actual[1].toolCallTimeoutMs,300000);
 assert.equal(actual[1].env.DO_NOT_FORWARD,undefined);
});
test('missing backend and unsupported host fail before registering',()=>{
 assert.throws(()=>apply({}),/mcpManager/);
 assert.throws(()=>apply({mcpManager:{register:()=>assert.fail()}},{installDir:path.join(os.tmpdir(),'redframe-missing-'+Date.now())}),/not installed/);
});
