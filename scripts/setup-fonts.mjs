/**
 * 霞鹜文楷 Lite（Regular）自托管字体安装 —— 一次性脚本，可重复执行。
 *
 * 为什么不用 cn-font-split 现场切字体：
 *   GitHub 在本机网络下不可达，拿不到 20MB 的源字体 TTF；
 *   而 lxgw-wenkai-lite-webfont 这个包本身就是「按 unicode-range 切好的 97 个 woff2 分片」，
 *   浏览器只会下载当前页面真正用到的那几片（通常 1~3 片，合计 <100KB），
 *   等于拿到了 cn-font-split 的产出物，还省掉一条构建流水线。
 *   代价是仓库里多约 3.9MB 的字体文件（一次性，此后无需再跑本脚本）。
 *
 * 用法：node scripts/setup-fonts.mjs
 * 幂等：已下载且非空的分片会跳过；CSS 每次重写。
 */
import fs from "node:fs/promises";
import path from "node:path";

const PKG = "lxgw-wenkai-lite-webfont";
const VERSION = "1.7.0";
const BASE = `https://unpkg.com/${PKG}@${VERSION}/`;
const OUT_DIR = path.resolve("public/fonts/lxgw");
const CONCURRENCY = 8;

const exists = async (p) => {
  try {
    const s = await fs.stat(p);
    return s.size > 0;
  } catch {
    return false;
  }
};

async function get(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res;
}

await fs.mkdir(OUT_DIR, { recursive: true });

// 1. 拉上游 CSS，改写为本地相对路径后写入
const remoteCss = await (await get(BASE + "lxgwwenkailite-regular.css")).text();
const files = [
  ...new Set(
    [...remoteCss.matchAll(/url\((['"]?)\.\/files\/([^'")]+)\1\)/g)].map((m) => m[2]),
  ),
];
const localCss = `/* 霞鹜文楷 Lite Regular v${VERSION} —— 自托管分片
 * 来源：npm ${PKG}@${VERSION}（${BASE}）
 * 授权：SIL Open Font License 1.1，允许自托管与再分发
 * 本文件由 scripts/setup-fonts.mjs 生成，请勿手改；换版本重跑该脚本即可。
 */
${remoteCss.replaceAll("./files/", "./")}`;
await fs.writeFile(path.join(OUT_DIR, "lxgw.css"), localCss);
console.log(`CSS 已写入（${files.length} 个 @font-face）`);

// 2. 并发下载分片，已存在的跳过
let done = 0;
let bytes = 0;
const queue = [...files];
const workers = Array.from({ length: CONCURRENCY }, async () => {
  while (queue.length) {
    const name = queue.shift();
    const dest = path.join(OUT_DIR, name);
    if (await exists(dest)) {
      const s = await fs.stat(dest);
      bytes += s.size;
      done++;
      continue;
    }
    const buf = Buffer.from(await (await get(BASE + "files/" + name)).arrayBuffer());
    await fs.writeFile(dest, buf);
    bytes += buf.length;
    done++;
    if (done % 20 === 0) console.log(`  ${done}/${files.length} ...`);
  }
});
await Promise.all(workers);
console.log(`分片就绪：${done} 个，合计 ${(bytes / 1048576).toFixed(2)}MB`);

// 3. 找出承载最高频汉字（含 ASCII 与「的一是不了」这类常用字）的分片，供首屏 preload
function parseRanges(spec) {
  return spec.split(",").flatMap((s) => {
    const m = s.trim().match(/^U\+([0-9a-f]+)(?:-([0-9a-f]+))?$/i);
    if (!m) return [];
    const a = parseInt(m[1], 16);
    const b = m[2] ? parseInt(m[2], 16) : a;
    const out = [];
    for (let c = a; c <= b; c++) out.push(c);
    return out;
  });
}
const faces = [...localCss.matchAll(/src:\s*url\('\.\/([^']+)'\)[^;]*;\s*unicode-range:\s*([^;]*)/g)];
const probe = [..."的一是不了在人有我他这中大为上个国来以们时地"].map((c) =>
  c.codePointAt(0),
);
const hits = new Map();
for (const [, file, range] of faces) {
  const set = new Set(parseRanges(range));
  const n = probe.filter((c) => set.has(c)).length;
  if (n) hits.set(file, n);
}
const best = [...hits.entries()].sort((a, b) => b[1] - a[1])[0];
if (best) {
  const s = await fs.stat(path.join(OUT_DIR, best[0]));
  console.log(`首屏 preload 建议：${best[0]}（命中 ${best[1]}/${probe.length} 个高频字，${(s.size / 1024).toFixed(0)}KB）`);
}
