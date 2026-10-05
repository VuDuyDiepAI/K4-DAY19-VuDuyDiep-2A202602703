#!/usr/bin/env python3
"""Crawl the two drug-topic knowledge bases used by the Knowledge Graph lab.

KB 1 (law):  BLHS 2015 (sửa đổi 2017) Chương XX + Luật Phòng, chống ma túy 2021 Chương I,
             from vi.wikisource.org — one Markdown file per "Điều".
KB 2 (news): recent articles from the tuoitre.vn "ma-tuy" tag — one file per article.

Same rules as scripts/fetch_public_pages.py: robots.txt checked, >= 1 s between requests,
provenance (source_url, retrieved_at, document_version) written to front matter + sources.csv.

    python scripts/crawl_drug_corpus.py --news-limit 20
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).parent))
from fetch_public_pages import DEFAULT_USER_AGENT, markdown_document, write_manifest  # noqa: E402

WIKISOURCE = "https://vi.wikisource.org/wiki/"
BLHS = "Bộ luật Hình sự nước Cộng hòa xã hội chủ nghĩa Việt Nam 2015 (sửa đổi, bổ sung 2017)"
LAW_PAGES = [
    # (wiki title, law short name, document_version)
    (f"{BLHS}/Phần thứ hai/Chương XX", "BLHS", "100/2015/QH13 sửa đổi bởi 12/2017/QH14"),
    ("Luật Phòng, chống ma túy nước Cộng hòa xã hội chủ nghĩa Việt Nam 2021/Chương I", "Luật PCMT", "73/2021/QH14"),
]
NEWS_TAG_PAGES = ["https://tuoitre.vn/timeline-tag/ma-tuy/trang-{}.htm".format(n) for n in range(1, 6)]
ARTICLE_LINK = re.compile(r'href="(/[a-z0-9-]+-\d{15,}\.htm)"')
DIEU_HEADING = re.compile(r"^Điều (\d+)\.\s*(.+)$", re.MULTILINE)

_robots: dict[str, RobotFileParser] = {}
_last_request = 0.0

def fetch(url: str, delay: float) -> str:
    """GET with robots.txt check and politeness delay. Raises PermissionError if disallowed."""
    global _last_request
    host = "/".join(url.split("/")[:3])
    if host not in _robots:
        parser = RobotFileParser()
        robots = urlopen(Request(host + "/robots.txt", headers={"User-Agent": DEFAULT_USER_AGENT}), timeout=20)
        parser.parse(robots.read().decode("utf-8", "replace").splitlines())
        _robots[host] = parser
    if not _robots[host].can_fetch(DEFAULT_USER_AGENT, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0.0, delay - (time.monotonic() - _last_request)))
    _last_request = time.monotonic()
    with urlopen(Request(url, headers={"User-Agent": DEFAULT_USER_AGENT}), timeout=60) as response:  # noqa: S310
        return response.read().decode("utf-8", "replace")

def html_to_text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style|sup|figure|table)[\s\S]*?</\1>", "", fragment)
    fragment = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>|</li>", "\n", fragment)
    text = html.unescape(re.sub(r"<[^>]*(>|$)", "", fragment)).replace("\u200b", "")
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

def crawl_law(out_dir: Path, delay: float, manifest: dict) -> int:
    saved = 0
    for title, law, version in LAW_PAGES:
        url = WIKISOURCE + quote(title.replace(" ", "_"))
        page = fetch(url, delay)
        body = page[page.find("mw-parser-output"): page.find('class="printfooter"')]
        text = html_to_text(body)
        text = "\n".join(line for line in text.splitlines() if not line.startswith(("▲", "↑", "^")))
        heads = list(DIEU_HEADING.finditer(text))
        for index, head in enumerate(heads):
            end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            content = re.split(r"\n(?:Chú thích|Tham khảo|Ghi chú)\n", text[head.start():end])[0].strip()
            number, name = head.group(1), head.group(2).strip()
            doc_id = f"{'blhs' if law == 'BLHS' else 'pcmt'}-dieu-{number}"
            metadata = {
                "doc_id": doc_id, "title": f"Điều {number} {law}. {name}", "source_url": url,
                "retrieved_at": date.today().isoformat(), "document_version": version,
                "kb": "law", "law": law, "article": f"Điều {number} {law}", "language": "vi",
            }
            write_doc(out_dir, metadata, content, manifest)
            saved += 1
    return saved

def crawl_news(out_dir: Path, delay: float, limit: int, manifest: dict) -> int:
    links: list[str] = []
    for tag_page in NEWS_TAG_PAGES:
        for path in ARTICLE_LINK.findall(fetch(tag_page, delay)):
            if path not in links:
                links.append(path)
        if len(links) >= limit * 2:
            break
    saved = 0
    for path in links:
        if saved >= limit:
            break
        url = urljoin("https://tuoitre.vn", path)
        try:
            page = fetch(url, delay)
        except (OSError, PermissionError) as error:
            print(f"Skipping {url}: {error}", file=sys.stderr)
            continue
        title = re.search(r'<h1[^>]*data-role="title"[^>]*>([\s\S]*?)</h1>', page)
        sapo = re.search(r'<(?:p|h2)[^>]*data-role="sapo"[^>]*>([\s\S]*?)</(?:p|h2)>', page)
        published = re.search(r'itemprop="datePublished" datetime="([^"]+)"', page)
        start = page.find('data-role="content"')
        paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", page[start: page.find("detail-author-bot", start)])
        body = "\n\n".join(p for p in (html_to_text(p) for p in paragraphs) if len(p) > 40)
        if not title or "ma túy" not in (title.group(1) + body).lower() or len(body) < 300:
            continue
        metadata = {
            "doc_id": "news-" + path.strip("/").rsplit("-", 1)[-1].removesuffix(".htm"),
            "title": html_to_text(title.group(1)), "source_url": url,
            "retrieved_at": date.today().isoformat(),
            "document_version": html.unescape(published.group(1)) if published else "not-stated",
            "kb": "news", "publisher": "tuoitre.vn", "language": "vi",
        }
        lead = html_to_text(sapo.group(1)) + "\n\n" if sapo else ""
        write_doc(out_dir, metadata, lead + body, manifest)
        saved += 1
    return saved

def write_doc(out_dir: Path, metadata: dict, content: str, manifest: dict) -> None:
    path = out_dir / f"{metadata['doc_id']}.md"
    path.write_text(markdown_document(metadata, content), encoding="utf-8")
    manifest[metadata["doc_id"]] = {**metadata, "file_path": path.as_posix(), "license_or_permission": (
        "public-domain-legal-text" if metadata["kb"] == "law" else "public-news-excerpt-for-education")}
    print(f"Saved {path}")

def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--law-dir", type=Path, default=Path("data/drug_law"))
    parser.add_argument("--news-dir", type=Path, default=Path("data/drug_news"))
    parser.add_argument("--news-limit", type=int, default=20)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()
    if args.delay < 1:
        print("--delay must be at least 1 second to respect source websites.", file=sys.stderr)
        return 2
    for out_dir, crawl in ((args.law_dir, lambda d, m: crawl_law(d, args.delay, m)),
                           (args.news_dir, lambda d, m: crawl_news(d, args.delay, args.news_limit, m))):
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict = {}
        count = crawl(out_dir, manifest)
        write_manifest(out_dir / "sources.csv", manifest)
        print(f"{out_dir}: {count} documents")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
