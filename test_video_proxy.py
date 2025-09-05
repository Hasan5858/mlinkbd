#!/usr/bin/env python3
"""
Test the video proxy functionality
"""

import requests
import time

def test_video_proxy():
    """Test the video proxy endpoint"""
    base_url = "http://localhost:5001"
    
    print("🧪 Testing Video Proxy...")
    print("=" * 50)
    
    # Test video proxy endpoint
    test_video_url = "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4"
    
    try:
        print(f"Testing proxy with sample video URL...")
        response = requests.get(f"{base_url}/proxy/video", params={'url': test_video_url}, timeout=10)
        
        if response.status_code == 200:
            print("✅ Video proxy working!")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"   Content-Length: {response.headers.get('Content-Length', 'N/A')}")
        else:
            print(f"❌ Video proxy failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Video proxy error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Video proxy test completed!")

if __name__ == "__main__":
    test_video_proxy()
