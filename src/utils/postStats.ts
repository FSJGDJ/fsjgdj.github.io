// 文章统计：字数与预计阅读时长，均由正文自动计算
// 口径：剔除代码块后，中日韩字符按字计，其余按空格分词计；
// 中文约 400 字/分钟估算阅读时长
export interface PostStats {
  words: number;
  minutes: number;
}

export function getPostStats(body: string): PostStats {
  const text = body
    .replace(/```[\s\S]*?```/g, " ") // 代码块不计入正文字数
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ") // 图片语法
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // 链接保留文字
    .replace(/[#>*`~|]/g, " ");
  const CJK = /[一-鿿぀-ヿ＀-￯]/g;
  const cjkCount = (text.match(CJK) ?? []).length;
  const wordCount = text
    .replace(CJK, " ")
    .split(/\s+/)
    .filter(Boolean).length;
  const words = cjkCount + wordCount;
  return { words, minutes: Math.max(1, Math.ceil(words / 400)) };
}
