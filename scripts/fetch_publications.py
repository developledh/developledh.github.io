#!/usr/bin/env python3
"""
Google Scholar 자동 연동 스크립트 (경량화 버전)
- 프로필 한 번만 요청 → 개별 논문 상세 요청 없음 (빠르고 안정적)
- GitHub Actions에서 주기적으로 실행되어 publications/_index.md 자동 갱신
- 실행 전: pip install scholarly
- 환경변수 (GitHub Secrets):
    SCHOLAR_ID   : Google Scholar URL의 user= 뒤 값
    AUTHOR_NAME  : Bold 처리할 본인 이름 (예: DH Lee)
"""

import os
import sys
import re
import time
from datetime import datetime

try:
    from scholarly import scholarly
except ImportError:
    print("scholarly not installed. Run: pip install scholarly")
    sys.exit(1)

# ── 설정 ──────────────────────────────────────────────────────────────
SCHOLAR_ID  = os.environ.get("SCHOLAR_ID", "YOUR_SCHOLAR_ID_HERE")
AUTHOR_NAME = os.environ.get("AUTHOR_NAME", "Your Name")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content", "publications", "_index.md"
)
# ──────────────────────────────────────────────────────────────────────


def bold_author(authors: str, name: str) -> str:
    """저자 목록에서 본인 이름 Bold 처리 (여러 형태 지원)."""
    if not name or not authors:
        return authors
    parts = name.strip().split()
    patterns = [re.escape(name)]
    if len(parts) >= 2:
        last, first = parts[-1], parts[0]
        fi = first[0]
        patterns += [
            rf"{re.escape(last)},?\s+{re.escape(fi)}\.?",
            rf"{re.escape(last)},?\s+{re.escape(first)}",
            rf"{re.escape(fi)}\.\s+{re.escape(last)}",
        ]
    return re.sub(f"({'|'.join(patterns)})", r"**\1**", authors, flags=re.IGNORECASE)


def fetch_author(scholar_id: str):
    """Scholar 프로필 + 논문 목록 한 번에 가져오기 (fill 1회)."""
    print(f"Google Scholar에서 프로필 가져오는 중... (ID: {scholar_id})")
    for attempt in range(1, 4):
        try:
            author = scholarly.search_author_id(scholar_id)
            # sortby='pubdate' 로 최신순 정렬, 개별 논문 상세 fill 없음
            author = scholarly.fill(author, sections=["publications"], sortby="pubdate")
            return author
        except Exception as e:
            print(f"  시도 {attempt}/3 실패: {e}")
            if attempt < 3:
                time.sleep(15 * attempt)
    return None


def group_by_year(publications: list) -> dict:
    groups: dict = {}
    for pub in publications:
        year = str(pub.get("bib", {}).get("pub_year", "")).strip() or "Preprint"
        groups.setdefault(year, []).append(pub)
    return groups


def format_pub(pub: dict, author_name: str, scholar_id: str) -> str:
    bib   = pub.get("bib", {})
    title = bib.get("title", "Unknown Title").strip()

    # 저자 (이름 Bold)
    raw_authors = bib.get("author", "")
    authors = bold_author(raw_authors, author_name)

    # 게재지
    venue = (bib.get("venue") or bib.get("journal") or bib.get("booktitle") or "").strip()
    year  = str(bib.get("pub_year", "")).strip()

    # URL
    pub_url    = pub.get("pub_url", "").strip()
    author_pid = pub.get("author_pub_id", "").strip()
    link = pub_url or (
        f"https://scholar.google.com/citations?"
        f"view_op=view_citation&citation_for_view={author_pid}"
        if author_pid else ""
    )

    # 피인용 수
    citedby  = pub.get("num_citations", 0)
    cite_str = f" · Cited by {citedby}" if citedby else ""

    title_md = f"**[{title}]({link})**" if link else f"**{title}**"
    parts = [title_md]
    if authors:
        parts.append(authors)
    venue_year = ", ".join(filter(None, [f"*{venue}*" if venue else "", year]))
    if venue_year:
        parts.append(venue_year + cite_str)
    elif cite_str:
        parts.append(cite_str.strip(" · "))

    return "  \n".join(parts)


def generate_markdown(pubs_by_year: dict, author_name: str, scholar_id: str) -> str:
    updated     = datetime.now().strftime("%B %Y")
    scholar_url = f"https://scholar.google.com/citations?user={scholar_id}&sortby=pubdate"

    md = f"""---
title: "Publications"
url: /publications/
hidemeta: true
showtoc: false
---

## Publications

*Last updated: {updated} &nbsp;·&nbsp; [Google Scholar 프로필]({scholar_url})*

---
"""
    sorted_years = sorted(
        pubs_by_year.keys(),
        key=lambda y: int(y) if y.isdigit() else 0,
        reverse=True,
    )
    for year in sorted_years:
        md += f"\n### {year}\n\n"
        for pub in pubs_by_year[year]:
            md += format_pub(pub, author_name, scholar_id) + "\n\n---\n\n"

    return md.rstrip() + "\n"


def main():
    if SCHOLAR_ID == "YOUR_SCHOLAR_ID_HERE":
        print("SCHOLAR_ID 환경변수를 설정해 주세요.")
        sys.exit(1)

    print(f"Scholar ID : {SCHOLAR_ID}")
    print(f"Author Name: {AUTHOR_NAME}")

    author = fetch_author(SCHOLAR_ID)
    if not author:
        print("프로필 가져오기 실패. 기존 파일 유지.")
        sys.exit(1)

    pubs = author.get("publications", [])
    print(f"논문 {len(pubs)}편 발견.")

    pubs_by_year = group_by_year(pubs)
    markdown     = generate_markdown(pubs_by_year, AUTHOR_NAME, SCHOLAR_ID)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"완료! {OUTPUT_PATH} 업데이트됨.")


if __name__ == "__main__":
    main()
