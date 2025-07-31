import os
from serpapi import GoogleSearch
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

API_KEY = os.getenv("SERPAPI_API_KEY")

def get_keyword_insights(keyword: str, url: str) -> dict:
    """
    Uses SerpAPI to perform an "allintitle" analysis for a more
    accurate keyword difficulty score.
    """
    if not API_KEY:
        return {"success": False, "error": "SerpAPI key not found."}

    # Handle multiple keywords by analyzing the first one
    first_keyword = keyword.split(',')[0].strip()
    
    # Perform an "allintitle" search
    allintitle_query = f"allintitle:{first_keyword}"

    params = {
        "engine": "google",
        "q": allintitle_query,
        "api_key": API_KEY
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        
        competing_pages = results.get("search_information", {}).get("total_results", 0)
        
        # A more accurate difficulty score based on direct competition
        if competing_pages > 100000:
            difficulty = "Very High"
        elif competing_pages > 20000:
            difficulty = "High"
        elif competing_pages > 5000:
            difficulty = "Medium"
        elif competing_pages > 1000:
            difficulty = "Low"
        else:
            difficulty = "Very Low"

        # --- Check for domain in top 10 of a REGULAR search ---
        regular_search_params = {"engine": "google", "q": first_keyword, "api_key": API_KEY}
        regular_search = GoogleSearch(regular_search_params)
        regular_results = regular_search.get_dict()

        is_in_top_10 = False
        user_domain = urlparse(url).netloc.replace('www.', '')
        organic_results = regular_results.get("organic_results", [])
        
        for result in organic_results[:10]:
            if user_domain in result.get("link", ""):
                is_in_top_10 = True
                break

        return {
            "success": True,
            "keyword_analyzed": first_keyword,
            "competing_pages": f"{competing_pages:,}", # Format with commas
            "estimated_difficulty": difficulty,
            "domain_in_top_10": is_in_top_10
        }

    except Exception as e:
        return {"success": False, "error": str(e)}