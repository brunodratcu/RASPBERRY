from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from auth import hash_password, verify_password, generate_token, token_required
import sqlite3
import os

app = Flask(__name__)
CORS(app)

# ===== BANCO DE DADOS =====
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Tabela de eventos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data TEXT NOT NULL,
            hora TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    ''')
    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')

    # Adiciona usuário admin padrão se não existir
    cursor.execute("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        from auth import hash_password
        senha_hash = hash_password("admin")
        cursor.execute("INSERT INTO usuarios (username, senha) VALUES (?, ?)", ("admin", senha_hash))
    conn.commit()
    conn.close()

# 🔔 Chame a função antes do servidor iniciar
init_db()


# ===== ROTAS PÚBLICAS =====
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    senha = data.get("password")
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT senha FROM usuarios WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user and verify_password(senha, user[0]):
        token = generate_token(username)
        return jsonify({"token": token}), 200
    else:
        return jsonify({"message": "Credenciais inválidas"}), 401

@app.route('/')
def serve_index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# ===== ROTAS PROTEGIDAS =====
@app.route('/api/eventos', methods=['POST'])
@token_required
def adicionar_evento(usuario):
    data = request.get_json()
    nome = data.get('nome')
    data_evento = data.get('data')
    hora_evento = data.get('hora')
    criado_em = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO eventos (nome, data, hora, criado_em) VALUES (?, ?, ?, ?)",
                   (nome, data_evento, hora_evento, criado_em))
    conn.commit()
    conn.close()

    return jsonify({'mensagem': 'Evento cadastrado com sucesso!'}), 201

@app.route('/api/eventos-hoje', methods=['GET'])
@token_required
def eventos_hoje(usuario):
    hoje = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT nome, hora FROM eventos WHERE data = ?", (hoje,))
    eventos = cursor.fetchall()
    conn.close()

    eventos_formatados = [{'nome': nome, 'hora': hora} for nome, hora in eventos]
    return jsonify(eventos_formatados)

# ===== DELETANDO EVENTO CADASTRADO =====
@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
@token_required
def deletar_evento(usuario, evento_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
    conn.commit()
    conn.close()

    return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)      
    app.run(debug=True)