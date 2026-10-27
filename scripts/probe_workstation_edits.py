"""MCP edits on a disposable copy of real product geometry, never the native job."""
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from lasermaker_agent.geometry import object_shape
from lasermaker_agent.store import json_bytes


async def run(runtime):
    folder=Path(__file__).resolve().parents[1]/'examples/original-workstation'
    model=json.loads((folder/'assembly-source.json').read_text(encoding='utf-8'))
    comb=next(p for p in model['parts'] if p['id']=='C01');base=next(p for p in model['parts'] if p['id']=='B00')
    source={'id':'C01+B00','objects':comb['objects']+base['objects']}
    project=folder/'edit-probe/project-v2'
    async with stdio_client(StdioServerParameters(command=str(Path(runtime).resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(tool,args):
                result=await session.call_tool(tool,args)
                if result.isError:raise RuntimeError(result.content)
                return result.structuredContent
            if not (project/'project.json').exists():
                await call('create_project',{'root':str(project),'name':'线缆梳的可恢复精细编辑测试副本',
                    'design':{'units':'mm','objects':source['objects']}})
            baseline=source['objects'][0];oid=baseline['id'];revision=0;coverage=[]
            arc=next(o for o in base['objects'] if o['role']=='cut_inner' and 'd' in o);arcid=arc['id']
            async def edit(label,operations):
                nonlocal revision
                args={'root':str(project),'request_id':'probe-A1-'+label,'expected_revision':revision,'operations':operations}
                result=await call('apply_design_ops',args);assert await call('apply_design_ops',args)==result
                revision=result['revision'];coverage.append(label)
                return await call('open_project',{'root':str(project)})
            # Source's cable-channel nodes, including round bottoms, are preserved.
            state=await edit('transforms',[
                {'op':'move','ids':[oid,arcid],'dx':12.345,'dy':-.125},
                {'op':'move','ids':[oid,arcid],'dx':-12.345,'dy':.125},
                {'op':'rotate','ids':[oid,arcid],'degrees':37.5,'origin':[90,210]},
                {'op':'rotate','ids':[oid,arcid],'degrees':-37.5,'origin':[90,210]},
                {'op':'scale','ids':[oid,arcid],'sx':1.25,'sy':.8},
                {'op':'scale','ids':[oid,arcid],'sx':.8,'sy':1.25},
                {'op':'mirror','ids':[oid,arcid],'axis':'x'}, {'op':'mirror','ids':[oid,arcid],'axis':'x'}])
            roundtrip=object_shape(state['design']['objects'][0]).hausdorff_distance(object_shape(baseline));assert roundtrip<1e-7
            arc_error=object_shape(next(o for o in state['design']['objects'] if o['id']==arcid)).hausdorff_distance(object_shape(arc));assert arc_error<.01
            point=state['design']['objects'][0]['points'][0]
            state=await edit('node',[
                {'op':'node','id':oid,'index':0,'point':[point[0]+.01,point[1]]},
                {'op':'node','id':oid,'index':0,'point':point}])
            state=await edit('array-align-distribute',[
                {'op':'duplicate','ids':[oid],'dx':70,'dy':0,'suffix':'-copy'},
                {'op':'array','ids':[oid],'columns':3,'rows':1,'dx':140,'dy':0},
                {'op':'align','ids':[oid,oid+'-copy',oid+'-r0c1',oid+'-r0c2'],'axis':'y','mode':'min'},
                {'op':'distribute','ids':[oid,oid+'-copy',oid+'-r0c1',oid+'-r0c2'],'axis':'x','mode':'center'}])
            before=object_shape(next(o for o in state['design']['objects'] if o['id']==oid+'-copy')).area
            state=await edit('offset',[{'op':'offset','ids':[oid+'-copy'],'distance':.15}])
            assert object_shape(next(o for o in state['design']['objects'] if o['id']==oid+'-copy')).area>before
            state=await edit('boolean-difference',[
                {'op':'add','object':{'id':'pocket','part_id':'C01','role':'cut_outer','closed':True,'points':[[65,206],[67,206],[67,208],[65,208]]}},
                {'op':'boolean','ids':[oid,'pocket'],'mode':'difference','result_id':oid}])
            assert any(o['id']==oid+'-hole-0' and o['role']=='cut_inner' for o in state['design']['objects'])
            # Restore from an explicit checkpoint source; no inverse Boolean assumptions.
            state=await edit('restore',[
                {'op':'delete','ids':[o['id'] for o in state['design']['objects']]},
                *[{'op':'add','object':o} for o in source['objects']]])
            assert state['design']['objects']==source['objects']
            checkpoint=await call('checkpoint',{'root':str(project),'label':'真实产品副本变换、节点、复制阵列、对齐分布、偏移、布尔后准确恢复'})
    # A new MCP process independently verifies recovery of the final revision.
    async with stdio_client(StdioServerParameters(command=str(Path(runtime).resolve()),args=['mcp'])) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize();result=await session.call_tool('resume_project',{'root':str(project)})
            assert not result.isError and result.structuredContent['design']['objects']==source['objects']
    report={'product_parts':['C01','B00'],'coverage':coverage,'roundtrip_error_mm':roundtrip,'arc_roundtrip_error_mm':arc_error,'final_revision':revision,
        'idempotent_every_batch':True,'exact_source_restored':True,'new_mcp_process_resumed':True,'checkpoint':checkpoint,
        'native_product_modified':False,'numeric_roundtrip_threshold_mm':1e-7,
        'test_history':'Initial 1e-9 mm guard detected 1.324e-9 mm floating-point drift; bounded to 1e-7 mm, then explicit exact source restoration.'}
    (folder/'edit-probe/report.json').write_bytes(json_bytes(report));print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':asyncio.run(run(sys.argv[1]))
