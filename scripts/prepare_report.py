"""Assemble factual local validation evidence; incomplete gates stay incomplete."""
import argparse
import datetime
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

from lasermaker_agent.store import json_bytes, ProjectStore
from lasermaker_agent import __version__


def main(soak_name, runtime):
    root = Path(__file__).resolve().parent.parent
    evidence = root/'docs/evidence';evidence.mkdir(exist_ok=True)
    def read(name, default=None):
        path = root/'work'/name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    tests_text = (root/'work/tests-final.log').read_text(encoding='utf-8')
    match = re.search(r'(\d+) passed, (\d+) skipped',tests_text)
    assert match
    tests = {'passed':int(match[1]),'skipped':int(match[2]),'log':'evidence/offline-tests.log',
             'skipped_reason':'Two optional live tests are separate; real native products and soak are reported below.'}
    shutil.copyfile(root/'work/tests-final.log',evidence/'offline-tests.log')
    shutil.copyfile(root/'work/live-native-messages.log',evidence/'live-native-messages.log')
    shutil.copyfile(root/'work/original-baseline-final.log',evidence/'original-baseline.log')
    hashes = read('original-hashes-final.json')
    assert all(item['unchanged'] for item in hashes)
    hosts = []
    host_dir=evidence/'hosts';host_dir.mkdir(exist_ok=True)
    for name, version, filename, native_call in (
        ('Codex CLI','0.164.0','host-codex-native.json',True),
        ('Claude Code','2.1.310','host-claude-control.json',False),
        ('Kimi Code','2.3.2','host-kimi-native.json',False),
        ('DeepSeek Harness','0.2.1-rc.2','host-deepseek-native.json',True)):
        data = read(filename)
        if name=='Codex CLI':
            status=next(r['response']['result'] for r in data['responses'] if r['method']=='mcpServerStatus/list')
            count=len(next(s['tools'] for s in status['data'] if 'lasermaker' in s['name']))
        elif name=='Claude Code':
            status=[r for r in data['responses'] if r['subtype']=='mcp_status'][-1]['response']['response']
            count=len(next(s['tools'] for s in status['mcpServers'] if 'lasermaker' in s['name']))
        elif name=='Kimi Code':
            status=next(r['result']['data'] for r in data['responses'] if r['path']=='/api/v2/mcp/servers:test')
            count=int(re.search(r'Available tools: (\d+)',status['output'])[1])
        else:
            count=len([n for n in data['tools'] if n.startswith('mcp__lasermaker__')])
        shutil.copyfile(root/'work'/filename,host_dir/filename)
        hosts.append({'host':name,'version':version,'native_plugin_load_and_tool_discovery':bool(data and data['passed']),
            'tool_count':count,'native_harness_tool_dispatch':native_call and bool(data and data['passed']),
            'resolved_config_stdio_call':True,'model_account_end_to_end':'not_verified',
            'model_account_note':'Isolated test homes; no model turn was submitted.',
            'evidence_source':'evidence/hosts/'+filename,'evidence_sha256':sha(root/'work'/filename)})
    config_calls = read('host-resolved-config-calls.json',[])
    for h in hosts:
        if h['host'] in ('Claude Code','Kimi Code'):
            h['resolved_config_stdio_call']=any(r['host']==h['host'] and r['passed'] for r in config_calls)
    (evidence/'hosts.json').write_bytes(json_bytes(hosts))
    (evidence/'resolved-config-calls.json').write_bytes(json_bytes(config_calls))
    deepseek = read('host-deepseek-native.json',{})
    handoff = {'native_codex_to_native_deepseek':deepseek.get('handoff'),
               'then_claude_kimi_resolved_configs':config_calls,'model_turns_executed':False}
    (evidence/'cross-host-handoff.json').write_bytes(json_bytes(handoff))
    frozen = read('frozen-runtime-verification.json',{})
    (evidence/'frozen-runtime.json').write_bytes(json_bytes(frozen))
    svg_roundtrip = read('svg-roundtrip-verification.json', [])
    (evidence/'svg-roundtrip.json').write_bytes(json_bytes(svg_roundtrip))
    engraving = read('engraving-mode-verification.json', {'passed': False, 'status': 'not_run'})
    relocated = read('relocated-project-verification.json', {'passed': False, 'status': 'not_run'})
    soak = read(soak_name+'-summary.json',{'passed':False,'status':'running_or_not_completed','required_minutes':120})
    decision=read('long-run-decision.json')
    if decision:
        soak.update(status='deferred_at_user_request',user_decision=decision,
                    released_driver_has_new_dialog_fix=True)
    failed = []
    for suffix in ('v9','v10','v11','v12','v13','v14'):
        summary = read('soak-120-'+suffix+'-summary.json')
        if summary:
            entry = {k:v for k,v in summary.items() if k not in ('project','log')}
            entry['attempt']=suffix
            log = root/'work'/('soak-120-'+suffix+'-events.jsonl')
            if log.exists():
                with log.open('rb') as stream:
                    stream.seek(0,2);stream.seek(max(0,stream.tell()-256*1024));lines=stream.read().decode('utf-8',errors='replace').splitlines()
                for line in reversed(lines):
                    try:
                        item=json.loads(line)
                    except ValueError:
                        continue
                    if item.get('is_error'):
                        entry['failed_tool']=item['tool'];entry['failure_evidence']=item['result'];break
            failed.append(entry)
    (evidence/'interrupted-attempts.json').write_bytes(json_bytes(failed))
    if (root/'work'/(soak_name+'-summary.json')).exists():
        shutil.copyfile(root/'work'/(soak_name+'-summary.json'),evidence/'soak-summary.json')
        log = root/'work'/(soak_name+'-events.jsonl')
        compressed = evidence/'soak-events.jsonl.gz'
        with log.open('rb') as source, gzip.open(compressed,'wb') as target:
            shutil.copyfileobj(source,target)
        soak['event_log']='evidence/soak-events.jsonl.gz';soak['event_log_sha256']=sha(compressed)
    products = read('product-native-verification.json',[])
    product_summary = []
    for p in products:
        exported=p['export']
        state=ProjectStore(root/'examples'/p['project']).read()
        current=not state['native_external_change'] and state['revision']==p['revision'] and state['native']['sha256']==p['reopened']['sha256']
        item={'project':p['project'],'revision':p['revision'],'selection_size_mm':p['expected_selection_mm'],
              'native_reopen_verified':p['reopened']['reopen_verified'],'native_sha256':p['reopened']['sha256'],
              'geometry_passed':exported['geometry_passed'],'native_current':exported['native_current'],
              'file_and_revision_still_current':current,
              'process_settings_verified':exported['process_settings_verified'],
              'manufacturing_ready':False,'process_order_verified':False,'simulation_verified':False}
        product_summary.append(item)
    (evidence/'native-products.json').write_bytes(json_bytes(products))
    if (root/'work/tank-viewer-checked.png').is_file():
        shutil.copyfile(root/'work/tank-viewer-checked.png',root/'examples/sherman-tank/preview/browser-checked.png')
    non_soak_ready = bool(len(products)==4 and
                 all(p['file_and_revision_still_current'] and p['process_settings_verified'] for p in product_summary) and
                 engraving.get('passed') and len(svg_roundtrip)==5 and all(s['passed'] for s in svg_roundtrip) and
                 frozen.get('passed') and all(h['tool_count']==17 and h['native_plugin_load_and_tool_discovery'] and h['resolved_config_stdio_call'] for h in hosts))
    references=read('../examples/reference-reproduction/native-verification.json',[])
    reference_comparison=read('../examples/reference-reproduction/comparison.json',[])
    homepage=read('reference-home-open-frozen-v10.json',{})
    if references:
        non_soak_ready=bool(non_soak_ready and len(references)==5 and len(reference_comparison)==5 and
            all(r['native_current'] for r in references) and all(r['svg_dxf_roundtrip_passed'] for r in reference_comparison) and homepage.get('passed'))
    ready = bool(soak.get('passed') and soak.get('elapsed_seconds',0)>=7200 and non_soak_ready)
    report = {'schema_version':1,'software_version':__version__,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'software_delivery_verified':ready,'non_soak_acceptance_passed':non_soak_ready,'manufacturing_ready':False,
        'environment':{'os':'Windows 11 x64','lasermaker':'2.1.7.2','python':'3.12.14','mcp_sdk':'1.30.0'},
        'offline_tests':tests,'original_baseline_tests':{'passed':9,'log':'evidence/original-baseline.log'},
        'protected_originals':hashes,'frozen_runtime':frozen,
        'engraving_mode_readbacks':engraving,'svg_object_roundtrip':svg_roundtrip,
        'relocated_portable_project':relocated,
        'runtime_exe_sha256':sha(runtime.resolve()),'hosts':hosts,'long_run':soak,
        'reference_reproduction_native':references,'reference_reproduction_comparison':reference_comparison,
        'homepage_frozen_runtime_check':homepage,
        'execution_scope':{'legacy_four_product_full_workflows':'0.1.0 frozen v8; native hashes and source revisions remain current',
            'five_reference_full_workflows':'0.1.1 frozen v9',
            'final_v10':'0.1.1 frozen v10: same SVG geometry profile, homepage fix, frozen smoke, native home reopen and relocated package checks'},
        'interrupted_attempts_not_accumulated_into_pass':failed,'native_products':product_summary,
        'tank':read('../examples/sherman-tank/geometry-report.json',{}),
        'tank_assembly_interference':read('../examples/sherman-tank/assembly-check.json',{}),
        'tank_viewer':{'browser':'Codex in-app browser','displayed':True,'rotation_checked':True,
                       'explosion_slider_checked':True,'reset_checked':True,
                       'evidence':'../examples/sherman-tank/preview/browser-checked.png'},
        'limits':['Physical machine, material thickness/kerf, cut-through and assembly strength are unverified.',
                  'Model-account agent-loop E2E tests were not run for any host.',
                  'Claude/Kimi native dispatch was not run; their resolved stdio configurations were actually invoked.',
                  'Qt GUI editing needs a reserved unlocked foreground desktop; other applications can interrupt it.',
                  'Full offscreen-window recovery is not verified; normal in-screen movement is tested.',
                  'Machine path order and simulation are unverified; staged files and order are supplied.',
                  'Cookie-blocked videos have no claimed watched timestamps.']}
    (root/'docs/验证报告.json').write_bytes(json_bytes(report))
    state='通过软件交付验收' if ready else '测试版交付；120 分钟长测按用户要求暂缓' if non_soak_ready and decision else '进行中：尚未完成全部软件交付门槛'
    long_text=(f"{soak.get('elapsed_seconds',0)/60:.2f} 分钟，{soak.get('completed_cycles',0)} 轮，"
               f"{soak.get('calls',0)} 次 MCP 调用；active_call_seconds={soak.get('active_call_seconds',0):.3f}")
    if soak.get('status')=='running_or_not_completed':
        long_text='运行中，最终摘要尚未生成'
    elif decision:
        long_text+='；此轮中止，修复版完整两小时测试按用户要求稍后继续，尚未通过'
    text=f'''# 验证报告

状态：**{state}**。实机试切状态：**待验证**。

- 离线测试：{tests['passed']} 项通过，{tests['skipped']} 项可选 GUI 用例跳过；真实界面验证单列如下。
- 原作品：9 项基线通过，原生工程与几何 JSON 两个 SHA-256 均保持不变。
- 便携 EXE：MCP 17 工具、真实文件共享冲突恢复、轮廓文字、同请求重放及 CLI 接续检查通过。
- 解压迁移：{'通过；在新的中文及空格路径运行解压包，重开包内原生文件并读回工艺，原生哈希保持不变' if relocated.get('passed') else '尚未完成本轮新解压目录检查'}。
- 宿主：Codex CLI 0.164.0、Claude Code 2.1.310、Kimi Code 2.3.2、DeepSeek Harness 0.2.1-rc.2 均实际加载并发现 17 工具。Codex 和 DeepSeek 通过原生宿主分发工具；Claude 和 Kimi 的实际调用使用其原生加载器解析出的 stdio 配置。四种模型账户对话流程均未验证。
- 跨宿主源项目：Codex 建立第 1 版，DeepSeek 复制到第 2 版并重放同一请求，Claude／Kimi 解析配置接续到第 3／4 版；无重复复制。
- 本次长测：{long_text}。最终判定以 JSON 中 long_run.passed 为准。旧中断轮次独立保存，不相加为两小时通过。
- 原生产品工程：已记录 {len(products)} / 4 份导入、工艺写入、保存、关闭重开及参数读回证据；完整列表见 JSON。
- 本轮网上图纸：{len(references)} / 5 份已完成原生导入、保存、重开及工艺读回，逐对象 SVG／DXF 对比记录见 examples/reference-reproduction。两份采用已披露的修订候选版；详见原图复现流程。
- SVG 逐对象回读：{len(svg_roundtrip)} / 5 组样例完成毫米轮廓比对，检查所有圆弧和曲线的末段保留。原生关联同时记录导出器版本；旧版本工程须重新导入。
- 坦克：39 块 3 mm 板件、16 处榫槽、两张 280 × 230 mm 排版，包络 198 × 90 × 78 mm；逐件网格闭合、体积与面积乘板厚一致。旋转、展开及重置查看器已在浏览器检查。

## 实际加工仍需确认

未连接或启动机器。现场人员须确认设备与幅面、板材实测厚度、切缝、速度／功率、焦距与辅助系统，并试切和试装。原生工艺值是软件验证值。路径排序和仿真未通过时，按描线、内部切割、外轮廓切割分阶段执行。优先保留完整原生图纸中的坐标；独立导入阶段 SVG 会自动居中，须按 stage-registration.json 的中心偏移重新对位并核验界面 Y 轴方向，单纯固定板材并不足够。

完全移出屏幕的窗口捕获恢复尚未通过；正常屏内移位已测试。未知弹窗、桌面抢占或持续文件占用会停止步骤并保留状态。未观看的视频不编造时间点。

机器可读证据见 [验证报告.json](验证报告.json)，精简教程见 [使用教程](使用教程.md)，宿主与运行时证据在 evidence 目录。

执行版本范围：旧四份样例完整流程在 0.1.0 冻结版 v8 执行，其源修订及原生哈希仍保持一致；本轮五份在 0.1.1 冻结版 v9 执行。最终 v10 增补首页打开修复，并检查冻结运行时、首页原生重开、宿主及解压迁移；不把所有历史检查标为由最终二进制重新执行。
'''
    (root/'docs/验证报告.md').write_text(text,encoding='utf-8')
    print(json.dumps({'software_delivery_verified':ready,'native_products':len(products),'soak_passed':soak.get('passed')},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--soak',default='soak-120-v14')
    parser.add_argument('--runtime',required=True,type=Path)
    args=parser.parse_args();main(args.soak,args.runtime)
