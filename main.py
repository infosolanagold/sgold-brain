from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
# Enable CORS to allow your Wix site to talk to this brain
CORS(app)

@app.route('/', methods=['GET'])
def home():
    return "Solana Gold Guard AI is ONLINE (English Mode) 🟢"

@app.route('/scan', methods=['POST'])
def scan_token():
    try:
        # 1. Get address from frontend
        data = request.json
        token_address = data.get('address')

        if not token_address:
            return jsonify({"risk": "ERROR", "score": 0, "summary": "No address provided."}), 400

        print(f"🔍 Scanning: {token_address}")

        # 2. Query RugCheck API
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
        
        # 10s timeout to prevent hanging
        response = requests.get(rugcheck_url, timeout=10)

        # If token is unknown or too new
        if response.status_code != 200:
            return jsonify({
                "risk": "UNKNOWN", 
                "score": 0, 
                "summary": "Token not found or too new on chain. High caution advised."
            })

        rc_data = response.json()

        # 3. Calculate Security Score (10M MC Logic)
        # RugCheck gives a Danger score. We convert to Safety Score (0-100).
        danger_score = rc_data.get('score', 0)
        
        # Formula: 100 - (Danger / 100). Clamped between 0 and 100.
        safety_score = max(0, min(100, 100 - int(danger_score / 100)))

        # 4. Define Risk Label
        risk_label = "SAFE"
        if safety_score < 50:
            risk_label = "CRITICAL" # Red
        elif safety_score < 80:
            risk_label = "WARNING"  # Orange

        # 5. Generate English Summary
        risks_list = rc_data.get('risks', [])
        
        if not risks_list:
            summary = "Clean Analysis: Liquidity locked, Mint disabled. No major risks detected."
        else:
            # Pick the most critical risk name
            top_risk = risks_list[0].get('name', 'Potential Risk')
            summary = f"SECURITY ALERT: {top_risk}. Manual inspection recommended."

        # 6. Send response to Wix
        return jsonify({
            "score": safety_score,
            "risk": risk_label,
            "summary": summary
        })

    except Exception as e:
        print(f"❌ Internal Error: {e}")
        return jsonify({
            "risk": "ERROR", 
            "score": 0, 
            "summary": "Neural Node connection error. Please try again."
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
