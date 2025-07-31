import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PAGESPEED_API_KEY")
PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

def get_pagespeed_insights(url_to_analyze: str) -> dict:
    """
    Fetches Google PageSpeed Insights for a given URL.
    """
    params = {
        'url': url_to_analyze,
        'key': API_KEY,
        'strategy': 'MOBILE'
    }
    try:
        response = requests.get(PAGESPEED_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        performance_score = data.get('lighthouseResult', {}).get('categories', {}).get('performance', {}).get('score', 0) * 100
        return {
            "success": True,
            "performance_score": int(performance_score)
        }
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

def check_on_page_seo(url_to_analyze: str) -> dict:
    """
    Fetches the webpage and checks for basic on-page SEO elements,
    extracting their content as well.
    """
    results = {}
    try:
        headers = {'User-Agent': 'RankOnTopBot/1.0'}
        response = requests.get(url_to_analyze, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract Title Tag content
        title_tag = soup.find('title')
        results['title'] = title_tag.string.strip() if title_tag and title_tag.string else None
        
        # Extract Meta Description content
        meta_description = soup.find('meta', attrs={'name': 'description'})
        results['meta_description'] = meta_description.get('content').strip() if meta_description and meta_description.get('content') else None
        
        # Extract H1 Tag content
        h1_tag = soup.find('h1')
        results['h1'] = h1_tag.string.strip() if h1_tag and h1_tag.string else None
        
        return results
        
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

def run_seo_analysis(url: str) -> dict:
    """
    A master function to run all SEO analysis tasks.
    """
    pagespeed = get_pagespeed_insights(url)
    on_page = check_on_page_seo(url)
    
    return {
        "pagespeed": pagespeed,
        "on_page_elements": on_page
    }