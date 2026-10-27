"""Five bounded real GUI workflows over the frozen MCP, with disclosed repairs."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.store import json_bytes
from lasermaker_agent.sample import registration_plan


def zoom_large_view(project,width):
    """View-only wheel events to the exact managed native window, never a job."""
    if width<=500:return {'wheel_ticks':0}
    import ctypes
    from ctypes import wintypes
    from lasermaker_agent.store import ProjectStore
    from lasermaker_agent.windows_driver import WindowsDriver,desktop_lock
    with desktop_lock():
        binding=ProjectStore(project).read()['gui_binding']
        driver=WindowsDriver()
        window=driver.assert_document(binding['document_name'],expected_pid=binding['pid'])
        rect=window.rectangle();x=rect.left+(rect.width()-320)//2;y=rect.top+(rect.height()+150)//2
        message=ctypes.windll.user32.SendMessageTimeoutW
        message.argtypes=[wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t,wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
        message.restype=ctypes.c_ssize_t
        with driver._foreground(window.handle):
            for _ in range(5):
                response=ctypes.c_size_t()
                if not message(window.handle,0x020A,((-120)&0xffff)<<16,(y<<16)|(x&0xffff),2,500,ctypes.byref(response)):
                    raise RuntimeError('VIEW_ZOOM_MESSAGE_TIMEOUT')
    return {'wheel_ticks':-5,'view_only':True,'target_document':binding['document_name']}


async def run(runtime):
    root=Path(__file__).resolve().parents[1]
    output=root/'examples/reference-reproduction'
    cases=json.loads((output/'reconstruction.json').read_text(encoding='utf-8'))
    results=[]
    async with stdio_client(StdioServerParameters(command=str(runtime.resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools)==17
            for case in cases:
                name=case['id'];folder=output/name;project=folder/'project'
                async def call(tool,args):
                    r=await session.call_tool(tool,args)
                    if r.isError:raise RuntimeError(f'{name}/{tool}: {r.content}')
                    assert r.structuredContent is not None
                    print(json.dumps({'case':name,'tool':tool,'ok':True}),flush=True)
                    return r.structuredContent
                original=json.loads((folder/'original-reconstruction.json').read_text(encoding='utf-8'))
                if not (project/'project.json').exists():
                    await call('create_project',{'root':str(project),'name':'原图复现测试-'+name,'design':original})
                    before=await call('preflight',{'root':str(project)})
                    assert before['geometry_passed']==case['original_preflight']['geometry_passed']
                    (folder/'mcp-original-preflight.json').write_bytes(json_bytes(before))
                ops=json.loads((folder/'repair-operations.json').read_text(encoding='utf-8'))
                if ops:
                    args={'root':str(project),'request_id':'ref5-disclosed-repair-v1','expected_revision':0,'operations':ops}
                    edited=await call('apply_design_ops',args)
                    assert await call('apply_design_ops',args)==edited
                state=await call('resume_project',{'root':str(project)})
                candidate=json.loads((folder/'design.json').read_text(encoding='utf-8'))
                assert state['design']==candidate
                if state['pending_ui_operations']:raise RuntimeError('UNRECONCILED_UI_OPERATION')
                preflight=await call('preflight',{'root':str(project)})
                assert preflight['geometry_passed']
                b=preflight['bounds_mm'];size=[b[2]-b[0],b[3]-b[1]]
                base={'root':str(project),'expected_revision':state['revision']}
                def args(label,**kw):return {**base,'request_id':'ref5-native-v1-'+label,**kw}
                imported=await call('import_design',args('import'))
                colors={l['color'] for l in imported['layers']}
                processes=[]
                for color,mode,speed in (('#000000','cut',10),('#0000ff','engrave',100)):
                    if color not in colors:continue
                    process={'mode':mode,'speed_mm_s':speed,'power_max_percent':15}
                    if mode=='cut':process['power_min_percent']=13
                    await call('set_layer_process',args('process-'+mode,color=color,process=process))
                    processes.append((color,process))
                saved=await call('save_native',args('save',filename='native/reference-reproduction.lcpx'))
                reopened=await call('reload_and_verify',args('reopen',path=saved['path'],expected_size_mm=size))
                readbacks=[]
                for color,process in processes:
                    readbacks.append(await call('verify_layer_process',args('verify-'+process['mode'],color=color,process=process)))
                viewport=await asyncio.to_thread(zoom_large_view,project,size[0])
                capture=await call('capture_app',{'root':str(project),'filename':'evidence/reopened.png'})
                await call('checkpoint',{'root':str(project),'label':'原图复现：尺寸及工艺磁盘读回'})
                delivery=await call('export_delivery',{'root':str(project)})
                assert delivery['native_current'] and delivery['process_settings_verified']
                registration=folder/'stage-registration.json';registration.write_bytes(json_bytes(registration_plan(candidate)))
                delivery['artifacts']['stage_registration']=str(registration)
                delivery['sha256']['stage_registration']=hashlib.sha256(registration.read_bytes()).hexdigest()
                delivery['artifacts']={k:Path(v).relative_to(folder).as_posix() for k,v in delivery['artifacts'].items()}
                (folder/'delivery.json').write_bytes(json_bytes(delivery))
                await call('close_verified_document',args('close'))
                result={'id':name,'project_id':state['project_id'],'revision':state['revision'],'source_sha256':case['source_sha256'],
                    'original_preflight_passed':case['original_preflight']['geometry_passed'],'disclosed_repairs':case['repair_audit'],
                    'import':imported,'reopened':reopened,'process_readbacks':readbacks,'capture':capture,
                    'viewport':viewport,
                    'native_current':True,'manufacturing_ready':False,'expected_selection_mm':size}
                (folder/'native-verification.json').write_bytes(json_bytes(result));results.append(result)
                (output/'native-verification.json').write_bytes(json_bytes(results))
                print(json.dumps({'case':name,'COMPLETE':True,'size_mm':size}),flush=True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    asyncio.run(run(parser.parse_args().runtime))
