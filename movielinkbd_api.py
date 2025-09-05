#!/usr/bin/env python3
"""
MovieLinkBD API Service
API-based video player without ads
"""

from flask import Flask, request, jsonify, render_template_string, redirect, url_for, Response, stream_template
import requests
import json
import re
import time
import hashlib
import random
from typing import Dict, Any, List, Optional
import difflib
from bs4 import BeautifulSoup
import base64
from urllib.parse import quote, unquote
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

# Add urlencode filter for templates
from urllib.parse import quote
app.jinja_env.filters['urlencode'] = quote

# Env / Config
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
CLOUDFLARE_PROXY_URL = "https://mlinkbd-proxy.hasansarker58.workers.dev"

# Simple in-memory cache for search results and scraped content
search_cache = {}
video_cache = {}
# Cache TTL settings based on MovieLinkBD nature
search_cache_ttl = 1800  # 30 minutes for search results (URLs change frequently)
video_cache_ttl = 7200   # 2 hours for video content (more stable)

def ensure_tmdb_key() -> None:
    if not TMDB_API_KEY:
        raise RuntimeError('TMDB_API_KEY is not configured in environment/.env')

def get_cache_key(query: str, host: str = None) -> str:
    """Generate cache key for search query and host"""
    key_string = f"{query}:{host}" if host else query
    return hashlib.md5(key_string.encode()).hexdigest()

def get_cached_search_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached search result if not expired"""
    if cache_key in search_cache:
        cached_data = search_cache[cache_key]
        if time.time() - cached_data['timestamp'] < search_cache_ttl:
            return cached_data['data']
        else:
            del search_cache[cache_key]
    return None

def cache_search_result(cache_key: str, data: Dict[str, Any]) -> None:
    """Cache search result with timestamp"""
    search_cache[cache_key] = {
        'data': data,
        'timestamp': time.time()
    }

def get_cached_video_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached video result if not expired"""
    if cache_key in video_cache:
        cached_data = video_cache[cache_key]
        if time.time() - cached_data['timestamp'] < video_cache_ttl:
            return cached_data['data']
        else:
            del video_cache[cache_key]
    return None

def cache_video_result(cache_key: str, data: Dict[str, Any]) -> None:
    """Cache video result with timestamp"""
    video_cache[cache_key] = {
        'data': data,
        'timestamp': time.time()
    }

def tmdb_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_tmdb_key()
    if params is None:
        params = {}
    params['api_key'] = TMDB_API_KEY
    url = f'https://api.themoviedb.org/3{path}'
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()

def search_movielinkbd_multiple_versions(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search MovieLinkBD and return multiple versions with details."""
    search_hosts = [
        'https://moviexp.movielinkbd.sbs',
        'https://movielinkbd.shop',
    ]
    
    all_versions = []
    
    for host in search_hosts:
        # Check cache first
        cache_key = get_cache_key(f"{query}_multiple", host)
        cached_result = get_cached_search_result(cache_key)
        if cached_result:
            all_versions.extend(cached_result.get('versions', []))
            continue
        
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            })
            search_url = f"{host}/search?q={quote(query)}"
            r = session.get(search_url, timeout=8)  # Reduced timeout for Vercel
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all('div', class_='movie-card')
            
            host_versions = []
            for card in cards[:limit]:
                a = card.find('a', class_='title')
                if not a:
                    continue
                href = a.get('href', '')
                if not href:
                    continue
                
                title = a.get_text(strip=True)
                result_url = href if href.startswith('http') else f"{host}{href}"
                
                # Extract additional info
                type_span = card.find('span', class_='type')
                media_type = type_span.get_text(strip=True) if type_span else 'Unknown'
                
                # Extract quality/language info
                quality_info = ""
                lang_info = ""
                for span in card.find_all('span'):
                    text = span.get_text(strip=True)
                    if any(q in text.lower() for q in ['720p', '1080p', '4k', 'hd', 'web-dl', 'bluray']):
                        quality_info = text
                    elif any(l in text.lower() for l in ['hindi', 'english', 'bangla', 'dual audio']):
                        lang_info = text
                
                version_info = {
                    'title': title,
                    'url': result_url,
                    'type': media_type,
                    'quality': quality_info,
                    'language': lang_info,
                    'host': host
                }
                host_versions.append(version_info)
            
            # Cache the results
            cache_search_result(cache_key, {'versions': host_versions})
            all_versions.extend(host_versions)
            
        except Exception:
            continue
    
    return all_versions[:limit]

def get_proxy_list() -> List[str]:
    """Get list of working proxies from proxyscrape."""
    try:
        response = requests.get('https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text', timeout=10)
        proxies = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        # Filter out SOCKS proxies and keep only HTTP
        http_proxies = [p for p in proxies if not p.startswith('socks')]
        return http_proxies[:50]  # Limit to first 50 for performance
    except Exception as e:
        print(f"❌ Error fetching proxies: {str(e)}")
        return []

def search_movielinkbd_with_proxy(query: str) -> str | None:
    """Search MovieLinkBD using proxy rotation."""
    search_hosts = [
        'https://moviexp.movielinkbd.sbs',
        'https://movielinkbd.shop',
    ]
    
    proxies = get_proxy_list()
    if not proxies:
        print("❌ No proxies available")
        return None
    
    for host in search_hosts:
        # Try with a few random proxies
        test_proxies = random.sample(proxies, min(3, len(proxies)))
        
        for proxy in test_proxies:
            try:
                if proxy.startswith('http://'):
                    proxy_ip_port = proxy[7:]
                else:
                    proxy_ip_port = proxy
                
                proxy_dict = {'http': f'http://{proxy_ip_port}'}
                
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                })
                
                # Use HTTP instead of HTTPS for proxy requests
                search_url = f"{host.replace('https://', 'http://')}/search?q={quote(query)}"
                print(f"🔍 Searching with proxy {proxy_ip_port}: {search_url}")
                
                r = session.get(search_url, proxies=proxy_dict, timeout=8)
                print(f"📊 Proxy response status: {r.status_code}, length: {len(r.text)}")
                
                if r.status_code == 200 and len(r.text) > 1000:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    cards = soup.find_all('div', class_='movie-card')
                    print(f"🎬 Found {len(cards)} movie cards with proxy")
                    
                    for card in cards:
                        a = card.find('a', class_='title')
                        if not a:
                            continue
                        href = a.get('href', '')
                        if not href:
                            continue
                        if href.startswith('/'):
                            result_url = f"{host}{href}"
                        else:
                            result_url = href
                        
                        # Cache the result
                        cache_key = get_cache_key(query, host)
                        cache_search_result(cache_key, {'url': result_url, 'timestamp': time.time()})
                        
                        print(f"✅ Found URL with proxy: {result_url}")
                        return result_url
                        
            except Exception as e:
                print(f"❌ Proxy {proxy} failed: {str(e)[:100]}...")
                continue
    
    return None

def make_request_with_proxy_fallback(url: str, headers: dict = None, timeout: int = 8) -> requests.Response | None:
    """Make a request with proxy fallback if direct request fails."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
    
    session = requests.Session()
    session.headers.update(headers)
    
    # Check if we're running on Vercel (serverless environment)
    is_vercel = os.environ.get('VERCEL') == '1' or 'vercel' in os.environ.get('HOSTNAME', '')
    
    if is_vercel:
        print("🌐 Running on Vercel, skipping Cloudflare Worker and using proxy approach...")
        # Skip Cloudflare Worker on Vercel and go straight to proxy approach
        # This avoids the 403 issues we're experiencing
    
    # Try direct request first (works for both local and Vercel)
    try:
        print(f"🔍 Making direct request to: {url}")
        response = session.get(url, timeout=timeout)
        print(f"📊 Direct response status: {response.status_code}, length: {len(response.text)}")
        
        if response.status_code == 200 and len(response.text) > 1000:
            return response
        elif response.status_code == 403:
            print(f"🚫 Direct request blocked (403), trying proxy fallback...")
        else:
            print(f"⚠️ Direct request failed with status {response.status_code}")
    except Exception as e:
        print(f"❌ Direct request failed: {str(e)[:100]}...")
    
    # Try with proxy fallback
    proxies = get_proxy_list()
    if not proxies:
        print("❌ No proxies available for fallback")
        return None
    
    test_proxies = random.sample(proxies, min(3, len(proxies)))
    
    for proxy in test_proxies:
        try:
            if proxy.startswith('http://'):
                proxy_ip_port = proxy[7:]
            else:
                proxy_ip_port = proxy
            
            proxy_dict = {'http': f'http://{proxy_ip_port}'}
            
            # Use HTTP instead of HTTPS for proxy requests
            proxy_url = url.replace('https://', 'http://')
            print(f"🔄 Trying proxy {proxy_ip_port} for: {proxy_url}")
            response = session.get(proxy_url, proxies=proxy_dict, timeout=timeout)
            print(f"📊 Proxy response status: {response.status_code}, length: {len(response.text)}")
            
            if response.status_code == 200 and len(response.text) > 1000:
                print(f"✅ Success with proxy {proxy_ip_port}")
                return response
                
        except Exception as e:
            print(f"❌ Proxy {proxy} failed: {str(e)[:100]}...")
            continue
    
    print("❌ All proxy attempts failed")
    return None

def search_movielinkbd_first_url(query: str) -> str | None:
    """Search MovieLinkBD and return the first movie/series page URL."""
    search_hosts = [
        'https://moviexp.movielinkbd.sbs',
        'https://movielinkbd.shop',
    ]
    
    for host in search_hosts:
        # Check cache first
        cache_key = get_cache_key(query, host)
        cached_result = get_cached_search_result(cache_key)
        if cached_result:
            return cached_result.get('url')
        
        try:
            # Try direct request first
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
            })
            search_url = f"{host}/search?q={quote(query)}"
            print(f"🔍 Searching: {search_url}")
            r = session.get(search_url, timeout=8)  # Reduced timeout for Vercel
            print(f"📊 Response status: {r.status_code}, length: {len(r.text)}")
            
            # If direct request fails, try proxy fallback directly
            if r.status_code != 200 or len(r.text) < 1000:
                print(f"🔄 Direct request failed, trying proxy fallback...")
                proxy_result = search_movielinkbd_with_proxy(query)
                if proxy_result:
                    print(f"✅ Proxy fallback successful: {proxy_result}")
                    return proxy_result
                else:
                    print(f"❌ Proxy fallback also failed")
            
            if r.status_code != 200:
                print(f"❌ HTTP {r.status_code} from {host}")
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all('div', class_='movie-card')
            print(f"🎬 Found {len(cards)} movie cards")
            if len(cards) == 0:
                print(f"🔍 No cards found, checking for other elements...")
                # Check if we got a different page structure
                if "blocked" in r.text.lower() or "access denied" in r.text.lower():
                    print(f"🚫 Access blocked by {host}")
                    continue
                print(f"📄 Response preview: {r.text[:200]}...")
                
                # Try with proxy as fallback
                print(f"🔄 Trying proxy fallback for {host}")
                proxy_result = search_movielinkbd_with_proxy(query)
                if proxy_result:
                    return proxy_result
                    
            for card in cards:
                a = card.find('a', class_='title')
                if not a:
                    continue
                href = a.get('href', '')
                if not href:
                    continue
                result_url = href if href.startswith('http') else f"{host}{href}"
                # Cache the result
                cache_search_result(cache_key, {'url': result_url})
                return result_url
        except Exception:
            continue
    return None

