---
title: '不用剪辑软件做视频：一次 ffmpeg + Node.js 的命令行创作实录'
description: '给 Mili 的《world.execute(me);》做一支 ASCII 风格 MV 的完整记录：机器上没有 ffmpeg 怎么办、6371 帧怎么画、B 站和网易云的素材从哪来，以及最重要的一课——渲染必须是确定性的。'
pubDate: 2026-10-05
tags: ['ffmpeg', 'Node.js', '创作']
---

## 前言

前几天给自己挖了个坑：想给 Mili 的《world.execute(me);》做一支 MV，风格定为「琥珀色荧光屏上的 ASCII 终端」。成品是一支 3 分 32 秒、1080p、30fps 的视频——整个过程没有打开过任何剪辑软件。

做完回头看，最大的收获其实是重新理解了视频的本质：**它就是一堆按顺序命名的图片，加一条音轨**。剩下的所有事情——画每一帧、查歌词时间轴、下载参考素材、把图片序列压成视频——全部可以用代码和命令行解决。这篇文章把这条流水线拆开讲一遍，重点是 ffmpeg 和几个真正帮上忙的工具，代码都附上了，可以直接抄。

## 一、第一个坎：这台机器上根本没有 ffmpeg

打开终端敲 `ffmpeg -version`，得到的是熟悉的「不是内部或外部命令」。去官网下载、解压、配 PATH，一套流程下来挺烦的——但其实有一条懒人路线：**用 pip 借一个**。

```
pip install imageio-ffmpeg
```

`imageio-ffmpeg` 本来是 Python 图像库 imageio 的附属包，它的职责很简单：随身带一个编译好的静态 ffmpeg 可执行文件。装完之后用一行 Python 把它的路径打印出来：

```python
import imageio_ffmpeg
print(imageio_ffmpeg.get_ffmpeg_exe())
# C:\Users\你\AppData\...\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe
```

在 bash 里可以直接把它存成变量用：

```bash
FFMPEG="$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
"$FFMPEG" -version
```

这个方案的好处是：**不碰 PATH，不污染系统，升级 pip 包就等于升级 ffmpeg**。另外记得确认它带了 mp3 编码器（后面处理音频要用）：

```bash
"$FFMPEG" -encoders | grep mp3
```

能看到 `libmp3lame` 就说明齐活了。

## 二、思路：视频就是一堆图片加一条音轨

确定了工具，接下来是整条流水线的骨架。MV 是 30fps、约 212 秒，所以总共要画 6371 张图，每张 1920×1080，命名成 `frames/0001.png` 到 `frames/6371.png`。最后的合成由一段 ffmpeg 命令完成：

```bash
ffmpeg -y -framerate 30 -i frames/%04d.png -i audio.mp3 \
  -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest output.mp4
```

这行命令值得逐个参数讲清楚，因为它们每一个都有存在的理由：

- `-framerate 30`：告诉 ffmpeg 这些图片按每秒 30 张的速度播放。注意它必须写在 `-i` **前面**，因为它描述的是输入的属性，写错位置会被当成输出参数而静默失效。
- `frames/%04d.png`：C 语言 printf 风格的通配符，`%04d` 匹配补零到四位的数字。所以画帧的时候一定要用 `String(i).padStart(4, '0')` 命名，否则文件排序乱了，ffmpeg 读出来的帧序就是错的。
- `-c:v libx264`：视频用 H.264 编码。不新、不旧，所有平台都认。
- `-crf 17`：质量控制，取值 0–51，数字越小质量越高、体积越大。默认 23 已经不错，17 基本达到肉眼无损。我的 MV 大量画面是细小的 ASCII 字符，压狠了会糊成一团，所以取了 17——最终 3 分半的视频约 60MB，可以接受。
- `-preset slow`：编码器花更多时间换更好的压缩率。合成只跑一次，慢一点无所谓。
- `-pix_fmt yuv420p`：**最容易踩的坑**。canvas 画出来的是 RGB，而很多播放器（手机、微信内置浏览器）只认 YUV420 像素格式，不加这个参数，视频在你电脑上好好的，发给别人就是黑屏。
- `-c:a aac -b:a 192k`：音轨转成 AAC。mp3 也能封装进 mp4，但 AAC 兼容性更好。
- `-shortest`：视频轨和音轨长度不一致时，以短的为准截断。

所以整条流水线真正要写的代码只有两块：**怎么把 6371 帧画出来**，以及**素材从哪来**。

## 三、画帧：@napi-rs/canvas

