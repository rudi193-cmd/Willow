"""Web search tool using DuckDuckGo HTML search"""
import requests
from urllib.parse import quote_plus
import re
from html import unescape

def search(query, max_results=5):
    """Search the web using DuckDuckGo HTML search."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        html = response.text
        
        results = []
        
        # Parse using improved regex
        # Look for result divs
        result_blocks = re.findall(r'<div class="result[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
        
        for block in result_blocks[:max_results]:
            # Extract title and URL
            title_match = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', block)
            # Extract snippet
            snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>([^<]+)</a>', block)
            
            if title_match:
                url_raw = title_match.group(1)
                title_raw = title_match.group(2)
                snippet_raw = snippet_match.group(1) if snippet_match else ""
                
                # Clean up
                title = unescape(re.sub(r'\s+', ' ', title_raw).strip())
                url_clean = unescape(url_raw.strip())
                snippet = unescape(re.sub(r'\s+', ' ', snippet_raw).strip())
                
                results.append({
                    'title': title[:100],
                    'url': url_clean,
                    'snippet': snippet[:200] if snippet else "No description available"
                })
        
        return {
            'success': True,
            'result': {
                'query': query,
                'results': results,
                'count': len(results)
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f"Search failed: {str(e)}"
        }