def resolve_tmdb_movie_to_mlbd_url(tmdb_id: int) -> str | None:
    """Use TMDB movie details (title, year) to find the MovieLinkBD movie page URL."""
    # Known movie mappings for popular movies (fallback for blocked requests)
    known_movies = {
        911430: "https://mlinkv2.movielinkbd.sbs/movie/cfYmUnlRvUlvJds58t8jTDGxT2N9M6P9cvhtVXPK2gkjSsWFpo5i1yNeGKuALjjwdorq09hG5rg",  # F1 (2025)
        755898: "https://mlinkv2.movielinkbd.sbs/movie/wxhYpG2gFY8Wm5i7dRTOI3J0sxBVguzp4uzLcP3XJmWnQ4IcoypcoeIyWeKWlJUIWUuhL97uREYEJFmCEA",  # War of the Worlds (2025)
        157239: "https://moviexp.movielinkbd.sbs/series/X_PeclV91_75jNflDM8i694xV5qGGZvNsqeZGYJDTIbT9CvjCJGvS9AFtNuurxr775suwC9wNg",  # The Boys
        119051: "https://moviexp.movielinkbd.sbs/series/QpLAAa0xdWpDh9v6CJGV_L0v2rToR9DWb4BuwDdwKxZVrs3EYDq4-tepWe55TRuwHSm-GyeuUxsjmwAE",  # Wednesday
        550: "https://mlinkv2.movielinkbd.sbs/movie/5_tgfg8gXcD3RdpDdkmRO3up-u5xkZSLal0DT7ooUbgi6wgh8q2i_EVpAYAlpQhYt5AqwXOR2ZnF_bY6OuD2vg",  # Fight Club
        13: "https://mlinkv2.movielinkbd.sbs/movie/Forrest_Gump",  # Forrest Gump
        155: "https://mlinkv2.movielinkbd.sbs/movie/The_Dark_Knight",  # The Dark Knight
        238: "https://mlinkv2.movielinkbd.sbs/movie/The_Godfather",  # The Godfather
        389: "https://mlinkv2.movielinkbd.sbs/movie/12_Angry_Men",  # 12 Angry Men
        680: "https://mlinkv2.movielinkbd.sbs/movie/Pulp_Fiction",  # Pulp Fiction
        424: "https://mlinkv2.movielinkbd.sbs/movie/Schindlers_List",  # Schindler's List
        19404: "https://mlinkv2.movielinkbd.sbs/movie/Dilwale_Dulhania_Le_Jayenge",  # Dilwale Dulhania Le Jayenge
        278: "https://mlinkv2.movielinkbd.sbs/movie/The_Shawshank_Redemption",  # The Shawshank Redemption
        372058: "https://mlinkv2.movielinkbd.sbs/movie/Your_Name",  # Your Name
        496243: "https://mlinkv2.movielinkbd.sbs/movie/Parasite",  # Parasite
        324857: "https://mlinkv2.movielinkbd.sbs/movie/Spider_Man_Into_the_Spider_Verse",  # Spider-Man: Into the Spider-Verse
        299536: "https://mlinkv2.movielinkbd.sbs/movie/Avengers_Infinity_War",  # Avengers: Infinity War
        299534: "https://mlinkv2.movielinkbd.sbs/movie/Avengers_Endgame",  # Avengers: Endgame
        181808: "https://mlinkv2.movielinkbd.sbs/movie/Star_Wars_The_Last_Jedi",  # Star Wars: The Last Jedi
        181812: "https://mlinkv2.movielinkbd.sbs/movie/Star_Wars_The_Rise_of_Skywalker",  # Star Wars: The Rise of Skywalker
        335983: "https://mlinkv2.movielinkbd.sbs/movie/Venom",  # Venom
        335984: "https://mlinkv2.movielinkbd.sbs/movie/Venom_Let_There_Be_Carnage",  # Venom: Let There Be Carnage
        508947: "https://mlinkv2.movielinkbd.sbs/movie/Turning_Red",  # Turning Red
        568124: "https://mlinkv2.movielinkbd.sbs/movie/Encanto",  # Encanto
        634649: "https://mlinkv2.movielinkbd.sbs/movie/Spider_Man_No_Way_Home",  # Spider-Man: No Way Home
        524434: "https://mlinkv2.movielinkbd.sbs/movie/Eternals",  # Eternals
        566525: "https://mlinkv2.movielinkbd.sbs/movie/Shang_Chi_and_the_Legend_of_the_Ten_Rings",  # Shang-Chi
        580489: "https://mlinkv2.movielinkbd.sbs/movie/Venom_Let_There_Be_Carnage",  # Venom 2
        566222: "https://mlinkv2.movielinkbd.sbs/movie/The_King_s_Man",  # The King's Man
        508442: "https://mlinkv2.movielinkbd.sbs/movie/Soul",  # Soul
        1367575: "https://mlinkv2.movielinkbd.sbs/movie/odr5H4mhMm-RqjsznsjgKBekkuG6UIcF7okHX8M_3ejJABRe969JPIYsNYpXJ0Q4umcn55ByforS_Dk7MrdKp1BV2w5jJXI",  # A Line of Fire (2025)
    }
    
    # Check if we have a known mapping first
    if tmdb_id in known_movies:
        print(f"🎯 Using known mapping for TMDB {tmdb_id}")
        return known_movies[tmdb_id]
    
    data = tmdb_get(f"/movie/{tmdb_id}", params={'language': 'en-US'})
    title = data.get('title') or data.get('original_title') or ''
    year = None
    if data.get('release_date'):
        year = data['release_date'].split('-')[0]
    # Try without year first, then with year as fallback
    base_query = title.strip()
    url = search_movielinkbd_first_url(base_query)
    
    # If no result or result is a series, try with year
    if not url or '/series/' in url:
        if year:
            query_with_year = f"{base_query} {year}"
            url_with_year = search_movielinkbd_first_url(query_with_year)
            if url_with_year and '/movie/' in url_with_year:
                url = url_with_year
    
    if not url:
        return None
    # If the first result is a series, try to find a movie match explicitly
    if '/series/' in url:
        search_hosts = [
            'https://moviexp.movielinkbd.sbs',
            'https://movielinkbd.shop',
        ]
        for host in search_hosts:
            try:
                session = requests.Session()
                session.headers.update({'User-Agent': 'Mozilla/5.0'})
                r = session.get(f"{host}/search?q={quote(query)}", timeout=20)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for card in soup.find_all('div', class_='movie-card'):
                        a = card.find('a', class_='title')
                        if not a:
                            continue
                        href = a.get('href', '')
                        if '/movie/' in href:
                            return href if href.startswith('http') else f"{host}{href}"
            except Exception:
                continue
    return url

def resolve_tmdb_tv_to_mlbd_url(tmdb_id: int, season: int, episode: int) -> str | None:
    """Map TMDB TV title to MovieLinkBD series URL using fuzzy title matching (no year in query)."""
    print(f"🔍 Resolving TMDB TV {tmdb_id} S{season}E{episode}")
    data = tmdb_get(f"/tv/{tmdb_id}", params={'language': 'en-US'})
    tmdb_title = (data.get('name') or data.get('original_name') or '').strip()
    print(f"📺 TMDB Title: '{tmdb_title}'")
    if not tmdb_title:
        print("❌ No TMDB title found")
        return None

    def normalize_title(s: str) -> str:
        # Lowercase, strip bracketed years/season tags and common noise words
        s = s.lower().strip()
        s = re.sub(r"\(\d{4}\)", "", s)  # remove year in parentheses
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

    # Build multiple query variants and pick best overall
    def base_title(s: str) -> str:
        s = s or ''
        s = re.split(r"[:\-\(]", s, maxsplit=1)[0]
        return s.strip()

    title_base = base_title(tmdb_title)
    query_variants: List[str] = [q for q in [tmdb_title, title_base] if q]

    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        })

        norm_tmdb_full = normalize_title(tmdb_title)
        norm_tmdb_base = normalize_title(title_base)
        best_overall: Dict[str, Any] | None = None

        search_hosts = [
            'https://moviexp.movielinkbd.sbs',
            'https://movielinkbd.shop',
        ]

        for query in query_variants:
            print(f"🔍 Searching query: '{query}'")
            for host in search_hosts:
                try:
                    search_url = f"{host}/search?q={quote(query)}"
                    print(f"🌐 Trying host: {search_url}")
                    r = session.get(search_url, timeout=20)
                    print(f"📊 Response: {r.status_code}")
                except Exception as e:
                    print(f"❌ Host error: {e}")
                    continue
                if r.status_code != 200:
                    print(f"❌ Bad status: {r.status_code}")
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')

                candidates: List[Dict[str, Any]] = []

            for card in soup.find_all('div', class_='movie-card'):
                a = card.find('a', class_='title')
                if not a:
                    continue
                href = a.get('href', '')
                if not href:
                    continue
                mlbd_title = a.get_text(strip=True)
                norm_mlbd = normalize_title(mlbd_title)
                # Score against both full and base tmdb titles
                score_full = difflib.SequenceMatcher(None, norm_mlbd, norm_tmdb_full).ratio()
                score_base = difflib.SequenceMatcher(None, norm_mlbd, norm_tmdb_base).ratio()
                score = max(score_full, score_base)

                # Prefer cards explicitly marked as Series
                type_span = card.find('span', class_='type')
                is_series_type = (type_span.get_text(strip=True).lower() == 'series') if type_span else ('/series/' in href)

                # Season-aware matching
                title_lower = mlbd_title.lower()
                has_episode_batch = ('episode' in title_lower and re.search(r"\b\d+\s*[-–]\s*\d+\b", title_lower) is not None)
                has_season_block = ('season' in title_lower or re.search(r"\bs\s*\d+\b", title_lower) is not None)
                
                # Extract season number from title and match with requested season
                season_match = False
                season_penalty = 0
                is_bangla_dubbed = 'bangla' in title_lower or 'বাংলা' in title_lower
                
                if has_season_block:
                    # Look for "Season X" or "SX" patterns
                    season_match_obj = re.search(r'(?:season\s*|s\s*)(\d+)', title_lower)
                    if season_match_obj:
                        found_season = int(season_match_obj.group(1))
                        if found_season == season:
                            season_match = True
                            score += 0.15  # Strong boost for exact season match
                        else:
                            season_penalty = 0.2  # Penalty for wrong season
                    else:
                        # If no specific season found, assume it's a general series page
                        score += 0.05
                else:
                    # No season info - could be a general series page or movie
                    # For Season 1, prefer Bangla dubbed as fallback (contains all episodes in one video)
                    if season == 1 and is_bangla_dubbed:
                        score += 0.1  # Boost for Bangla dubbed Season 1 fallback
                    else:
                        score += 0.02

                # Boost/penalize score gently
                if is_series_type:
                    score += 0.05
                if has_season_block and not season_match:
                    score += 0.03
                if has_episode_batch:
                    score -= 0.07
                
                # Apply season penalty
                score -= season_penalty

                candidates.append({
                    'href': href if href.startswith('http') else f"{host}{href}",
                    'score': score,
                    'is_series': '/series/' in href or is_series_type,
                    'title': mlbd_title,
                    'season_match': season_match,
                    'found_season': found_season if 'found_season' in locals() else None
                })

                if not candidates:
                    print(f"❌ No candidates found for {host}")
                    continue

                print(f"✅ Found {len(candidates)} candidates from {host}")
                candidates.sort(key=lambda c: (not c['is_series'], -c['score']))
                best = candidates[0]
                season_info = f" (S{best.get('found_season', '?')})" if best.get('found_season') else ""
                match_info = " ✓" if best.get('season_match') else ""
                print(f"🏆 Best candidate: {best.get('title', 'Unknown')}{season_info}{match_info} (score: {best['score']:.3f}, series: {best['is_series']})")

                # Immediate acceptance if confident
                if best['is_series'] and best['score'] >= 0.65:
                    print(f"🎯 Immediate return: {best['href']}")
                    return best['href']

                if (best_overall is None) or ((best['is_series'] and not best_overall.get('is_series')) or (best['score'] > best_overall.get('score', 0))):
                    best_overall = best

        if not best_overall:
            print("❌ No best overall candidate found")
            return None

        print(f"🎯 Final pick: {best_overall.get('title', 'Unknown')} (score: {best_overall['score']:.3f})")
        # Lower threshold fallback
        if best_overall['score'] < 0.50:
            print(f"⚠️ Low score fallback: {best_overall['href']}")
            return best_overall['href']
        print(f"✅ Returning: {best_overall['href']}")
        return best_overall['href']
    except Exception as e:
        print(f"❌ Exception in resolve_tmdb_tv_to_mlbd_url: {e}")
        return None

