// Native Cordis + official dsh-mcp-client smoke; no model/provider is instantiated.
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, writeFileSync, readFileSync, copyFileSync, symlinkSync, existsSync, lstatSync, rmdirSync } from "node:fs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const host = resolve(root, "work/hosts");
const stage = resolve(root, "work/宿主插件 ref-v10 path");
const fromHost = createRequire(resolve(host, "package.json"));
const load = (name) => import(pathToFileURL(fromHost.resolve(name)).href);
const { Context } = await load("@deepseek-ai/cordis");
const { default: SystemPrompt } = await load("@deepseek-ai/dsh-system-prompt");
const { default: Tools } = await load("@deepseek-ai/dsh-tools");
const { default: Skills } = await load("@deepseek-ai/dsh-skill");
const adapterDir = resolve(stage, "adapters/deepseek");
mkdirSync(adapterDir, { recursive: true });
for (const file of ["index.js", "cordis.patch.yml"]) {
  copyFileSync(resolve(root, "adapters/deepseek", file), resolve(adapterDir, file));
}
// Only the isolated test copy receives a dependency junction. Release files do not.
const dependencyLink = resolve(adapterDir, "node_modules");
if (!existsSync(dependencyLink)) symlinkSync(resolve(host, "node_modules"), dependencyLink, "junction");
const adapter = await import(pathToFileURL(resolve(adapterDir, "index.js")).href);
const ctx = new Context();
let report;
try {
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(Tools, { mode: "native" });
  await ctx.plugin(Skills);
  await ctx.plugin(adapter);
  const tools = ctx.tools.schemas();
  const doctor = tools.find((tool) => tool.name === "mcp__lasermaker__doctor");
  if (!doctor) throw new Error("Native tool discovery failed");
  const skill = (await ctx.skills.list()).find((entry) => entry.name === "lasermaker-workflow");
  if (!skill) throw new Error("Shared Skill was not mounted");
  const result = await ctx.tools.execute({ callId: "native-smoke-doctor", name: doctor.name,
    arguments: {}, signal: AbortSignal.timeout(30000) });
  if (result.isError) throw new Error(JSON.stringify(result));
  if (tools.filter(t=>t.name.startsWith('mcp__lasermaker__')).length!==17) throw new Error('Expected 17 tools');
  const project = JSON.parse(readFileSync(resolve(root,'work/host-handoff-project.json'),'utf8')).root;
  async function call(name, args) {
    const r = await ctx.tools.execute({callId:'handoff-'+name, name:'mcp__lasermaker__'+name,
      arguments:args,signal:AbortSignal.timeout(30000)});
    if(r.isError)throw new Error(JSON.stringify(r));
    return r.value.structuredContent;
  }
  const resumed = await call('resume_project',{root:project});
  if(![1,2].includes(resumed.revision))throw new Error('Unexpected handoff revision');
  const editArgs = {root:project,request_id:'deepseek-native-duplicate-001',expected_revision:1,
    operations:[{op:'duplicate',ids:resumed.design.objects.filter(o=>o.part_id==='P').map(o=>o.id),dx:75,dy:0,suffix:'-copy'}]};
  const edited = await call('apply_design_ops',editArgs);
  const replay = await call('apply_design_ops',editArgs);
  if(edited.revision!==2||JSON.stringify(edited)!==JSON.stringify(replay))throw new Error('Duplicate replay mismatch');
  const preflight = await call('preflight',{root:project});
  if(!preflight.geometry_passed||preflight.part_count!==2)throw new Error(JSON.stringify(preflight));
  const handoff = {resumed_revision:resumed.revision,edited,replay,preflight};
  report = { passed: true, host: "DeepSeek Harness", version: "0.2.1-rc.2", model_turn_executed: false,
    tools: tools.map((tool) => tool.name), skill, result, handoff };
} catch (error) {
  report = { passed: false, error: String(error), stack: error.stack, model_turn_executed: false };
} finally {
  await ctx.fiber.dispose();
  if (lstatSync(dependencyLink).isSymbolicLink()) rmdirSync(dependencyLink);
}
writeFileSync(resolve(root, "work/host-deepseek-native.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({ passed: report.passed, error: report.error, tool_count: report.tools?.length,
  skill: report.skill?.name }));
process.exitCode = report.passed ? 0 : 1;
