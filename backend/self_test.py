"""Synthetic PDF -> MCP -> Excel; no private input files."""
from pathlib import Path
import asyncio,json,os,sys,subprocess,zipfile,math
from xml.etree import ElementTree as E
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
BASE=Path(__file__).resolve().parent

def pdf_fixture(path):
 stream=b'1 0 0 RG 20 20 260 260 re S 0 0 0 RG 50 50 m 250 50 l 50 50 m 50 250 l S 48 248 4 4 re f 148 148 4 4 re f 248 98 4 4 re f'
 objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
 result=b'%PDF-1.4\n';offsets=[0]
 for i,obj in enumerate(objects,1):offsets.append(len(result));result+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
 start=len(result);result+=b'xref\n0 5\n0000000000 65535 f \n'
 result+=b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets[1:])
 result+=b'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n';path.write_bytes(result)

def unpack(result):
 if result.isError:raise RuntimeError(str(result.content))
 return result.structuredContent or json.loads(result.content[0].text)

async def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--getdata-exe',type=Path);args=parser.parse_args()
 env={k:v for k,v in os.environ.items() if not k.startswith(('CODEX','REDFRAME_NODE','REDFRAME_ARTIFACT'))}
 env['REDFRAME_GETDATA_EXE']=str(args.getdata_exe.resolve(strict=True)) if args.getdata_exe else ''
 folder=BASE/'selftest';folder.mkdir(exist_ok=True);pdf_fixture(folder/'synthetic.pdf')
 from openpyxl import Workbook
 from openpyxl.styles import PatternFill
 wb=Workbook();sh=wb.active;sh.title='Template';sh.append(['文章标题','图片字母','X','Y','线段表示含义']);sh['A1'].fill=PatternFill('solid',fgColor='F2C000');sh['A2']='Keep original';wb.save(folder/'template.xlsx')
 params=StdioServerParameters(command=sys.executable,args=[str(BASE/'server.py')],env=env)
 async with stdio_client(params) as (r,w):
  async with ClientSession(r,w) as session:
   init=await session.initialize();assert 'refine_panel_points' in (init.instructions or ''),'Refinement workflow must be embedded in server instructions';listing=await session.list_tools();assert len(listing.tools)==11
   job=unpack(await session.call_tool('prepare_job',{'pdf_paths':[str(folder/'synthetic.pdf')],'template_path':str(folder/'template.xlsx')}));jid=job['job_id']
   assert job['papers'][0]['candidates'],'Synthetic red frame was not detected'
   refused=await session.call_tool('export_workbook',{'job_id':jid,'coverage_notes':'Must reject incomplete data'});assert refused.isError
   panel=unpack(await session.call_tool('crop_panel',{'job_id':jid,'paper_id':1,'page':1,'box_points':[0,0,300,300],'panel_label':'Synthetic panel'}))
   points=[[200,200],[603,602],[1003,802]]  # Exact origin plus controlled coarse offsets.
   d=unpack(await session.call_tool('submit_digitization',{'job_id':jid,'panel_id':panel['id'],'title':'Portable Graph Test','metric':'Mass remaining (%)','x_unit':'days','y_unit':'%','calibration':{'x':[[200,0],[1000,10]],'y':[[1000,0],[200,100]]},'series':[{'label':'Control 中文; α','points':points},{'label':'Treatment; β','points':[[200,1000],[600,800],[1000,200]]}]}))
   assert d['points']==6
   refined=unpack(await session.call_tool('refine_panel_points',{'job_id':jid,'panel_id':panel['id'],'marker_specs':[{'label':'Control 中文; α','shape':'square','fill':'filled','radius':8,'stroke_width':2,'search_radius':8},{'label':'Treatment; β','shape':'manual'}]}))
   assert refined['refined']==2,refined
   for row,true in zip(refined['points'][:3],[[200,200],[600,600],[1000,800]]):assert math.dist(row['selected'],true)<1
   blocked=await session.call_tool('review_panel',{'job_id':jid,'panel_id':panel['id'],'accepted':True,'review_notes':'Must reject missing per-point decisions'});assert blocked.isError
   for path in [refined['overlay'],*refined['patches']]:
    shown=await session.call_tool('view_job_image',{'job_id':jid,'relative_path':path});assert shown.content[0].type=='image'
   view=await session.call_tool('view_job_image',{'job_id':jid,'relative_path':d['overlay']});assert view.content[0].type=='image'
   unpack(await session.call_tool('review_panel',{'job_id':jid,'panel_id':panel['id'],'accepted':True,'review_notes':'Synthetic programmatic regression: three recovered image marker centers and three manually specified treatment coordinates; not a model visual-accuracy test.','point_reviews':[{'label':r['label'],'point_index':r['point_index'],'decision':'keep_coarse','notes':'Synthetic manual coordinates independently specified by the test fixture'} for r in refined['points'] if r['status']=='needs_review']}))
   final_result=await session.call_tool('export_workbook',{'job_id':jid,'coverage_notes':'Single synthetic PDF, one panel, six independently specified synthetic coordinates; this is a programmatic export regression.'})
   if not args.getdata_exe:
    assert final_result.isError and 'GetData is not configured' in str(final_result.content),'No-desktop CI must refuse export without fallback'
    report={'ok':True,'tools':11,'refined_points':2,'desktop_export_tested':False,'missing_getdata_refused':True,'synthetic_input_only':True}
    (BASE/'selftest_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('MCP PORTABLE CHECK PASSED: 11 tools, coarse -> refinement -> per-point review verified; missing GetData refused. Desktop export NOT tested.');return
   final=unpack(final_result)
   assert final['validation']['points']==6 and final['validation']['engine']=='openpyxl'
   assert final['validation']['digitizer']=='getdata' and final['validation']['getdata_executed'] is True
   proof=final['validation']['getdata_exports'][0];assert proof['verified'] and proof['curves']==2 and proof['points']==6
   from getdata_adapter import parse_export,sha256
   assert sha256(proof['txt'])==proof['txt_sha256']
   raw=parse_export(proof['txt'],['RF0001','RF0002'])
   for actual,expected in zip(raw['RF0001'],[[0,100],[5,50],[10,25]]):assert all(abs(a-b)<.1 for a,b in zip(actual,expected)),(actual,expected)
   assert raw['RF0002']==[[0,0],[5,25],[10,100]]
   assert proof['point_refinement']['refined']==2
   ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
   with zipfile.ZipFile(final['workbook']) as z:
    sheet=E.fromstring(z.read('xl/worksheets/sheet2.xml'));values={c.get('r'):float(c.find('s:v',ns).text) for c in sheet.findall('.//s:c',ns) if c.get('t') not in ('s','str','inlineStr','e','b') and c.find('s:v',ns) is not None}
    for i,(x,y) in enumerate(raw['RF0001']+raw['RF0002'],2):assert math.isclose(values[f'C{i}'],x) and math.isclose(values[f'D{i}'],y)
    zero=sheet.find('.//s:c[@r="C2"]',ns);styles=E.fromstring(z.read('xl/styles.xml'));fmt=list(styles.find('s:cellXfs',ns))[int(zero.get('s','0'))].get('numFmtId')
    custom={c.get('numFmtId'):c.get('formatCode') for c in styles.findall('s:numFmts/s:numFmt',ns)}
    assert fmt=='1' or custom.get(fmt)=='0','Zero must use integer format'
   report={'ok':True,'tools':11,'points':6,'refined_points':2,'desktop_export_tested':True,'synthetic_input_only':True,'workbook':final['workbook'],'getdata_evidence':proof}
   (BASE/'selftest_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('MCP GETDATA SELF-TEST PASSED: coarse -> refinement -> review -> actual GetData -> TXT -> Excel, 11 tools, 2 curves/6 points, Excel XML and zero format checked.')

if __name__=='__main__':asyncio.run(main())
