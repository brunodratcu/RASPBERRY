# auth.py
import jwt
import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, jsonify

# troque por uma chave segura em produção
SECRET_KEY = "troque_esta_chave_por_uma_super_secreta"

def hash_password(password: str) -> str:
    return generate_password_hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)

def generate_token(identity: str, hours: int = 24*365) -> str:
    """Gera um JWT com expiração em 'hours' horas (default: 1 ano)."""
    payload = {
        "sub": identity,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=hours),
        "iat": datetime.datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    # PyJWT 2.x returns str
    return token

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = None
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
        if not token:
            return jsonify({"message": "Token requerido."}), 401
        user = decode_token(token)
        if not user:
            return jsonify({"message": "Token inválido ou expirado."}), 401
        # passa o identity ao handler
        return f(user, *args, **kwargs)
    return decorated
