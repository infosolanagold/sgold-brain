from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
# Autorise ton site Wix à parler au serveur
CORS(app)

# --- 1. LA DATABASE COMPLÈTE (Tes 6 Exemples) ---
database_reports = [
    {
        "id": 101, 
        "target": "Fake_JUP_Airdrop", 
        "desc": "Phishing site asking for seed phrase. Hosting on unverified domain.", 
        "status": "approved", 
        "img": None
    },
    {
        "id": 102, 
        "target": "Bonk_Killer_V2", 
        "desc": "Mint Authority enabled. Liquidity not locked. Dev dumping.", 
        "status": "approved", 
        "img": None
    },
    {
        "id": 103, 
        "target": "Solana_Printer_DAO", 
        "desc": "Honeypot detected. Transfer fee set to 99%.", 
        "status": "approved", 
        "img": None
    },
    {
        "id": 104, 
        "target": "Rug_Master_69", 
        "desc": "Serial rugger wallet detected. Linked to 15 prior scams.", 
        "status": "approved", 
        "img": None
    },
    {
        "id": 105, 
        "target": "Tesla_Token_Official", 
        "desc": "Impersonation scam. Mutable metadata.", 
        "status": "approved", 
        "img": None
    },
    {
        "id": 106, 
        "target": "Free_SOL_Claim", 
        "desc": "Wallet drainer script embedded in connect button.", 
        "status": "approved", 
        "img": None
    }
]

@app.route('/', methods=['GET'])
def home():
    return "Solana Gold Guard AI is ONLINE 🟢"

# --- 2. GESTION DES RAPPORTS ---

@app.route('/reports', methods=['GET'])
def get_reports():
    # Envoie la liste des 6 arnaques au site Wix
    return jsonify(database_reports)

@app.route('/reports/add', methods=['POST'])
def add_report():
    try:
        new_report = request.json
        # On ajoute le nouveau rapport en haut de la liste
        database_reports.insert(0, new_report)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reports/delete', methods=['POST'])
def delete_report():
    try:
        id_to_delete = request.json.get('id')
        global database_reports
        database_reports = [r for r in database_reports if r["id"] != id_to_delete]
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 3. SCANNER INTELLIGENT (RugCheck) ---

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')

        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address provided."}), 400

        print(f"🔍 Scanning: {token_address}")

        # Interroger RugCheck
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, timeout=10)

        if response.status_code != 200:
            return jsonify({
                "risk": "UNKNOWN", 
                "score": 0, 
                "summary": "Token not found or too new on chain."
            })

        rc_data = response.json()

        # Calcul du Score
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # Label
        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        # Résumé (Anglais)
        risks_list = rc_data.get('risks', [])
        if not risks_list:
            summary = "Clean Analysis: Liquidity locked, Mint disabled."
        else:
            top_risk = risks_list[0].get('name', 'Potential Risk')
            summary = f"SECURITY ALERT: {top_risk}. Manual inspection recommended."

        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Neural Node Error."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