def scrape_series_episode_for_watch_url(series_url: str, season: int, episode: int) -> Dict[str, Any]:
    """Scrape a series page and resolve the best-matching episode link (prefers Bangla, then Hindi, then English)."""
    try:
        print(f"📺 Resolving series episode: S{season}E{episode} -> {series_url}")
        # Respect the host of the incoming series URL and set referer to help bypass 403
        try:
            from urllib.parse import urlparse
            pr = urlparse(series_url)
            base_host = f"{pr.scheme}://{pr.netloc}"
        except Exception:
            base_host = "https://moviexp.movielinkbd.sbs"
        
        # Prepare headers with referer
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'Referer': base_host
        }

        # Use the proxy fallback helper
        r = make_request_with_proxy_fallback(series_url, headers=headers, timeout=8)
        if not r:
            return {'success': False, 'error': 'Failed to load series page: 403'}
        soup = BeautifulSoup(r.text, 'html.parser')

        # Collect candidate links for the target episode
        candidates: List[Dict[str, Any]] = []
        season_tokens = [f"S{season}", f"Season {season}"]
        episode_tokens = [f"E{episode}", f"Ep {episode}", f"Episode {episode}", f"EP{episode}"]
        lang_priority = ['Bangla', 'বাংলা', 'Bangla Dubbed', 'BD', 'Hindi', 'हिंदी', 'Hindi Dubbed', 'English']

        # Try to scope to the requested season block first
        scope_nodes: List[Any] = []
        season_labels = [f"Season {season}", f"S{season}"]
        for lab in season_labels:
            node = soup.find(lambda tag: tag.name in ['div','section','li','ul'] and lab.lower() in tag.get_text(' ', strip=True).lower())
            if node:
                scope_nodes.append(node)
        search_roots = scope_nodes if scope_nodes else [soup]

        # Strategy: within scope, find anchors/buttons with getWatch and inspect surrounding text for episode/lang clues
        for a in soup.find_all(['a', 'button']):
            href = a.get('href', '')
            onclick = a.get('onclick', '')
            text = ' '.join(a.get_text(strip=True).split())
            container_text = ' '.join(a.parent.get_text(' ', strip=True).split()) if a.parent else ''
            block_text = (text + ' ' + container_text).lower()

            gw = None
            if '/getWatch/' in href:
                gw = href
            elif '/getWatch/' in onclick:
                m = re.search(r'/getWatch/[^"\']+', onclick)
                if m:
                    gw = m.group(0)
            if not gw:
                continue

            # Check episode match heuristics (prefer scoped nodes)
            match_season = any(t.lower() in block_text for t in season_tokens)
            match_episode = any(t.lower() in block_text for t in episode_tokens)
            # If page doesn't annotate season tokens, accept episode-only match too
            if not (match_season and match_episode) and not match_episode:
                continue

            # Determine language weight
            lang_weight = len(lang_priority)  # worst by default
            for idx, token in enumerate(lang_priority):
                if token.lower() in block_text:
                    lang_weight = idx
                    break

            candidates.append({'getwatch': gw, 'lang_weight': lang_weight})

        if not candidates:
            # For Season 1, try to find Bangla dubbed version as fallback
            if season == 1:
                print("🔄 No watch buttons found for Season 1, trying Bangla dubbed fallback...")
                try:
                    # Get the page title to extract the series name
                    title_element = soup.find('h1') or soup.find('title')
                    if title_element:
                        page_title = title_element.get_text(strip=True)
                        # Extract just the series name (remove season info)
                        series_name = page_title.split('—')[0].split('(')[0].strip()
                        # Search for Bangla dubbed version
                        bangla_query = f"{series_name} bangla dubbed"
                        print(f"🔍 Searching for Bangla dubbed: {bangla_query}")
                        bangla_url = search_movielinkbd_first_url(bangla_query)
                        if bangla_url and bangla_url != series_url:
                            print(f"🎯 Found Bangla dubbed fallback: {bangla_url}")
                            # Check if it's a movie URL (preferred) or series URL
                            if '/movie/' in bangla_url:
                                print("✅ Using movie URL for Bangla dubbed")
                                return scrape_movie_page_for_watch_url(bangla_url)
                            else:
                                print("⚠️ Bangla dubbed is series URL, trying movie page scraping")
                                return scrape_movie_page_for_watch_url(bangla_url)
                        else:
                            print("❌ No Bangla dubbed version found")
                except Exception as e:
                    print(f"❌ Bangla fallback failed: {e}")
            
            # Fallback to movie resolver in case series page uses a different structure
            return scrape_movie_page_for_watch_url(series_url)

        # Pick best by language priority
        candidates.sort(key=lambda c: c['lang_weight'])
        best_gw = candidates[0]['getwatch']
        if not best_gw.startswith('http'):
            best_gw = f"{base_host}{best_gw}"

        print(f"🎯 Selected getWatch: {best_gw}")
        gw_resp = make_request_with_proxy_fallback(best_gw, timeout=30)
        if gw_resp.status_code != 200:
            return {'success': False, 'error': f'Failed to load getWatch page: {gw_resp.status_code}'}
        gw_soup = BeautifulSoup(gw_resp.text, 'html.parser')

        # Resolve to final watch/episode URL (meta/JS/redirect)
        watch_url = None
        meta_refresh = gw_soup.find('meta', attrs={'http-equiv': 'refresh'})
        if meta_refresh:
            content = meta_refresh.get('content', '')
            if 'url=' in content:
                watch_url = content.split('url=')[1]
        if not watch_url:
            for script in gw_soup.find_all('script'):
                if script.string and ('window.location' in script.string or 'location.href' in script.string):
                    m = re.search(r'\"([^\"]*(watch|episode)[^\"]*)\"|\'([^\']*(watch|episode)[^\']*)\'', script.string)
                    if m:
                        watch_url = (m.group(1) or m.group(3))
                        break
        if not watch_url and ('/watch/' in gw_resp.url or '/episode/' in gw_resp.url):
            watch_url = gw_resp.url
        if not watch_url:
            return {'success': False, 'error': 'Could not resolve final watch URL'}
        if not watch_url.startswith('http'):
            watch_url = f"{base_host}{watch_url}"

        print(f"✅ Episode watch URL: {watch_url}")
        return api_service.scrape_video_page(watch_url)
    except Exception as e:
        print(f"❌ Series episode scrape error: {e}")
        return {'success': False, 'error': str(e)}

