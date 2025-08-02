import os
import asyncpg
from dotenv import load_dotenv
import json
import sys

# Load environment variables
load_dotenv()

# Global variable for the connection pool
db_pool = None

async def init_pool():
    """Initializes the PostgreSQL connection pool."""
    global db_pool
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            raise ValueError("FATAL ERROR: DATABASE_URL environment variable not set.")
        
        # Clean URL if it contains sslmode parameter
        if "?sslmode=require" in DATABASE_URL:
            DATABASE_URL = DATABASE_URL.replace("?sslmode=require", "")
        
        # Create connection pool with SSL
        db_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=10,
            ssl=True  # Enable SSL; Render handles 'require' via this
        )
        print("✅ Database connection pool created successfully")
    except Exception as e:
        print(f"❌ FATAL ERROR creating connection pool: {e}")
        sys.exit(1)

async def close_pool():
    """Closes the PostgreSQL connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("✅ Database connection pool closed")

async def init_db():
    """Initializes the database tables if they don't exist."""
    async with db_pool.acquire() as conn:
        try:
            # Expanded users table for MVP Plus
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    analysis_count INTEGER DEFAULT 0 NOT NULL,
                    subscription_tier TEXT DEFAULT 'free' NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            # New table for analysis history
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    target TEXT NOT NULL,
                    results_json JSONB NOT NULL
                );
            ''')
            print("✅ Database tables verified/created")
        except Exception as e:
            print(f"❌ Database table creation error: {e}")

async def add_user(email: str, password_hash: str) -> bool:
    """Adds a new user to the database using a connection from the pool."""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO users (email, password_hash) VALUES ($1, $2)",
                email, password_hash
            )
            return True
        except asyncpg.UniqueViolationError:
            return False
        except Exception as e:
            print(f"❌ Database error in add_user: {e}")
            return False

async def get_user_by_email(email: str):
    """Retrieves a user's data as a dictionary."""
    async with db_pool.acquire() as conn:
        try:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1", 
                email
            )
        except Exception as e:
            print(f"❌ Database error in get_user_by_email: {e}")
            return None

async def increment_analysis_count(email: str):
    """Increments the analysis count for a given user."""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "UPDATE users SET analysis_count = analysis_count + 1 WHERE email = $1",
                email
            )
        except Exception as e:
            print(f"❌ Database error in increment_analysis_count: {e}")

async def save_analysis_result(user_id: int, target: str, results: dict):
    """Saves the result of an analysis to the history table."""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO analysis_history (user_id, target, results_json) VALUES ($1, $2, $3)",
                user_id, target, json.dumps(results)
            )
        except Exception as e:
            print(f"❌ Error saving analysis history: {e}")