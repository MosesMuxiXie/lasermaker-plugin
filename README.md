# lasermaker plugin

让 Codex、Claude Code、Kimi Code、DeepSeek Harness 等 Agent 精确绘制激光切割／雕刻图形，并操作 **Windows LaserMaker V2.1.7.2**，保存和重新打开 `.lcpx` 工程核验。

共享 Python 核心提供 17 个 stdio MCP 工具和同名 CLI：毫米坐标、稳定对象 ID、曲线与文字路径、孔槽、布尔与偏移、SVG/DXF、预检、工艺读回、检查点及跨会话恢复。插件没有发送或启动激光机的工具。

![原创双抽屉工具站](examples/original-workstation/preview/open.png)

## 下载和安装

在 [Releases](https://github.com/MosesMuxiXie/lasermaker-plugin/releases/latest) 下载 **`lasermaker-agent-0.1.2-plugin.zip`**。这是包含 Python 运行时的完整 Windows x64 便携包，不需要系统 Python。GitHub 自动源码 ZIP 和 `-source.zip` 用于开发，**不包含便携运行时**。

1. 安装 Windows 简体中文版 LaserMaker **2.1.7.2**。驱动查找 `C:/Program Files/LaserMaker2/Bin/LaserMaker.exe`。
2. 将 ZIP 解压到固定位置，例如 `D:/Tools/lasermaker-agent`。该目录内应直接看到 `plugin.json`、`mcp.json` 和 `runtime`；保留 EXE 与 `_internal` 的相对位置。
3. 对照 Release 的 `SHA256SUMS.txt` 核对文件，然后运行自检：

```powershell
Get-FileHash '.\lasermaker-agent-0.1.2-plugin.zip' -Algorithm SHA256
$pluginRoot = (Resolve-Path 'D:/Tools/lasermaker-agent').Path
& "$pluginRoot/runtime/lasermaker-agent.exe" doctor
& "$pluginRoot/runtime/lasermaker-agent.exe" tools
```

`doctor` 返回版本和安装状态；`tools` 列出 17 个工具。GUI 操作需要未锁定的本地桌面。开始前保存自己的图纸；出现“自动恢复”等未知弹窗时，先人工处理并保留需要的恢复文档，再让 Agent 检查状态。

完整包已经包含四种宿主的清单，不需要再安装适配覆盖包。

### Codex

已测试 Codex CLI **0.164.0** 的原生插件加载、工具发现和实际调用：

```powershell
codex plugin marketplace add 'D:/Tools/lasermaker-agent'
codex plugin add lasermaker-agent@lasermaker-local
codex plugin list --json
```

Codex Desktop 可从插件界面添加该本地市场。仅克隆源码不足以启动便携 MCP，须使用完整 Release 包或自行构建运行时。

### Claude Code

已测试 Claude Code **2.1.310** 的插件加载和 MCP 发现：

```powershell
claude plugin validate 'D:/Tools/lasermaker-agent'
claude --plugin-dir 'D:/Tools/lasermaker-agent'
```

在会话中用 `/mcp` 查看连接。清单通过 `${CLAUDE_PLUGIN_ROOT}` 解析运行时，共享 Skill 为 `lasermaker-workflow`。

### Kimi Code

已测试 Kimi Code **2.3.2**。在 Kimi 会话内执行：

```text
/plugins install D:/Tools/lasermaker-agent
/reload
/plugins info lasermaker-agent
/plugins mcp enable lasermaker-agent lasermaker
```

路径含空格时可在 `/plugins` 面板输入完整目录。Kimi 将插件复制到管理目录；更新便携文件后需重新安装或更新插件。

### DeepSeek Harness

已测试 DeepSeek Harness **0.2.1-rc.2**、Cordis **4.0.5** 的原生 bundle 和官方 `dsh-mcp-client`：

```powershell
dsh plugin --profile laser add 'D:/Tools/lasermaker-agent'
dsh --profile laser --dump-config
```

配置应包含 `dsh-plugin-lasermaker`。宿主需要 `dsh-tools`、`dsh-skill`、`dsh-system-prompt` 等服务及 `package.json` 中的 peer dependencies。便携包包含插件和 Python 运行时；Harness、Node.js 和模型账户由宿主提供。

### 通用 stdio MCP

将以下内容放入宿主的 MCP 配置，并改为真实安装路径：

```json
{
  "mcpServers": {
    "lasermaker": {
      "command": "D:/Tools/lasermaker-agent/runtime/lasermaker-agent.exe",
      "args": ["mcp"],
      "cwd": "D:/Tools/lasermaker-agent"
    }
  }
}
```

再让 Agent 读取 `skills/lasermaker-workflow/SKILL.md`。通用 MCP 接入与宿主原生插件加载分别记录验证结果。

## 使用方法

可以让 Agent 执行：

> 设计一套名义 3 mm 板材的桌面收纳件，先画带尺寸的分解图，再绘制孔槽、文字路径和装配关系。预检后导入 LaserMaker，核对尺寸及图层，保存并关闭，再按准确路径重开核验。交付源文件、SVG/DXF、原生工程和试切片，不启动机器。

流程是 `doctor` → `create_project` / `resume_project` → `apply_design_ops` → `preflight` → `import_design` → `set_layer_process` → `save_native` → `reload_and_verify` → `verify_layer_process` → `checkpoint` → `export_delivery`。

- 源坐标使用 mm；几何计算容差 0.01 mm，GUI 读回容差 0.05 mm，均不代表实机精度。
- 黑色切割、红色描线；雕刻要核对实际工艺，不能只凭颜色判断。
- 重试几何请求须保留原请求 ID、原版本和全部参数。GUI 结果未知时先检查日志与文件，不能盲目重复导入。
- 切换宿主时先 `resume_project`；发现用户修改原生工程时保留副本，避免覆盖。

详细说明：[精简教程](docs/使用教程.md) · [接口与恢复](docs/接口与恢复.md) · [安装说明](docs/安装.md) · [资料来源](docs/资料来源.md)。

## 样例与验证

[原创双抽屉工具站](examples/original-workstation/README.md) 包含先冻结的 15 页分解图、54 个零件、4 张 600 × 400 mm 排板、987 个绘图对象、120 组榫槽及 80 mm 抽屉行程，并交付三维装配、STL、OpenSCAD、SVG/DXF 和原生工程。另有 [39 件拼装坦克](examples/sherman-tank/装配说明.md)、[插槽试切片](examples/slot-coupon/) 和 [雕刻工艺样例](examples/engraving-modes/说明.md)。

0.1.2 修复圆弧镜像／不等比缩放、装配到 SVG 的 Y 方向转换，以及恢复时过期验收记录的复用。MCP 已实际达到 20,000 对象上限，第 20,001 个对象会被原子拒绝。详见 [验证报告](docs/验证报告.md)。

四种宿主已验证无模型账户的加载和工具发现；Codex／DeepSeek 已作原生调用，Claude／Kimi 已通过宿主解析出的 stdio 配置调用。模型对话端到端未验证。120 分钟连续工作负载测试暂缓；机器幅面、材料、切缝、五金、承重和实机加工待现场验证，`manufacturing_ready` 保持 `false`。样例的速度／功率仅用于软件读回测试。

## 从源码开发

需要 Python **3.12 x64**，字体测试使用 Windows 的 Arial 和微软雅黑；不分发系统字体。

```powershell
py -3.12 -m venv .venv
& .venv/Scripts/python.exe -m pip install -e '.[dev,design]'
& .venv/Scripts/python.exe -m pytest -q
& .venv/Scripts/python.exe -m lasermaker_agent mcp
```

`scripts/build.ps1` 测试并构建便携运行时。`requirements.lock.txt` 记录已测试依赖；`design` 依赖用于图纸 PDF 和预览生成。Windows GUI 仅支持上述 Windows 环境。四种 `-adapter.zip` 是可选覆盖层，不能替代完整运行时。

## 许可证

软件使用 [MIT](LICENSE)。上游 [Ganzhe2028/lasermaker-mcp-cli-skill](https://github.com/Ganzhe2028/lasermaker-mcp-cli-skill) 的署名及许可保留在 [第三方声明](THIRD_PARTY_NOTICES.md)，运行时许可在 `licenses/`。私人原作品和本地评测使用的第三方参考图素材不包含在公开分发中。
