"""Conservative local marker-template fitting. Scores are heuristics, not probabilities.

Only refines supplied points; never discovers new observations or changes axes/labels.
Requires an explicit shape/size hint from the image-reading agent.
"""
import math
import numpy as np

SHAPES={'circle','square','diamond','triangle_up','triangle_down'}

def validate_spec(spec):
    if spec.get('shape')=='manual':return {**spec,'radius':2.,'search_radius':1,'stroke_width':1.}
    if spec.get('shape') not in SHAPES:raise ValueError('Unsupported marker shape')
    if spec.get('fill','filled') not in ('filled','open'):raise ValueError('Marker fill must be filled/open')
    radius=float(spec['radius']);search=float(spec.get('search_radius',8));stroke=float(spec.get('stroke_width',1.5))
    if not all(math.isfinite(v) for v in (radius,search,stroke)) or not 2<=radius<=24 or not 1<=search<=24 or not .5<=stroke<=radius:
        raise ValueError('Require radius 2..24, search_radius 1..24 and stroke_width .5..radius, in crop pixels')
    color=spec.get('color')
    if color is not None and (not isinstance(color,list) or len(color)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=255 for v in color)):
        raise ValueError('color must be [r,g,b] in 0..255')
    return {**spec,'radius':radius,'search_radius':int(search),'stroke_width':stroke}

def template(shape,fill,radius,stroke,half):
    yy,xx=np.mgrid[-half:half+1,-half:half+1].astype(float)
    if shape=='circle':dist=np.hypot(xx,yy)
    elif shape=='square':dist=np.maximum(abs(xx),abs(yy))
    elif shape=='diamond':dist=abs(xx)+abs(yy)
    else:
        if shape=='triangle_down':yy=-yy
        # Equilateral triangle centered at its centroid; radius is circumradius.
        dist=np.maximum(yy*2,np.maximum(np.sqrt(3)*xx-yy,-np.sqrt(3)*xx-yy))
    outer=np.clip(radius+.5-dist,0,1)
    return outer if fill=='filled' else outer-np.clip(radius-stroke+.5-dist,0,1)

def refine_point(rgb,point,spec):
    spec=validate_spec(spec);coarse=[float(v) for v in point]
    h,w=rgb.shape[:2];cx,cy=coarse
    if not all(math.isfinite(v) for v in coarse) or not (0<=cx<w and 0<=cy<h):raise ValueError('Coarse point outside image')
    radius=spec['radius'];search=spec['search_radius'];half=math.ceil(radius*1.2)+2
    ix,iy=round(cx),round(cy);extent=half+search
    base={'coarse':coarse,'candidate':None,'selected':coarse,'status':'needs_review','score':0.,'reason':'insufficient_image_border'}
    if spec['shape']=='manual':return {**base,'reason':'manual_series'}
    if ix-extent<0 or iy-extent<0 or ix+extent>=w or iy+extent>=h:return base
    crop=rgb[iy-extent:iy+extent+1,ix-extent:ix+extent+1].astype(float)
    bg=np.percentile(crop.reshape(-1,3),90,axis=0)
    if spec.get('color') is not None:
        direction=bg-np.array(spec['color'],float);norm=float(direction@direction)
        if norm<40**2:return {**base,'reason':'low_contrast'}
        delta=bg-crop;ink=np.clip(np.einsum('ijk,k->ij',delta,direction)/norm,0,1)
        residual=np.linalg.norm(delta-ink[:,:,None]*direction,axis=2)
        ink*=np.exp(-(residual/55)**2)
    else:
        grey=crop.mean(axis=2);background=float(np.mean(bg));dark=float(grey.min())
        if background-dark<50:return {**base,'reason':'low_contrast'}
        ink=np.clip((background-grey)/(background-dark),0,1)
    windows=np.lib.stride_tricks.sliding_window_view(ink,(half*2+1,half*2+1))
    ink_energy=np.einsum('ijkl,ijkl->ij',windows,windows)
    best=np.full(ink_energy.shape,-1.,float)
    for r in np.linspace(radius*.85,radius*1.15,5):
        t=template(spec['shape'],spec.get('fill','filled'),r,spec['stroke_width'],half)
        overlap=np.einsum('ijkl,kl->ij',windows,t,optimize=False)
        score=2*overlap/(float((t*t).sum())+ink_energy+1e-9)
        best=np.maximum(best,score)
    ys,xs=np.mgrid[-search:search+1,-search:search+1]
    best[np.hypot(xs+ix-cx,ys+iy-cy)>search]=-1
    row,col=np.unravel_index(np.argmax(best),best.shape);score=float(best[row,col])
    px,py=float(ix+col-search),float(iy+row-search)
    # Subpixel parabola around the best integer center; only a local interpolation.
    if 0<col<2*search and 0<row<2*search:
        def offset(a,b,c):
            den=a-2*b+c
            return float(np.clip(.5*(a-c)/den,-.5,.5)) if den<-.0001 and min(a,c)>=0 else 0.
        px+=offset(best[row,col-1],score,best[row,col+1]);py+=offset(best[row-1,col],score,best[row+1,col])
    separate=np.hypot(xs-(col-search),ys-(row-search))>=max(3,radius*1.4)
    runner=max(0.,float(best[separate].max())) if separate.any() else 0.
    result={**base,'candidate':[px,py],'score':round(score,5),'peak_margin':round(score-runner,5),'shift_pixels':round(math.hypot(px-cx,py-cy),5)}
    if score<.88:result['reason']='weak_shape_match'
    elif score-runner<.07:result['reason']='ambiguous_candidates'
    elif math.hypot(px-cx,py-cy)>search-1:result['reason']='search_boundary'
    else:result.update(selected=[px,py],status='refined',reason='shape_match')
    return result

def refine_series(image,series,specs):
    rgb=np.asarray(image.convert('RGB'));by_label={}
    for item in specs:
        label=item['label']
        if label in by_label:raise ValueError('Duplicate marker spec label')
        by_label[label]=validate_spec(item)
    if set(by_label)!=set(s['label'] for s in series):raise ValueError('Provide exactly one marker spec for every series')
    rows=[]
    for s in series:
        for i,p in enumerate(s.get('coarse_pixel_points',s['pixel_points']),1):
            rows.append({'label':s['label'],'point_index':i,**refine_point(rgb,p,by_label[s['label']])})
    for i,row in enumerate(rows):
        if row['status']!='refined':continue
        r=by_label[row['label']]['radius']
        # A nearby other series cannot be assigned safely by shape alone.
        if any(other['label']!=row['label'] and math.dist(row['selected'],other['coarse'])<r*1.5 for other in rows):
            row.update(selected=row['coarse'],status='needs_review',reason='near_other_series')
    for s in series:
        group=[r for r in rows if r['label']==s['label']]
        if any(b['selected'][0]<a['selected'][0] or math.dist(a['selected'],b['selected'])<1 for a,b in zip(group,group[1:])):
            # Restore the whole series together: pairwise restoration could introduce a new reversal.
            for row in group:row.update(selected=row['coarse'],status='needs_review',reason='ordering_or_duplicate')
    return rows
