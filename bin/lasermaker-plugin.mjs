#!/usr/bin/env node
import { parseArgs, ensureInstalled, hostCommands, runHostCommand, forward } from '../installer/core.mjs';

async function main(){
  const args=parseArgs(process.argv.slice(2));
  if(args.command==='version'){console.log('Installer/integration 0.1.3; Windows core 0.1.2');return 0;}
  if(args.command==='help'){
    console.log(`LaserMaker Plugin - Windows x64\n\nUsage:\n  lasermaker-plugin install [codex|claude|kimi|deepseek] [--dir PATH] [--profile laser]\n  lasermaker-plugin doctor\n  lasermaker-plugin config\n  lasermaker-plugin path\n  lasermaker-plugin mcp\n\nDownloads and verifies the portable runtime once. No Python or administrator access required.\nInstaller/integration package 0.1.3; verified Windows core 0.1.2.`);return 0;
  }
  const installed=await ensureInstalled({base:args.dir});
  if(args.command==='install'){
    for(const task of hostCommands(args.host,installed.root,args.profile))runHostCommand(task.command,task.args);
    if(args.host==='kimi')console.log(`Paste this into Kimi, then reload:\n/plugins install ${installed.root}\n/reload`);
    else console.log(args.host?`LaserMaker is installed for ${args.host}. Restart the host or open a new session.`:`LaserMaker installed. Run "lasermaker-plugin config" for a generic MCP configuration.`);
    return 0;
  }
  if(args.command==='path'){console.log(installed.root);return 0;}
  if(args.command==='config'){
    console.log(JSON.stringify({mcpServers:{lasermaker:{command:installed.executable,args:['mcp'],cwd:installed.root}}},null,2));return 0;
  }
  return await forward(installed.executable,[args.command]);
}
try{process.exitCode=await main();}catch(error){process.stderr.write(`LaserMaker: ${error.message}\n`);process.exitCode=1;}
