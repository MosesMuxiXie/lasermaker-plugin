import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { existsSync } from "node:fs";
import * as mcpClient from "@deepseek-ai/dsh-mcp-client";
import * as skillFilesystem from "@deepseek-ai/dsh-skill-filesystem";

export const name = "lasermaker-agent";
export const inject = ["tools", "skills"];

export async function apply(ctx) {
  const executable = fileURLToPath(new URL("../../runtime/lasermaker-agent.exe", import.meta.url));
  if (!existsSync(executable)) throw new Error("LaserMaker Windows runtime missing; install the complete release ZIP.");
  await ctx.plugin(skillFilesystem, {
    providerName: "lasermaker-agent",
    includeDefaultRoots: false,
    bundledSkillDir: fileURLToPath(new URL("../../skills/", import.meta.url)),
    watch: false,
  });
  await ctx.plugin(mcpClient, {
    serverName: "lasermaker",
    transport: "stdio",
    command: executable,
    args: ["mcp"],
    cwd: dirname(executable),
    toolCallTimeoutMs: 120000,
    failOnStartupError: true,
  });
}
