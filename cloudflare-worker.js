/**
 * Cloudflare Worker for Video Proxying
 * Handles video streaming from MovieLinkBD sources
 * Compatible with Vercel deployment
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // CORS headers for all responses
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, HEAD, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Range, User-Agent, Referer',
      'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
    };

    // Handle preflight requests
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 200,
        headers: corsHeaders,
      });
    }

    // Allow GET and HEAD requests for video proxying
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method not allowed', {
        status: 405,
        headers: corsHeaders,
      });
    }

    // Extract video URL from query parameter
    const videoUrl = url.searchParams.get('url');
    if (!videoUrl) {
      return new Response('Missing video URL parameter', {
        status: 400,
        headers: corsHeaders,
      });
    }

    try {
      // Decode the video URL
      const decodedUrl = decodeURIComponent(videoUrl);
      
      // Validate URL
      let targetUrl;
      try {
        targetUrl = new URL(decodedUrl);
      } catch (e) {
        return new Response('Invalid video URL', {
          status: 400,
          headers: corsHeaders,
        });
      }

      // Only allow MovieLinkBD domains for security
      const allowedDomains = [
        'play.movielinkbd.mom',
        'playk8.movielinkbd.sbs',
        'moviexp.movielinkbd.sbs',
        'mlinkv2.movielinkbd.sbs',
        'mlink82.movielinkbd.sbs',
        'movielinkbd.shop',
        'movielinkbd.one'
      ];
      
      if (!allowedDomains.includes(targetUrl.hostname)) {
        return new Response('Domain not allowed', {
          status: 403,
          headers: corsHeaders,
        });
      }

      // Prepare headers for the upstream request
      const upstreamHeaders = new Headers();
      
      // Copy important headers from the original request
      const headersToForward = [
        'Range',
        'User-Agent',
        'Accept',
        'Accept-Language',
        'Accept-Encoding',
        'Referer',
        'Cache-Control'
      ];
      
      headersToForward.forEach(header => {
        const value = request.headers.get(header);
        if (value) {
          upstreamHeaders.set(header, value);
        }
      });

      // Set default User-Agent if not present
      if (!upstreamHeaders.get('User-Agent')) {
        upstreamHeaders.set('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36');
      }

      // Set Referer to prevent blocking
      if (!upstreamHeaders.get('Referer')) {
        upstreamHeaders.set('Referer', 'https://movielinkbd.one/');
      }

      // Make the request to the video source
      const upstreamRequest = new Request(decodedUrl, {
        method: request.method, // Forward the original method (GET or HEAD)
        headers: upstreamHeaders,
      });

      // Fetch the video with streaming
      const response = await fetch(upstreamRequest);
      
      if (!response.ok) {
        return new Response(`Upstream error: ${response.status}`, {
          status: response.status,
          headers: corsHeaders,
        });
      }

      // Prepare response headers
      const responseHeaders = new Headers(corsHeaders);
      
      // Copy important headers from upstream response
      const headersToCopy = [
        'Content-Type',
        'Content-Length',
        'Content-Range',
        'Accept-Ranges',
        'Cache-Control',
        'ETag',
        'Last-Modified',
        'Expires'
      ];
      
      headersToCopy.forEach(header => {
        const value = response.headers.get(header);
        if (value) {
          responseHeaders.set(header, value);
        }
      });

      // Set additional headers for better video streaming
      responseHeaders.set('X-Content-Type-Options', 'nosniff');
      responseHeaders.set('X-Frame-Options', 'SAMEORIGIN');
      
      // Handle range requests for video seeking
      if (request.headers.get('Range')) {
        responseHeaders.set('Accept-Ranges', 'bytes');
      }

      // Return the streaming response
      // For HEAD requests, don't include the body
      const responseBody = request.method === 'HEAD' ? null : response.body;
      
      return new Response(responseBody, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });

    } catch (error) {
      console.error('Worker error:', error);
      
      return new Response(`Proxy error: ${error.message}`, {
        status: 500,
        headers: corsHeaders,
      });
    }
  },
};
