---
name: ai-profile
description: >-
  移动端 GPU 硬件性能自动化采样、Snapdragon Profiler 总线对账与多画质梯次分析公共技能。
  支持在聊天框输入 /AI_profile:start、/ai-profile:start、/profile-start 等快捷指令即时开始采样。
  当用户要求测试 Android 手机真机 GPU 性能、采集总线物理带宽 (DDR 读写)、获取单帧 MB/帧、分析 UBWC 压缩率、
  进行免侵入原地 Attach 采样、对账 Snapdragon Profiler 截帧 CSV、按类似 PerfDog 方式交互式打标签采样、
  或输入快捷启停指令时使用。
---

# AiProfile — 移动端 GPU 硬件性能自动化与总线对账技能

本技能为所有 Agent 提供跨项目的移动端 GPU 硬件物理性能自动化测试与对账能力。底层驱动 Qualcomm Snapdragon Profiler 硬件计数器与 Android OS 系统接口，测量真实的系统总线 DDR 带宽、片元着色量、UBWC 硬件无损压缩率与显存/内存水位。

---

## 零、 聊天框极速快捷指令 (Slash Commands)

当用户在 Agent 聊天输入框中输入以下快捷指令时，**Agent 应直接无缝执行对应底层命令，无需二次确认或闲聊，秒级反馈执行结果**：

| 聊天框快捷输入 | 对应底层执行命令 | 作用说明 |
| :--- | :--- | :--- |
| `/AI_profile:start` 或 `/ai-profile:start`、`/profile-start` | `profile-start` | 自动锁定真机前台运行的游戏，启动后台硬件高频物理采样（5Hz/200ms） |
| `/AI_profile:start --launch` | `profile-start --launch` | 启动采样前，先在手机上唤醒并拉起该游戏应用 |
| `/AI_profile:mark <标签名称>` 或 `/profile-mark <标签>` | `profile-mark <标签>` | 为当前正在采样的测试会话记录时间轴标记（如打怪、切图、进副本） |
| `/AI_profile:stop` 或 `/ai-profile:stop`、`/profile-stop` | `profile-stop` | 立即停止采样、拉取数据、自动在浏览器打开走势图并呈现分段画像总结 |
| `/AI_profile:gui` 或 `/profile-gui` | `profile-gui` | 极速秒开 PerfDog 风格的独立桌面悬浮控制面板 |

---

## 一、 核心工作模式与 CLI 调用

脚本位置：`C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py`

### 1. 模式 A：PerfDog 交互录制模式（点击即开始，回车即打标，输入 q 结束）
像 PerfDog 一样自由控制时长，边在手机上玩游戏，边在电脑键盘上随时敲回车打标签（例如标记“进副本”、“团战开始”、“释放大招”、“回城”）：

```powershell
# 启动交互式录制模式（自动锁定手机前台应用，每秒采样 5 次）：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py record --tag "大世界实测"

# 操作指南：
# 1. 直接输入标签名称并回车 -> 为当前时间点打标签 (Marker)
# 2. 输入 'q' / 'stop' 或按 Ctrl+C -> 停止收集，自动拉取数据并生成分段画像与时间轴图表
```

产物输出：
- `capture.png`：测试机位截图；
- `summary.md`：全景物理对账报告，包含**PerfDog 分段标签对比大表**；
- `timeline.html`：单文件完全离线的 HTML5 交互式走势图（带垂直标签指示线）；
- `raw/sdp_xxx_labeled.csv`：逐行打上当前阶段标签的增强 CSV 数据。

---

### 2. 模式 B：PerfDog 桌面悬浮控制面板 (Tkinter GUI)
提供免命令行的桌面图形小浮窗，包含【▶ 开始收集】、【🏷️ 打标签】输入框、【⏹ 结束收集】大按钮：

```powershell
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py gui
```
- 点击开始后实时显示采样计时与瞬时真机温度；
- 支持回车快速打标签与预设标签一键标记；
- 点击结束自动打开 HTML 走势图与分析报告。

---

### 3. 模式 C：分立生命周期命令（适合自动化脚本与 Agent 工具链）
支持非阻塞后台会话，由外部测试脚本在特定事件发生时打标签：

```powershell
# 1. 后台启动采样会话：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py start --tag "Boss战"

# 2. 随时打标签：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py mark "全屏特效爆发"

# 3. 随时结束并生成分段报告：
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py stop
```

---

### 4. 模式 D：固定时长单次快照采样
针对标准化稳态性能测试，直接采集指定时长（如 3 秒或 1800 秒）：

```powershell
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py run --attach --duration 3.0 --period 200 --tag "极高配"
```

---

### 5. 模式 E：截帧 CSV 相机聚合与对账（消除 Excel SUM 虚高）
当用户提供 Snapdragon Profiler GUI 导出的截帧 CSV（如 `fs_l.csv`）时，直接提取各相机根节点并求和（Main Camera + UICamera），消除父子 Marker 重复累加：

```powershell
python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py filter-camera <path_to_raw_csv> --out <path_to_filtered_csv>
```

---

### 6. 模式 F：跨项目组落地（Unity 3 分钟极简嵌入）
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
