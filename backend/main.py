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

class UserLogin(UserCreate): pass
class Token(BaseModel):
    access_token: str
    token_type: str

origins = ["*"]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- API Endpoints ---
@app.get("/", status_code=status.HTTP_200_OK)
def health_check():
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

    if db_user.get('subscription_tier') == 'free' and db_user.get('analysis_count', 0) >= 10:
        raise HTTPException(status_code=403, detail="Free analysis limit reached. Please upgrade.")

    final_response = {"status": "complete"}
    analysis_performed = False
    
    target = None
    if request.url:
        target = str(request.url)
        final_response["seo_analysis"] = run_seo_analysis(target)
        if request.keyword:
            final_response["aieo_analysis"] = get_keyword_insights(request.keyword, target)
        analysis_performed = True
    
    if request.app_id:
        target = request.app_id
        final_response["aso_analysis"] = get_app_store_insights(target)
        analysis_performed = True
    
    if analysis_performed and db_user:
        save_analysis_result(db_user['id'], target, final_response)
        increment_analysis_count(current_user.email)

    if not request.url and not request.app_id:
        raise HTTPException(status_code=422, detail="Please provide a URL or an App ID.")

    return final_response