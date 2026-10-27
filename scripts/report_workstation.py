"""Assemble final evidence and product index only from verified current files."""
import hashlib
import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from lasermaker_agent import __version__
from lasermaker_agent.store import ProjectStore,json_bytes,digest
from lasermaker_agent.workstation import load_frozen_spec
from verify_workstation import verify_completed_native

BASE=Path(__file__).resolve().parents[1];ROOT=BASE/'examples/original-workstation'


def main():
    spec=load_frozen_spec(ROOT/'blueprint');geometry=json.loads((ROOT/'geometry-report.json').read_text(encoding='utf-8'))
    model=json.loads((ROOT/'assembly-source.json').read_text(encoding='utf-8'))
    assert model['drawing_profile']=='engineering-up-to-svg-down-v1'
    assert geometry['geometry_passed'] and len(model['parts'])==54
    native=[];cards=[];hashes={}
    for folder in [*(ROOT/f'sheet-{i}' for i in range(1,5)),ROOT/'fixtures']:
        target=json.loads((folder/'design.json').read_text(encoding='utf-8'))
        state=ProjectStore(folder/'project').resume()
        record=verify_completed_native(folder,state,target);native.append(record)
        assert not [p for p in (folder/'project/operations').glob('*.json') if json.loads(p.read_text(encoding='utf-8'))['status']!='complete']
        drawing=json.loads((folder/'mcp-drawing.json').read_text(encoding='utf-8'))
        assert drawing['request_replay_verified'] and drawing['rejected_1001_ops_without_mutation']
        assert sum(b['count'] for b in drawing['batches'])==len(target['objects'])
        delivery=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
        def link(key,label):return f'<a href="{html.escape(folder.name+"/"+delivery["artifacts"][key],quote=True)}">{label}</a>'
        cards.append(f'<article><h3>{folder.name}</h3><p>{len(target["objects"])} 个对象 · 原生重开与工艺读回通过</p><p>'+ ' / '.join([link('native','LaserMaker 原生工程'),link('svg','SVG'),link('dxf','DXF')])+f'</p><a href="{folder.name}/stage-registration.json">分阶段注册说明</a></article>')
    sourcecheck=json.loads((ROOT/'design-verification.json').read_text(encoding='utf-8'))
    edits=json.loads((ROOT/'edit-probe/report.json').read_text(encoding='utf-8'))
    limits=json.loads((ROOT/'limit-probe.json').read_text(encoding='utf-8'))
    assert edits['exact_source_restored'] and edits['new_mcp_process_resumed'] and limits['objects_reached']==20000
    hosts={}
    for name,file in [('Codex','host-codex-native.json'),('Claude Code','host-claude-control.json'),('Kimi Code','host-kimi-native.json'),('DeepSeek Harness','host-deepseek-native.json')]:
        value=json.loads((BASE/'work'/file).read_text(encoding='utf-8'));assert value['passed'],(name,value.get('error'))
        hosts[name]={'native_loader_and_tool_discovery_passed':True,'model_account_end_to_end':'unverified'}
        (ROOT/'audit'/file).write_bytes(json_bytes(value))
    config_calls=json.loads((BASE/'work/host-resolved-config-calls.json').read_text(encoding='utf-8'))
    assert len(config_calls)==2 and all(r['passed'] and r['doctor']['version']==__version__ for r in config_calls)
    suites=ET.parse(BASE/'work/publish-tests.xml').getroot().findall('testsuite')
    assert suites and sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)==0
    total=sum(int(s.get('tests',0)) for s in suites);skipped=sum(int(s.get('skipped',0)) for s in suites)
    assert total-skipped>=87
    (ROOT/'audit/publish-tests.log').write_bytes((BASE/'work/publish-tests.log').read_bytes())
    runtime=BASE/'work/portable-workstation-v11/lasermaker-agent/lasermaker-agent.exe'
    report={'plugin_version':__version__,'runtime_sha256':hashlib.sha256(runtime.read_bytes()).hexdigest(),
        'product':spec['name'],'parts':54,'sheet_count':4,'product_object_count':987,'native_projects_verified':len(native),
        'drawing_profile':model['drawing_profile'],'blueprint_unchanged':True,'max_plan_deviation_mm':sourcecheck['max_plan_deviation_mm'],
        'mating_pairs':len(sourcecheck['mating']['matched_tab_slot_pairs']),'drawer_travel_mm':[0,80],
        'continuous_wood_interference_passed':not sourcecheck['continuous_travel_check']['stationary_vs_swept_intersections'],
        'automated_tests':{'passed':total-skipped,'skipped_optional_live':skipped,'log':'audit/publish-tests.log'},
        'maximum_objects_test':limits,'fine_edit_and_recovery':edits,'hosts':hosts,
        'host_call_coverage':'Codex/DeepSeek native tool calls; Claude/Kimi host-resolved stdio configs; no model turns',
        'native_verification':native,'two_hour_soak':'deferred by explicit user instruction',
        'machine_validated':False,'physical_fit_verified':False,'manufacturing_ready':False,
        'unverified':['machine bed and controller','physical stock thickness and kerf','guide hardware and slot fit','cut order / simulation','load / wear / tipping'],
        'fixed_findings':['SVG engineering Y direction and engraved face','exact Arc reflection and unequal-axis scale','stale native-success cache','resumed draw replay audit'],
        'prior_attempts':'superseded/ - retained, excluded from current acceptance'}
    (ROOT/'verification-report.json').write_bytes(json_bytes(report))
    (ROOT/'native-verification.json').write_bytes(json_bytes(native))
    text='''# 原创双抽屉工具站：极限功能测试

从零编制平面分解图，再按冻结的尺寸规格独立重建。成品 270 × 210 × 280 mm，名义 3 mm 板材，54 个零件，4 张 600 × 400 mm 排板、987 个实际绘图对象；另有独立试切片与定位尺。

- [打开产品与加工文件索引](产品与加工索引.html)
- [15 页平面分解设计图](blueprint/平面分解设计图-A1.pdf) · [特征尺寸表](blueprint/特征尺寸表.csv) · [冻结的尺寸规格](blueprint/dimensions.json)
- [可旋转、展开、开闭抽屉的离线三维装配](三维装配.html)
- [装配说明与现场确认项目](装配说明.md) · [零件清单](零件清单.csv)
- [可编辑的装配及轮廓源文件](assembly-source.json) · [OpenSCAD](workstation.scad) · [装配 STL](workstation-assembled.stl)
- [完整软件验证报告](verification-report.json) · [独立尺寸、接头和运动检查](design-verification.json) · [20,000 对象边界检查](limit-probe.json)

4 张产品排板及 1 张辅助试片均经过真实 MCP 导入、尺寸读回、工艺设置、保存并关闭后按准确路径重开核验。下方每个目录的 `delivery.json` 指向当前有效原生工程、SVG/DXF、分阶段文件和检查报告。

数值几何计算容差为 0.01 mm，界面尺寸读回容差为 0.05 mm，均不代表激光机加工精度。软件核验通过，尚未完成材料试切、五金试装、承重／抗倾覆或实机加工。图层中的速度和功率只用于验证参数落盘，不作为加工建议。两小时长测继续暂停。

旧方向测试及弹窗中断记录保存在 `superseded/`，不用于当前交付。软件为 0.1.2，四种宿主已作无模型账户的插件加载／工具发现核验；Codex 与 DeepSeek 原生调用、Claude 与 Kimi 解析配置后的 stdio 调用均另有记录，模型对话端到端仍未验证。

复建：在源码目录安装 `.[dev,design]` 后，先使用新文件夹编制／检查／冻结下一版本设计图，再运行 `scripts/prepare_workstation.py`、`scripts/check_workstation.py`、`scripts/verify_workstation.py`。A1 图纸已冻结，作者脚本默认拒绝覆盖，不要删除冻结文件绕过保护。
'''
    (ROOT/'README.md').write_text(text,encoding='utf-8')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>原创工具站 · 设计与加工交付</title>
