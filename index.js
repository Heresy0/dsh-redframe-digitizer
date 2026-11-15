import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {registerWorkflowSkill} from './skill.js';

export const name='redframe-digitizer';
export const inject=['mcpManager'];

/** Register a plugin-owned MCP server; the host owns connection and disposal. */
export function apply(ctx,config={}){
 if(typeof ctx.mcpManager?.register!=='function')throw Error('This Harness version has no mcpManager.register; use the documented manual MCP client configuration instead.');
 const installDir=path.resolve(config.installDir||process.env.REDFRAME_INSTALL_DIR||path.join(path.dirname(fileURLToPath(import.meta.url)),'backend'));
 const runtimePath=path.join(installDir,'runtime.json');
 if(!fs.existsSync(runtimePath))throw Error('Redframe backend is not installed: run backend/install.cmd first, then set this plugin config.installDir to that installed backend folder.');
 const runtime=JSON.parse(fs.readFileSync(runtimePath,'utf8'));
 if(runtime.schemaVersion!==3||runtime.engine!=='openpyxl'||runtime.digitizer!=='getdata')throw Error('Backend needs the 0.3 installer migration; rerun setup.py with Harness Python and --getdata-exe PATH.');
 if(runtime.toolsetVersion!==5)throw Error('Backend needs the 0.5 installer migration for batch tools; update backend source and rerun setup.py --getdata-exe PATH.');
 if(typeof runtime.getdata?.executable!=='string'||!fs.existsSync(runtime.getdata.executable))throw Error('Configured GetData executable is missing; rerun setup.py --getdata-exe PATH.');
 const command=runtime.python,script=path.join(installDir,'server.py');
 if(typeof command!=='string'||!fs.existsSync(command)||!fs.existsSync(script))throw Error('Backend paths are invalid; reinstall after moving its folder.');
 const serverName=config.serverName||'redframe_digitizer';
 if(!/^[A-Za-z0-9_-]{1,32}$/.test(serverName))throw Error('Invalid MCP server name');
 ctx.mcpManager.register(serverName,{transport:'stdio',command,args:[script],cwd:installDir,startupTimeoutMs:30000,toolCallTimeoutMs:300000});
 registerWorkflowSkill(ctx);
}