class MovieLinkBDAPI:
    """API service for MovieLinkBD scraping and video serving"""
    
    def __init__(self):
        self.session = requests.Session()
        # Set up session with headers that avoid brotli
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',  # Avoid brotli
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        })
    
    def extract_video_info(self, html_content: str) -> Dict[str, Any]:
        """Extract video information from the HTML content"""
        video_info = {
            'title': '',
            'video_url': '',
            'download_url': '',
            'popunder_url': '',
            'stable_id': '',
            'file_info': {},
            'player_type': 'unknown',
            'quality_options': [],
            'subtitles': []
        }
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title
            title_element = soup.find('title')
            if title_element:
                video_info['title'] = title_element.get_text().strip()
            
            # Extract video source URL from JavaScript
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string:
                    script_content = script.string
                    
                    # Look for SRC variable
                    src_match = re.search(r'const SRC\s*=\s*["\']([^"\']+)["\']', script_content)
                    if src_match:
                        video_info['video_url'] = src_match.group(1).replace('\\/', '/')
                    
                    # Look for download URL in href attributes
                    download_match = re.search(r'href=["\']([^"\']*\/file\/[^"\']*)["\']', script_content)
                    if download_match:
                        video_info['download_url'] = download_match.group(1)
                    
                    # Look for popunder URL
                    popunder_match = re.search(r'const POPUNDER_URL = ["\']([^"\']+)["\']', script_content)
                    if popunder_match:
                        video_info['popunder_url'] = popunder_match.group(1).replace('\\/', '/')
                    
                    # Look for stable ID
                    stable_id_match = re.search(r'const STABLE_ID = ["\']([^"\']+)["\']', script_content)
                    if stable_id_match:
                        video_info['stable_id'] = stable_id_match.group(1)
            
            # Extract file information from chips
            chips = soup.find_all('span', class_='chip')
            for chip in chips:
                chip_text = chip.get_text().strip()
                if 'GB' in chip_text:
                    video_info['file_info']['size'] = chip_text
                elif 'MKV' in chip_text or 'MP4' in chip_text:
                    video_info['file_info']['format'] = chip_text
                elif 'Fast Stream' in chip_text:
                    video_info['file_info']['stream_type'] = chip_text
            
            # Also search for download URL in the entire HTML content
            if not video_info['download_url']:
                download_match = re.search(r'href=["\']([^"\']*\/file\/[^"\']*)["\']', html_content)
                if download_match:
                    video_info['download_url'] = download_match.group(1)
            
            # Determine player type
            if 'jwplayer' in html_content.lower():
                video_info['player_type'] = 'jwplayer'
            elif 'video' in html_content.lower():
                video_info['player_type'] = 'html5_video'
            
            # Extract quality options
            quality_patterns = [
                r'(\d{3,4}p)',
                r'(HD|SD|FHD|UHD|4K)',
                r'(720p|1080p|480p|360p)'
            ]
            for pattern in quality_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                video_info['quality_options'].extend(matches)
            
            video_info['quality_options'] = list(set(video_info['quality_options']))
            
        except Exception as e:
            print(f"Error extracting video info: {e}")
        
        return video_info
    
    def scrape_video_page(self, url: str) -> Dict[str, Any]:
        """Scrape the video page and extract all information"""
        results = {
            'success': False,
            'url': url,
            'video_info': {},
            'error': ''
        }
        
        try:
            print(f"🌐 Scraping MovieLinkBD URL: {url}")
            
            # Make request
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ Successfully got response!")
                
                # Get the HTML content (requests handles gzip automatically)
                html_content = response.text
                
                # Check if we got proper HTML
                if html_content.startswith('<!DOCTYPE html') or html_content.startswith('<html') or '<script>' in html_content:
                    print("✅ Got proper HTML content!")
                    results['success'] = True
                    
                    # Extract video information
                    video_info = self.extract_video_info(html_content)
                    results['video_info'] = video_info
                    
                else:
                    print("❌ Content doesn't appear to be HTML")
                    results['error'] = "Content is not HTML format"
                    
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                results['error'] = f"HTTP {response.status_code}"
                
        except Exception as e:
            print(f"❌ Error: {e}")
            results['error'] = str(e)
        
        return results

# Initialize the API service
api_service = MovieLinkBDAPI()

