from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os
from datetime import datetime
import logging
import hashlib

# --- SETUP LOGGING ---
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- SÉCURITÉ ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SOLANA_ADMIN")
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# --- CONFIGURATION CRITIQUE DU STOCKAGE ---
# C'est ici que ça se joue. On définit le chemin vers le disque persistant.
# Sur Render, le "Mount Path" du disque doit être configuré sur /var/data
PERSISTENT_DISK_PATH = "/var/data"

# Vérification au démarrage
if os.path.exists(PERSISTENT_DISK_PATH):
    logging.info(f"✅ DISQUE PERSISTANT DÉTECTÉ : {PERSISTENT_DISK_PATH}")
    BASE_PATH = PERSISTENT_DISK_PATH
else:
    logging.warning("⚠️ ATTENTION : DISQUE NON DÉTECTÉ. Utilisation du stockage temporaire (Risque de perte de données !)")
    BASE_PATH = os.getcwd()

DB_FILE = os.path.join(BASE_PATH, "database.json")
REF_FILE = os.path.join(BASE_PATH, "referrals.json")

# --- FONCTIONS DE SAUVEGARDE ROBUSTES ---

def load_data():
    # Si le fichier existe sur le disque, on le charge
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                logging.info(f"📂 Chargé {len(data)} rapports depuis {DB_FILE}")
                return data
        except Exception as e:
            logging.error(f"Erreur lecture DB: {e}")
            return []
    else:
        # Si le fichier n'existe pas encore (premier lancement sur le disque)
        logging.info("✨ Création d'une nouvelle base de données vide sur le disque.")
        return []

def save_data(data):
    try:
        # On écrit directement sur le disque
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"❌ CRITIQUE : Impossible de sauvegarder sur {DB_FILE} : {e}")

# Chargement initial
global_reports = load_data()
global_referrals = []

# Charge les referrals s'ils existent
if os.path.exists(REF_FILE):
    try:
        with open(REF_FILE, 'r') as f: global_referrals = json.load(f)
    except: pass

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ONLINE", 
        "reports_count": len(global_reports),
        "storage_location": BASE_PATH, # Vérifie que ça affiche /var/data
        "disk_connected": os.path.exists(PERSISTENT_DISK_PATH)
    })

@app.route('/report/list', methods=['GET'])
def list_reports():
    return jsonify(global_reports)

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        # Création de l'entrée
        new_report = {
            "id": int(time.time() * 1000),
            "target": data.get('target'),
            "desc": data.get('desc'),
            "contact": data.get('contact'),
            "img": data.get('img'),
            "status": 'pending', # Par défaut en attente de validation admin
            "submitted_at": datetime.now().isoformat()
        }
        
        # Ajout et Sauvegarde Immédiate
        global_reports.insert(0, new_report)
        save_data(global_reports) # <--- Sauvegarde sur le disque dur
        
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Erreur submit: {e}")
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
        save_data(global_reports) # <--- Sauvegarde après modification admin
        
    return jsonify({"status": "updated"})

# --- REFERRALS & ADMIN ---
@app.route('/admin/login', methods=['POST'])
def login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/referral/track', methods=['POST'])
def track_referral():
    return jsonify({"status": "tracked"}) # Placeholder pour simplifier

@app.route('/referral/list', methods=['GET'])
def list_ref():
    return jsonify(global_referrals)

# --- SCANNER ---
@app.route('/scan', methods=['POST'])
def scan_contract():
    # ... (Garde ton code scanner ici ou utilise celui ci-dessous simplifié)
    return jsonify({"score": 50, "risk": "UNKNOWN", "summary": "API Connect Error"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
