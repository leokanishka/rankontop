import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, HttpUrl, EmailStr
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import bcrypt

from security import create_access_token, get_current_user, User
from analyzers.seo_analyzer import run_seo_analysis
from analyzers.aieo_analyzer import get_keyword_insights
from analyzers.aso_analyzer import get_app_store_insights
from database import init_pool, close_pool, init_db, add_user, get_user_by_email, increment_analysis_count, save_analysis_result

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_pool()
    await init_db()

@app.on_event("shutdown")
async def on_shutdown():
    await close_pool()

class AnalysisRequest(BaseModel):
    url: Optional[HttpUrl] = None
    keyword: Optional[str] = None
    app_id: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(UserCreate): pass
class Token(BaseModel):
    access_token: str
    token_type: str

# Secure CORS: Allow specific origins (update with your Vercel URL)
origins = [
    "https://rankontop.vercel.app",
    "http://localhost:8000",  # For local testing
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "ok"}

@app.post("/register/")
async def register_user(user: UserCreate):
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    success = await add_user(user.email, hashed_password.decode('utf-8'))
    if not success:
        raise HTTPException(status_code=400, detail="Email already registered")
    return {"message": "User registered successfully"}

@app.post("/login/", response_model=Token)
async def login_user(user_login: UserLogin):
    db_user = await get_user_by_email(user_login.email)
    if not db_user or not bcrypt.checkpw(
        user_login.password.encode('utf-8'), 
        db_user['password_hash'].encode('utf-8')
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": user_login.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/analyze/")
async def analyze_url(request: AnalysisRequest, current_user: User = Depends(get_current_user)):
    db_user = await get_user_by_email(current_user.email)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check analysis limits
    if db_user.get('subscription_tier') == 'free' and db_user.get('analysis_count', 0) >= 10:
        raise HTTPException(status_code=403, detail="Analysis limit reached")

    # Validate inputs: Prevent mixing URL and App ID
    if request.url and request.app_id:
        raise HTTPException(status_code=422, detail="Provide either URL or App ID, not both")

    # Perform actual analysis
    final_response = {}
    target = None
    analysis_performed = False
    
    seo_score = 0
    aieo_score = 0
    aso_score = 0
    
    if request.url:
        target = str(request.url)
        # Run SEO analysis
        seo_results = run_seo_analysis(target)
        final_response["seo_analysis"] = seo_results
        
        # Calculate SEO sub-score
        pagespeed = seo_results.get("pagespeed", {}).get("performance_score", 0)
        on_page = seo_results.get("on_page_elements", {})
        on_page_completeness = 100
        if not on_page.get('title'): on_page_completeness -= 33.3
        if not on_page.get('meta_description'): on_page_completeness -= 33.3
        if not on_page.get('h1'): on_page_completeness -= 33.3
        # Estimated CTR - placeholder; in future, derive from AIEO top10
        estimated_ctr = 50  # Default; enhance later
        
        seo_score = (pagespeed * 0.4) + (on_page_completeness * 0.3) + (estimated_ctr * 0.3)
        
        # Run AIEO analysis if keyword provided
        if request.keyword:
            aieo_results = get_keyword_insights(request.keyword, target)
            final_response["aieo_analysis"] = aieo_results
            
            # Calculate AIEO sub-score
            difficulty_map = {"Very Low": 100, "Low": 75, "Medium": 50, "High": 25, "Very High": 0}
            difficulty_inverse = difficulty_map.get(aieo_results.get("estimated_difficulty", "Medium"), 50)
            top10_presence = 100 if aieo_results.get("domain_in_top_10") else 0
            ai_readability = 70  # Placeholder; add real calc with Flesch/spaCy later
            
            aieo_score = (difficulty_inverse * 0.4) + (top10_presence * 0.3) + (ai_readability * 0.3)
        
        analysis_performed = True
    
    if request.app_id:
        target = request.app_id
        aso_results = get_app_store_insights(request.app_id)
        final_response["aso_analysis"] = aso_results
        
        # Calculate ASO sub-score
        user_rating_norm = (aso_results.get("user_rating", 0) / 5) * 100
        sentiment_score = aso_results.get("review_sentiment_score", 0)
        
        aso_score = (user_rating_norm * 0.5) + (sentiment_score * 0.5)
        
        analysis_performed = True
    
    if not request.url and not request.app_id:
        raise HTTPException(status_code=422, detail="Provide URL or App ID")

    # Calculate overall score
    overall_score = round((seo_score * 0.4) + (aieo_score * 0.3) + (aso_score * 0.3), 1)
    final_response["overall_score"] = overall_score

    # Update user stats and save history
    if analysis_performed:
        await increment_analysis_count(current_user.email)
        await save_analysis_result(db_user['id'], target, final_response)

    return final_response