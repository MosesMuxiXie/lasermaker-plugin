# LaserMaker for Kimi Code

[← Main README](../../README.md) · [Codex](../codex/README.md) · [Claude Code](../claude/README.md) · [DeepSeek Harness](../deepseek/README.md)

Kimi Code loads the native `kimi.plugin.json`, shared workflow skill, and local stdio MCP server. File installation and in-session activation are separate steps.

## 1. Requirements

- Windows x64, Node.js 20+ with npm/npx, and Git.
- Kimi Code with the `/plugins` interface and your normal model account. Tested baseline: **2.3.2**. Check your CLI version before following this guide.
- For GUI operations: LaserMaker **2.1.7.2** at `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`, with an unlocked local desktop.

This guide targets the `kimi.plugin.json` / `/plugins` interface. If your build exposes a different plugin format or only legacy commands, compare it with the supported baseline and its own documentation. Integration version: **0.1.3**; pinned Windows core: **0.1.2**. Setup does not supply a model account.

## 2. Download and install the files

Run in PowerShell:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install kimi
```

The installer downloads and verifies the portable runtime and prints the exact local root. The first download is about 140 MB. No npm login, system Python, or administrator access is required. See [installation details](../../docs/installation.md) for the per-command Git-source opt-in and cache behavior.

**This step does not automatically activate the Kimi plugin.** Copy the exact commands printed by the installer into Kimi Code. For example, if your actual root were `D:/Tools/lasermaker-agent`, the in-session commands would be:

```text
/plugins install D:/Tools/lasermaker-agent
/reload
```

Use the printed path, not the example path. For a path containing spaces that your build parses ambiguously, open `/plugins` and enter the full local path in its installation interface.

Use the installer or the full release ZIP. Installing this repository's source alone does not supply the portable runtime required by the manifest.

## 3. Check enablement and tool discovery

Inside Kimi Code:

```text
/plugins list
/plugins info lasermaker-agent
```

Inspect the plugin diagnostics. If the plugin or its MCP server is disabled, explicitly enable them and reload:

```text
/plugins enable lasermaker-agent
/plugins mcp enable lasermaker-agent lasermaker
/reload
```

Then ask:

```text
Use the installed LaserMaker plugin. Discover its MCP tools and call doctor.
Report the core version and whether LaserMaker is installed. Read the
lasermaker-workflow skill. Do not modify a drawing yet.
```

Expect **17 tools**, with names discovered from Kimi rather than guessed prefixes. `doctor` reports core version `0.1.2`. A false `lasermaker_installed` value permits geometry-only work, but GUI operations need the supported application installed.

You can also check the runtime from PowerShell:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
```

## 4. Build a detailed product

Keep the editable project outside Kimi's managed plugin directory. Try this request:

```text
Use the LaserMaker workflow to create a new project at
D:/LaserProjects/kimi-organizer for a detailed flat-pack desk organizer
using nominal 3 mm sheet stock. Draw dimensioned disassembly plans first,
including assembly relationships. Reconstruct the contours, holes, tabs,
slots, and outlined labels from those plans using stable IDs and millimetres.

Create a separate fit coupon. Record unmeasured thickness and kerf as
assumptions. Preflight, checkpoint, and export SVG/DXF with a report.

List the tested process parameters still needed before GUI work. Once
supplied and the desktop is available, import, read back drawing dimensions
and actual layer modes/settings, save a native file, reopen the exact
returned path, and verify every used layer again. Export source, native
project, assembly instructions, and verification evidence. Do not start a job.
```

The agent should use `create_project` / `open_project`, `apply_design_ops`, `preflight`, and `checkpoint` for source work. Native verification then uses `import_design`, `set_layer_process`, `save_native`, `reload_and_verify`, and `verify_layer_process`, followed by `checkpoint` and `export_delivery`.

Check the drawing dimensions, not just the page size. Black/red conventions do not prove cut/score mode; actual settings must be read back. Use operator-supplied tested process values. If simulation or machine ordering cannot be confirmed, request separate engraving/score, inner-cut, and outer-cut stages. A geometry pass does not establish physical fit.

## 5. Resume and understand managed copies

Kimi copies local plugin installations into its managed plugin area. Editing the original extracted directory does not update that managed copy; reinstall and `/reload` when intentionally replacing the plugin. Keep the original portable layout intact, including the EXE and `_internal` directory.

Product state belongs in your project directory. In a new Kimi session or another host, ask:

```text
Resume D:/LaserProjects/kimi-organizer with resume_project. Report the latest
revision, pending operations, and external native-file changes before editing.
Continue from stored project state, not this conversation's memory.
```

`resume_project` returns the latest revision rather than rewinding to a checkpoint. For timed-out geometry edits, replay the exact original request ID, payload, and original `expected_revision`. For an unknown GUI outcome, inspect the existing app, receipt, and files; do not blindly repeat imports. Let only one agent operate the desktop at a time.

## 6. Custom directory and offline setup

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install kimi --dir 'D:/Tools/LaserMaker'
```

Paste the newly printed versioned root into Kimi's `/plugins install` command, then `/reload`. Use the same `--dir` for later installer `doctor`, `path`, and `config` commands.

Without Node.js, download and checksum the **complete plugin ZIP** from [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest), extract it, and install the extracted root through `/plugins install`. It must contain `kimi.plugin.json`, `skills/`, and the complete `runtime/`. A source-only archive is insufficient.

The installer's `config` command offers a generic stdio MCP alternative. Choose either that connection or the plugin-declared server to avoid duplicate tools; generic MCP alone does not prove native plugin installation.

## 7. Troubleshooting and removal

- **Files installed but no tools:** complete the in-session installation and `/reload`; then inspect `/plugins info lasermaker-agent`.
- **Plugin enabled but MCP disabled:** enable the `lasermaker` server explicitly with the command above, then reload.
- **Reinstalled source changes seem ignored:** inspect the managed copy and reinstall; changing the original directory alone has no effect.
- **Runtime path error:** use the complete ZIP or installer and preserve relative paths; do not point Kimi at a source-only checkout.
- **`EALLOWGIT`, changed-cache, or stale lock:** follow the [installation recovery guide](../../docs/installation.md).
- **Unknown dialog, focus loss, or external native change:** preserve the project and inspect operation records before any further GUI edit.

To stop using the plugin, run `/plugins disable lasermaker-agent` and `/reload`. To remove its installation record, run `/plugins remove lasermaker-agent` and follow Kimi's confirmation. Keep your product projects separate from the plugin's managed files.

## Verification and references

The Kimi Code 2.3.2 baseline checked native manifest loading, tool discovery, and host-resolved stdio calls. The Node installer prints the required interactive commands; it does not claim automatic Kimi activation. Model-account product conversations and physical processing remain unverified.

See [official Kimi Code plugin documentation](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/plugins.md), [core validation](../../docs/验证报告.md), the [workflow skill](../../skills/lasermaker-workflow/SKILL.md), and [API/recovery](../../docs/接口与恢复.md).
