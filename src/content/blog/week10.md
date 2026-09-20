---
title: 'KMDF IOCTL 遥测驱动实战：Ring Buffer 与用户态导出'
description: '自己写一个 KMDF 教学驱动，在内核态采集 IOCTL 元数据进环形缓冲区，再用用户态程序导出成 JSONL——附完整的踩坑记录。'
pubDate: 2026-09-19
tags: ["KMDF", "驱动开发", "Windows"]
---

## 前言

这次做了一个完整的驱动教学项目：自己编写一个 KMDF 驱动（编译产物 `TEST.sys`），在内核态把每个 IOCTL 请求的**元数据**采集进一个固定容量的 Ring Buffer，
再配一个用户态采集器把数据导出成 `ioctl_events.jsonl`。
从写代码、编译、签名到虚拟机加载实测全流程走通，把过程和踩的坑记录下来。

## 一、设计思路

整体分三层：

1. **共用契约头 `shared_ioctl.h`** —— 内核态和用户态都包含它，保证 IOCTL 编号与结构布局两端一致；
2. **KMDF 驱动** —— 处理工作 IOCTL，每次请求完成后把一条遥测记录写入 Ring Buffer；另提供一个专用查询 IOCTL 返回快照和统计；
3. **用户态程序** —— 固定测试程序负责制造流量，采集器负责读取并导出。

### 遥测记录：只存元数据

每条记录只包含请求的"轮廓"，不碰输入/输出缓冲区的内容：

```c
#pragma pack(push, 1)
typedef struct _TEL_RECORD {
    LARGE_INTEGER Timestamp;        /* 内核系统时间 (100ns, 自 1601) */
    ULONG         Pid;              /* 请求进程 PID */
    ULONG         IoctlCode;        /* 原始 IOCTL 编号 */
    USHORT        DeviceType;       /* 从 IOCTL 编号解出的位域 */
    USHORT        Function;
    USHORT        Method;
    USHORT        Access;
    ULONG         InputLength;
    ULONG         OutputLength;
    ULONG         CompletionStatus; /* 请求完成时的 NTSTATUS */
} TEL_RECORD, *PTEL_RECORD;
#pragma pack(pop)
```

几个细节：

- `#pragma pack(1)` 定宽对齐，避免内核/用户态编译器对齐策略不同导致字段错位；
- DeviceType / Function / Method / Access 不单独传，直接从 IOCTL 编号按位域解出：

```c
#define TEL_DECODE_DEVICE_TYPE(code)  (USHORT)((((ULONG)(code)) >> 16) & 0xFFFF)
#define TEL_DECODE_FUNCTION(code)     (USHORT)((((ULONG)(code)) >>  2) & 0x0FFF)
#define TEL_DECODE_METHOD(code)       (USHORT)(((ULONG)(code)) & 0x3)
#define TEL_DECODE_ACCESS(code)       (USHORT)((((ULONG)(code)) >> 14) & 0x3)
```

- 结构里没有任何指针——只有值拷贝，天然安全。

### Ring Buffer：固定容量 + 覆盖计数

内核内存不能随意动态分配，遥测/日志类组件的通用做法就是环形缓冲区：容量恒定（这里 64 条），写满后新记录覆盖最旧的，同时 `OverwriteCount++` 如实上报"被冲掉多少"。

```c
static TEL_RECORD g_Ring[TEL_RING_CAPACITY];  /* 64 个槽位 */
static ULONG      g_WriteIndex;
static ULONG      g_TotalWrites;
static ULONG      g_OverwriteCount;
static KSPIN_LOCK g_RingLock;                 /* 自旋锁保护 */

VOID TelRecordWrite(const TEL_RECORD *Rec)
{
    KIRQL oldIrql;
    KeAcquireSpinLock(&g_RingLock, &oldIrql);
    g_Ring[g_WriteIndex] = *Rec;
    g_WriteIndex = (g_WriteIndex + 1) % TEL_RING_CAPACITY;
    g_TotalWrites++;
    if (g_TotalWrites > TEL_RING_CAPACITY)
        g_OverwriteCount++;
    KeReleaseSpinLock(&g_RingLock, oldIrql);
}
```

自旋锁在持锁期间 IRQL 升到 DISPATCH_LEVEL，所以整条路径只用非分页内存（全局数组天然如此），不会缺页——这也是为什么不在持锁路径里做任何分配或触碰分页内存。

### 两个 IOCTL，绝不混用

```c
#define TEL_IOCTL_WORK   CTL_CODE(TEL_DEVICE_TYPE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define TEL_IOCTL_QUERY  CTL_CODE(TEL_DEVICE_TYPE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
```

`EvtIoDeviceControl` 里 `TEL_IOCTL_WORK` 完成"工作"（回写请求序号）后落一条遥测；`TEL_IOCTL_QUERY` 把统计头 + 64 条快照拷给用户态，
**自己不写 Ring**，避免查询行为污染数据。
设备符号链接 `\\.\TelemetryDev`，用户态直接 `CreateFile` 打开。

