from flask import Flask, redirect, url_for, session, request, jsonify, make_response
from flask_session import Session
from datetime import timedelta, datetime, timezone
import os
import msal
import jwt

# --------------------------
# Configuration
# --------------------------
# Load config from environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
AUTHORITY = os.getenv("AUTHORITY", f"https://login.microsoftonline.com/{TENANT_ID}")
REDIRECT_PATH = os.getenv("REDIRECT_PATH", "/redirect")
SCOPES = os.getenv("SCOPES", "openid profile email").split()
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", os.urandom(24))
SESSION_TYPE = os.getenv("SESSION_TYPE", "filesystem")  # For demo; use Redis/Memcached in prod
INTERNAL_JWT_SECRET = os.getenv("INTERNAL_JWT_SECRET")  # Secret shared with your gateway/agent
INTERNAL_JWT_AUDIENCE = os.getenv("INTERNAL_JWT_AUDIENCE", "watsonx-orchestrate")
INTERNAL_JWT_ISSUER = os.getenv("INTERNAL_JWT_ISSUER", "wxo-auth-service")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")  # 'Lax' or 'Strict' recommended

if not CLIENT_ID or not CLIENT_SECRET or not TENANT_ID:
    raise RuntimeError("Missing required env vars: CLIENT_ID, CLIENT_SECRET, TENANT_ID")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SESSION_SECRET_KEY,
    SESSION_TYPE=SESSION_TYPE,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=int(os.getenv("SESSION_TTL_MIN", "60"))),
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE=COOKIE_SAMESITE,
)

Session(app)

def _build_redirect_uri():
    # Build absolute redirect URI for OIDC code flow
    return request.url_root.strip("/") + REDIRECT_PATH

def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache
    )

def _init_auth_flow():
    return _build_msal_app().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=_build_redirect_uri(),
        # MSAL handles PKCE automatically for web apps; state/nonce managed in the flow
    )

def _get_user_from_id_token(id_token_claims: dict):
    # Normalize useful user info
    return {
        "sub": id_token_claims.get("sub"),
        "name": id_token_claims.get("name") or id_token_claims.get("preferred_username"),
        "email": id_token_claims.get("preferred_username") or id_token_claims.get("email"),
        "oid": id_token_claims.get("oid"),
        "tid": id_token_claims.get("tid"),
        "roles": id_token_claims.get("roles") or id_token_claims.get("groups") or [],
    }

def _mint_internal_jwt(user: dict, ttl_minutes: int = 60):
    if not INTERNAL_JWT_SECRET:
        return None
    now = datetime.now(timezone.utc)
    payload = {
        "iss": INTERNAL_JWT_ISSUER,
        "aud": INTERNAL_JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        # standard identity fields
        "sub": user.get("sub") or user.get("oid"),
        "name": user.get("name"),
        "email": user.get("email"),
        "tid": user.get("tid"),
        "roles": user.get("roles"),
    }
    token = jwt.encode(payload, INTERNAL_JWT_SECRET, algorithm="HS256")
    return token

@app.route("/")
def index():
    authed = bool(session.get("user"))
    return jsonify({
        "message": "wxo-auth-app is running",
        "authenticated": authed,
        "user": session.get("user") if authed else None
    })

@app.route("/login")
def login():
    flow = _init_auth_flow()
    session["auth_flow"] = flow
    return redirect(flow["auth_uri"])

@app.route(REDIRECT_PATH, methods=["GET", "POST"])
def authorized():
    if "auth_flow" not in session:
        return redirect(url_for("login"))
    flow = session.get("auth_flow")
    try:
        result = _build_msal_app().acquire_token_by_auth_code_flow(flow, request.args)
    except ValueError:
        # Likely caused by CSRF or incorrectly formed request
        session.pop("auth_flow", None)
        return make_response(("Invalid auth request", 400))
    if "error" in result:
        # Authentication/consent failed
        session.pop("auth_flow", None)
        return make_response((json.dumps(result, indent=2), 401, {"Content-Type": "application/json"}))
    # Success
    id_token_claims = result.get("id_token_claims", {})
    user = _get_user_from_id_token(id_token_claims)
    session["user"] = user
    session["tokens"] = {
        "id_token": result.get("id_token"),
        "access_token": result.get("access_token"),
        "expires_in": result.get("expires_in"),
        "scope": result.get("scope"),
        "token_type": result.get("token_type"),
    }
    session.permanent = True
    # Optionally redirect back to a front-end/chat URL passed as 'state_return'
    return_url = request.args.get("state_return") or url_for("me", _external=True)
    return redirect(return_url)

@app.route("/me")
def me():
    if "user" not in session:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": session["user"]})

@app.route("/assertion")
def assertion():
    """Endpoint for Watsonx/your gateway to fetch an internal signed JWT asserting the user's identity.
       Requires the user to have an active session (cookie)."""
    if "user" not in session:
        return jsonify({"error": "not_authenticated"}), 401
    token = _mint_internal_jwt(session["user"], ttl_minutes=int(os.getenv("INTERNAL_JWT_TTL_MIN", "60")))
    if not token:
        return jsonify({"error": "internal_jwt_not_configured"}), 500
    return jsonify({"token": token})

@app.route("/logout")
def logout():
    # Clear local session
    session.clear()
    # Optionally, also sign out from Microsoft by redirecting to the logout endpoint
    post_logout_redirect_uri = request.args.get("post_logout_redirect_uri") or (request.url_root.rstrip("/") + "/")
    ms_logout = f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={post_logout_redirect_uri}"
    return redirect(ms_logout)

if __name__ == "__main__":
    # For local dev only. Use a real WSGI server (gunicorn/uwsgi) and HTTPS in production.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=os.getenv("FLASK_DEBUG", "false").lower()=="true")
