from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

try:
    import feedparser
    import yaml
except ModuleNotFoundError as exc:
    print(f"必要なライブラリが見つかりません: {exc.name}")
    print("先に `pip install -r requirements.txt` を実行してください。")
    raise SystemExit(1) from exc


BASE_DIR = Path(__file__).resolve().parent
FEEDS_PATH = BASE_DIR / "feeds.yml"
KEYWORDS_PATH = BASE_DIR / "keywords.yml"
TRANSLATIONS_PATH = BASE_DIR / "translations.yml"
DOCS_DIR = BASE_DIR / "docs"
NEWS_DIR = BASE_DIR / "news"
USER_AGENT = "news-digest/1.0 (+https://github.com/) RSS reader"
MAX_ITEMS_PER_CATEGORY = 12
SUMMARY_MAX_CHARS = 140
TRANSLATIONS: dict[str, dict[str, str]] = {}


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class FeedConfig:
    category: str
    name: str
    url: str
    enabled: bool = True


@dataclass
class Article:
    category: str
    source: str
    title: str
    url: str
    summary: str
    keywords: list[str]
    title_ja: str = ""
    summary_ja: str = ""
    published_at: datetime | None = None
    published_label: str = ""
    sort_key: float = field(default=0.0)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAMLの形式が正しくありません: {path}")
    return data


def load_feeds() -> list[FeedConfig]:
    data = load_yaml(FEEDS_PATH)
    feeds: list[FeedConfig] = []
    for category, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            enabled = bool(item.get("enabled", True))
            url = str(item.get("url", "")).strip()
            name = str(item.get("name", "")).strip()
            if not enabled or not url:
                continue
            feeds.append(FeedConfig(category=str(category), name=name, url=url, enabled=enabled))
    return feeds


def load_keywords() -> dict[str, list[str]]:
    data = load_yaml(KEYWORDS_PATH)
    keywords: dict[str, list[str]] = {}
    for category, items in data.items():
        if isinstance(items, list):
            keywords[str(category)] = [str(item).strip() for item in items if str(item).strip()]
    return keywords


def load_translations() -> dict[str, dict[str, str]]:
    if not TRANSLATIONS_PATH.exists():
        return {}
    data = load_yaml(TRANSLATIONS_PATH)
    raw_articles = data.get("articles", {})
    if not isinstance(raw_articles, dict):
        return {}

    translations: dict[str, dict[str, str]] = {}
    for url, values in raw_articles.items():
        if not isinstance(values, dict):
            continue
        normalized_url = normalize_url(str(url))
        translations[normalized_url] = {
            "title_ja": str(values.get("title_ja", "")).strip(),
            "summary_ja": str(values.get("summary_ja", "")).strip(),
        }
    return translations


