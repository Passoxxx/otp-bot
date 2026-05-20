import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

DATABASE_FILE = "users.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscription_end TEXT,
                subscription_type TEXT,
                calls_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS pending_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                subscription_type TEXT,
                crypto TEXT,
                payment_id TEXT,
                tx_hash TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT
            )
        ''')
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS call_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                from_country TEXT,
                to_number TEXT,
                message TEXT,
                audio_file TEXT,
                recording_file TEXT,
                duration INTEGER,
                cost REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS redeem_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                created_by INTEGER,
                used_by INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                used_at TEXT DEFAULT NULL
            )
        ''')

def get_user(user_id):
    with get_db() as db:
        user = db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        return dict(user) if user else None

def create_user(user_id, username, first_name):
    with get_db() as db:
        db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))

def has_active_subscription(user_id):
    user = get_user(user_id)
    if not user or not user['subscription_end']:
        return False
    subscription_end = datetime.fromisoformat(user['subscription_end'])
    return subscription_end > datetime.now()

def get_subscription_days_left(user_id):
    user = get_user(user_id)
    if not user or not user['subscription_end']:
        return 0
    subscription_end = datetime.fromisoformat(user['subscription_end'])
    days_left = (subscription_end - datetime.now()).days
    return max(0, days_left)

def activate_subscription(user_id, subscription_type, days):
    end_date = datetime.now() + timedelta(days=days)
    with get_db() as db:
        db.execute('''
            UPDATE users 
            SET subscription_end = ?, subscription_type = ?
            WHERE user_id = ?
        ''', (end_date.isoformat(), subscription_type, user_id))

def add_pending_payment(user_id, amount, subscription_type, crypto, payment_id):
    with get_db() as db:
        db.execute('''
            INSERT INTO pending_payments (user_id, amount, subscription_type, crypto, payment_id, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, amount, subscription_type, crypto, payment_id))

def get_pending_payment(user_id, payment_id):
    with get_db() as db:
        pending = db.execute('''
            SELECT * FROM pending_payments 
            WHERE user_id = ? AND payment_id = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, payment_id)).fetchone()
        return dict(pending) if pending else None

def mark_payment_completed(payment_id, tx_hash):
    with get_db() as db:
        db.execute('''
            UPDATE pending_payments 
            SET status = 'confirmed', tx_hash = ?, confirmed_at = CURRENT_TIMESTAMP
            WHERE payment_id = ?
        ''', (tx_hash, payment_id))

def add_call_to_history(user_id, from_country, to_number, message, audio_file, recording_file, duration, cost):
    with get_db() as db:
        db.execute('''
            INSERT INTO call_history (user_id, from_country, to_number, message, audio_file, recording_file, duration, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, from_country, to_number, message, audio_file, recording_file, duration, cost))

def get_call_history(user_id, limit=5):
    with get_db() as db:
        history = db.execute('''
            SELECT * FROM call_history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        return [dict(h) for h in history]

# ============================================
# FUNZIONI PER REDEEM CODICI
# ============================================

def generate_redeem_code() -> str:
    import random
    import string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    
    with get_db() as db:
        db.execute('''
            INSERT INTO redeem_codes (code, created_by)
            VALUES (?, ?)
        ''', (code, 1))
    
    return code

def redeem_code(user_id: int, code: str) -> bool:
    code = code.upper().strip()
    
    with get_db() as db:
        result = db.execute('''
            SELECT * FROM redeem_codes 
            WHERE code = ? AND used_by IS NULL
        ''', (code,)).fetchone()
        
        if not result:
            return False
        
        activate_subscription(user_id, "lifetime", 3650)
        
        db.execute('''
            UPDATE redeem_codes 
            SET used_by = ?, used_at = CURRENT_TIMESTAMP
            WHERE code = ?
        ''', (user_id, code))
        
        return True

def list_redeem_codes() -> list:
    with get_db() as db:
        codes = db.execute('''
            SELECT code, used_by, created_at, used_at 
            FROM redeem_codes 
            ORDER BY created_at DESC
        ''').fetchall()
        return [dict(c) for c in codes]