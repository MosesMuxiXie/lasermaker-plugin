"""Generate exact tank sheets, individual solids and an offline 3-D viewer."""
import csv
import json
import math
import struct
import base64
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from lasermaker_agent.geometry import object_bounds, contours, preflight
from lasermaker_agent.service import Service
from lasermaker_agent.store import json_bytes, digest
from lasermaker_agent.tank import build_tank, mesh_part, part_stock, world_point, assembled_bounds


def write_stl(path, triangles):
    with path.open('wb') as stream:
        stream.write(b'LaserMaker original tank fixture; units mm'.ljust(80, b'\0'))
        stream.write(struct.pack('<I', len(triangles)))
        for a, b, c in triangles:
            normal = [(b[(i+1)%3]-a[(i+1)%3])*(c[(i+2)%3]-a[(i+2)%3])-
                      (b[(i+2)%3]-a[(i+2)%3])*(c[(i+1)%3]-a[(i+1)%3]) for i in range(3)]
            length = math.sqrt(sum(v*v for v in normal))
            assert length > 1e-12
            stream.write(struct.pack('<12fH', *[v/length for v in normal], *a, *b, *c, 0))


def explode_offset(pid):
    if pid.startswith('W'):
        return [0, -42 if int(pid[1:])<=8 else 42, 0]
    if pid.startswith('T'):
        return [0, -25 if pid=='T01' else 25, 0]
    if pid.startswith('R'):
        k = int(pid[1:])
        return [0, 0, 65+8*k] if k<=6 else [0, 0, 130 if k<9 else 91]
    if pid=='H02':
        return [0, 0, 45]
    if pid in ('H03', 'H04'):
        return [0, -12 if pid=='H03' else 12, 12]
    return [0, 0, 0]


def color_for(pid):
    if pid.startswith('T'):
        return [67, 74, 66]
    if pid.startswith('W'):
        return [162, 157, 118]
    if pid.startswith('R'):
        return [149, 163, 109]
    return [182, 174, 128]


