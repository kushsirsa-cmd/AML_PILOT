"""Demo authentication + role permissions.

Demo-grade on purpose: one shared password, HMAC-signed bearer tokens, roles read from the users table. Replace with OIDC
(Entra ID / Okta / Cognito) before real use - every route already gets its identity from `deps.current_user`.
"""
import base64
import hashlib
import hmac
import json
import time

from .config import settings

ROLES = ["ANALYST", "SENIOR_ANALYST", "MLRO", "COMPLIANCE_MANAGER", "ADMIN"]
ROLE_LABEL = {"ANALYST": "Analyst", "SENIOR_ANALYST": "Senior Analyst", "MLRO": "MLRO", "COMPLIANCE_MANAGER": "Compliance Manager", "ADMIN": "Admin"}

# who may do what (enforced server-side; the UI only hides buttons)
CAN = {
    "approve_high_risk": {"SENIOR_ANALYST", "MLRO", "COMPLIANCE_MANAGER"},
    "mlro_decision": {"MLRO"},
    "sar_decision": {"MLRO"},
    "report_approve": {"MLRO", "COMPLIANCE_MANAGER"},
    "qa_review": {"SENIOR_ANALYST", "COMPLIANCE_MANAGER"},
    "admin": {"ADMIN"},
}

DEMO_USERS = [
    ("analyst.demo", "Anna Kowalska", "ANALYST", "anna.kowalska@demo.bank"),
    ("senior.demo", "Stefan Nowak", "SENIOR_ANALYST", "stefan.nowak@demo.bank"),
    ("mlro.demo", "Maria Wiśniewska", "MLRO", "maria.wisniewska@demo.bank"),
    ("manager.demo", "Piotr Zieliński", "COMPLIANCE_MANAGER", "piotr.zielinski@demo.bank"),
    ("admin.demo", "Alex Admin", "ADMIN", "alex.admin@demo.bank"),
]


def _sig(payload: str) -> str:
    return hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str, ttl_s: int = 12 * 3600) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": int(time.time()) + ttl_s}).encode()).decode()
    return f"{body}.{_sig(body)}"


def read_token(token: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sig(body)):
            return None
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
        return data["u"] if data["exp"] > time.time() else None
    except Exception:  # noqa: BLE001 - any malformed token is simply invalid
        return None
