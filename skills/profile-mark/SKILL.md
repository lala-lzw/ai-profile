---
name: profile-mark
description: >-
  为当前正在运行的 GPU 硬件性能采样会话打上阶段标签（如'Boss战'、'放技能'、'切图'）。
  当用户在聊天框输入 /profile-mark 或 /AI_profile:mark 时使用。
---

# profile-mark 快捷打标指令

用户在聊天框输入此指令时，直接调用底层 `profile-mark <标签名称>` 命令为当前时间轴记录阶段标签。

```powershell
profile-mark <标签名称>
```

执行入口：同级目录 `../ai-profile/scripts/aiprofile_cli.py`（相对本文件解析为绝对路径后调用）。
```
python <ai-profile 技能目录>/scripts/aiprofile_cli.py mark <标签名称>
```
若已把 `ai-profile/bin` 加入 PATH，也可直接使用同名快捷命令；缺少 ai-profile 技能时先安装它。
