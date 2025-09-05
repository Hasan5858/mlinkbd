#!/usr/bin/env python3
"""
Test MovieLinkBD API
"""

import requests
import time
import json

def test_api():
    """Test the MovieLinkBD API"""
    base_url = "http://localhost:5001"
    
    print("🧪 Testing MovieLinkBD API...")
    print("=" * 50)
    
    # Test 1: Health check
    print("1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return
    
    # Test 2: Home page
    print("\n2. Testing home page...")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print("✅ Home page accessible")
        else:
            print(f"❌ Home page failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Home page error: {e}")
    
    # Test 3: API endpoint with sample URL
    print("\n3. Testing API endpoint...")
    test_url = "https://mlink82.movielinkbd.sbs/watch/9lMVJKddYFC_Qb5WKn07glFItFKzYVHZdHNeNObbqWFNJzbjJhvQBad2kE37LXew6QS-VLAkFFccLEzze10qyHgOPc8AUg6cp9rx--7GWQrJz4m1NDa4l6_ZoTXC2rGu43q0L64eL8CpXy5-E6G79vG1ZjVXtuyu_f3o8qVP8BdH-5Kh-X9fblgO4DKukRdU"
    
    try:
        response = requests.get(f"{base_url}/api/watch", params={'url': test_url}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ API endpoint working")
                video_info = data.get('video_info', {})
                print(f"   Title: {video_info.get('title', 'N/A')[:50]}...")
                print(f"   Video URL: {'Found' if video_info.get('video_url') else 'Not found'}")
                print(f"   Download URL: {'Found' if video_info.get('download_url') else 'Not found'}")
                print(f"   Player Type: {video_info.get('player_type', 'N/A')}")
            else:
                print(f"❌ API returned error: {data.get('error', 'Unknown error')}")
        else:
            print(f"❌ API request failed: {response.status_code}")
    except Exception as e:
        print(f"❌ API test error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 API testing completed!")
    print(f"🌐 Web interface: {base_url}")
    print(f"🔗 API endpoint: {base_url}/api/watch?url=YOUR_URL")

if __name__ == "__main__":
    test_api()
