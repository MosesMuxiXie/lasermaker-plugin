"""Real save/reopen readback for shallow/deep modes and outlined multilingual text."""
import argparse
import asyncio
from pathlib import Path

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.store import json_bytes


async def main(runtime):
    base=Path(__file__).resolve().parent.parent
    root=base/'examples/engraving-modes/project'
    async with stdio_client(StdioServerParameters(command=str(runtime.resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(name,args):
                r=await session.call_tool(name,args)
                assert not r.isError,r.content
                return r.structuredContent
            if not (root/'project.json').exists():
                await call('create_project',{'root':str(root),'name':'浅雕深雕与文字轮廓软件核验',
                    'design':{'units':'mm','sheet_mm':[100,80],'objects':[{'id':'outer','part_id':'P',
                        'role':'cut_outer','closed':True,'points':[[5,5],[65,5],[65,35],[5,35]]}]}})
            await call('apply_design_ops',{'root':str(root),'expected_revision':0,'request_id':'engraving-text-v1',
                'operations':[{'op':'text','id':'label','part_id':'P','role':'engrave','text':'回O',
                    'position':[12,12],'height_mm':8,'font_path':'C:/Windows/Fonts/msyh.ttc'}]})
            baseargs={'root':str(root),'expected_revision':1}
            def args(label,**kw):
                return {**baseargs,'request_id':'engraving-final-v2-'+label,**kw}
            assert (await call('preflight',{'root':str(root)}))['geometry_passed']
            await call('import_design',args('import'))
            cut={'mode':'cut','speed_mm_s':10,'power_max_percent':15,'power_min_percent':13}
            await call('set_layer_process',args('cut',color='#000000',process=cut))
            results=[]
            for mode in ('shallow_engrave','engrave'):
                process={'mode':mode,'speed_mm_s':100,'power_max_percent':15}
                await call('set_layer_process',args(mode+'-set',color='#0000ff',process=process))
                saved=await call('save_native',args(mode+'-save',filename='native/'+mode+'-v2.lcpx'))
                reopened=await call('reload_and_verify',args(mode+'-open',path=saved['path'],expected_size_mm=[60,30]))
                verified=await call('verify_layer_process',args(mode+'-verify',color='#0000ff',process=process))
                await call('verify_layer_process',args(mode+'-verify-cut',color='#000000',process=cut))
                results.append({'mode':mode,'saved':saved,'reopened':reopened,'verified':verified})
            capture=await call('capture_app',{'root':str(root),'filename':'evidence/engraving-reopened-v2.png'})
            exported=await call('export_delivery',{'root':str(root)})
            assert exported['native_current'] and exported['process_settings_verified']
            exported['artifacts']={k:Path(v).relative_to(root.parent).as_posix() for k,v in exported['artifacts'].items()}
            (root.parent/'delivery.json').write_bytes(json_bytes(exported))
            await call('close_verified_document',args('close'))
    (base/'work/engraving-mode-verification.json').write_bytes(json_bytes({'passed':True,
        'outlined_text':'回O','font_file_bundled':False,'size_mm':[60,30],
        'capture':capture,
        'shallow_and_deep_are_separate_passes':True,'manufacturing_ready':False,'results':results}))
    (root.parent/'verification.json').write_bytes((base/'work/engraving-mode-verification.json').read_bytes())
    print('Both engraving modes saved and reopened; settings read back; no machine started')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True,type=Path)
    asyncio.run(main(parser.parse_args().runtime))
