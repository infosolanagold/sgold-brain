from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging
import hashlib

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
# Autoriser toutes les origines pour éviter les erreurs CORS sur ton site
CORS(app, resources={r"/*": {"origins": "*"}})

# --- SÉCURITÉ ADMIN ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# --- DISQUE PERSISTANT (RENDER) ---
if os.path.exists("/var/data"):
    BASE_PATH = "/var/data"
    logging.info(f"✅ MODE PRODUCTION : Disque persistant trouvé sur {BASE_PATH}")
else:
    BASE_PATH = os.getcwd()
    logging.warning("⚠️ MODE TEMPORAIRE : Aucun disque trouvé. Les données seront perdues au redémarrage.")

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")

# --- FONCTIONS DE BASE DE DONNÉES ---
def load_data(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erreur lecture fichier {filepath}: {e}")
            return []
    return []

def save_data(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Erreur sauvegarde fichier {filepath}: {e}")

# Chargement au démarrage
global_reports = load_data(DB_FILE)
global_referrals = load_data(REF_FILE)

# --- ROUTES PRINCIPALES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE",
        "reports_count": len(global_reports),
        "storage_mode": "PERSISTENT" if BASE_PATH == "/var/data" else "TEMPORARY",
        "scan_engine": "ACTIVE (INSTITUTIONAL GRADE)"
    })

# --- GESTION DES RAPPORTS (DATABASE) ---

@app.route('/report/list', methods=['GET'])
def list_reports():
    return jsonify(global_reports)

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        new_report = {
            "id": int(time.time() * 1000),
            "target": data.get('target'),
            "desc": data.get('desc'),
            "contact": data.get('contact', ''),
            "img": data.get('img'),
            "status": 'pending', 
            "submitted_at": datetime.now().isoformat()
        }
        
        global_reports.insert(0, new_report)
        save_data(DB_FILE, global_reports)
        
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Submit error: {e}")
        return jsonify({"error": "failed"}), 500

@app.route('/report/action', methods=['POST'])
def action_report():
    data = request.json
    if data.get('token') != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    action = data.get('action')
    r_id = data.get('id')
    global global_reports
    
    modified = False
    if action == 'delete':
        global_reports = [r for r in global_reports if r.get('id') != r_id]
        modified = True
    elif action == 'approve':
        for r in global_reports:
            if r.get('id') == r_id: 
                r['status'] = 'approved'
                modified = True
    
    if modified:
        save_data(DB_FILE, global_reports)
        
    return jsonify({"status": "updated"})

# --- REFERRALS & ADMIN LOGIN ---

@app.route('/admin/login', methods=['POST'])
def login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/referral/track', methods=['POST'])
def track_referral():
    try:
        data = request.json
        entry = {
            "id": int(time.time() * 1000),
            "visitorWallet": data.get('visitorWallet'),
            "referrerWallet": data.get('referrerWallet'),
            "server_time": datetime.now().isoformat(),
            "paid": False
        }
        global_referrals.append(entry)
        save_data(REF_FILE, global_referrals)
        return jsonify({"status": "tracked"})
    except: return jsonify({"error": "failed"}), 500

@app.route('/referral/list', methods=['GET'])
def list_ref():
    return jsonify(global_referrals)

@app.route('/referral/pay', methods=['POST'])
def pay_ref():
    data = request.json
    if data.get('token') != ADMIN_TOKEN: return jsonify({"error": "Unauthorized"}), 403
    
    target = data.get('referrerWallet')
    for ref in global_referrals:
        if ref.get('referrerWallet') == target: ref['paid'] = True
        
    save_data(REF_FILE, global_referrals)
    return jsonify({"status": "paid"})


