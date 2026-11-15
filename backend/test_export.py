"""Regression tests for values, template preservation, names and unsupported objects."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,zipfile
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.comments import Comment
from export_xlsx import export,snapshot

class ExcelExport(unittest.TestCase):
    def fixture(self,root):
        wb=Workbook();s=wb.active;s.title='Template'
        s.append(['文章标题','图片字母','X','Y','线段表示含义']);s['A1'].fill=PatternFill('solid',fgColor='F2C000')
        s['A2']='Original';s['B2']='=1+2';s['A2'].font=Font(name='Arial',size=13,bold=True)
        s['A2'].comment=Comment('Keep note','Fixture');s['A2'].hyperlink='https://example.com/'
        s.merge_cells('A4:B4');s['A4']='Merged';s.row_dimensions[4].height=30;s.column_dimensions['A'].width=42;s.freeze_panes='C2'
        path=root/'template.xlsx';wb.save(path);return path

    def payload(self,root):
        template=self.fixture(root)
        def paper(i,title):return dict(id=i,title=title,source='synthetic.pdf',panels=[dict(label='Panel a',metric='=literal metric',page=1,x_unit='day',y_unit='%',review='known synthetic geometry',series=[dict(label='Control',points=[[0,100],[5.25,50.123456789],[10,0]])])])
        return dict(template=str(template),output=str(root/'result.xlsx'),preview_dir=str(root/'previews'),papers=[paper(1,'Effects of Leaf experiment'),paper(2,'effects of leaf second')])

    def test_preserves_template_and_numeric_values_with_collision(self):
        with TemporaryDirectory() as d:
            root=Path(d);p=self.payload(root);before=snapshot(load_workbook(p['template'])['Template'])
            report=export(p);wb=load_workbook(p['output'])
            self.assertEqual(report['points'],6);self.assertTrue(report['requires_recalculation']);self.assertEqual(report['engine'],'openpyxl')
            self.assertEqual(wb.sheetnames,['Template','Effects of Leaf','effects of leaf (2)'])
            self.assertEqual(snapshot(wb['Template']),before)
            sh=wb['Effects of Leaf'];self.assertEqual(sh['D3'].value,50.123456789);self.assertEqual(sh['C2'].number_format,'0');self.assertEqual(sh['D4'].number_format,'0')
            self.assertEqual(sh['B2'].data_type,'s');self.assertEqual(sh['B2'].value,'=literal metric')
            self.assertTrue((root/'previews/paper_1.png').is_file());wb.close()

    def test_unsupported_template_refuses_before_writing(self):
        with TemporaryDirectory() as d:
            root=Path(d);p=self.payload(root)
            with zipfile.ZipFile(p['template'],'a') as z:z.writestr('xl/drawings/drawing1.xml','<unsupported/>')
            with self.assertRaisesRegex(ValueError,'Complex template'):export(p)
            self.assertFalse(Path(p['output']).exists())

    def test_nonfinite_value_is_not_written(self):
        with TemporaryDirectory() as d:
            root=Path(d);p=self.payload(root);p['papers'][0]['panels'][0]['series'][0]['points'][0][1]=float('nan')
            with self.assertRaisesRegex(ValueError,'finite'):export(p)
            self.assertFalse(Path(p['output']).exists())

if __name__=='__main__':unittest.main()