在 Node 里画图有几个选择：起个无头浏览器截屏（太重）、用 sharp 合成 SVG（文字排版很别扭）、或者用 canvas。我选了 `@napi-rs/canvas`，决定性理由是它**提供预编译的二进制包**——在 Windows 上 `npm install` 直接成功，不用跟 node-gyp 和 Visual Studio 构建工具搏斗。API 和浏览器的 canvas 完全一致，会前端就上手。

```js
npm install @napi-rs/canvas
```

第一个要解决的问题是字体。浏览器里写 `font = 'monospace'` 就能跑，因为浏览器会替你找系统字体；但 Node 是个无头环境，**没有任何字体回退机制，所有字体必须显式注册**：

```js
import { createCanvas, GlobalFonts } from '@napi-rs/canvas';

GlobalFonts.registerFromPath('C:/Windows/Fonts/CascadiaMono.ttf', 'CascadiaMono');
GlobalFonts.registerFromPath('C:/Windows/Fonts/msyh.ttc', 'MSYH');
```

我的 MV 里终端字符用 Cascadia Mono（等宽，终端味的来源），歌词字幕用微软雅黑——中文渲染必须用 `.ttc` 这类 CJK 字体，否则全是方块。顺便说一句，`.ttc` 是 TrueType Collection，一个文件里打包了多个字重，`registerFromPath` 能直接处理。

画帧的主循环没什么玄机，就是「按帧号算出这一帧该长什么样，然后画出来存盘」：

```js
const canvas = createCanvas(1920, 1080);
const ctx = canvas.getContext('2d');

for (let i = 0; i < TOTAL_FRAMES; i++) {
  renderFrame(ctx, i);          // 一切画面逻辑都从这个帧号出发
  fs.writeFileSync(
    `frames/${String(i).padStart(4, '0')}.png`,
    canvas.toBuffer('image/png')
  );
}
```

6371 帧平均每帧 128 毫秒，全程渲完大约十四分钟。还有一个好用的小功能值得点名：`ctx.filter = 'blur(4px)'` 是可用的。MV 里那层 CRT 荧光屏的辉光效果，就是把文字先模糊画一遍、再清晰画一遍叠出来的。

## 四、最重要的一课：渲染必须是确定性的

这是整个项目里我认为最值钱的经验。

MV 里大量效果需要「随机」：故障艺术（glitch）的撕裂位置、雪花噪点、数据流的乱码字符。直觉写法是 `Math.random()`——但这会埋下一颗雷：

**渲染中途改了某一幕的代码，只想重渲那一幕的几千帧，重渲出来的像素和旁边没动过的帧对不上。** 肉眼未必看得出单帧差异，但播起来接缝处会闪烁。更糟的是调试：你说「第 2333 帧画面不对」，可每次渲染第 2333 帧都不一样，根本没法复现。

解法是把整条规则倒过来——**画面是帧号的纯函数**：`frame = f(frameIndex)`，同一个帧号永远产出同一张图。项目里专门写了个检查脚本强制执行，源码里禁止出现三样东西：

1. `Math.random()` —— 换成带种子的伪随机数；
2. `Date.now()` —— 时间必须由帧号推算（`t = frameIndex / 30`），不能反过来；
3. `requestAnimationFrame` —— 这是浏览器 API，Node 里根本没有；动画的本质不是「每秒画 30 次的循环」，而是「第 i 帧长什么样」这个函数。

伪随机数用 mulberry32，十几行，够快够好：

```js
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 每一帧用自己的帧号（乘个质数散一下）做种子
const rand = mulberry32(frameIndex * 7919);
```

原理一句话：伪随机数生成器是「拿种子算出下一个数的数学函数」，**种子相同，产出的数列就完全相同**。所以每个故障效果在生成前先播种一次帧号——人眼看它是乱的，机器看它是恒定的。「随机」和「可复现」就这样同时成立了。

这个性质看起来是洁癖，实际上是后面所有工程手段的地基。

## 五、素材从哪来

### 5.1 参考视频：B 站的两步下载

动工前我参考了一支 B 站上的同类 ASCII MV（BV1Jwhy6BEMJ）来定版式。想把它下载下来拆解，登录、装客户端都懒得弄，其实两步 API 就够了：

```bash
# 第一步：BV 号换 cid（视频分 P 后每一段有自己的 cid）
curl "https://api.bilibili.com/x/web-interface/view?bvid=BV1Jwhy6BEMJ"
# 响应的 data.cid 字段就是第二步要用的

# 第二步：cid 换真实播放地址
curl "https://api.bilibili.com/x/player/playurl?bvid=BV1Jwhy6BEMJ&cid=XXXXXX&platform=html5&high_quality=1"
# 响应的 durl[0].url 就是 mp4 直链
```

拿到直链直接下会得到 403，因为 B 站的 CDN 做了**防盗链**：它校验请求头里的 `Referer`，不是从 b 站页面发起的下载一律拒绝。带上两个头就过了：

