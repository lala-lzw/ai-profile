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
