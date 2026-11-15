"""Portable batch contracts and rollback/review gates; no desktop success mocks."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import copy,json,unittest
from PIL import Image,ImageDraw
from openpyxl import Workbook
import core

class BatchStages(unittest.TestCase):
    def job(self,base,panels=1):
        jid='c'*32;root=base/jid;root.mkdir()
        wb=Workbook();wb.active.append(['文章标题','图片字母','X','Y','线段表示含义']);wb.save(root/'template.xlsx');wb.close()
        items=[]
        for i in range(panels):
            pid=f'p{i+1}';folder=root/'panels'/pid;folder.mkdir(parents=True)
            im=Image.new('RGB',(180,180),'white');ImageDraw.Draw(im).ellipse((83,83,97,97),fill='black');im.save(folder/'image.png')
            items.append(dict(id=pid,paper_id=1,page=1,label=pid,image=f'panels/{pid}/image.png',image_size=[180,180],status='needs_digitization'))
        core.save(root/'job.json',dict(id=jid,papers=[dict(id=1,source_name='synthetic.pdf')],panels=items))
        return jid,root

    def inputs(self,jid,pid='p1',manual=False):
        return dict(job_id=jid,panel_id=pid,title='Known Batch Graph',metric='Mass remaining',x_unit='day',y_unit='%',calibration={'x':[[0,0],[179,179]],'y':[[179,0],[0,179]]},series=[{'label':'Control','points':[[93,92]]}],marker_specs=[dict(label='Control',shape='manual' if manual else 'circle',radius=7)])

    def decision(self,result):
        return dict(panel_id=result['panel_id'],expected_revision=result['revision'],review_notes='Known synthetic center and shape inspected for contract regression',point_reviews=[dict(label=r['label'],point_index=r['point_index'],decision='keep_coarse',notes='Known synthetic coarse position verified by fixture') for r in result['points'] if r['status']=='needs_review'])

    def test_same_coordinates_as_legacy_path(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d),2)
            a=self.inputs(jid);spec=a.pop('marker_specs');core.submit_digitization(**a);single=core.refine_panel_points(jid,'p1',spec)
            batch=core.submit_and_refine(**self.inputs(jid,'p2'))
            self.assertEqual(single['points'],batch['points']);self.assertEqual(batch['stage'],'awaiting_visual_review')
            _,job=core.load_job(jid);self.assertTrue(all(p['status']=='awaiting_review' for p in job['panels']))
            self.assertTrue(all((root/p).is_file() for p in batch['patches']))

    def test_failed_stage_preserves_old_job_and_old_overlay(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d));a=self.inputs(jid);a.pop('marker_specs');original=core.submit_digitization(**a)
            core.review_panel(jid,'p1',True,'Fixture accepted before failed resubmission')
            before=(root/'job.json').read_bytes();image=(root/original['overlay']).read_bytes()
            with patch.object(core,'_refine_panel',side_effect=RuntimeError('forced stage failure')):
                with self.assertRaisesRegex(RuntimeError,'previous panel state preserved'):core.submit_and_refine(**self.inputs(jid))
            self.assertEqual((root/'job.json').read_bytes(),before);self.assertEqual((root/original['overlay']).read_bytes(),image)

    def test_invalid_specs_are_rejected_before_state_change(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d));before=(root/'job.json').read_bytes();a=self.inputs(jid);a['marker_specs'][0]['radius']=float('nan')
            with self.assertRaises(ValueError):core.submit_and_refine(**a)
            self.assertEqual((root/'job.json').read_bytes(),before)

    def test_one_bad_review_does_not_commit_other_good_review(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d),2)
            reviews=[self.decision(core.submit_and_refine(**self.inputs(jid,pid,True))) for pid in ('p1','p2')]
            reviews[1]['point_reviews']=[];before=(root/'job.json').read_bytes()
            with patch.object(core,'export_workbook') as export:
                with self.assertRaisesRegex(ValueError,'individually'):core.review_and_export(jid,reviews,'Both panels covered')
                export.assert_not_called()
            self.assertEqual((root/'job.json').read_bytes(),before)

    def test_stale_duplicate_unknown_and_missing_revisions(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d));first=core.submit_and_refine(**self.inputs(jid))
            current=core.refine_panel_points(jid,'p1',self.inputs(jid)['marker_specs'])
            self.assertNotEqual(first['revision'],current['revision'])
            good=self.decision(current);stale=self.decision(first)
            unknown={**good,'panel_id':'unknown'};missing={**good,'expected_revision':None}
            before=(root/'job.json').read_bytes()
            for reviews in ([stale],[good,good],[unknown],[missing]):
                with self.subTest(reviews=reviews),self.assertRaises(ValueError):core.review_and_export(jid,reviews,'Covered')
                self.assertEqual((root/'job.json').read_bytes(),before)

    def test_partial_coverage_or_missing_notes_does_not_commit(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d),2);result=core.submit_and_refine(**self.inputs(jid));before=(root/'job.json').read_bytes()
            for notes in ('','Only one of two panels reviewed'):
                with self.assertRaises(ValueError):core.review_and_export(jid,[self.decision(result)],notes)
                self.assertEqual((root/'job.json').read_bytes(),before)

    def test_failed_export_retains_valid_review_for_direct_retry(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d));result=core.submit_and_refine(**self.inputs(jid,manual=True))
            (root/'result.xlsx').write_bytes(b'last successful result')
            with patch.object(core,'export_workbook',side_effect=RuntimeError('native export failed')):
                with self.assertRaisesRegex(RuntimeError,'Reviews saved'):core.review_and_export(jid,[self.decision(result)],'Covered')
            _,job=core.load_job(jid);self.assertEqual(job['panels'][0]['status'],'accepted');self.assertEqual(job['last_batch']['phase'],'export_failed')
            self.assertEqual((root/'result.xlsx').read_bytes(),b'last successful result')
            core._validate_export(root.resolve(),job,'Retry only export')

    def test_changed_source_pixels_invalidate_accepted_revision(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid,root=self.job(Path(d));result=core.submit_and_refine(**self.inputs(jid));r=self.decision(result)
            core.review_panel(jid,'p1',True,r['review_notes'],r['point_reviews'],r['expected_revision'])
            _,job=core.load_job(jid);Image.new('RGB',(180,180),'white').save(root/job['panels'][0]['image'])
            with self.assertRaisesRegex(ValueError,'changed'):core._validate_export(root.resolve(),job,'Covered')

if __name__=='__main__':unittest.main()
