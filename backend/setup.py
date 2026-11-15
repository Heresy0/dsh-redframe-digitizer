"""Configure this extracted copy. Never edits client global settings."""
from pathlib import Path
import argparse,os,platform,subprocess,sys,json,shutil
BASE=Path(__file__).resolve().parent

def run(args,**kwargs):
 subprocess.run([str(x) for x in args],check=True,stdin=subprocess.DEVNULL,**kwargs)

def configure():
 parser=argparse.ArgumentParser()
 parser.add_argument('--node');parser.add_argument('--node-modules');parser.add_argument('--marker')
 args=parser.parse_args()
 if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or platform.machine().upper() not in ('AMD64','X86_64'):
  raise RuntimeError('This package requires Windows x64 and Python 3.12. Use matching Codex runtime or install Python 3.12 x64.')
 home=Path.home();deps=home/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
 node=Path(args.node or deps/'node/bin/node.exe')
 if not node.is_file() and shutil.which('node'):node=Path(shutil.which('node'))
 modules=Path(args.node_modules or deps/'node/node_modules')
 markers=list((home/'.codex/plugins/cache/openai-primary-runtime/spreadsheets').glob('*/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs'))
 markers.sort(key=lambda p:p.stat().st_mtime,reverse=True)
 marker=Path(args.marker) if args.marker else (markers[0] if markers else None)
 if not node.is_file() or not (modules/'@oai/artifact-tool').is_dir() or marker is None or not marker.is_file():
  raise RuntimeError('Codex spreadsheet runtime not found. Open this folder in Codex and ask the assistant to locate bundled Python/Node/node_modules and artifact marker; run setup.py --node PATH --node-modules PATH --marker PATH. GetData alone is insufficient. No client configuration was installed.')
 env=dict(os.environ);env.update(REDFRAME_NODE=str(node),REDFRAME_NODE_MODULES=str(modules),REDFRAME_ARTIFACT_MARKER=str(marker))
 # Verify the actual module rather than treating a directory as proof of compatibility.
 run([node,'-e',"const{createRequire}=require('module');const p=require('path');const r=createRequire(p.join(process.env.REDFRAME_NODE_MODULES,'package.json'));import(require('url').pathToFileURL(r.resolve('@oai/artifact-tool')).href).then(()=>console.log('Spreadsheet runtime OK'))"],env=env)
 venv=BASE/'.venv';python=venv/'Scripts/python.exe'
 if not python.is_file():run([sys.executable,'-m','venv','--without-pip',venv])
 install=[sys.executable,'-m','pip','--python',python,'install','-r',BASE/'requirements.txt','--disable-pip-version-check','--quiet']
 if (BASE/'wheelhouse').is_dir():install+=['--no-index','--find-links',BASE/'wheelhouse']
 else:print('Installing Python dependencies from your configured package index (network required).')
 run(install)
 runtime={'python':str(python),'env':{k:env[k] for k in ['REDFRAME_NODE','REDFRAME_NODE_MODULES','REDFRAME_ARTIFACT_MARKER']}}
 (BASE/'runtime.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2),encoding='utf-8')
 run([python,BASE/'self_test.py'],env=env)
 # Publish connection files only after a successful complete self-test.
 server={'command':str(python),'args':[str(BASE/'server.py')],'env':runtime['env']}
 (BASE/'mcp-client.json').write_text(json.dumps({'mcpServers':{'redframe_digitizer':server}},ensure_ascii=False,indent=2),encoding='utf-8')
 toml='[mcp_servers.redframe_digitizer]\ncommand = '+json.dumps(str(python))+'\nargs = '+json.dumps(server['args'])+'\nstartup_timeout_sec = 30\ntool_timeout_sec = 300\n\n[mcp_servers.redframe_digitizer.env]\n'
 toml+=''.join(k+' = '+json.dumps(v)+'\n' for k,v in runtime['env'].items())
 folder=BASE/'.codex';folder.mkdir(exist_ok=True);path=folder/'config.toml'
 if path.exists() and path.read_text(encoding='utf-8')!=toml:shutil.copy2(path,folder/'config.toml.before-setup.bak')
 path.write_text(toml,encoding='utf-8')
 print('\nINSTALLATION AND SELF-TEST PASSED.\nOpen this folder in Codex, or import mcp-client.json using your MCP client.\nMoving this extracted folder later requires running install.cmd again.')

if __name__=='__main__':
 try:configure()
 except Exception as exc:
  print('\nSETUP FAILED: '+str(exc),file=sys.stderr);sys.exit(1)
