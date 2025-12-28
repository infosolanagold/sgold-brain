from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests # L'outil pour parler à la Blockchain

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    address: str

# URL Publique de Solana (Pour commencer)
# Note: Pour une version Pro, on utilisera une clé Helius ici plus tard.
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

KNOWN_SCAMS = ["ScamTokenAddress", "Honeypot123"]

def get_onchain_data(token_address):
    """
    Interroge la VRAIE Blockchain Solana.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            token_address,
            {"encoding": "jsonParsed"}
        ]
    }
    
    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, timeout=5)
        data = response.json()
        
        # Si le token n'existe pas
        if "result" not in data or data["result"]["value"] is None:
            return None
            
        # On récupère les infos techniques
        info = data["result"]["value"]["data"]["parsed"]["info"]
        return info
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def analyze_risk(address):
    # 1. Check Blacklist (Toujours actif)
    if address in KNOWN_SCAMS:
        return {
            "score": 0, "risk": "CRITICAL",
            "checks": [{"name": "DATABASE", "status": "BLACKLISTED", "safe": False}],
            "summary": "DANGER: Address identified in Global Blacklist."
        }

    # 2. Récupération des données RÉELLES (Live)
    token_data = get_onchain_data(address)
    
    if not token_data:
        # Si on ne trouve pas le token sur la blockchain
        return {
            "score": 0, "risk": "UNKNOWN",
            "checks": [],
            "summary": "Error: Token not found on Solana Mainnet. Check the address."
        }

    # 3. Analyse des Vraies Données
    # Est-ce que le Mint est désactivé ? (Mint Authority doit être null)
    mint_auth = token_data.get("mintAuthority")
    mint_safe = (mint_auth is None)

    # Est-ce que le Freeze est désactivé ? (Freeze Authority doit être null)
    freeze_auth = token_data.get("freezeAuthority")
    freeze_safe = (freeze_auth is None)

    checks = []
    checks.append({
        "name": "MINT AUTH", 
        "status": "REVOKED ✅" if mint_safe else "ACTIVE ⚠️", 
        "safe": mint_safe
    })
    checks.append({
        "name": "FREEZE AUTH", 
        "status": "REVOKED ✅" if freeze_safe else "ACTIVE ⚠️", 
        "safe": freeze_safe
    })

    # Calcul du Score Réel
    score = 100
    if not mint_safe: score -= 50 # Très dangereux
    if not freeze_safe: score -= 30 # Dangereux

    risk_level = "LOW"
    if score < 50: risk_level = "CRITICAL"
    elif score < 90: risk_level = "MEDIUM"

    # Résumé intelligent
    summary = "SAFE: Contract is renounced and immutable."
    if not mint_safe: summary = "DANGER: Developer can mint unlimited tokens (Rug Pull Risk)."
    elif not freeze_safe: summary = "WARNING: Developer can freeze wallets (Honeypot Risk)."

    return {
        "score": score,
        "risk": risk_level,
        "checks": checks,
        "summary": summary
    }

@app.get("/")
def read_root():
    return {"status": "Solana Gold Guard AI (REAL DATA) is Online"}

@app.post("/scan")
def scan_token(request: TokenRequest):
    clean_address = request.address.strip()
    if len(clean_address) < 10:
        raise HTTPException(status_code=400, detail="Invalid address")
    
    result = analyze_risk(clean_address)
    return result
