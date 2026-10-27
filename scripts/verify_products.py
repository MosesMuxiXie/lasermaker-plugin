"""Bounded real native delivery workflow via the frozen stdio MCP runtime.

Run after the soak releases the desktop. Same original request IDs make confirmed
steps replayable. Unknown GUI outcomes stop and require inspection.
"""
import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lasermaker_agent.store import json_bytes
from lasermaker_agent.sample import registration_plan


async def run(runtime):
    root = Path(__file__).resolve().parent.parent
    results = []
    params = StdioServerParameters(command=str(runtime.resolve()), args=['mcp'])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                if result.isError or result.structuredContent is None:
                    raise RuntimeError(f'{name}: {result.content}')
                return result.structuredContent
            tools = await session.list_tools()
            assert len(tools.tools)==17
            for relative in ('creator-cockpit/project', 'slot-coupon/project',
                             'sherman-tank/sheet-1/project', 'sherman-tank/sheet-2/project'):
                project = root/'examples'/relative
                state = await call('resume_project', {'root': str(project)})
                preflight = await call('preflight', {'root': str(project)})
                assert preflight['geometry_passed']
                b = preflight['bounds_mm']; expected = [b[2]-b[0], b[3]-b[1]]
                base = {'root': str(project), 'expected_revision': state['revision']}
                def args(label, **kwargs):
                    return {**base, 'request_id': 'product-final-v2-'+label, **kwargs}
                evidence = {'project': relative, 'revision': state['revision'], 'expected_selection_mm': expected}
                evidence['import'] = await call('import_design', args('import'))
                colors = {layer['color'] for layer in evidence['import']['layers']}
                processes = []
                for color, mode, speed in (('#ff0000', 'score', 100), ('#000000', 'cut', 10),
                                            ('#0000ff', 'shallow_engrave', 100)):
                    if color not in colors:
                        continue
                    process = {'mode': mode, 'speed_mm_s': speed, 'power_max_percent': 15, 'power_min_percent': 13}
                    if mode in ('engrave','shallow_engrave'):
                        process.pop('power_min_percent')
                    await call('set_layer_process', args('process-'+mode, color=color, process=process))
                    processes.append((color, process))
                saved = await call('save_native', args('save', filename='native/product-v2.lcpx'))
                evidence['reopened'] = await call('reload_and_verify', args('reopen', path=saved['path'], expected_size_mm=expected))
                evidence['process_readbacks'] = []
                for color, process in processes:
                    evidence['process_readbacks'].append(await call('verify_layer_process', args('verify-'+process['mode'], color=color, process=process)))
                evidence['capture'] = await call('capture_app', {'root': str(project), 'filename': 'evidence/product-reopened-v2.png'})
                evidence['checkpoint'] = await call('checkpoint', {'root': str(project), 'label': '原生工程重开及工艺读回通过'})
                exported = await call('export_delivery', {'root': str(project)})
                assert exported['native_current'] and exported['process_settings_verified']
                evidence['export'] = exported
                registration=project.parent/'stage-registration.json'
                registration.write_bytes(json_bytes(registration_plan(state['design'])))
                exported['artifacts']['stage_registration']=str(registration)
                portable_index = dict(exported)
                portable_index['artifacts'] = {k: Path(v).relative_to(project.parent).as_posix() for k,v in exported['artifacts'].items()}
                (project.parent/'delivery.json').write_bytes(json_bytes(portable_index))
                await call('close_verified_document', args('close'))
                results.append(evidence)
                (root/'work/product-native-verification.json').write_bytes(json_bytes(results))
                print(json.dumps({'project': relative, 'native_current': True, 'dimensions': expected}, ensure_ascii=False), flush=True)
    return results


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True, type=Path)
    asyncio.run(run(parser.parse_args().runtime))
