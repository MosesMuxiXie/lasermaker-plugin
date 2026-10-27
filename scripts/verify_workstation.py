"""Bounded real MCP drawing and Windows native-file acceptance for the product."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.store import json_bytes,digest

ROOT=Path(__file__).resolve().parents[1]/'examples/original-workstation'


def verify_completed_native(folder,state,target):
    """Never treat an old success JSON as current without its underlying bytes."""
    folder=Path(folder)
    record=json.loads((folder/'native-verification.json').read_text(encoding='utf-8'))
    native=state.get('native') or {}
    def require(condition):
        if not condition:raise ValueError('STALE_NATIVE_ACCEPTANCE_EVIDENCE: '+folder.name)
    require(not state.get('native_external_change') and not state.get('native_parameters_dirty'))
    require(record.get('project_id')==state['project_id'])
    require(record.get('revision')==state['revision']==native.get('revision'))
    require(record.get('design_digest')==digest(target)==native.get('design_digest') and state['design']==target)
    require(record.get('source_sha256')==hashlib.sha256((folder/'design.json').read_bytes()).hexdigest())
    require(native.get('verification',{}).get('reopen_verified') and native.get('source_scope',{}).get('complete'))
    path=(folder/'project'/native['path']).resolve()
    require(path.is_relative_to((folder/'project').resolve()) and path.is_file())
    require(hashlib.sha256(path.read_bytes()).hexdigest()==native.get('sha256')==record.get('native_sha256'))
    delivery=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
    require(delivery.get('native_current') and delivery.get('process_settings_verified'))
    for key,relative in delivery['artifacts'].items():
        output=(folder/relative).resolve()
        require(output.is_relative_to(folder.resolve()) and output.is_file())
        require(hashlib.sha256(output.read_bytes()).hexdigest()==delivery['sha256'][key])
    return record


def fit_view(project):
    from ctypes import wintypes
    from lasermaker_agent.store import ProjectStore
    from lasermaker_agent.windows_driver import WindowsDriver,desktop_lock
    with desktop_lock():
        binding=ProjectStore(project).read()['gui_binding'];driver=WindowsDriver()
        w=driver.assert_document(binding['document_name'],expected_pid=binding['pid']);box=w.rectangle()
        buttons=[c for c in driver._controls(w,'Button') if c.rectangle().top>box.bottom-90 and 295<c.rectangle().left-box.left<355]
        if len(buttons)!=1:raise RuntimeError('FIT_VIEW_CONTROL_AMBIGUOUS')
        with driver._foreground(w.handle):
            driver._select_all(w);driver._input_click(w,buttons[0].rectangle())
            r=wintypes.RECT(box.left+145,box.top+550,box.left+149,box.top+554);driver._input_click(w,r)
        return {'view_only':True,'fit_control_clicked':True,'fit_all_verified':False,'document_name':binding['document_name']}


async def session_run(runtime,phase,case=None):
    entries=sorted(ROOT.glob('sheet-*/design.json'))+[ROOT/'fixtures/design.json'];results=[]
    if case is not None:
        entries=[p for p in entries if p.parent.name==case]
        if not entries:raise ValueError('UNKNOWN_WORKSTATION_SHEET')
    async with stdio_client(StdioServerParameters(command=str(runtime.resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize();tools=await session.list_tools();assert len(tools.tools)==17
            for source in entries:
                folder=source.parent;project=folder/'project';name=folder.name
                async def call(tool,args,expect_error=False):
                    result=await session.call_tool(tool,args)
                    print(json.dumps({'phase':phase,'sheet':name,'tool':tool,'ok':not result.isError}),flush=True)
                    if expect_error:
                        assert result.isError
                        return [c.text for c in result.content if c.type=='text']
                    if result.isError:raise RuntimeError(f'{name}/{tool}: {result.content}')
                    assert result.structuredContent is not None
                    return result.structuredContent
                target=json.loads(source.read_text(encoding='utf-8'))
                if phase=='draw':
                    if not (project/'project.json').exists():
                        await call('create_project',{'root':str(project),'name':'原创工具站-'+name,'design':{**target,'objects':[]}})
                    state=await call('open_project',{'root':str(project)})
                    objects=state['design']['objects'];assert objects==target['objects'][:len(objects)]
                    receipts=[]
                    for start in range(len(objects),len(target['objects']),40):
                        batch=target['objects'][start:start+40]
                        args={'root':str(project),'request_id':f'original-A1-draw-{start:04}',
                              'expected_revision':state['revision'],'operations':[{'op':'add','object':o} for o in batch]}
                        state=await call('apply_design_ops',args)
                        receipts.append({'start':start,'count':len(batch),'revision':state['revision']})
                    # Also replay the exact original first transaction when
                    # resuming after an interruption immediately after commit.
                    all_receipts=[]
                    for start in range(0,len(target['objects']),40):
                        original={'root':str(project),'request_id':f'original-A1-draw-{start:04}',
                            'expected_revision':start//40,
                            'operations':[{'op':'add','object':o} for o in target['objects'][start:start+40]]}
                        replay=await call('apply_design_ops',original);assert replay['revision']==start//40+1
                        all_receipts.append({'start':start,'count':min(40,len(target['objects'])-start),'revision':replay['revision']})
                    state=await call('resume_project',{'root':str(project)})
                    assert state['design']==target and not state['pending_ui_operations']
                    before=digest(state['design']);revision=state['revision']
                    rejected=await call('apply_design_ops',{'root':str(project),'request_id':'original-A1-limit-rejected',
                        'expected_revision':revision,'operations':[{'op':'delete','ids':['nonexistent']}]*1001},True)
                    after=await call('open_project',{'root':str(project)})
                    assert after['revision']==revision and digest(after['design'])==before
                    checkpoint=await call('checkpoint',{'root':str(project),'label':'按冻结设计图逐批重建完成；等待跨进程恢复'})
                    record={'revision':revision,'objects':len(target['objects']),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                        'request_replay_verified':True,'rejected_1001_ops_without_mutation':True,'limit_error':rejected,
                        'batches':all_receipts,
                        'batches_this_run':receipts,'checkpoint':checkpoint}
                    (folder/'mcp-drawing.json').write_bytes(json_bytes(record));continue
                state=await call('resume_project',{'root':str(project)})
                assert state['design']==target and not state['pending_ui_operations']
                pf=await call('preflight',{'root':str(project)});assert pf['geometry_passed'],pf
                base={'root':str(project),'expected_revision':state['revision']}
                def args(label,**kw):return {**base,'request_id':'original-A1-native-'+label,**kw}
                if (folder/'native-verification.json').exists():
                    # Completed sheets retain all their actual evidence, never regenerate.
                    results.append(verify_completed_native(folder,state,target));continue
                imported=await call('import_design',args('import'))
                processes=[]
                for color,mode,speed in [('#000000','cut',10),('#ff0000','score',100),('#0000ff','engrave',100)]:
                    if color not in {l['color'] for l in imported['layers']}:continue
                    process={'mode':mode,'speed_mm_s':speed,'power_max_percent':15}
                    if mode!='engrave':process['power_min_percent']=13
                    await call('set_layer_process',args('process-'+mode,color=color,process=process));processes.append((color,process))
                b=pf['bounds_mm'];size=[b[2]-b[0],b[3]-b[1]]
                saved=await call('save_native',args('save',filename='native/original-workstation.lcpx'))
                reopened=await call('reload_and_verify',args('reopen',path=saved['path'],expected_size_mm=size))
                checks=[]
                for color,process in processes:checks.append(await call('verify_layer_process',args('verify-'+process['mode'],color=color,process=process)))
                sha=hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()
                view=await asyncio.to_thread(fit_view,project)
                assert hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest()==sha
                capture=await call('capture_app',{'root':str(project),'filename':'evidence/reopened.png'})
                await call('checkpoint',{'root':str(project),'label':'跨 MCP 重启恢复；原生保存及重开尺寸、工艺已读回'})
                delivery=await call('export_delivery',{'root':str(project)})
                assert delivery['native_current'] and delivery['process_settings_verified']
                from lasermaker_agent.sample import registration_plan
                from lasermaker_agent.geometry import export_dxf,ROLES
                registration=folder/'stage-registration.json';registration.write_bytes(json_bytes(registration_plan(target)))
                delivery['artifacts']['stage_registration']=str(registration)
                delivery['sha256']['stage_registration']=hashlib.sha256(registration.read_bytes()).hexdigest()
                for role in ROLES:
                    path=folder/f'stage-{role}.dxf';path.write_bytes(export_dxf(target,[role]))
                    delivery['artifacts']['dxf_'+role]=str(path)
                    delivery['sha256']['dxf_'+role]=hashlib.sha256(path.read_bytes()).hexdigest()
                delivery['artifacts']={k:Path(v).relative_to(folder).as_posix() for k,v in delivery['artifacts'].items()}
                (folder/'delivery.json').write_bytes(json_bytes(delivery))
                record={'sheet':name,'objects':len(target['objects']),'revision':state['revision'],'project_id':state['project_id'],
                    'design_digest':digest(target),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'mcp_restart_resumed':True,
                    'import':imported,'reopened':reopened,'process_readbacks':checks,'view':view,'capture':capture,
                    'native_current':True,'native_sha256':sha,'machine_validated':False,'physical_fit_verified':False,
                    'process_parameters':'test readback only - not validated for any material or device'}
                (folder/'native-verification.json').write_bytes(json_bytes(record));results.append(record)
                await call('close_verified_document',args('close'))
                (ROOT/'native-verification.json').write_bytes(json_bytes(results))
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--phase',choices=['draw','native'],required=True)
    p.add_argument('--case');args=p.parse_args();asyncio.run(session_run(args.runtime,args.phase,args.case))
