from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
# IMPORTANT : Cela permet à ton site Wix de communiquer avec ce serveur
CORS(app)

@app.route('/', methods=['GET'])
def home():
    return "Solana Gold Guard AI is ONLINE 🟢"

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        # 1. Récupérer l'adresse envoyée par le site
        data = request.json
        token_address = data.get('address')

        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "Adresse manquante."}), 400

        print(f"🔍 Scanning: {token_address}")

        # 2. Interroger l'API RugCheck (Version Summary pour la rapidité)
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        
        # On met un timeout de 10s pour ne pas faire planter le serveur si RugCheck est lent
        response = requests.get(rugcheck_url, timeout=10)

        # Si le token est inconnu ou trop récent
        if response.status_code != 200:
            return jsonify({
                "risk": "UNKNOWN", 
                "score": 0, 
                "summary": "Token introuvable ou trop récent sur la blockchain. Soyez prudent."
            })

        rc_data = response.json()

        # 3. Calcul du Score (Conversion Logique 10M MC)
        # RugCheck donne un score de DANGER (ex: 5000). On veut un score de SÉCURITÉ (0-100).
        danger_score = rc_data.get('score', 0)
        
        # Formule : 100 - (Danger / 100). On garde le résultat entre 0 et 100.
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 4. Définition du Label (Vert / Orange / Rouge)
        risk_label = "SAFE"
        if safety_score < 50:
            risk_label = "CRITICAL" # Rouge
        elif safety_score < 80:
            risk_label = "WARNING"  # Orange

        # 5. Création du Résumé (Summary) pour le Dashboard
        risks_list = rc_data.get('risks', [])
        
        if not risks_list:
            summary = "Analyse terminée : Liquidité verrouillée, Mint désactivé. Aucun risque majeur détecté."
        else:
            # On prend le risque le plus critique pour l'afficher
            top_risk = risks_list[0].get('name', 'Risque détecté')
            summary = f"ALERTE SÉCURITÉ : {top_risk}. Une inspection manuelle est recommandée."

        # 6. Envoi de la réponse au site
        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary
        })

    except Exception as e:
        print(f"❌ Erreur interne : {e}")
        return jsonify({
            "risk": "ERROR", 
            "score": 0, 
            "summary": "Erreur de connexion au noeud neuronal. Veuillez réessayer."
        }), 500

if __name__ == '__main__':
    # Port 10000 est standard pour Render
    app.run(host='0.0.0.0', port=10000)
