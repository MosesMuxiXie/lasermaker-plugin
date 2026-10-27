import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, mkdir, rm, cp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { validateZip, parseArgs, hostCommands, ensureInstalled, powershellInvocation, selectExecutable, runHostCommand } from '../installer/core.mjs';

const hash = b => createHash('sha256').update(b).digest('hex');
function zip(names) {
  const chunks=[];
  for (const value of names) {
    const name=Buffer.from(typeof value==='string'?value:value.name), h=Buffer.alloc(46);
    h.writeUInt32LE(0x02014b50,0);h.writeUInt16LE(0x800,8);h.writeUInt16LE(8,10);
    h.writeUInt32LE(10,24);h.writeUInt16LE(name.length,28);
    if(value.symlink)h.writeUInt32LE((0xa000<<16)>>>0,38);
    chunks.push(h,name);
  }
  const directory=Buffer.concat(chunks), end=Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(names.length,8);end.writeUInt16LE(names.length,10);end.writeUInt32LE(directory.length,12);
  return Buffer.concat([directory,end]);
}

test('ZIP validation accepts publisher root and rejects traversal, collisions and links',()=>{
  assert.equal(validateZip(zip(['lasermaker-agent/runtime/lasermaker-agent.exe'])).entries,1);
  for(const name of ['../x','/absolute','lasermaker-agent/../x','lasermaker-agent/a:ads','lasermaker-agent/CON','lasermaker-agent/a.','other/file'])
    assert.throws(()=>validateZip(zip([name])));
  assert.throws(()=>validateZip(zip(['lasermaker-agent/A','lasermaker-agent/a'])));
  assert.throws(()=>validateZip(zip([{name:'lasermaker-agent/link',symlink:true}])));
  assert.throws(()=>validateZip(Buffer.from('not zip')));
});

test('CLI parses only supported commands, hosts and options',()=>{
  assert.equal(parseArgs(['--version']).command,'version');
  assert.deepEqual(parseArgs(['install','codex','--dir','D:/space path']),{command:'install',host:'codex',dir:'D:/space path',profile:'laser'});
  for(const args of [['install','unknown'],['delete'],['install','--dir'],['install','codex','--unknown'],['install','deepseek','--profile','../x']])
    assert.throws(()=>parseArgs(args));
});

test('host resolution preserves PATH priority rather than choosing a different installed version',()=>{
  assert.equal(selectExecutable('C:/npm/codex\r\nC:/npm/codex.cmd\r\nC:/app/codex.exe'),'C:/npm/codex.cmd');
  assert.equal(selectExecutable('C:/app/codex.exe\r\nC:/npm/codex.cmd'),'C:/app/codex.exe');
});

test('host setup uses argument arrays and keeps Kimi explicit',()=>{
  const root='D:/Chinese 中文/with spaces';
  assert.deepEqual(hostCommands('codex',root).map(c=>c.args),[
    ['plugin','marketplace','add',root],['plugin','add','lasermaker-agent@lasermaker-local']]);
  assert.equal(hostCommands('claude',root)[0].args.includes(root),true);
  assert.deepEqual(hostCommands('kimi',root),[]);
  assert.deepEqual(hostCommands('deepseek',root,'laser')[0].args,['plugin','--profile','laser','add',root]);
  const command=powershellInvocation('tool.cmd',[root,"literal'$(); & text"]);
  assert.equal(command.command.toLowerCase().endsWith('powershell.exe'),true);
  assert.equal(command.args.includes('-ExecutionPolicy'),false);
  assert.equal(command.args.includes('-EncodedCommand'),true);
});

async function fixture(t){
  const base=await mkdtemp(path.join(os.tmpdir(),'lasermaker-setup-'));t.after(()=>rm(base,{recursive:true,force:true}));
  const packageRoot=path.join(base,'package');await mkdir(packageRoot);
  await writeFile(path.join(packageRoot,'README.md'),'English README\n');
  const bytes=zip(['lasermaker-agent/runtime/lasermaker-agent.exe']), exe=Buffer.from('verified runtime'),dll=Buffer.from('verified dependency');
  const runtimeTreeSha256=hash(JSON.stringify({'_internal/python312.dll':hash(dll),'lasermaker-agent.exe':hash(exe)}));
  const manifest={bundleVersion:'0.1.3',coreVersion:'0.1.2',repository:'MosesMuxiXie/lasermaker-plugin',tag:'v0.1.2',asset:'lasermaker-agent-0.1.2-plugin.zip',sha256:hash(bytes),executableSha256:hash(exe),runtimeTreeSha256};
  let downloads=0,probes=0;
  const options={base:path.join(base,'install'),packageRoot,manifest,platform:'win32',arch:'x64',log:()=>{},
    download:async(url,file)=>{downloads++;await writeFile(file,bytes);},
    extract:async(file,destination)=>{await mkdir(path.join(destination,'lasermaker-agent/runtime/_internal'),{recursive:true});await writeFile(path.join(destination,'lasermaker-agent/runtime/lasermaker-agent.exe'),exe);await writeFile(path.join(destination,'lasermaker-agent/runtime/_internal/python312.dll'),dll);},
    probe:async()=>{probes++;return {ok:true,result:{name:'lasermaker-agent',version:'0.1.2',windows:true}};}};
  return {base,options,manifest,exe,counts:()=>({downloads,probes})};
}

