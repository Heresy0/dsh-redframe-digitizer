import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const req=createRequire(path.join(process.env.REDFRAME_NODE_MODULES||(()=>{throw Error('Run install.cmd: spreadsheet runtime not configured')})(),'package.json'));
console.error('Loading spreadsheet runtime');
const {FileBlob,SpreadsheetFile}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
console.error('Spreadsheet runtime loaded');
const markerPath=process.env.REDFRAME_ARTIFACT_MARKER;
if(process.argv[2]==='--test-template'){
 execFileSync(process.execPath,[markerPath,'--operation-kind','create','--expected-output-count','1','--output-format','xlsx'],{stdio:'pipe'});
 const {Workbook}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
 const test=Workbook.create();const sh=test.worksheets.add('Template');
 sh.getRange('A1:E1').values=[['文章标题','图片字母','X','Y','线段表示含义']];
 sh.getRange('A1:E1').format.fill='#F2C000';
 await(await SpreadsheetFile.exportXlsx(test)).save(process.argv[3]);process.exit(0);
}
const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input.template));
const original=wb.worksheets.items.map(s=>({name:s.name,values:JSON.stringify(s.getUsedRange().values)}));
const template=wb.worksheets.items[0];
const used=new Set(wb.worksheets.items.map(s=>s.name.toLowerCase()));
const counts=[];
// Follow the installed spreadsheet author's operation contract before mutations.
const marker=process.env.REDFRAME_ARTIFACT_MARKER||(()=>{throw Error('Run install.cmd: artifact operation marker not configured')})();
execFileSync(process.execPath,[marker,'--operation-kind','edit','--expected-output-count','1','--output-format','xlsx'],{stdio:'pipe'});
for(const p of input.papers){
 let base=p.title.trim().split(/\s+/).slice(0,3).join(' ').replace(/[\\/?*\[\]:]/g,' ').trim().slice(0,31)||`Paper ${p.id}`;
 let name=base,i=2;while(used.has(name.toLowerCase())){const suffix=` (${i++})`;name=base.slice(0,31-suffix.length)+suffix;}used.add(name.toLowerCase());
 const sh=wb.worksheets.add(name),rows=[];
 for(const panel of p.panels)for(const series of panel.series)for(const [x,y] of series.points){
  const meaning=p.panels.length>1?`${panel.label}; ${series.label}`:series.label;
  rows.push([p.title,panel.metric,x,y,meaning]);
 }
 const end=rows.length+1;
 sh.getRange('A1:E1').copyFrom(template.getRange('A1:E1'),'all');
 sh.getRange('A1:E1').values=[['文章标题','图片字母','X','Y','线段表示含义']];
 for(const [c,width] of Object.entries({A:110,B:63,C:18,D:18,E:65}))sh.getRange(`${c}1:${c}${end}`).format.columnWidth=width;
 sh.getRange('A1:E1').format.rowHeight=29;
 sh.getRange(`A2:E${end}`).format.font={name:'Times New Roman',size:14,color:'#000000'};
 sh.getRange(`A2:E${end}`).format.wrapText=true;
 sh.getRange(`C2:D${end}`).format.horizontalAlignment='center';
 sh.getRange(`C2:D${end}`).setNumberFormat('0.#####');
 sh.getRange(`A2:E${end}`).values=rows;
 const units=t=>[...t].reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0);
 for(let r=0;r<rows.length;r++){
  sh.getRange(`A${r+2}:E${r+2}`).format.rowHeight=Math.max(47,Math.ceil(units(rows[r][0])/95)*18+4,Math.ceil(units(rows[r][4])/56)*18+4,Math.ceil(units(rows[r][1])/54)*18+4);
  for(const [col,j] of [['C',2],['D',3]])if(Number.isInteger(Math.round(rows[r][j]*1e5)/1e5))sh.getRange(`${col}${r+2}`).setNumberFormat('0');
 }
 let firstRow=2;
 for(const panel of p.panels){
  wb.notes.add({id:`${name}:C${firstRow}`,target:{cell:{sheetName:name,sheetId:sh.sheetId,address:`C${firstRow}`}},authorId:'',createdAt:'',body:{plainText:`Source: ${p.source}; PDF page ${panel.page}; ${panel.label}. X: ${panel.x_unit}; Y: ${panel.y_unit}. Graph digitization of mean marker centers; no error-bar extraction. Review: ${panel.review}`}});
  firstRow+=panel.series.reduce((n,s)=>n+s.points.length,0);
 }
 if(JSON.stringify(sh.getRange(`A2:E${end}`).values)!==JSON.stringify(rows))throw Error('Written data differs');
 counts.push({paper:p.id,sheet:name,points:rows.length,curves:p.panels.reduce((n,q)=>n+q.series.length,0)});
}
for(const o of original)if(JSON.stringify(wb.worksheets.getItem(o.name).getUsedRange().values)!==o.values)throw Error('Template content changed');
wb.recalculate();
await(await SpreadsheetFile.exportXlsx(wb)).save(input.output);
for(const item of counts){const img=await wb.render({sheetName:item.sheet,range:`A1:E${Math.min(item.points+1,7)}`,scale:1,format:'png'});await fs.writeFile(path.join(input.preview_dir,`paper_${item.paper}.png`),new Uint8Array(await img.arrayBuffer()));}
await fs.writeFile(path.join(path.dirname(input.output),'validation.json'),JSON.stringify({ok:true,papers:counts.length,points:counts.reduce((n,c)=>n+c.points,0),curves:counts.reduce((n,c)=>n+c.curves,0),original_sheets_preserved:true,counts},null,2));
