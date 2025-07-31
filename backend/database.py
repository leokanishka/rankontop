import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import json

load_dotenv()

db_pool = None

def init_pool():
    global db_pool
    if not db_pool:
        try:
            DATABASE_URL = os.getenv("DATABASE_URL")
            if not DATABASE_URL:
                raise ValueError("DATABASE_URL environment variable not set.")
            db_pool = psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
            print("Database connection pool created successfully.")
        except (psycopg2.Error, ValueError) as e:
            print(f"Error creating connection pool: {e}")
            # Exit if we can't connect to the DB, as the app is useless without it.
            exit(1)

def close_pool():
    global db_pool
    if db_pool:
        db_pool.closeall()
        print("Database connection pool closed.")

def init_db():
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
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
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (email, password_hash))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    except psycopg2.Error as e:
        conn.rollback()
        return False
    finally:
        db_pool.putconn(conn)

def get_user_by_email(email: str):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_data = cur.fetchone()
            if user_data:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, user_data))
        return None
    except psycopg2.Error:
        return None
    finally:
        db_pool.putconn(conn)

def increment_analysis_count(email: str):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET analysis_count = analysis_count + 1 WHERE email = %s", (email,))
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
    finally:
        db_pool.putconn(conn)

def save_analysis_result(user_id: int, target: str, results: dict):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            results_string = json.dumps(results)
            cur.execute(
                "INSERT INTO analysis_history (user_id, target, results_json) VALUES (%s, %s, %s)",
                (user_id, target, results_string)
            )
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
    finally:
        db_pool.putconn(conn)