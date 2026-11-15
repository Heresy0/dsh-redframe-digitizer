"""Portable failure/authority tests. Mocks here do NOT prove desktop execution."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy,json,unittest
from PIL import Image
from openpyxl import Workbook,load_workbook
import core
from getdata_adapter import parse_export,checked_points,executable_from_config

class GetDataSafety(unittest.TestCase):
    def panel(self):
        return dict(id='panel1',paper_id=1,label='a',page=1,title='Known Graph Test',metric='Mass remaining',x_unit='day',y_unit='%',image='image.png',image_size=[120,120],status='accepted',review='Synthetic geometry only',calibration={'x':[[10,0],[110,10]],'y':[[110,0],[10,100]]},series=[dict(label='Control 中文; α',pixel_points=[[10,10],[60,60],[110,85]],points=[[0,100],[5,50],[10,25]])])

    def test_parser_refuses_missing_duplicate_extra_and_bad_rows(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'out.txt'
            for content in ['header\nRF0001\n0 100\n','RF0001\n0 100\nRF0001\n1 2\nRF0002\n0 1', 'RF0001\n0 100\nRF9999\n0 1','RF0001\nnan 2\nRF0002\n0 1']:
                p.write_text(content)
                with self.assertRaises(ValueError):parse_export(p,['RF0001','RF0002'])

    def test_read_actual_values_and_quantized_reference(self):
        p=self.panel();p['series'][0]['pixel_points'][1]=[60.06,60.06]
        parsed={'RF0001':[[0,100],[5.01111111111111,49.8888888888889],[10,25]]}
        records,delta=checked_points(p,parsed)
        self.assertEqual(records[0]['points'],parsed['RF0001']);self.assertGreater(delta,0)
        for malformed in ({'RF0001':[[0,100]]},{'RF0001':[[0,100],[5,50],[10,25]]}):
            with self.assertRaises(ValueError):checked_points(p,malformed)

    def test_reversed_anchor_order_is_supported_and_log_blocked(self):
        p=self.panel();p['calibration']['x'].reverse();p['calibration']['y'].reverse()
        actual={'RF0001':p['series'][0]['points']}
        self.assertEqual(checked_points(p,actual)[0][0]['points'],actual['RF0001'])
        p['calibration']['x_scale']='log10'
        with self.assertRaisesRegex(ValueError,'linear'):checked_points(p,actual)

    def test_missing_getdata_does_not_fall_back_to_preview(self):
        with TemporaryDirectory() as d,patch.dict('os.environ',{'REDFRAME_GETDATA_EXE':''}):
            with self.assertRaisesRegex(RuntimeError,'No fallback'):executable_from_config(d)

    def job(self,root):
        jid='a'*32;folder=root/jid;folder.mkdir();p=self.panel()
        Image.new('RGB',(120,120),'white').save(folder/'image.png')
        wb=Workbook();wb.active.append(['文章标题','图片字母','X','Y','线段表示含义']);wb.save(folder/'template.xlsx');wb.close()
        core.save(folder/'job.json',dict(id=jid,panels=[p],papers=[dict(id=1,source_name='synthetic.pdf')],status='review_required'))
        return jid,folder

    def test_failed_desktop_export_never_calls_excel_writer(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,folder=self.job(Path(d))
            with patch('getdata_adapter.executable_from_config',return_value=Path('fake-test-only.exe')),patch('getdata_adapter.export_panel',side_effect=RuntimeError('desktop failed')),patch('export_xlsx.export') as writer:
                with self.assertRaisesRegex(RuntimeError,'desktop failed'):core.export_workbook(jid,'Synthetic coverage')
                writer.assert_not_called();self.assertFalse((folder/'result.xlsx').exists())

    def test_excel_consumes_adapter_result_not_stored_preview(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,folder=self.job(Path(d));job=json.loads((folder/'job.json').read_text(encoding='utf-8'))
            # Deliberately poison stored preview, while the adapter supplies known TXT values.
            records=copy.deepcopy(job['panels'][0]['series']);job['panels'][0]['series'][0]['points']=[[-9,-9]]*3;core.save(folder/'job.json',job)
            proof={'txt':str(folder/'test-only.txt'),'txt_sha256':'mock-proof','verified':True}
            with patch('getdata_adapter.executable_from_config',return_value=Path('fake-test-only.exe')),patch('getdata_adapter.export_panel',return_value=(records,proof)):
                result=core.export_workbook(jid,'Synthetic coverage')
            wb=load_workbook(result['workbook']);sh=wb.worksheets[1]
            self.assertEqual([list(r) for r in sh.iter_rows(min_row=2,min_col=3,max_col=4,values_only=True)],records[0]['points']);wb.close()

if __name__=='__main__':unittest.main()
