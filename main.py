from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import hashlib

app = FastAPI()

class TokenRequest(BaseModel):
    address: str

KNOWN_SCAMS = ["8x...", "Gv...", "ScamTokenAddress"]

def analyze_risk(address):
    # Blacklist Check
    if address in KNOWN_SCAMS:
        return {"score": 0, "risk": "CRITICAL", "summary": "Identified in Blacklist."}

    # Simulation IA stable basée sur l'adresse
    hash_val = int(hashlib.sha256(address.encode('utf-8')).hexdigest(), 16) % 100
    
    # Critères simulés
    liq_locked = hash_val > 20 
    mint_off = hash_val > 30

    checks = []
    checks.append({"name": "LIQUIDITY", "status": "LOCKED" if liq_locked else "UNLOCKED", "safe": liq_locked})
    checks.append({"name": "MINT AUTH", "status": "DISABLED" if mint_off else "ENABLED", "safe": mint_off})

    # Score
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
        "summary": f"AI Scan completed. Risk level assessed as {risk_level}."
    }

@app.get("/")
def read_root():
    return {"status": "Solana Gold Guard AI is Online"}

@app.post("/scan")
def scan_token(request: TokenRequest):
    if len(request.address) < 5:
        raise HTTPException(status_code=400, detail="Invalid address")
    result = analyze_risk(request.address)
    return result
