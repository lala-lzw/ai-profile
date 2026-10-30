---
name: ai-profile
description: >-
  采集 Android 真机 GPU 硬件计数器，使用 AiProfile 桌面工作台打标、预览 FPS，
  生成保留 sdpcli 原始数据的离线报告。用于 GPU、Shader、指令、缓存、停顿和访存分析，
  以及 /profile-start、/profile-mark、/profile-stop、/profile-gui 等采样命令。
---

# AiProfile — GPU 采样与离线分析

脚本入口为本技能目录下的 `scripts/aiprofile_cli.py`，Windows 命令包装器位于 `bin/`。
命令从项目工作目录运行，默认产物保存在该目录的 `Docs/Benchmarks/GPU/aiprofile_<时间>/<会话名>/`。
需要 Python（含 Tkinter）、ADB、已授权 Android 设备，以及可用的 Qualcomm sdpcli。
可用 `SDPCLI_PATH` 指向本地 sdpcli；采样会话状态保存在用户目录的 `.aiprofile_session.json`。

## 选择入口

| 用户请求 | 执行入口 | 行为 |
| --- | --- | --- |
| 打开面板、`/profile-gui`、`/AI_profile:gui` | `profile-gui` 或 `python <技能目录>/scripts/gui_panel.py` | 打开工作台，等待用户点击开始 |
| 开始后台采样、`/profile-start`、`/AI_profile:start` | `profile-start [--package 包名] [--period 200]` | 未指定包名时锁定前台应用 |
| 打标签、`/profile-mark 标签` | `profile-mark 标签` | 在活动会话记录阶段标记 |
| 结束采样、`/profile-stop` | `profile-stop` | 停止、拉取数据并生成报告 |

`--launch` 表示开始采样时拉起指定应用。没有这项参数时按前台应用原地采样。
桌面入口通过 `pythonw` 启动，ADB 子进程不弹控制台。重开面板可恢复已有活动会话。

## 桌面工作台

左侧选择设备、目标应用、采样间隔和会话名称，点击开始后进行采样。
右侧展示 FPS 和 GPU 指标曲线，支持指标分组、图例开关、时间窗口和暂停曲线显示。
暂停曲线只暂停绘制，原始采样继续；每轮预览补读全部新增 CLI 行，保留中间峰值。
支持回车打标和预设阶段标签，结束后可打开离线报告。

FPS 来自目标应用的 SurfaceFlinger `actualPresentTime`，单独保存采样记录及原始帧时间戳。
目前该额外采集器随桌面面板运行；纯 CLI 采样不启动 SurfaceFlinger FPS 采集。
缺少权限、目标图层或有效帧间隔时显示“—”，已知图层没有新帧时显示 0。

## 数据口径

- 指标名使用 sdpcli CSV 原始列名，CSV 单元格以字符串保存，原文件可按字节下载和 SHA-256 核对。
- 不将 GPU 计数器除以 FPS，不自动进行单帧换算。`--fps` 仅保留旧调用兼容。
- 图表默认使用易读显示单位；M/G 为十进制缩写，MB 为 10⁶ Bytes，CPU 频率显示 MHz。
  `Clocks / Second` 显示 M cycles/s，不把周期计数当作硬件频率。
  图表和面板可切回原始数值；悬停与原始表保留完整原值。
- GPU 横轴按样本序号与配置采样间隔估算；CLI 没有逐行时间戳，不把估算时间描述为实测时间。
  FPS 使用其独立记录的经过时间，标签筛选使用实际标记时间。
- 可疑量级只标记待核实，不自动修正、删除或用零替代。未知时间单位不猜测。

## 报告与标签筛选

`timeline.html` 为无外部资源依赖的单文件报告。使用“标签筛选”勾选一个或多个阶段，
或点击“仅已打标”排除未打标的准备阶段；FPS 与 GPU 曲线同步筛选。
被排除区间断开显示，坐标轴按当前数据适配，原始文件仍完整保留。
FPS 区域只展示数值与曲线。

| 产物 | 内容 |
| --- | --- |
| `raw/sdp_<会话>.csv` | 原始 sdpcli 输出 |
| `raw/sdp_<会话>_labeled.csv` | 保留原值，附来源行号和阶段标签 |
| `raw/fps.csv`、`raw/surfaceflinger_frames.csv` | 桌面会话的 FPS 与帧时间戳 |
| `summary.json`、`summary.md` | 原始数据、来源校验、阶段索引和当前样本 |
| `data_audit.csv`、`data_audit.md` | 待核实数据的原始列名、原值与来源行 |
| `capture.png` | 结束采样时的设备截图 |

## 其他模式

- 终端交互打标：`python <技能目录>/scripts/aiprofile_cli.py record --tag 测试场景`。
  输入标签并回车记录标记，输入 `q` 或 `stop` 结束。
- 固定时长采样：`python <技能目录>/scripts/aiprofile_cli.py run --attach --duration 3 --period 200 --tag 测试场景`。
- 截帧 CSV 相机根节点聚合：`python <技能目录>/scripts/aiprofile_cli.py filter-camera 原始.csv --out 聚合.csv`。
  仅在需要核对截帧与运行采样时阅读 [references/verification_rules.md](references/verification_rules.md)，
  先核对机位、应用和计数器定义，勿将示例比例套用于所有设备。
- Unity 工程可使用 `agent_sdk/AiProfileAgent.cs` 接入项目自己的画质设置回调；需要此模式时读取该文件。

## 验证

在仓库根目录运行 `python -m unittest discover -s skills/ai-profile/tests -v`。
Node.js 仅用于离线报告脚本的行为测试，正式报告和桌面运行不依赖 Node.js。
