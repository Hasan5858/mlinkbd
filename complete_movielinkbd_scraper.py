#!/usr/bin/env python3
"""
Complete MovieLinkBD Scraper
Successfully extracts all video information including video URL and download URL
"""

import requests
import json
import re
from typing import Dict, Any, List
from bs4 import BeautifulSoup


class CompleteMovieLinkBDScraper:
    """Complete scraper that extracts all video information"""
    
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
    
    def extract_ad_info(self, html_content: str) -> Dict[str, Any]:
        """Extract advertisement and redirect information"""
        ad_info = {
            'telegram_url': '',
            'facebook_url': '',
            'jaya9_urls': [],
            'extra_urls': [],
            'adult_urls': [],
            'social_cooldown': 0,
            'page_cooldown': 0
        }
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract from JavaScript variables
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string:
                    script_content = script.string
                    
                    # Extract Telegram URL
                    tg_match = re.search(r'var TELEGRAM = ["\']([^"\']+)["\']', script_content)
                    if tg_match:
                        ad_info['telegram_url'] = tg_match.group(1).replace('\\/', '/')
                    
                    # Extract Facebook URL
                    fb_match = re.search(r'var FACEBOOK = ["\']([^"\']+)["\']', script_content)
                    if fb_match:
                        ad_info['facebook_url'] = fb_match.group(1).replace('\\/', '/')
                    
                    # Extract cooldown values
                    social_cd_match = re.search(r'var SOCIAL_COOLDOWN_H = (\d+)', script_content)
                    if social_cd_match:
                        ad_info['social_cooldown'] = int(social_cd_match.group(1))
                    
                    page_cd_match = re.search(r'var PAGE_COOLDOWN_MIN = (\d+)', script_content)
                    if page_cd_match:
                        ad_info['page_cooldown'] = int(page_cd_match.group(1))
                    
                    # Extract JAYA9 URLs
                    jaya9_match = re.search(r'var JAYA9 = \[([^\]]+)\]', script_content)
                    if jaya9_match:
                        urls = re.findall(r'["\']([^"\']+)["\']', jaya9_match.group(1))
                        ad_info['jaya9_urls'] = [url.replace('\\/', '/') for url in urls]
                    
                    # Extract EXTRA URLs
                    extra_match = re.search(r'var EXTRA = \[([^\]]+)\]', script_content)
                    if extra_match:
                        urls = re.findall(r'["\']([^"\']+)["\']', extra_match.group(1))
                        ad_info['extra_urls'] = [url.replace('\\/', '/') for url in urls]
                    
                    # Extract ADULT URLs
                    adult_match = re.search(r'var ADULT = \[([^\]]+)\]', script_content)
                    if adult_match:
                        urls = re.findall(r'["\']([^"\']+)["\']', adult_match.group(1))
                        ad_info['adult_urls'] = [url.replace('\\/', '/') for url in urls]
        
        except Exception as e:
            print(f"Error extracting ad info: {e}")
        
        return ad_info
    
    def scrape_video_page(self, url: str) -> Dict[str, Any]:
        """Scrape the video page and extract all information"""
        results = {
            'success': False,
            'url': url,
            'html_content': '',
            'video_info': {},
            'ad_info': {},
            'page_analysis': {},
            'error': ''
        }
        
        try:
            print(f"🌐 Scraping MovieLinkBD URL...")
            print(f"📋 URL: {url}")
            
            # Make request
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ Successfully got response!")
                print(f"📊 Response Details:")
                print(f"   Status Code: {response.status_code}")
                print(f"   Content Length: {len(response.content)} bytes")
                print(f"   Content Type: {response.headers.get('content-type', 'unknown')}")
                print(f"   Content Encoding: {response.headers.get('content-encoding', 'none')}")
                
                # Get the HTML content (requests handles gzip automatically)
                html_content = response.text
                results['html_content'] = html_content
                
                print(f"📄 HTML Content Length: {len(html_content)} characters")
                
                # Check if we got proper HTML
                if html_content.startswith('<!DOCTYPE html') or html_content.startswith('<html') or '<script>' in html_content:
                    print("✅ Got proper HTML content!")
                    results['success'] = True
                    
                    # Extract video information
                    print("🔍 Extracting video information...")
                    video_info = self.extract_video_info(html_content)
                    results['video_info'] = video_info
                    
                    # Extract advertisement information
                    print("🔍 Extracting advertisement information...")
                    ad_info = self.extract_ad_info(html_content)
                    results['ad_info'] = ad_info
                    
                    # Basic page analysis
                    results['page_analysis'] = {
                        'has_video_player': 'jwplayer' in html_content.lower() or 'video' in html_content.lower(),
                        'has_ads': 'TELEGRAM' in html_content or 'FACEBOOK' in html_content,
                        'has_download': '/file/' in html_content,
                        'content_type': 'video_page' if video_info['video_url'] else 'unknown'
                    }
                    
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


