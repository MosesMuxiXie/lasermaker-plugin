# Easy installation and English documentation

The user requested an English default README and a simpler npm/npx installation path, with alternatives if npm publishing is unavailable. npm credentials are unavailable; public GitHub package specs are supported by npm exec, so the primary command will be `npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install codex`.

Ruling: keep the already verified Python/Windows runtime at 0.1.2 and version the installer/integration package as 0.1.3. No geometry or machine-control behavior changes. The installer pins the original release ZIP and executable SHA-256 and overlays only the new integration files and bilingual documentation.

Implementation: a dependency-free Node 20+ CLI, optional DeepSeek peer dependencies, per-user versioned installation, bounded HTTPS download, ZIP path/link validation before PowerShell extraction, exact runtime hash/doctor verification, an exclusive install lock, atomic publication, and refusal to replace an unknown directory. Cached installs do not download again. All progress goes to stderr so the `mcp` command preserves stdio.

Host setup uses official CLIs: Codex marketplace add/install, Claude marketplace install, DeepSeek profile add. Kimi receives one explicit slash command because its stable installation interface is interactive. No model prompts, security settings, administrator permissions or laser jobs are involved.

Verification: failing Node tests first; ZIP and integrity/ownership failures; real release download and cached reuse; installed 17-tool MCP call; native host setup in isolated homes; npm pack content/privacy checks; GitHub-backed npx after publication; Python regression tests. Keep Chinese README and offline ZIP fallback. Publish only after checks and one read-only review.

Primary references: https://docs.npmjs.com/cli/v12/commands/npm-exec/ ; https://docs.npmjs.com/cli/v12/using-npm/package-spec/ ; https://docs.npmjs.com/cli/v12/configuring-npm/package-json/ ; https://nodejs.org/api/child_process.html .

Live verification found npm 12's default `allow-git=none` (`EALLOWGIT`). The published commands explicitly use `--allow-git=root` for this invocation, with no persistent npm configuration change. A fresh-cache GitHub-backed npx version check passed with this opt-in; HTTPS tarballs are also opt-in on npm 12, so they do not simplify the command.
