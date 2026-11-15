"""Install on top of the Python reported by Harness load_workspace_dependencies."""
from pathlib import Path
import argparse,importlib,json,os,subprocess,sys,venv
BASE=Path(__file__).resolve().parent

def run(args):subprocess.run([str(v) for v in args],check=True,stdin=subprocess.DEVNULL)

def configure():
    parser=argparse.ArgumentParser()
    parser.add_argument('--harness-python',type=Path,help='Python returned by Harness load_workspace_dependencies')
    parser.add_argument('--env-dir',type=Path,default=BASE/'.venv')
    parser.add_argument('--wheelhouse',type=Path)
    parser.add_argument('--skip-deps',action='store_true',help='For environments with all required dependencies already installed')
    args=parser.parse_args()
    if args.harness_python and args.harness_python.resolve()!=Path(sys.executable).resolve():
        forwarded=[args.harness_python,Path(__file__).resolve(),'--env-dir',args.env_dir]
        if args.wheelhouse:forwarded+=['--wheelhouse',args.wheelhouse]
        if args.skip_deps:forwarded+=['--skip-deps']
        run(forwarded);return
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11+ required; use the Python returned by Harness load_workspace_dependencies.')
    try:office=importlib.import_module('openpyxl')
    except ImportError:raise RuntimeError('This interpreter has no openpyxl. In Harness call load_workspace_dependencies and run setup.py with its Python, or pass --harness-python PATH.')
    print('Using openpyxl '+office.__version__+' from the selected base Python',flush=True)
    directory=args.env_dir.resolve()
    # Inherit the Harness-managed Office libraries instead of copying or modifying its runtime.
    venv.EnvBuilder(system_site_packages=True,with_pip=False).create(directory)
    python=directory/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not args.skip_deps:
        cmd=[sys.executable,'-m','pip','--python',python,'install','-r',BASE/'requirements.txt','--disable-pip-version-check','--quiet']
        wheels=args.wheelhouse or (BASE/'wheelhouse' if (BASE/'wheelhouse').is_dir() else None)
        if wheels:cmd+=['--no-index','--find-links',wheels]
        else:print('Installing extra MCP/PDF dependencies from the configured Python package index (network required).',flush=True)
        run(cmd)
    run([python,'-c',"import mcp,pypdf,pypdfium2,numpy,PIL,openpyxl;print('MCP/PDF/Office imports OK')"])
    run([python,BASE/'self_test.py'])
    # Write connection state only after the complete self-test passes.
    runtime={'schemaVersion':2,'engine':'openpyxl','python':str(python),'basePython':sys.executable,'openpyxlVersion':office.__version__}
    old=BASE/'runtime.json'
    if old.exists() and json.loads(old.read_text(encoding='utf-8')).get('engine')!='openpyxl':
        (BASE/'runtime.before-0.2.local.json').write_text(old.read_text(encoding='utf-8'),encoding='utf-8')
    old.write_text(json.dumps(runtime,ensure_ascii=False,indent=2),encoding='utf-8')
    server={'command':str(python),'args':[str(BASE/'server.py')]}
    (BASE/'mcp-client.json').write_text(json.dumps({'mcpServers':{'redframe_digitizer':server}},ensure_ascii=False,indent=2),encoding='utf-8')
    entry={'id':'mcp-redframe','name':'@deepseek-ai/dsh-mcp-client','config':{'serverName':'redframe_digitizer','transport':'stdio',**server,'toolCallTimeoutMs':300000,'startupTimeoutMs':30000}}
    (BASE/'harness-client.entry.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf-8')
    # YAML accepts JSON-quoted scalar strings, including Windows paths.
    (BASE/'harness-plugin.patch.yml').write_text('- id: redframe-digitizer\n  config:\n    installDir: '+json.dumps(str(BASE))+'\n',encoding='utf-8')
    print('INSTALLATION AND SELF-TEST PASSED. Configure Harness with harness-client.entry.json, or use harness-plugin.patch.yml for the plugin. No separate spreadsheet runtime or Node exporter is required.')

if __name__=='__main__':
    try:configure()
    except Exception as exc:print('SETUP FAILED: '+str(exc),file=sys.stderr);sys.exit(1)
