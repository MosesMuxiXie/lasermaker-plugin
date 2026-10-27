"""Build the original product's deliverable geometry and self-contained previews."""
import csv
import json
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from lasermaker_agent.geometry import object_bounds,contours,preflight,export_svg,export_dxf
from lasermaker_agent.store import json_bytes,digest
from lasermaker_agent.tank import mesh_part,part_stock,assembled_bounds
from lasermaker_agent.workstation import build_workstation,drawer_state
from prepare_tank import preview,write_stl

ROOT=Path(__file__).resolve().parents[1]/'examples/original-workstation'


def color(pid):
    if pid.startswith('D1'):return [186,144,91]
    if pid.startswith('D2'):return [154,177,164]
    if pid.startswith('H'):return [155,105,68]
    if pid.startswith(('C','R')):return [194,156,99]
    if pid.startswith('U'):return [204,178,134]
    if pid.startswith('T'):return [175,183,143]
    return [214,196,165]


def explode(pid):
    if pid=='B00':return [0,0,-35]
    if pid in ('B01','B02'):return [-60 if pid=='B01' else 60,0,20]
    if pid=='B03':return [0,65,10]
    if pid=='B04':return [0,0,60]
    if pid=='B05':return [0,0,15]
    if pid.startswith('D'):
        k=int(pid.split('-')[1]);x=-45 if k==2 else 45 if k==3 else 0
        return [x,-75-(28 if k in (5,6,7,8) else 0),20 if k>=9 else 0]
    if pid.startswith('H'):return [0,20,70]
    if pid.startswith(('C','U','T','R')):return [0,0,100 if pid.startswith(('U','T')) else 70]
    return [0,0,0]


def sheet_png(design,path,title):
    w,h=design['sheet_mm'];s=2
    im=Image.new('RGB',(int(w*s+80),int(h*s+130)),'#fafaf6');d=ImageDraw.Draw(im)
    f=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',14);t=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    d.text((35,18),title,font=t,fill='#263b47');d.rectangle((40,70,40+w*s,70+h*s),outline='#bbc5cc')
    for o in design['objects']:
        for c in contours(o):
            pts=c+([c[0]] if o['closed'] else [])
            if len(pts)>1:d.line([(40+x*s,70+y*s) for x,y in pts],fill={'score':'#c64739','engrave':'#3669b3'}.get(o['role'],'#243342'),width=1)
        if o['role']=='cut_outer':
            b=object_bounds(o);d.text((42+b[0]*s,72+b[1]*s),o['part_id'],font=f,fill='#288399')
    d.text((35,h*s+92),'黑：切割  红：描线  蓝：雕刻 / 尺寸 mm，缩略图不用来测量',font=f,fill='#526473');im.save(path)


def write_viewer(model):
    # Reuse the already tested WebGL renderer, replacing only its product data,
    # camera framing and labels. No external libraries or network assets.
    base=Path(__file__).resolve().parents[1]/'examples/sherman-tank/三维装配.html'
    html=base.read_text(encoding='utf-8');data=[]
    for p in model['parts']:
        data.append({'id':p['id'],'name':p['name'],'v':[round(v,6) for tri in mesh_part(p)[0] for q in tri for v in q],
                     'color':[v/255 for v in color(p['id'])],'offset':explode(p['id']),'drawer':p['group'].startswith('drawer-')})
    start=html.index('const parts=');end=html.index(';\nconst canvas=',start)
    html=html[:start]+'const parts='+json.dumps(data,separators=(',',':'))+html[end:]
    for before,after in [
        ('坦克装配模型','原创工具站装配模型'),('谢尔曼风格拼装坦克','原创双抽屉桌面工具站'),
        ('198 × 90 × 78 mm · 名义板厚 3 mm · 39 块板件 + 直径 6 mm、长 12 mm 木圆棒','270 × 210 × 280 mm · 名义板厚 3 mm · 54 块板件 · 双抽屉行程 80 mm'),
        ('可旋转的三维坦克板件装配模型','可旋转、展开和打开抽屉的原创工具站模型'),
        ('木圆棒列入装配清单，网格不包含外购件。','五金、负载与抗倾覆待实物验证；网格仅含木板。'),
        ('vec3(10.,0.,40.+65.*spread)','vec3(0.,0.,140.+30.*spread)'),
        ('-r.z/500.','-r.z/1000.'),('zoom=.011','zoom=.0046'),('zoom=.011;','zoom=.0046;'),
        ('yaw=.7','yaw=2.45'),
        ('window.tankViewer','window.workstationViewer')]:html=html.replace(before,after)
    html=html.replace('<button id="reset">','<label>抽屉伸出<input id="travel" type="range" min="0" max="80" step="1" value="0"></label><button id="reset">')
    html=html.replace("const amount=document.getElementById('explode');","const amount=document.getElementById('explode'),travel=document.getElementById('travel');")
    html=html.replace('p.offset.map(v=>v*Number(amount.value))','p.offset.map((v,i)=>v*Number(amount.value)-(i===1&&p.drawer?Number(travel.value):0))')
    html=html.replace('amount.oninput=draw;','amount.oninput=draw;travel.oninput=draw;')
    html=html.replace('amount.value=0;draw()','amount.value=0;travel.value=0;draw()')
    (ROOT/'三维装配.html').write_text(html,encoding='utf-8')