## 二、踩坑记录（本次最有价值的部分）

### 1. WDK 版本重定向

VS 里构建直接报 `MSB4062: 无法加载 Microsoft.DriverKit.Build.Tasks.18.0.dll`。
原因是项目没写死 SDK 版本，MSBuild 自动解析到了**已经卸载的** 10.0.26100.0，而机器上实际装的是 10.0.28000.0。
VS 的"重定向项目"对话框又检测不到升级项（旧版本残留注册表但文件已删）。

解法：直接改 `.vcxproj`，在全部 4 个配置组里钉死版本：

```xml
<WindowsTargetPlatformVersion>10.0.28000.0</WindowsTargetPlatformVersion>
```

### 2. C4819：中文注释 + 无 BOM UTF-8

驱动项目把警告当错误，`C4819`（无效字符）直接升级成编译失败。
源文件是 UTF-8 但没带 BOM，MSVC 在代码页 936（GBK）下解码炸了。
给所有源文件加上 **UTF-8 BOM** 即可（或者项目统一加 `/utf-8` 编译选项）。

### 3. 0xE000022F：INF 不含数字签名信息

`devcon install` 一直 failed，setupapi.dev.log 里的关键行：

> `Driver package does not contain a catalog file, and Code Integrity is in Test Signing mode.`

测试签名模式下，**没有 cat 目录文件的驱动包会被 Driver Store 拒收**。完整解法三步：

```bat
Inf2Cat.exe /driver:D:\...\pkg /os:10_X64
signtool.exe sign /fd sha256 /n WDKTestCert TEST.cat
certutil -addstore Root TEST.cer
certutil -addstore TrustedPublisher TEST.cer
```

注意：cat 里记录的是 `TEST.sys` 的哈希——**每次重新编译 sys 之后都必须重新 Inf2Cat + 签名**，否则哈希对不上又会失败。

### 4. devcon 不是系统自带命令

VM 里敲 `devcon` 报"不是内部或外部命令"——它只在装了 WDK 的宿主机上，需要手动拷进 VM（`<WDK>\Tools\<版本>\x64\devcon.exe`）。

### 5. C:\Windows\System32\drivers 别乱放

这是系统自带驱动的目录（TrustedInstaller 保护），自己测试用的 INF/sys/exe 应该放自建的 `C:\drivers`。
安装后系统会自动把 sys 复制进 DriverStore 管理，`C:\drivers` 里的只是安装来源。

## 三、实测结果

测试程序四个阶段：低频 5 次 → 连续 300 次（打满 Ring）→ 不同合法长度（0/8/64/512）→ 4 类预设失败（未定义 IOCTL / 输出过小 / 输入超限 / 查询缓冲过小）。

| 指标 | 实测值 | 校验 |
|---|---|---|
| 请求总数 | 313 | 5 + 300 + 8 合法 + 4 失败（另有查询产生的记录）|
| 成功 / 失败 | 309 / 4 | 4 条失败 gle 分别对应不同错误码 |
| totalWrites | 313 | 与请求总数吻合 |
| overwriteCount | 249 | **313 − 64 = 249，分毫不差** |
| validCount | 64 | Ring 容量上限 |

最有说服力的就是覆盖数：313 次写入灌进 64 个槽位，被挤掉的最旧记录恰好是 313 − 64 = 249 条，环形缓冲区的覆盖语义被精确验证。
`ioctl_events.jsonl` 里保留的是最新的 64 条，失败请求的 `completion_status` 非 0，四个解码字段齐全。

### 遥测数据下载

- [📥 ioctl_events.jsonl：Ring Buffer 快照导出，64 条遥测记录（JSONL）](/ioctl_events.jsonl)

每行一条 JSON 事件，包含时间戳、请求进程 PID、IOCTL 编号及解出的 device_type / function / method / access 四字段、输入输出长度和完成状态。
可以搜索 `"completion_status":"0x00000000"` 之外的状态值定位那 4 条预设失败请求。

## 四、总结

- 固定容量 Ring Buffer 是内核遥测/日志组件的标准形态：容量恒定、无分配、天然保留"最近现场"，代价是旧数据被冲掉——所以必须配覆盖计数如实上报；
- 查询路径与工作路径分离的 IOCTL 设计让数据消费端不会污染数据本身；
- 驱动开发一半的时间花在工程链路上：版本匹配、签名、证书信任、部署工具。setupapi.dev.log 是排查安装问题最重要的第一手材料。

> 环境：宿主机 Windows 11 x64 + VS2026 + WDK 10.0.28000.0；VM Windows x64（测试签名模式）；驱动 KMDF，调试器 WinDbg + kdnet（备用）。
