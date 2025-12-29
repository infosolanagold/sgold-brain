from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

# ==========================================
# ⚠️ REMETS TES CLÉS ICI (Attention aux espaces !)
# ==========================================
JSONBIN_ID = "COLLE_TON_BIN_ID_ICI"      # Ex: 676eff...
JSONBIN_KEY = "COLLE_TA_MASTER_KEY_ICI"  # Ex: $2a$10...
# ==========================================

BASE_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
HEADERS = {
    "Content-Type": "application/json",
    "X-Master-Key": JSONBIN_KEY
}

# --- FONCTIONS DATABASE BLINDÉES ---

def save_db(data):
    """Sauvegarde les données (Force la réparation si besoin)"""
    try:
        response = requests.put(BASE_URL, json=data, headers=HEADERS)
        if response.status_code == 200:
            print("✅ Sauvegarde réussie.")
            return True
        else:
            print(f"❌ Erreur Save: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Crash Save: {e}")
        return False

def load_db():
    """Charge les données et RÉPARE si le JSON est invalide"""
    try:
        response = requests.get(f"{BASE_URL}/latest", headers=HEADERS)
        
        if response.status_code != 200:
            print(f"⚠️ Erreur lecture ({response.status_code})... Tentative de réparation.")
            save_db([]) # On crée une liste vide pour réparer
            return []

        # Tente de lire le JSON
        try:
            data = response.json()
            # JSONBin v3 met les données dans "record". Si "record" n'existe pas, on prend tout.
            return data.get("record", [])
        except json.JSONDecodeError:
            print("⚠️ Le contenu du Bin n'est pas du JSON valide ! Réparation...")
            save_db([]) # Le fichier était corrompu, on remet à zéro
            return []

    except Exception as e:
        print(f"❌ Crash total Load: {e}")
        return []

# --- DÉMARRAGE ---
print("🔄 Connexion au Cloud...")
database_reports = load_db()
print(f"🟢 Démarrage réussi : {len(database_reports)} rapports en mémoire.")

@app.route('/', methods=['GET'])
def home():
    return f"Solana Gold Guard AI ONLINE. {len(database_reports)} Threats tracked."

@app.route('/reports', methods=['GET'])
def get_reports():
    # On recharge pour être à jour
    global database_reports
    database_reports = load_db()
    return jsonify(database_reports)

@app.route('/reports/add', methods=['POST'])
def add_report():
    try:
        new_report = request.json
        current_data = load_db()
        current_data.insert(0, new_report) # Ajoute en haut de la liste
        
        if save_db(current_data):
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Cloud Save Failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reports/delete', methods=['POST'])
def delete_report():
    try:
        id_to_delete = request.json.get('id')
        current_data = load_db()
        # On garde tout SAUF l'id qu'on veut supprimer
        updated_data = [r for r in current_data if r["id"] != id_to_delete]
        
        if save_db(updated_data):
            return jsonify({"status": "deleted"})
        else:
            return jsonify({"error": "Cloud Delete Failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- SCANNER (RUGCHECK) ---
@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

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
        summary = "Clean Analysis: Liquidity locked, Mint disabled." if not risks_list else f"SECURITY ALERT: {risks_list[0].get('name', 'Risk')}."

        return jsonify({"score": safety_score, "risk": risk_label, "summary": summary})

    except Exception as e:
        return jsonify({"risk": "ERROR", "score": 0, "summary": "System Error."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