def fixtures():
    objects=[]
    def poly(pid,pts,role='cut_outer',suffix='outer'):
        objects.append({'id':pid+'-'+suffix,'part_id':pid,'role':role,'closed':True,'points':pts})
    def rectangle(pid,x,y,w,h,role='cut_outer',suffix='outer'):
        poly(pid,[[x,y],[x+w,y],[x+w,y+h],[x,y+h]],role,suffix)
    rectangle('F01',6,6,154,38)
    for k,slot in enumerate((3,3.05,3.1,3.15,3.2,3.25,3.3)):
        x=15+k*20;rectangle('F01',x,12,slot,16,'cut_inner','fit-'+str(k))
        # Short binary score labels distinguish candidates without tiny text.
        for j in range(k+1):objects.append({'id':f'F01-code-{k}-{j}','part_id':'F01','role':'score','closed':False,'points':[[x+j*.55,33],[x+j*.55,36]]})
    poly('F02',[[6,52],[36,52],[36,74],[29,74],[29,82],[13,82],[13,74],[6,74]])
    # Stepped rail setup gauge: base Z=0 to rail-bottom12 / upper108.
    for n,x in enumerate((45,78)):
        poly('F0'+str(n+3),[[x,52],[x+24,52],[x+24,64],[x+12,64],[x+12,160],[x,160]])
        objects.append({'id':f'F0{n+3}-12','part_id':f'F0{n+3}','role':'score','closed':False,'points':[[x,64],[x+10,64]]})
    return {'units':'mm','sheet_mm':[180,170],'minimum_web_mm':2.99,'material':{'thickness_mm':3,'kerf_mm':None,'fit_validated':False},'objects':objects}


def main():
    model=build_workstation(ROOT/'blueprint')
    (ROOT/'assembly-source.json').write_bytes(json_bytes(model))
    views=ROOT/'preview';views.mkdir(exist_ok=True);meshes=ROOT/'meshes';meshes.mkdir(exist_ok=True)
    for name,state,expanded in [('assembled',model,False),('exploded',model,True),('open',drawer_state(model,80),False)]:
        preview(state,views,expanded,title='原创双抽屉工具站 · '+{'assembled':'闭合','exploded':'分解装配','open':'双抽屉伸出 80 mm'}[name],
                subtitle='54 块原创板件 | 270 × 210 × 280 mm | 先画分解图，再按图重建',color_func=color,explode_func=explode)
        generated=views/('exploded' if expanded else 'assembled')
        if name=='open':
            generated.with_suffix('.png').replace(views/'open.png');generated.with_suffix('.svg').replace(views/'open.svg')
    # Restore closed view after the reusable renderer's fixed output name.
    preview(model,views,title='原创双抽屉工具站 · 闭合',subtitle='54 块原创板件 | 270 × 210 × 280 mm | 五金与实物配合待验证',color_func=color,explode_func=explode)
    write_viewer(model)
    triangles=[];bom=[];scad=['// Original workstation - millimetres - 54 independent wood solids.']
    for p in model['parts']:
        mesh,area=mesh_part(p);triangles+=mesh;write_stl(meshes/(p['id']+'.stl'),mesh)
        shape=part_stock(p);points=[];paths=[]
        for ring in (shape.exterior,*shape.interiors):
            coords=list(ring.coords)[:-1];paths.append(list(range(len(points),len(points)+len(coords))));points.extend(coords)
        scad.append(f'// {p["id"]} {p["name"]}\nmultmatrix({json.dumps(p["transform"])}) linear_extrude(height=3) polygon(points={json.dumps(points)},paths={json.dumps(paths)});')
        b=object_bounds(p['objects'][0]);bom.append({'id':p['id'],'name':p['name'],'sheet':p['sheet']+1,'quantity':1,
            'width_mm':round(b[2]-b[0],4),'height_mm':round(b[3]-b[1],4),'thickness_mm':3,'area_mm2':round(area,4),'group':p['group']})
    write_stl(ROOT/'workstation-assembled.stl',triangles)
    (ROOT/'workstation.scad').write_text('\n'.join(scad)+'\n',encoding='utf-8')
    with (ROOT/'零件清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(bom[0]));writer.writeheader();writer.writerows(bom)
    for i,doc in enumerate(model['sheets']):
        folder=ROOT/f'sheet-{i+1}';folder.mkdir(exist_ok=True)
        (folder/'design.json').write_bytes(json_bytes(doc))
        (folder/'drawing.svg').write_text(export_svg(doc),encoding='utf-8');(folder/'drawing.dxf').write_bytes(export_dxf(doc))
        sheet_png(doc,views/f'sheet-{i+1}.png',f'第 {i+1} 张 / 600 × 400 mm / 原创工具站')
    coupon=fixtures();folder=ROOT/'fixtures';folder.mkdir(exist_ok=True)
    (folder/'design.json').write_bytes(json_bytes(coupon));(folder/'drawing.svg').write_text(export_svg(coupon),encoding='utf-8');(folder/'drawing.dxf').write_bytes(export_dxf(coupon))
    sheet_png(coupon,views/'fixtures.png','独立试切片与滑轨定位尺 / 180 × 170 mm')
    report={'part_count':54,'sheet_count':len(model['sheets']),'object_count':sum(len(s['objects']) for s in model['sheets']),
        'bounds_mm':assembled_bounds(model),'sheets':[preflight(s) for s in model['sheets']],'fixtures':preflight(coupon),
        'blueprint_sha256':model['blueprint_sha256'],'sheet_design_sha256':[digest(s) for s in model['sheets']],
        'triangles':len(triangles),'geometry_passed':all(preflight(s)['geometry_passed'] for s in [*model['sheets'],coupon]),
        'machine_validated':False,'physical_fit_verified':False,'two_hour_soak':'deferred by user'}
    (ROOT/'geometry-report.json').write_bytes(json_bytes(report));print(json.dumps({k:v for k,v in report.items() if k not in ('sheets','fixtures','sheet_design_sha256')},ensure_ascii=False))


if __name__=='__main__':main()