def normalize_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def shorten(value: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    value = strip_html(value)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def parse_entry_datetime(entry: Any) -> tuple[datetime | None, str, float]:
    for attr in ("published", "updated", "created"):
        raw_value = getattr(entry, attr, "") or entry.get(attr, "")
        if not raw_value:
            continue
        try:
            dt = parsedate_to_datetime(raw_value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone()
            return local_dt, local_dt.strftime("%Y-%m-%d %H:%M"), local_dt.timestamp()
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    return None, "", 0.0


def matched_keywords(text: str, keywords: list[str]) -> list[str]:
    haystack = text.casefold()
    matches: list[str] = []
    for keyword in keywords:
        if keyword.casefold() in haystack:
            matches.append(keyword)
    return matches


def fetch_articles(feeds: list[FeedConfig], keywords_by_category: dict[str, list[str]]) -> dict[str, list[Article]]:
    results: dict[str, list[Article]] = {category: [] for category in keywords_by_category}
    seen_urls: set[str] = set()

    for feed in feeds:
        parsed = feedparser.parse(feed.url, request_headers={"User-Agent": USER_AGENT})
        if parsed.bozo:
            print(f"[warn] RSSの取得または解析に問題があります: {feed.name} ({feed.url})")

        category_keywords = keywords_by_category.get(feed.category, [])
        for entry in parsed.entries:
            title = strip_html(getattr(entry, "title", "") or entry.get("title", ""))
            url = normalize_url(getattr(entry, "link", "") or entry.get("link", ""))
            if not title or not url or url in seen_urls:
                continue

            raw_summary = (
                getattr(entry, "summary", "")
                or entry.get("summary", "")
                or getattr(entry, "description", "")
                or entry.get("description", "")
            )
            summary = shorten(raw_summary)
            searchable = " ".join([feed.name, title, summary])
            keywords = matched_keywords(searchable, category_keywords)
            if not keywords:
                continue

            published_at, published_label, sort_key = parse_entry_datetime(entry)
            translation = TRANSLATIONS.get(url, {})
            seen_urls.add(url)
            results.setdefault(feed.category, []).append(
                Article(
                    category=feed.category,
                    source=feed.name,
                    title=title,
                    url=url,
                    summary=summary or "RSSに短い説明が含まれていません。",
                    title_ja=translation.get("title_ja", ""),
                    summary_ja=translation.get("summary_ja", ""),
                    keywords=keywords,
                    published_at=published_at,
                    published_label=published_label,
                    sort_key=sort_key,
                )
            )

    for category, articles in results.items():
        articles.sort(key=lambda article: article.sort_key, reverse=True)
        results[category] = articles[:MAX_ITEMS_PER_CATEGORY]
    return results


def display_title(article: Article) -> str:
    return article.title_ja or article.title


def display_summary(article: Article) -> str:
    return article.summary_ja or article.summary


def translated_page_url(url: str) -> str:
    return "https://translate.google.com/translate?sl=auto&tl=ja&u=" + quote(url, safe="")


def tagify(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^\wぁ-んァ-ン一-龥]+", "_", value)
    return value.strip("_")


def collect_tags(articles_by_category: dict[str, list[Article]], categories: list[str]) -> list[str]:
    tags = ["news", *categories]
    for category in categories:
        for article in articles_by_category.get(category, []):
            tags.extend(tagify(keyword) for keyword in article.keywords)
    return sorted({tag for tag in tags if tag})


def yaml_front_matter(date_label: str, tags: list[str]) -> str:
    lines = ["---", "type: news-digest", f"date: {date_label}", "tags:"]
    lines.extend(f"  - {tag}" for tag in tags)
    lines.append("---")
    return "\n".join(lines)


def article_markdown(article: Article) -> str:
    keywords = ", ".join(article.keywords)
    published = article.published_label or "不明"
    lines = [
        f"### {display_title(article)}",
        f"- 取得元: {article.source}",
        f"- 公開日時: {published}",
        f"- 概要: {display_summary(article)}",
        f"- URL: {article.url}",
        f"- 日本語翻訳リンク: {translated_page_url(article.url)}",
        f"- 関連キーワード: {keywords}",
        "- 自分への関係: 関心キーワードに一致。あとで本文を確認する。",
    ]
    if article.title_ja:
        lines.insert(1, f"- 原題: {article.title}")
    lines.append("")
    return "\n".join(lines)


def category_markdown(title: str, articles: list[Article]) -> str:
    lines = [f"## {title}", ""]
    if not articles:
        lines.extend(["該当する記事はありませんでした。", ""])
        return "\n".join(lines)
    for article in articles:
        lines.append(article_markdown(article))
    return "\n".join(lines)


def write_markdown_files(articles_by_category: dict[str, list[Article]], now: datetime) -> list[Path]:
    date_label = now.strftime("%Y-%m-%d")
    daily_dir = NEWS_DIR / "daily"
    tech_dir = NEWS_DIR / "tech"
    mma_dir = NEWS_DIR / "mma"
    for directory in (daily_dir, tech_dir, mma_dir):
        directory.mkdir(parents=True, exist_ok=True)

    tech_articles = articles_by_category.get("tech", [])
    mma_articles = articles_by_category.get("mma", [])
    daily_tags = collect_tags(articles_by_category, ["tech", "mma"])
    tech_tags = collect_tags(articles_by_category, ["tech"])
    mma_tags = collect_tags(articles_by_category, ["mma"])

    daily_content = "\n\n".join(
        [
            yaml_front_matter(date_label, daily_tags),
            f"# {date_label} ニュースまとめ",
            category_markdown("テックニュース", tech_articles),
            category_markdown("格闘技ニュース", mma_articles),
            "## 気になったこと\n\n-",
            "## あとで調べること\n\n-",
            "",
        ]
    )
    tech_content = "\n\n".join(
        [
            yaml_front_matter(date_label, tech_tags),
            f"# {date_label} テックニュース",
            category_markdown("テックニュース", tech_articles),
            "## 気になったこと\n\n-",
            "## あとで調べること\n\n-",
            "",
        ]
    )
    mma_content = "\n\n".join(
        [
            yaml_front_matter(date_label, mma_tags),
            f"# {date_label} 格闘技ニュース",
            category_markdown("格闘技ニュース", mma_articles),
            "## 気になったこと\n\n-",
            "## あとで調べること\n\n-",
            "",
        ]
    )

    paths = [
        daily_dir / f"{date_label}_ニュースまとめ.md",
        tech_dir / f"{date_label}_テックニュース.md",
        mma_dir / f"{date_label}_格闘技ニュース.md",
    ]
    for path, content in zip(paths, [daily_content, tech_content, mma_content], strict=True):
        path.write_text(content, encoding="utf-8", newline="\n")
    return paths


def article_html(article: Article) -> str:
    keywords = "".join(f"<span>{html.escape(keyword)}</span>" for keyword in article.keywords)
    published = html.escape(article.published_label or "不明")
    original_title = ""
    if article.title_ja:
        original_title = f'<p class="original-title">原題: {html.escape(article.title)}</p>'
    return f"""
      <article class="article">
        <div class="article-meta">
          <span>{html.escape(article.source)}</span>
          <span>{published}</span>
        </div>
        <h3><a href="{html.escape(article.url)}" target="_blank" rel="noopener noreferrer">{html.escape(display_title(article))}</a></h3>
        {original_title}
        <p>{html.escape(display_summary(article))}</p>
        <div class="article-links">
          <a href="{html.escape(article.url)}" target="_blank" rel="noopener noreferrer">原文</a>
          <a href="{html.escape(translated_page_url(article.url))}" target="_blank" rel="noopener noreferrer">日本語翻訳で開く</a>
        </div>
        <div class="keywords" aria-label="関連キーワード">{keywords}</div>
      </article>
    """.rstrip()


def section_html(title: str, articles: list[Article], category_class: str) -> str:
    if articles:
        body = "\n".join(article_html(article) for article in articles)
    else:
        body = '<p class="empty">該当する記事はありませんでした。</p>'
    return f"""
    <section class="section {category_class}">
      <div class="section-heading">
        <h2>{html.escape(title)}</h2>
        <span>{len(articles)}件</span>
      </div>
      <div class="articles">
{body}
      </div>
    </section>
    """.rstrip()


def write_html(articles_by_category: dict[str, list[Article]], now: datetime) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    date_label = now.strftime("%Y-%m-%d")
    updated_label = now.strftime("%Y-%m-%d %H:%M")
    tech_articles = articles_by_category.get("tech", [])
    mma_articles = articles_by_category.get("mma", [])
    total = len(tech_articles) + len(mma_articles)
    html_content = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{date_label} ニュースまとめ</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="page-header">
    <p class="date">{date_label}</p>
    <h1>ニュースまとめ</h1>
    <p class="summary">テックニュースと格闘技ニュースを、関心キーワードに合う記事だけに絞って表示しています。</p>
    <div class="stats">
      <span>合計 {total}件</span>
      <span>最終更新 {updated_label}</span>
    </div>
  </header>
  <main>
{section_html("テックニュース", tech_articles, "tech")}
{section_html("格闘技ニュース", mma_articles, "mma")}
  </main>
</body>
</html>
"""
    path = DOCS_DIR / "index.html"
    path.write_text(html_content, encoding="utf-8", newline="\n")
    return path


def print_console_summary(articles_by_category: dict[str, list[Article]]) -> None:
    labels = {"tech": "テックニュース", "mma": "格闘技ニュース"}
    for category, label in labels.items():
        articles = articles_by_category.get(category, [])
        print(f"\n## {label}: {len(articles)}件")
        if not articles:
            print("- 該当する記事はありませんでした。")
            continue
        for article in articles:
            keywords = ", ".join(article.keywords)
            print(f"- [{article.source}] {display_title(article)}")
            print(f"  {article.url}")
            print(f"  keywords: {keywords}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RSSからニュースを集めてMarkdownとHTMLを生成します。")
    parser.add_argument("--no-html", action="store_true", help="docs/index.html を生成しません。")
    parser.add_argument("--no-markdown", action="store_true", help="news/*.md を生成しません。")
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()
    now = datetime.now().astimezone()
    feeds = load_feeds()
    keywords = load_keywords()
    global TRANSLATIONS
    TRANSLATIONS = load_translations()
    articles_by_category = fetch_articles(feeds, keywords)

    print_console_summary(articles_by_category)

    if not args.no_markdown:
        paths = write_markdown_files(articles_by_category, now)
        for path in paths:
            print(f"[write] {path.relative_to(BASE_DIR)}")

    if not args.no_html:
        html_path = write_html(articles_by_category, now)
        print(f"[write] {html_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
