"""Exercise the configured 20,000-object limit over the real stdio MCP.

Separate diagnostic grid; never imported into LaserMaker or sent to a device.
"""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.store import json_bytes


async def main(runtime):
    base=Path(__file__).resolve().parents[1];project=base/'work/workstation-limit-20000'
    report=[];start=time.monotonic()
    async with stdio_client(StdioServerParameters(command=str(Path(runtime).resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(tool,args,error=False):
                before=time.monotonic();result=await session.call_tool(tool,args)
                report.append({'tool':tool,'seconds':round(time.monotonic()-before,3),'is_error':result.isError})
                print(json.dumps(report[-1]),flush=True)
                assert bool(result.isError)==error,result.content
                return result.structuredContent if not error else [c.text for c in result.content if c.type=='text']
            objects=[{'id':name,'role':'score','closed':False,'points':[[0,y],[1,y]]} for name,y in [('A',0),('B',300)]]
            await call('create_project',{'root':str(project),'name':'极限对象数诊断格阵，不导入设备','design':{'units':'mm','objects':objects}})
            for revision,oid in enumerate(('A','B')):
                result=await call('apply_design_ops',{'root':str(project),'request_id':'limit-array-'+oid,'expected_revision':revision,
                    'operations':[{'op':'array','ids':[oid],'columns':100,'rows':100,'dx':2,'dy':2}]})
            assert result['object_count']==20000
            current=await call('resume_project',{'root':str(project)});assert len(current['design']['objects'])==20000
            path=project/'project.json';before=hashlib.sha256(path.read_bytes()).hexdigest()
            error=await call('apply_design_ops',{'root':str(project),'request_id':'limit-20001','expected_revision':2,
                'operations':[{'op':'add','object':{'id':'over-limit','role':'score','closed':False,'points':[[0,600],[1,600]]}}]},True)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before
            pf=await call('preflight',{'root':str(project)});assert pf['geometry_passed'] and pf['object_count']==20000
            await call('checkpoint',{'root':str(project),'label':'20000对象通过；第20001对象原子拒绝，文件未变'})
    output={'configured_limit':20000,'objects_reached':20000,'over_limit_error':error,'rejected_without_file_mutation':True,
        'large_stdio_response_verified':True,'calls':report,'elapsed_seconds':round(time.monotonic()-start,3),
        'imported_to_gui':False,'machine_started':False,'project':str(project),'timed_soak':False}
    (base/'examples/original-workstation/limit-probe.json').write_bytes(json_bytes(output))


if __name__=='__main__':asyncio.run(main(sys.argv[1]))
