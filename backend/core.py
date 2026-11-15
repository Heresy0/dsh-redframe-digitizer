"""Local, agent-assisted scientific graph digitization. No network or model keys."""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, subprocess, uuid, zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
import numpy as np
from PIL import Image, ImageDraw
import pypdfium2 as pdfium
from pypdf import PdfReader

BASE=Path(__file__).resolve().parent
JOB_ROOT=Path(os.environ.get('REDFRAME_JOB_ROOT',BASE/'jobs')).resolve()
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def save(path,value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)

def load_job(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}',job_id): raise ValueError('Invalid job ID')
    root=(JOB_ROOT/job_id).resolve()
    return root,json.loads((root/'job.json').read_text(encoding='utf-8'))

def asset(root,relative_path):
    path=(root/relative_path).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Path must stay inside this job')
    return path

def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def panel_revision(root,panel):
    """Bind review to semantic inputs, selected points, source pixels and revision ID."""
    keys=('id','paper_id','page','label','box_points','image','image_size','title','metric','x_unit','y_unit','calibration','series','revision_id')
    data={k:panel.get(k) for k in keys}
    refinement=deepcopy(panel.get('refinement'))
    if refinement:
        for point in refinement['points']:point.pop('manual_review',None)
    data['refinement']=refinement
    data['image_sha256']=file_hash(asset(root,panel['image']))
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def inspect_template(path):
    with zipfile.ZipFile(path) as z:
        w=ET.fromstring(z.read('xl/workbook.xml'))
        return {'sheets':[s.get('name') for s in w.find('s:sheets',NS)],
                'policy':'Preserve existing worksheets; add one worksheet per PDF. New columns follow the supplied example.'}

def red_candidates(image):
    """Raster rectangles are candidates only. Never treat red curve segments as confirmed frames."""
    original=image.size; small=image.copy();small.thumbnail((1200,1600))
    a=np.array(small.convert('RGB')).astype(np.int16)
    mask=(a[:,:,0]>140)&(a[:,:,0]-a[:,:,1]>55)&(a[:,:,0]-a[:,:,2]>45)
    seen=np.zeros(mask.shape,bool); h,w=mask.shape; boxes=[]
    for y,x in zip(*np.where(mask)):
        if seen[y,x]:continue
        stack=[(int(y),int(x))];seen[y,x]=True;xs=[];ys=[]
        while stack:
            yy,xx=stack.pop();xs.append(xx);ys.append(yy)
            for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
                ny,nx=yy+dy,xx+dx
                if 0<=ny<h and 0<=nx<w and mask[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx]=True;stack.append((ny,nx))
        l,t,rr,b=min(xs),min(ys),max(xs),max(ys)
        if rr-l<55 or b-t<40:continue
        edges=[mask[t:min(t+5,h),l:rr+1].any(axis=0).mean(),mask[max(t,b-4):b+1,l:rr+1].any(axis=0).mean(),
               mask[t:b+1,l:min(l+5,w)].any(axis=1).mean(),mask[t:b+1,max(l,rr-4):rr+1].any(axis=1).mean()]
        if min(edges)<.55:continue
        boxes.append([l*original[0]/w,t*original[1]/h,(rr+1)*original[0]/w,(b+1)*original[1]/h])
    return boxes

def prepare_job(pdf_paths,template_path):
    if not pdf_paths:raise ValueError('At least one PDF required')
    template=Path(template_path).resolve()
    if template.suffix.lower()!='.xlsx':raise ValueError('Template must be .xlsx')
    template_info=inspect_template(template)
    paths=[Path(p).resolve() for p in pdf_paths]
    if len(set(paths))!=len(paths):raise ValueError('Duplicate PDF paths')
    for p in paths:
        if p.suffix.lower()!='.pdf' or not p.is_file():raise ValueError(f'PDF not found: {p}')
    jid=uuid.uuid4().hex;root=JOB_ROOT/jid;root.mkdir(parents=True)
    shutil.copy2(template,root/'template.xlsx')
    job={'id':jid,'template':template_info,'papers':[],'panels':[],'status':'review_required'}
    for i,path in enumerate(paths,1):
        folder=root/f'paper_{i:02}';folder.mkdir()
        # Snapshot inputs so subsequent source edits cannot silently change a run.
        snapshot=folder/'source.pdf';shutil.copy2(path,snapshot)
        reader=PdfReader(snapshot);doc=pdfium.PdfDocument(snapshot)
        paper={'id':i,'source_name':path.name,'sha256':file_hash(snapshot),'title':path.stem.rstrip('.'),'pages':[]}
        for j,page in enumerate(reader.pages):
            rendered=doc[j].render(scale=2,draw_annots=True).to_pil().convert('RGB')
            image_path=folder/f'page_{j+1:03}.png';rendered.save(image_path)
            width,height=doc[j].get_size()
            # Raster detection also sees baked-in red frames and rotated annotation appearances.
            frames=[[b[0]/2,b[1]/2,b[2]/2,b[3]/2] for b in red_candidates(rendered)]
            paper['pages'].append({'number':j+1,'size_points':[width,height],
                'image':str(image_path.relative_to(root)),'redframe_candidates':frames,'text':page.extract_text() or ''})
        doc.close();job['papers'].append(paper)
    save(root/'job.json',job)
    return {'job_id':jid,'template':template_info,'papers':[{'id':p['id'],'suggested_title':p['title'],
        'pages':len(p['pages']),'candidates':[{'page':q['number'],'boxes_points':q['redframe_candidates']} for q in p['pages'] if q['redframe_candidates']]} for p in job['papers']],
        'next':'Read paper pages and view images; verify red frames, true title, axes and legend before cropping. Candidate detection is not proof of complete coverage.'}

def read_paper(job_id,paper_id,page_start=1,page_count=3):
    _,job=load_job(job_id);p=next(p for p in job['papers'] if p['id']==paper_id)
    if page_start<1 or not 1<=page_count<=10:raise ValueError('page_start >=1; page_count 1..10')
    return {**{k:v for k,v in p.items() if k!='pages'},'pages':p['pages'][page_start-1:page_start-1+page_count]}

def crop_panel(job_id,paper_id,page,box_points,panel_label):
    root,job=load_job(job_id);paper=next(p for p in job['papers'] if p['id']==paper_id)
    record=next(q for q in paper['pages'] if q['number']==page)
    l,t,r,b=map(float,box_points);w,h=record['size_points']
    if not all(math.isfinite(v) for v in (l,t,r,b)) or not 0<=l<r<=w or not 0<=t<b<=h:
        raise ValueError('Box must be inside page, in PDF points, top-left origin')
    pid=uuid.uuid4().hex[:12];folder=root/'panels'/pid;folder.mkdir(parents=True)
    doc=pdfium.PdfDocument(root/f'paper_{paper_id:02}'/'source.pdf')
    im=doc[page-1].render(scale=4,draw_annots=True).to_pil().convert('RGB')
    crop=im.crop(tuple(round(v*4) for v in (l,t,r,b)));crop.save(folder/'image.png');doc.close()
    panel={'id':pid,'paper_id':paper_id,'page':page,'label':panel_label,'box_points':[l,t,r,b],
           'image':str((folder/'image.png').relative_to(root)),'image_size':list(crop.size),'status':'needs_digitization'}
    job['panels'].append(panel);save(root/'job.json',job)
    return panel

def convert(pixel,anchors,scale):
    if len(anchors)!=2:raise ValueError('Each axis requires exactly two [pixel,value] anchors')
    (p0,v0),(p1,v1)=[[float(v) for v in a] for a in anchors]
    if not all(math.isfinite(v) for v in (p0,p1,v0,v1,pixel)) or p0==p1 or v0==v1:raise ValueError('Invalid or degenerate axis')
    if scale not in ('linear','log10'):raise ValueError('Only linear/log10 axes supported')
    if scale=='log10':
        if min(v0,v1)<=0:raise ValueError('Log-axis anchors must be positive')
        v0,v1=math.log10(v0),math.log10(v1)
    value=v0+(pixel-p0)/(p1-p0)*(v1-v0)
    result=10**value if scale=='log10' else value
    if not math.isfinite(result):raise ValueError('Non-finite converted coordinate')
    return result

def submit_digitization(job_id,panel_id,title,metric,x_unit,y_unit,calibration,series):
    root,job=load_job(job_id);p=next(p for p in job['panels'] if p['id']==panel_id)
    result=_submit_panel(root,p,title,metric,x_unit,y_unit,calibration,series)
    save(root/'job.json',job)
    return result

def _submit_panel(root,p,title,metric,x_unit,y_unit,calibration,series):
    if not title.strip() or not metric.strip() or not series:raise ValueError('Title, metric, series required')
    sx=calibration.get('x_scale','linear');sy=calibration.get('y_scale','linear')
    image=Image.open(asset(root,p['image'])).convert('RGB');draw=ImageDraw.Draw(image);colors=['red','blue','green','magenta','orange','cyan']
    records=[];labels=[]
    for i,s in enumerate(series):
        label=s['label'].strip()
        if not label or label in labels or not s['points']:raise ValueError('Unique non-empty series labels and point lists required')
        labels.append(label);points=[]
        for xy in s['points']:
            x,y=map(float,xy)
            if not (math.isfinite(x) and math.isfinite(y) and 0<=x<image.width and 0<=y<image.height):raise ValueError('Marker outside crop')
            xx=convert(x,calibration['x'],sx);yy=convert(y,calibration['y'],sy)
            points.append([xx,yy]);draw.ellipse((x-6,y-6,x+6,y+6),outline=colors[i%len(colors)],width=2)
        if any(b[0]<a[0] for a,b in zip(points,points[1:])):raise ValueError('Points must be ordered by increasing X')
        records.append({'label':label,'pixel_points':s['points'],'points':points})
    image.save(asset(root,str(Path(p['image']).with_name('overlay.png'))))
    p.update(title=title,metric=metric,x_unit=x_unit,y_unit=y_unit,calibration=calibration,series=records,status='awaiting_review')
    p['overlay']=str(Path(p['image']).with_name('overlay.png'))
    if sx==sy=='linear':
        p['getdata_project']=str(Path(p['image']).with_suffix('.gdw'))
        write_gdw(asset(root,p['getdata_project']),asset(root,p['image']),p)
    else:p.pop('getdata_project',None)
    # A resubmission always invalidates any prior acceptance.
    p.pop('refinement',None)
    p.pop('review',None);p.pop('accepted_revision',None);p['revision_id']=uuid.uuid4().hex
    return {'panel_id':p['id'],'revision':panel_revision(root,p),'status':p['status'],'overlay':p['overlay'],'getdata_project':p.get('getdata_project'),
        'curves':len(records),'points':sum(len(s['points']) for s in records),'data':records,
        'next':'View overlay and source legend, then call review_panel. These are calculated preview coordinates. export_workbook will run GetData and use its actual TXT values; only linear-axis export is currently verified.'}

def write_gdw(path,image,panel):
    w,h=panel['image_size'];c=panel['calibration'];(x0,xmin),(x1,xmax)=c['x'];(y0,ymin),(y1,ymax)=c['y']
    if c.get('x_scale','linear')!='linear' or c.get('y_scale','linear')!='linear':raise ValueError('Actual GetData export supports verified linear axes only')
    if round(x0*9)==round(x1*9) or round(y0*9)==round(y1*9):raise ValueError('GetData quantization collapses axis anchors')
    # Current installed GetData rejects PNG; JPEG keeps the identical pixel grid.
    jpeg=path.with_suffix('.jpg');Image.open(image).convert('RGB').save(jpeg,quality=100,subsampling=0)
    image=jpeg
    s=f'<?xml version="1.0" encoding="UTF-8"?><GetDataWorkspace><version>2.20</version><File><Name>{escape(str(image))}</Name><Width>{w}</Width><Height>{h}</Height></File>'
    for index,line in enumerate(panel['series'],1):
        points=','.join(str(round(v*9)) for xy in line['pixel_points'] for v in xy)
        s+=f'<Line><Caption>RF{index:04}</Caption><LineColor>0,0,0</LineColor><BkColor>255,255,255</BkColor><PtColor>220,0,0</PtColor><LineType>0</LineType><Points MF="9">{points}</Points></Line>'
    for tag,x,y,value in [('Xmin',x0,y0,xmin),('Xmax',x1,y0,xmax),('Ymin',x0,y0,ymin),('Ymax',x0,y1,ymax)]:
        s+=f'<{tag} MF="9">{round(x*9)},{round(y*9)},{value}</{tag}>'
    s+='<CurrentLine>0</CurrentLine><XScale>linear</XScale><YScale>linear</YScale><Position>0,0</Position><Zoom><FitToWindow/></Zoom></GetDataWorkspace>'
    path.write_text(s,encoding='utf-8')

def refine_panel_points(job_id,panel_id,marker_specs):
    """Bounded proposals from clean source pixels; unknown/ambiguous markers stay put."""
    root,job=load_job(job_id);p=next(p for p in job['panels'] if p['id']==panel_id)
    result=_refine_panel(root,p,marker_specs)
    save(root/'job.json',job)
    return result

def _refine_panel(root,p,marker_specs):
    from refine_points import refine_series
    if not p.get('series'):raise ValueError('Submit coarse digitization first')
    original=Image.open(asset(root,p['image'])).convert('RGB')
    rows=refine_series(original,p['series'],marker_specs)
    records=deepcopy(p['series']);c=p['calibration']
    for row in rows:
        if row['status']!='refined':continue
        for axis,key in enumerate(('x','y')):
            before=convert(row['coarse'][axis],c[key],c.get(key+'_scale','linear'))
            after=convert(row['selected'][axis],c[key],c.get(key+'_scale','linear'))
            if before*after<0 or (before==0 and abs(after)>1e-12):
                row.update(selected=row['coarse'],status='needs_review',reason='zero_boundary_requires_review');break
    for series in records:
        group=[r for r in rows if r['label']==series['label']]
        series['coarse_pixel_points']=[r['coarse'] for r in group]
        series['pixel_points']=[r['selected'] for r in group]
        series['points']=[[convert(x,c['x'],c.get('x_scale','linear')),convert(y,c['y'],c.get('y_scale','linear'))] for x,y in series['pixel_points']]
    overlay=original.copy();draw=ImageDraw.Draw(overlay)
    def marks(d,x,y,color,kind):
        if kind=='cross':d.line((x-5,y,x+5,y),fill=color,width=1);d.line((x,y-5,x,y+5),fill=color,width=1)
        else:d.ellipse((x-6,y-6,x+6,y+6),outline=color,width=1)
    for row in rows:
        marks(draw,*row['coarse'],'cyan','cross')
        if row['candidate']:marks(draw,*row['candidate'],'orange','circle')
        marks(draw,*row['selected'],'magenta','cross')
    folder=asset(root,p['image']).parent
    overlay.save(folder/'refinement_overlay.png')
    patches=[]
    for start in range(0,len(rows),12):
        batch=rows[start:start+12];sheet=Image.new('RGB',(880,240*math.ceil(len(batch)/4)),'white');d=ImageDraw.Draw(sheet)
        for i,row in enumerate(batch):
            cx,cy=row['coarse'];extent=35
            patch=original.crop((round(cx)-extent,round(cy)-extent,round(cx)+extent+1,round(cy)+extent+1)).resize((184,184),Image.Resampling.NEAREST)
            pd=ImageDraw.Draw(patch);scale=184/(extent*2+1)
            for point,color,kind in [(row['coarse'],'cyan','cross'),(row['candidate'],'orange','circle'),(row['selected'],'magenta','cross')]:
                if point:marks(pd,(point[0]-(round(cx)-extent))*scale,(point[1]-(round(cy)-extent))*scale,color,kind)
            x=i%4*220;y=i//4*240;sheet.paste(patch,(x,y+48))
            sn=next(j for j,s in enumerate(records,1) if s['label']==row['label'])
            d.text((x+2,y+2),f"S{sn} P{row['point_index']} score={row['score']:.3f}\n{row['reason']}\ncyan=coarse magenta=selected",fill='black')
        path=folder/f'refinement_patches_{start//12+1}.png';sheet.save(path);patches.append(str(path.relative_to(root)))
    p.update(series=records,status='awaiting_review',overlay=str((folder/'refinement_overlay.png').relative_to(root)),
             refinement={'algorithm':'local_shape_dice_v1','marker_specs':marker_specs,'points':rows,'patches':patches})
    p.pop('review',None);p.pop('accepted_revision',None);p['revision_id']=uuid.uuid4().hex
    if p.get('getdata_project'):write_gdw(asset(root,p['getdata_project']),asset(root,p['image']),p)
    return {'panel_id':p['id'],'revision':panel_revision(root,p),'status':p['status'],'overlay':p['overlay'],'patches':patches,'refined':sum(r['status']=='refined' for r in rows),
            'unresolved':sum(r['status']=='needs_review' for r in rows),'points':rows,
            'next':'View overlay AND every patch sheet. Cyan is coarse, magenta selected, orange candidate. Scores are heuristic, not probability. Each unresolved point needs an explicit keep_coarse decision and source-based note in review_panel; if wrong, resubmit corrected coordinates. Acceptance is never automatic.'}

def review_panel(job_id,panel_id,accepted,review_notes,point_reviews=None,expected_revision=None):
    root,job=load_job(job_id);panel=next(p for p in job['panels'] if p['id']==panel_id)
    _review_panel(root,panel,accepted,review_notes,point_reviews,expected_revision)
    save(root/'job.json',job)
    return {'panel_id':panel_id,'status':panel['status'],'revision':panel_revision(root,panel)}

def _review_panel(root,panel,accepted,review_notes,point_reviews=None,expected_revision=None):
    if expected_revision is not None and expected_revision!=panel_revision(root,panel):raise ValueError('Stale panel revision; inspect current overlay and patches before reviewing')
    if panel['status']=='needs_digitization' or not review_notes.strip():raise ValueError('Digitization and concrete review notes required')
    if accepted and panel.get('refinement'):
        unresolved={(r['label'],r['point_index']):r for r in panel['refinement']['points'] if r['status']=='needs_review'}
        decisions={}
        for item in point_reviews or []:
            key=(item['label'],item['point_index'])
            if key in decisions or key not in unresolved or item.get('decision')!='keep_coarse' or not item.get('notes','').strip():
                raise ValueError('Each unresolved point needs a unique keep_coarse decision with source-based notes; correct wrong points by resubmitting')
            decisions[key]=item
        if set(decisions)!=set(unresolved):raise ValueError('Resolve every flagged refinement point individually before acceptance')
        for key,row in unresolved.items():row['manual_review']=decisions[key]
    panel['status']='accepted' if accepted else 'needs_correction'
    panel['review']=review_notes
    if accepted:panel['accepted_revision']=panel_revision(root,panel)
    else:panel.pop('accepted_revision',None)

def submit_and_refine(job_id,panel_id,title,metric,x_unit,y_unit,calibration,series,marker_specs):
    """One deterministic stage; commit job state only after submit AND refine succeed."""
    from refine_points import validate_spec
    if not marker_specs:raise ValueError('Marker specs required; use shape=manual for unknown markers')
    labels=[s['label'].strip() for s in series];spec_labels=[s['label'] for s in marker_specs]
    if len(set(spec_labels))!=len(spec_labels) or set(labels)!=set(spec_labels):raise ValueError('Provide exactly one marker spec for every series')
    for spec in marker_specs:validate_spec(spec)
    root,job=load_job(job_id)
    index=next(i for i,p in enumerate(job['panels']) if p['id']==panel_id)
    panel=deepcopy(job['panels'][index])
    stage=root/'panels'/panel_id/'revisions'/uuid.uuid4().hex;stage.mkdir(parents=True)
    shutil.copy2(asset(root,panel['image']),stage/'image.png')
    panel['image']=str((stage/'image.png').relative_to(root));panel.pop('getdata_project',None)
    try:
        _submit_panel(root,panel,title,metric,x_unit,y_unit,calibration,series)
        result=_refine_panel(root,panel,marker_specs)
        job['panels'][index]=panel
        save(root/'job.json',job)
    except Exception as exc:
        save(stage/'error.json',{'error':str(exc),'state_committed':False})
        raise RuntimeError('submit_and_refine failed; previous panel state preserved. Diagnostics: '+str(stage/'error.json')+'; '+str(exc)) from exc
    return {**result,'stage':'awaiting_visual_review','job_id':job_id,
            'next':'Inspect this revision overlay and EVERY patch sheet. Then submit actual per-point decisions via review_and_export with expected_revision. This stage never accepts panels or exports.'}

def review_and_export(job_id,reviews,coverage_notes):
    """Preflight ALL supplied decisions on a copy; persist valid reviews, then export."""
    if not reviews:raise ValueError('At least one explicit panel review required; use export_workbook to retry already accepted data')
    root,job=load_job(job_id);trial=deepcopy(job);seen=set();revisions={}
    for review in reviews:
        pid=review['panel_id'];expected=review.get('expected_revision')
        if pid in seen:raise ValueError('Duplicate panel review')
        if not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected):raise ValueError('expected_revision from current refinement result is required')
        seen.add(pid)
        panel=next((p for p in trial['panels'] if p['id']==pid),None)
        if panel is None:raise ValueError('Unknown panel ID')
        _review_panel(root,panel,True,review['review_notes'],review.get('point_reviews'),expected)
        revisions[pid]=expected
    # Check coverage, every pending panel, unresolved points, titles and axes BEFORE writes.
    _validate_export(root,trial,coverage_notes)
    trial['last_batch']={'phase':'reviewed','panel_revisions':revisions,'reviewed_panels':len(reviews)}
    save(root/'job.json',trial)
    try:
        result=export_workbook(job_id,coverage_notes)
    except Exception as exc:
        _,latest=load_job(job_id)
        latest['last_batch'].update(phase='export_failed',error=str(exc),resume='Resolve the export error, then call export_workbook with the same job_id and coverage_notes; valid reviews remain saved')
        save(root/'job.json',latest)
        raise RuntimeError('Reviews saved; export failed. Inspect job_status.last_batch and GetData evidence; retry export_workbook without repeating valid reviews. '+str(exc)) from exc
    _,latest=load_job(job_id);latest['last_batch'].update(phase='exported',workbook=result['workbook']);save(root/'job.json',latest)
    return {**result,'stage':'exported','reviewed_panels':len(reviews)}