# HTML template for the video player
VIDEO_PLAYER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    
    <!-- JWPlayer Scripts -->
    <script src="https://ssl.p.jwpcdn.com/player/v/8.22.0/jwplayer.js"></script>
    <script src="https://cdn.jwplayer.com/libraries/IDzF9Zmk.js"></script>
    
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: #0b1020;
            color: #e6edf3;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .title {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #fff;
        }
        
        .file-info {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .info-chip {
            background: rgba(255, 255, 255, 0.1);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .video-container {
            position: relative;
            width: 100%;
            max-width: 1000px;
            margin: 0 auto;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }
        
        .video-wrapper {
            position: relative;
            width: 100%;
            padding-bottom: 56.25%; /* 16:9 aspect ratio */
            height: 0;
        }
        
        .video-wrapper iframe,
        .video-wrapper video {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
        }
        
        .controls {
            margin-top: 20px;
            text-align: center;
        }
        
        .btn {
            background: #007bff;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin: 0 10px;
            font-size: 16px;
            transition: background 0.3s;
        }
        
        .btn:hover {
            background: #0056b3;
        }
        
        .btn-secondary {
            background: #6c757d;
        }
        
        .btn-secondary:hover {
            background: #545b62;
        }
        
        .error {
            background: #dc3545;
            color: white;
            padding: 20px;
            border-radius: 5px;
            text-align: center;
            margin: 20px 0;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            font-size: 18px;
        }
        
        .quality-info {
            margin-top: 15px;
            font-size: 14px;
            color: #9aa4b2;
        }
        
        .video-loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-size: 18px;
            z-index: 10;
        }
        
        .video-error {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #ff6b6b;
            font-size: 16px;
            text-align: center;
            z-index: 10;
        }
        
        /* JWPlayer Custom Styling */
        .jwplayer {
            border-radius: 10px !important;
            overflow: hidden !important;
        }
        
        .jwplayer .jw-controls {
            background: linear-gradient(transparent, rgba(0,0,0,0.8)) !important;
        }
        
        .jwplayer .jw-button-color {
            color: #007bff !important;
        }
        
        .jwplayer .jw-icon-play {
            background-color: #007bff !important;
        }
        
        .jwplayer .jw-progress {
            background-color: rgba(255,255,255,0.3) !important;
        }
        
        .jwplayer .jw-buffer {
            background-color: rgba(0,123,255,0.5) !important;
        }
        
        .jwplayer .jw-rail {
            background-color: #007bff !important;
        }
        
        .jwplayer .jw-knob {
            background-color: #007bff !important;
        }
        
        .jwplayer .jw-time-tip {
            background-color: #1a1a2e !important;
            color: #fff !important;
        }
        
        .jwplayer .jw-menu {
            background-color: #1a1a2e !important;
            border: 1px solid #007bff !important;
        }
        
        .jwplayer .jw-menu-item {
            color: #fff !important;
        }
        
        .jwplayer .jw-menu-item:hover {
            background-color: #007bff !important;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">{{ title }}</h1>
            {% if file_info %}
            <div class="file-info">
                {% if file_info.size %}
                <span class="info-chip">📁 {{ file_info.size }}</span>
                {% endif %}
                {% if file_info.format %}
                <span class="info-chip">🎬 {{ file_info.format }}</span>
                {% endif %}
                {% if file_info.stream_type %}
                <span class="info-chip">⚡ {{ file_info.stream_type }}</span>
                {% endif %}
            </div>
            {% endif %}
        </div>
        
        {% if video_url %}
        <div class="video-container">
            <div class="video-wrapper">
                <!-- JWPlayer Container -->
                <div id="player" style="width: 100%; height: 100%;"></div>
                
                <!-- Fallback HTML5 video player -->
                <video id="video-player" controls preload="none" style="width: 100%; height: 100%; display: none;">
                    <source src="/proxy/video?url={{ video_url | urlencode }}" type="video/mp4">
                    <source src="/proxy/video?url={{ video_url | urlencode }}" type="video/webm">
                    <source src="/proxy/video?url={{ video_url | urlencode }}" type="video/ogg">
                    <p>Your browser does not support the video tag. <a href="{{ video_url }}" target="_blank">Click here to download the video</a></p>
                </video>
            </div>
        </div>
        
        <div class="controls">
            <button id="play-video" class="btn" onclick="playVideo()" style="display: none;">
                ▶️ Play Video
            </button>
            <button id="switch-player" class="btn btn-secondary" onclick="switchPlayer()">
                🔄 Switch Player
            </button>
            {% if download_url %}
            <a href="{{ download_url }}" class="btn btn-secondary" target="_blank">
                📥 Download Video
            </a>
            {% endif %}
            <a href="/" class="btn">🏠 Back to Home</a>
        </div>
        
        {% if quality_options %}
        <div class="quality-info">
            Available Qualities: {{ quality_options | join(', ') }}
        </div>
        {% endif %}
        
        {% else %}
        <div class="error">
            ❌ No video URL found. The video might not be available or the URL is invalid.
        </div>
        {% endif %}
    </div>
    
    <script>
        // Video loading and error handling
        document.addEventListener('DOMContentLoaded', function() {
            const videoContainer = document.querySelector('.video-container');
            const video = document.getElementById('video-player');
            
            if (videoContainer) {
                // Add loading indicator
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'video-loading';
                loadingDiv.innerHTML = '🔄 Loading video...';
                videoContainer.appendChild(loadingDiv);
                
                // Initialize JWPlayer
                initializeJWPlayer();
                
                // Handle HTML5 video events (fallback)
                if (video) {
                    video.addEventListener('loadstart', function() {
                        loadingDiv.style.display = 'block';
                    });
                    
                    video.addEventListener('canplay', function() {
                        loadingDiv.style.display = 'none';
                    });
                    
                    video.addEventListener('error', function(e) {
                        loadingDiv.style.display = 'none';
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'video-error';
                        errorDiv.innerHTML = '❌ Video failed to load. <br><a href="{{ video_url }}" target="_blank" style="color: #007bff;">Try direct link</a>';
                        videoContainer.appendChild(errorDiv);
                    });
                }
            }
        });
        
        // Initialize JWPlayer with MovieLinkBD configuration
        function initializeJWPlayer() {
            if (typeof jwplayer === 'undefined') {
                console.log('JWPlayer not loaded, falling back to HTML5');
                setTimeout(function() {
                    document.getElementById('player').style.display = 'none';
                    document.getElementById('video-player').style.display = 'block';
                    document.getElementById('play-video').style.display = 'inline-block';
                }, 2000);
                return;
            }
            
            try {
                // Set JWPlayer license key (same as MovieLinkBD)
                jwplayer.key = "cLGMn8T20tGvW+0eXPhq4NNmLB57TrscPjd1IyJF84o=";
                
                // Get video URL and determine type
                const videoUrl = "{{ video_url }}";
                const proxyUrl = "/proxy/video?url=" + encodeURIComponent(videoUrl);
                
                // Guess video type based on URL
                function guessType(url) {
                    if (url.includes('.m3u8')) return 'hls';
                    if (url.includes('.mpd')) return 'dash';
                    if (url.includes('.mp4')) return 'mp4';
                    if (url.includes('.webm')) return 'webm';
                    if (url.includes('.ogg')) return 'ogg';
                    return 'mp4'; // default
                }
                
                // Create multiple quality sources
                const qualityOptions = {{ quality_options | tojson }};
                const playlist = [];
                
                // Add main source
                playlist.push({
                    file: proxyUrl,
                    type: guessType(videoUrl),
                    label: 'Auto',
                    default: true
                });
                
                // Add quality-specific sources if available
                if (qualityOptions && qualityOptions.length > 0) {
                    // Remove duplicates and sort qualities
                    const uniqueQualities = [...new Set(qualityOptions)].sort((a, b) => {
                        const order = ['360p', '480p', '720p', '1024p', '1080p', 'hd', 'HD', 'sd', 'SD'];
                        return order.indexOf(a) - order.indexOf(b);
                    });
                    
                    uniqueQualities.forEach(quality => {
                        if (quality !== 'Auto') {
                            playlist.push({
                                file: proxyUrl,
                                type: guessType(videoUrl),
                                label: quality.toUpperCase(),
                                default: false
                            });
                        }
                    });
                }
                
                // Setup JWPlayer with MovieLinkBD configuration
                const player = jwplayer('player').setup({
                    width: '100%',
                    height: '100%',
                    title: "{{ title }}",
                    primary: 'html5',
                    stretching: 'contain',
                    preload: 'auto',
                    autostart: true,
                    mute: false,
                    hlshtml: true,
                    renderCaptionsNatively: true,
                    playbackRateControls: true,
                    showAdMarkers: false,
                    cast: {}, // Chromecast / Android TV
                    playlist: playlist,
                    // Additional MovieLinkBD-like settings
                    skin: {
                        name: 'seven',
                        active: '#007bff',
                        inactive: '#ffffff',
                        background: 'transparent'
                    },
                    controls: true,
                    displaytitle: true,
                    displaydescription: true,
                    sharing: false,
                    related: false,
                    abouttext: 'MovieLinkBD Ad-Free Player',
                    aboutlink: 'https://movielinkbd.one'
                });
                
                // Handle JWPlayer events
                player.on('ready', function() {
                    console.log('✅ JWPlayer ready');
                    document.querySelector('.video-loading').style.display = 'none';
                    // Ensure player is not muted
                    try {
                        player.setMute(false);
                        console.log('🔊 Player unmuted');
                    } catch (e) {
                        console.log('Note: Could not set mute state');
                    }
                });
                
                player.on('error', function(e) {
                    console.error('❌ JWPlayer error:', e);
                    // Fallback to HTML5 player
                    document.getElementById('player').style.display = 'none';
                    document.getElementById('video-player').style.display = 'block';
                    document.getElementById('play-video').style.display = 'inline-block';
                });
                
                player.on('buffer', function() {
                    console.log('🔄 JWPlayer buffering...');
                });
                
            } catch (error) {
                console.error('❌ JWPlayer setup error:', error);
                // Fallback to HTML5 player
                document.getElementById('player').style.display = 'none';
                document.getElementById('video-player').style.display = 'block';
                document.getElementById('play-video').style.display = 'inline-block';
            }
        }
        
        // Function to switch between JWPlayer and HTML5 video player
        function switchPlayer() {
            const player = document.getElementById('player');
            const video = document.getElementById('video-player');
            const switchBtn = document.getElementById('switch-player');
            const playBtn = document.getElementById('play-video');
            
            if (player && video) {
                if (player.style.display !== 'none') {
                    // Switch to HTML5 video
                    player.style.display = 'none';
                    video.style.display = 'block';
                    playBtn.style.display = 'inline-block';
                    switchBtn.innerHTML = '🎬 Switch to JWPlayer';
                } else {
                    // Switch to JWPlayer
                    video.style.display = 'none';
                    playBtn.style.display = 'none';
                    player.style.display = 'block';
                    switchBtn.innerHTML = '🎥 Switch to HTML5';
                    // Reinitialize JWPlayer
                    initializeJWPlayer();
                }
            }
        }
        
        // Function to manually play the video
        function playVideo() {
            const video = document.getElementById('video-player');
            const playBtn = document.getElementById('play-video');
            
            if (video) {
                video.load();
                video.play().then(() => {
                    playBtn.style.display = 'none';
                    console.log('✅ Video started playing');
                }).catch((error) => {
                    console.error('❌ Video play failed:', error);
                    playBtn.innerHTML = '❌ Play Failed - Try Switch Player';
                });
            }
        }
    </script>
</body>
</html>
"""

# Override with minimal full-page embed player (no extra UI)
VIDEO_PLAYER_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\" />
    <title>{{ title }}</title>
    <script src=\"https://ssl.p.jwpcdn.com/player/v/8.22.0/jwplayer.js\"></script>
    <script src=\"https://cdn.jwplayer.com/libraries/IDzF9Zmk.js\"></script>
    <style>
        html, body { height: 100%; }
        body { margin: 0; background: #000; overflow: hidden; }
        #root { position: fixed; inset: 0; }
        #player, #video-fallback { position: absolute; inset: 0; width: 100%; height: 100%; }
        .loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #fff; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; font-size: 16px; text-align: center; }
        .loading-spinner { border: 2px solid #333; border-top: 2px solid #fff; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .version-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; display: none; }
        .version-content { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1a1a1a; padding: 25px; border-radius: 10px; max-width: 500px; width: 90%; max-height: 70vh; overflow-y: auto; }
        .version-header { color: #fff; font-size: 20px; margin-bottom: 15px; text-align: center; }
        .version-item { padding: 12px; margin: 8px 0; background: #2a2a2a; border-radius: 6px; cursor: pointer; transition: all 0.3s; border: 2px solid transparent; }
        .version-item:hover { background: #3a3a3a; border-color: #007bff; }
        .version-title { font-weight: bold; color: #fff; font-size: 14px; margin-bottom: 5px; }
        .version-info { font-size: 12px; color: #ccc; }
        .version-badge { display: inline-block; background: #007bff; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-right: 5px; }
        .close-overlay { position: absolute; top: 10px; right: 15px; color: #fff; font-size: 24px; cursor: pointer; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: rgba(255,255,255,0.1); }
        .close-overlay:hover { background: rgba(255,255,255,0.2); }
        .versions-btn { position: absolute; top: 20px; right: 20px; background: rgba(0,0,0,0.7); color: #fff; border: 1px solid #007bff; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; z-index: 100; }
        .versions-btn:hover { background: rgba(0,123,255,0.8); }
    </style>
    <meta name=\"referrer\" content=\"no-referrer\" />
</head>
<body>
    <div id=\"root\">
        {% if video_url %}
        <div id=\"player\"></div>
        <div id=\"loading\" class=\"loading\">
            <div class=\"loading-spinner\"></div>
            <div>Finding your content...</div>
            <div style=\"font-size: 12px; color: #ccc; margin-top: 5px;\">This may take a few moments</div>
        </div>
                        <video id=\"video-fallback\" controls preload=\"none\" style=\"display:none; background:#000;\">
                    <source src=\"{{ cloudflare_proxy_url }}/?url={{ video_url | urlencode }}\" type=\"video/mp4\" />
                </video>
        {% if versions and versions|length > 1 %}
        <button class=\"versions-btn\" onclick=\"showVersions()\" id=\"versions-btn\" style=\"display:none;\">
            📋 {{ versions|length }} Versions
        </button>
        {% endif %}
        {% else %}
        <div class=\"loading\">
            <div class=\"loading-spinner\"></div>
            <div>Searching for content...</div>
            <div style=\"font-size: 12px; color: #ccc; margin-top: 5px;\">Please wait while we find your video</div>
        </div>
        {% endif %}
    </div>
    
    {% if versions and versions|length > 1 %}
    <div id=\"version-overlay\" class=\"version-overlay\">
        <div class=\"version-content\">
            <span class=\"close-overlay\" onclick=\"hideVersions()\">&times;</span>
            <div class=\"version-header\">Select Version</div>
            <div id=\"version-list\">
                {% for version in versions %}
                <div class=\"version-item\" onclick=\"loadVersion('{{ version.url }}')\" data-url=\"{{ version.url }}\">
                    <div class=\"version-title\">{{ version.title }}</div>
                    <div class=\"version-info\">
                        <span class=\"version-badge\">{{ version.type }}</span>
                        {% if version.quality %}<span class=\"version-badge\">{{ version.quality }}</span>{% endif %}
                        {% if version.language %}<span class=\"version-badge\">{{ version.language }}</span>{% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    {% endif %}
    
    <script>
        const versions = {{ versions | tojson if versions else '[]' }};
        
        function showVersions() {
            document.getElementById('version-overlay').style.display = 'block';
        }
        
        function hideVersions() {
            document.getElementById('version-overlay').style.display = 'none';
        }
        
        function loadVersion(url) {
            window.location.href = '/api/watch?url=' + encodeURIComponent(url);
        }
        
        (function(){
            const hasSource = {{ 'true' if video_url else 'false' }};
            
            // Show versions button after player loads if multiple versions available
            if (versions && versions.length > 1) {
                setTimeout(function() {
                    var btn = document.getElementById('versions-btn');
                    if (btn) btn.style.display = 'block';
                }, 2000);
            }
            
            if(!hasSource){ 
                // Auto-refresh for loading page every 3 seconds
                setTimeout(function() {
                    window.location.reload();
                }, 3000);
                return; 
            }
            
            function guessType(url){
                if(url.includes('.m3u8')) return 'hls';
                if(url.includes('.mpd')) return 'dash';
                if(url.includes('.webm')) return 'webm';
                if(url.includes('.ogg')) return 'ogg';
                return 'mp4';
            }
                            const videoUrl = "{{ video_url }}";
                const proxyUrl = "{{ cloudflare_proxy_url }}/?url=" + encodeURIComponent(videoUrl);
                const playlist = [{ file: proxyUrl, type: guessType(videoUrl), label: 'Auto', default: true }];
            try {
                if(typeof jwplayer === 'undefined') throw new Error('JW missing');
                jwplayer.key = "cLGMn8T20tGvW+0eXPhq4NNmLB57TrscPjd1IyJF84o=";
                const player = jwplayer('player').setup({
                    width: '100%', height: '100%',
                    title: "{{ title }}",
                    primary: 'html5', stretching: 'contain',
                    preload: 'auto', autostart: true, mute: false,
                    hlshtml: true, renderCaptionsNatively: true,
                    playbackRateControls: true, showAdMarkers: false,
                    cast: {}, playlist
                });
                player.on('ready', function(){
                    var l = document.getElementById('loading'); if(l) l.style.display='none';
                    var btn = document.getElementById('versions-btn'); if(btn) btn.style.display='block';
                    try{ player.setMute(false); }catch(e){}
                });
                player.on('error', function(){
                    document.getElementById('player').style.display='none';
                    var v = document.getElementById('video-fallback'); v.style.display='block';
                    var l = document.getElementById('loading'); if(l) l.style.display='none';
                    var btn = document.getElementById('versions-btn'); if(btn) btn.style.display='block';
                });
            } catch (e) {
                document.getElementById('player').style.display='none';
                var v = document.getElementById('video-fallback'); v.style.display='block';
                var l = document.getElementById('loading'); if(l) l.style.display='none';
                var btn = document.getElementById('versions-btn'); if(btn) btn.style.display='block';
            }
        })();
    </script>
 </body>
</html>
"""

# Immediate loading template with progress tracking
IMMEDIATE_LOADING_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\" />
    <title>{{ title }}</title>
    <script src=\"https://ssl.p.jwpcdn.com/player/v/8.22.0/jwplayer.js\"></script>
    <script src=\"https://cdn.jwplayer.com/libraries/IDzF9Zmk.js\"></script>
    <style>
        html, body { height: 100%; }
        body { margin: 0; background: #000; overflow: hidden; }
        #root { position: fixed; inset: 0; }
        #player, #video-fallback { position: absolute; inset: 0; width: 100%; height: 100%; }
        .loading-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; display: flex; flex-direction: column; justify-content: center; align-items: center; color: #fff; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
        .loading-spinner { border: 3px solid #333; border-top: 3px solid #007bff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin-bottom: 20px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .loading-text { font-size: 18px; margin-bottom: 10px; text-align: center; }
        .loading-subtext { font-size: 14px; color: #ccc; margin-bottom: 20px; text-align: center; }
        .progress-container { width: 300px; background: #333; border-radius: 10px; overflow: hidden; margin-bottom: 10px; }
        .progress-bar { height: 20px; background: linear-gradient(90deg, #007bff, #00bfff); width: 0%; transition: width 0.3s ease; border-radius: 10px; }
        .progress-text { font-size: 14px; color: #fff; text-align: center; }
        .version-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; display: none; }
        .version-content { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1a1a1a; padding: 25px; border-radius: 10px; max-width: 500px; width: 90%; max-height: 70vh; overflow-y: auto; }
        .version-header { color: #fff; font-size: 20px; margin-bottom: 15px; text-align: center; }
        .version-item { padding: 12px; margin: 8px 0; background: #2a2a2a; border-radius: 6px; cursor: pointer; transition: all 0.3s; border: 2px solid transparent; }
        .version-item:hover { background: #3a3a3a; border-color: #007bff; }
        .version-title { font-weight: bold; color: #fff; font-size: 14px; margin-bottom: 5px; }
        .version-info { font-size: 12px; color: #ccc; }
        .version-badge { display: inline-block; background: #007bff; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-right: 5px; }
        .close-overlay { position: absolute; top: 10px; right: 15px; color: #fff; font-size: 24px; cursor: pointer; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: rgba(255,255,255,0.1); }
        .close-overlay:hover { background: rgba(255,255,255,0.2); }
        .versions-btn { position: absolute; top: 20px; right: 20px; background: rgba(0,0,0,0.7); color: #fff; border: 1px solid #007bff; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; z-index: 100; }
        .versions-btn:hover { background: rgba(0,123,255,0.8); }
    </style>
    <meta name=\"referrer\" content=\"no-referrer\" />
</head>
<body>
    <div id=\"root\">
        <div id=\"player\"></div>
        <video id=\"video-fallback\" controls preload=\"none\" style=\"display:none; background:#000;\">
        </video>
        
        <div id=\"loading-overlay\" class=\"loading-overlay\">
            <div class=\"loading-spinner\"></div>
            <div class=\"loading-text\">Loading {{ title }}...</div>
            <div class=\"loading-subtext\">Finding and preparing your content</div>
            <div class=\"progress-container\">
                <div id=\"progress-bar\" class=\"progress-bar\"></div>
            </div>
            <div id=\"progress-text\" class=\"progress-text\">0%</div>
        </div>
        
        <button class=\"versions-btn\" onclick=\"showVersions()\" id=\"versions-btn\" style=\"display:none;\">
            📋 <span id=\"version-count\">0</span> Versions
        </button>
    </div>
    
    <div id=\"version-overlay\" class=\"version-overlay\">
        <div class=\"version-content\">
            <span class=\"close-overlay\" onclick=\"hideVersions()\">&times;</span>
            <div class=\"version-header\">Select Version</div>
            <div id=\"version-list\"></div>
        </div>
    </div>
    
    <script>
        const tmdbId = {{ tmdb_id }};
        const title = "{{ title }}";
        const type = "{{ type }}";
        const season = {{ season if season else 'null' }};
        const episode = {{ episode if episode else 'null' }};
        let versions = [];
        let currentProgress = 0;
        
        function updateProgress(percent, text) {
            currentProgress = percent;
            document.getElementById('progress-bar').style.width = percent + '%';
            document.getElementById('progress-text').textContent = text || (percent + '%');
        }
        
        function showVersions() {
            document.getElementById('version-overlay').style.display = 'block';
        }
        
        function hideVersions() {
            document.getElementById('version-overlay').style.display = 'none';
        }
        
        function loadVersion(url) {
            window.location.href = '/api/watch?url=' + encodeURIComponent(url);
        }
        
        function initializePlayer(videoInfo) {
            const loadingOverlay = document.getElementById('loading-overlay');
            const player = document.getElementById('player');
            const video = document.getElementById('video-fallback');
            
            if (!videoInfo || !videoInfo.video_url) {
                loadingOverlay.innerHTML = '<div style=\"text-align: center;\"><div style=\"color: #ff6b6b; font-size: 18px; margin-bottom: 10px;\">❌ No video found</div><div style=\"color: #ccc;\">The content might not be available</div></div>';
                return;
            }
            
            // Hide loading overlay
            loadingOverlay.style.display = 'none';
            
            // Show versions button if multiple versions available
            if (versions && versions.length > 1) {
                document.getElementById('version-count').textContent = versions.length;
                document.getElementById('versions-btn').style.display = 'block';
                
                // Populate version list
                const versionList = document.getElementById('version-list');
                versionList.innerHTML = '';
                versions.forEach(version => {
                    const item = document.createElement('div');
                    item.className = 'version-item';
                    item.innerHTML = `
                        <div class=\"version-title\">${version.title}</div>
                        <div class=\"version-info\">
                            <span class=\"version-badge\">${version.type}</span>
                            ${version.quality ? `<span class=\"version-badge\">${version.quality}</span>` : ''}
                            ${version.language ? `<span class=\"version-badge\">${version.language}</span>` : ''}
                        </div>
                    `;
                    item.onclick = () => loadVersion(version.url);
                    versionList.appendChild(item);
                });
            }
            
            // Initialize JWPlayer
            try {
                if (typeof jwplayer === 'undefined') throw new Error('JWPlayer not loaded');
                
                jwplayer.key = "cLGMn8T20tGvW+0eXPhq4NNmLB57TrscPjd1IyJF84o=";
                
                function guessType(url) {
                    if (url.includes('.m3u8')) return 'hls';
                    if (url.includes('.mpd')) return 'dash';
                    if (url.includes('.webm')) return 'webm';
                    if (url.includes('.ogg')) return 'ogg';
                    return 'mp4';
                }
                
                const videoUrl = videoInfo.video_url;
                const proxyUrl = "{{ cloudflare_proxy_url }}/?url=" + encodeURIComponent(videoUrl);
                const playlist = [{ file: proxyUrl, type: guessType(videoUrl), label: 'Auto', default: true }];
                
                const playerInstance = jwplayer('player').setup({
                    width: '100%', height: '100%',
                    title: title,
                    primary: 'html5', stretching: 'contain',
                    preload: 'auto', autostart: true, mute: false,
                    hlshtml: true, renderCaptionsNatively: true,
                    playbackRateControls: true, showAdMarkers: false,
                    cast: {}, playlist
                });
                
                playerInstance.on('ready', function() {
                    console.log('✅ Player ready');
                    try { playerInstance.setMute(false); } catch(e) {}
                });
                
                playerInstance.on('error', function() {
                    console.log('❌ JWPlayer error, falling back to HTML5');
                    player.style.display = 'none';
                    video.style.display = 'block';
                    video.src = proxyUrl;
                });
                
            } catch (e) {
                console.log('❌ JWPlayer setup failed, using HTML5 fallback');
                player.style.display = 'none';
                video.style.display = 'block';
                video.src = "{{ cloudflare_proxy_url }}/?url=" + encodeURIComponent(videoInfo.video_url);
            }
        }
        
        // Start background scraping
        async function startScraping() {
            updateProgress(10, 'Getting content info...');
            
            try {
                const endpoint = type === 'movie' ? `/api/scrape/${tmdbId}` : `/api/scrape/${tmdbId}/${season}/${episode}`;
                updateProgress(25, 'Searching for content...');
                
                const response = await fetch(endpoint);
                const data = await response.json();
                
                if (data.success) {
                    updateProgress(75, 'Preparing video...');
                    versions = data.versions || [];
                    updateProgress(100, 'Ready!');
                    
                    setTimeout(() => {
                        initializePlayer(data.video_info);
                    }, 500);
                } else {
                    throw new Error(data.error || 'Scraping failed');
                }
            } catch (error) {
                console.error('Scraping error:', error);
                updateProgress(100, 'Error loading content');
                setTimeout(() => {
                    document.getElementById('loading-overlay').innerHTML = 
                        '<div style=\"text-align: center;\"><div style=\"color: #ff6b6b; font-size: 18px; margin-bottom: 10px;\">❌ Loading Failed</div><div style=\"color: #ccc;\">' + error.message + '</div></div>';
                }, 1000);
            }
        }
        
        // Start scraping when page loads
        document.addEventListener('DOMContentLoaded', startScraping);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    """Home page with URL input form"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MovieLinkBD API - Ad-Free Video Player</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background: linear-gradient(135deg, #0b1020 0%, #1a1a2e 100%);
                color: #e6edf3;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .container {
                max-width: 600px;
                width: 90%;
                text-align: center;
            }
            
            .logo {
                font-size: 48px;
                margin-bottom: 20px;
            }
            
            .title {
                font-size: 32px;
                font-weight: bold;
                margin-bottom: 10px;
                color: #fff;
            }
            
            .subtitle {
                font-size: 18px;
                color: #9aa4b2;
                margin-bottom: 40px;
            }
            
            .form-group {
                margin-bottom: 20px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 10px;
                font-size: 16px;
                color: #fff;
            }
            
            .form-group input {
                width: 100%;
                padding: 15px;
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.1);
                color: #fff;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            
            .form-group input:focus {
                outline: none;
                border-color: #007bff;
            }
            
            .form-group input::placeholder {
                color: #9aa4b2;
            }
            
            .btn {
                background: #007bff;
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-size: 18px;
                font-weight: bold;
                transition: background 0.3s;
                width: 100%;
            }
            
            .btn:hover {
                background: #0056b3;
            }
            
            .features {
                margin-top: 40px;
                text-align: left;
            }
            
            .feature {
                display: flex;
                align-items: center;
                margin-bottom: 15px;
                padding: 10px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
            
            .feature-icon {
                font-size: 24px;
                margin-right: 15px;
            }
            
            .api-info {
                margin-top: 30px;
                padding: 20px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                text-align: left;
            }
            
            .api-info h3 {
                margin-bottom: 10px;
                color: #007bff;
            }
            
            .api-info code {
                background: rgba(0, 0, 0, 0.3);
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🎬</div>
            <h1 class="title">MovieLinkBD API</h1>
            <p class="subtitle">Ad-Free Video Player</p>
            
            <div class="nav-links" style="margin: 20px 0;">
                <a href="/search" style="color: #007bff; text-decoration: none; font-size: 18px; margin: 0 15px; padding: 10px 20px; border: 2px solid #007bff; border-radius: 5px; display: inline-block;">🔍 Search Movies</a>
                <a href="/api/health" style="color: #28a745; text-decoration: none; font-size: 18px; margin: 0 15px; padding: 10px 20px; border: 2px solid #28a745; border-radius: 5px; display: inline-block;">📊 API Status</a>
            </div>
            
            <form action="/watch" method="POST">
                <div class="form-group">
                    <label for="url">Enter MovieLinkBD URL:</label>
                    <input type="url" id="url" name="url" placeholder="https://mlink82.movielinkbd.sbs/watch/..." required>
                </div>
                <button type="submit" class="btn">🚀 Watch Video</button>
            </form>
            
            <div class="features">
                <div class="feature">
                    <span class="feature-icon">🚫</span>
                    <span>No Ads - Clean viewing experience</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">⚡</span>
                    <span>Fast streaming with multiple quality options</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">📥</span>
                    <span>Direct download links available</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">🔒</span>
                    <span>Secure and private</span>
                </div>
            </div>
            
            <div class="api-info">
                <h3>API Usage:</h3>
                <p>You can also use this as an API:</p>
                <p><code>GET /api/watch?url=YOUR_MOVIELINKBD_URL</code></p>
                <p><code>POST /watch</code> with form data</p>
            </div>
        </div>
    </body>
    </html>
    '''

def scrape_movie_page_for_watch_url(movie_url):
    """Scrape movie page to find the watch button and get the actual watch URL"""
    try:
        print(f"🔍 Scraping movie page: {movie_url}")
        
        # Use the proxy fallback helper
        response = make_request_with_proxy_fallback(movie_url, timeout=8)
        if not response:
            return {'success': False, 'error': 'Failed to load movie page: 403'}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for watch buttons/links
        watch_links = []
        
        # Look for various watch button patterns
        watch_selectors = [
            'a[href*="/getWatch/"]',
            'a[href*="/watch/"]',
            'button[onclick*="getWatch"]',
            'a[onclick*="getWatch"]',
            '.watch-btn',
            '.play-btn',
            '#watch-btn',
            '#play-btn'
        ]
        
        for selector in watch_selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get('href', '')
                onclick = element.get('onclick', '')
                
                if '/getWatch/' in href:
                    watch_links.append(href)
                elif '/getWatch/' in onclick:
                    # Extract URL from onclick
                    import re
                    match = re.search(r'/getWatch/[^"\']+', onclick)
                    if match:
                        watch_links.append(match.group(0))
        
        if not watch_links:
            return {'success': False, 'error': 'No watch button found on movie page'}
        
        # Use the first watch link found
        getwatch_url = watch_links[0]
        if not getwatch_url.startswith('http'):
            getwatch_url = f"https://playk8.movielinkbd.sbs{getwatch_url}"
        
        print(f"🎯 Found getWatch URL: {getwatch_url}")
        
        # Now get the getWatch page to find the actual watch URL
        getwatch_response = make_request_with_proxy_fallback(getwatch_url, timeout=30)
        
        if getwatch_response.status_code != 200:
            return {'success': False, 'error': f'Failed to load getWatch page: {getwatch_response.status_code}'}
        
        getwatch_soup = BeautifulSoup(getwatch_response.text, 'html.parser')
        
        # Look for redirect or actual watch URL
        watch_url = None
        
        # Check for meta refresh redirect
        meta_refresh = getwatch_soup.find('meta', attrs={'http-equiv': 'refresh'})
        if meta_refresh:
            content = meta_refresh.get('content', '')
            if 'url=' in content:
                watch_url = content.split('url=')[1]
        
        # Check for JavaScript redirect
        scripts = getwatch_soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for window.location or similar redirects
                if 'window.location' in script.string or 'location.href' in script.string:
                    import re
                    # Try to extract URL from JavaScript
                    url_match = re.search(r'["\']([^"\']*watch[^"\']*)["\']', script.string)
                    if url_match:
                        watch_url = url_match.group(1)
                        break
        
        # Check if the page itself is a watch page
        if not watch_url and '/watch/' in getwatch_response.url:
            watch_url = getwatch_response.url
        
        if not watch_url:
            return {'success': False, 'error': 'Could not find actual watch URL from getWatch page'}
        
        # Ensure the watch URL has the proper domain
        if not watch_url.startswith('http'):
            watch_url = f"https://playk8.movielinkbd.sbs{watch_url}"
        
        print(f"✅ Found actual watch URL: {watch_url}")
        
        # Now scrape the actual watch page
        return api_service.scrape_video_page(watch_url)
        
    except Exception as e:
        print(f"❌ Error scraping movie page: {e}")
        return {'success': False, 'error': f'Error scraping movie page: {str(e)}'}

@app.route('/watch', methods=['GET', 'POST'])
def watch_video():
    """Handle video URL submission and display player"""
    # Handle both GET (from search) and POST (from form) requests
    if request.method == 'GET':
        url = request.args.get('url')
    else:  # POST
        url = request.form.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Check if this is a movie page or watch page
    if '/movie/' in url or '/series/' in url:
        # This is a movie/series page, we need to find the watch button
        print(f"🎬 Detected movie/series page, looking for watch button...")
        result = scrape_movie_page_for_watch_url(url)
    else:
        # This is already a watch page
        result = api_service.scrape_video_page(url)
    
    if not result['success']:
        return f'''
        <div class="error">
            ❌ Failed to scrape video: {result['error']}
            <br><br>
            <a href="/" class="btn">🏠 Back to Home</a>
        </div>
        ''', 400
    
    video_info = result['video_info']
    
    # Render the video player template
    return render_template_string(VIDEO_PLAYER_TEMPLATE, **video_info)

@app.route('/api/watch')
def api_watch():
    """API endpoint to get video information"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    # Scrape the video page
    result = api_service.scrape_video_page(url)
    
    if not result['success']:
        return jsonify({'error': result['error']}), 400
    
    return jsonify({
        'success': True,
        'video_info': result['video_info']
    })

@app.route('/api/<int:tmdb_id>')
def api_tmdb_movie(tmdb_id: int):
    """Return ad-free player by TMDB movie ID with immediate loading and progress."""
    try:
        # Check video cache first
        video_cache_key = get_cache_key(f"movie_{tmdb_id}")
        cached_video = get_cached_video_result(video_cache_key)
        if cached_video:
            print(f"🎯 Using cached video for TMDB {tmdb_id}")
            cached_video['cloudflare_proxy_url'] = CLOUDFLARE_PROXY_URL
            return render_template_string(VIDEO_PLAYER_TEMPLATE, **cached_video)
        
        # Get TMDB movie details for title
        data = tmdb_get(f"/movie/{tmdb_id}", params={'language': 'en-US'})
        movie_title = data.get('title') or data.get('original_title') or 'Unknown Movie'
        
        # Return immediate player with progress tracking
        return render_template_string(IMMEDIATE_LOADING_TEMPLATE, 
                                    tmdb_id=tmdb_id, 
                                    title=movie_title,
                                    type='movie',
                                    cloudflare_proxy_url=CLOUDFLARE_PROXY_URL)
    except Exception as e:
        return jsonify({'error': f'Failed to load TMDB movie: {str(e)}'}), 500

@app.route('/api/<int:tmdb_id>/<int:season>/<int:episode>')
def api_tmdb_tv_episode(tmdb_id: int, season: int, episode: int):
    """Return ad-free player by TMDB TV season/episode with immediate loading and progress."""
    try:
        # Check video cache first
        video_cache_key = get_cache_key(f"tv_{tmdb_id}_{season}_{episode}")
        cached_video = get_cached_video_result(video_cache_key)
        if cached_video:
            print(f"🎯 Using cached video for TMDB {tmdb_id} S{season}E{episode}")
            cached_video['cloudflare_proxy_url'] = CLOUDFLARE_PROXY_URL
            return render_template_string(VIDEO_PLAYER_TEMPLATE, **cached_video)
        
        # Get TMDB TV details for title
        data = tmdb_get(f"/tv/{tmdb_id}", params={'language': 'en-US'})
        tv_title = data.get('name') or data.get('original_name') or 'Unknown Series'
        
        # Return immediate player with progress tracking
        return render_template_string(IMMEDIATE_LOADING_TEMPLATE, 
                                    tmdb_id=tmdb_id, 
                                    title=tv_title,
                                    type='tv',
                                    season=season,
                                    episode=episode,
                                    cloudflare_proxy_url=CLOUDFLARE_PROXY_URL)
    except Exception as e:
        return jsonify({'error': f'Failed to load TMDB TV episode: {str(e)}'}), 500

@app.route('/api/scrape/<int:tmdb_id>')
def api_scrape_movie(tmdb_id: int):
    """Background scraping endpoint for movies with caching."""
    try:
        print(f"🔍 Starting scrape for TMDB movie {tmdb_id}")
        
        # Check video cache first
        video_cache_key = get_cache_key(f"movie_{tmdb_id}")
        cached_video = get_cached_video_result(video_cache_key)
        if cached_video:
            print(f"🎯 Returning cached video for TMDB {tmdb_id}")
            return jsonify({
                'success': True,
                'video_info': cached_video,
                'versions': cached_video.get('versions', [])
            })
        
        # Get TMDB movie details
        print(f"📡 Getting TMDB data for movie {tmdb_id}")
        data = tmdb_get(f"/movie/{tmdb_id}", params={'language': 'en-US'})
        movie_title = data.get('title') or data.get('original_title') or 'Unknown Movie'
        print(f"🎬 Movie title: {movie_title}")
        
        # Resolve movie URL with timeout handling
        print(f"🔍 Resolving MovieLinkBD URL for: {movie_title}")
        try:
            mlbd_url = resolve_tmdb_movie_to_mlbd_url(tmdb_id)
            if not mlbd_url:
                print(f"❌ Could not resolve URL for {movie_title}")
                return jsonify({'success': False, 'error': 'Could not map TMDB movie to source'})
        except Exception as e:
            print(f"❌ Error resolving URL: {str(e)}")
            return jsonify({'success': False, 'error': f'Timeout or error resolving movie: {str(e)}'})
        
        print(f"✅ Found MovieLinkBD URL: {mlbd_url}")
        
        # Find multiple versions (skip for now to speed up)
        versions = []  # search_movielinkbd_multiple_versions(movie_title, limit=5)
        
        # Scrape video content
        print(f"🎥 Scraping video content from: {mlbd_url}")
        result = scrape_movie_page_for_watch_url(mlbd_url) if '/movie/' in mlbd_url else api_service.scrape_video_page(mlbd_url)
        if not result['success']:
            print(f"❌ Scraping failed: {result['error']}")
            return jsonify({'success': False, 'error': result['error']})
        
        print(f"✅ Scraping successful for {movie_title}")
        
        # Add versions to video_info and cache
        result['video_info']['versions'] = versions
        cache_video_result(video_cache_key, result['video_info'])
        
        return jsonify({
            'success': True,
            'video_info': result['video_info'],
            'versions': versions
        })
    except Exception as e:
        print(f"❌ Exception in scrape_movie: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to scrape TMDB movie: {str(e)}'})

@app.route('/api/scrape/<int:tmdb_id>/<int:season>/<int:episode>')
def api_scrape_tv_episode(tmdb_id: int, season: int, episode: int):
    """Background scraping endpoint for TV episodes with caching."""
    try:
        # Check video cache first
        video_cache_key = get_cache_key(f"tv_{tmdb_id}_{season}_{episode}")
        cached_video = get_cached_video_result(video_cache_key)
        if cached_video:
            print(f"🎯 Returning cached video for TMDB {tmdb_id} S{season}E{episode}")
            return jsonify({
                'success': True,
                'video_info': cached_video,
                'versions': cached_video.get('versions', [])
            })
        
        # Get TMDB TV details
        data = tmdb_get(f"/tv/{tmdb_id}", params={'language': 'en-US'})
        tv_title = data.get('name') or data.get('original_name') or 'Unknown Series'
        
        # Resolve series URL
        mlbd_series_url = resolve_tmdb_tv_to_mlbd_url(tmdb_id, season, episode)
        if not mlbd_series_url:
            return jsonify({'success': False, 'error': 'Could not map TMDB series to source'})
        
        # Find multiple versions
        versions = search_movielinkbd_multiple_versions(tv_title, limit=5)
        
        # Scrape video content
        result = scrape_series_episode_for_watch_url(mlbd_series_url, season, episode)
        if not result['success']:
            return jsonify({'success': False, 'error': result['error']})
        
        # Add versions to video_info and cache
        result['video_info']['versions'] = versions
        cache_video_result(video_cache_key, result['video_info'])
        
        return jsonify({
            'success': True,
            'video_info': result['video_info'],
            'versions': versions
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to scrape TMDB TV episode: {str(e)}'})

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'MovieLinkBD API',
        'version': '1.0.0'
    })

@app.route('/api/test-search')
def test_search():
    """Test search functionality"""
    try:
        # Test with a simple search
        result = search_movielinkbd_first_url("F1")
        return jsonify({
            'success': True,
            'result': result,
            'message': 'Search test completed'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Search test failed'
        })

@app.route('/search')
def search_page():
    """Search page with form"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MovieLinkBD Search</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #111; color: #fff; }
            .container { max-width: 1200px; margin: 0 auto; }
            .search-form { text-align: center; margin: 50px 0; }
            .search-input { 
                padding: 15px; 
                font-size: 18px; 
                width: 400px; 
                border: 2px solid #007bff; 
                border-radius: 5px; 
                background: #222; 
                color: #fff; 
            }
            .search-btn { 
                padding: 15px 30px; 
                font-size: 18px; 
                background: #007bff; 
                color: white; 
                border: none; 
                border-radius: 5px; 
                cursor: pointer; 
                margin-left: 10px; 
            }
            .search-btn:hover { background: #0056b3; }
            .results { margin-top: 30px; }
            .movie-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
            .movie-card { 
                background: #222; 
                border-radius: 8px; 
                overflow: hidden; 
                transition: transform 0.3s; 
                cursor: pointer; 
            }
            .movie-card:hover { transform: scale(1.05); }
            .movie-poster { width: 100%; height: 300px; object-fit: cover; }
            .movie-info { padding: 15px; }
            .movie-title { font-weight: bold; margin-bottom: 5px; color: #fff; }
            .movie-meta { font-size: 12px; color: #888; margin-bottom: 3px; }
            .loading { text-align: center; margin: 50px 0; }
            .error { color: #ff4444; text-align: center; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 style="text-align: center; color: #007bff;">🎬 MovieLinkBD Search</h1>
            
            <form class="search-form" onsubmit="searchMovies(event)">
                <input type="text" class="search-input" id="searchQuery" placeholder="Search for movies..." required>
                <button type="submit" class="search-btn">🔍 Search</button>
            </form>
            
            <div id="results" class="results"></div>
        </div>
        
        <script>
            function searchMovies(event) {
                event.preventDefault();
                const query = document.getElementById('searchQuery').value;
                const resultsDiv = document.getElementById('results');
                
                resultsDiv.innerHTML = '<div class="loading">🔍 Searching for "' + query + '"...</div>';
                
                fetch('/api/search?q=' + encodeURIComponent(query))
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            resultsDiv.innerHTML = '<div class="error">❌ ' + data.error + '</div>';
                            return;
                        }
                        
                        if (data.movies && data.movies.length > 0) {
                            let html = '<h2>🎬 Search Results for "' + query + '" (' + data.movies.length + ' found)</h2>';
                            html += '<div class="movie-grid">';
                            
                            data.movies.forEach(movie => {
                                html += `
                                    <div class="movie-card" onclick="watchMovie('${movie.watch_url}')">
                                        <img src="${movie.poster}" class="movie-poster" alt="${movie.title}" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgdmlld0JveD0iMCAwIDIwMCAzMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIyMDAiIGhlaWdodD0iMzAwIiBmaWxsPSIjMzMzIi8+Cjx0ZXh0IHg9IjEwMCIgeT0iMTUwIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPk5vIEltYWdlPC90ZXh0Pgo8L3N2Zz4='">
                                        <div class="movie-info">
                                            <div class="movie-title">${movie.title}</div>
                                            <div class="movie-meta">📅 ${movie.year}</div>
                                            <div class="movie-meta">🎭 ${movie.type}</div>
                                            <div class="movie-meta">🌐 ${movie.language}</div>
                                            <div class="movie-meta">⭐ ${movie.rating}</div>
                                        </div>
                                    </div>
                                `;
                            });
                            
                            html += '</div>';
                            resultsDiv.innerHTML = html;
                        } else {
                            resultsDiv.innerHTML = '<div class="error">❌ No movies found for "' + query + '"</div>';
                        }
                    })
                    .catch(error => {
                        resultsDiv.innerHTML = '<div class="error">❌ Search failed: ' + error.message + '</div>';
                    });
            }
            
            function watchMovie(watchUrl) {
                window.location.href = '/watch?url=' + encodeURIComponent(watchUrl);
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/search')
def search_movies():
    """Search for movies on MovieLinkBD"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Search query is required'})
    
    try:
        print(f"🔍 Searching for: {query}")
        
        # Use the same session setup as our scraper
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # Try main domain first, then backup domain
        search_hosts = [
            'https://moviexp.movielinkbd.sbs',
            'https://movielinkbd.shop',
        ]
        
        response = None
        for host in search_hosts:
            try:
                search_url = f"{host}/search?q={quote(query)}"
                response = session.get(search_url, timeout=8)  # Reduced timeout for Vercel
                if response.status_code == 200:
                    break
            except Exception:
                continue
        
        if not response or response.status_code != 200:
            return jsonify({'error': f'Search failed on all domains'})
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find movie cards
        movie_cards = soup.find_all('div', class_='movie-card')
        movies = []
        
        for card in movie_cards:
            try:
                # Extract movie information
                title_link = card.find('a', class_='title')
                if not title_link:
                    continue
                
                title = title_link.get_text().strip()
                movie_url = title_link.get('href', '')
                
                # Extract poster image
                img = card.find('img')
                poster = img.get('data-src', '') if img else ''
                
                # Extract metadata
                quality_span = card.find('span', class_='quality')
                quality = quality_span.get_text().strip() if quality_span else 'Unknown'
                
                language_span = card.find('span', class_='language')
                language = language_span.get_text().strip() if language_span else 'Unknown'
                
                type_span = card.find('span', class_='type')
                movie_type = type_span.get_text().strip() if type_span else 'Movie'
                
                # Extract rating
                rating_badge = card.find('span', class_='rating-badge')
                rating = rating_badge.get_text().strip() if rating_badge else 'N/A'
                
                # Extract year from title (simple regex)
                import re
                year_match = re.search(r'\((\d{4})\)', title)
                year = year_match.group(1) if year_match else 'Unknown'
                
                # For now, we'll use the movie URL directly and let the watch page handle the flow
                # The watch page will need to be updated to handle movie pages
                watch_url = movie_url
                
                movies.append({
                    'title': title,
                    'year': year,
                    'type': movie_type,
                    'language': language,
                    'quality': quality,
                    'rating': rating,
                    'poster': poster,
                    'movie_url': movie_url,
                    'watch_url': watch_url
                })
                
            except Exception as e:
                print(f"⚠️ Error parsing movie card: {e}")
                continue
        
        print(f"✅ Found {len(movies)} movies for query: {query}")
        return jsonify({
            'query': query,
            'movies': movies,
            'total': len(movies)
        })
        
    except Exception as e:
        print(f"❌ Search error: {e}")
        return jsonify({'error': f'Search failed: {str(e)}'})

@app.route('/proxy/video')
def proxy_video():
    """Proxy endpoint to stream video content"""
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    print(f"🎬 Proxying video URL: {video_url}")
    
    try:
        # Set headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Range': request.headers.get('Range', '')  # Support range requests for video seeking
        }
        
        # Make request to the video URL with streaming
        response = requests.get(video_url, headers=headers, stream=True, timeout=30)
        
        print(f"📊 Video response status: {response.status_code}")
        print(f"📊 Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"📊 Content-Length: {response.headers.get('Content-Length', 'N/A')}")
        
        if response.status_code in [200, 206]:  # 206 for partial content (range requests)
            # Set appropriate headers for video streaming
            response_headers = {
                'Content-Type': response.headers.get('Content-Type', 'video/mp4'),
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'public, max-age=3600',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                'Access-Control-Allow-Headers': 'Range, Content-Type'
            }
            
            # Include Content-Length if available
            if 'Content-Length' in response.headers:
                response_headers['Content-Length'] = response.headers['Content-Length']
            
            # Include Content-Range for partial content
            if 'Content-Range' in response.headers:
                response_headers['Content-Range'] = response.headers['Content-Range']
            
            # Stream the video content
            def generate():
                try:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            yield chunk
                except Exception as e:
                    print(f"❌ Error in video streaming: {e}")
                    return
            
            return Response(generate(), headers=response_headers, status=response.status_code)
        else:
            print(f"❌ Video request failed: {response.status_code}")
            return jsonify({'error': f'Failed to fetch video: {response.status_code}'}), 400
            
    except Exception as e:
        print(f"❌ Video proxy error: {e}")
        return jsonify({'error': f'Error streaming video: {str(e)}'}), 500

if __name__ == '__main__':
    print("🚀 Starting MovieLinkBD API Server...")
    print("📱 Access the web interface at: http://localhost:5001")
    print("🔗 API endpoints:")
    print("   GET  /api/watch?url=YOUR_URL")
    print("   POST /watch")
    print("   GET  /api/health")
    print("   GET  /proxy/video?url=VIDEO_URL")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