<style>body{margin:0;background:#f2f3ef;color:#253b40;font:16px/1.6 system-ui}main{max-width:1180px;margin:auto;padding:32px}h1{font-size:32px;margin-bottom:8px}a{color:#17687d}header,article,section{background:white;border:1px solid #d6ded8;border-radius:12px;padding:22px;margin:16px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.grid article{margin:0}img{width:100%;border-radius:8px}iframe{width:100%;height:740px;border:0}.tag{color:#396b55}small{color:#65726c}</style>
<main><header><p class="tag">ORIGINAL PRODUCT / LASERMAKER AGENT 0.1.2</p><h1>双抽屉桌面工具站</h1><p>54 块板件 · 270 × 210 × 280 mm · 4 张板 · 987 个加工对象</p><p>先画分解图，冻结尺寸，再独立重建；120 组榫槽、双抽屉 80 mm 连续行程和 20,000 对象软件边界测试。</p><p><a href="blueprint/平面分解设计图-A1.pdf">平面分解图 PDF</a> / <a href="blueprint/特征尺寸表.csv">特征尺寸表</a> / <a href="装配说明.md">装配说明</a> / <a href="verification-report.json">验证报告</a></p><small>几何与软件核验通过。材料、切缝、五金、承重和实机加工仍待现场确认；参数是读回测试值。两小时长测暂停。</small></header>
<section><h2>离线三维装配</h2><iframe src="三维装配.html" title="可旋转、展开和开闭抽屉的三维模型"></iframe><a href="三维装配.html">独立打开三维模型</a></section>
<div class="grid"><article><img src="preview/assembled.png" alt="闭合装配"></article><article><img src="preview/open.png" alt="抽屉伸出80毫米"></article></div>
<section><h2>当前加工文件</h2><p>原生工程均已保存、关闭并按准确路径重新打开，尺寸和对应颜色工艺读回通过。加工顺序未作实机仿真；使用分阶段文件时按注册说明对齐。</p><div class="grid">CARDS</div></section>
<section><h2>继续设计</h2><p><a href="assembly-source.json">毫米轮廓与装配源</a> / <a href="零件清单.csv">零件清单</a> / <a href="workstation.scad">OpenSCAD</a> / <a href="workstation-assembled.stl">多实体 STL</a></p><p><a href="design-verification.json">独立图纸对照与运动检查</a> / <a href="edit-probe/report.json">精细编辑及重启恢复</a> / <a href="limit-probe.json">对象上限测试</a></p></section></main></html>'''
    (ROOT/'产品与加工索引.html').write_text(page.replace('CARDS',''.join(cards)),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('plugin_version','parts','sheet_count','product_object_count','native_projects_verified','manufacturing_ready')},ensure_ascii=False))


if __name__=='__main__':main()
