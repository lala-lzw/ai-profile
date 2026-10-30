---
name: profile-start
description: >-
  极速启动 Android 手机 GPU 硬件物理性能采样（自动锁定当前前台应用，200ms 高频硬件采样）。
  当用户在聊天框输入 /profile-start 或 /AI_profile:start 时使用。
---

# profile-start 快捷启动指令

用户在聊天框输入此指令时，直接调用底层 `profile-start` 命令启动采样，并向用户反馈目标应用、采样频率与打标指令。

```powershell
profile-start
```

若用户附带了参数（如 `--launch` 或 `--package <包名>`），原样透传。
