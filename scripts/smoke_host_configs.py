"""Invoke stdio configurations resolved by native hosts; no model account.

This is deliberately labeled separately from dispatch through a host's agent loop.
"""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lasermaker_agent.store import json_bytes


async def main():
    root = Path(__file__).resolve().parent.parent
    project = Path(json.loads((root/'work/host-handoff-project.json').read_text(encoding='utf-8'))['root'])
    assert project.resolve().is_relative_to((root/'work').resolve())
    claude = json.loads((root/'work/host-claude-control.json').read_text(encoding='utf-8'))
    last = [r for r in claude['responses'] if r['subtype']=='mcp_status'][-1]
    claude_config = next(s['config'] for s in last['response']['response']['mcpServers'] if 'lasermaker' in s['name'])
    kimi = json.loads((root/'work/host-kimi-native.json').read_text(encoding='utf-8'))
    server_list = next(r['result']['data'] for r in kimi['responses'] if r['path']=='/api/v2/mcp/servers')
    kimi_config = next(s['config'] for s in server_list if 'lasermaker' in s['name'])
    reports = []
    for host, config, revision, label in (('Claude Code',claude_config,2,'move'),('Kimi Code',kimi_config,3,'rotate')):
        params = StdioServerParameters(command=config['command'],args=config['args'],cwd=config.get('cwd'))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                async def call(name,args):
                    r = await session.call_tool(name,args)
                    assert not r.isError, r.content
                    return r.structuredContent
                assert len((await session.list_tools()).tools)==17
                doctor = await call('doctor',{})
                state = await call('resume_project',{'root':str(project)})
                ids = [o['id'] for o in state['design']['objects'] if o['part_id']=='P-copy']
                op = {'op':label,'ids':ids,**({'dx':0,'dy':5} if label=='move' else {'degrees':2,'origin':[110,25]})}
                arguments = {'root':str(project),'request_id':host+'-config-'+label+'-001',
                             'expected_revision':revision,'operations':[op]}
                edited = await call('apply_design_ops',arguments)
                assert edited['revision']==revision+1
                report = await call('preflight',{'root':str(project)})
                assert report['geometry_passed'],report
                await call('checkpoint',{'root':str(project),'label':host+' resolved config handoff'})
                reports.append({'host':host,'passed':True,'resolved_config_from_native_loader':True,
                    'native_harness_dispatch':False,'model_turn_executed':False,'doctor':doctor,
                    'revision':edited['revision'],'preflight':report})
    (root/'work/host-resolved-config-calls.json').write_bytes(json_bytes(reports))
    print(json.dumps([{'host':r['host'],'passed':r['passed'],'revision':r['revision']} for r in reports]))


if __name__=='__main__':
    asyncio.run(main())
