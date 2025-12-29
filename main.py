from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from supabase import create_client, Client
import os

app = Flask(__name__)
# Autorise tout le monde (Wix, Mobile, PC)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- TES CLÉS SUPABASE (CONNECTÉES) ---
SUPABASE_URL = "https://jbciscdzfnvzpvxqxkcq.supabase.co"
# Note : Si cette clé ne marche pas, essaie celle qui commence par "ey..." (plus longue)
SUPABASE_KEY = "sb_publishable_GCxfFIJidoGqIXxyDNFjhQ_RXQwyOP3"

# Connexion à la base de données
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ SUPABASE CONNECTED")
except Exception as e:
    print(f"⚠️ Erreur connexion Supabase: {e}")

@app.route('/', methods=['GET'])
def home():
    return "SOLANA GOLD GUARD V2 [DB ACTIVE]"

# --- 1. RÉCUPÉRER LES RAPPORTS (Pour l'affichage Mobile/PC) ---
@app.route('/reports', methods=['GET'])
def get_reports():
    try:
        # On récupère les 50 derniers rapports validés
        response = supabase.table('reports').select("*").eq('status', 'approved').order('created_at', desc=True).limit(50).execute()
        return jsonify(response.data)
    except Exception as e:
        print(f"Erreur Lecture DB: {e}")
        return jsonify([]), 200 # On renvoie une liste vide pour ne pas faire planter le site

# --- 2. AJOUTER UN RAPPORT (Depuis le formulaire) ---
@app.route('/reports/add', methods=['POST'])
def add_report():
    try:
        data = request.json
        # On crée la donnée à envoyer
        new_row = {
            "target": data.get('target'),
            "description": data.get('desc'),
            "status": "approved", # Auto-approuvé pour la démo
            "reporter_wallet": data.get('wallet', 'Anonymous')
        }
        # Envoi vers Supabase
        supabase.table('reports').insert(new_row).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Erreur Écriture DB: {e}")
        return jsonify({"error": str(e)}), 500

# --- 3. LE SCANNER (RUGCHECK) ---
@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        data = request.json
        token_address = data.get('address')
        if not token_address: return jsonify({"risk": "ERROR", "score": 0, "summary": "No address."}), 400

        # Carte d'identité pour passer les filtres
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        response = requests.get(rugcheck_url, headers=headers, timeout=6)
        
        if response.status_code != 200:
            return jsonify({"score": 0, "risk": "UNKNOWN", "summary": "Token not found or too new."})

        rc_data = response.json()
        danger = rc_data.get('score', 0)
        safety = max(0, min(100, 100 - int(danger / 100)))
        
        risk = "SAFE"
        if safety < 50: risk = "CRITICAL"
        elif safety < 80: risk = "WARNING"
        
        risks = rc_data.get('risks', [])
        summary = f"ALERT: {risks[0].get('name', 'Risk Detected')}" if risks else "Clean Analysis: Liquidity locked, Mint disabled."

        return jsonify({"score": safety, "risk": risk, "summary": summary})

    except Exception as e:
        print(f"Erreur Scan: {e}")
        return jsonify({"risk": "ERROR", "score": 0, "summary": "Scan failed."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
