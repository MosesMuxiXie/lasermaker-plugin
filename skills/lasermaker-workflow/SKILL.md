---
name: lasermaker-workflow
description: Use when creating, precisely editing, checking, or resuming LaserMaker laser-cutting and engraving designs on Windows, including SVG scale errors, native lcpx delivery, and interrupted multi-session projects.
---

# LaserMaker workflow

Use the plugin's discovered MCP tools. Raw names below acquire a host-specific prefix; do not invent it. Without MCP, run runtime/lasermaker-agent.exe tools and the same CLI operation with a UTF-8 --args-file.

Start with doctor, then open_project or resume_project. Canonical source geometry uses millimetres and stable object IDs. apply_design_ops is atomic and requires the current revision and a unique request ID.

For a timed-out geometry request, replay the **exact original request ID and arguments, including its original expected_revision**. Changing the revision changes the digest and causes REQUEST_CONFLICT. Do not generate a fresh ID because an outcome is unknown. A receipt returns the original result even after later revisions.

For UI_OUTCOME_UNKNOWN or a pending UI operation, inspect the app, recorded operation file and actual artifact paths. Do not blindly repeat an import or duplication or discard a dialog. Preserve user modifications. Continue only after establishing which postcondition actually happened; otherwise report the unresolved state.

Use source edits for paths, nodes, transforms, duplication/arrays, align/distribute, booleans, offsets and outlined text. Do not patch heuristic lcpx point streams. set_material changes declared metadata only: different thickness also requires explicit joinery and assembly edits.

Run preflight, then import_design. The exporter already uses the LaserMaker2.1.7.2 96/25.4 coordinate profile. Verify the **drawing's expected dimensions**, not the page width. A 280 mm page does not mean a 252 mm drawing should be stretched to 280 mm. Imported position is reported against the application's current anchor; actual bed origin needs separate setup.

Use set_layer_process only on a bound managed document. The sample uses black cut and red score; color alone is not proof of mode. Read back actual mode, speed in mm/s and power percentages. Use operator-supplied/tested production parameters. Existing presets and tutorial numbers are uncalibrated.

Use save_native with a new project-contained path; its returned filename contains the project ID. Use that returned path with reload_and_verify and expected drawing size, then verify_layer_process for each used color. A renamed tab or screenshot is not proof of saving. Checkpoint and export_delivery when source and native revision/scope match. Afterward close_verified_document can close this verified saved document before further fresh imports. Unsaved process changes require a new save/reopen first.

Deliver source, SVG/DXF, current native project, staged score/inner/outer files, fit coupon and reports. Distinguish geometry/software verification from physical fit, machine settings and actual cutting. No tool transmits or starts a laser. Report unverified path planning or simulation explicitly.

Read [使用教程](../../docs/使用教程.md), [接口与恢复](../../docs/接口与恢复.md), or [安装](../../docs/安装.md) when needed.
