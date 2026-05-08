#!/usr/bin/env python3
"""Scrape news headlines from a webpage and display them as a numbered list."""

import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser


class HeadlineParser(HTMLParser):
    """Extract text from common headline tags: h1, h2, h3, article titles."""

    HEADLINE_TAGS = {"h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.headlines = []
        self._current_tag = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HEADLINE_TAGS:
            self._current_tag = tag
            self._current_text = []

    def handle_endtag(self, tag):
        if tag == self._current_tag and tag in self.HEADLINE_TAGS:
            text = " ".join("".join(self._current_text).split())
            if text:
                self.headlines.append(text)
            self._current_tag = None
            self._current_text = []

    def handle_data(self, data):
        if self._current_tag in self.HEADLINE_TAGS:
            self._current_text.append(data)


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def scrape_newsfeed(url: str, limit: int = 20) -> list[str]:
    html = fetch_html(url)
    parser = HeadlineParser()
    parser.feed(html)
    return parser.headlines[:limit]


def display(headlines: list[str]) -> None:
    if not headlines:
        print("No headlines found.")
        return
    for i, headline in enumerate(headlines, start=1):
        print(f"{i:>3}. {headline}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python newsfeed_scraper.py <URL> [limit]")
        print("Example: python newsfeed_scraper.py https://news.ycombinator.com 10")
        sys.exit(1)

    url = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    try:
        headlines = scrape_newsfeed(url, limit)
        print(f"\n=== Newsfeed from {url} ===\n")
        display(headlines)
    except urllib.error.URLError as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
