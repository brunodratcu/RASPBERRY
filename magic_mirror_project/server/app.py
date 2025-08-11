from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from auth import hash_password, verify_password, generate_token, token_required
import sqlite3
import os

app = Flask(__name__)
CORS(app)


#DB_PATH = "db/database.db"
#PICO_IP = "192.168.0.150"  # <-- Substituir pelo IP do Pico W


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
       # Tabela de dispositivos Pico conectados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            name TEXT,
            last_sync TEXT,
            status TEXT DEFAULT 'offline'
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
#==================================================================
# ===== FUNÇÕES DE SINCRONIZAÇÃO COM PICO =====
def descobrir_picos():
    """Descobre automaticamente dispositivos Pico na rede local"""
    global PICO_IPS
    import subprocess
    import ipaddress
    
    # Obtém a rede local (exemplo: 192.168.1.0/24)
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        local_ip = result.stdout.strip().split()[0]
        network = ipaddress.IPv4Network(f"{'.'.join(local_ip.split('.')[:-1])}.0/24", strict=False)
        
        picos_encontrados = []
        print(f"🔍 Procurando Picos na rede {network}")
        
        # Testa IPs na faixa da rede local
        for ip in network.hosts():
            ip_str = str(ip)
            try:
                response = requests.get(f"http://{ip_str}:{PICO_PORT}/api/pico-id", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('device_type') == 'pico':
                        picos_encontrados.append(ip_str)
                        print(f"📱 Pico encontrado: {ip_str} - {data.get('name', 'Sem nome')}")
            except:
                continue
        
        PICO_IPS = picos_encontrados
        
        # Atualiza banco de dados com Picos encontrados
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        for ip in picos_encontrados:
            cursor.execute("INSERT OR REPLACE INTO pico_devices (ip_address, status) VALUES (?, ?)", 
                          (ip, 'online'))
        conn.commit()
        conn.close()
        
        print(f"✅ {len(picos_encontrados)} Picos descobertos")
        return picos_encontrados
        
    except Exception as e:
        print(f"❌ Erro ao descobrir Picos: {e}")
        return []

def enviar_evento_para_pico(pico_ip, evento_data):
    """Envia evento específico para um Pico"""
    try:
        payload = {
            "id": evento_data["id"],
            "nome": evento_data["nome"],
            "hora": evento_data["hora"],
            "data": evento_data.get("data"),
            "acao": "adicionar"
        }
        
        response = requests.post(
            f"http://{pico_ip}:{PICO_PORT}/api/evento", 
            json=payload, 
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Evento {evento_data['id']} enviado para Pico {pico_ip}")
            return True
        else:
            print(f"❌ Erro ao enviar evento para {pico_ip}: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro de conexão com Pico {pico_ip}: {e}")
        return False

def sincronizar_todos_eventos_hoje():
    """Sincroniza todos os eventos de hoje com todos os Picos online"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Busca eventos de hoje não sincronizados
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, hora, data FROM eventos WHERE data = ?", (hoje,))
    eventos_hoje = cursor.fetchall()
    
    if not eventos_hoje:
        print("📅 Nenhum evento para hoje")
        conn.close()
        return
    
    # Descobre Picos se necessário
    if AUTO_DISCOVER_PICOS and not PICO_IPS:
        descobrir_picos()
    
    eventos_sincronizados = 0
    
    # Envia eventos para cada Pico online
    for pico_ip in PICO_IPS:
        print(f"🔄 Sincronizando com Pico {pico_ip}")
        
        # Primeiro, limpa eventos antigos do Pico
        try:
            requests.post(f"http://{pico_ip}:{PICO_PORT}/api/limpar", timeout=5)
        except:
            pass
        
        # Envia cada evento
        for evento_id, nome, hora, data in eventos_hoje:
            evento_data = {
                "id": evento_id,
                "nome": nome,
                "hora": hora,
                "data": data
            }
            
            if enviar_evento_para_pico(pico_ip, evento_data):
                eventos_sincronizados += 1
        
        # Solicita atualização do display
        try:
            requests.post(f"http://{pico_ip}:{PICO_PORT}/api/atualizar", timeout=5)
        except:
            pass
    
    # Marca todos os eventos como sincronizados
    cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE data = ?", (hoje,))
    conn.commit()
    conn.close()
    
    print(f"📱 Sincronização concluída: {eventos_sincronizados} eventos enviados")

def verificar_pico_online(pico_ip):
    """Verifica se um Pico específico está online"""
    try:
        response = requests.get(f"http://{pico_ip}:{PICO_PORT}/api/status", timeout=3)
        return response.status_code == 200
    except:
        return False

# ===== THREAD PARA SINCRONIZAÇÃO AUTOMÁTICA =====
def thread_sincronizacao():
    """Thread que roda em background para sincronização automática"""
    while True:
        try:
            print("🔄 Iniciando sincronização automática...")
            sincronizar_todos_eventos_hoje()
            time.sleep(60)  # Sincroniza a cada 1 minuto
        except Exception as e:
            print(f"❌ Erro na thread de sincronização: {e}")
            time.sleep(30)

def iniciar_thread_sincronizacao():
    """Inicia a thread de sincronização em background"""
    thread = threading.Thread(target=thread_sincronizacao, daemon=True)
    thread.start()
    print("🔄 Thread de sincronização automática iniciada")
# ===============================================================

# 🔔 Chame a função antes do servidor iniciar
init_db()

iniciar_thread_sincronizacao()
# Descobre Picos na inicialização
if AUTO_DISCOVER_PICOS:
    threading.Thread(target=descobrir_picos, daemon=True).start()


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

    if not nome or not data_evento or not hora_evento:
        return jsonify({"erro": "Preencha todos os campos"}), 400


    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO eventos (nome, data, hora, criado_em) VALUES (?, ?, ?, ?)",
                   (nome, data_evento, hora_evento, criado_em))
    conn.commit()
    conn.close()





    #============================================================
    # Se o evento for para hoje, sincroniza imediatamente com todos os Picos
    hoje = datetime.now().strftime('%Y-%m-%d')
    if data_evento == hoje:
        print(f"🆕 Novo evento para hoje: {nome} às {hora_evento}")
        
        # Descobre Picos se necessário
        if not PICO_IPS:
            descobrir_picos()
        
        # Envia para todos os Picos online
        evento_data = {
            "id": evento_id,
            "nome": nome,
            "hora": hora_evento,
            "data": data_evento
        }
        
        sucesso_total = True
        for pico_ip in PICO_IPS:
            if enviar_evento_para_pico(pico_ip, evento_data):
                # Solicita atualização do display
                try:
                    requests.post(f"http://{pico_ip}:{PICO_PORT}/api/atualizar", timeout=5)
                except:
                    pass
            else:
                sucesso_total = False
        
        # Marca como sincronizado se pelo menos um Pico recebeu
        if PICO_IPS and sucesso_total:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE id = ?", (evento_id,))
            conn.commit()
            conn.close()

    return jsonify({'mensagem': 'Evento cadastrado com sucesso!'}), 201


"""
    # Se o evento for hoje, envia para o Pico W
    if data_evento == date.today().isoformat():
        try:
            requests.post(f"http://{PICO_IP}/update-event", json={
                "nome": nome,
                "hora": hora_evento
            }, timeout=3)
            print(f"Evento de hoje enviado ao Pico W: {nome} às {hora_evento}")
        except requests.exceptions.RequestException as e:
            print(f"⚠ Erro ao enviar evento para Pico W: {e}")
"""
#    return jsonify({"mensagem": "Evento cadastrado com sucesso"}), 201





@app.route('/api/eventos-hoje', methods=['GET'])
@token_required
def eventos_hoje(usuario):
    hoje = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, hora FROM eventos WHERE data = ?", (hoje,))
    eventos = cursor.fetchall()
    conn.close()


    eventos_formatados = [{'id':id, 'nome': nome, 'hora': hora, 'sincronizado':bool(sincronizado)} for id, nome, hora, sincronizado in eventos]

    return jsonify(eventos_formatados)

"""# ===== DELETANDO EVENTO CADASTRADO =====
@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
@token_required
def deletar_evento(usuario, evento_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
    conn.commit()
    conn.close()
    return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200


# ===== RESETANDO BANCO DE DADOS =====
@app.route('/api/eventos', methods=['DELETE'])
@token_required
def deletar_todos_eventos(usuario):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos")
    conn.commit()
    conn.close()
    return jsonify({'mensagem': 'Todos os eventos foram excluídos com sucesso!'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)      
    app.run(debug=True)"""

@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
@token_required
def deletar_evento(usuario, evento_id):
    # Primeiro verifica se o evento existe e se é de hoje
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT data, sincronizado FROM eventos WHERE id = ?", (evento_id,))
    evento = cursor.fetchone()
    
    if not evento:
        conn.close()
        return jsonify({'mensagem': 'Evento não encontrado!'}), 404
    
    data_evento, sincronizado = evento
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Remove do banco
    cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
    conn.commit()
    conn.close()
    
    # Se era de hoje e estava sincronizado, remove de todos os Picos também
    if data_evento == hoje and sincronizado:
        for pico_ip in PICO_IPS:
            try:
                payload = {"id": evento_id, "acao": "deletar"}
                requests.post(f"http://{pico_ip}:{PICO_PORT}/api/evento", json=payload, timeout=5)
                requests.post(f"http://{pico_ip}:{PICO_PORT}/api/atualizar", timeout=5)
            except:
                pass
    
    return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200

@app.route('/api/eventos', methods=['DELETE'])
@token_required
def deletar_todos_eventos(usuario):
    # Limpa todos os eventos de todos os Picos primeiro
    for pico_ip in PICO_IPS:
        try:
            requests.post(f"http://{pico_ip}:{PICO_PORT}/api/limpar", timeout=5)
            requests.post(f"http://{pico_ip}:{PICO_PORT}/api/atualizar", timeout=5)
        except:
            pass
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos")
    conn.commit()
    conn.close()
    
    return jsonify({'mensagem': 'Todos os eventos foram excluídos com sucesso!'}), 200

# ===== NOVAS ROTAS PARA GERENCIAR PICOS =====
@app.route('/api/picos/descobrir', methods=['POST'])
@token_required
def descobrir_picos_manual(usuario):
    """Descobre Picos manualmente"""
    picos = descobrir_picos()
    return jsonify({
        'mensagem': f'{len(picos)} Picos descobertos',
        'picos': picos
    }), 200

@app.route('/api/picos/status', methods=['GET'])
@token_required
def status_todos_picos(usuario):
    """Verifica status de todos os Picos"""
    status_picos = []
    
    for pico_ip in PICO_IPS:
        online = verificar_pico_online(pico_ip)
        status_picos.append({
            'ip': pico_ip,
            'online': online,
            'url': f'http://{pico_ip}:{PICO_PORT}'
        })
    
    return jsonify({
        'picos': status_picos,
        'total': len(PICO_IPS),
        'online': sum(1 for p in status_picos if p['online'])
    }), 200

@app.route('/api/picos/sincronizar', methods=['POST'])
@token_required
def sincronizar_todos_picos(usuario):
    """Força sincronização manual com todos os Picos"""
    sincronizar_todos_eventos_hoje()
    return jsonify({'mensagem': 'Sincronização realizada com todos os Picos!'}), 200

if __name__ == '__main__':
    print("🚀 Iniciando servidor Flask com sincronização automática...")
    print("🔍 Descoberta automática de Picos habilitada")
    app.run(host='0.0.0.0', port=5000, debug=True)(f"🔗 URL do Pico configurada: {PICO_URL}")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
