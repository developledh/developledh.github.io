#!/usr/bin/env python3
"""
Google Scholar 자동 연동 스크립트
- GitHub Actions에서 주기적으로 실행되어 publications/_index.md 자동 갱신
- 실행 전: pip install scholarly
- 환경변수 설정 (GitHub Secrets):
    SCHOLAR_ID   : Google Scholar 프로필 ID (URL의 user= 뒤 값)
    AUTHOR_NAME  : 논문에서 Bold 처리할 본인 이름 (예: Donghyeon Lee)
"""

import os
import sys
import time
import re
from datetime import datetime

try:
    from scholarly import scholarly, ProxyGenerator
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
MAX_RETRIES = 3
# ──────────────────────────────────────────────────────────────────────


def bold_author(authors: str, name: str) -> str:
    """
    저자 목록에서 본인 이름을 **Bold** 처리.
    'Lee, D.H.' / 'D. Lee' / 'Donghyeon Lee' 등 다양한 형태 지원.
    """
    if not name or not authors:
        return authors

    # 풀네임 매칭 (대소문자 무시)
    parts = name.strip().split()
    patterns = [re.escape(name)]  # 전체 이름

    if len(parts) >= 2:
        last  = parts[-1]
        first = parts[0]
        first_initial = first[0]
        # "Lee, D." / "Lee, Donghyeon" 형태
        patterns.append(rf"{re.escape(last)},?\s+{re.escape(first_initial)}\.?")
        patterns.append(rf"{re.escape(last)},?\s+{re.escape(first)}")
        # "D. Lee" 형태
        patterns.append(rf"{re.escape(first_initial)}\.\s+{re.escape(last)}")

    combined = "|".join(patterns)
    return re.sub(f"({combined})", r"**\1**", authors, flags=re.IGNORECASE)


def fetch_author(scholar_id: str):
    """Scholar 프로필을 가져오고 실패 시 재시도."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[{attempt}/{MAX_RETRIES}] Scholar에서 프로필 가져오는 중...")
            author = scholarly.search_author_id(scholar_id)
            author = scholarly.fill(author, sections=["publications"])
            return author
        except Exception as e:
            print(f"  오류: {e}")
            if attempt < MAX_RETRIES:
                wait = 10 * attempt
                print(f"  {wait}초 후 재시도...")
                time.sleep(wait)
    return None


def fill_pub_details(pub: dict) -> dict:
    """개별 논문의 상세 정보(venue, year 등) 보완."""
    try:
        return scholarly.fill(pub)
    except Exception:
        return pub


def group_by_year(publications: list) -> dict:
    """연도별로 논문 그룹핑. 연도 없으면 'Preprint'로."""
    groups: dict = {}
    for pub in publications:
        bib  = pub.get("bib", {})
        year = str(bib.get("pub_year", "")).strip() or "Preprint"
        groups.setdefault(year, []).append(pub)
    return groups


def format_pub(pub: dict, author_name: str, scholar_id: str) -> str:
    """논문 하나를 마크다운 형식으로 변환."""
    bib   = pub.get("bib", {})
    title = bib.get("title", "Unknown Title").strip()

    # 저자
    raw_authors = bib.get("author", "")
    authors = bold_author(raw_authors, author_name)

    # 게재지
    venue = (
        bib.get("venue")
        or bib.get("journal")
        or bib.get("booktitle")
        or ""
    ).strip()

    year = str(bib.get("pub_year", "")).strip()

    # URL
    pub_url    = pub.get("pub_url", "").strip()
    author_pid = pub.get("author_pub_id", "").strip()
    link = pub_url or (
        f"https://scholar.google.com/citations?"
        f"view_op=view_citation&citation_for_view={author_pid}"
        if author_pid else ""
    )

    # 피인용 수
    citedby = pub.get("num_citations", 0)
    cite_str = f" · Cited by {citedby}" if citedby else ""

    lines = []
    title_md = f"**[{title}]({link})**" if link else f"**{title}**"
    lines.append(title_md)
    if authors:
        lines.append(authors)
    venue_year = ", ".join(filter(None, [f"*{venue}*" if venue else "", year]))
    if venue_year:
        lines.append(venue_year + cite_str)
    elif cite_str:
        lines.append(cite_str.strip(" · "))

    return "  \n".join(lines)


def generate_markdown(pubs_by_year: dict, author_name: str, scholar_id: str) -> str:
    updated = datetime.now().strftime("%B %Y")
    scholar_url = (
        f"https://scholar.google.com/citations?user={scholar_id}&sortby=pubdate"
    )

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
            md += format_pub(pub, author_name, scholar_id)
            md += "\n\n---\n\n"

    return md.rstrip() + "\n"


def main():
    if SCHOLAR_ID == "YOUR_SCHOLAR_ID_HERE":
        print("SCHOLAR_ID가 설정되지 않았습니다.")
        print("GitHub Secret 또는 환경변수로 SCHOLAR_ID를 설정해 주세요.")
        sys.exit(1)

    print(f"Scholar ID : {SCHOLAR_ID}")
    print(f"Author Name: {AUTHOR_NAME}")
    print(f"출력 경로  : {OUTPUT_PATH}")
    print()

    author = fetch_author(SCHOLAR_ID)
    if not author:
        print("프로필 가져오기 실패. 기존 파일 유지.")
        sys.exit(1)

    raw_pubs = author.get("publications", [])
    print(f"논문 {len(raw_pubs)}편 발견. 상세 정보 수집 중...")

    # 논문 상세 채우기 (너무 많으면 상위 30편만)
    filled_pubs = []
    for i, pub in enumerate(raw_pubs[:30]):
        print(f"  [{i+1}/{min(len(raw_pubs), 30)}] {pub.get('bib',{}).get('title','')[:60]}...")
        filled_pubs.append(fill_pub_details(pub))
        time.sleep(0.5)   # 과도한 요청 방지

    pubs_by_year = group_by_year(filled_pubs)
    markdown = generate_markdown(pubs_by_year, AUTHOR_NAME, SCHOLAR_ID)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n완료! {OUTPUT_PATH} 업데이트됨.")


if __name__ == "__main__":
    main()
