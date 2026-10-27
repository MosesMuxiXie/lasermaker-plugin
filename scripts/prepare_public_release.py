"""Create a reviewed publication copy; never publish the working directory.

The local verification archive remains untouched. Frozen blueprint files and
manufacturing bytes are copied exactly; only JSON evidence paths/bindings are
made portable. Packages are built from this explicit public copy.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from lasermaker_agent.packaging import SOURCE_CONTENT,package_release
from lasermaker_agent.store import json_bytes
from lasermaker_agent.workstation import load_frozen_spec

EXAMPLES={'original-workstation','sherman-tank','engraving-modes'}
DOCS={'安装.md','使用教程.md','接口与恢复.md','资料来源.md','runtime-licenses.json','验证报告.md','验证报告.json'}
TEXT_SUFFIXES={'.json','.md','.py','.mjs','.js','.txt','.toml','.yml','.yaml','.csv','.svg','.html','.scad','.ps1'}
SECRET=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
PRIVATE_PATH=re.compile(r'(?i)[A-Z]:[\\/](?:Users[\\/][^\\/\s]+|OneDrive[\\/])')
PRIVATE_HASHES={'e30299a25fffe809d66eee260f1b9c7719163c24877b35a201d297c0a196c6db',
                '98d95b3ade60c0591cf151f63174fa439e3a56ae88fbef59a6869d2c30c8dc9a'}


def include_public_path(path):
    p=Path(path);parts=p.parts
    if p.as_posix().casefold()=='tests/fixtures/cockpit-geometry.json':return False
    if any(x in {'.git','.venv','work','build','dist','__pycache__','.pytest_cache','.ruff_cache','superseded','audit','operations'} for x in parts):return False
    if any(x.endswith(('.egg-info','.dist-info')) or x=='node_modules' for x in parts):return False
    if p.name in {'.project.lock','.service.lock'} or p.suffix=='.pyc':return False
    if parts[0]=='examples':
        if len(parts)<2 or parts[1] not in EXAMPLES:return False
        if 'edit-probe' in parts and p.name!='report.json':return False
    if parts[0]=='docs' and (len(parts)!=2 or p.name not in DOCS):return False
    return parts[0] in SOURCE_CONTENT or parts[0] in {'.gitignore','PUBLICATION.json'}


def redact_json(value,root):
    """Preserve all geometry and file SHA values while removing local bindings."""
    if isinstance(value,dict):return {k:redact_json(v,root) for k,v in value.items() if k!='gui_binding'}
    if isinstance(value,list):return [redact_json(v,root) for v in value]
    if isinstance(value,str):
        for prefix in (str(root)+'\\',str(root)+'/',root.as_posix()+'/'):
            if value.casefold().startswith(prefix.casefold()):return value[len(prefix):].replace('\\','/')
        result=value
        for prefix in (str(root)+'\\',str(root)+'/',root.as_posix()+'/'):
            result=result.replace(prefix,'<project>/')
        result=re.sub(r'(?i)[A-Z]:[\\/]Users[\\/][^\\/\s"\']+', '<user>',result)
        return result
    return value


def scan_public_tree(root):
    issues=[]
    for p in sorted(Path(root).rglob('*')):
        if not p.is_file() or '.git' in p.parts:continue
        if hashlib.sha256(p.read_bytes()).hexdigest() in PRIVATE_HASHES:
            issues.append({'path':p.relative_to(root).as_posix(),'code':'PRIVATE_ARTWORK_HASH'})
        if p.suffix.lower() not in TEXT_SUFFIXES:continue
        text=p.read_text(encoding='utf-8-sig')
        if SECRET.search(text):issues.append({'path':p.relative_to(root).as_posix(),'code':'SECRET_PATTERN'})
        if PRIVATE_PATH.search(text):issues.append({'path':p.relative_to(root).as_posix(),'code':'PRIVATE_ABSOLUTE_PATH'})
    return issues


def prepare(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    if target==source or target.exists():raise ValueError('NEW_PUBLIC_STAGE_DIRECTORY_REQUIRED')
    # Required acceptance is checked before the publication copy is created.
    report=json.loads((source/'examples/original-workstation/verification-report.json').read_text(encoding='utf-8'))
    if report['native_projects_verified']!=5 or report['manufacturing_ready'] or not report['blueprint_unchanged']:
        raise ValueError('SOFTWARE_ACCEPTANCE_REPORT_REQUIRED')
    load_frozen_spec(source/'examples/original-workstation/blueprint')
    target.mkdir(parents=True)
    copied=[];redacted=[]
    for entry in dict.fromkeys((*SOURCE_CONTENT,'.gitignore')):
        start=source/entry
        if not start.exists():continue
        files=[start] if start.is_file() else sorted(start.rglob('*'))
        for p in files:
            if not p.is_file():continue
            relative=p.relative_to(source)
            if not include_public_path(relative):continue
            if p.is_symlink():raise ValueError('SYMLINK_IN_PUBLIC_SOURCE')
            output=target/relative;output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,output);copied.append(relative.as_posix())
            if p.suffix=='.json' and 'blueprint' not in relative.parts:
                value=json.loads(p.read_text(encoding='utf-8-sig'));clean=redact_json(value,source)
                if clean!=value:output.write_bytes(json_bytes(clean));redacted.append(relative.as_posix())
    # Do not copy a coupon derived from private benchmark data. Build a fresh
    # public geometric example from the explicitly synthetic test source.
    from lasermaker_agent.sample import coupon_design
    from lasermaker_agent.service import Service
    synthetic=json.loads((target/'tests/fixtures/synthetic-six-part.json').read_text(encoding='utf-8'))
    coupon=target/'examples/slot-coupon';coupon.mkdir(parents=True)
    service=Service();project=coupon/'project'
    service.call('create_project',{'root':str(project),'name':'公开合成插槽试切片','design':coupon_design(synthetic)})
    delivery=service.call('export_delivery',{'root':str(project)})
    assert delivery['geometry_passed'] and not delivery['native_current']
    delivery['artifacts']={k:Path(v).relative_to(coupon).as_posix() for k,v in delivery['artifacts'].items()}
    (coupon/'delivery.json').write_bytes(json_bytes(delivery))
    (coupon/'README.md').write_text('''# 公开合成插槽试切片

独立合成矩形和七档 2.7–3.3 mm 槽宽，步长 0.1 mm；SVG/DXF 与几何预检见 delivery.json。这份合成示例未作原生导入或实物试切，native_current=false。已经通过原生软件核验的工具站辅助试片另见 ../original-workstation/fixtures/delivery.json；所有实际加工均须现场试切。
''',encoding='utf-8')
    # Public sample metadata can be reopened after relocation. UI bindings are
    # intentionally acquired again by reload_and_verify, never reused by PID.
    for manifest in (target/'examples').rglob('manifest.json'):
        value=json.loads(manifest.read_text(encoding='utf-8'))
        if 'artifacts' not in value or 'sha256' not in value:continue
        for key,relative in list(value['artifacts'].items()):
            file=target/relative
            if file.exists() and file.parent==manifest.parent:value['artifacts'][key]=file.name
        manifest.write_bytes(json_bytes(value))
    # The private prototype and third-party reference artwork are deliberately
    # excluded; the notices explain the narrower public contents.
    notices=target/'THIRD_PARTY_NOTICES.md'
    original=notices.read_text(encoding='utf-8')
    start=original.find('Reference cockpit geometry')
    if start>=0:original=original[:start]+'''User-provided cockpit artwork and the five third-party reference artwork
datasets used in local evaluation are not included in this public distribution.
They are not relicensed by the software MIT license. The original workstation,
tank and small calibration examples are supplied as project test designs.
Bundled runtime distribution licenses are retained under licenses/ and listed
in docs/runtime-licenses.json. System fonts are not redistributed.
'''
    notices.write_text(original,encoding='utf-8')
    # Replace the local-only image/provenance index with this public inventory.
    (target/'examples/README.md').write_text('''# 公开样例

- [原创双抽屉工具站](original-workstation/README.md)：54 个零件、4 张排板、原生工程、分解图和三维装配。
- [谢尔曼风格拼装模型](sherman-tank/装配说明.md)：39 个板件与三维模型。
- [独立插槽试切片](slot-coupon/)；[描线与雕刻工艺样例](engraving-modes/说明.md)。

私人原作品、网上参考图的原始素材、失败会话与原始宿主日志保留在本地，不包含在公开包中。实物试切、机器参数和承重仍需现场确认。
''',encoding='utf-8')
    product_readme=target/'examples/original-workstation/README.md'
    product_readme.write_text(product_readme.read_text(encoding='utf-8').replace(
        '旧方向测试及弹窗中断记录保存在 `superseded/`，不用于当前交付。',
        '旧方向测试及弹窗中断记录仅保留在原工作区，不包含在公开发行中。'),encoding='utf-8')
    for file in (target/'docs/验证报告.json',target/'examples/original-workstation/verification-report.json'):
        value=json.loads(file.read_text(encoding='utf-8'))
        if 'automated_tests' in value:value['automated_tests']['log']='Local test logs excluded; rerun python -m pytest -q from source.'
        value['prior_attempts']='Local-only; failed sessions are excluded from public distribution.'
        file.write_bytes(json_bytes(value))
    publication={'schema_version':1,'version':report['plugin_version'],
        'purpose':'Public source and release packaging; local evidence remains in original workspace.',
        'excluded':['private cockpit artwork','third-party reference artwork datasets','work and account caches','failed sessions','raw host traces','desktop PID bindings'],
        'redacted_json_paths':redacted,'manufacturing_files_modified':False,
        'frozen_blueprint_verified':True,'native_file_sha256':[r['native_sha256'] for r in report['native_verification']]}
    (target/'PUBLICATION.json').write_bytes(json_bytes(publication))
    issues=scan_public_tree(target)
    if issues:raise ValueError('PUBLIC_SCAN_FAILED: '+json.dumps(issues,ensure_ascii=False))
    load_frozen_spec(target/'examples/original-workstation/blueprint')
    return {'copied_files':len(copied),'redacted_json_files':len(redacted),'public_scan_issues':issues,'stage':str(target)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--stage',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.source,a.stage),ensure_ascii=False))