def main():
    """Main function"""
    # Use the correct URL format from the user's example
    target_url = "https://mlink82.movielinkbd.sbs/watch/9lMVJKddYFC_Qb5WKn07glFItFKzYVHZdHNeNObbqWFNJzbjJhvQBad2kE37LXew6QS-VLAkFFccLEzze10qyHgOPc8AUg6cp9rx--7GWQrJz4m1NDa4l6_ZoTXC2rGu43q0L64eL8CpXy5-E6G79vG1ZjVXtuyu_f3o8qVP8BdH-5Kh-X9fblgO4DKukRdU"
    
    scraper = CompleteMovieLinkBDScraper()
    results = scraper.scrape_video_page(target_url)
    
    print("\n" + "="*80)
    print("COMPLETE MOVIELINKBD SCRAPING RESULTS")
    print("="*80)
    
    if results['success']:
        print("✅ Successfully scraped video page!")
        
        # Display video information
        video_info = results['video_info']
        print(f"\n🎬 VIDEO INFORMATION:")
        print(f"   Title: {video_info['title']}")
        print(f"   Video URL: {video_info['video_url']}")
        print(f"   Download URL: {video_info['download_url']}")
        print(f"   Popunder URL: {video_info['popunder_url']}")
        print(f"   Stable ID: {video_info['stable_id']}")
        print(f"   Player Type: {video_info['player_type']}")
        print(f"   File Info: {video_info['file_info']}")
        print(f"   Quality Options: {', '.join(video_info['quality_options'])}")
        
        # Display advertisement information
        ad_info = results['ad_info']
        print(f"\n📢 ADVERTISEMENT INFORMATION:")
        print(f"   Telegram URL: {ad_info['telegram_url']}")
        print(f"   Facebook URL: {ad_info['facebook_url']}")
        print(f"   Social Cooldown: {ad_info['social_cooldown']} hours")
        print(f"   Page Cooldown: {ad_info['page_cooldown']} minutes")
        print(f"   JAYA9 URLs: {len(ad_info['jaya9_urls'])} found")
        print(f"   Extra URLs: {len(ad_info['extra_urls'])} found")
        print(f"   Adult URLs: {len(ad_info['adult_urls'])} found")
        
        # Display page analysis
        page_analysis = results['page_analysis']
        print(f"\n📊 PAGE ANALYSIS:")
        print(f"   Has Video Player: {page_analysis['has_video_player']}")
        print(f"   Has Ads: {page_analysis['has_ads']}")
        print(f"   Has Download: {page_analysis['has_download']}")
        print(f"   Content Type: {page_analysis['content_type']}")
        
        # Save results
        try:
            with open('complete_movielinkbd_content.html', 'w', encoding='utf-8') as f:
                f.write(results['html_content'])
            print("💾 HTML content saved to: complete_movielinkbd_content.html")
            
            with open('complete_movielinkbd_analysis.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'video_info': video_info,
                    'ad_info': ad_info,
                    'page_analysis': page_analysis
                }, f, indent=2, ensure_ascii=False)
            print("💾 Analysis saved to: complete_movielinkbd_analysis.json")
            
        except Exception as e:
            print(f"❌ Failed to save files: {e}")
    
    else:
        print(f"❌ Failed to scrape content: {results['error']}")


if __name__ == "__main__":
    main()
