#!/usr/bin/env python3
"""
Google Scholar 논문 자동 수집 스크립트 (scholarly + FreeProxies)
- FreeProxies: scholarly 내장 무료 프록시 풀로 GitHub Actions CI 차단 우회
- 환경변수:
    SCHOLAR_ID   : Google Scholar URL의 user= 뒤 값
    AUTHOR_NAME  : Bold 처리할 본인 이름 (예: DH Lee)
- 로컬 실행: python scripts/fetch_publications.py
- CI 실행: GitHub Actions에서 자동 실행 (USE_FREE_PROXY=true)
"""

import os
import re
import sys
import time
from datetime import datetime

try:
    from scholarly import scholarly, ProxyGenerator
except ImportError:
    print("설치 필요: pip install scholarly")
    sys.exit(1)

# ── 설정 ──────────────────────────────────────────────────────────────
SCHOLAR_ID       = os.environ.get("SCHOLAR_ID", "YOUR_SCHOLAR_ID_HERE")
AUTHOR_NAME      = os.environ.get("AUTHOR_NAME", "Your Name")
USE_FREE_PROXY   = os.environ.get("USE_FREE_PROXY", "false").lower() == "true"
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content", "publications", "_index.md"
)
# ──────────────────────────────────────────────────────────────────────


def setup_proxy():
    """CI 환경에서는 FreeProxies로 IP 우회."""
    if not USE_FREE_PROXY:
        print("프록시 없이 직접 연결 (로컬 실행)")
        return True
    try:
        print("FreeProxies 설정 중 (작동 프록시 탐색, 1~2분 소요)...")
        pg = ProxyGenerator()
        pg.FreeProxies()
        scholarly.use_proxy(pg)
        print("FreeProxies 설정 완료")
        return True
    except Exception as e:
        print(f"FreeProxies 설정 오류: {e}")
        return False


def bold_author(authors: str, name: str) -> str:
    """저자 목록에서 본인 이름 **Bold** 처리."""
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
    return re.sub(f"({'|'.join(patterns)})", r"**\\1**", authors, flags=re.IGNORECASE)


def fetch_author(scholar_id: str):
    """Scholar 프로필 + 논문 목록 가져오기 (재시도 포함)."""
    for attempt in range(1, 4):
        try:
            print(f"[{attempt}/3] Scholar 프로필 가져오는 중...")
            author = scholarly.search_author_id(scholar_id)
            author = scholarly.fill(author, sections=["publications"], sortby="year")
            print(f"논문 {len(author.get('publications', []))}편 발견")
            return author
        except Exception as e:
            print(f"  실패: {e}")
            if attempt < 3:
                wait = 30 * attempt
                print(f"  {wait}초 후 재시도...")
                time.sleep(wait)
    return None


def group_by_year(publications: list) -> dict:
    groups: dict = {}
    for pub in publications:
        year = str(pub.get("bib", {}).get("pub_year", "")).strip() or "Preprint"
        groups.setdefault(year, []).append(pub)
    return groups


def format_pub(pub: dict, author_name: str, scholar_id: str) -> str:
    bib    = pub.get("bib", {})
    title  = bib.get("title", "Unknown Title").strip()
    authors = bold_author(bib.get("author", ""), author_name)
    venue  = (bib.get("venue") or bib.get("journal") or bib.get("booktitle") or "").strip()
    year   = str(bib.get("pub_year", "")).strip()

    pub_url    = pub.get("pub_url", "").strip()
    author_pid = pub.get("author_pub_id", "").strip()
    link = pub_url or (
        f"https://scholar.google.com/citations?"
        f"view_op=view_citation&citation_for_view={author_pid}"
        if author_pid else ""
    )

    citedby  = pub.get("num_citations", 0)
    cite_str = f" · Cited by {citedby}" if citedby else ""

    title_md   = f"**[{title}]({link})**" if link else f"**{title}**"
    venue_year = ", ".join(filter(None, [f"*{venue}*" if venue else "", year]))

    parts = [title_md]
    if authors:
        parts.append(authors)
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

*Last updated: {updated} &nbsp;·&nbsp; [Google Scholar]({scholar_url})*

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

    print(f"Scholar ID      : {SCHOLAR_ID}")
    print(f"Author Name     : {AUTHOR_NAME}")
    print(f"Free Proxy 사용 : {USE_FREE_PROXY}")

    if not setup_proxy():
        sys.exit(1)

    author = fetch_author(SCHOLAR_ID)
    if not author:
        print("프로필 가져오기 실패. 기존 파일 유지.")
        sys.exit(1)

    pubs_by_year = group_by_year(author.get("publications", []))
    markdown     = generate_markdown(pubs_by_year, AUTHOR_NAME, SCHOLAR_ID)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n완료! {OUTPUT_PATH} 업데이트됨.")


if __name__ == "__main__":
    main()
