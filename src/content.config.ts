import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const blog = defineCollection({
  // 从 src/content/blog/ 目录读取所有 Markdown 文件
  loader: glob({ base: './src/content/blog', pattern: '**/*.{md,mdx}' }),
  // 规定每篇文章开头必须填的信息
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
  }),
});

export const collections = { blog };