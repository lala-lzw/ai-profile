---
name: profile-stop
description: >-
  结束 AiProfile Android GPU 采样、拉取 CLI 原始 CSV 并生成离线报告。
  当用户输入 /profile-stop 或 /AI_profile:stop，或要求结束当前采样时使用。
---

# 结束当前采样

执行 `profile-stop`。命令停止设备采样、拉取原始 CSV，并打开 `timeline.html`。
向用户反馈报告位置、原始样本和已记录标签。指标保持 CLI 原名与原值，不除以 FPS。
桌面会话另有 SurfaceFlinger FPS 记录时，报告会同时展示 FPS 曲线。

执行入口：同级目录 `../ai-profile/scripts/aiprofile_cli.py`（相对本文件解析为绝对路径后调用）。
```
python <ai-profile 技能目录>/scripts/aiprofile_cli.py stop
```
若已把 `ai-profile/bin` 加入 PATH，也可直接使用同名快捷命令；缺少 ai-profile 技能时先安装它。
