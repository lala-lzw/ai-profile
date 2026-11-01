# 示例数据：iQOO 10 单次实测

一次真机采样的脱敏数据，用于演示报告和 PerfDog 对照。设备为 iQOO 10，被测内容是作者自制的 Demo。

| 路径 | 内容 |
| --- | --- |
| `raw/sdp_ExampleSession.csv` | sdpcli 原始输出，字节未修改（SHA-256 `a97cee80…ed371`） |
| `raw/fps.csv` | SurfaceFlinger FPS 记录 |
| `summary.json` | 会话汇总（脱敏后），对照脚本的输入 |
| `timeline.html` | 用本工具重新生成的离线报告，双击即可打开 |
| `perfdog/perfdog_gpu_counters.csv` | PerfDog 导出表中的 `time`、`FPS` 与可配对的 28 项 GPU 计数器列 |
| `comparison/` | 对照结果：两种时间对齐方式的统计表与对照图 |

## 脱敏说明

- 应用包名、Activity 与图层名统一替换为 `com.example.demo`。
- 阶段标签改为通用名 `scene` / `end`；设备只保留型号 `iQOO 10`，去掉系统与内存等其他字段。
- 删除绝对时间戳和设备开机时钟的偏移，不包含截图和逐帧时间戳文件。
- PerfDog 数据只保留对照用到的列，不含应用、设备和用户信息。
- 计数器数值未做任何修改。

结论与局限见 [对照验证](../../docs/perfdog_comparison.md)。
