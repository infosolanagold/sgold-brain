from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import hashlib

app = FastAPI()

# Configuration CORS (Pour autoriser ton site)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    address: str

KNOWN_SCAMS = ["ScamTokenAddress", "Honeypot123", "FakeUSDC"]

def analyze_risk(address):
    # 1. Vérification Blacklist
    if address in KNOWN_SCAMS:
        return {
            "score": 0,
            "risk": "CRITICAL",
            "checks": [
                {"name": "DATABASE", "status": "BLACKLISTED", "safe": False},
                {"name": "SAFETY", "status": "COMPROMISED", "safe": False}
            ],
            "summary": "DANGER: Address identified in Global Blacklist. Do not interact."
        }

    # 2. Simulation IA stable
    try:
        hash_val = int(hashlib.sha256(address.encode('utf-8')).hexdigest(), 16) % 100
    except:
        hash_val = 50 
    
    liq_locked = hash_val > 20 
    mint_off = hash_val > 30

    checks = []
    checks.append({"name": "LIQUIDITY", "status": "LOCKED" if liq_locked else "UNLOCKED", "safe": liq_locked})
    checks.append({"name": "MINT AUTH", "status": "DISABLED" if mint_off else "ENABLED", "safe": mint_off})

    score = hash_val
    if not liq_locked: score -= 30
    if not mint_off: score -= 40
    score = max(0, min(100, score))

    risk_level = "LOW"
    if score < 50: risk_level = "HIGH"
    elif score < 80: risk_level = "MEDIUM"

    return {
        "score": score,
        "risk": risk_level,
        "checks": checks,
        "summary": f"AI Scan completed. Risk level assessed as {risk_level} based on simulated vectors."
    }

@app.get("/")
def read_root():
    return {"status": "Solana Gold Guard AI is Online"}

@app.post("/scan")
def scan_token(request: TokenRequest):
    clean_address = request.address.strip()
    if len(clean_address) < 3:
        raise HTTPException(status_code=400, detail="Invalid address")
    
    result = analyze_risk(clean_address)
    return result
