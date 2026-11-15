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
 runtime=json.loads((BASE/'runtime.json').read_text(encoding='utf-8'));env=dict(os.environ);env.update(runtime['env'])
 folder=BASE/'selftest';folder.mkdir(exist_ok=True);pdf_fixture(folder/'synthetic.pdf')
 subprocess.run([env['REDFRAME_NODE'],str(BASE/'export.mjs'),'--test-template',str(folder/'template.xlsx')],check=True,stdin=subprocess.DEVNULL,env=env,timeout=120)
 params=StdioServerParameters(command=sys.executable,args=[str(BASE/'server.py')],env=env)
 async with stdio_client(params) as (r,w):
  async with ClientSession(r,w) as session:
   init=await session.initialize();assert 'prepare_job' in (init.instructions or ''),'Workflow must be embedded in server instructions for Harness';listing=await session.list_tools();assert len(listing.tools)==8
   job=unpack(await session.call_tool('prepare_job',{'pdf_paths':[str(folder/'synthetic.pdf')],'template_path':str(folder/'template.xlsx')}));jid=job['job_id']
   assert job['papers'][0]['candidates'],'Synthetic red frame was not detected'
   refused=await session.call_tool('export_workbook',{'job_id':jid,'coverage_notes':'Must reject incomplete data'});assert refused.isError
   panel=unpack(await session.call_tool('crop_panel',{'job_id':jid,'paper_id':1,'page':1,'box_points':[0,0,300,300],'panel_label':'Synthetic panel'}))
   points=[[200,200],[600,600],[1000,800]]
   d=unpack(await session.call_tool('submit_digitization',{'job_id':jid,'panel_id':panel['id'],'title':'Portable Graph Test','metric':'Mass remaining (%)','x_unit':'days','y_unit':'%','calibration':{'x':[[200,0],[1000,10]],'y':[[1000,0],[200,100]]},'series':[{'label':'Control','points':points}]}))
   assert d['points']==3
   view=await session.call_tool('view_job_image',{'job_id':jid,'relative_path':d['overlay']});assert view.content[0].type=='image'
   unpack(await session.call_tool('review_panel',{'job_id':jid,'panel_id':panel['id'],'accepted':True,'review_notes':'Synthetic fixed geometry: 3 known mean centers; anchors independently specified by fixture. This is a programmatic regression, not an AI recognition accuracy test.'}))
   final=unpack(await session.call_tool('export_workbook',{'job_id':jid,'coverage_notes':'Single synthetic PDF with one red-framed panel, 3 known marker points.'}))
   assert final['validation']['points']==3
   ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
   with zipfile.ZipFile(final['workbook']) as z:
    sheet=E.fromstring(z.read('xl/worksheets/sheet2.xml'));values={c.get('r'):float(c.find('s:v',ns).text) for c in sheet.findall('.//s:c',ns) if c.get('t') not in ('s','str','inlineStr','e','b') and c.find('s:v',ns) is not None}
    for i,(x,y) in enumerate([(0,100),(5,50),(10,25)],2):assert math.isclose(values[f'C{i}'],x) and math.isclose(values[f'D{i}'],y)
    zero=sheet.find('.//s:c[@r="C2"]',ns);styles=E.fromstring(z.read('xl/styles.xml'));fmt=list(styles.find('s:cellXfs',ns))[int(zero.get('s','0'))].get('numFmtId')
    custom={c.get('numFmtId'):c.get('formatCode') for c in styles.findall('s:numFmts/s:numFmt',ns)}
    assert fmt=='1' or custom.get(fmt)=='0','Zero must use integer format'
   report={'ok':True,'tools':8,'points':3,'synthetic_input_only':True,'workbook':final['workbook']}
   (BASE/'selftest_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('MCP SELF-TEST PASSED: 8 tools, 3 known points, Excel XML and zero format checked.')

if __name__=='__main__':asyncio.run(main())
