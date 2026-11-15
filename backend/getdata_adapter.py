"""Actual GetData desktop export; no silent computational fallback."""
import argparse
import json
import subprocess
import time
from pathlib import Path
import os, re, math, hashlib, tempfile
from contextlib import contextmanager

def executable_from_config(base):
    """Explicit environment override or installer-owned runtime.json; no path guesses."""
    value=os.environ.get('REDFRAME_GETDATA_EXE')
    if 'REDFRAME_GETDATA_EXE' not in os.environ:
        config=Path(base)/'runtime.json'
        value=json.loads(config.read_text(encoding='utf-8')).get('getdata',{}).get('executable') if config.is_file() else None
    if not value:raise RuntimeError('GetData is not configured. Rerun setup.py --getdata-exe PATH or set REDFRAME_GETDATA_EXE. No fallback export was performed.')
    path=Path(value).expanduser().resolve()
    if not path.is_file():raise FileNotFoundError('Configured GetData executable is missing: '+str(path))
    if os.name!='nt':raise RuntimeError('Actual GetData export requires an interactive Windows session')
    return path

@contextmanager
def desktop_lock():
    """Serialize this user's adapters across processes/backends; release on crash too."""
    import msvcrt
    path=Path(tempfile.gettempdir())/'redframe-getdata-desktop.lock'
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush()
        deadline=time.monotonic()+30
        while True:
            try:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:
                if time.monotonic()>=deadline:raise RuntimeError('Another GetData export is busy; retry after it finishes')
                time.sleep(.2)
        try:yield
        finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def parse_export(path, expected_tokens):
    """Opaque ASCII curve IDs avoid legacy TXT encoding/label truncation ambiguity."""
    text=Path(path).read_bytes().decode('latin-1')
    numeric=re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$')
    result={};current=None
    for line in text.splitlines():
        stripped=line.strip()
        if not stripped:continue
        if stripped in expected_tokens:
            if stripped in result:raise ValueError('GetData duplicated curve '+stripped)
            current=stripped;result[current]=[];continue
        match=numeric.fullmatch(line)
        if match:
            if current is None:raise ValueError('GetData numeric row before curve caption')
            xy=[float(v) for v in match.groups()]
            if not all(math.isfinite(v) for v in xy):raise ValueError('GetData exported non-finite value')
            result[current].append(xy)
        elif current is not None:raise ValueError('Unexpected GetData export content after curve caption')
    if set(result)!=set(expected_tokens):raise ValueError('GetData curve list differs from expected curves')
    return result

def checked_points(panel, parsed):
    """Validate against independently computed GDW quantization, return actual TXT values."""
    c=panel['calibration']
    if c.get('x_scale','linear')!='linear' or c.get('y_scale','linear')!='linear':
        raise ValueError('GetData adapter currently verifies linear axes only; log export is blocked')
    def q(v):return round(float(v)*9)/9
    def value(pixel,anchors):
        (p0,v0),(p1,v1)=anchors;p0=q(p0);p1=q(p1)
        if p0==p1:raise ValueError('GetData quantization collapses axis anchors')
        return float(v0)+(q(pixel)-p0)/(p1-p0)*(float(v1)-float(v0))
    records=[];max_preview_delta=0.
    for index,series in enumerate(panel['series'],1):
        points=parsed[f'RF{index:04}']
        if len(points)!=len(series['pixel_points']):raise ValueError('GetData point count mismatch')
        for j,((x,y),(px,py)) in enumerate(zip(points,series['pixel_points'])):
            ex,ey=value(px,c['x']),value(py,c['y'])
            if not (math.isclose(x,ex,rel_tol=1e-11,abs_tol=1e-10) and math.isclose(y,ey,rel_tol=1e-11,abs_tol=1e-10)):
                raise ValueError('GetData coordinate mismatch: '+series['label'])
            max_preview_delta=max(max_preview_delta,abs(x-series['points'][j][0]),abs(y-series['points'][j][1]))
        records.append({**series,'points':points})
    return records,max_preview_delta

def export_panel(panel,workspace,output,executable):
    adapter=GetDataAdapter(executable);output=Path(output);workspace=Path(workspace)
    evidence={'engine':'getdata','executable':str(executable),'workspace':str(workspace),'workspace_sha256':sha256(workspace),'verified':False}
    try:
        with desktop_lock():
            try:adapter.export(workspace,output)
            finally:adapter.close()
        if sha256(workspace)!=evidence['workspace_sha256']:raise ValueError('GetData modified its input workspace')
        tokens=[f'RF{i:04}' for i in range(1,len(panel['series'])+1)]
        parsed=parse_export(output,tokens)
        records,delta=checked_points(panel,parsed)
        evidence.update(verified=True,txt=str(output),txt_sha256=sha256(output),points=sum(len(s['points']) for s in records),curves=len(records),max_preview_delta=delta,pixel_quantization='GDW MF=9; 1/9 pixel',curve_map={token:s['label'] for token,s in zip(tokens,records)})
        if panel.get('refinement'):
            rr=panel['refinement']['points']
            evidence['point_refinement']={'algorithm':panel['refinement']['algorithm'],'refined':sum(r['status']=='refined' for r in rr),'manually_confirmed_coarse':sum(bool(r.get('manual_review')) for r in rr),'marker_specs':panel['refinement']['marker_specs'],'points':rr}
        return records,evidence
    except Exception as exc:
        evidence['error']=str(exc)
        if adapter.pid:
            from getdata_win32 import windows
            evidence['failure_windows']=[dict(r,children=windows(parent=r['hwnd'])) for r in windows(adapter.pid) if r['visible']]
            evidence['process_exit_code']=adapter.process.poll()
        raise
    finally:
        evidence['events']=adapter.events
        output.with_suffix('.evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')

