from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
# Autorise les requêtes du site Wix
CORS(app)

# --- 1. LA MÉMOIRE DU CERVEAU (DATABASE) ---
# Ces rapports seront chargés au démarrage.
# Note: Sur la version gratuite de Render, si le serveur redémarre, ça revient à cette liste.
database_reports = [
    {"id": 101, "target": "Fake_JUP_Airdrop", "desc": "Phishing site asking for seed phrase.", "status": "approved", "img": None},
    {"id": 102, "target": "Bonk_Killer_V2", "desc": "Mint Authority enabled. Dev dumping.", "status": "approved", "img": None},
    {"id": 103, "target": "Solana_Printer_DAO", "desc": "Honeypot detected. 99% Tax.", "status": "approved", "img": None}
]

@app.route('/', methods=['GET'])
def home():
    return "Solana Gold Guard AI & Database are ONLINE 🟢"

# --- 2. GESTION DE LA DATABASE ---

@app.route('/reports', methods=['GET'])
def get_reports():
    """Envoie la liste des arnaques au site"""
    return jsonify(database_reports)

@app.route('/reports/add', methods=['POST'])
def add_report():
    """Ajoute une nouvelle arnaque (Admin Approve)"""
    try:
        new_report = request.json
        # On l'ajoute au début de la liste
        database_reports.insert(0, new_report)
        return jsonify({"status": "success", "count": len(database_reports)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reports/delete', methods=['POST'])
def delete_report():
    """Supprime une arnaque"""
    try:
        id_to_delete = request.json.get('id')
        global database_reports
        database_reports = [r for r in database_reports if r["id"] != id_to_delete]
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 3. LE SCANNER (AI) ---

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')

        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        print(f"🔍 Scanning: {token_address}")

        # Appel RugCheck
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, timeout=10)

        if response.status_code != 200:
            return jsonify({"risk": "UNKNOWN", "score": 0, "summary": "Token not found/new."})

        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        risks_list = rc_data.get('risks', [])
        if not risks_list:
            summary = "Clean Analysis: Liquidity locked, Mint disabled."
        else:
            top_risk = risks_list[0].get('name', 'Risk Detected')
            summary = f"SECURITY ALERT: {top_risk}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Neural connection error."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
