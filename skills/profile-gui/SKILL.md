---
name: profile-gui
description: >-
  打开 AiProfile GPU 性能采样桌面工作台。
  当用户要求打开性能采样面板，或输入 /profile-gui、/AI_profile:gui 时使用。
---

# 打开 AiProfile 工作台

执行 `profile-gui`，打开设备与应用选择、手动采样、阶段打标、GPU 曲线和 FPS 面板。
采样由用户点击开始按钮控制。已有会话会恢复显示。

如命令未安装，使用本仓库 `skills/ai-profile/scripts/gui_panel.py`；
Windows 使用 `pythonw` 启动。详细数据口径见 [ai-profile](../ai-profile/SKILL.md)。

执行入口：同级目录 `../ai-profile/scripts/aiprofile_cli.py`（相对本文件解析为绝对路径后调用）。
```
python <ai-profile 技能目录>/scripts/aiprofile_cli.py gui
```
若已把 `ai-profile/bin` 加入 PATH，也可直接使用同名快捷命令；缺少 ai-profile 技能时先安装它。
