#!/usr/bin/env python3
"""
Analyze TMDB→MovieLinkBD TV mapping step-by-step.

Usage:
  python analyze_tv_mapping.py <tmdb_tv_id> [--season N] [--episode M]

This tool:
  1) Fetches TMDB TV info (title/original_name)
  2) Builds multiple query variants (full/base)
  3) Scrapes MLBD search for each query and scores candidates
  4) Picks the best `/series/` URL and explains why
  5) Optionally inspects the selected series page structure
"""

import os
import sys
import re
import json
import argparse
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup


# Load .env if available
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
MLBD_BASE = 'https://playk8.movielinkbd.sbs'


def ensure_tmdb_key() -> None:
    if not TMDB_API_KEY:
        print('ERROR: TMDB_API_KEY is not configured in environment/.env', file=sys.stderr)
        sys.exit(2)


def tmdb_tv_details(tv_id: int) -> Dict[str, Any]:
    ensure_tmdb_key()
    url = f'https://api.themoviedb.org/3/tv/{tv_id}'
    resp = requests.get(url, params={'api_key': TMDB_API_KEY, 'language': 'en-US'}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def normalize_title(s: str) -> str:
    s = (s or '').lower().strip()
    s = re.sub(r"\(\d{4}\)", "", s)
    s = re.sub(r"\b(season\s*\d+|s\d+|ep\s*\d+|e\d+)\b", "", s)
    noise = [
        'bangla dubbed', 'bangla', 'বাংলা', 'bd', 'hindi dubbed', 'hindi', 'हिंदी',
        'dual audio', 'english dubbed', 'english', 'web-dl', 'webdl', 'webrip',
        'hdrip', 'brrip', 'dvdrip', 'rip', '480p', '720p', '1080p', '4k', 'uhd', 'hd', 'sd'
    ]
    for w in noise:
        s = re.sub(rf"\b{re.escape(w)}\b", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def base_title(s: str) -> str:
    s = s or ''
    s = re.split(r"[:\-\(]", s, maxsplit=1)[0]
    return s.strip()


def score_similarity(a: str, b: str) -> float:
    # Cheap Jaccard-like token overlap as a robust scoring without difflib dependency
    at = [t for t in a.split() if t]
    bt = [t for t in b.split() if t]
    if not at or not bt:
        return 0.0
    sa, sb = set(at), set(bt)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def fetch_search_html(query: str) -> str | None:
    url = f"{MLBD_BASE}/search?q={requests.utils.quote(query)}"
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    })
    r = session.get(url, timeout=30)
    if r.status_code != 200:
        print(f"WARN: search response {r.status_code} for query='{query}'")
        return None
    return r.text


def parse_candidates(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    out: List[Dict[str, Any]] = []
    for card in soup.find_all('div', class_='movie-card'):
        a = card.find('a', class_='title')
        if not a:
            continue
        href = a.get('href', '')
        if not href:
            continue
        title = a.get_text(strip=True)
        type_span = card.find('span', class_='type')
        movie_type = type_span.get_text(strip=True) if type_span else ''
        language_span = card.find('span', class_='language')
        language = language_span.get_text(strip=True) if language_span else ''
        rating_span = card.find('span', class_='rating-badge')
        rating = rating_span.get_text(strip=True) if rating_span else ''

        full_href = href if href.startswith('http') else f"{MLBD_BASE}{href}"

        out.append({
            'title': title,
            'href': full_href,
            'raw_href': href,
            'type': movie_type,
            'language': language,
            'rating': rating,
            'is_series': ('/series/' in href) or (movie_type.lower() == 'series'),
        })
    return out


def inspect_series_structure(series_url: str, season: int | None = None) -> Dict[str, Any]:
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    r = session.get(series_url, timeout=30)
    info: Dict[str, Any] = {'status': r.status_code, 'url': series_url, 'has_getwatch': 0, 'seasons_found': []}
    if r.status_code != 200:
        return info
    soup = BeautifulSoup(r.text, 'html.parser')
    # Count getWatch anchors/buttons
    count = 0
    for a in soup.find_all(['a', 'button']):
        href = a.get('href', '')
        onclick = a.get('onclick', '')
        if '/getWatch/' in href or '/getWatch/' in onclick:
            count += 1
    info['has_getwatch'] = count
    # Detect season labels
    for s in range(1, 21):
        lab = f"Season {s}"
        node = soup.find(lambda tag: tag.name in ['div','section','li','ul'] and lab.lower() in tag.get_text(' ', strip=True).lower())
        if node:
            info['seasons_found'].append(s)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description='Analyze TMDB→MLBD TV mapping')
    parser.add_argument('tmdb_id', type=int, help='TMDB TV ID')
    parser.add_argument('--season', type=int, default=None)
    parser.add_argument('--episode', type=int, default=None)
    args = parser.parse_args()

    tv = tmdb_tv_details(args.tmdb_id)
    name = (tv.get('name') or '').strip()
    original_name = (tv.get('original_name') or '').strip()
    title_base = base_title(name)
    tmdb_norm_full = normalize_title(name)
    tmdb_norm_base = normalize_title(title_base)

    print(json.dumps({
        'tmdb': {
            'id': args.tmdb_id,
            'name': name,
            'original_name': original_name,
            'title_base': title_base,
            'norm_full': tmdb_norm_full,
            'norm_base': tmdb_norm_base,
        }
    }, indent=2))

    queries: List[str] = []
    for q in [name, title_base]:
        if q and q.lower() not in [qq.lower() for qq in queries]:
            queries.append(q)

    best_overall: Dict[str, Any] | None = None

    for q in queries:
        print(f"\n=== Query: {q} ===")
        html = fetch_search_html(q)
        if not html:
            print('No HTML returned')
            continue
        cands = parse_candidates(html)
        scored: List[Dict[str, Any]] = []
        for c in cands:
            nml = normalize_title(c['title'])
            score_full = score_similarity(nml, tmdb_norm_full)
            score_base = score_similarity(nml, tmdb_norm_base)
            score = max(score_full, score_base)
            title_lower = c['title'].lower()
            has_episode_batch = ('episode' in title_lower and re.search(r"\b\d+\s*[-–]\s*\d+\b", title_lower) is not None)
            has_season_block = ('season' in title_lower or re.search(r"\bs\s*\d+\b", title_lower) is not None)
            if c['is_series']:
                score += 0.05
            if has_season_block:
                score += 0.03
            if has_episode_batch:
                score -= 0.07
            row = dict(c)
            row.update({'norm_title': nml, 'score': round(score, 4), 'score_full': round(score_full,4), 'score_base': round(score_base,4), 'has_episode_batch': has_episode_batch, 'has_season_block': has_season_block})
            scored.append(row)

        scored.sort(key=lambda x: (not x['is_series'], -x['score']))
        for i, s in enumerate(scored[:15], start=1):
            print(f"{i:2d}. [{s['score']:.3f}] {'SERIES' if s['is_series'] else 'movie '} | {s['title']} | lang={s['language'] or '-'} | href={s['href']}")

        if scored:
            pick = scored[0]
            if best_overall is None or ((pick['is_series'] and not best_overall.get('is_series')) or (pick['score'] > best_overall.get('score', 0))):
                best_overall = pick

    if not best_overall:
        print('\nNo candidates found across all queries.')
        sys.exit(1)

    print('\n=== PICK ===')
    print(json.dumps(best_overall, indent=2))

    if best_overall['is_series']:
        info = inspect_series_structure(best_overall['href'], args.season)
        print('\n=== SERIES STRUCTURE ===')
        print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()


