---
title: 'Windows 驱动信息整理'
description: '记录本机驱动服务列表与驱动签名校验信息'
pubDate: 2026-09-05
---

## 说明

在虚拟机中配置了sysmon系统监视器，采集正常驱动加载事件，使用脚本提取了driver_events.csv，随后使用drivertnery导出current_drivers.csv，当前状态快照。将csv导出作为存档

## 附件

- [📥 sysmon侧：历史加载事件，脚本产物（CSV）](/driver_events.csv)
- [📥 driverquery 侧：当前状态快照（CSV）](/current_drivers.csv)

## 注

- 大部分系统驱动都来自 Microsoft Windows，签名校验状态为 Valid。
- 少数第三方驱动（如 VMware 相关）由硬件兼容性发布者签名。
- BYOVD关注的是：这个驱动有没有可以被利用的漏洞，在加载时有没有利用它
  