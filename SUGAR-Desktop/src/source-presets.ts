/** Public publisher feeds and pages; these use the existing RSS/web collectors. */
export const SOURCE_PRESETS = [
  { id: "un", label: "UN news · 6 languages", description: "Public UN reporting in English, French, Spanish, Arabic, Chinese and Russian.",
    source: "https://www.un.org/de/delegate/page/un-news-outlets",
    feeds: ["en", "fr", "es", "ar", "zh", "ru"].map((lang) => `https://news.un.org/feed/subscribe/${lang}/news/all/rss.xml`), sites: [] as string[] },
  { id: "eu", label: "EU policy and diplomacy", description: "Council press releases and foreign affairs meetings.",
    source: "https://www.consilium.europa.eu/en/about-site/rss/",
    feeds: ["https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "https://www.consilium.europa.eu/en/rss/meetings.ashx?cat=fac"], sites: [] as string[] },
  { id: "education", label: "Education and culture", description: "UNESCO news and Council education, youth, culture and sport meetings.",
    source: "https://www.unesco.org/en/newsroom",
    feeds: ["https://www.consilium.europa.eu/en/rss/meetings.ashx?cat=eycs"], sites: ["https://www.unesco.org/en/newsroom"] },
] as const;
