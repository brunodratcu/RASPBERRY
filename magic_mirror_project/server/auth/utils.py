import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

import jwt
from functools import wraps
from flask import request, jsonify

SECRET_KEY = "sua_chave_secreta"  # Troque por uma chave forte
"""
def get_hashed_password(password):
    return generate_password_hash(password)

def check_password(password, hashed):
    return check_password_hash(hashed, password)
"""
def hash_password(password):
    return generate_password_hash(password)

def verify_password(password, hashed):
    return check_password_hash(hashed, password)

def init_db():
    conn = sqlite3.connect("db/database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            date TEXT,
            time TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_event(name, date, time):
    conn = sqlite3.connect("db/database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (name, date, time) VALUES (?, ?, ?)", (name, date, time))
    conn.commit()
    conn.close()





def generate_token(username):
    payload = {"username": username}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        if not token:
            return jsonify({'message': 'Token ausente!'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = data['username']
        except Exception:
            return jsonify({'message': 'Token inválido!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated