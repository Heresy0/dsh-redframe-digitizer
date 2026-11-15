"""Real MCP single/batch equivalence; optional actual GetData desktop export."""
from pathlib import Path
from xml.etree import ElementTree as E
import argparse,asyncio,json,math,os,sys,uuid,zipfile
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from self_test import pdf_fixture,unpack
from pypdf import PdfReader,PdfWriter
from openpyxl import Workbook
BASE=Path(__file__).resolve().parent

def workbook_rows(path):
    # Independent readback of Excel XML, rather than comparing the writer's input.
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(si.itertext()) for si in E.fromstring(z.read('xl/sharedStrings.xml'))]
        sheet=E.fromstring(z.read('xl/worksheets/sheet2.xml'));rows=[]
        for row in sheet.findall('s:sheetData/s:row',ns):
            if int(row.get('r'))==1:continue
            values=[]
            for cell in row.findall('s:c',ns):
                text=cell.find('s:v',ns);kind=cell.get('t')
                if kind=='inlineStr':value=''.join(cell.find('s:is',ns).itertext())
                elif kind=='s':value=shared[int(text.text)]
                else:value=float(text.text)
                values.append(value)
            rows.append(values)
        return rows

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--getdata-exe',type=Path);args=parser.parse_args()
    env={k:v for k,v in os.environ.items() if not k.startswith(('CODEX','REDFRAME_NODE','REDFRAME_ARTIFACT'))}
    env['REDFRAME_GETDATA_EXE']=str(args.getdata_exe.resolve(strict=True)) if args.getdata_exe else ''
    folder=BASE/'selftest'/('batch_'+uuid.uuid4().hex);folder.mkdir(parents=True)
    pdf_fixture(folder/'one.pdf');writer=PdfWriter();page=PdfReader(folder/'one.pdf').pages[0]
    writer.add_page(page);writer.add_page(page)
    with (folder/'two.pdf').open('wb') as stream:writer.write(stream)
    wb=Workbook();wb.active.title='Template';wb.active.append(['文章标题','图片字母','X','Y','线段表示含义']);wb.active['A2']='Preserve original';wb.save(folder/'template.xlsx');wb.close()
    results={}
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(BASE/'server.py')],env=env)) as (r,w):
      async with ClientSession(r,w) as session:
        init=await session.initialize();tools=await session.list_tools();assert len(tools.tools)==11
        assert 'submit_and_refine' in (init.instructions or '')
        for mode in ('single','batch'):
            mutations=[];reviews=[];semantic=[]
            async def invoke(name,arguments,mutation=False):
                if mutation:mutations.append(name)
                return await session.call_tool(name,arguments)
            job=unpack(await invoke('prepare_job',{'pdf_paths':[str(folder/'two.pdf')],'template_path':str(folder/'template.xlsx')}));jid=job['job_id']
            for page_number in (1,2):
                panel=unpack(await invoke('crop_panel',dict(job_id=jid,paper_id=1,page=page_number,box_points=[0,0,300,300],panel_label=f'Panel {page_number}')))
                common=dict(job_id=jid,panel_id=panel['id'],title='Batch Equivalence Graph',metric='Mass remaining (%)',x_unit='day',y_unit='%',calibration={'x':[[200,0],[1000,10]],'y':[[1000,0],[200,100]]},series=[{'label':'Control 中文','points':[[200,200],[603,602],[1003,802]]},{'label':'Treatment','points':[[200,1000],[600,800],[1000,200]]}])
                specs=[dict(label='Control 中文',shape='square',fill='filled',radius=8,stroke_width=2,search_radius=8),dict(label='Treatment',shape='manual')]
                if mode=='single':
                    unpack(await invoke('submit_digitization',common,True))
                    refined=unpack(await invoke('refine_panel_points',dict(job_id=jid,panel_id=panel['id'],marker_specs=specs),True))
                else:refined=unpack(await invoke('submit_and_refine',{**common,'marker_specs':specs},True))
                assert refined['refined']==2
                for path in [refined['overlay'],*refined['patches']]:
                    image=await invoke('view_job_image',dict(job_id=jid,relative_path=path));assert image.content[0].type=='image'
                semantic.append([{k:p[k] for k in ('label','point_index','coarse','candidate','selected','status','score','reason')} for p in refined['points']])
                reviews.append(dict(panel_id=panel['id'],expected_revision=refined['revision'],review_notes='Synthetic fixed geometry and programmatic image-result regression, not a model visual accuracy claim',point_reviews=[dict(label=p['label'],point_index=p['point_index'],decision='keep_coarse',notes='Known synthetic coordinate retained; deliberate manual fixture series or zero-boundary point') for p in refined['points'] if p['status']=='needs_review']))
            coverage='Two synthetic PDF pages, one fixed-geometry red frame and one panel on each page; 12 points total'
            if mode=='single':
                for review in reviews:unpack(await invoke('review_panel',dict(job_id=jid,accepted=True,**review),True))
                exported=await invoke('export_workbook',dict(job_id=jid,coverage_notes=coverage),True)
            else:exported=await invoke('review_and_export',dict(job_id=jid,reviews=reviews,coverage_notes=coverage),True)
            status=unpack(await invoke('job_status',dict(job_id=jid)))
            assert all(p['status']=='accepted' for p in status['panels'])
            result=dict(job_id=jid,mutation_calls=len(mutations),calls=mutations,semantic=semantic)
            if args.getdata_exe:
                final=unpack(exported);proofs=final['validation']['getdata_exports']
                assert final['validation']['points']==12 and final['validation']['getdata_executed']
                assert len(proofs)==2 and all(p['verified'] for p in proofs)
                result.update(workbook=final['workbook'],rows=workbook_rows(final['workbook']))
                if mode=='batch':assert status['last_batch']['phase']=='exported'
            else:
                assert exported.isError and 'GetData is not configured' in str(exported.content)
                if mode=='batch':assert status['last_batch']['phase']=='export_failed'
            results[mode]=result
    assert results['single']['semantic']==results['batch']['semantic']
    assert results['single']['mutation_calls']==7 and results['batch']['mutation_calls']==3
    if args.getdata_exe:
        a,b=results['single']['rows'],results['batch']['rows'];assert len(a)==len(b)==12
        for x,y in zip(a,b):
            assert x[:2]==y[:2] and x[4]==y[4]
            assert all(math.isclose(x[i],y[i],rel_tol=1e-13,abs_tol=1e-12) for i in (2,3))
    report=dict(ok=True,tools=11,desktop_export_tested=bool(args.getdata_exe),points_per_path=12,single_mutation_calls=7,batch_mutation_calls=3,measurement='MCP state-changing calls for two panels, excluding identical preparation/image viewing/status; not measured LLM turns/tokens',results=results)
    (BASE/'batch_selftest_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))

if __name__=='__main__':asyncio.run(main())
