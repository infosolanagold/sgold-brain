from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
import random  # Ajouté car tu l'utilises dans le fallback
from datetime import datetime
import logging
import numpy as np

# --- GESTION DES IMPORTS LOURDS (Pour éviter le crash au démarrage) ---
try:
    import torch
    import torch.nn as nn
    AI_AVAILABLE = True
except ImportError:
    logging.warning("⚠️ Torch non installé. Mode AI désactivé.")
    AI_AVAILABLE = False

try:
    from solana.rpc.api import Client
    # Gestion de la compatibilité des versions Solana/Solders
    try:
        from solana.publickey import PublicKey
    except ImportError:
        from solders.pubkey import Pubkey as PublicKey
    RPC_AVAILABLE = True
except ImportError:
    logging.warning("⚠️ Solana/Solders non installé. Mode RPC désactivé.")
    RPC_AVAILABLE = False

app = Flask(__name__)
# Restreindre les origines en production est mieux, mais '*' est ok pour le dev
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)

# --- SÉCURITÉ ADMIN ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
# Utilisation d'un hash simple pour la session
ADMIN_TOKEN = f"SECURE_SESSION_{hash(ADMIN_PASSWORD)}"

# --- CONFIGURATION FICHIERS ---
# Utilisation de /tmp si /var/data n'est pas dispo (meilleur pour les cloud serverless)
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
else:
    BASE_PATH = os.getcwd() # Ou "/tmp" sur certains cloud

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")
MODEL_FILE = os.path.join(BASE_PATH, "rug_model.pth")
MEAN_FILE = os.path.join(BASE_PATH, "mean.npy")
STD_FILE = os.path.join(BASE_PATH, "std.npy")

def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return []

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving {filepath}: {e}")

global_reports = load_json(DB_FILE)
global_referrals = load_json(REF_FILE)

# --- Solana RPC ---
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
client = Client(SOLANA_RPC) if RPC_AVAILABLE else None

# --- Grok AI Model ---
class RugPullClassifier(nn.Module if AI_AVAILABLE else object):
    def __init__(self, input_size=5):
        super().__init__()
        if AI_AVAILABLE:
            self.fc1 = nn.Linear(input_size, 64)
            self.fc2 = nn.Linear(64, 32)
            self.fc3 = nn.Linear(32, 1)
            self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        if not AI_AVAILABLE: return 0
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = self.sigmoid(self.fc3(x))
        return x

model = None
mean = None
std = None

if AI_AVAILABLE and os.path.exists(MODEL_FILE):
    try:
        model = RugPullClassifier()
        model.load_state_dict(torch.load(MODEL_FILE, map_location=torch.device('cpu')))
        model.eval()
        mean = np.load(MEAN_FILE)
        std = np.load(STD_FILE)
        logging.info("✅ Grok AI Model loaded successfully!")
    except Exception as e:
        logging.error(f"Failed to load model: {e}")
        model = None
