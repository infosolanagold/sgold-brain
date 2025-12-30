from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time

app = Flask(__name__)
# Autorise tout le monde à se connecter
CORS(app, resources={r"/*": {"origins": "*"}})

# --- MÉMOIRE VIVE (Stocke les rapports tant que le serveur est allumé) ---
# C'est ici que les rapports des utilisateurs vont arriver
global_reports = []

@app.route('/', methods=['GET'])
def home():
    return f"SERVER ONLINE. {len(global_reports)} reports in memory."

# --- 1. RECEVOIR UN RAPPORT (Depuis le site) ---
@app.route('/report/submit', methods=['POST'])
def submit_report():
    try:
        data = request.json
        # On ajoute un ID unique basé sur l'heure
        data['id'] = int(time.time() * 1000)
        data['status'] = 'pending'
        
        # On ajoute le rapport en haut de la liste
        global_reports.insert(0, data)
        print(f"🚨 Nouveau rapport reçu : {data['target']}")
        return jsonify({"status": "success", "id": data['id']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 2. ENVOYER LES RAPPORTS (Vers ton Admin) ---
@app.route('/report/list', methods=['GET'])
def get_reports():
    return jsonify(global_reports)

# --- 3. ACTIONS ADMIN (Approuver/Supprimer) ---
@app.route('/report/action', methods=['POST'])
def action_report():
    try:
        req = request.json
        action = req.get('action') # 'approve' ou 'delete'
        report_id = req.get('id')
        
        global global_reports
        
        if action == 'delete':
            # On garde tout sauf celui qu'on veut supprimer
            global_reports = [r for r in global_reports if r['id'] != report_id]
        elif action == 'approve':
            # On cherche le rapport et on change son statut
            for r in global_reports:
                if r['id'] == report_id:
                    r['status'] = 'approved'
                    
        return jsonify({"status": "updated", "current_count": len(global_reports)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 4. LE SCANNER (inchangé, toujours blindé) ---
@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        headers = {"User-Agent": "Mozilla/5.0"}
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, headers=headers, timeout=5)

        if response.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token too new."})

        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        risks = rc_data.get('risks', [])
        summary = "Clean Analysis." if not risks else f"ALERT: {risks[0].get('name')}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})

    except Exception:
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Scan failed."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
