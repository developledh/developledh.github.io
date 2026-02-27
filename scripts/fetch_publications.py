#!/usr/bin/env python3
"""
Google Scholar 직접 파싱 스크립트 (scholarly 미사용)
- requests + BeautifulSoup 으로 Scholar 프로필 페이지 직접 파싱
- scholarly 봇 감지 우회 문제 없음
- 환경변수:
    SCHOLAR_ID   : Google Scholar URL의 user= 뒤 값
    AUTHOR_NAME  : Bold 처리할 본인 이름 (예: DH Lee)
"""

import os
import re
import sys
import time
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("필요 라이브러리 설치: pip install requests beautifulsoup4")
    sys.exit(1)

# ── 설정 ──────────────────────────────────────────────────────────────
SCHOLAR_ID  = os.environ.get("SCHOLAR_ID", "YOUR_SCHOLAR_ID_HERE")
AUTHOR_NAME = os.environ.get("AUTHOR_NAME", "Your Name")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content", "publications", "_index.md"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
# ──────────────────────────────────────────────────────────────────────


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
    return re.sub(f"({'|'.join(patterns)})", r"**\1**", authors, flags=re.IGNORECASE)


def fetch_page(scholar_id: str, start: int = 0) -> BeautifulSoup | None:
    """Scholar 프로필 페이지 한 페이지 가져오기."""
    url = (
        f"https://scholar.google.com/citations"
        f"?user={scholar_id}&hl=en&sortby=pubdate"
        f"&view_op=list_works&pagesize=100&cstart={start}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  페이지 요청 실패 (start={start}): {e}")
        return None


def parse_publications(soup: BeautifulSoup, scholar_id: str) -> list[dict]:
    """HTML에서 논문 목록 파싱."""
    pubs = []
    rows = soup.select("#gsc_a_b .gsc_a_tr")
    if not rows:
        print("  논문 행을 찾지 못했습니다.")
        return pubs

    for row in rows:
        title_el  = row.select_one(".gsc_a_at")
        gray_els  = row.select(".gs_gray")
        year_el   = row.select_one(".gsc_a_y span")
        cited_el  = row.select_one(".gsc_a_ac")

        if not title_el:
            continue

        title   = title_el.get_text(strip=True)
        href    = title_el.get("href", "")
        pub_url = f"https://scholar.google.com{href}" if href else ""

        authors = gray_els[0].get_text(strip=True) if len(gray_els) > 0 else ""
        venue   = gray_els[1].get_text(strip=True) if len(gray_els) > 1 else ""
        year    = year_el.get_text(strip=True) if year_el else ""
        cited   = cited_el.get_text(strip=True) if cited_el else ""
        cited   = int(cited) if cited.isdigit() else 0

        pubs.append({
            "title":   title,
            "url":     pub_url,
            "authors": authors,
            "venue":   venue,
            "year":    year or "Preprint",
            "cited":   cited,
        })
    return pubs


def fetch_all_publications(scholar_id: str) -> list[dict]:
    """모든 논문 가져오기 (페이지네이션 지원)."""
    all_pubs = []
    start = 0
    while True:
        print(f"  논문 목록 가져오는 중... (offset={start})")
        soup = fetch_page(scholar_id, start)
        if soup is None:
            break

        pubs = parse_publications(soup, scholar_id)
        if not pubs:
            break

        all_pubs.extend(pubs)
        print(f"  {len(pubs)}편 파싱 완료 (누적: {len(all_pubs)}편)")

        # 다음 페이지 버튼 확인
        next_btn = soup.select_one("#gsc_bpf_next:not([disabled])")
        if not next_btn:
            break

        start += 100
        time.sleep(1)  # 과도한 요청 방지

    return all_pubs


def group_by_year(publications: list[dict]) -> dict:
    groups: dict = {}
    for pub in publications:
        year = pub.get("year", "Preprint")
        groups.setdefault(year, []).append(pub)
    return groups


def format_pub(pub: dict, author_name: str) -> str:
    title   = pub["title"]
    url     = pub["url"]
    authors = bold_author(pub["authors"], author_name)
    venue   = pub["venue"]
    year    = pub["year"]
    cited   = pub["cited"]

    cite_str  = f" · Cited by {cited}" if cited else ""
    title_md  = f"**[{title}]({url})**" if url else f"**{title}**"
    venue_year = ", ".join(filter(None, [f"*{venue}*" if venue else "", year if year != "Preprint" else ""]))

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
            md += format_pub(pub, author_name) + "\n\n---\n\n"

    return md.rstrip() + "\n"


def main():
    if SCHOLAR_ID == "YOUR_SCHOLAR_ID_HERE":
        print("SCHOLAR_ID 환경변수를 설정해 주세요.")
        sys.exit(1)

    print(f"Scholar ID : {SCHOLAR_ID}")
    print(f"Author Name: {AUTHOR_NAME}")
    print(f"출력 경로  : {OUTPUT_PATH}")

    pubs = fetch_all_publications(SCHOLAR_ID)
    if not pubs:
        print("논문을 가져오지 못했습니다. 기존 파일 유지.")
        sys.exit(1)

    print(f"\n총 {len(pubs)}편 수집 완료.")
    pubs_by_year = group_by_year(pubs)
    markdown     = generate_markdown(pubs_by_year, AUTHOR_NAME, SCHOLAR_ID)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"완료! {OUTPUT_PATH} 업데이트됨.")


if __name__ == "__main__":
    main()
