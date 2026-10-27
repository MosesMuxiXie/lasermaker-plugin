import fs from 'node:fs/promises';
import { createReadStream, createWriteStream } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash, randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const packageRoot=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const overlayEntries=['plugin.json','mcp.json','kimi.plugin.json','package.json','README.md','README.zh-CN.md',
  '.agents','.claude-plugin','adapters','skills','bin','installer','docs/installation.md','docs/安装.md'];
const owner='MosesMuxiXie/lasermaker-plugin';
const markerName='.lasermaker-installation.json';

export async function sha256(file){
  const h=createHash('sha256');for await(const chunk of createReadStream(file))h.update(chunk);return h.digest('hex');
}

export async function fingerprintRuntime(root){
  const files=[];let size=0;
  async function walk(folder){
    const stat=await fs.lstat(folder);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('RUNTIME_TREE_LINK_OR_DIRECTORY');
    for(const name of await fs.readdir(folder)){
      const file=path.join(folder,name),s=await fs.lstat(file);
      if(s.isSymbolicLink())throw Error('RUNTIME_TREE_LINK');
      if(s.isDirectory())await walk(file);
      else if(s.isFile()){
        files.push(file);size+=s.size;if(files.length>10000||size>2*1024**3)throw Error('RUNTIME_TREE_SIZE_LIMIT');
      }else throw Error('RUNTIME_TREE_FILE_TYPE');
    }
  }
  await walk(root);const values=new Map();let cursor=0;
  await Promise.all(Array.from({length:Math.min(8,files.length)},async()=>{
    while(cursor<files.length){const file=files[cursor++];values.set(path.relative(root,file).split(path.sep).join('/'),await sha256(file));}
  }));
  const hashes=Object.fromEntries([...values].sort(([a],[b])=>a<b?-1:a>b?1:0));
  return {sha256:createHash('sha256').update(JSON.stringify(hashes)).digest('hex'),files:files.length,hashes};
}

