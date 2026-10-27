"""Stage A: original dimension specification and drawings. No CAD-core imports.

The frozen spec uses engineering primitives and independent assembly placements;
the later reconstruction does not import this renderer or copy its paths.
"""
import hashlib
import json
import math
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'examples/original-workstation'


def rect(x,y,w,h,r=0):
    return {'type':'roundrect' if r else 'rect','x':x,'y':y,'w':w,'h':h,'r':r}


def circle(x,y,r):
    return {'type':'circle','x':x,'y':y,'r':r}


def spec():
    parts=[]
    def add(pid,name,body,origin=(0,0,0),plane='xy',group='case',tabs=None,notches=None,holes=None,marks=None):
        p={'id':pid,'name':name,'group':group,'plane':plane,'origin_mm':list(origin),
           'body':body,'tabs':tabs or [],'notches':notches or [],'holes':holes or [],'marks':marks or []}
        parts.append(p);return p
    def hole(p,key,shape):p['holes'].append({'id':key,**shape})
    def tab(p,x,y,w,h):p['tabs'].append(rect(x,y,w,h))
    def label(p,text,x,y,h=3):p['marks'].append({'type':'text','id':'label-'+str(len(p['marks'])),'text':text,'x':x,'y':y,'height':h})
    base=add('B00','底座',rect(-135,-105,270,210,8))
    for x in (-128.5,128.5):
        for y in (-60,0,60):hole(base,f'side-{x}-{y}',rect(x-1.575,y-8.1,3.15,16.2))
    for x in (-90,-30,30,90):hole(base,f'back-{x}',rect(x-8.1,86.925,16.2,3.15))
    for x in (-118,118):
        for y in (-98,98):hole(base,f'foot-{x}-{y}',circle(x,y,1.6))
    label(base,'TOOL STATION / 3 mm',-60,-15,4)
    for i,x in enumerate((-130,127)):
        p=add(f'B0{i+1}','左侧板' if i==0 else '右侧板',
            {'type':'shoulder','points':[[-90,3],[-90,220],[30,220],[85,280],[90,280],[90,3]],
             'cubic_controls':[[30,245],[55,280]]},(x,0,0),'yz')
        for y in (-60,0,60):
            tab(p,y-8,0,16,3)
            for z in (97.5,201.5):hole(p,f'deck-{y}-{z}',rect(y-8.1,z-1.575,16.2,3.15))
            for z in (13.5,109.5):hole(p,f'rail-{y}-{z}',rect(y-6.1,z-1.575,12.2,3.15))
        for z in (52,148):hole(p,f'guide-{z}',circle(-40,z,1.6))
        for z in (30,60,126,156):
            for y in (-65,-45,-25,-5,15,35,55):hole(p,f'vent-{y}-{z}',rect(y-4,z-1.5,8,3,1.5))
        label(p,p['id'],62,205)
    back=add('B03','背板',rect(-127,3,254,277),(0,90,0),'xz')
    for x in (-90,-30,30,90):
        tab(back,x-8,0,16,3)
        for z in (97.5,201.5):hole(back,f'deck-{x}-{z}',rect(x-8.1,z-1.575,16.2,3.15))
    for z in (228,246,264):
        for x in range(-108,109,18):hole(back,f'peg-{x}-{z}',rect(x-1.575,z-5.1,3.15,10.2))
    for z in (35,50,65,80,131,146,161,176):
        for x in range(-100,101,20):hole(back,f'vent-{x}-{z}',rect(x-4,z-1.5,8,3,1.5))
    label(back,'ORIGINAL / TOOL STATION',-108,209,4)
    for pid,z,name in [('B04',200,'操作台'),('B05',96,'中层隔板')]:
        p=add(pid,name,rect(-127,-90,254,177),(0,0,z))
        for y in (-60,0,60):
            for x in (-130,127):tab(p,x,y-8,3,16)
        for x in (-90,-30,30,90):tab(p,x-8,87,16,3)
        label(p,pid,-120,68)
        if pid=='B04':
            for x in (75,105):
                for y in (-40,-20):hole(p,f'comb-{x}-{y}',rect(x-6.1,y-1.575,12.2,3.15))
    for i,(x,z) in enumerate([(-127,12),(117,12),(-127,108),(117,108)]):
        p=add(f'B0{6+i}','抽屉滑轨',rect(x,-88,10,170),(0,0,z))
        for y in (-60,0,60):tab(p,-130 if x<0 else 127,y-6,3,12)
        label(p,p['id'],x+2,-80,2.5)
    for d,dz in [(1,0),(2,96)]:
        prefix=f'D{d}';group=f'drawer-{d}'
        floor=add(prefix+'-01','抽屉底板',rect(-125,-90,250,165,3),(0,0,15+dz),group=group)
        for x in (-119.5,119.5):
            for y in (-60,0,55):hole(floor,f'side-{x}-{y}',rect(x-1.575,y-6.1,3.15,12.2))
        for x in (-85,0,85):hole(floor,f'back-{x}',rect(x-6.1,67.925,12.2,3.15))
        for x in (-95,-32,32,95):hole(floor,f'front-{x}',rect(x-6.1,-84.075,12.2,3.15))
        for y in (-55,0,50):hole(floor,f'long-{y}',rect(-1.575,y-6.1,3.15,12.2))
        for y in (-30,25):
            for x in (-80,80):hole(floor,f'cross-{x}-{y}',rect(x-6.1,y-1.575,12.2,3.15))
        label(floor,prefix+' / 6 CELLS',-90,7,3)
        for i,x in enumerate((-121,118)):
            p=add(prefix+f'-0{2+i}','抽屉侧板',rect(-81,18,152,72),(x,0,dz),'yz',group)
            for y in (-60,0,55):tab(p,y-6,15,12,3)
            hole(p,'travel-slot',rect(-55,50.2,100,3.6,1.8))
            label(p,p['id'],-70,75)
        p=add(prefix+'-04','抽屉后板',rect(-118,18,236,72),(0,71,dz),'xz',group)
        for x in (-85,0,85):tab(p,x-6,15,12,3)
        label(p,p['id'],-108,76)
        p=add(prefix+'-05','抽屉面板',rect(-125,18,250,74,3),(0,-81,dz),'xz',group)
        for x in (-95,-32,32,95):tab(p,x-6,15,12,3)
        hole(p,'finger',rect(-30,46,60,18,9))
        label(p,'01 / TOOLS' if d==1 else '02 / PARTS',-112,64,4)
        for k,y in enumerate((-84,-87,-90)):
            p=add(prefix+f'-0{6+k}','三层拉手',rect(-45,39,90,32,5),(0,y,dz),'xz',group)
            hole(p,'finger',rect(-30,46,60,18,9))
        p=add(prefix+'-09','纵向分格',rect(-78,18,146,50),(-1.5,0,dz),'yz',group)
        for y in (-55,0,50):tab(p,y-6,15,12,3)
        for y in (-30,25):p['notches'].append(rect(y-1.575,43,3.15,26))
        label(p,p['id'],-70,25)
        for k,y in enumerate((-28.5,26.5)):
            p=add(prefix+f'-{10+k}','横向分格',rect(-118,18,236,50),(0,y,dz),'xz',group)
            for x in (-80,80):tab(p,x-6,15,12,3)
            p['notches'].append(rect(-1.575,17,3.15,26))
            label(p,p['id'],-108,55)
    for i,x in enumerate((-108,-72,-36,36,72,108)):
        p=add(f'H{i+1:02}','可拆挂钩',{'type':'polygon','points':[[55,222],[63,222],[64,230],[74,235],[87,235],[87,251],[69,251],[64,241],[55,233]]},
              (x-1.5,0,0),'yz','hook')
        for z in (228,246):tab(p,87,z-5,3,10)
        # Lower tab joins body across y=74..87, not a disconnected tongue.
        p['tabs'].append(rect(74,223,13,12))
        label(p,p['id'],72,238,2.5)
    for i,y in enumerate((-38.5,-18.5)):
        p=add(f'C{i+1:02}','双排线缆梳',rect(60,203,60,17),(0,y,0),'xz','comb')
        for x in (75,105):tab(p,x-6,200,12,3)
        for x in (70,84,98,112):p['notches'].append(rect(x-2.5,212,5,10,2.5))
    def container(prefix,x0,x1,zmax,group):
        p=add(prefix+'1', '工具杯底' if prefix=='U' else '托盘底',rect(x0,-38,x1-x0,86),(0,0,203),group=group)
        for x in (x0+5.5,x1-5.5):
            for y in (-16,25):hole(p,f'side-{x}-{y}',rect(x-1.575,y-6.1,3.15,12.2))
        for y in (-32.5,42.5):
            for x in (x0+24,x1-24):hole(p,f'end-{x}-{y}',rect(x-5.1,y-1.575,10.2,3.15))
        for k,x in enumerate((x0+4,x1-7)):
            q=add(prefix+str(2+k),'容器侧板',rect(-34,206,78,zmax-206),(x,0,0),'yz',group)
            for y in (-16,25):tab(q,y-6,203,12,3)
            if prefix=='U':
                for y in (-18,0,18,36):
                    for z in (219,234,249):hole(q,f'vent-{y}-{z}',rect(y-3,z-1.5,6,3,1.5))
        for k,y in enumerate((-31,44)):
            q=add(prefix+str(4+k),'容器前后板',rect(x0+7,206,x1-x0-14,zmax-206),(0,y,0),'xz',group)
            for x in (x0+24,x1-24):tab(q,x-5,203,10,3)
            if prefix=='U':
                for x in (x0+19,x0+38,x0+57):
                    for z in (219,234,249):hole(q,f'vent-{x}-{z}',rect(x-3,z-1.5,6,3,1.5))
            elif k==0:q['notches'].append(rect((x0+x1)/2-6,220,12,10,3))
        return p
    floor=container('U',-118,-42,266,'cup')
    for y in (-18,28):hole(floor,f'center-{y}',rect(-81.575,y-5.1,3.15,10.2))
    for x in (-101,-59):hole(floor,f'cross-{x}',rect(x-5.1,3.425,10.2,3.15))
    p=add('U6','工具杯纵分格',rect(-31,206,72,40),(-81.5,0,0),'yz','cup')
    for y in (-18,28):tab(p,y-5,203,10,3)
    p['notches'].append(rect(3.425,226,3.15,21))
    p=add('U7','工具杯横分格',rect(-111,206,62,40),(0,6.5,0),'xz','cup')
    for x in (-101,-59):tab(p,x-5,203,10,3)
    p['notches'].append(rect(-81.575,205,3.15,21))
    floor=container('T',-23,53,228,'tray')
    for y in (-16,25):hole(floor,f'divider-{y}',rect(13.425,y-5.1,3.15,10.2))
    p=add('T6','托盘分格',rect(-31,206,72,18),(13.5,0,0),'yz','tray')
    for y in (-16,25):tab(p,y-5,203,10,3)
    p=add('R01','半毫米刻度尺',rect(-100,-12,200,24,3),(-10,-76,203),group='ruler')
    for x in (-94,94):hole(p,f'hanging-{x}',circle(x,0,1.6))
    for k in range(361):
        length=6 if k%20==0 else 4.5 if k%10==0 else 3 if k%2==0 else 1.5
        p['marks'].append({'id':f'tick-{k:03}','type':'line','points':[[-90+k*.5,-9],[-90+k*.5,-9+length]]})
    for k in range(0,181,10):label(p,str(k),-90+k,2,2)
    assert len(parts)==54
    return {'schema_version':1,'design_revision':'A1','name':'原创双抽屉桌面工具站',
        'units':'mm','envelope_mm':[270,210,280],'thickness_mm':3,'slot_width_mm':3.15,
        'sheet_mm':[600,400],'sheet_margin_mm':6,'part_gap_mm':6,'minimum_web_mm':2.99,
        'drawer_travel_mm':80,'guide_slot_overall_length_mm':100,'guide_slot_width_mm':3.6,
        'guide_slot_bounds_y_mm':[-55,45],'guide_bolt_y_mm':-40,'guide_spacer_nominal_mm':6,
        'assembly_planes':{'xy':{'u':[1,0,0],'v':[0,1,0]},'xz':{'u':[1,0,0],'v':[0,0,1]},'yz':{'u':[0,1,0],'v':[0,0,1]}},
        'parts':parts,'physical_fit_verified':False,'machine_validated':False,
        'notes':['槽宽为名义厚度加 0.15 mm，总间隙；未补偿切缝。','所有二维坐标为部件局部坐标，按 plane 和 origin_mm 映射到装配坐标；xz 板厚向 -Y。',
                 '导向槽总长 100 mm（包括两端圆弧），从 Y=-55 到45，光杆中心行程范围 -53.2..43.2。设计使用 -40..40，共80mm。',
                 '四个导向件及六毫米间隔套待现场选型；木板三维检查不包含外购五金、承重和抗倾覆。']}