```bash
curl -o ref.mp4 "$URL" \
  -H "User-Agent: Mozilla/5.0" \
  -H "Referer: https://www.bilibili.com"
```

代价是不登录最高只能拿 360P、音质约 65kbps。对「研究构图和节奏」这个用途完全够了——毕竟参考视频只是给人看的，不是往成片里拼的。

### 5.2 歌词时间轴：网易云的歌词接口

MV 的场景切换全部由歌词时间驱动：副歌唱到哪个词、故障强度在哪一秒拉满，都锚定在具体的歌词时间点上。时间轴的来源是网易云的公开接口，也是两步：

```bash
# 搜索拿歌曲 id
curl "https://music.163.com/api/search/get?s=world.execute(me);&type=1"

# 拉歌词：lv=1 要原文 LRC，tv=-1 顺便带上官方翻译
curl "https://music.163.com/api/song/lyric?id=XXXXXX&lv=1&tv=-1"
```

返回的 `lrc.lyric` 是标准 LRC 格式，长这样：

```
[02:03.45]And there was a software
[02:06.10]that ran the world
```

解析它只需要一个正则加一次进制换算。注意 LRC 允许一行带多个时间戳（`[00:12.00][00:15.00]同一句`），所以要用 `matchAll` 把所有时间戳都收进来：

```js
function parseLrc(text) {
  const lines = [];
  for (const raw of text.split('\n')) {
    const stamps = [...raw.matchAll(/\[(\d+):(\d+(?:\.\d+)?)\]/g)];
    const content = raw.replace(/\[(\d+):(\d+(?:\.\d+)?)\]/g, '').trim();
    for (const [, mm, ss] of stamps) {
      lines.push({ time: Number(mm) * 60 + Number(ss), text: content });
    }
  }
  return lines.sort((a, b) => a.time - b.time);
}
```

渲染时从帧号反推时间，再找出当前正在唱的那一行，这一帧的画面内容就定了：

```js
const t = frameIndex / 30;                       // 第几秒
const current = lyrics.findLast(l => l.time <= t); // 最近一条开始唱的歌词
```

`findLast` 是 ES2023 的数组方法，语义正好是「最后一次满足条件的位置」——比手写倒序循环清楚得多。

## 六、局部重渲染：改一幕，不必全部重来

流水线搭好之后，真正的迭代才刚开始——而迭代能不能转得动，取决于改一处要等多久。全量渲染十四分钟显然不能接受。

好在第四节的确定性在这里兑现了价值：既然每一帧只由帧号决定，那么**帧与帧之间没有任何隐藏状态**，重渲某个区间完全不影响区间外的帧。渲染脚本支持指定范围：

```bash
node render.js --from 3000 --to 3400
```

这会把 3000 到 3400 帧的 PNG **直接覆盖**（不是断点续渲，是覆写区间），然后重跑一次合成。ffmpeg 合成 6371 张图大约九十秒——于是「改一行代码 → 看效果」的循环被压缩到了两分钟以内，够把一个场景磨到满意为止。

区间边界会不会有缝？不会，这正是确定性渲染的回报：第 2999 帧和第 3401 帧从没被重渲过，它们和重渲区间内任何一帧的关系，跟最初渲染时一模一样。

## 七、写在最后

最终成片：1080p、30fps、3 分 32 秒、约 60MB，一气呵成地生成，也可以精确到任意帧重新生成。整条流水线用到的工具汇总一下：

| 环节 | 工具 | 一句话说明 |
| --- | --- | --- |
| 拿到 ffmpeg | imageio-ffmpeg | `pip install` 借一个静态二进制，不碰 PATH |
| 画帧 | @napi-rs/canvas | 预编译、API 与浏览器 canvas 一致，记得手动注册字体 |
| 合成 | ffmpeg | `libx264 + crf 17 + yuv420p + aac`，兼容性拉满 |
| 参考视频 | B 站 web API | view 拿 cid → playurl 拿直链，记得带 Referer |
| 歌词时间轴 | 网易云 API | `lrc` 带时间戳原文，`tlyric` 带官方翻译 |

最后说点感受。剪辑软件适合「看着素材做决定」的创作——素材是既成的，人在时间线上排列组合。而程序化视频适合另一类创作：**当整个画面可以被描述成一个函数 `f(frameIndex)`**，你得到的是剪辑软件给不了的三样东西——可以整体推翻重来的渲染、精确到单帧的调试、以及一份永远不会「丢工程文件」的代码仓库。

以后再有人跟我说「视频做不了」，我大概会先问一句：你的 ffmpeg 路径找到了吗？
