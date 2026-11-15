"""Known synthetic centers + review gates; no private literature fixtures in CI."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import math,unittest
from PIL import Image,ImageDraw
import numpy as np
import core
from refine_points import refine_point,refine_series

class LocalRefinement(unittest.TestCase):
    def image(self,shape='circle',fill='filled'):
        im=Image.new('RGB',(180,180),'white');d=ImageDraw.Draw(im)
        kw={'fill':'black'} if fill=='filled' else {'outline':'black','width':2}
        if shape=='circle':d.ellipse((83,83,97,97),**kw)
        elif shape=='square':d.rectangle((83,83,97,97),**kw)
        elif shape=='diamond':d.polygon([(90,82),(98,90),(90,98),(82,90)],**kw)
        else:d.polygon([(90,82),(97,94),(83,94)],**kw)
        return im

    def test_filled_and_open_centers_recover_coarse_offsets(self):
        for shape in ('circle','square'):
            for fill in ('filled','open'):
                with self.subTest(shape=shape,fill=fill):
                    row=refine_point(np.array(self.image(shape,fill)),[93,92],dict(shape=shape,fill=fill,radius=7,stroke_width=2))
                    self.assertEqual(row['status'],'refined',row)
                    self.assertLess(math.dist(row['selected'],[90,90]),.6)

    def test_blank_line_errorbar_and_wrong_color_are_not_markers(self):
        for kind in ('blank','line','errorbar','wrong_color'):
            im=Image.new('RGB',(180,180),'white');d=ImageDraw.Draw(im)
            if kind=='line':d.line((60,90,120,90),fill='black',width=2)
            if kind=='errorbar':
                d.line((90,70,90,110),fill='black',width=2);d.line((83,70,97,70),fill='black',width=2);d.line((83,110,97,110),fill='black',width=2)
            if kind=='wrong_color':d.ellipse((83,83,97,97),fill='blue')
            spec=dict(shape='circle',fill='filled',radius=7)
            if kind=='wrong_color':spec['color']=[255,0,0]
            row=refine_point(np.array(im),[93,92],spec)
            self.assertEqual(row['selected'],[93,92]);self.assertEqual(row['status'],'needs_review')

    def test_polygon_shapes_and_duplicate_centers(self):
        for shape in ('diamond','triangle_up'):
            row=refine_point(np.array(self.image(shape)),[93,92],dict(shape=shape,radius=8))
            self.assertEqual(row['status'],'refined',row);self.assertLess(math.dist(row['selected'],[90,90]),1)
        rows=refine_series(self.image(),[dict(label='a',pixel_points=[[92,92],[94,92]])],[dict(label='a',shape='circle',radius=7)])
        self.assertTrue(all(r['reason']=='ordering_or_duplicate' for r in rows))

    def test_two_equal_candidates_and_other_series_are_flagged(self):
        im=Image.new('RGB',(180,180),'white');d=ImageDraw.Draw(im)
        for x in (82,98):d.ellipse((x-4,86,x+4,94),fill='black')
        row=refine_point(np.array(im),[90,90],dict(shape='circle',fill='filled',radius=4,search_radius=12))
        self.assertEqual(row['reason'],'ambiguous_candidates');self.assertEqual(row['selected'],[90,90])
        rows=refine_series(self.image(),[dict(label='a',pixel_points=[[93,92]]),dict(label='b',pixel_points=[[94,93]])],[dict(label=x,shape='circle',radius=7) for x in ('a','b')])
        self.assertTrue(all(r['reason']=='near_other_series' for r in rows))

    def test_manual_border_invalid_spec_and_no_mutation(self):
        series=[dict(label='a',pixel_points=[[93,92]])]
        rows=refine_series(self.image(),series,[dict(label='a',shape='manual')])
        self.assertEqual(rows[0]['reason'],'manual_series');self.assertEqual(series[0]['pixel_points'],[[93,92]])
        row=refine_point(np.array(self.image()),[1,1],dict(shape='circle',radius=7))
        self.assertEqual(row['reason'],'insufficient_image_border')
        for radius in (float('nan'),0,99):
            with self.assertRaises(ValueError):refine_point(np.array(self.image()),[93,92],dict(shape='circle',radius=radius))

    def job(self,root):
        jid='b'*32;folder=root/jid;folder.mkdir();self.image().save(folder/'image.png')
        p=dict(id='p',paper_id=1,label='panel',page=1,title='Known Marker Test',metric='Mass',x_unit='day',y_unit='%',image='image.png',image_size=[180,180],status='accepted',review='old review',getdata_project='image.gdw',calibration={'x':[[0,0],[179,179]],'y':[[179,0],[0,179]]},series=[dict(label='a',pixel_points=[[93,92]],points=[[93,87]])])
        core.save(folder/'job.json',dict(id=jid,papers=[dict(id=1,source_name='synthetic.pdf')],panels=[p]))
        return jid

    def test_refinement_invalidates_review_and_is_repeatable(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid=self.job(Path(d));spec=[dict(label='a',shape='circle',radius=7)]
            a=core.refine_panel_points(jid,'p',spec);b=core.refine_panel_points(jid,'p',spec)
            self.assertEqual(a['points'],b['points']);self.assertEqual(a['status'],'awaiting_review')
            root,job=core.load_job(jid);self.assertNotIn('review',job['panels'][0])
            self.assertEqual(job['panels'][0]['series'][0]['coarse_pixel_points'],[[93,92]])
            self.assertTrue(all((root/p).is_file() for p in a['patches']))

    def test_unresolved_requires_individual_review_and_resubmit_clears_state(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid=self.job(Path(d));core.refine_panel_points(jid,'p',[dict(label='a',shape='manual')])
            with self.assertRaisesRegex(ValueError,'individually'):core.review_panel(jid,'p',True,'General note is insufficient')
            core.review_panel(jid,'p',True,'Known original marker checked',[dict(label='a',point_index=1,decision='keep_coarse',notes='Synthetic center manually inspected')])
            root,job=core.load_job(jid);self.assertEqual(job['panels'][0]['status'],'accepted')
            core.submit_digitization(jid,'p','Known Marker Test','Mass','day','%',job['panels'][0]['calibration'],[dict(label='a',points=[[90,90]])])
            _,job=core.load_job(jid);self.assertNotIn('refinement',job['panels'][0]);self.assertNotIn('review',job['panels'][0])

    def test_zero_boundary_is_flagged_without_clamping(self):
        with TemporaryDirectory() as d,patch.object(core,'JOB_ROOT',Path(d)):
            jid=self.job(Path(d));root,job=core.load_job(jid)
            job['panels'][0]['calibration']['x']=[[93,0],[173,80]];core.save(root/'job.json',job)
            result=core.refine_panel_points(jid,'p',[dict(label='a',shape='circle',radius=7)])
            row=result['points'][0];self.assertEqual(row['reason'],'zero_boundary_requires_review')
            self.assertEqual(row['selected'],[93,92]);self.assertLess(row['candidate'][0],93)

if __name__=='__main__':unittest.main()
