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
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erreur lecture DB: {e}")
            return []
    return []

def save_data(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Erreur sauvegarde DB: {e}")

# Chargement au démarrage
global_reports = load_data()
global_referrals = []
if os.path.exists(REF_FILE):
    try:
        with open(REF_FILE, 'r') as f: global_referrals = json.load(f)
    except: pass

# --- ROUTES PRINCIPALES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE",
        "reports_count": len(global_reports),
        "storage_mode": "PERSISTENT" if BASE_PATH == "/var/data" else "TEMPORARY",
        "scan_engine": "ACTIVE (STRICT & DETAILED)"
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
        save_data(global_reports)
        
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
        save_data(global_reports)
        
    return jsonify({"status": "updated"})


# --- MOTEUR DE SCAN (SCANNER LOGIC - STRICT & DÉTAILLÉ) ---

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
                    "summary": "🚨 BLACKLISTED: Known Scam",
                    "details": ["⚠️ Ce token a été signalé et confirmé comme une fraude par la communauté Solana Gold Guard."]
                })

        # ÉTAPE 2 : Interroger l'API RugCheck avec analyse poussée
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            api_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
            res = requests.get(api_url, headers=headers, timeout=5)
            
            if res.status_code == 200:
                rc_data = res.json()
                danger_score = rc_data.get('score', 0) 
                safety_score = max(0, 100 - danger_score)
                
                risks = rc_data.get('risks', [])
                summary = "Analyse terminée"
                
                # LA VIANDE (Analyse détaillée)
                detailed_analysis = []
                
                if risks:
                    summary = "Problèmes critiques détectés"
                    
                    for risk in risks:
                        r_name = risk.get('name', '').lower()
                        r_desc = risk.get('description', '').lower()
                        r_combined = r_name + " " + r_desc

                        # 💧 LIQUIDITÉ
                        if 'liquidity' in r_combined or 'lp' in r_combined:
                            if 'low' in r_combined or 'unlocked' in r_combined:
                                safety_score -= 40
                                if "💧 Liquidité Faible/Non-Verrouillée : Les développeurs n'ont pas bloqué les fonds. Ils peuvent retirer l'argent (Rug Pull) à n'importe quel moment." not in detailed_analysis:
                                    detailed_analysis.append("💧 Liquidité Faible/Non-Verrouillée : Les développeurs n'ont pas bloqué les fonds. Ils peuvent retirer l'argent (Rug Pull) à n'importe quel moment.")

                        # 🖨️ MINT AUTHORITY
                        if 'mint' in r_combined and 'authority' in r_combined:
                            safety_score -= 60
                            if "🖨️ Mint Authority Actif : Le créateur a gardé le droit d'imprimer de nouveaux tokens à l'infini, ce qui détruira la valeur de votre investissement." not in detailed_analysis:
                                detailed_analysis.append("🖨️ Mint Authority Actif : Le créateur a gardé le droit d'imprimer de nouveaux tokens à l'infini, ce qui détruira la valeur de votre investissement.")

                        # 🧊 FREEZE AUTHORITY
                        if 'freeze' in r_combined and 'authority' in r_combined:
                            safety_score -= 60
                            if "🧊 Freeze Authority Actif (HONEYPOT) : Vous pouvez acheter ce token, mais le contrat permet au créateur de geler votre portefeuille pour vous empêcher de revendre." not in detailed_analysis:
                                detailed_analysis.append("🧊 Freeze Authority Actif (HONEYPOT) : Vous pouvez acheter ce token, mais le contrat permet au créateur de geler votre portefeuille pour vous empêcher de revendre.")

                        # 🐋 WHALES
                        if 'top holders' in r_combined or 'concentration' in r_combined:
                            safety_score -= 25
                            if "🐋 Concentration des Whales : Une quantité dangereuse de tokens est détenue par très peu de portefeuilles. S'ils décident de vendre, le prix s'effondrera." not in detailed_analysis:
                                detailed_analysis.append("🐋 Concentration des Whales : Une quantité dangereuse de tokens est détenue par très peu de portefeuilles. S'ils décident de vendre, le prix s'effondrera.")
                
                # 🎣 PHISHING
                meta = rc_data.get('tokenMeta', {})
                token_name = meta.get('name', '').lower()
                if any(x in token_name for x in ['claim', 'reward', 'stakin', 'gift', 'v2', 'airdrop']):
                    safety_score = min(safety_score, 25)
                    detailed_analysis.append("🎣 Nom Trompeur (Phishing) : Le nom de ce token utilise des mots-clés d'arnaque typiques pour vous inciter à connecter votre portefeuille.")

                # Sécuriser le score entre 0 et 100
                safety_score = max(0, min(100, safety_score))
                
                # Token clean
                if safety_score >= 85 and not detailed_analysis:
                    detailed_analysis.append("✅ Aucun signal d'alarme majeur détecté. Le contrat semble propre. (DYOR)")

                # Paliers stricts
                if safety_score < 50:
                    risk_label = "CRITICAL"
                elif safety_score < 85:
                    risk_label = "WARNING"
                else:
                    risk_label = "SAFE"
                    summary = "Token propre"

                return jsonify({
                    "score": safety_score,
                    "risk": risk_label,
                    "summary": summary,
                    "details": detailed_analysis,
                    "reasons": [r.get('name', 'Unknown') for r in risks][:4] 
                })
            else:
                return jsonify({
                    "score": 50,
                    "risk": "UNKNOWN",
                    "summary": "Token trop récent ou introuvable.",
                    "details": ["🕵️ Le token est trop récent pour avoir un historique ou l'API n'a pas pu l'analyser."]
                })

        except Exception as e:
            return jsonify({
                "score": 50, 
                "risk": "UNKNOWN", 
                "summary": "Erreur de connexion",
                "details": ["⚠️ Impossible de se connecter au moteur de scan externe."]
            })

    except Exception as e:
        return jsonify({"risk": "ERROR", "score": 0}), 500


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
        
        try:
            with open(REF_FILE, 'w') as f: json.dump(global_referrals, f, indent=4)
        except: pass
        
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
        
    try:
        with open(REF_FILE, 'w') as f: json.dump(global_referrals, f, indent=4)
    except: pass
    return jsonify({"status": "paid"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
