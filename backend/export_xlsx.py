"""Excel authoring with the openpyxl library supplied by Harness Python."""
from __future__ import annotations
from copy import copy
from pathlib import Path
import math,os,re,warnings,zipfile
from openpyxl import load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.comments import Comment
from openpyxl.workbook.properties import CalcProperties
from PIL import Image,ImageDraw,ImageFont

HEADERS=['文章标题','图片字母','X','Y','线段表示含义']

def snapshot(sheet):
    cells={}
    for row in sheet:
        for c in row:
            if c.value is not None or c.has_style:
                cells[c.coordinate]=(c.value,c.data_type,copy(c.font),copy(c.fill),copy(c.border),copy(c.alignment),c.number_format,copy(c.protection),
                    (c.comment.text,c.comment.author) if c.comment else None,c.hyperlink.target if c.hyperlink else None)
    return (cells,str(sheet.freeze_panes),tuple(str(r) for r in sheet.merged_cells.ranges),
        {k:(v.width,v.hidden) for k,v in sheet.column_dimensions.items()},
        {k:(v.height,v.hidden) for k,v in sheet.row_dimensions.items()})

def number_format(value):
    return '0' if float(round(value,5)).is_integer() else '0.#####'

def sheet_name(title,used):
    base=re.sub(r'[\\/?*\[\]:]',' ',' '.join(title.split()[:3])).strip().strip("'")[:31] or 'Paper'
    name=base;i=2
    while name.casefold() in used:
        suffix=f' ({i})';name=base[:31-len(suffix)]+suffix;i+=1
    used.add(name.casefold());return name

def font(size):
    directory=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    for filename in [directory/'msyh.ttc',directory/'simsun.ttc','DejaVuSans.ttf']:
        try:return ImageFont.truetype(str(filename),size)
        except OSError:pass
    return ImageFont.load_default()

def preview(sheet,path):
    """Readable data QA only; host office_render provides native workbook rendering."""
    widths=[650,400,150,150,650];f=font(17);header=font(18)
    probe=ImageDraw.Draw(Image.new('RGB',(1,1)))
    def wrap(value,width):
        text=str(value if value is not None else '')
        lines=[];line=''
        for ch in text:
            if ch=='\n' or probe.textlength(line+ch,font=f)>width-16:
                lines.append(line);line='' if ch=='\n' else ch
            else:line+=ch
        lines.append(line);return lines
    rows=[]
    for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row,7),max_col=5):
        values=[]
        for c in row:
            v=c.value
            if isinstance(v,(int,float)):
                v=str(round(v)) if c.number_format=='0' else f'{v:.5f}'.rstrip('0').rstrip('.')
            values.append(v)
        lines=[wrap(v,w) for v,w in zip(values,widths)]
        rows.append((lines,max(42,max(map(len,lines))*25+14)))
    im=Image.new('RGB',(sum(widths)+2,42+sum(h for _,h in rows)),'white');draw=ImageDraw.Draw(im)
    draw.text((8,8),'Data preview — not a native Excel rendering',font=f,fill='black');top=42
    for i,(lines,height) in enumerate(rows):
        left=0
        for col,(block,w) in enumerate(zip(lines,widths)):
            draw.rectangle((left,top,left+w,top+height),fill='#F2C000' if i==0 else 'white',outline='#D9D9D9')
            for j,line in enumerate(block):draw.text((left+8,top+7+j*25),line,font=header if i==0 else f,fill='black')
            left+=w
        top+=height
    im.save(path)

