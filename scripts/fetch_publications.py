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
except ImportError as e:
    print(f"scholarly import 실패: {e}")
    print('설치 필요: pip install scholarly "httpx<0.28" "bibtexparser<2"')
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


def _name_variants(name: str) -> set:
    """본인 이름의 표기 변형 집합 (정규화된 소문자). 예: 'Dong Ho Lee' →
    dong ho lee / dh lee / d h lee / d lee / lee dh / lee dong ho"""
    norm = lambda s: re.sub(r"[.\s]+", " ", s).strip().lower()
    parts = name.strip().split()
    variants = {name}
    if len(parts) >= 2:
        last, firsts = parts[-1], parts[:-1]
        inits = "".join(p[0] for p in firsts)
        variants |= {
            f"{inits} {last}", f"{' '.join(inits)} {last}", f"{firsts[0][0]} {last}",
            f"{last} {inits}", f"{last} {' '.join(firsts)}",
        }
    return {norm(v) for v in variants}


def bold_author(authors: str, name: str) -> str:
    """쉼표로 구분된 저자 목록에서 본인 이름과 일치하는 항목만 **Bold** 처리.
    저자 단위로 비교하므로 'Na Young Lee, Dong Ho Lee'처럼 경계를 넘는 오매칭이 없다."""
    if not name or not authors:
        return authors
    variants = _name_variants(name)
    norm = lambda s: re.sub(r"[.\s]+", " ", s).strip().lower()
    out = []
    for a in (x.strip() for x in authors.split(",")):
        if not a:
            continue
        out.append(f"**{a}**" if norm(a) in variants else a)
    return ", ".join(out)


def fetch_author(scholar_id: str):
    """Scholar 프로필 + 기본 논문 목록 가져오기 (재시도 포함)."""
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


def load_existing_entries(path: str) -> dict:
    """기존 _index.md에서 제목 → {author, venue}를 읽어 fill 실패 시 대체 데이터로 사용."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()

    entries: dict = {}
    for block in re.split(r"\n---\n", text):
        m_title = re.search(r"^\*\*(?:\[(.+?)\]\(.*?\)|(.+?))\*\*\s*$", block, flags=re.M)
        if not m_title:
            continue
        title = (m_title.group(1) or m_title.group(2)).strip()
        m_auth  = re.search(r'<span class="pub-authors">(.*?)</span>', block, flags=re.S)
        # 예: "*Small* 21 (7), 2410006, 2025 · Cited by 23"  →  venue="Small", volinfo="21 (7), 2410006"
        m_venue = re.search(
            r"^\*([^*\n]+)\*\s*(.*?)(?:,\s*\d{4})?(?:\s*·\s*Cited by\s*\d+)?\s*$",
            block, flags=re.M,
        )
        entries[title] = {
            "author":  m_auth.group(1).replace("**", "").strip() if m_auth else "",
            "venue":   m_venue.group(1).strip() if m_venue else "",
            "volinfo": m_venue.group(2).strip() if m_venue else "",
        }
    return entries


def enrich_publications(pubs: list, existing: dict) -> list:
    """각 논문의 상세 정보(저자, 저널 등)를 개별 fill로 보완.
    fill이 실패하면 재시도하고, 끝내 실패하면 기존 파일의 저자/저널 정보를 재사용한다."""
    enriched = []
    for i, pub in enumerate(pubs):
        title = pub.get("bib", {}).get("title", "?")
        print(f"  [{i+1}/{len(pubs)}] 상세 정보 가져오는 중: {title[:60]}...")
        full = None
        for attempt in range(1, 4):
            try:
                full = scholarly.fill(pub)
                break
            except Exception as e:
                print(f"    [{attempt}/3] 상세 정보 실패: {e}")
                if attempt < 3:
                    time.sleep(10 * attempt)
        if full is None:
            prev = existing.get(title.strip())
            if prev and (prev["author"] or prev["venue"]):
                print("    기존 파일의 저자/저널 정보 재사용")
                pub.setdefault("bib", {})
                if prev["author"]:
                    pub["bib"]["author"] = prev["author"]
                if prev["venue"]:
                    pub["bib"]["venue"] = prev["venue"]
                if prev["volinfo"]:
                    pub["bib"]["_volinfo"] = prev["volinfo"]
            else:
                print("    기존 정보 없음 → 기본 데이터 사용")
            full = pub
        enriched.append(full)
        time.sleep(2)   # 연속 요청 사이 짧은 대기
    return enriched


def group_by_year(publications: list) -> dict:
    groups: dict = {}
    for pub in publications:
        year = str(pub.get("bib", {}).get("pub_year", "")).strip() or "Preprint"
        groups.setdefault(year, []).append(pub)
    return groups


def format_authors(authors: str, name: str) -> str:
    """scholarly의 'A and B and C' 형식을 'A, B, C'로 바꾸고 본인 이름 Bold 처리."""
    authors = ", ".join(a.strip() for a in re.split(r"\s+and\s+", authors) if a.strip())
    return bold_author(authors, name)


def format_volinfo(bib: dict) -> str:
    """Google Scholar 표기와 같은 '21 (7), 2410006' 형식의 권/호/페이지 문자열."""
    if bib.get("_volinfo"):            # 기존 파일에서 재사용한 경우
        return bib["_volinfo"].strip()
    vol   = str(bib.get("volume", "") or "").strip()
    num   = str(bib.get("number", "") or "").strip()
    pages = str(bib.get("pages", "") or "").strip()
    s = vol
    if num:
        s = f"{s} ({num})".strip()
    if pages:
        s = f"{s}, {pages}" if s else pages
    return s


def format_pub(pub: dict, author_name: str, scholar_id: str) -> str:
    bib    = pub.get("bib", {})
    title  = bib.get("title", "Unknown Title").strip()
    authors = format_authors(bib.get("author", ""), author_name)
    venue  = (bib.get("venue") or bib.get("journal") or bib.get("booktitle") or "").strip()
    volinfo = format_volinfo(bib)
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
    venue_md   = " ".join(filter(None, [f"*{venue}*" if venue else "", volinfo]))
    venue_year = ", ".join(filter(None, [venue_md, year]))

    parts = [title_md]
    if authors:
        # span으로 감싸서 CSS로 폰트 크기 조절 가능하게 함 (Hugo unsafe HTML 허용)
        parts.append(f'<span class="pub-authors">{authors}</span>')
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

    pubs = author.get("publications", [])
    existing = load_existing_entries(OUTPUT_PATH)
    print(f"\n각 논문 상세 정보 수집 중 ({len(pubs)}편, 기존 항목 {len(existing)}개 로드)...")
    pubs = enrich_publications(pubs, existing)

    pubs_by_year = group_by_year(pubs)
    markdown     = generate_markdown(pubs_by_year, AUTHOR_NAME, SCHOLAR_ID)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n완료! {OUTPUT_PATH} 업데이트됨.")


if __name__ == "__main__":
    main()
