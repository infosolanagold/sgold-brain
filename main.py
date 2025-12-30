from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- CONFIGURATION DU DISQUE PERSISTANT ---
# C'est ici que tes données seront stockées à vie (sur le disque à 7$)
DB_FILE = "/var/data/database.json"

# --- GESTION DE LA BASE DE DONNÉES ---
def load_db():
    """Charge la base de données depuis le disque dur au démarrage."""
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_db(data):
    """Sauvegarde immédiate sur le disque dur."""
    try:
        with open(DB_FILE, 'w') as f:
            # indent=4 permet de rendre le fichier lisible pour un humain si besoin
            json.dump(data, f, indent=4) 
    except Exception as e:
        print(f"ERREUR SAUVEGARDE DISQUE: {e}")

# Charge la mémoire au démarrage du serveur
global_reports = load_db()

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return f"SERVER ONLINE. Running on Persistent Storage. {len(global_reports)} reports loaded."

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: 
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        headers = {"User-Agent": "Mozilla/5.0"}
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, headers=headers, timeout=5)

        if response.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new."})

        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        
        # Calcul du score de sécurité (Inverse du Danger)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        risk_label = "SAFE"
        if safety_score < 50: 
            risk_label = "CRITICAL"
        elif safety_score < 80: 
            risk_label = "WARNING"

        risks = rc_data.get('risks', [])
        summary = "Clean Analysis." if not risks else f"ALERT: {risks[0].get('name')}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})
    except:
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Scan failed."}), 500

@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        # Création ID unique basé sur l'heure
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        
        # Ajout en mémoire
        global_reports.insert(0, data)
        
        # SAUVEGARDE CRITIQUE SUR LE DISQUE
        save_db(global_reports) 
        
        return jsonify({"status": "success", "id": data['id']})
    except Exception as e: 
        return jsonify({"error": str(e)}), 500

@app.route('/report/list', methods=['GET'])
def get_reports():
    return jsonify(global_reports)

@app.route('/report/action', methods=['POST'])
def action_report():
    try:
        req = request.json
        action = req.get('action')
        report_id = req.get('id')
        global global_reports
        
        updated = False
        
        if action == 'delete':
            global_reports = [r for r in global_reports if r['id'] != report_id]
            updated = True
        elif action == 'approve':
            for r in global_reports:
                if r['id'] == report_id: 
                    r['status'] = 'approved'
                    updated = True
        
        if updated:
            # SAUVEGARDE CRITIQUE APRES MODIFICATION
            save_db(global_reports) 
            
        return jsonify({"status": "updated"})
    except Exception as e: 
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
