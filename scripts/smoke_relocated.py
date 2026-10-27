"""Check a native project reopened from a freshly extracted portable package."""
import argparse
import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.store import json_bytes, file_hash


async def main(runtime,project):
    runtime,project=runtime.resolve(),project.resolve()
    async with stdio_client(StdioServerParameters(command=str(runtime),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(name,args):
                r=await session.call_tool(name,args)
                assert not r.isError,r.content
                return r.structuredContent
            state=await call('resume_project',{'root':str(project)})
            assert not state['native_external_change']
            native=project/state['native']['path']
            expected_hash=state['native']['sha256']
            processes=state['native']['verification']['layer_process_readbacks']
            base={'root':str(project),'expected_revision':state['revision']}
            def args(label,**kwargs):
                return {**base,'request_id':'relocation-v1-'+label,**kwargs}
            report=await call('preflight',{'root':str(project)})
            b=report['bounds_mm']
            reopened=await call('reload_and_verify',args('open',path=str(native),expected_size_mm=[b[2]-b[0],b[3]-b[1]]))
            assert reopened['reopen_verified'] and reopened['sha256']==expected_hash
            readbacks=[]
            for color,values in processes.items():
                process={k:values[k] for k in ('mode','speed_mm_s','power_max_percent','power_min_percent') if k in values}
                readbacks.append(await call('verify_layer_process',args('read-'+color[1:],color=color,process=process)))
            exported=await call('export_delivery',{'root':str(project)})
            assert exported['native_current'] and exported['process_settings_verified']
            await call('close_verified_document',args('close'))
            assert file_hash(native)==expected_hash
    result={'passed':True,'project':str(project),'runtime_sha256':file_hash(runtime),
            'native_sha256':expected_hash,'reopened':reopened,'process_readbacks':readbacks,
            'native_unchanged':True,'relocated_root_verified':True}
    root=Path(__file__).resolve().parent.parent
    (root/'work/relocated-project-verification.json').write_bytes(json_bytes(result))
    print(json_bytes(result).decode('utf-8'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--project',required=True,type=Path)
    args_=parser.parse_args();asyncio.run(main(args_.runtime,args_.project))