def preview(model, root, exploded=False, *, title=None, subtitle=None, color_func=color_for, explode_func=explode_offset):
    faces = []
    # View from front/right/top. Same world coordinates as STL; only preview offsets vary.
    view = [1, -1, 1.25]
    def project(p):
        return [(p[0]+p[1])*.76, .4*p[0]-.4*p[1]-.64*p[2]]
    for part in model['parts']:
        shift = explode_func(part['id']) if exploded else [0, 0, 0]
        for tri in mesh_part(part)[0]:
            tri = [[p[i]+shift[i] for i in range(3)] for p in tri]
            a, b, c = tri
            n = [(b[(i+1)%3]-a[(i+1)%3])*(c[(i+2)%3]-a[(i+2)%3])-
                 (b[(i+2)%3]-a[(i+2)%3])*(c[(i+1)%3]-a[(i+1)%3]) for i in range(3)]
            length = math.sqrt(sum(x*x for x in n))
            dot = sum(n[i]*view[i] for i in range(3))/length
            if dot <= 0:
                continue
            shade = .62+.38*min(1, dot/math.sqrt(sum(x*x for x in view)))
            color = tuple(round(v*shade) for v in color_func(part['id']))
            depths = [sum(p[i]*view[i] for i in range(3)) for p in tri]
            faces.append((depths, [project(p) for p in tri], color))
    points = [p for _, tri, _ in faces for p in tri]
    bounds = [min(p[i] for p in points) for i in (0, 1)]+[max(p[i] for p in points) for i in (0, 1)]
    scale = min(1050/(bounds[2]-bounds[0]), 600/(bounds[3]-bounds[1]))
    screen = lambda p: (75+(p[0]-bounds[0])*scale, 100+(p[1]-bounds[1])*scale)
    pixels = np.full((800, 1200, 3), [242, 242, 237], dtype=np.uint8)
    zbuffer = np.full((800, 1200), -np.inf)
    # Depth interpolation avoids painter-order artifacts on large overlapping plates.
    for depths, tri, color in faces:
        (x1, y1), (x2, y2), (x3, y3) = [screen(p) for p in tri]
        lo_x, hi_x = max(0, int(min(x1,x2,x3))), min(1199, math.ceil(max(x1,x2,x3)))
        lo_y, hi_y = max(0, int(min(y1,y2,y3))), min(799, math.ceil(max(y1,y2,y3)))
        if hi_x<lo_x or hi_y<lo_y:
            continue
        denominator = (y2-y3)*(x1-x3)+(x3-x2)*(y1-y3)
        if abs(denominator)<1e-10:
            continue
        yy, xx = np.mgrid[lo_y:hi_y+1,lo_x:hi_x+1]
        xx, yy = xx+.5, yy+.5
        a = ((y2-y3)*(xx-x3)+(x3-x2)*(yy-y3))/denominator
        b = ((y3-y1)*(xx-x3)+(x1-x3)*(yy-y3))/denominator
        c = 1-a-b
        depth = a*depths[0]+b*depths[1]+c*depths[2]
        target = zbuffer[lo_y:hi_y+1,lo_x:hi_x+1]
        mask = (a>=-1e-8)&(b>=-1e-8)&(c>=-1e-8)&(depth>target)
        target[mask] = depth[mask]
        pixels[lo_y:hi_y+1,lo_x:hi_x+1][mask] = color
    for part in model['parts']:
        shift = explode_func(part['id']) if exploded else [0,0,0]
        for obj in part['objects']:
            if obj['role']!='score':
                continue
            for ring in contours(obj):
                if obj['closed']:
                    ring = ring+[ring[0]]
                points = [world_point(part,[x,y,3.01]) for x,y in ring]
                points = [[p[i]+shift[i] for i in range(3)] for p in points]
                for p,q in zip(points,points[1:]):
                    a,b = np.array(screen(project(p))),np.array(screen(project(q)))
                    samples = max(2,math.ceil(max(abs(b-a))*2))
                    f = np.linspace(0,1,samples)
                    xy = (a[None,:]+f[:,None]*(b-a)).astype(int)
                    valid = (xy[:,0]>=0)&(xy[:,0]<1200)&(xy[:,1]>=0)&(xy[:,1]<800)
                    xy,f = xy[valid],f[valid]
                    dp,dq = sum(p[i]*view[i] for i in range(3)),sum(q[i]*view[i] for i in range(3))
                    visible = dp+(dq-dp)*f>=zbuffer[xy[:,1],xy[:,0]]-.2
                    xy = xy[visible]
                    pixels[xy[:,1],xy[:,0]] = [75,78,53]
    image = Image.fromarray(pixels)
    draw = ImageDraw.Draw(image)
    title = title or ('谢尔曼风格 · 爆炸装配示意' if exploded else '谢尔曼风格 · 3 mm 板材拼装模型')
    subtitle = subtitle or '39 块切割件 + 1 根木圆棒 | 198 × 90 × 78 mm | 原创榫槽结构'
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 28)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 18)
    draw.text((48, 25), title, font=font, fill='#263728')
    draw.text((48, 744), subtitle, font=small, fill='#475747')
    name = 'exploded' if exploded else 'assembled'
    image.save(root/f'{name}.png')
    encoded = base64.b64encode((root/f'{name}.png').read_bytes()).decode('ascii')
    (root/f'{name}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><desc>Rasterized depth-correct assembly preview; use sheet SVG for machining.</desc><image width="1200" height="800" href="data:image/png;base64,{encoded}"/></svg>', encoding='utf-8')


