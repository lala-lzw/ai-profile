---
name: profile-stop
description: >-
  极速结束 Android 手机 GPU 硬件性能采样，拉取物理数据并在浏览器打开时间轴走势图。
  当用户在聊天框输入 /profile-stop 或 /AI_profile:stop 时使用。
---

# profile-stop 快捷结束指令

用户在聊天框输入此指令时，直接调用底层 `profile-stop` 命令结束采样，拉取数据、切分分段画像，自动在默认浏览器中打开 `timeline.html`，并向用户汇总输出物理总线带宽、UBWC 压缩率与分段对比表。

```powershell
profile-stop
```
