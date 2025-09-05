#!/usr/bin/env python3
"""
Test script for Cloudflare Worker video proxy
"""

import requests
import urllib.parse

def test_cloudflare_worker():
    """Test the Cloudflare Worker with a real video URL"""
    
    # Get a real video URL from the API
    print("🔍 Getting video URL from API...")
    try:
        response = requests.get("http://localhost:5001/api/scrape/755898")
        data = response.json()
        
        if data.get('success') and data.get('video_info', {}).get('video_url'):
            video_url = data['video_info']['video_url']
            print(f"✅ Got video URL: {video_url[:50]}...")
            
            # Test Cloudflare Worker
            cloudflare_url = "https://mlinkbd-proxy.hasansarker58.workers.dev/"
            encoded_url = urllib.parse.quote(video_url, safe='')
            proxy_url = f"{cloudflare_url}?url={encoded_url}"
            
            print(f"🌐 Testing Cloudflare Worker...")
            print(f"📡 Proxy URL: {proxy_url[:100]}...")
            
            # Test with HEAD request
            try:
                head_response = requests.head(proxy_url, timeout=10)
                print(f"📊 HEAD Response: {head_response.status_code}")
                print(f"📋 Headers: {dict(head_response.headers)}")
                
                if head_response.status_code in [200, 206, 302]:
                    print("✅ Cloudflare Worker is working!")
                else:
                    print(f"⚠️ Unexpected status code: {head_response.status_code}")
                    
            except Exception as e:
                print(f"❌ Error testing Cloudflare Worker: {e}")
                
        else:
            print("❌ Failed to get video URL from API")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_cloudflare_worker()