def job_status(job_id):
    root,job=load_job(job_id)
    return {'job_id':job_id,'papers':len(job['papers']),'panels':[{**{k:p[k] for k in ['id','paper_id','label','status']},'revision':panel_revision(root,p),'unresolved_refinement':sum(r['status']=='needs_review' and not r.get('manual_review') for r in p.get('refinement',{}).get('points',[]))} for p in job['panels']],
            'points':sum(len(s['points']) for p in job['panels'] for s in p.get('series',[])),'exports':job.get('exports',[]),
            'digitizer':'getdata','last_getdata_attempt':job.get('last_getdata_attempt'),'last_batch':job.get('last_batch'),'getdata_exports':job.get('getdata_exports',[])}

def export_workbook(job_id,coverage_notes):
    root,job=load_job(job_id)
    _validate_export(root,job,coverage_notes)
    return _export_workbook(root,job,coverage_notes)

def _validate_export(root,job,coverage_notes):
    if not coverage_notes.strip():raise ValueError('Explain how all red frames/pages were checked')
    if not job['panels'] or any(p['status']!='accepted' for p in job['panels']):raise ValueError('All panels must pass visual review before export')
    if any(r['status']=='needs_review' and not r.get('manual_review') for p in job['panels'] for r in p.get('refinement',{}).get('points',[])):
        raise ValueError('Unresolved refinement points block export')
    for paper in job['papers']:
        panels=[p for p in job['panels'] if p['paper_id']==paper['id']]
        if not panels:raise ValueError(f'Paper {paper["id"]} has no accepted panels; incomplete export blocked')
        if len(set(p['title'] for p in panels))!=1:raise ValueError('Inconsistent article titles across panels')
    for panel in job['panels']:
        if panel.get('accepted_revision') and panel['accepted_revision']!=panel_revision(root,panel):raise ValueError('Accepted panel changed; review the current revision again')
        if any(panel['calibration'].get(k,'linear')!='linear' for k in ('x_scale','y_scale')):
            raise ValueError('GetData adapter currently verifies linear axes only; log-axis export is blocked, without fallback')

def _export_workbook(root,job,coverage_notes):
    # No fallback: every accepted panel must pass a real GetData desktop export.
    from getdata_adapter import executable_from_config,export_panel
    executable=executable_from_config(BASE)
    run=root/'getdata_exports'/uuid.uuid4().hex;run.mkdir(parents=True)
    job['last_getdata_attempt']=str(run.relative_to(root));save(root/'job.json',job)
    exported_panels=[];evidence=[]
    for original in job['panels']:
        panel=deepcopy(original)
        # Rebuild from the reviewed pixels, including older PNG-backed jobs.
        project=run/f"{panel['id']}.gdw"
        write_gdw(project,asset(root,panel['image']),panel)
        records,proof=export_panel(panel,project,project.with_suffix('.txt'),executable)
        panel['series']=records;panel['getdata_export']=proof
        exported_panels.append(panel);evidence.append({'panel_id':panel['id'],**proof})
    output=root/'result.xlsx';preview=root/'previews';preview.mkdir(exist_ok=True)
    payload={'template':str(root/'template.xlsx'),'output':str(output),'preview_dir':str(preview),'papers':[]}
    for paper in job['papers']:
        panels=[p for p in exported_panels if p['paper_id']==paper['id']]
        payload['papers'].append({'id':paper['id'],'title':panels[0]['title'],'source':paper['source_name'],'panels':panels})
    payload_file=root/'export.json';save(payload_file,payload)
    from export_xlsx import export
    report=export(payload)
    report.update(digitizer='getdata',getdata_executed=True,getdata_exports=evidence)
    save(root/'validation.json',report)
    job['exports'].append(str(output)) if 'exports' in job else job.update(exports=[str(output)])
    job['getdata_exports']=evidence
    job['coverage_notes']=coverage_notes;job['status']='exported';save(root/'job.json',job)
    return {'workbook':str(output),'validation':report,'preview_dir':str(preview),
        'next':'Data previews are not native workbook rendering. Use Harness office_render for workbook visual QA; if requires_recalculation is true, use office_recalculate first. Compare red-frame coverage. Structural checks are not scientific ground truth.'}