def viewer(model, root):
    data = []
    for part in model['parts']:
        triangles, _ = mesh_part(part)
        vertices = [round(v, 7) for t in triangles for p in t for v in p]
        data.append({'id': part['id'], 'name': part['name'], 'v': vertices,
                     'color': [v/255 for v in color_for(part['id'])], 'offset': explode_offset(part['id'])})
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>坦克装配模型 · LaserMaker Agent</title><style>
body{margin:0;background:#eef0e9;color:#243627;font:16px system-ui}header{padding:20px 28px;background:#fff;border-bottom:1px solid #ccd2c5}h1{font-size:22px;margin:0 0 8px}p{margin:6px 0}canvas{width:100%;height:70vh;display:block;touch-action:none}section{padding:12px 28px}label{display:inline-flex;gap:12px;align-items:center;margin-right:24px}button{padding:8px 14px;background:#fff;border:1px solid #aebaa7;border-radius:4px;color:inherit}input{width:220px}small{color:#56634f}</style>
<header><h1>谢尔曼风格拼装坦克</h1><p>198 × 90 × 78 mm · 名义板厚 3 mm · 39 块板件 + 直径 6 mm、长 12 mm 木圆棒</p><small>拖动旋转，滚轮缩放。三维网格与切割源使用相同轮廓；实物榫槽配合尚待试切。</small></header>
<canvas id="c" aria-label="可旋转的三维坦克板件装配模型"></canvas><section><label>展开装配<input id="explode" type="range" min="0" max="1" step="0.01" value="0"></label><button id="reset">恢复视角</button><p id="status"></p></section>
<script>const parts=DATA;
const canvas=document.getElementById('c'),gl=canvas.getContext('webgl',{antialias:true});
if(!gl){document.getElementById('status').textContent='此浏览器未启用 WebGL，请查看 assembled.png、exploded.png 或使用 STL 查看器。';throw Error('WebGL unavailable')}
function shader(t,s){const v=gl.createShader(t);gl.shaderSource(v,s);gl.compileShader(v);if(!gl.getShaderParameter(v,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(v));return v}
const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,`attribute vec3 pos;attribute vec3 normal;uniform vec3 color;uniform vec3 shift;uniform float yaw;uniform float pitch;uniform float zoom;uniform float aspect;uniform float spread;varying vec3 vColor;void main(){vec3 p=pos+shift-vec3(10.,0.,40.+65.*spread);float a=cos(yaw),b=sin(yaw),d=cos(pitch),e=sin(pitch);vec3 q=vec3(a*p.x-b*p.y,b*p.x+a*p.y,p.z);vec3 r=vec3(q.x,d*q.z-e*q.y,e*q.z+d*q.y);gl_Position=vec4(r.x*zoom/aspect,r.y*zoom,-r.z/500.,1.);float light=.55+.45*abs(dot(normalize(normal),normalize(vec3(.7,-1.,1.5))));vColor=color*light;}`));
gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`precision mediump float;varying vec3 vColor;void main(){gl_FragColor=vec4(vColor,1.);}`));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
for(const p of parts){let out=[];for(let k=0;k<p.v.length;k+=9){let a=p.v.slice(k,k+3),b=p.v.slice(k+3,k+6),c=p.v.slice(k+6,k+9);let u=b.map((x,i)=>x-a[i]),v=c.map((x,i)=>x-a[i]);let n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];for(let j=0;j<3;j++)out.push(...p.v.slice(k+j*3,k+j*3+3),...n)}p.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,p.buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(out),gl.STATIC_DRAW);p.count=out.length/6;delete p.v}
const U=n=>gl.getUniformLocation(program,n);let yaw=.7,pitch=.65,zoom=.011,drag=null;const amount=document.getElementById('explode');
function draw(){const ratio=Math.min(2,devicePixelRatio||1),w=Math.round(canvas.clientWidth*ratio),h=Math.round(canvas.clientHeight*ratio);canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);gl.clearColor(.933,.941,.914,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.uniform1f(U('yaw'),yaw);gl.uniform1f(U('pitch'),pitch);gl.uniform1f(U('zoom'),zoom/(1.+Number(amount.value)*.85));gl.uniform1f(U('spread'),Number(amount.value));gl.uniform1f(U('aspect'),w/h);for(const p of parts){gl.bindBuffer(gl.ARRAY_BUFFER,p.buffer);const pos=gl.getAttribLocation(program,'pos'),n=gl.getAttribLocation(program,'normal');gl.enableVertexAttribArray(pos);gl.enableVertexAttribArray(n);gl.vertexAttribPointer(pos,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(n,3,gl.FLOAT,false,24,12);gl.uniform3fv(U('color'),p.color);gl.uniform3fv(U('shift'),p.offset.map(v=>v*Number(amount.value)));gl.drawArrays(gl.TRIANGLES,0,p.count)}}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(-1.4,Math.min(1.4,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];draw()};canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.002,Math.min(.03,zoom*Math.exp(-e.deltaY*.001)));draw()};amount.oninput=draw;document.getElementById('reset').onclick=()=>{yaw=.7;pitch=.65;zoom=.011;amount.value=0;draw()};window.onresize=draw;draw();document.getElementById('status').textContent=parts.length+' 块独立板件；木圆棒列入装配清单，网格不包含外购件。';window.tankViewer={partCount:parts.length,draw};
</script></html>'''
    (root/'三维装配.html').write_text(template.replace('DATA', json.dumps(data, separators=(',', ':'))), encoding='utf-8')


def sheet_preview(model, number, root):
    scale, margin = 4, 40
    image = Image.new('RGB', (1200, 1040), '#fafaf6')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14)
    title = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 24)
    at = lambda p:(margin+p[0]*scale,70+p[1]*scale)
    draw.text((40,20),f'第 {number+1} 张 · 280 × 230 mm · 零件编号仅作看图索引',font=title,fill='#263728')
    draw.rectangle([at((0,0)),at((280,230))],outline='#9da89c')
    for obj in model['sheets'][number]['objects']:
        for line in contours(obj):
            if obj['closed']:
                line=line+[line[0]]
            draw.line([at(p) for p in line],fill='#c83b36' if obj['role']=='score' else '#202d24',width=1)
    for part in model['parts']:
        if part['sheet']!=number:
            continue
        x,y=part['sheet_position_mm']
        draw.text(at((x+1,y+1)),part['id'],font=font,fill='#245f8e')
    image.save(root/f'sheet-{number+1}.png')


def main():
    root = Path(__file__).resolve().parent.parent/'examples/sherman-tank'
    root.mkdir(parents=True, exist_ok=True)
    model = build_tank()
    model['sheet_design_sha256']=[digest(sheet) for sheet in model['sheets']]
    (root/'assembly-source.json').write_bytes(json_bytes(model))
    preview_dir = root/'preview';preview_dir.mkdir(exist_ok=True)
    for exploded in (False, True):
        preview(model, preview_dir, exploded)
    for number in range(2):
        sheet_preview(model, number, preview_dir)
    viewer(model, root)
    meshdir = root/'meshes';meshdir.mkdir(exist_ok=True)
    triangles, scad, bom = [], ['// Original flat-pack tank; millimetres. Same polygonal contours as STL.'], []
    service = Service()
    for n, sheet in enumerate(model['sheets']):
        project = root/f'sheet-{n+1}/project'
        if not (project/'project.json').exists():
            service.call('create_project', {'root': str(project), 'name': f'坦克第 {n+1} 张板', 'design': sheet})
        else:
            assert service.call('open_project', {'root': str(project)})['design']==sheet, 'Existing source differs; preserve it before regeneration'
        result = service.call('export_delivery', {'root': str(project)})
        result['artifacts'] = {k: Path(v).relative_to(project.parent).as_posix() for k,v in result['artifacts'].items()}
        (project.parent/'delivery.json').write_bytes(json_bytes(result))
    for p in model['parts']:
        mesh, area = mesh_part(p);triangles.extend(mesh)
        write_stl(meshdir/f'{p["id"]}.stl', mesh)
        shape = part_stock(p)
        points, paths = [], []
        for ring in (shape.exterior, *shape.interiors):
            coords = list(ring.coords)[:-1]
            paths.append(list(range(len(points), len(points)+len(coords))))
            points.extend([[round(v, 8) for v in c] for c in coords])
        scad.append(f'// {p["id"]} {p["name"]}\ncolor({json.dumps([v/255 for v in color_for(p["id"])])}) multmatrix({json.dumps(p["transform"])}) linear_extrude(height=3) polygon(points={json.dumps(points)},paths={json.dumps(paths)});')
        b = object_bounds(next(o for o in p['objects'] if o['role']=='cut_outer'))
        bom.append({'id': p['id'], 'name': p['name'], 'sheet': p['sheet']+1, 'quantity': 1,
                    'width_mm': round(b[2]-b[0], 3), 'height_mm': round(b[3]-b[1], 3),
                    'thickness_mm': 3, 'planar_area_mm2': round(area, 3), 'attachment': p['attachment']})
    write_stl(root/'tank-assembled.stl', triangles)
    (root/'tank.scad').write_text('\n'.join(scad)+'\n', encoding='utf-8')
    with (root/'零件清单.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(bom[0]));writer.writeheader();writer.writerows(bom)
    report = {'source': 'assembly-source.json', 'part_count': len(model['parts']), 'joints': len(model['joints']),
              'sheet_design_sha256':model['sheet_design_sha256'],
              'assembled_bounds_mm': assembled_bounds(model), 'sheets': [preflight(s) for s in model['sheets']],
              'triangles': len(triangles), 'machine_validated': False, 'fit_validated': False,
              'note': 'Per-part manifold and volume checks run in tests/test_tank.py; assembled STL is a multi-solid visualization, not a fused manufacturing mesh.'}
    (root/'geometry-report.json').write_bytes(json_bytes(report))
    print(json.dumps({'parts': len(bom), 'triangles': len(triangles), 'bounds': report['assembled_bounds_mm'], 'root': str(root)}, ensure_ascii=False))


if __name__=='__main__':
    main()
