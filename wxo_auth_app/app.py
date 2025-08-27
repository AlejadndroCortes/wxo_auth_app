import os
import json
from flask import Flask, redirect, request, session, url_for, jsonify, render_template
from msal import ConfidentialClientApplication
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "supersecret")

# Configuración Microsoft Identity
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = os.getenv("REDIRECT_PATH", "/redirect")
SCOPE = ["User.Read"]  # Scopes básicos

@app.route("/")
def index():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("home.html", user=session["user"])

@app.route("/login")
def login():
    cca = ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    auth_url = cca.get_authorization_request_url(
        SCOPE, redirect_uri=url_for("authorized", _external=True)
    )
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():# Aquí manejas el token recibido de Microsoft
    code = request.args.get("code")
    if not code:
        return "Error: no se recibió el código de Microsoft", 400

    cca = ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = cca.acquire_token_by_authorization_code(
        code, scopes=SCOPE, redirect_uri=url_for("authorized", _external=True)
    )

    if "id_token_claims" in result:
        session["user"] = result["id_token_claims"]
        return redirect(url_for("index"))
    return "Error al autenticar", 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={url_for('index', _external=True)}"
    )

@app.route("/me")
def me():
    if "user" in session:
        return jsonify({"authenticated": True, "user": session["user"]})
    return jsonify({"authenticated": False})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

    