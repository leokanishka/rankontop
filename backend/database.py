import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import json

load_dotenv()

# Global variable for the connection pool
db_pool = None

def init_pool():
    """Initializes the PostgreSQL connection pool."""
    global db_pool
    if not db_pool:
        try:
            DATABASE_URL = os.getenv("DATABASE_URL")
            if not DATABASE_URL:
                raise ValueError("FATAL ERROR: DATABASE_URL environment variable not set.")
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=DATABASE_URL
            )
            print("Database connection pool created successfully.")
        except (psycopg2.Error, ValueError) as e:
            print(f"FATAL ERROR creating connection pool: {e}")
            # If the database can't be reached, the app can't run.
            exit(1)

def close_pool():
    """Closes the PostgreSQL connection pool."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        print("Database connection pool closed.")

def init_db():
    """Initializes the database tables if they don't exist."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            # Expanded users table for MVP Plus
            cur.execute('''
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
            cur.execute('''
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    target TEXT NOT NULL,
                    results_json JSONB NOT NULL
                );
            ''')
        conn.commit()
        print("Database tables verified/created successfully.")
    except psycopg2.Error as e:
        print(f"Database table creation error: {e}")
        conn.rollback()
    finally:
        db_pool.putconn(conn)

def add_user(email: str, password_hash: str) -> bool:
    """Adds a new user to the database using a connection from the pool."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (email, password_hash))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback() # Important for handling unique constraint violation
        return False
    except psycopg2.Error as e:
        print(f"Database error in add_user: {e}")
        conn.rollback()
        return False
    finally:
        db_pool.putconn(conn)

def get_user_by_email(email: str):
    """Retrieves a user's data as a dictionary."""
    conn = db_pool.getconn()
    user = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_data = cur.fetchone()
            if user_data:
                # Convert the tuple result into a dictionary
                columns = [desc[0] for desc in cur.description]
                user = dict(zip(columns, user_data))
    except psycopg2.Error as e:
        print(f"Database error in get_user_by_email: {e}")
    finally:
        db_pool.putconn(conn)
        return user

def increment_analysis_count(email: str):
    """Increments the analysis count for a given user."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET analysis_count = analysis_count + 1 WHERE email = %s", (email,))
        conn.commit()
    except psycopg2.Error as e:
        print(f"Database error in increment_analysis_count: {e}")
        conn.rollback()
    finally:
        db_pool.putconn(conn)

def save_analysis_result(user_id: int, target: str, results: dict):
    """Saves the result of an analysis to the history table."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            # Convert the Python dictionary to a JSON string for storing in JSONB
            results_string = json.dumps(results)
            cur.execute(
                "INSERT INTO analysis_history (user_id, target, results_json) VALUES (%s, %s, %s)",
                (user_id, target, results_string)
            )
        conn.commit()
    except psycopg2.Error as e:
        print(f"Error saving analysis history: {e}")
        conn.rollback()
    finally:
        db_pool.putconn(conn)