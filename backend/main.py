from fastapi import FastAPI, HTTPException, Depends, Response, status
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
def on_startup():
    init_pool()
    init_db()

@app.on_event("shutdown")
def on_shutdown():
    close_pool()

# --- Pydantic Models ---
class AnalysisRequest(BaseModel):
    url: Optional[HttpUrl] = None
    keyword: Optional[str] = None
    app_id: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(UserCreate):
    pass
    
class Token(BaseModel):
    access_token: str
    token_type: str

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
@app.get("/", status_code=status.HTTP_200_OK)
def health_check():
    """
    A simple endpoint that Render can use to confirm the service is live.
    """
    return {"status": "ok"}

@app.post("/register/")
def register_user(user: UserCreate):
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    success = add_user(user.email, hashed_password.decode('utf-8'))
    if not success:
        raise HTTPException(status_code=400, detail="Email already registered.")
    return {"message": "User registered successfully."}

@app.post("/login/", response_model=Token)
def login_user(user_login: UserLogin):
    db_user = get_user_by_email(user_login.email)
    if not db_user or not bcrypt.checkpw(user_login.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    access_token = create_access_token(data={"sub": user_login.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/analyze/")
def analyze_url(request: AnalysisRequest, current_user: User = Depends(get_current_user)):
    db_user = get_user_by_email(current_user.email)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    if db_user['subscription_tier'] == 'free' and db_user['analysis_count'] >= 10:
        raise HTTPException(status_code=403, detail="Free analysis limit reached. Please upgrade.")

    final_response = {"status": "complete"}
    
    analysis_performed = False
    if request.url:
        seo_results = run_seo_analysis(str(request.url))
        final_response["seo_analysis"] = seo_results
        
        on_page_checks = seo_results.get("on_page_elements", {})
        if on_page_checks and not on_page_checks.get("error"):
            passed_checks = sum(1 for check in on_page_checks.values() if check)
            total_checks = len(on_page_checks)
            on_page_score = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
        else:
            on_page_score = 0

        pagespeed_score = seo_results.get("pagespeed", {}).get("performance_score", 0)

        aeo_geo_score = 0
        if request.keyword:
            keyword_results = get_keyword_insights(request.keyword, str(request.url))
            final_response["aieo_analysis"] = keyword_results
            if keyword_results.get("success"):
                aeo_geo_score += 50 if keyword_results.get("domain_in_top_10") else 0
                difficulty = keyword_results.get("estimated_difficulty", "")
                if difficulty == "Low": aeo_geo_score += 50
                elif difficulty == "Medium": aeo_geo_score += 25
        
        overall_score = (pagespeed_score * 0.5) + (on_page_score * 0.3) + (aeo_geo_score * 0.2)
        final_response["overall_score"] = int(overall_score)
        
        save_analysis_result(db_user['id'], str(request.url), final_response)
        analysis_performed = True
    
    if request.app_id:
        aso_results = get_app_store_insights(request.app_id)
        final_response["aso_analysis"] = aso_results
        save_analysis_result(db_user['id'], request.app_id, final_response)
        analysis_performed = True
    
    if analysis_performed:
        increment_analysis_count(current_user.email)

    if not request.url and not request.app_id:
        return {"status": "error", "message": "Please provide a URL or an App ID."}

    return final_response