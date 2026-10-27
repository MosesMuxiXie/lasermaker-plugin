"""Frozen worker/CLI verification, including a real Windows sharing violation."""
import argparse
import asyncio
import json
import subprocess
import time
import uuid
from pathlib import Path

import win32file
import win32con
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lasermaker_agent.store import json_bytes


async def main(runtime):
    base = Path(__file__).resolve().parent.parent
    project = base/'work'/('frozen-sharing-'+uuid.uuid4().hex[:8])
    params = StdioServerParameters(command=str(runtime.resolve()),args=['mcp'])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools)==17
            async def call(name,args):
                r = await session.call_tool(name,args)
                assert not r.isError, r.content
                return r.structuredContent
            await call('create_project',{'root':str(project),'name':'真实文件共享冲突验证',
                'design':{'units':'mm','sheet_mm':[100,80],'objects':[]}})
            args = {'root':str(project),'expected_revision':0,'request_id':'sharing-edit-001','operations':[
                {'op':'add','object':{'id':'rect','part_id':'P','role':'cut_outer','closed':True,
                    'points':[[5,5],[65,5],[65,35],[5,35]]}},
                {'op':'text','id':'text','part_id':'P','role':'score','text':'Laser O','height_mm':4,
                    'position':[10,12],'font_path':'C:/Windows/Fonts/arial.ttf'}]}
            handle = win32file.CreateFile(str(project/'project.json'),win32con.GENERIC_READ,
                win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE,None,win32con.OPEN_EXISTING,0,None)
            pending = asyncio.create_task(call('apply_design_ops',args))
            try:
                until = time.monotonic()+10
                while not list(project.glob('.project.json.*.tmp')):
                    assert not pending.done(), 'Worker ended before sharing retry could be observed'
                    assert time.monotonic()<until
                    await asyncio.sleep(.01)
                before = time.monotonic()
                await asyncio.sleep(.3)
                assert not pending.done(), 'Frozen atomic replace did not retry the held destination'
                held_seconds = time.monotonic()-before
            finally:
                win32file.CloseHandle(handle)
            result = await pending
            assert result['revision']==1
            assert await call('apply_design_ops',args)==result
            report = await call('preflight',{'root':str(project)})
            assert report['geometry_passed']
            exported = await call('export_delivery',{'root':str(project)})
            assert '<text' not in Path(exported['artifacts']['svg']).read_text(encoding='utf-8')
            evidence = {'passed':True,'tool_count':17,'real_windows_sharing_conflict':True,
                'held_after_temp_created_seconds':held_seconds,'same_request_replay':True,
                'packed_font_outlines':True,'preflight':report,'runtime':str(runtime.resolve())}
    command = subprocess.run([str(runtime.resolve()),'resume_project','--json',json.dumps({'root':str(project)})],
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert command.returncode==0,command.stderr
    envelope = json.loads(command.stdout)
    assert envelope['ok'] and envelope['result']['revision']==1
    evidence['cli_resume']=True
    (base/'work/frozen-runtime-verification.json').write_bytes(json_bytes(evidence))
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True,type=Path)
    asyncio.run(main(parser.parse_args().runtime))
