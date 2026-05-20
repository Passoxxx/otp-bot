import hashlib
import time
import requests
from database import get_db

def get_sol_price():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
        data = response.json()
        return data['solana']['usd']
    except:
        return 150.0

def get_ltc_price():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd")
        data = response.json()
        return data['litecoin']['usd']
    except:
        return 80.0

def usd_to_sol(amount_usd):
    price = get_sol_price()
    return round(amount_usd / price, 6)

def usd_to_ltc(amount_usd):
    price = get_ltc_price()
    return round(amount_usd / price, 6)

def generate_payment_id(user_id, subscription_type):
    timestamp = int(time.time())
    raw = f"{user_id}_{subscription_type}_{timestamp}"
    return hashlib.md5(raw.encode()).hexdigest()[:8].upper()