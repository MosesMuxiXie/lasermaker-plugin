# LaserMaker for DeepSeek Harness

[← Main README](../../README.md) · [Codex](../codex/README.md) · [Claude Code](../claude/README.md) · [Kimi Code](../kimi/README.md)

This adapter is a native Cordis bundle. It loads the shared skills and official `@deepseek-ai/dsh-mcp-client` against the bundled Windows executable, resolved relative to the installed adapter.

## 1. Requirements and profile selection

- Windows x64, Node.js 20+ with npm/npx, Git, and a working `dsh` CLI.
- Tested baseline: **DeepSeek Harness 0.2.1-rc.2 / Cordis 4.0.5**. Check `dsh --version` and `dsh plugin --help`.
- A profile supplying the Harness `tools` and `skills` services, compatible MCP/skill peer packages, and the usual model/system-prompt services for conversations.
- For GUI operations: LaserMaker **2.1.7.2** at `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`, with an unlocked local desktop.

The installer defaults to a profile named **`laser`**. If you normally use another profile, select that profile explicitly. Initializing a profile or adding a package does not by itself provide all the services needed for chat and tool dispatch. This installer does not configure model accounts or build a complete Harness profile.

Integration version: **0.1.3**; verified Windows core: **0.1.2**. The peer versions are declared in [package.json](../../package.json); resolve them in the Harness environment when using this adapter. They are optional for the standalone Node downloader.

## 2. Install into the intended profile

Run in PowerShell:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install deepseek
```

For an existing profile named `desktop`, use:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install deepseek --profile desktop
```

Choose one command for your intended profile. The installer downloads/verifies the portable runtime, then invokes `dsh plugin --profile NAME add ROOT`. The first download is about 140 MB. No npm login, system Python, or administrator access is required. The Git-source opt-in is explained in the [installation guide](../../docs/installation.md).

The CLI delegates package management to the selected profile. Preserve its existing composition and resolve reported peer/service requirements there. Restart that profile after installation if its runtime does not apply the change automatically.

## 3. Confirm configuration, activation, and tools

For the default profile:

```powershell
dsh --profile laser --dump-config
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
```

Use your chosen profile name consistently. Inspect the resolved configuration for the `dsh-plugin-lasermaker` bundle and `lasermaker-agent` entry. Start the same profile through your normal Harness entry point, and check startup diagnostics for the MCP server named `lasermaker`.

In a conversation, ask:

```text
Use the installed LaserMaker bundle. Discover its MCP tools and call doctor.
Report the core version, whether LaserMaker is installed, and whether the
lasermaker-workflow skill is available. Do not modify a drawing yet.
```

Expect **17 tools**. Use discovered names: the adapter registers them through the host MCP client, so do not invent a prefix. `doctor` reports core `0.1.2`. A false `lasermaker_installed` value permits geometry-only work but excludes GUI operations until the supported application is installed.

A successful package-add command is different from successful bundle activation or model tool dispatch. Confirm all three separately.

## 4. Build a complete product

Store your design outside the profile's `node_modules` and the plugin installation. Try:

```text
Use the LaserMaker workflow to create a new project at
D:/LaserProjects/deepseek-organizer for a detailed flat-pack organizer using
nominal 3 mm stock. First draw dimensioned disassembly plans and assembly
relationships, then reconstruct contours, holes, tabs, slots, and outlined
labels from those plans with stable object IDs and millimetres.

Create a separate fit coupon. Record unmeasured thickness/kerf as assumptions.
Preflight, checkpoint, and export SVG/DXF and a verification report.

List the tested layer parameters still needed before GUI work. Once supplied
and the desktop is available, import, read back drawing dimensions and actual
process settings, save a new native lcpx, reopen the exact returned path,
verify every used layer again, and export the delivery and assembly guide.
Do not send or start a machine job.
```

Review the tool sequence:

