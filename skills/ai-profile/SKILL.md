---
name: ai-profile
description: >-
  移动端 GPU 硬件性能自动化采样、Snapdragon Profiler 总线对账与多画质梯次分析公共技能。
  当用户要求测试 Android 手机真机 GPU 性能、采集总线物理带宽 (DDR 读写)、获取单帧 MB/帧、分析 UBWC 压缩率、
  进行免侵入原地 Attach 采样、对账 Snapdragon Profiler 截帧 CSV、或将性能测试自动化带入新项目组时使用。
---

# AiProfile — 移动端 GPU 硬件性能自动化与总线对账技能

本技能为所有 Agent 提供跨项目的移动端 GPU 硬件物理性能自动化测试与对账能力。底层驱动 Qualcomm Snapdragon Profiler 硬件计数器与 Android OS 系统接口，测量真实的系统总线 DDR 带宽、片元着色量、UBWC 硬件无损压缩率与显存/内存水位。

---

## 一、 核心工作模式与 CLI 调用

脚本位置：`C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py`

### 1. 模式 A：黑盒免侵入原地挂载采样（最常用，零代码侵入）
对任意正在真机前台运行的游戏（无论有无源码、发行包或竞品），**无需重启应用、不杀进程、不重置机位**，直接原地挂载采样：

```powershell
# 自动识别当前前台游戏，原地挂载采样 3 秒：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py run --attach --tag "场景名_画质名"

# 显式指定包名采样：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py run --package com.xxx.game --attach --tag "极高配"
```

产物输出在目标测试目录：
- `capture.png`：瞬时机位截屏证据；
- `summary.md`：核心物理对账大表（DDR 读写、单帧 MB/帧、UBWC 压缩率）；
- `summary.json`：全量硬件计数器结构化数据；
- `raw/sdp_xxx.csv`：Adreno 原始采样数据。

---

### 2. 模式 B：截帧 CSV 相机聚合与对账（消除 Excel SUM 虚高）
当用户提供 Snapdragon Profiler GUI 导出的截帧 CSV（如 `fs_l.csv`）时，直接提取各相机根节点并求和（Main Camera + UICamera），消除父子 Marker 重复累加：

```powershell
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py filter-camera <path_to_raw_csv> --out <path_to_filtered_csv>
```

---

### 3. 模式 C：跨项目组落地（Unity 3 分钟极简嵌入）
当新项目组需要接入全自动切画质跑分时：
1. 将 `C:/Users/user/.gemini/config/skills/ai-profile/agent_sdk/AiProfileAgent.cs` 复制到项目工程 `Assets/Scripts/`；
2. 游戏启动时绑定项目自己的切画质单例：
   ```csharp
   AiProfileAgent.OnSetQualityRequested = (tier) => {
       GameSettingManager.Instance.SetQuality(tier);
   };
   ```
3. 即可在电脑端下发全自动多档画质测试命令。

---

## 二、 关键对账物理准则

在对比截帧数据 (L3) 与总线物理实测数据 (L2) 时，严格遵守以下规律：
1. **顶点读取（Vertex Read）几乎 1:1**：顶点在 GLES 中不走 UBWC 压缩，直接穿透至 DDR，比值在 `1.09x ~ 1.20x`，是验证同一机位场景的最强铁证；
2. **读总访存穿透比约为 2.1x ~ 2.5x**：中间消除的流量是 Adreno UBWC 硬件无损压缩（~68%）与 L2 缓存命中过滤的物理结果；
3. **写总访存穿透比约为 1.55x ~ 1.66x**：对应 Framebuffer UBWC 写入压缩过滤；
4. **片元与指令穿透比约为 1.5x ~ 1.8x**：截帧静态瞬间展开 vs 稳态运行动态遮挡剔除的合理差异。
详细物理机理参考：[对账准则](references/verification_rules.md)。

