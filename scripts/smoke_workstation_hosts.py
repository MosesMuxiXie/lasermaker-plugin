"""Run existing account-free host checks in a new isolated 0.1.2 staging copy."""
import asyncio
import json
import shutil
import subprocess
import sys
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'work/宿主插件 workstation-v11 path'


def prepare():
    if not STAGE.exists():
        STAGE.mkdir()
        for name in ('plugin.json','mcp.json','package.json','kimi.plugin.json','.agents','.claude-plugin','skills','adapters','LICENSE','README.md'):
            source=ROOT/name;target=STAGE/name
            shutil.copytree(source,target) if source.is_dir() else shutil.copyfile(source,target)
        shutil.copytree(ROOT/'work/portable-workstation-v11/lasermaker-agent',STAGE/'runtime')
    home=ROOT/'work/hosts/codex-workstation-v11-home';home.mkdir(exist_ok=True)
    config='[marketplaces.lasermaker-local]\nsource_type = "local"\nsource = '+"'"+str(STAGE)+"'"+'\n\n[plugins."lasermaker-agent@lasermaker-local"]\nenabled = true\n'
    (home/'config.toml').write_text(config,encoding='utf-8')
    backup=ROOT/'work/host-evidence-before-workstation';backup.mkdir(exist_ok=True)
    for file in (ROOT/'work').glob('host-*.json'):
        if not (backup/file.name).exists():shutil.copyfile(file,backup/file.name)
    executable=ROOT/'work/hosts/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ('API_KEY','TOKEN','SECRET'))}
    env['CODEX_HOME']=str(home)
    subprocess.run([str(executable),'plugin','add','lasermaker-agent@lasermaker-local'],cwd=STAGE,env=env,
                   check=True,timeout=60,creationflags=0x08000000)


def python_smoke(name):
    file=ROOT/'scripts'/('smoke_'+name+'.py')
    source=file.read_text(encoding='utf-8').replace('宿主插件 ref-v10 path','宿主插件 workstation-v11 path').replace('-ref-v10-home','-workstation-v11-home')
    namespace={'__file__':str(file),'__name__':'workstation_host_smoke'}
    exec(compile(source,str(file),'exec'),namespace)
    if name=='kimi':namespace['main']()
    else:asyncio.run(namespace['run']())


def main():
    command=sys.argv[1]
    if command=='prepare':prepare();return
    if command=='deepseek':
        source=(ROOT/'scripts/smoke_deepseek.mjs').read_text(encoding='utf-8').replace('宿主插件 ref-v10 path','宿主插件 workstation-v11 path')
        file=ROOT/'work/smoke-deepseek-workstation.mjs';file.write_text(source,encoding='utf-8')
        result=subprocess.run(['node',str(file)],cwd=ROOT,timeout=180);raise SystemExit(result.returncode)
    python_smoke(command)


if __name__=='__main__':main()
