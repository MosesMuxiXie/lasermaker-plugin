"""Build the concise Chinese reference-test index and material-separated files."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from lasermaker_agent.geometry import export_svg,export_dxf,object_bounds,preflight
from lasermaker_agent.sample import registration_plan
from lasermaker_agent.store import ProjectStore,json_bytes,file_hash


def main(runtime):
    root=Path(__file__).resolve().parents[1];base=root/'examples/reference-reproduction'
    cases=json.loads((base/'reconstruction.json').read_text(encoding='utf-8'))
    comparisons=json.loads((base/'comparison.json').read_text(encoding='utf-8'))
    native=json.loads((base/'native-verification.json').read_text(encoding='utf-8'))
    assert len(cases)==len(comparisons)==len(native)==5
    assert all(r['svg_dxf_roundtrip_passed'] for r in comparisons)
    names={'vases':'七款试管花瓶','toggle':'木制拨动开关','tray':'贴木皮托盘','clamps':'木制弹簧夹','notebook':'木封面笔记本'}
    notes={
      'vases':'作者使用 3 mm 桦木胶合板、16 × 150 mm 带口沿试管。原图槽宽 2.8 mm、榫宽 3.2 mm 已含作者实测 0.2 mm 切缝补偿，不应重复补偿。原样版有两块小榫片距主体约 0.002 mm；候选版经有记录的平移和布尔合并连接，约 1.60 mm 的切割线变化单列，不宣称走刀原样一致。',
      'toggle':'作者按 3 mm 材料设计，模板已含 0.1 mm 切缝补偿。保留弹簧、分层机构、销及拆装小工具；未添加第二份切缝偏移。作者原 PDF 的组装链接误指向宝箱，实际组装请使用上列拨动开关页面。',
      'tray':'作者使用 6 mm 杨木胶合板和樱桃木皮；标注成品约 230 × 110 × 25 mm。底板原图宽约 228.7 mm，不能按成品宽度擅自拉伸。完整原生工程用于软件验收；加工应使用本例 materials 下按胶合板／木皮分开的文件，木皮厚度及工艺现场确认。',
      'clamps':'原图 12 个零件：夹体和转动垫块各按三层构造，另需橡皮筋等。作者未给出可直接用于本机的材料厚度和激光配方；保留原轮廓，按实测板材试装。',
      'notebook':'原图是两块封面、各 16 个装订孔和非零填充雕刻图。SVG 无毫米单位，按 CSS 96 px/in 与配套 PDF 核对；孔距约 12.6448 mm，与正文约写的 12.6 mm 分别保留。雕刻自交按非零填充正则化，并在候选版删除 4 个面积小于 10⁻⁸ mm² 的微小碎片；原样版与修订日志保留。'}
    # The mixed-material tray must not become a single production-material job.
    tray=base/'tray';design=json.loads((tray/'design.json').read_text(encoding='utf-8'))
    plywood_parts={o['part_id'] for o in design['objects'] if o['role']=='cut_outer' and object_bounds(o)[2]<300}
    assert len(plywood_parts)==5
    material_index=[];materials=tray/'materials';materials.mkdir(exist_ok=True)
    for name,parts,thickness in (('plywood-6mm',plywood_parts,6),
                                ('veneer-measure-thickness',{o['part_id'] for o in design['objects']}-plywood_parts,None)):
        subset=copy.deepcopy(design);subset['objects']=[o for o in subset['objects'] if o['part_id'] in parts]
        subset['material']={'name':name,'thickness_mm':thickness,'kerf_mm':None,'fit_validated':False}
        assert preflight(subset)['geometry_passed']
        (materials/(name+'.json')).write_bytes(json_bytes(subset))
        (materials/(name+'.svg')).write_text(export_svg(subset),encoding='utf-8')
        (materials/(name+'.dxf')).write_bytes(export_dxf(subset))
        (materials/(name+'-registration.json')).write_bytes(json_bytes(registration_plan(subset)))
        material_index.append({'name':name,'parts':len(parts),'objects':len(subset['objects']),'thickness_mm':thickness,
                               'geometry_passed':True,'manufacturing_ready':False})
    (materials/'index.json').write_bytes(json_bytes(material_index))
    lines=['# 五份网上图纸复现测试','',
        '本轮不进行两小时压力测试。五份加工候选版均实际完成 LaserMaker 导入、尺寸核对、保存、磁盘重开及工艺读回。', '',
        '原图来自 Maker Design Lab 的八份公开项目，记录随机种子后抽取五份。原图及衍生图纸按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 保留署名、非商业与相同方式共享要求；软件 MIT 许可不改变图纸许可。', '',
        '先看 [原图／复现对照图](comparison-contact-sheet.png)、[绘制流程](../../docs/原图复现流程.md) 和 [数值报告](comparison.json)。图中为便于看清加粗预览线条，加工文件仍用实际中心线。', '',
        '精度口径：原图切割曲线采样与原样复现的偏差小于 0.01 mm；候选源对 SVG 实际回读最大偏差约 '
        f'{max(r["svg_max_deviation_mm"] for r in comparisons):.6f} mm。DXF 先按 0.005 mm 目标弦误差离散，再检查回读序列化误差。原生工程核对总尺寸与图层参数，尚未逐节点解析 .lcpx。以上均不代表机器精度。', '',
        '花瓶与笔记本保留了原样版的预检问题，并另给修订候选版；不要将“候选版通过”解释为“作者原图原样通过”。黑色用于切割，蓝色用于填充雕刻，测试参数不作为生产配方。', '']
    summary=[]
    for case,comparison in zip(cases,comparisons):
        key=case['id'];folder=base/key;store=ProjectStore(folder/'project');state=store.resume()
        assert not state['native_external_change'] and state['native']['verification']['reopen_verified']
        pending=[json.loads(p.read_text(encoding='utf-8')) for p in (folder/'project/operations').glob('*.json')]
        assert all(p['status']=='complete' for p in pending)
        assert file_hash(folder/'original/source.svg')==case['source_sha256']==case['source']['sha256']
        delivery=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
        assert delivery['native_current'] and delivery['process_settings_verified']
        for name,path in delivery['artifacts'].items():
            assert (folder/path).is_file()
            if name in delivery['sha256']:assert file_hash(folder/path)==delivery['sha256'][name]
        links=[]
        for item,label in (('native','原生 .lcpx'),('svg','SVG'),('dxf','DXF'),('source','可编辑毫米源')):
            links.append(f'[{label}](<{key}/{delivery["artifacts"][item]}>)')
        s=case['preflight'];count=s['part_count'];objects=s['object_count']
        lines.extend([f'## {names[key]}','',f'[作者原图与装配页面]({case["source"]["page"]}) · [未改动原 SVG](<{key}/original/source.svg>)', '',
            ' · '.join(links),'',f'加工候选版：{count} 个平面零件、{objects} 个对象。总选区尺寸：'
            f'{s["bounds_mm"][2]-s["bounds_mm"][0]:.5f} × {s["bounds_mm"][3]-s["bounds_mm"][1]:.5f} mm。','',
            notes[key],'',f'[原样毫米源](<{key}/original-reconstruction.json>) · [原样预检](<{key}/original-preflight.json>) · '
            f'[修订记录](<{key}/repair-audit.json>) · [对象比对](<{key}/comparison.json>) · [原生读回](<{key}/native-verification.json>)',''])
        if key=='tray':lines.extend(['[分材料文件](tray/materials/index.json)：plywood-6mm 与 veneer-measure-thickness；木皮未标定厚度。',''])
        if key=='notebook':lines.extend(['[冻结版 v10 首页重开与清晰截图](notebook/homepage-open-verification.json)。失败的额外预览请求被确认取消，原日志及人工核对记录保留在 project/evidence，未标为成功。',''])
        summary.append({'id':key,'source_sha256':case['source_sha256'],'raw_preflight_passed':case['original_preflight']['geometry_passed'],
            'candidate_preflight_passed':True,'native_saved_reopened':True,'native_sha256':state['native']['sha256'],
            'source_revision':state['revision'],'svg_objects_checked':comparison['svg_objects_checked'],
            'svg_max_deviation_mm':comparison['svg_max_deviation_mm'],'dxf_contours_checked':comparison['dxf_contours_checked'],
            'disclosed_repair_count':len(case['repair_audit']),'manufacturing_ready':False})
    lines.extend(['## 现场加工前','',
        '确认幅面、材料实厚、已有切缝补偿、焦距和速度／功率。先雕刻，再内切，最后外轮廓；阶段文件独立导入会居中，须按 stage-registration.json 配准。花瓶排版宽约 837 mm，不能直接假定适合当前机器。', '',
        '没有发送或启动机器，没有进行实物试装、深度／烧蚀测量、实机走刀仿真或 120 分钟长测。模型账户对话流程仍未验证。', ''])
    (base/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    report={'schema_version':1,'software_version':'0.1.1','selected_ids':[c['id'] for c in cases],
        'cases':summary,'all_five_native_workflows_passed':True,'all_five_candidate_svg_dxf_checks_passed':True,
        'source_cutline_faithful_cases':4,'disclosed_cutline_modified_case':'vases',
        'runtime_sha256':file_hash(runtime),'manufacturing_ready':False,'long_run':'deferred_by_user',
        'calibration':json.loads((base/'calibration.json').read_text(encoding='utf-8')),
        'full_native_five_runtime':'0.1.1 frozen v9','final_homepage_fix_runtime':'0.1.1 frozen v10',
        'homepage_fix':json.loads((root/'work/reference-home-open-frozen-v10.json').read_text(encoding='utf-8'))}
    (base/'verification-summary.json').write_bytes(json_bytes(report))
    print(json.dumps({'five_native_passed':True,'svg_max_deviation_mm':max(c['svg_max_deviation_mm'] for c in summary),
                      'objects_checked':sum(c['svg_objects_checked'] for c in summary)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    main(parser.parse_args().runtime.resolve())
