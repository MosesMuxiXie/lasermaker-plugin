# LaserMaker for Claude Code

[← Main README](../../README.md) · [Codex](../codex/README.md) · [Kimi Code](../kimi/README.md) · [DeepSeek Harness](../deepseek/README.md)

Use the native Claude Code plugin to load the LaserMaker MCP server and design workflow together. This guide is for the Windows **Claude Code CLI**.

## 1. Requirements

- Windows x64, Node.js 20+ with npm/npx, and Git.
- Claude Code and your normal model account/sign-in. Tested baseline: **2.1.310**. Check `claude --version` and `claude plugin install --help`.
- For GUI work: LaserMaker **2.1.7.2** at `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`, on an unlocked local desktop.

The shell `plugin install --marketplace` shortcut requires a sufficiently recent build; official documentation lists **2.1.292+**. The tested 2.1.310 build supports it. Setup does not configure model credentials. Integration version: **0.1.4**; verified Windows core: **0.1.2**.

## 2. Install in user scope

Run in PowerShell:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install claude
```

The installer downloads and verifies the portable runtime, adds its local marketplace, and invokes `claude plugin install` with the real plugin root and `--scope user`. No npm login, system Python, or administrator access is needed. The first download is about 140 MB. The Git-source opt-in applies only to this command; see the [installation guide](../../docs/installation.md).

User scope makes the plugin available across your Claude Code projects. Restart Claude Code or start a new session after setup.

## 3. Check the plugin and MCP connection

In PowerShell:

```powershell
claude plugin list --json
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
```

Find `lasermaker-agent@lasermaker-local` in the installed plugin list. `doctor` should report core version `0.1.2`. If `lasermaker_installed` is false, geometry tools remain usable, but GUI operations need the supported application installed.

Inside Claude Code, open `/mcp` and inspect the plugin's `lasermaker` server. Then ask:

```text
Use the installed LaserMaker plugin. Discover its MCP tools and call doctor.
Report the core version and application availability. Read the packaged
lasermaker-workflow skill before designing. Do not modify a drawing yet.
```

Expect **17 tools**. Use the names Claude actually discovers; MCP prefixes are host-specific. The workflow skill is under the plugin's `skills/` directory. Let Claude load it by relevance or inspect the displayed skill entry rather than guessing a slash-command name.

## 4. Design and verify a complete product

Keep source projects outside the plugin cache. Try:

```text
Use the LaserMaker workflow to create a new project at
D:/LaserProjects/claude-organizer for a detailed flat-pack organizer using
nominal 3 mm stock. First draw dimensioned disassembly plans and assembly
relationships. Reconstruct the contours, holes, tabs, slots, and outlined
labels from those plans using stable IDs and millimetres.

Include a separate fit coupon. Record unmeasured thickness/kerf as
assumptions, preflight, checkpoint, and export SVG/DXF with a report.

Before GUI work, report which tested layer parameters are still needed.
When they are supplied and the desktop is available, import, read back
dimensions and processes, save a new native lcpx, reopen its exact returned
path, and verify all used layers again. Export the verified delivery and
assembly instructions. Do not send or start a machine job.
```

Check this sequence:

1. `doctor`, then `create_project`, `open_project`, or `resume_project`.
2. `apply_design_ops`, `preflight`, and `checkpoint`.
3. `import_design`, verifying the expected **drawing** dimensions rather than the page width.
4. `set_layer_process` using operator-supplied tested settings, with actual readback.
5. `save_native`, `reload_and_verify` with its returned path, then `verify_layer_process` for every used color.
6. `checkpoint` and `export_delivery`; `close_verified_document` may then close the verified saved document.

Black/red are useful cut/score conventions; read back actual modes. Repository power/speed examples are not production presets. If simulation or ordering cannot be confirmed, deliver explicit engraving/score, inner-cut, and outer-cut stages. Review preflight errors, source revision, coupon, artifact paths, and native evidence separately from physical fit.

## 5. Resume or switch agents

In a later session, ask:

```text
Resume D:/LaserProjects/claude-organizer with resume_project. Report the latest
revision, pending operations, and external native-file changes before editing.
Use stored project state rather than reconstructing the design from this chat.
```

Keep the same absolute root when another agent takes over. `resume_project` does not roll back to a checkpoint. Replay timed-out geometry operations with the exact original request ID and payload, including the original `expected_revision`. Unknown GUI outcomes require inspecting the app, receipt, and artifacts before another edit; do not repeat imports with a new ID. Serialize desktop operations across agents.

## 6. Custom directory, offline setup, and temporary loading

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install claude --dir 'D:/Tools/LaserMaker'
```

Use the same `--dir` on later installer `doctor`, `path`, and `config` commands. The chosen base contains a versioned plugin root; `path` prints that root.

Without Node.js, download and checksum the complete plugin ZIP from [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest). For an extracted root at `D:/Tools/lasermaker-agent`:

```powershell
claude plugin validate 'D:/Tools/lasermaker-agent'
claude plugin install lasermaker-agent --marketplace 'D:/Tools/lasermaker-agent' --scope user
```

For temporary loading, start from your product workspace:

```powershell
claude --plugin-dir 'D:/Tools/lasermaker-agent'
```

Use one loading method per session to avoid duplicate servers. Keep `.claude-plugin/plugin.json`, `adapters/claude.mcp.json`, `skills/`, and the complete `runtime/` together. `${CLAUDE_PLUGIN_ROOT}` resolves the installed runtime automatically. A source-only archive lacks that runtime.

The installer's `config` command provides a generic stdio MCP alternative. That fallback alone is not proof of native plugin loading.

## 7. Troubleshooting and removal

- **Unknown `--marketplace`:** compare your CLI version/help with the tested build, or use its documented marketplace-add/install flow.
- **No server in `/mcp`:** restart, inspect `/plugin`, confirm enablement, and read the server startup diagnostics.
- **Different app and shell configuration:** check the Windows account and intended `CLAUDE_CONFIG_DIR`, if customized.
- **Missing runtime:** use the complete release ZIP or installer; do not move the EXE away from `_internal`.
- **`EALLOWGIT`, changed-cache, or stale-lock error:** follow [installation troubleshooting](../../docs/installation.md), preserving files.
- **Unknown GUI outcome, focus loss, or external edits:** stop that step, inspect existing state, and preserve user changes.

To remove the user-scoped plugin:

```powershell
claude plugin uninstall lasermaker-agent@lasermaker-local --scope user
```

Keep product sources and native files in their separate project directory. Removing an entire marketplace is unnecessary for this operation.

## Verification and references

The 0.1.3 installer completed native Claude plugin installation in isolated user configuration. The core baseline checked host-resolved stdio discovery and calls. These checks are separate from model-account product conversations and physical processing, which remain unverified.

See [official Claude Code installation](https://code.claude.com/docs/en/discover-plugins), [plugin overview](https://code.claude.com/docs/en/plugins), [release verification](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/tag/v0.1.4), and the [workflow skill](../../skills/lasermaker-workflow/SKILL.md). Commands were also checked against the installed 2.1.310 help.
