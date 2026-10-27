# 原创双抽屉工具站：极限功能测试

从零编制平面分解图，再按冻结的尺寸规格独立重建。成品 270 × 210 × 280 mm，名义 3 mm 板材，54 个零件，4 张 600 × 400 mm 排板、987 个实际绘图对象；另有独立试切片与定位尺。

- [打开产品与加工文件索引](产品与加工索引.html)
- [15 页平面分解设计图](blueprint/平面分解设计图-A1.pdf) · [特征尺寸表](blueprint/特征尺寸表.csv) · [冻结的尺寸规格](blueprint/dimensions.json)
- [可旋转、展开、开闭抽屉的离线三维装配](三维装配.html)
- [装配说明与现场确认项目](装配说明.md) · [零件清单](零件清单.csv)
- [可编辑的装配及轮廓源文件](assembly-source.json) · [OpenSCAD](workstation.scad) · [装配 STL](workstation-assembled.stl)
- [完整软件验证报告](verification-report.json) · [独立尺寸、接头和运动检查](design-verification.json) · [20,000 对象边界检查](limit-probe.json)

4 张产品排板及 1 张辅助试片均经过真实 MCP 导入、尺寸读回、工艺设置、保存并关闭后按准确路径重开核验。下方每个目录的 `delivery.json` 指向当前有效原生工程、SVG/DXF、分阶段文件和检查报告。

数值几何计算容差为 0.01 mm，界面尺寸读回容差为 0.05 mm，均不代表激光机加工精度。软件核验通过，尚未完成材料试切、五金试装、承重／抗倾覆或实机加工。图层中的速度和功率只用于验证参数落盘，不作为加工建议。两小时长测继续暂停。

旧方向测试及弹窗中断记录仅保留在原工作区，不包含在公开发行中。软件为 0.1.2，四种宿主已作无模型账户的插件加载／工具发现核验；Codex 与 DeepSeek 原生调用、Claude 与 Kimi 解析配置后的 stdio 调用均另有记录，模型对话端到端仍未验证。

复建：在源码目录安装 `.[dev,design]` 后，先使用新文件夹编制／检查／冻结下一版本设计图，再运行 `scripts/prepare_workstation.py`、`scripts/check_workstation.py`、`scripts/verify_workstation.py`。A1 图纸已冻结，作者脚本默认拒绝覆盖，不要删除冻结文件绕过保护。