def bounds(p):
    points=[]
    for s in [p['body'],*p['tabs']]:
        if s['type'] in ('polygon','shoulder'):points+=s['points']
        else:points += [[s['x'],s['y']],[s['x']+s['w'],s['y']+s['h']]]
    return [min(q[0] for q in points),min(q[1] for q in points),max(q[0] for q in points),max(q[1] for q in points)]


def draw_shape(c,s):
    t=s['type']
    if t in ('rect','roundrect'):
        c.roundRect(s['x'],s['y'],s['w'],s['h'],s.get('r',0),stroke=1,fill=0)
    elif t=='circle':c.circle(s['x'],s['y'],s['r'],stroke=1,fill=0)
    else:
        p=c.beginPath();pts=s['points'];p.moveTo(*pts[0])
        for i,q in enumerate(pts[1:],1):
            if t=='shoulder' and i==3:p.curveTo(*s['cubic_controls'][0],*s['cubic_controls'][1],*q)
            else:p.lineTo(*q)
        p.close();c.drawPath(p)


def make_blueprint():
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    ROOT.mkdir(parents=True,exist_ok=True)
    target=ROOT/'blueprint';target.mkdir(exist_ok=True)
    if (target/'frozen-manifest.json').exists():raise RuntimeError('FROZEN_BLUEPRINT_ALREADY_EXISTS')
    design=spec()
    (target/'dimensions.json').write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (target/'特征尺寸表.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['part','category','feature','engineering_primitive_mm'])
        for p in design['parts']:
            for category in ('body','tabs','notches','holes','marks'):
                for i,s in enumerate([p['body']] if category=='body' else p[category]):
                    writer.writerow([p['id'],category,s.get('id',str(i)),json.dumps(s,ensure_ascii=False,separators=(',',':'))])
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    pdf=target/'平面分解设计图-A1.pdf';c=canvas.Canvas(str(pdf),pagesize=(1191,842))
    c.setTitle(design['name']+' - 原创尺寸设计 A1')
    c.setFont('STSong-Light',30);c.drawString(48,784,design['name'])
    c.setFont('STSong-Light',15)
    intro=['原创尺寸设计 A1 / 所有尺寸 mm / 本图先于加工轮廓冻结',
           '外形 270 × 210 × 280；名义板厚 3；54 块板件；双抽屉各六格，行程 80。',
           '设计路线：底座 / 两侧板 / 背板 / 中层 / 操作台 / 四滑轨 → 双抽屉 → 分格与拉手 → 顶部配件。',
           '连接：板件厚 3；槽厚 3.15；16 mm 榫对应 16.2 mm 长槽；12 mm 榫对应 12.2 mm 长槽。',
           '装配坐标：X 左右，Y 向后，Z 向上。plane=xy/xz/yz；xz 厚度朝 -Y，其余分别 +Z/+X。',
           '抽屉底面 Z=15/111；侧壁 Z=18..90 / 114..186；导向中心 Z=52/148，Y=-40。',
           '抽屉槽 Y=-55..45，总长100，宽3.6，端半径1.8；关闭和伸出80时螺杆相对Y=-40/40。',
           '抽屉侧壁与机壳内壁间隔6；底板左右余量2；滑轨上表面Z=15/111，托住底板。',
           '工具杯 76 × 86 × 63；浅托盘 76 × 86 × 25；6挂钩；双排线缆梳；180 mm有效刻度。',
           '每个部件后续图给出包围尺寸及局部坐标原点；全部孔槽、榫、开口的绝对坐标详见 dimensions.json。',
           '尺寸 JSON 是本图的配套特征表，不是加工 SVG。后续重建脚本独立解释这些工程图元。',
           '红色虚示矩形为开口切除，蓝色为内孔，灰色为附加榫；图示接缝线不是额外切割线。',
           '待验证：实测板厚、切缝、五金选型、强度、承重、抗倾覆、设备工作幅面和实际加工参数。',
           '600 × 400 mm 是测试排板尺寸；本图不授权或触发机器加工。两小时长测保持暂停。']
    for i,line in enumerate(intro):c.drawString(48,738-i*37,line)
    c.setFont('Helvetica',10);c.drawString(48,40,'A1 / ORIGINAL DESIGN / DIMENSION SPECIFICATION BEFORE CAD RECONSTRUCTION');c.showPage()
    for page in range(math.ceil(len(design['parts'])/4)):
        c.setFont('STSong-Light',19);c.drawString(40,804,f'部件平面分解图 A1 - {page+1:02} / 14')
        for index,p in enumerate(design['parts'][page*4:page*4+4]):
            col=index%2;row=index//2;x=40+col*580;y=435-row*386
            c.setStrokeColorRGB(.8,.83,.85);c.setLineWidth(.5);c.rect(x,y-17,553,365)
            b=bounds(p);w=b[2]-b[0];h=b[3]-b[1];scale=min(445/w,239/h)
            c.setFont('STSong-Light',14);c.setFillColorRGB(.12,.2,.28);c.drawString(x+12,y+326,p['id']+' / '+p['name'])
            c.setFont('Helvetica',10);c.drawString(x+12,y+307,f'{w:g} x {h:g} x 3 | plane {p["plane"]} | origin {p["origin_mm"]}')
            ox=x+65-b[0]*scale;oy=y+51-b[1]*scale
            c.saveState();c.translate(ox,oy);c.scale(scale,scale);c.setLineWidth(.55/scale)
            c.setStrokeColorRGB(.1,.13,.18);draw_shape(c,p['body'])
            c.setStrokeColorRGB(.45,.48,.5)
            for s in p['tabs']:draw_shape(c,s)
            c.setStrokeColorRGB(.05,.35,.7)
            for s in p['holes']:draw_shape(c,s)
            c.setStrokeColorRGB(.8,.2,.2)
            for s in p['notches']:draw_shape(c,s)
            c.setStrokeColorRGB(.5,.2,.1);c.setFillColorRGB(.35,.24,.15)
            for s in p['marks']:
                if s['type']=='line':c.line(*s['points'][0],*s['points'][1])
                elif s['type']=='text':
                    c.setFont('Helvetica',s['height']);c.drawString(s['x'],s['y'],s['text'])
            c.restoreState()
            # Independent dimension lines, always outside the silhouette.
            left=ox+b[0]*scale;right=ox+b[2]*scale;bottom=oy+b[1]*scale;top=oy+b[3]*scale
            c.setStrokeColorRGB(.3,.4,.5);c.line(left,bottom-13,right,bottom-13);c.line(left-16,bottom,left-16,top)
            for q in (left,right):c.line(q,bottom-17,q,bottom-9)
            for q in (bottom,top):c.line(left-20,q,left-12,q)
            c.setFont('Helvetica',9);c.drawCentredString((left+right)/2,bottom-25,f'{w:.2f}')
            c.saveState();c.translate(left-24,(bottom+top)/2);c.rotate(90);c.drawCentredString(0,0,f'{h:.2f}');c.restoreState()
            c.setFont('STSong-Light',10);c.drawString(x+12,y+8,f'附加榫 {len(p["tabs"])} / 开口 {len(p["notches"])} / 内孔槽 {len(p["holes"])} / 刻线与文字 {len(p["marks"])}')
        c.setFont('STSong-Light',10);c.drawString(40,22,'配套尺寸表 dimensions.json 定义每个特征的局部 x / y / w / h / r 或控制点；打印缩放不作为测量依据。');c.showPage()
    c.save()
    print(json.dumps({'blueprint':str(pdf),'parts':54,'frozen':False},ensure_ascii=False))


def freeze():
    folder=ROOT/'blueprint'
    manifest={'stage':'A - independent design before reconstruction','design_revision':'A1',
              'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file() and p.name!='frozen-manifest.json'}}
    if (folder/'frozen-manifest.json').exists():raise RuntimeError('ALREADY_FROZEN')
    (folder/'frozen-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':
    import sys
    freeze() if '--freeze' in sys.argv else make_blueprint()
