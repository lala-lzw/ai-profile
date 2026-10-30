# 移动端 GPU 硬件总线与截帧单帧对账准则

根据 Adreno 660（SM8350）与 Unity URP (GLES/Vulkan) 的实测验证，建立以下物理对账铁律：

## 一、 证据分层标准 (Hierarchy of Metrics)

| 层级 | 采集源 | 代表含义 | 典型指标 |
| :--- | :--- | :--- | :--- |
| **L2 物理总线层** | Qualcomm `sdpcli` 硬件采样 | 穿透到 DRAM 物理芯片的真实流量与工作状态 | DDR 读写物理带宽 (`Read/Write Total`)、UBWC 压缩率、GPU 利用率、真实功耗与时钟 |
| **L3 逻辑管线层** | Snapdragon Profiler GUI 截帧 (Snapshot) | GPU 内部各级 Shader 管线发出的未压缩请求 | 相机节点求和 (`RenderSingleCamera`)、精确片元数、展开指令数、内部未压缩访存 |

---

## 二、 关键对账三大铁律

### 1. 顶点读取（Vertex Read）接近 1:1 绝对吻合
- **现象**：在全档位下，GUI 截帧单帧顶点读取与 sdpcli 实测折算的物理顶点读取比值保持在 `1.09x ~ 1.20x`（近乎 1:1）。
- **物理机理**：在移动端中，顶点缓冲（Vertex Buffer）通常以原始 `float/half` 存储，驱动无法对其进行 UBWC 压缩，因此顶点读取直接穿透至物理 DDR。**顶点吻合是验证两套工具测量同一场景机位与几何负载的最强铁证**。

### 2. 读写访存穿透比精准对应 UBWC 硬件无损压缩率
- **现象**：
  - 读总访存穿透比稳定在 **`2.1x ~ 2.5x`**（即未压缩内部请求约 21~50 MB，真实打到 DDR 的物理读取为 10~19 MB）；
  - 写总访存穿透比稳定在 **`1.55x ~ 1.66x`**（即 Framebuffer 写入请求约 8~16 MB，真实写入 DDR 为 5~10 MB）。
- **物理机理**：中间消除的带宽正是 Adreno 660 的 UBWC 硬件无损压缩（~68% 压缩率）与 L2 缓存命中过滤的物理结果。

### 3. GLES 相机聚合消除重复累加
- **现象**：Snapdragon Profiler CSV 将父级 Marker（`Main Camera`、`ForwardRenderer`、`RenderLoop.Draw`）与底层 `glDrawElements` 并列导出。直接整列无脑 SUM 会将每个 Draw Call 重复累加 4~5 次（虚高 5 倍）。
- **规则**：直接提取各相机根节点（`RenderSingleCamera`）相加（Main Camera + UICamera），即为整帧权威、无重复的单帧数据。

