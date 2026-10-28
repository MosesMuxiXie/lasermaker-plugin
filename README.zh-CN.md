# LaserMaker 插件

[English](README.md)

**从尺寸设计到原生工程核验，四种 Agent 共用同一套绘图与续作流程。**

[安装](#一条命令安装) · [各 Agent 教程](#选择你的-agent) · [产品样例](#功能与样例) · [下载](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest)

为 Codex、Claude Code、Kimi Code、DeepSeek Harness 提供精确毫米绘图、MCP 和 Windows LaserMaker 自动操作。

## 一条命令安装

需要 Windows x64、Node.js 20+（含 npm/npx）、Git，以及已安装的 Agent CLI：

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin install codex
```

将 `codex` 换成 `claude`、`deepseek` 或 `kimi`。安装器会自动下载便携运行时、核对 SHA-256、解压并调用宿主的安装命令；无需 npm 登录、系统 Python、管理员权限或手写 EXE 路径。首次下载约 140 MB，再次运行复用已校验缓存。

`--allow-git=root` 按 npm 12 的要求，仅为本次命令显式许可这个 GitHub 包，不修改全局 npm 配置。

Codex／Claude 自动接入；DeepSeek 默认使用 `laser` profile；Kimi 需要将安装器打印的一条 `/plugins install ...` 命令粘贴到会话内，再 `/reload`。

这是直接从公开 GitHub 仓库运行的 npm 包，不是已发布到 npm registry 的同名包。安装器／宿主集成包为 **0.1.4**，继续使用未改动、已核验的 **0.1.2 Windows 核心**，因此 `doctor` 报告 0.1.2。0.1.4 修复了 DeepSeek Harness 0.2.1-rc.3 的安装兼容性。

```powershell
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin doctor
npx --yes --allow-git=root github:MosesMuxiXie/lasermaker-plugin config
```

`config` 输出可直接粘贴的通用 MCP 配置。默认安装到 `%LOCALAPPDATA%/LaserMakerAgent/versions/0.1.4/lasermaker-agent`；可用 `--dir 'D:/Tools/LaserMaker'` 指定其他安装根目录，后续命令也使用同一选项。已有项目、未知目录和被改动的缓存均不会被覆盖。

也可以全局安装：

```powershell
npm install -g --allow-git=root github:MosesMuxiXie/lasermaker-plugin
lasermaker-plugin install codex
```

[完整安装说明（英文）](docs/installation.md) · [原有中文安装说明](docs/安装.md)

## 选择你的 Agent

以下详细 README 使用英文，覆盖安装、工具检查、完整产品示例、原生保存重开、跨会话续作、离线接入、故障排查与卸载：

- **[Codex 教程 →](adapters/codex/README.md)**：本地市场、CLI 检查、本地 Desktop 注意事项和 MCP 备选接入。
- **[Claude Code 教程 →](adapters/claude/README.md)**：用户级安装、`/mcp` 检查、共享 Skill 和临时加载。
- **[Kimi Code 教程 →](adapters/kimi/README.md)**：会话内安装、`/reload`、MCP 启用和托管副本检查。
- **[DeepSeek Harness 教程 →](adapters/deepseek/README.md)**：profile 选择、原生 bundle、依赖服务和工具调用。

## 不使用 Node.js

从 [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest) 下载 `lasermaker-agent-0.1.4-plugin.zip` 并按校验文件核对，解压后注册本地插件目录。完整 ZIP 自带 Python；GitHub 自动源码包和小型安装器 tgz 不包含 Python。离线安装命令见英文安装说明。

## 功能与样例

17 个 MCP 工具与同名 CLI 支持项目、曲线、孔槽、节点、文字路径、变换／阵列／布尔／偏移、SVG/DXF、预检、图层工艺、原生保存重开、检查点和跨 Agent 续作。插件没有发送或启动激光机的工具。

![双抽屉工具站](examples/original-workstation/preview/open.png)

[原创双抽屉工具站](examples/original-workstation/README.md)：先冻结 15 页分解图，再独立重建 54 件、987 个绘图对象、4 张排板、120 组榫槽和 80 mm 抽屉行程；提供加工文件、试切片、装配说明与三维查看器。另有 [坦克模型](examples/sherman-tank/装配说明.md)、[合成试切片](examples/slot-coupon/) 与 [雕刻样例](examples/engraving-modes/说明.md)。

0.1.2 核心已有 91 项 Python 测试通过，2 项可选现场测试跳过；5 份原生工程完成实际导入、尺寸／工艺读回、保存、关闭和重开。20,000 对象上限已实际验证，超限原子拒绝。四种宿主已有无模型账户的加载／工具发现与分层调用验证。

GUI 需要本地未锁定桌面及 `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe` 的 2.1.7.2 版本。材料实测、切缝、五金、承重、机器幅面、实机走刀／加工和模型账户端到端尚未验证；两小时长测继续暂缓。示例功率仅用于读回测试。`manufacturing_ready=false`。

[验证报告](docs/验证报告.md) · [教程](docs/使用教程.md) · [接口与恢复](docs/接口与恢复.md) · [MIT](LICENSE)
