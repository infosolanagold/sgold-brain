from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
# 1. AUTORISER TOUT LE MONDE (Wix, Local, Mobile)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/', methods=['GET'])
def home():
    return "SERVER ONLINE. WAITING FOR SCANS..."

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        print(f"🔍 Scanning: {token_address}")

        # 2. AJOUT D'UNE CARTE D'IDENTITÉ (User-Agent)
        # Sinon RugCheck bloque la requête en pensant que c'est un robot méchant
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, headers=headers, timeout=8)

        if response.status_code != 200:
            print(f"⚠️ RugCheck Error: {response.status_code}")
            # On renvoie une structure valide même si le token est inconnu
            return jsonify({
                "score": 0, 
                "risk": "UNKNOWN", 
                "summary": "Token too new or not found in database."
            })

        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        risk_label = "SAFE"
        if safety_score < 50: risk_label = "CRITICAL"
        elif safety_score < 80: risk_label = "WARNING"

        risks_list = rc_data.get('risks', [])
        summary = "Clean Analysis: Liquidity locked." if not risks_list else f"ALERT: {risks_list[0].get('name', 'Risk Detected')}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})

    except Exception as e:
        print(f"❌ Internal Error: {str(e)}")
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Scan failed."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
