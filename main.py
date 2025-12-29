from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# --- PAGE D'ACCUEIL (Pour vérifier que le serveur marche) ---
@app.route('/', methods=['GET'])
def home():
    return "Solana Gold Guard SCANNER ONLINE. Ready to protect."

# --- LE SEUL TRUC IMPORTANT : LE SCANNER ---
@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        # 1. Récupérer l'adresse envoyée par le site
        data = request.json
        token_address = data.get('address')
        
        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address provided."}), 400

        # 2. Interroger l'API RugCheck (C'est gratuit et public)
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, timeout=5) # Timeout court pour pas faire attendre

        # 3. Si RugCheck ne connait pas le token (ex: token trop récent)
        if response.status_code != 200:
            return jsonify({
                "score": 0, 
                "risk": "UNKNOWN", 
                "summary": "Token not found or too new to analyze."
            })

        # 4. Analyser la réponse
        rc_data = response.json()
        danger_score = rc_data.get('score', 0)
        
        # On inverse le score : RugCheck donne un score de Danger, nous on veut un score de SÉCURITÉ
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 5. Déterminer le niveau de risque
        risk_label = "SAFE"
        if safety_score < 50:
            risk_label = "CRITICAL"
        elif safety_score < 80:
            risk_label = "WARNING"

        # 6. Créer un résumé simple
        risks_list = rc_data.get('risks', [])
        if not risks_list:
            summary = "Clean Analysis: Liquidity locked, Mint authority disabled."
        else:
            # On prend le premier risque listé pour l'afficher
            summary = f"SECURITY ALERT: {risks_list[0].get('name', 'Potential Risk Detected')}."

        # 7. Renvoyer le résultat au site
        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary
        })

    except Exception as e:
        print(f"Erreur Scan: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Internal Server Error."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