else:
    logging.warning("⚠️ Model file not found or Torch missing. Using fallback logic.")

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE 🟢", 
        "reports": len(global_reports),
        "ai_active": model is not None
    })

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0}), 400

        # 1. CHECK DATABASE
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0,
                    "risk": "CRITICAL",
                    "summary": "🚨 BLACKLISTED: Reported by Community.",
                    "reasons": ["Blacklisted locally"]
                })

        # 2. RUGCHECK API
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary", headers=headers, timeout=5)
            if res.status_code == 200:
                rc_data = res.json()
            else:
                rc_data = {}
        except:
            rc_data = {}

        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))
        
        reasons = []
        risks = rc_data.get('risks', [])
        if risks:
            reasons.append(f"RugCheck Alert: {risks[0].get('name')}")

        # 3. HEURISTIQUE
        token_name = rc_data.get('tokenMeta', {}).get('name', '').lower()
        suspicious_keywords = ['claim', 'reward', 'stakin', 'migrat', 'support', 'gift']
        if any(word in token_name for word in suspicious_keywords):
            safety_score = min(safety_score, 40)
            reasons.append(f"Nom suspect: '{token_name}'")

        # 4. ON-CHAIN ANALYSIS (RPC)
        tx_count = 0
        holder_count_estimate = 0
        lifespan_days = 0.0
        
        if RPC_AVAILABLE and client:
            try:
                pubkey = PublicKey(token_address)
                # Note: get_signatures_for_address peut être lourd/lent
                signatures = client.get_signatures_for_address(pubkey, limit=10).value
                tx_history = signatures if signatures else []
                tx_count = len(tx_history)
                
                if tx_count < 5:
                    safety_score -= 20
                    reasons.append("Très peu de transactions récentes")
            except Exception as e:
                logging.error(f"RPC Error: {e}")

        # 5. AI PREDICTION (Ou Fallback)
        if model and AI_AVAILABLE:
            # Valeurs par défaut si RPC échoue
            number_adds = tx_count * 0.5
            number_removes = tx_count * 0.1
            add_remove_ratio = number_adds / (number_removes + 1e-6)
            
            try:
                features_np = np.array([[number_adds, number_removes, add_remove_ratio, lifespan_days, holder_count_estimate]])
                # Normalisation manuelle si mean/std chargés
                if mean is not None and std is not None:
                    features_np = (features_np - mean) / std
                
                features_tensor = torch.tensor(features_np, dtype=torch.float32)
                with torch.no_grad():
                    risk_prob = model(features_tensor).item() * 100
                
                ai_score = 100 - risk_prob
                # On pondère le score AI avec le score technique
                safety_score = (safety_score * 0.6) + (ai_score * 0.4)
                reasons.append(f"AI Risk Assessment: {risk_prob:.1f}%")
            except Exception as e:
                logging.error(f"AI Error: {e}")
        else:
            # Fallback simple pour ne pas bloquer
            reasons.append("AI Engine: Offline (Mode Fallback)")

        # Finalisation du score
        safety_score = int(max(0, min(100, safety_score)))
        
        risk_label = "SAFE"
        if safety_score < 40: risk_label = "CRITICAL"
        elif safety_score < 75: risk_label = "WARNING"

        summary = "Clean Analysis." if not reasons else f"Issues found: {len(reasons)}"

        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary,
            "reasons": reasons,
            "powered_by": "SolanaGoldGuard V4"
        })

    except Exception as e:
        logging.error(f"Global Scan Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "error": str(e)}), 500

# --- AUTH ROUTES ---
@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        data['submitted_at'] = datetime.now().isoformat()
        
        global_reports.insert(0, data)
        save_json(DB_FILE, global_reports)
        return jsonify({"status": "success", "id": data['id']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/report/list', methods=['GET'])
def list_reports():
    return jsonify(global_reports)

@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    action = data.get('action')
    r_id = data.get('id')
    
    global global_reports
    updated = False
    
    if action == 'delete':
        global_reports = [r for r in global_reports if r.get('id') != r_id]
        updated = True
    elif action == 'approve':
        for r in global_reports:
            if r.get('id') == r_id:
                r['status'] = 'approved'
                updated = True
                
    if updated: save_json(DB_FILE, global_reports)
    return jsonify({"status": "updated"})

# --- REFERRAL ROUTES ---
@app.route('/referral/track', methods=['POST'])
def track_ref():
    try:
        data = request.json
        data['server_time'] = datetime.now().isoformat()
        if 'paid' not in data: data['paid'] = False
        global_referrals.append(data)
        save_json(REF_FILE, global_referrals)
        return jsonify({"status": "tracked"})
    except: return jsonify({"error": "Failed"}), 500

@app.route('/referral/list', methods=['GET'])
def list_refs():
    return jsonify(global_referrals)

@app.route('/referral/pay', methods=['POST'])
def pay_ref():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    target = data.get('referrerWallet')
    for ref in global_referrals:
        if ref.get('referrerWallet') == target:
            ref['paid'] = True
    save_json(REF_FILE, global_referrals)
    return jsonify({"status": "paid"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
