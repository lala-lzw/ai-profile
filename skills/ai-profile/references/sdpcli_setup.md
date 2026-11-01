# SDP CLI 下载与安装

首次配置 AiProfile，或出现“未找到 Android sdpcli 预编译包”时使用本指引。
AiProfile 在电脑上通过 ADB 调用手机端的 Snapdragon Profiler CLI，需准备 **Android aarch64 版 `sdpcli`**。

## 下载入口与包选择

高通官方入口：<https://www.qualcomm.com/developer/software/snapdragon-profiler>。
在官网查找 **Snapdragon Profiler CLI / Command Line Interface** 的 Android 下载包，按当前页面流程下载并解压。
若页面要求登录，使用自己的高通账号完成下载；若只找到桌面 GUI，继续查找包含 Android `sdpcli` 的 CLI 包。
截至 2026-10-31 已确认上述产品页可访问，尚未核实可直接下载的 `.zip` / `.exe` 安装包地址，勿拼接版本号猜测直链。

| 文件或版本 | 用途 |
| --- | --- |
| Android aarch64 的 `sdpcli`（无 `.exe` 后缀） | 推送到 Android 手机运行，供 AiProfile 采样使用 |
| Windows 的 `sdpcli.exe` | 在支持的 Windows 设备上运行，不能替代手机端的 Android 二进制 |
| Android 包内同版本的 `.so` 文件 | 与 `sdpcli` 一起保留，供手机端加载 |

解压后保留完整的 Android 包。当前采集器会从 `sdpcli` 的同级目录推送以下依赖文件（存在时）：

```text
sdpcli
libsysmon.so
libsysmondomain.so
libsysmondomainV2.so
libsysmonslpi.so
```

迁移到其他电脑时也应一起复制这些文件，保持包内版本一致。
包内的 `sdpcli-layer-*.apk` 用于 Vulkan trace；AiProfile 当前的实时计数器采样不要求安装这些 APK。
本技能仓库提供配置指引，二进制需另行取得。

## 在电脑上配置位置

脚本按以下顺序查找 `sdpcli`，找到即用：

1. 环境变量 `SDPCLI_PATH`（指向 `sdpcli` 文件，或包含它的目录）。
2. `~/.aiprofile/sdpcli/sdpcli`。
3. `%LOCALAPPDATA%`、`%APPDATA%`、`~/Qualcomm`、`~/.local/share/Qualcomm` 下的
   `Qualcomm/SnapdragonProfilerCLI/Android/<版本>/sdpcli`，多个版本时取版本目录名最大者。

自动查找不依赖固定版本号。解压到其他位置时，设置 `SDPCLI_PATH`。
以下 PowerShell 示例需将路径替换为实际解压位置；macOS / Linux 在 shell 配置中 `export SDPCLI_PATH=/path/to/sdpcli`：

```powershell
$sdpcliFile = 'D:\Tools\Qualcomm\SnapdragonProfilerCLI\Android\2026.8.0\sdpcli'
if (-not (Test-Path -LiteralPath $sdpcliFile -PathType Leaf)) {
    throw "未找到 Android sdpcli：$sdpcliFile"
}
$env:SDPCLI_PATH = $sdpcliFile
[Environment]::SetEnvironmentVariable('SDPCLI_PATH', $sdpcliFile, 'User')
```

`$env:SDPCLI_PATH` 对当前终端及其启动的进程生效；最后一行保存为用户环境变量。
从当前终端启动 AiProfile，或重启承载 AiProfile 的终端 / Agent 应用后再打开面板，确保进程读到新变量。

## 部署到手机并验证

先准备可用的 Python（桌面面板需 Tkinter）、PATH 中的 ADB，以及已开启 USB 调试并授权的骁龙 / Adreno Android 设备。
运行 `adb devices`，确认目标设备状态为 `device`。
连接多台设备时，在当前 PowerShell 中设置 `$env:ANDROID_SERIAL = '目标设备序列号'`。

正式开始采样时，采集器会自动推送二进制及同目录依赖到 `/data/local/tmp/gdp_sdpcli/`。
如需提前验证安装，在**本技能根目录**（包含 `scripts/` 的 `ai-profile/` 目录）运行：

```powershell
python -c "from scripts.adb_bridge import AdbBridge; from scripts.sdp_collector import SdpCollector; SdpCollector(AdbBridge()).prepare_device_daemon()"
adb shell "LD_LIBRARY_PATH=/data/local/tmp/gdp_sdpcli /data/local/tmp/gdp_sdpcli/sdpcli --version"
adb shell "LD_LIBRARY_PATH=/data/local/tmp/gdp_sdpcli /data/local/tmp/gdp_sdpcli/sdpcli r l"
```

前一条命令部署文件，后两条分别输出设备端版本和可用计数器列表，不开始采样。
确认成功后，按技能首页的面板或 CLI 入口使用 AiProfile。

## 常见问题

- **找不到本地文件**：检查 `SDPCLI_PATH` 指向文件而非目录，并确认启动面板的进程读到了该变量；自动查找只覆盖上述位置。
- **`Exec format error`**：确认使用 Android aarch64 的 `sdpcli`，而非 Windows `.exe` 或其他架构包。
- **找不到共享库 / `dlopen` 失败**：检查 Android 包的同版本 `.so` 是否位于二进制同级目录，并使用上述 `LD_LIBRARY_PATH` 验证。
- **手机显示旧版本**：采集器复用设备端已可执行的 `sdpcli`，仅修改电脑上的路径不会覆盖它；升级时需同步替换设备端的二进制和依赖库，再检查版本。