export function validateZip(bytes){
  // Inspect the central directory before asking Windows to extract anything.
  let end=-1;
  for(let i=bytes.length-22;i>=Math.max(0,bytes.length-65557);i--)
    if(bytes.readUInt32LE(i)===0x06054b50&&i+22+bytes.readUInt16LE(i+20)===bytes.length){end=i;break;}
  if(end<0)throw Error('INVALID_ZIP_DIRECTORY');
  const count=bytes.readUInt16LE(end+10),size=bytes.readUInt32LE(end+12),start=bytes.readUInt32LE(end+16);
  if(!count||count>10000||bytes.readUInt16LE(end+4)||bytes.readUInt16LE(end+6)||bytes.readUInt16LE(end+8)!==count||start+size!==end)
    throw Error('UNSUPPORTED_ZIP_LAYOUT');
  let at=start,total=0;const seen=new Set();
  for(let k=0;k<count;k++){
    if(at+46>end||bytes.readUInt32LE(at)!==0x02014b50)throw Error('INVALID_ZIP_ENTRY');
    const flags=bytes.readUInt16LE(at+8),method=bytes.readUInt16LE(at+10),length=bytes.readUInt32LE(at+24);
    const names=bytes.readUInt16LE(at+28),extra=bytes.readUInt16LE(at+30),comment=bytes.readUInt16LE(at+32),attributes=bytes.readUInt32LE(at+38);
    if(flags&1||![0,8].includes(method)||((attributes>>>16)&0xf000)===0xa000||attributes&0x400)throw Error('ZIP_LINK_OR_ENCRYPTION');
    if(at+46+names+extra+comment>end)throw Error('INVALID_ZIP_ENTRY_SIZE');
    const raw=bytes.subarray(at+46,at+46+names);
    if(!(flags&0x800)&&raw.some(v=>v>127))throw Error('ZIP_NAME_ENCODING');
    const name=new TextDecoder('utf-8',{fatal:true}).decode(raw),components=name.replace(/\/$/,'').split('/');
    if(components[0]!=='lasermaker-agent'||name.includes('\\')||name.includes('\0')||components.some(p=>
      !p||p==='.'||p==='..'||/[<>:"|?*\x00-\x1f]/.test(p)||/[. ]$/.test(p)||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(p)))
      throw Error('UNSAFE_ZIP_PATH');
    const key=components.join('/').normalize('NFC').toLowerCase();
    if(seen.has(key))throw Error('ZIP_PATH_COLLISION');seen.add(key);
    total+=length;if(length>512*1024**2||total>2*1024**3)throw Error('ZIP_SIZE_LIMIT');
    at+=46+names+extra+comment;
  }
  if(at!==end)throw Error('INVALID_ZIP_DIRECTORY_SIZE');
  return {entries:count,uncompressedBytes:total};
}

export function parseArgs(args){
  const result={command:args[0]||'help',host:null,dir:null,profile:'laser'};
  if(['--help','-h'].includes(result.command))result.command='help';
  if(result.command==='--version')result.command='version';
  if(!['help','version','install','doctor','path','config','mcp'].includes(result.command))throw Error('UNKNOWN_COMMAND');
  for(let i=1;i<args.length;i++){
    const arg=args[i];
    if(['--dir','--profile'].includes(arg)){
      const value=args[++i];if(!value||value.startsWith('--'))throw Error('MISSING_OPTION_VALUE');
      result[arg.slice(2)]=value;
    }else if(result.command==='install'&&!result.host&&['codex','claude','kimi','deepseek'].includes(arg))result.host=arg;
    else throw Error('UNKNOWN_HOST_OR_OPTION');
  }
  if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(result.profile))throw Error('INVALID_PROFILE');
  return result;
}

export function hostCommands(host,root,profile='laser'){
  if(host==='codex')return [{command:'codex',args:['plugin','marketplace','add',root]},
    {command:'codex',args:['plugin','add','lasermaker-agent@lasermaker-local']}];
  if(host==='claude')return [{command:'claude',args:['plugin','install','lasermaker-agent','--marketplace',root,'--scope','user']}];
  if(host==='deepseek')return [{command:'dsh',args:['plugin','--profile',profile,'add',root]}];
  if(host==='kimi'||!host)return [];
  throw Error('UNKNOWN_HOST');
}

function powershell(script,payload){
  const data=Buffer.from(JSON.stringify(payload),'utf8').toString('base64');
  const code=`$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${data}')) | ConvertFrom-Json; ${script}`;
  return {command:path.join(process.env.SystemRoot||'C:\\Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),
    args:['-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(code,'utf16le').toString('base64')]};
}

export function powershellInvocation(command,args){
  return powershell('$callArgs=@($p.args); & $p.command @callArgs; if($null -ne $LASTEXITCODE){exit $LASTEXITCODE}',{command,args});
}

function runPS(script,payload,timeout=600000){
  const invocation=powershell(script,payload),result=spawnSync(invocation.command,invocation.args,
    {windowsHide:true,encoding:'utf8',timeout,maxBuffer:2*1024**2});
  if(result.error||result.status!==0)throw Error(`WINDOWS_HELPER_FAILED: ${result.error?.message||result.stderr?.trim()||result.status}`);
  return result.stdout;
}

async function download(url,destination,log){
  try{
    const response=await fetch(url,{signal:AbortSignal.timeout(600000)});
    if(!response.ok||!response.body)throw Error(`HTTP_${response.status}`);
    const final=new URL(response.url);
    if(final.protocol!=='https:'||!['github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'].includes(final.hostname))throw Error('UNEXPECTED_DOWNLOAD_ORIGIN');
    await pipeline(Readable.fromWeb(response.body),createWriteStream(destination,{flags:'wx'}));
  }catch(error){
    // Windows PowerShell uses the system proxy configuration. This also handles
    // installations where Node's fetch has no proxy configured.
    log('Retrying download with the Windows network configuration...');
    await fs.rm(destination,{force:true});
    runPS('Invoke-WebRequest -UseBasicParsing -Uri $p.url -OutFile $p.destination -TimeoutSec 600 -MaximumRedirection 5',{url,destination});
  }
}

async function probe(executable){
  const result=spawnSync(executable,['doctor'],{windowsHide:true,encoding:'utf8',timeout:60000,maxBuffer:1024**2});
  if(result.error||result.status!==0)throw Error(`RUNTIME_DOCTOR_FAILED: ${result.error?.message||result.stderr}`);
  return JSON.parse(result.stdout);
}

async function exists(p){try{await fs.lstat(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
async function directory(p){
  if(await exists(p)){const s=await fs.lstat(p);if(!s.isDirectory()||s.isSymbolicLink())throw Error('UNSAFE_INSTALL_DIRECTORY');}
  else await fs.mkdir(p,{recursive:true});
}

async function copyOverlay(source,destination){
  const copied={};
  async function visit(from,to){
    const s=await fs.lstat(from);if(s.isSymbolicLink())throw Error('SYMLINK_IN_INSTALLER_PACKAGE');
    if(s.isDirectory()){
      await fs.mkdir(to,{recursive:true});
      for(const name of await fs.readdir(from)){
        if(['node_modules','.git','__pycache__'].includes(name))continue;
        await visit(path.join(from,name),path.join(to,name));
      }
    }else{
      await fs.mkdir(path.dirname(to),{recursive:true});await fs.copyFile(from,to);
      copied[path.relative(destination,to)]=await sha256(to);
    }
  }
  for(const entry of overlayEntries)if(await exists(path.join(source,entry)))await visit(path.join(source,entry),path.join(destination,entry));
  return copied;
}

export async function ensureInstalled(options={}){
  const platform=options.platform||process.platform,arch=options.arch||process.arch;
  if(platform!=='win32'||arch!=='x64')throw Error('WINDOWS_X64_REQUIRED: this runtime operates the Windows desktop.');
  const manifest=options.manifest||JSON.parse(await fs.readFile(new URL('./manifest.json',import.meta.url),'utf8'));
  if(manifest.repository!==owner||!/^\d+\.\d+\.\d+$/.test(manifest.bundleVersion)||!/^v\d+\.\d+\.\d+$/.test(manifest.tag)||
    !/^lasermaker-agent-[\d.]+-plugin\.zip$/.test(manifest.asset)||![manifest.sha256,manifest.executableSha256,manifest.runtimeTreeSha256].every(v=>/^[a-f0-9]{64}$/.test(v)))throw Error('INVALID_INSTALLER_MANIFEST');
  const base=path.resolve(options.base||path.join(process.env.LOCALAPPDATA||path.join(os.homedir(),'AppData/Local'),'LaserMakerAgent'));
  const versions=path.join(base,'versions'),destination=path.join(versions,manifest.bundleVersion),root=path.join(destination,'lasermaker-agent');
  const executable=path.join(root,'runtime/lasermaker-agent.exe'),log=options.log||(s=>process.stderr.write(s+'\n'));
  await directory(base);await directory(versions);
  const lock=path.join(base,'.install.lock');let locked=false,temp=null;
  try{
    try{await fs.mkdir(lock);locked=true;}catch(e){if(e.code==='EEXIST')throw Error(`INSTALL_LOCKED: another installation may be running. Inspect ${path.join(lock,'owner.json')}; see the installation guide before removing a stale lock.`);throw e;}
    await fs.writeFile(path.join(lock,'owner.json'),JSON.stringify({pid:process.pid,createdAt:new Date().toISOString()}));
    if(await exists(destination)){
      if((await fs.lstat(destination)).isSymbolicLink()||!await exists(path.join(root,markerName)))throw Error('UNMANAGED_INSTALL_DIRECTORY: choose a different --dir.');
      const marker=JSON.parse(await fs.readFile(path.join(root,markerName),'utf8'));
      if(marker.owner!==owner||marker.bundleVersion!==manifest.bundleVersion||marker.archiveSha256!==manifest.sha256||
         await sha256(executable)!==manifest.executableSha256)throw Error('INSTALL_INTEGRITY_FAILED: existing files were preserved; choose a new --dir.');
      let runtime;
      try{runtime=await fingerprintRuntime(path.join(root,'runtime'));}catch{throw Error('INSTALL_INTEGRITY_FAILED: runtime dependencies are missing or unsafe.');}
      if(runtime.sha256!==manifest.runtimeTreeSha256)throw Error('INSTALL_INTEGRITY_FAILED: runtime dependencies changed; existing files were preserved.');
      for(const [relative,expected] of Object.entries(marker.overlay||{})){
        const target=path.resolve(root,relative);
        if(!target.startsWith(root+path.sep)||await sha256(target)!==expected)throw Error('INSTALL_INTEGRITY_FAILED: modified integration files were preserved.');
      }
      log(`Using cached LaserMaker Agent ${manifest.coreVersion}.`);
      return {root,executable,bundleVersion:manifest.bundleVersion,coreVersion:manifest.coreVersion,cached:true};
    }
    temp=path.join(base,'.setup-'+randomUUID());await fs.mkdir(temp);
    const archive=path.join(temp,'runtime.zip'),url=`https://github.com/${owner}/releases/download/${manifest.tag}/${manifest.asset}`;
    log(`Downloading the verified Windows runtime ${manifest.coreVersion} (first installation only)...`);
    await (options.download||((u,p)=>download(u,p,log)))(url,archive);
    if(await sha256(archive)!==manifest.sha256)throw Error('DOWNLOAD_CHECKSUM_MISMATCH');
    const check=validateZip(await fs.readFile(archive));log(`SHA-256 verified; extracting ${check.entries} files...`);
    const unpacked=path.join(temp,'unpacked');await fs.mkdir(unpacked);
    await (options.extract||((file,destination)=>runPS('Expand-Archive -LiteralPath $p.file -DestinationPath $p.destination -ErrorAction Stop',{file,destination})))(archive,unpacked);
    const staged=path.join(unpacked,'lasermaker-agent'),stagedExe=path.join(staged,'runtime/lasermaker-agent.exe');
    if(await sha256(stagedExe)!==manifest.executableSha256)throw Error('RUNTIME_EXECUTABLE_CHECKSUM_MISMATCH');
    const runtime=await fingerprintRuntime(path.join(staged,'runtime'));
    if(runtime.sha256!==manifest.runtimeTreeSha256)throw Error('RUNTIME_TREE_CHECKSUM_MISMATCH');
    const result=await (options.probe||probe)(stagedExe);
    if(!result.ok||result.result?.name!=='lasermaker-agent'||result.result.version!==manifest.coreVersion||!result.result.windows)throw Error('RUNTIME_DOCTOR_IDENTITY_MISMATCH');
    const overlay=await copyOverlay(options.packageRoot||packageRoot,staged);
    await fs.writeFile(path.join(staged,markerName),JSON.stringify({owner,bundleVersion:manifest.bundleVersion,coreVersion:manifest.coreVersion,
      archiveSha256:manifest.sha256,executableSha256:manifest.executableSha256,overlay},null,2)+'\n');
    await fs.rename(unpacked,destination);
    const pointer=path.join(base,'.current-'+randomUUID()+'.json');
    await fs.writeFile(pointer,JSON.stringify({root,bundleVersion:manifest.bundleVersion,coreVersion:manifest.coreVersion})+'\n');
    await fs.rename(pointer,path.join(base,'current.json'));
    log(`Installed to ${root}`);return {root,executable,bundleVersion:manifest.bundleVersion,coreVersion:manifest.coreVersion,cached:false};
  }finally{
    if(temp){if(path.dirname(temp)!==base||!path.basename(temp).startsWith('.setup-'))throw Error('UNSAFE_TEMP_CLEANUP');await fs.rm(temp,{recursive:true,force:true});}
    if(locked){if(path.dirname(lock)!==base||path.basename(lock)!=='.install.lock')throw Error('UNSAFE_LOCK_CLEANUP');await fs.rm(lock,{recursive:true,force:true});}
  }
}

export function selectExecutable(output){return output.trim().split(/\r?\n/).find(p=>/\.(exe|cmd)$/i.test(p));}

export function runHostCommand(command,args){
  let found;
  try{found=JSON.parse(runPS('@(Get-Command -Name $p.command -CommandType Application -All -ErrorAction Stop | ForEach-Object {$_.Source}) | ConvertTo-Json -Compress',{command},10000));}
  catch{throw Error(`HOST_CLI_NOT_FOUND: install ${command} first; the plugin files are already installed.`);}
  const executable=selectExecutable((Array.isArray(found)?found:[found]).join('\n'));
  if(!executable)throw Error('HOST_EXECUTABLE_NOT_FOUND');
  let invocation={command:executable,args};
  if(executable.toLowerCase().endsWith('.cmd')){
    if([executable,...args].some(a=>/["\r\n%!:^&|<>]/.test(a.replace(/^[A-Za-z]:/,'').replaceAll('/',path.sep))))
      throw Error('HOST_BATCH_PATH_UNSUPPORTED: choose --dir with ordinary letters, spaces or Unicode.');
    invocation=powershellInvocation(executable,args);
  }
  const child=spawnSync(invocation.command,invocation.args,{stdio:'inherit',windowsHide:true,timeout:180000});
  if(child.error||child.status!==0)throw Error(`HOST_SETUP_FAILED: ${command} exited ${child.status??child.error?.message}. Plugin files were preserved.`);
}

export async function forward(executable,args){
  const child=spawn(executable,args,{stdio:'inherit',windowsHide:true});
  return await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',code=>resolve(code??1));});
}
