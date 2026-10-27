# LaserMaker for Codex

[← Main README](../../README.md) · [Claude Code](../claude/README.md) · [Kimi Code](../kimi/README.md) · [DeepSeek Harness](../deepseek/README.md)

Create precise laser-cutting geometry and operate local Windows LaserMaker through Codex's native plugin, MCP tools, and packaged workflow skill.

## 1. Requirements

- Windows x64, Node.js 20+ with npm/npx, and Git.
- A working Windows Codex CLI. Tested baseline: **0.164.0**. Check `codex --version` and `codex plugin --help`.
- Your normal Codex sign-in for model conversations; setup does not configure a model account.
- For GUI work: LaserMaker **2.1.7.2** at `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`, with the local desktop unlocked.

The installer/integrations are **0.1.3**; the verified Windows core remains **0.1.2**. Geometry-only work can start without LaserMaker. GUI tools operate this Windows computer; use a local executor when working in Desktop.

## 2. Install

Run in PowerShell:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install codex
```

The command downloads and verifies the portable runtime, registers the `lasermaker-local` marketplace, and installs `lasermaker-agent@lasermaker-local`. The first download is about 140 MB. No system Python or npm login is required. The Git-source opt-in applies only to this command; see the [installation guide](../../docs/installation.md).

Restart Codex or start a new session. For Desktop, inspect plugin enablement in the app. The CLI checks below are the tested baseline; Desktop labels can vary.

## 3. Confirm the runtime and tools

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
codex plugin list --json
```

Find `lasermaker-agent` under `lasermaker-local`. `doctor` should identify the core as `lasermaker-agent`, version `0.1.2`. If `lasermaker_installed` is false, geometry tools remain usable, but GUI operations need the supported application installed.

In a new Codex conversation, send:

```text
Use the installed LaserMaker plugin. Discover its tools and call doctor.
Report the core version and whether LaserMaker is installed. Read the
lasermaker-workflow skill. Do not open or modify a drawing yet.
```

Expect **17 MCP tools**. Use the names actually exposed by Codex; do not guess a host prefix. A successful installation or `doctor` call does not prove GUI or physical processing has passed.

## 4. Build a complete product

Keep product projects outside the plugin cache. Give Codex this task:

```text
Use the LaserMaker workflow to create D:/LaserProjects/desk-organizer as a
new project for a flat-pack organizer, approximately 160 x 100 x 100 mm,
using nominal 3 mm stock. First produce dimensioned disassembly plans and
assembly relationships. Reconstruct the base, walls, divider, tabs, slots,
and outlined labels from those plans with stable IDs and millimetres.

Include a separate fit coupon. Record unmeasured thickness and kerf as
assumptions. Preflight, checkpoint, and export SVG/DXF and a report.

Keep GUI work as a separate stage. Once I supply tested process settings
and the desktop is available, import, read back drawing dimensions and
layer processes, save a new native file, reopen its exact returned path,
verify all used processes again, and export the delivery package with
assembly instructions. Do not send or start a machine job.
```

Check that Codex follows this sequence:

1. `doctor`, then `create_project`, `open_project`, or `resume_project` as appropriate.
2. `apply_design_ops`, `preflight`, and `checkpoint` for precise source work.
3. `import_design` and readback of the expected **drawing** width/height, rather than sheet width.
4. `set_layer_process` using tested operator-supplied settings. Color alone does not establish a process mode.
5. `save_native`, then `reload_and_verify` with the **returned path**, followed by `verify_layer_process` for each used layer.
6. `checkpoint` and `export_delivery`. Use `close_verified_document` only after successful save/reopen verification.

Review the source revision, preflight results, artifact paths, coupon, and native verification evidence. If simulation or ordering cannot be confirmed, deliver engraving/score, inner-cut, and outer-cut stages with explicit operating order. Physical fit and machine settings still require on-site testing.

## 5. Resume across sessions or agents

Keep the same absolute project root. In a later conversation, ask:

```text
Resume D:/LaserProjects/desk-organizer with resume_project. Report the latest
revision, pending operations, and external native-file changes before editing.
Continue from durable state, not from a reconstruction of this chat.
```

`resume_project` returns the latest state; it does not rewind to a checkpoint. For a timed-out geometry edit, replay the exact original request ID, arguments, and original `expected_revision`. Unknown GUI outcomes require inspecting the app, receipt, and files before continuing; do not blindly repeat imports. Run desktop operations sequentially across agents.

## 6. Custom directory, offline setup, and MCP fallback

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install codex --dir 'D:/Tools/LaserMaker'
```

Use the same `--dir` with later `doctor`, `path`, and `config` commands. The installer creates a versioned plugin root beneath the chosen base.

Without Node.js, extract and checksum the **complete plugin ZIP** from [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest). For an extracted root at `D:/Tools/lasermaker-agent`:

```powershell
codex plugin marketplace add 'D:/Tools/lasermaker-agent'
codex plugin add lasermaker-agent@lasermaker-local
codex plugin list --json
```

The root needs `plugin.json`, `mcp.json`, `.agents/plugins/marketplace.json`, `skills/`, and the complete `runtime/`. A source checkout has no portable runtime.

The installer's `config` command prints the exact executable and working directory for a generic stdio MCP host. This is an alternative to native plugin loading; avoid registering the same server twice.

## 7. Troubleshooting and removal

- **CLI not found or `plugin` unavailable:** check the Windows CLI installation, version, and help. Downloaded plugin files are preserved if host setup fails.
- **Marketplace exists at another location:** inspect `codex plugin marketplace list`. Keep its source, or intentionally replace that registration after removing this plugin. Repeatedly choosing new directories will not fix a marketplace name collision.
- **No tools:** restart, inspect plugin enablement and MCP diagnostics, and check that the app and installation shell use the same Windows account and intended Codex configuration.
- **`EALLOWGIT`:** retain `--allow-git=root` in npm/npx commands.
- **Integrity/lock error:** preserve files and follow the [cache and lock guide](../../docs/installation.md#interrupted-installation).
- **Focus loss, unknown dialog, or external native edit:** preserve the document and inspect recorded state. Do not reimport over user changes.

To uninstall:

```powershell
codex plugin remove lasermaker-agent@lasermaker-local
```

If the marketplace is no longer used, remove its registration separately with `codex plugin marketplace remove lasermaker-local`. Codex removes its installed plugin cache; keep your design projects in a separate project directory.

## Verification and references

Codex 0.164.0 native loading/dispatch passed in the core baseline. The 0.1.3 installer also passed a fresh-cache GitHub-backed npx download/install into a Unicode directory with isolated Codex configuration. Two installed MCP restarts each exposed 17 tools and called `doctor`. Model-account product conversations and physical cutting remain unverified.

See [official OpenAI plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins), [release verification](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/tag/v0.1.3), the [workflow skill](../../skills/lasermaker-workflow/SKILL.md), and [API/recovery](../../docs/接口与恢复.md). Command syntax was also checked against the installed 0.164.0 CLI help.
