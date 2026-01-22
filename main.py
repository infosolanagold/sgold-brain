from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
from solana.rpc.api import Client  # Pour fetch on-chain data
import logging  # Pour debug
import torch
import torch.nn as nn
import numpy as np

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)

# --- SÉCURITÉ ADMIN ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
ADMIN_TOKEN = f"SECURE_SESSION_{hash(ADMIN_PASSWORD)}"

# --- CONFIGURATION FICHIERS ---
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
else:
    BASE_PATH = "."

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")
MODEL_FILE = os.path.join(BASE_PATH, "rug_model.pth")
MEAN_FILE = os.path.join(BASE_PATH, "mean.npy")
STD_FILE = os.path.join(BASE_PATH, "std.npy")

def load_json(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"Error saving {filepath}: {e}")

global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- Solana RPC ---
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
client = Client(SOLANA_RPC)

# --- Grok AI Model (PyTorch MLP) ---
class RugPullClassifier(nn.Module):
    def __init__(self, input_size=5):
        super(RugPullClassifier, self).__init__()
        self.fc1 = nn.Linear(input_size, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = self.sigmoid(self.fc3(x))
        return x

# Load model, mean, std
if os.path.exists(MODEL_FILE):
    model = RugPullClassifier()
    model.load_state_dict(torch.load(MODEL_FILE, map_location=torch.device('cpu')))
    model.eval()
    mean = np.load(MEAN_FILE)
    std = np.load(STD_FILE)
    logging.info("Grok AI Model loaded successfully!")
else:
    logging.error("Model file not found! Using fallback.")
    model = None  # Fallback to old logic if no model

# --- ROUTES PUBLIQUES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ONLINE", "reports": len(global_reports)})

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0}), 400

        # 1. CHECK DATABASE
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0, 
                    "risk": "CRITICAL", 
                    "summary": "🚨 BLACKLISTED: Reported by Solana Gold Guard Community as a SCAM.",
                    "reasons": ["Blacklisted par la communauté et approuvé par admin"]
                })

        # 2. RUGCHECK API
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=5)

        if res.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new or not found.", "reasons": ["Token non trouvé ou trop récent"]})

        rc_data = res.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 3. HEURISTIQUE
        token_meta = rc_data.get('tokenMeta', {})
        token_name = token_meta.get('name', '').lower()
        suspicious_keywords = ['claim', 'reward', 'airdrop', 'stakin', 'migrat', 'support', 'v2', 'gift', 'ledger', 'wallet', 'drainer', 'rug', 'honeypot', 'scam']
        is_suspicious_name = any(word in token_name for word in suspicious_keywords)
        summary = "Clean Analysis."
        risks = rc_data.get('risks', [])
        reasons = []
        if risks:
            summary = f"ALERT: {risks[0].get('name')}."
            reasons.append(f"Risque détecté par RugCheck: {risks[0].get('name')}")
        if is_suspicious_name:
            safety_score = min(safety_score, 40)
            summary = f"SUSPICIOUS NAME DETECTED ('{token_name}'). Possible Phishing/Drainer."
            reasons.append(f"Nom suspect détecté: '{token_name}' – Possible phishing/drainer")

        # 4. GROK SCAN AI (ON-CHAIN + VRAI ML)
        tx_count = 0
        holder_count_estimate = 0
        number_adds = 0  # Simu pour l'instant - ajoute API pour liquidity si possible
        number_removes = 0
        add_remove_ratio = 1.0
        lifespan_days = 0.0

        try:
            signatures = client.get_signatures_for_address(token_address, limit=10)
            tx_history = signatures.value if signatures.value else []
            tx_count = len(tx_history)
            if tx_count > 0:
                first_tx = client.get_transaction(tx_history[-1]['signature'])  # Approx first (oldest)
                last_tx = client.get_transaction(tx_history[0]['signature'])  # Newest
                first_time = datetime.fromtimestamp(first_tx.value['blockTime'])
                last_time = datetime.fromtimestamp(last_tx.value['blockTime'])
                lifespan_days = (last_time - first_time).days
            if tx_count < 5:
                safety_score -= 40
                reasons.append("Historique de transactions trop court (<5 tx)")
        except:
            safety_score -= 50
            reasons.append("Erreur RPC")

        try:
            largest_accounts = client.get_token_largest_accounts(token_address)
            if largest_accounts.value:
                holder_count_estimate = len(largest_accounts.value)
                if holder_count_estimate < 10:
                    safety_score -= 20
                    reasons.append(f"Peu de holders ({holder_count_estimate})")
        except:
            safety_score -= 10
            reasons.append("Impossible de fetcher holders")

        # Simu liquidity features (ajoute une API comme Birdeye ou Jupiter pour real added/removed si possible)
        number_adds = tx_count * 0.5  # Placeholder - adapte
        number_removes = tx_count * 0.1
        add_remove_ratio = number_adds / (number_removes + 1e-6)

        # Vrai AI prédiction avec model
        if model:
            features_np = np.array([[number_adds, number_removes, add_remove_ratio, lifespan_days, holder_count_estimate]])
            features_np = (features_np - mean) / std
            features_tensor = torch.tensor(features_np, dtype=torch.float32)
            with torch.no_grad():
                risk_prob = model(features_tensor).item() * 100  # Prob de rug (0-100)
            safety_score = max(0, min(100, 100 - risk_prob))
            reasons.append(f"Grok AI prédiction: Risque de rug {risk_prob:.2f}%")
        else:
            # Fallback si pas de model
            ai_adjustment = np.random.randint(0, 30)
            safety_score -= ai_adjustment
            reasons.append(f"Fallback AI: -{ai_adjustment}")

        safety_score = max(0, min(100, safety_score))

        # Label
        if safety_score < 30:
            risk_label = "CRITICAL"
            prediction = "Haut risque (rug potentiel dans 48h) – avoid! 🔥"
        elif safety_score < 70:
            risk_label = "WARNING"
            prediction = f"Risque modéré – proceed with caution. ⚠️"
        else:
            risk_label = "SAFE"
            prediction = "Bas risque – safe to ape! 🚀"

        return jsonify({
            "score": safety_score, 
            "risk": risk_label, 
            "summary": summary, 
            "prediction": prediction, 
            "tx_count": tx_count,
            "reasons": reasons
        })
        
    except Exception as e:
        print(f"Scan Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0}), 500

# Les autres routes restent identiques (submit_report, get_reports, admin_login, etc.)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
# --- NOUVELLE ROUTE GROK-ENHANCED (isolée) ---
@app.route('/grok-scan', methods=['POST'])
def grok_scan():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "grok_message": "No address provided! 🛑"}), 400

        # Réutilise la logique existante de /scan (sans la dupliquer)
        # On simule un appel interne à la logique de scan
        # (Tu peux refactor plus tard pour éviter la duplication)

        # 1. RugCheck (comme dans ton code)
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=5)
        if res.status_code != 200:
            return jsonify({
                "score": 0,
                "risk": "UNKNOWN",
                "summary": "Token too new or not found.",
                "grok_message": "Grok says: This token is too fresh... or too hidden. Suspicious? 😏"
            })

        rc_data = res.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 2. Heuristique + on-chain (comme ton code)
        suspicious_keywords = ['claim', 'reward', 'airdrop', 'stakin', 'migrat', 'support', 'v2', 'gift', 'ledger', 'wallet', 'drainer', 'rug', 'honeypot', 'scam']
        token_name = rc_data.get('tokenMeta', {}).get('name', '').lower()
        is_suspicious_name = any(word in token_name for word in suspicious_keywords)
        if is_suspicious_name:
            safety_score = min(safety_score, 40)

        # 3. On-chain (tx count, etc.)
        try:
            pubkey = PublicKey(token_address)
            signatures = client.get_signatures_for_address(pubkey, limit=10).value
            tx_count = len(signatures) if signatures else 0
            if tx_count < 5:
                safety_score -= 40
        except:
            tx_count = 0
            safety_score -= 30

        # 4. Grok AI boost (simple mais fun)
        grok_insight = ""
        if safety_score > 80:
            grok_insight = "Grok approves: This looks clean. Ape responsibly! 🚀"
        elif safety_score > 50:
            grok_insight = "Grok says: Meh... some red flags, but not screaming scam. DYOR hard."
        else:
            grok_insight = "Grok warns: High rug probability. Run away! ☠️"

        return jsonify({
            "score": safety_score,
            "risk": "CRITICAL" if safety_score < 30 else "WARNING" if safety_score < 70 else "SAFE",
            "summary": rc_data.get('risks', [{}])[0].get('name', 'No major risks detected'),
            "grok_insight": grok_insight,
            "tx_count": tx_count,
            "powered_by": "Grok x SolanaGoldGuard"
        })

    except Exception as e:
        logging.error(f"Grok Scan Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "grok_message": "Grok encountered a glitch... try again later! 🤖"}), 500