1. `doctor` and `create_project` / `open_project` / `resume_project`.
2. `apply_design_ops`, then `preflight` and `checkpoint`.
3. `import_design`, verifying expected **drawing** width/height rather than page width.
4. `set_layer_process` using tested operator-supplied values and actual GUI readback.
5. `save_native`, `reload_and_verify` with its returned path, and `verify_layer_process` for every used layer.
6. `checkpoint` and `export_delivery`; close the verified saved document with `close_verified_document` if needed.

Color conventions do not prove a process mode. Physical fit and machine parameters require on-site testing. If ordering or simulation cannot be verified, deliver separate engraving/score, inner-cut, and outer-cut stages with explicit operating order.

## 5. Resume across profiles, sessions, or agents

The same absolute project root is portable across hosts that can access it. Ask:

```text
Resume D:/LaserProjects/deepseek-organizer with resume_project. Report the
latest revision, pending operations, and external native-file changes before
editing. Continue from durable project state rather than conversation memory.
```

`resume_project` returns the latest state, not an automatic checkpoint rollback. For a timed-out geometry edit, replay the exact original request ID, payload, and original `expected_revision`. Unknown GUI outcomes require inspecting the app, receipt, and artifacts before another edit; never blindly repeat an import. Keep desktop operations sequential across profiles and agents.

## 6. Custom directory and offline installation

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install deepseek --profile laser --dir 'D:/Tools/LaserMaker'
```

Use the same `--dir` with subsequent installer `doctor`, `path`, and `config` commands, and the intended profile name for native Harness management.

Without the Node installer, extract and checksum the complete plugin ZIP from [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest). Harness itself still needs its Node environment. For an extracted root at `D:/Tools/lasermaker-agent`:

```powershell
dsh plugin --profile laser add 'D:/Tools/lasermaker-agent'
dsh --profile laser --dump-config
```

Keep `package.json`, `adapters/deepseek/index.js`, `adapters/deepseek/cordis.patch.yml`, `skills/`, and the complete `runtime/` together. The adapter computes the executable path relative to itself; moving only the JS file or EXE breaks that layout. Source archives do not include the portable runtime.

The installer's `config` command can instead provide a generic stdio MCP entry for an existing host bridge. Avoid connecting that entry and the native bundle simultaneously. Generic MCP configuration is separate from native bundle loading.

## 7. Troubleshooting and removal

- **Installed in the wrong profile:** inspect the profile selected by your actual launcher; installation and startup must target the same profile.
- **Package added but no tools:** inspect bundle selection, startup diagnostics, and the `tools`/`skills` services. Package-manager success alone does not establish runtime activation.
- **Missing peer package or injected service:** resolve the compatible packages and services declared by the adapter/profile. Do not treat disabled compatibility checks as a repair.
- **Runtime path missing:** use the complete ZIP or installer and preserve the bundle layout.
- **`EALLOWGIT`, changed-cache, or lock error:** follow the [installation recovery guide](../../docs/installation.md).
- **Unknown dialog, focus loss, or external native edit:** preserve state and reconcile the operation before more GUI work.

To remove the package from the default profile:

```powershell
dsh plugin --profile laser remove dsh-plugin-lasermaker
```

Use your actual profile name, restart that profile as needed, and keep product projects outside its managed package directories.

## Verification and references

The core baseline checked native DeepSeek bundle loading, 17-tool discovery, and actual dispatch without a model-account conversation. The 0.1.3 installer tests cover the new profile/add argument construction; the new installer shortcut is not claimed as a separately completed DeepSeek model end-to-end run. Physical processing remains unverified.

See the official [Harness repository](https://github.com/deepseek-ai/deepseek-harness), [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md), and [profile plugin manager](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/boot/plugin-manager/README.md). CLI forwarding syntax was checked with the installed 0.2.1-rc.2 help. Also see [core validation](../../docs/验证报告.md) and the [workflow skill](../../skills/lasermaker-workflow/SKILL.md).
