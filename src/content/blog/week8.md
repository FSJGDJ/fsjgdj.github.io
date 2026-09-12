---
title: '驱动程序时间线分析'
description: '通过脚本接收csv，记录虚拟机中驱动程序时间线'
pubDate: 2026-09-12
---

## 说明

把sysmon（事件ID 6），服务安装（事件ID 7045），以及drivertnery当前状态合并为统一时间线，并进行排序，html支持按驱动名称和事件类型筛选。
在脚本中统一时间格式和驱动路径，处理 %SystemRoot%、\SystemRoot、引号及大小写差异。

## 交互式报告查看

[👉 点击此处查看 Driver Timeline 交互式报告](/driver_timeline.html)

> 提示：如果无法直接预览，请右键链接选择“在新标签页打开”或下载 CSV 文件查看。

## 附件

- [📥 时间线数据（CSV）](/driver_timeline.csv)
- [🔎 交互式时间线（HTML，可筛选）](/driver_timeline.html)

## 技术细节

使用 PowerShell 脚本统一处理了：
路径标准化（%SystemRoot%、大小写）
时间格式统一
SHA256 哈希计算
签名状态验证
