import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import { siteConfig } from "../config";

export async function GET(context) {
  const posts = await getCollection("blog");
  return rss({
    title: siteConfig.siteName,
    description: siteConfig.description,
    site: context.site,
    items: posts
      .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf())
      .map((post) => ({
        title: post.data.title,
        description: post.data.description,
        pubDate: post.data.pubDate,
        link: `/blog/${post.id}/`,
        categories: post.data.tags,
      })),
  });
}