test('verified install is cached, overlays documentation and preserves project files',async t=>{
  const f=await fixture(t),first=await ensureInstalled(f.options);
  assert.equal(await readFile(path.join(first.root,'README.md'),'utf8'),'English README\n');
  await writeFile(path.join(first.root,'my-design.json'),'keep');
  const second=await ensureInstalled(f.options);
  assert.equal(first.root,second.root);assert.equal(f.counts().downloads,1);
  assert.equal(await readFile(path.join(first.root,'my-design.json'),'utf8'),'keep');
});

test('bad checksum never extracts or executes',async t=>{
  const f=await fixture(t);f.options.manifest={...f.manifest,sha256:'0'.repeat(64)};
  let extracted=false;f.options.extract=async()=>{extracted=true;};
  await assert.rejects(()=>ensureInstalled(f.options),/CHECKSUM/);
  assert.equal(extracted,false);assert.equal(f.counts().probes,0);
});

test('unknown existing version directory and active lock are not replaced',async t=>{
  const f=await fixture(t),destination=path.join(f.options.base,'versions','0.1.3');
  await mkdir(destination,{recursive:true});await writeFile(path.join(destination,'user.txt'),'keep');
  await assert.rejects(()=>ensureInstalled(f.options),/UNMANAGED/);
  assert.equal(await readFile(path.join(destination,'user.txt'),'utf8'),'keep');
  await rm(destination,{recursive:true});await mkdir(path.join(f.options.base,'.install.lock'));
  await assert.rejects(()=>ensureInstalled(f.options),/LOCKED/);
});

test('changed runtime is never executed or overwritten',async t=>{
  const f=await fixture(t),installed=await ensureInstalled(f.options);
  await writeFile(installed.executable,'changed');const before=f.counts().probes;
  await assert.rejects(()=>ensureInstalled(f.options),/INTEGRITY/);
  assert.equal(f.counts().probes,before);assert.equal(await readFile(installed.executable,'utf8'),'changed');
});

test('cached runtime dependencies are all checked, including additions and removals',async t=>{
  for(const mode of ['changed','removed','extra']){
    const f=await fixture(t),installed=await ensureInstalled(f.options),before=f.counts().probes;
    const dll=path.join(installed.root,'runtime/_internal/python312.dll');
    if(mode==='changed')await writeFile(dll,'modified DLL');
    if(mode==='removed')await rm(path.dirname(dll),{recursive:true});
    if(mode==='extra')await writeFile(path.join(path.dirname(dll),'untrusted.pth'),'unexpected');
    await assert.rejects(()=>ensureInstalled(f.options),/INTEGRITY/);
    assert.equal(f.counts().probes,before);
  }
});

test('unsupported platforms fail before network or directory creation',async t=>{
  const f=await fixture(t);await assert.rejects(()=>ensureInstalled({...f.options,platform:'linux'}),/WINDOWS_X64/);
  assert.equal(f.counts().downloads,0);
});

test('wrong executable and failed doctor never publish an installation',async t=>{
  for(const failure of ['hash','doctor']){
    const f=await fixture(t);
    if(failure==='hash')f.options.manifest={...f.manifest,executableSha256:'0'.repeat(64)};
    else f.options.probe=async()=>({ok:false});
    await assert.rejects(()=>ensureInstalled(f.options),failure==='hash'?/CHECKSUM/:/DOCTOR/);
    await assert.rejects(()=>readFile(path.join(f.options.base,'versions/0.1.3/lasermaker-agent/.lasermaker-installation.json')),/ENOENT/);
  }
});

test('a modified integration file is preserved and rejected on reuse',async t=>{
  const f=await fixture(t),installed=await ensureInstalled(f.options);
  await writeFile(path.join(installed.root,'README.md'),'modified');
  await assert.rejects(()=>ensureInstalled(f.options),/INTEGRITY/);
  assert.equal(await readFile(path.join(installed.root,'README.md'),'utf8'),'modified');
});

test('Windows npm command wrappers preserve Unicode/spaces and reject shell expansion', {skip:process.platform!=='win32'},async t=>{
  const f=await fixture(t),record=path.join(f.base,'argv.json');
  const commands=path.join(f.base,'中文命令 with spaces');await mkdir(commands);
  await writeFile(path.join(commands,'record.mjs'),`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(record)},JSON.stringify(process.argv.slice(2)));`);
  await writeFile(path.join(commands,'lm-fixture-host.cmd'),`@echo off\r\n"${process.execPath}" "%~dp0record.mjs" %*\r\n`);
  const original=process.env.PATH;process.env.PATH=commands+path.delimiter+original;
  try{
    runHostCommand('lm-fixture-host',['D:/目录 with spaces',"literal'$(); text"]);
    assert.deepEqual(JSON.parse(await readFile(record,'utf8')),['D:/目录 with spaces',"literal'$(); text"]);
    for(const arg of ['%PATH%','D:/A&B','D:/a^b','D:/a!b'])assert.throws(()=>runHostCommand('lm-fixture-host',[arg]),/UNSUPPORTED/);
  }finally{process.env.PATH=original;}
});