def wait_for(fn, label, timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=fn()
        if result:return result
        time.sleep(.1)
    raise TimeoutError(label)

class GetDataAdapter:
    def __init__(self, executable):
        global u, windows, menus, send, set_text, C
        from getdata_win32 import u, windows, menus, send, set_text, C
        self.executable=Path(executable).resolve(strict=True)
        self.events=[]
        self.pid=None

    def log(self, action, **details):
        self.events.append(dict(action=action, **details))

    def start(self):
        self.process=subprocess.Popen([str(self.executable)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
        self.pid=self.process.pid
        def find():
            matches=[r for r in windows(self.pid) if r['visible'] and u.GetMenu(r['hwnd']) and 'GetData' in r['text']]
            return matches[0] if len(matches)==1 else None
        row=wait_for(find,'GetData main window did not appear')
        self.hwnd=row['hwnd']
        self.menu=menus(u.GetMenu(self.hwnd))
        self.log('started', pid=self.pid, hwnd=self.hwnd, title=row['text'])

    def command(self, tokens):
        def flatten(rows):
            for row in rows:
                yield row
                yield from flatten(row['children'])
        rows=[r for r in flatten(self.menu) if any(token.casefold() in r['text'].casefold() for token in tokens)]
        if len(rows)!=1:raise RuntimeError(f'Unsupported/ambiguous menu command: {tokens}')
        row=rows[0]
        if not u.PostMessageW(self.hwnd,0x111,row['command'],0):raise C.WinError()
        self.log('menu_command', text=row['text'], command=row['command'])

    def dialogs(self):
        return [r for r in windows(self.pid) if r['visible'] and r['cls']=='#32770']

    def file_dialog(self, path, txt=False):
        def find():
            ds=self.dialogs()
            return ds[0] if len(ds)==1 else None
        row=wait_for(find,'Expected one file dialog')
        def ready():
            if self.process.poll() is not None:raise RuntimeError(f'GetData exited before file dialog became ready (exit code {self.process.returncode}); no fallback export')
            children=windows(parent=row['hwnd'])
            if row['text'] in ('GetDataW','GetData','GetData 2.20'):
                messages=[c['text'] for c in children if c['cls']=='Static' and c['text']]
                if messages:raise RuntimeError('GetData refused operation: '+'; '.join(messages))
            edits=[c for c in children if c['cls']=='Edit' and c['id'] in (1148,1152) and c['visible']]
            return (children,edits[0]) if len(edits)==1 else None
        children,edit=wait_for(ready,'File name control unavailable')
        if txt:
            combos=[c for c in children if c['cls']=='ComboBox' and c['id']==1136]
            if len(combos)!=1:raise RuntimeError('File type selector unavailable')
            combo=combos[0]['hwnd']; options=[]
            for i in range(send(combo,0x146)):
                b=C.create_unicode_buffer(1024)
                send(combo,0x148,i,C.cast(b,C.c_void_p).value)
                options.append(b.value)
            matches=[i for i,s in enumerate(options) if '*.txt' in s.lower() or s.upper().startswith('TXT -')]
            if len(matches)!=1:raise RuntimeError(f'TXT format not uniquely available: {options}')
            send(combo,0x14e,matches[0],0)
            if send(combo,0x147)!=matches[0]:raise RuntimeError('Could not select TXT')
            self.log('selected_format', format=options[matches[0]])
        set_text(edit['hwnd'],str(path))
        b=C.create_unicode_buffer(32768)
        send(edit['hwnd'],0xd,len(b),C.cast(b,C.c_void_p).value)
        if b.value!=str(path):raise RuntimeError('File name readback mismatch')
        if not u.PostMessageW(row['hwnd'],0x111,1,0):raise C.WinError()
        self.log('file_dialog_confirmed', dialog=row['text'], path=str(path))

    def export(self, workspace, output):
        workspace=Path(workspace).resolve(strict=True);output=Path(output).resolve()
        if output.exists():raise FileExistsError('Refusing to overwrite output')
        if workspace.suffix.lower()!='.gdw' or output.suffix.lower()!='.txt':raise ValueError('Expected GDW input and TXT output')
        output.parent.mkdir(parents=True,exist_ok=True)
        self.start()
        self.command(['打开(&W)工作空间','Open workspace','Open &workspace'])
        self.file_dialog(workspace)
        def loaded():
            rows=windows(self.pid)
            return any(r['hwnd']==self.hwnd and str(workspace).lower() in r['text'].lower() for r in rows) and not self.dialogs()
        wait_for(loaded,'Workspace did not load successfully')
        self.log('workspace_loaded', path=str(workspace))
        self.command(['导出(&E)数据','Export data','Export &data'])
        self.file_dialog(output,txt=True)
        last=None;stable=0
        def written():
            nonlocal last,stable
            if self.process.poll() is not None:raise RuntimeError(f'GetData exited during export (exit code {self.process.returncode}); no fallback export')
            if not output.is_file() or self.dialogs():return False
            size=output.stat().st_size
            stable=stable+1 if size==last else 0;last=size
            return size>0 and stable>=3
        wait_for(written,'Export output did not become stable')
        self.log('export_written', path=str(output), bytes=output.stat().st_size)
        return output

    def close(self):
        # Close only our dedicated process, never a pre-existing user instance.
        if self.pid and hasattr(self,'hwnd') and not self.dialogs():
            u.PostMessageW(self.hwnd,0x10,0,0)
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log('left_open',reason='Close did not finish; no force termination')
            else:self.log('closed',pid=self.pid)
        elif self.pid:
            self.log('left_open',reason='Unexpected modal dialog or incomplete startup; inspect own test instance',pid=self.pid)