def export(payload):
    template=Path(payload['template']);output=Path(payload['output'])
    # Fail instead of silently stripping unsupported complex template objects.
    with zipfile.ZipFile(template) as z:
        unsupported=[]
        for n in z.namelist():
            if n.startswith('xl/drawings/'):
                kinds=re.findall(rb'ObjectType=[\"\x27]([^\"\x27]+)',z.read(n)) if n.endswith('.vml') else []
                if not kinds or any(k!=b'Note' for k in kinds):unsupported.append(n)
            elif n.startswith(('xl/pivot','xl/slicer','xl/activeX/','xl/ctrlProps/','xl/threadedComments/','customXml/')) or n.endswith('vbaProject.bin'):
                unsupported.append(n)
    if unsupported:raise ValueError('Complex template objects require a separate preservation workflow: '+', '.join(unsupported[:3]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always');wb=load_workbook(template)
    if caught:raise ValueError('Template loader warning; export stopped to avoid data loss: '+str(caught[0].message))
    before={s.title:snapshot(s) for s in wb};original_formulas=sum(c.data_type=='f' for s in wb for row in s for c in row)
    template_sheet=wb.worksheets[0];used={n.casefold() for n in wb.sheetnames};expected={};counts=[]
    for paper in payload['papers']:
        name=sheet_name(paper['title'],used);sh=wb.create_sheet(name)
        for col,text in enumerate(HEADERS,1):
            c=sh.cell(1,col,text);src=template_sheet.cell(1,col)
            c.font=copy(src.font);c.fill=copy(src.fill);c.border=copy(src.border);c.alignment=copy(src.alignment)
            if c.fill.patternType is None:c.fill=PatternFill('solid',fgColor='F2C000')
        sh.row_dimensions[1].height=29
        for col,width in dict(A=110,B=63,C=18,D=18,E=65).items():sh.column_dimensions[col].width=width
        rows=[];starts=[]
        for panel in paper['panels']:
            starts.append((len(rows)+2,panel))
            for series in panel['series']:
                label=f"{panel['label']}; {series['label']}" if len(paper['panels'])>1 else series['label']
                for x,y in series['points']:
                    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (x,y)):
                        raise ValueError('Coordinates must be finite numeric values')
                    rows.append([paper['title'],panel['metric'],x,y,label])
        for index,row in enumerate(rows,2):
            for col,value in enumerate(row,1):
                c=sh.cell(index,col,value)
                if isinstance(value,str):c.data_type='s'  # Labels starting '=' remain literal text.
                c.font=Font(name='Times New Roman',size=14,color='000000')
                c.alignment=Alignment(horizontal='center' if col in (3,4) else 'left',vertical='center',wrap_text=True)
                if col in (3,4):c.number_format=number_format(value)
            units=lambda t:sum(2 if ord(c)>255 else 1 for c in t)
            sh.row_dimensions[index].height=max(47,math.ceil(units(row[0])/95)*18+4,math.ceil(units(row[1])/54)*18+4,math.ceil(units(row[4])/56)*18+4)
        for row,panel in starts:
            sh.cell(row,3).comment=Comment(f"Source: {paper['source']}; PDF page {panel['page']}; {panel['label']}. X: {panel['x_unit']}; Y: {panel['y_unit']}. Mean markers only; approximate graph digitization. Review: {panel['review']}",'Redframe Digitizer')
        expected[name]=rows;counts.append(dict(paper=paper['id'],sheet=name,points=len(rows),curves=sum(len(p['series']) for p in paper['panels'])))
    if original_formulas:wb.calculation=CalcProperties(fullCalcOnLoad=True)
    temp=output.with_name(output.stem+'.pending.xlsx');wb.save(temp)
    try:
        saved=load_workbook(temp)
        for name,state in before.items():
            if snapshot(saved[name])!=state:raise ValueError('Original template sheet changed: '+name)
        for name,rows in expected.items():
            actual=list(saved[name].iter_rows(min_row=2,max_row=len(rows)+1,max_col=5,values_only=True))
            for a,b in zip(actual,rows):
                if list(a[:2])!=b[:2] or a[4]!=b[4] or not all(math.isclose(a[i],b[i],rel_tol=1e-13,abs_tol=1e-13) for i in (2,3)):
                    raise ValueError('Exported row differs: '+name)
            for row in saved[name].iter_rows(min_row=2,max_col=4,min_col=3):
                for c in row:
                    if c.number_format!=number_format(c.value):raise ValueError('Numeric format changed')
        target=Path(payload['preview_dir']);target.mkdir(exist_ok=True)
        for name in expected:preview(saved[name],target/f"paper_{next(c['paper'] for c in counts if c['sheet']==name)}.png")
        saved.close();temp.replace(output)
    except Exception:
        temp.unlink(missing_ok=True);raise
    return dict(ok=True,engine='openpyxl',papers=len(counts),points=sum(c['points'] for c in counts),curves=sum(c['curves'] for c in counts),original_sheets_preserved=True,
        requires_recalculation=bool(original_formulas),preview_kind='data preview; use Harness office_render for native fidelity',counts=counts)
