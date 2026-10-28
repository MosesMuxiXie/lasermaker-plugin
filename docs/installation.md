# Installation

For a complete walkthrough of your host, choose [Codex](../adapters/codex/README.md), [Claude Code](../adapters/claude/README.md), [Kimi Code](../adapters/kimi/README.md), or [DeepSeek Harness](../adapters/deepseek/README.md). These guides include product prompts, native verification, resuming work, and host-specific troubleshooting.

## Recommended: one command

On **Windows x64**, install Node.js 20+ (including npm/npx), Git, and your preferred agent CLI. Then choose a host:

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install codex
# or: install claude / install deepseek / install kimi
```

No npm login, system Python, administrator access, manual ZIP extraction, or hand-written executable path is required. The package is fetched directly from this public GitHub repository; it is **not an npm-registry package**. The download is about 140 MB on the first installation. Repeated installation reuses the verified cache.

npm 12 disables Git dependencies by default. `--allow-git=root` is an explicit opt-in for the requested package in this command; it does not change persistent npm settings or enable dependency lifecycle scripts. Omitting it on npm 12 produces `EALLOWGIT`. See the official [npm source policy](https://docs.npmjs.com/cli/v12/commands/npm-install/#allow-git).

The installer/integration package is **0.1.4**. It uses the unchanged, tested **0.1.2 Windows runtime**. The original release ZIP, executable, and the complete 905-file runtime tree are pinned by SHA-256. A cached install checks all runtime files before reuse. `doctor` therefore reports runtime version `0.1.2`.

### What each host command does

- **Codex:** registers the local marketplace and installs `lasermaker-agent@lasermaker-local`. Restart Codex or open a new session.
- **Claude Code:** uses the native `claude plugin install --marketplace ... --scope user` command. Restart or open a new session, then inspect `/mcp`.
- **DeepSeek Harness:** installs the native bundle into the `laser` profile. Use `--profile NAME` to select another profile; the profile must already provide the Harness tool/skill/MCP services. The 0.1.4 integration declares `engines.dsh` as `>=0.2.1-rc.2 <0.3.0`; installation was checked on 0.2.1-rc.3.
- **Kimi Code:** installs the files, then prints `/plugins install <exact path>` and `/reload` for the Kimi conversation. This interactive step is required; it is not reported as automatic plugin activation.

Existing unrelated host configuration and project files are not overwritten. A running installation, unknown destination, or changed cached executable produces a clear error. Choose a fresh `--dir` if a prior installation was modified; files are preserved.

## Useful commands

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin path
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin config
```

`config` prints a ready-to-paste generic stdio MCP configuration with the exact installed executable path. `mcp` forwards stdio to the verified runtime; progress messages are sent only to stderr. Install once before configuring a host to avoid its startup timeout during the initial download.

Default location: `%LOCALAPPDATA%/LaserMakerAgent/versions/0.1.4/lasermaker-agent`. Override the installation base with `--dir 'D:/Tools/LaserMaker'` on any command. Use the same `--dir` for later commands.

Prefer a global command?

```powershell
npm install -g --allow-git=root github:MosesMuxiXie/lasermaker-plugin
lasermaker-plugin install codex
```

The DeepSeek peer packages are optional for the downloader; they are supplied by the DeepSeek host when that adapter is used. The installer has no third-party JavaScript runtime dependencies or automatic postinstall script.

## Without Node.js: offline ZIP

Download `lasermaker-agent-0.1.4-plugin.zip` from [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest), verify it against `SHA256SUMS.txt`, and extract it into a fixed directory. The directory containing `plugin.json` is the plugin root.

For Codex, run these two commands with that root:

```powershell
codex plugin marketplace add 'D:/Tools/lasermaker-agent'
codex plugin add lasermaker-agent@lasermaker-local
```

For Claude, run `claude plugin install lasermaker-agent --marketplace 'D:/Tools/lasermaker-agent' --scope user`. For Kimi, use `/plugins install D:/Tools/lasermaker-agent`. For DeepSeek, use `dsh plugin --profile laser add 'D:/Tools/lasermaker-agent'`.

The ZIP contains Python. The GitHub automatic source archive and the npm installer tarball do not contain Python; the latter downloads it on demand.

## LaserMaker and validation

GUI operations require LaserMaker **2.1.7.2**, installed at `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`, and an unlocked local desktop. Geometry tools can be used before LaserMaker is installed. Save your work and handle any recovery dialog before automation.

This installer does not alter machine settings or run a laser job. Runtime geometry/UI verification, physical fit, and actual processing are separate checks. See the [validation report](验证报告.md). No model account or provider credential is used by setup.

## Interrupted installation

If setup is terminated during download, its lock may remain. The error prints the exact `owner.json` path. Close other installers first; inspect the recorded PID and keep the lock while that process still exists. Do not delete the installation directory or your projects.

For the default installation base, the following removes **only an abandoned lock**. For a custom `--dir`, use its `.install.lock` path instead. If the owner record is missing, malformed, or the directory contains unexpected files, preserve it and choose a new `--dir`.

```powershell
$setupLock = Join-Path $env:LOCALAPPDATA 'LaserMakerAgent/.install.lock'
$setupOwnerFile = Join-Path $setupLock 'owner.json'
$setupOwner = Get-Content -LiteralPath $setupOwnerFile -Raw | ConvertFrom-Json
if (!$setupOwner.pid -or (Get-Process -Id $setupOwner.pid -ErrorAction SilentlyContinue)) {
    throw 'Keep the lock: its owner is running or could not be established.'
}
$setupLockFiles = @(Get-ChildItem -LiteralPath $setupLock -Force)
if ($setupLockFiles.Count -ne 1 -or $setupLockFiles[0].Name -ne 'owner.json') {
    throw 'Unexpected lock contents: preserve them and use a new --dir.'
}
Remove-Item -LiteralPath $setupOwnerFile
Remove-Item -LiteralPath $setupLock
```

Then repeat the original installation command. No recursive delete or execution-policy change is needed.

The GitHub package syntax and optional peers follow the official [npm package spec](https://docs.npmjs.com/cli/v12/using-npm/package-spec/), [npm exec](https://docs.npmjs.com/cli/v12/commands/npm-exec/), and [package.json](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/) documentation.
