"""Render the CAD references/candidates, then create a static visual contact sheet."""
import argparse
import copy
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont,ImageOps
from lasermaker_agent.geometry import export_svg,preflight


def main(sharp):
    root=Path(__file__).resolve().parents[1];base=root/'examples/reference-reproduction'
    cases=json.loads((base/'reconstruction.json').read_text(encoding='utf-8'))
    ET.register_namespace('','http://www.w3.org/2000/svg')
    pairs=[]
    for case in cases:
        folder=base/case['id'];preview=folder/'preview';preview.mkdir(exist_ok=True)
        source=ET.parse(folder/'original/source.svg').getroot()
        stroke_mm={'vases':1.0,'toggle':.3,'tray':.7,'clamps':.3,'notebook':.5}[case['id']]
        ids=set(case['cut_source_ids'])|set(case['engrave_source_ids'])
        graphics={'path','rect','circle','ellipse','line','polyline','polygon','text','flowRoot','use','image'}
        def filter_tree(e,in_defs=False):
            for child in list(e):
                tag=child.tag.rsplit('}',1)[-1]
                defs=in_defs or tag=='defs'
                if not defs and tag in graphics and child.get('id') not in ids:e.remove(child)
                else:
                    if child.get('id') in ids:
                        is_fill=child.get('id') in case['engrave_source_ids']
                        child.set('style',child.get('style','')+(';fill:#236ab5;stroke:none' if is_fill else f';fill:none;stroke:#161c25;stroke-width:{stroke_mm}mm'))
                    filter_tree(child,defs)
        filter_tree(source)
        original_svg=preview/'reference-machining.svg'
        ET.ElementTree(source).write(original_svg,encoding='utf-8',xml_declaration=True)
        design=json.loads((folder/'design.json').read_text(encoding='utf-8'))
        raw=json.loads((folder/'original-reconstruction.json').read_text(encoding='utf-8'))
        (preview/'raw-reproduction.svg').write_text(export_svg(raw),encoding='utf-8')
        candidate=ET.fromstring(export_svg(design))
        for group in candidate:
            if group.get('id')=='engrave':group.set('fill','#236ab5');group.set('stroke','none')
            elif group.get('id') in ('cut_inner','cut_outer'):
                group.set('stroke','#161c25');group.set('stroke-width',str(stroke_mm*96/25.4))
        candidate_svg=preview/'candidate-filled-preview.svg'
        ET.ElementTree(candidate).write(candidate_svg,encoding='utf-8',xml_declaration=True)
        for label,svg in (('reference',original_svg),('candidate',candidate_svg)):
            target=preview/(label+'.png')
            script="const sharp=require(process.argv[1]);sharp(process.argv[2],{limitInputPixels:150000000}).resize({width:1800}).flatten({background:'#ffffff'}).png().toFile(process.argv[3]).catch(e=>{console.error(e);process.exit(1)})"
            subprocess.run(['node','-e',script,str(sharp),str(svg),str(target)],check=True,timeout=60)
        bbox=preflight(design)['bounds_mm'];sheet=design['sheet_mm']
        views=[]
        for label in ('reference','candidate'):
            im=Image.open(preview/(label+'.png')).convert('RGB')
            crop=im.crop((max(0,(bbox[0]-3)/sheet[0]*im.width),max(0,(bbox[1]-3)/sheet[1]*im.height),
                          min(im.width,(bbox[2]+3)/sheet[0]*im.width),min(im.height,(bbox[3]+3)/sheet[1]*im.height)))
            views.append(ImageOps.contain(crop,(840,310)))
        pairs.append((case,views))
    canvas=Image.new('RGB',(1840,210+len(pairs)*390),'#f3f5f7');draw=ImageDraw.Draw(canvas)
    font_path='C:/Windows/Fonts/msyh.ttc';title=ImageFont.truetype(font_path,38);font=ImageFont.truetype(font_path,24);small=ImageFont.truetype(font_path,20)
    draw.text((40,25),'五份网上平面图纸：原图与复现对照',font=title,fill='#152238')
    draw.text((42,88),'Maker Design Lab · CC BY-NC-SA 4.0 | 原图坐标重建；修订见逐例 audit；不以图片判断加工精度',font=small,fill='#526074')
    draw.text((50,145),'原图加工图形（排除页眉说明）',font=font,fill='#152238')
    draw.text((970,145),'复现／加工候选版',font=font,fill='#152238')
    names={'vases':'七款试管花瓶','toggle':'木制拨动开关','tray':'贴木皮托盘','clamps':'木制弹簧夹','notebook':'木封面笔记本'}
    for i,(case,views) in enumerate(pairs):
        y=205+i*390
        draw.rounded_rectangle((30,y,1810,y+370),radius=16,fill='white')
        suffix=' · 有明确记录的修订' if case['repair_audit'] else ' · 保留原图几何'
        draw.text((50,y+12),names[case['id']]+suffix,font=font,fill='#152238')
        for x,im in zip((45,950),views):canvas.paste(im,(x+(840-im.width)//2,y+55+(310-im.height)//2))
    canvas.save(base/'comparison-contact-sheet.png')
    print('Five source/candidate preview pairs rendered and contact sheet saved')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sharp-module',type=Path,required=True)
    main(parser.parse_args().sharp_module)