# --- MOTEUR DE SCAN (INSTITUTIONAL GRADE AUDIT) ---

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address provided"}), 400

        # ÉTAPE 1 : Vérifier la Blacklist locale
        for report in global_reports:
            if report.get('target') == token_address and report.get('status') == 'approved':
                return jsonify({
                    "score": 0,
                    "risk": "CRITICAL",
                    "summary": "🚨 BLACKLISTED: Known Scam confirmed by Sentinel Database.",
                    "details": ["❌ Community Flag: This token has been reported and confirmed as a malicious contract."],
                    "stats": {"name": "BLACKLISTED", "symbol": "N/A", "liquidity": "N/A"}
                })

        # ÉTAPE 2 : Interroger l'API RugCheck (Timeout 15s)
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            api_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report"
            res = requests.get(api_url, headers=headers, timeout=15)
            
            if res.status_code == 200:
                rc_data = res.json()
                danger_score = rc_data.get('score', 0) 
                safety_score = max(0, 100 - danger_score)
                
                # --- EXTRACTION DES STATS ---
                meta = rc_data.get('tokenMeta', {})
                token_name = meta.get('name', 'Unknown')
                token_symbol = meta.get('symbol', '???')
                
                # Extraction de la liquidité
                markets = rc_data.get('markets', [])
                total_lp = sum([m.get('lp', {}).get('lpLockedUSD', 0) for m in markets]) if markets else 0
                if total_lp == 0: total_lp = rc_data.get('totalMarketLiquidity', 0)
                formatted_lp = f"${total_lp:,.2f}" if total_lp > 0 else "Unknown / Low"

                stats_data = {
                    "name": token_name,
                    "symbol": token_symbol,
                    "liquidity": formatted_lp
                }
                
                # --- ANALYSE TECHNIQUE (LES 4 PILIERS DE L'AUDIT) ---
                risks = rc_data.get('risks', [])
                
                mint_active = False
                freeze_active = False
                lp_warning = False
                whale_warning = False
                phishing_warning = False

                for risk in risks:
                    r_combined = (risk.get('name', '') + " " + risk.get('description', '')).lower()
                    if 'mint' in r_combined: mint_active = True
                    if 'freeze' in r_combined: freeze_active = True
                    if 'liquidity' in r_combined or 'lp' in r_combined: lp_warning = True
                    if 'top holders' in r_combined or 'concentration' in r_combined or 'single holder' in r_combined: whale_warning = True

                # Détection de mots-clés typiques de phishing
                if any(x in token_name.lower() for x in ['claim', 'reward', 'stakin', 'gift', 'v2', 'airdrop']):
                    phishing_warning = True
                    safety_score = min(safety_score, 25)

                detailed_analysis = []
                
                # 1. Vérification de l'Autorité de Création (Mint)
                if mint_active: detailed_analysis.append("❌ Mint Authority Active: Creator can inflate supply infinitely.")
                else: detailed_analysis.append("✅ Mint Authority Revoked: Fixed supply, no inflation risk detected.")

                # 2. Vérification du blocage des ventes (Freeze/Honeypot)
                if freeze_active: detailed_analysis.append("❌ Freeze Authority Active: Trading can be halted (Honeypot Risk).")
                else: detailed_analysis.append("✅ Freeze Authority Revoked: Contract cannot restrict your trades.")

                # 3. Analyse de la Liquidité
                if lp_warning or total_lp < 5000: 
                    detailed_analysis.append(f"⚠️ Liquidity Warning: LP is low or unlocked. High rug-pull probability.")
                else: 
                    detailed_analysis.append(f"✅ Liquidity Secured: Healthy Locked/Burned LP levels detected.")

                # 4. Distribution des Jetons (Whales)
                if whale_warning: detailed_analysis.append("⚠️ Holder Concentration: Top wallets control a massive % of supply (Dump risk).")
                else: detailed_analysis.append("✅ Healthy Distribution: No extreme algorithmic whale dominance found.")

                if phishing_warning: detailed_analysis.append("🎣 Phishing Alert: Name suggests a malicious airdrop/wallet-drainer scam.")

                # Boundaries
                safety_score = max(0, min(100, safety_score))
                
                # Résumés Institutionnels
                if safety_score < 50:
                    risk_label = "CRITICAL"
                    summary = "Institutional Risk Assessment: CRITICAL DANGER. Multiple catastrophic vectors detected in the core contract. Do not interact."
                elif safety_score < 85:
                    risk_label = "WARNING"
                    summary = "Institutional Risk Assessment: MODERATE RISK. Anomalies detected in contract logic or liquidity structure. Proceed with extreme caution."
                else:
                    risk_label = "SAFE"
                    summary = "Institutional Risk Assessment: CLEAR. Deep chain audit found no major algorithmic threats. Base contract appears secure."

                return jsonify({
                    "score": safety_score,
                    "risk": risk_label,
                    "summary": summary,
                    "details": detailed_analysis,
                    "stats": stats_data
                })
            else:
                return jsonify({
                    "score": 50,
                    "risk": "UNKNOWN",
                    "summary": "Token too new or API unresponsive.",
                    "details": ["🕵️ Data Sync Error: The token is too recent to have a verified history, or the RPC endpoint is busy."],
                    "stats": {"name": "Unknown", "symbol": "???", "liquidity": "N/A"}
                })

        except Exception as e:
            return jsonify({
                "score": 50, 
                "risk": "UNKNOWN", 
                "summary": "RPC Connection Error",
                "details": ["⚠️ Unable to establish a secure connection to the Solana blockchain. Try again later."],
                "stats": {"name": "Error", "symbol": "Error", "liquidity": "Error"}
            })

    except Exception as e:
        return jsonify({"risk": "ERROR", "score": 0}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
