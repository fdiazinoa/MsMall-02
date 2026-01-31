
import requests
import os
from dotenv import load_dotenv

load_dotenv()

URL = "http://localhost:8000/api/v1/audit/logs"
HEADERS = {
    "X-API-Key": "demo-key-123",
    "Content-Type": "application/json"
}

try:
    print(f"Testing DELETE {URL}...")
    res = requests.delete(URL, headers=HEADERS)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.text}")
except Exception as e:
    print(f"Request failed: {e}")
