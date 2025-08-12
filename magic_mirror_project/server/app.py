from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from auth import hash_password, verify_password, generate_token, token_required
import sqlite3
import os
import requests
import json
import threading
import time
import logging

app = Flask(__name__)
CORS(app)

# Configurações do Raspberry Pico
PICO_IPS = []  # Lista de IPs dos Picos conectados - será preenchida automaticamente
PICO_PORT = 80
AUTO_DISCOVER_PICOS = True
SYNC_INTERVAL = 60  # Sincronização a cada 60 segundos
MAX_RETRY_ATTEMPTS = 3

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            criado_em TEXT NOT NULL,
            sincronizado INTEGER DEFAULT 0,
            tentativas_sync INTEGER DEFAULT 0
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
            name TEXT DEFAULT 'Pico Desconhecido',
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Adiciona usuário admin padrão se não existir
    cursor.execute("SELECT * FROM usuarios WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        senha_hash = hash_password("admin")
        cursor.execute("INSERT INTO usuarios (username, senha) VALUES (?, ?)", ("admin", senha_hash))
    
    conn.commit()
    conn.close()
    logger.info("📚 Banco de dados inicializado")

# ===== FUNÇÕES DE DESCOBERTA E SINCRONIZAÇÃO =====
def descobrir_picos_na_rede():
    """Descobre automaticamente dispositivos Pico na rede local"""
    global PICO_IPS
    import subprocess
    import ipaddress
    import concurrent.futures
    
    def testar_ip_pico(ip_str):
        """Testa se um IP específico é um Pico"""
        try:
            response = requests.get(
                f"http://{ip_str}:{PICO_PORT}/api/pico-id", 
                timeout=2,
                headers={'User-Agent': 'FlaskEventSync/1.0'}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('device_type') == 'pico':
                    logger.info(f"📱 Pico encontrado: {ip_str} - {data.get('name', 'Sem nome')}")
                    return {
                        'ip': ip_str,
                        'name': data.get('name', 'Pico Desconhecido'),
                        'display': data.get('display', 'ILI9341')
                    }
        except:
            pass
        return None
    
    try:
        # Obtém a rede local
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        local_ip = result.stdout.strip().split()[0]
        network = ipaddress.IPv4Network(f"{'.'.join(local_ip.split('.')[:-1])}.0/24", strict=False)
        
        logger.info(f"🔍 Procurando Picos na rede {network}")
        picos_encontrados = []
        
        # Usa ThreadPoolExecutor para testar IPs em paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            # Testa apenas uma faixa menor para ser mais rápido
            ips_para_testar = [str(ip) for ip in list(network.hosts())[1:50]]  # Primeiros 50 IPs
            
            future_to_ip = {executor.submit(testar_ip_pico, ip): ip for ip in ips_para_testar}
            
            for future in concurrent.futures.as_completed(future_to_ip, timeout=30):
                result = future.result()
                if result:
                    picos_encontrados.append(result)
        
        # Atualiza lista global
        PICO_IPS = [pico['ip'] for pico in picos_encontrados]
        
        # Atualiza banco de dados
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        for pico in picos_encontrados:
            cursor.execute('''
                INSERT OR REPLACE INTO pico_devices (ip_address, name, status, last_sync) 
                VALUES (?, ?, ?, ?)
            ''', (pico['ip'], pico['name'], 'online', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ {len(picos_encontrados)} Picos descobertos")
        return picos_encontrados
        
    except Exception as e:
        logger.error(f"❌ Erro ao descobrir Picos: {e}")
        return []

def verificar_pico_online(pico_ip):
    """Verifica se um Pico específico está online"""
    try:
        response = requests.get(
            f"http://{pico_ip}:{PICO_PORT}/api/status", 
            timeout=3,
            headers={'User-Agent': 'FlaskEventSync/1.0'}
        )
        return response.status_code == 200
    except:
        return False

def enviar_evento_para_pico(pico_ip, evento_data, retry_count=0):
    """Envia evento específico para um Pico com retry automático"""
    if retry_count >= MAX_RETRY_ATTEMPTS:
        logger.error(f"❌ Máximo de tentativas excedido para Pico {pico_ip}")
        return False
        
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
            timeout=10,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'FlaskEventSync/1.0'
            }
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Evento {evento_data['id']} enviado para Pico {pico_ip}")
            return True
        else:
            logger.warning(f"⚠️ Resposta inesperada do Pico {pico_ip}: {response.status_code}")
            if retry_count < MAX_RETRY_ATTEMPTS - 1:
                time.sleep(2 ** retry_count)  # Backoff exponencial
                return enviar_evento_para_pico(pico_ip, evento_data, retry_count + 1)
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erro de conexão com Pico {pico_ip}: {e}")
        if retry_count < MAX_RETRY_ATTEMPTS - 1:
            time.sleep(2 ** retry_count)  # Backoff exponencial
            return enviar_evento_para_pico(pico_ip, evento_data, retry_count + 1)
        return False

def limpar_eventos_pico(pico_ip):
    """Limpa todos os eventos de um Pico específico"""
    try:
        response = requests.post(
            f"http://{pico_ip}:{PICO_PORT}/api/limpar",
            timeout=5,
            headers={'User-Agent': 'FlaskEventSync/1.0'}
        )
        return response.status_code == 200
    except:
        return False

def atualizar_display_pico(pico_ip):
    """Solicita atualização do display de um Pico"""
    try:
        response = requests.post(
            f"http://{pico_ip}:{PICO_PORT}/api/atualizar",
            timeout=5,
            headers={'User-Agent': 'FlaskEventSync/1.0'}
        )
        return response.status_code == 200
    except:
        return False

def sincronizar_todos_eventos_hoje():
    """Sincroniza todos os eventos de hoje com todos os Picos online"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Busca eventos de hoje
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, hora, data, sincronizado, tentativas_sync 
        FROM eventos 
        WHERE data = ? 
        ORDER BY hora
    """, (hoje,))
    eventos_hoje = cursor.fetchall()
    
    if not eventos_hoje:
        logger.info("📅 Nenhum evento para hoje")
        conn.close()
        return {"sincronizados": 0, "erros": 0, "picos": 0}
    
    # Descobre/atualiza lista de Picos se necessário
    if AUTO_DISCOVER_PICOS and (not PICO_IPS or len(PICO_IPS) == 0):
        descobrir_picos_na_rede()
    
    if not PICO_IPS:
        logger.warning("⚠️ Nenhum Pico descoberto na rede")
        conn.close()
        return {"sincronizados": 0, "erros": 0, "picos": 0}
    
    eventos_sincronizados = 0
    erros_sincronizacao = 0
    picos_online = 0
    
    # Sincroniza com cada Pico
    for pico_ip in PICO_IPS:
        if not verificar_pico_online(pico_ip):
            logger.warning(f"⚠️ Pico {pico_ip} offline - pulando sincronização")
            continue
            
        picos_online += 1
        logger.info(f"🔄 Sincronizando com Pico {pico_ip}")
        
        # Limpa eventos antigos do Pico
        limpar_eventos_pico(pico_ip)
        
        # Envia cada evento de hoje
        for evento_id, nome, hora, data, sincronizado, tentativas in eventos_hoje:
            evento_data = {
                "id": evento_id,
                "nome": nome,
                "hora": hora,
                "data": data
            }
            
            if enviar_evento_para_pico(pico_ip, evento_data):
                eventos_sincronizados += 1
                # Atualiza status no banco
                cursor.execute("""
                    UPDATE eventos 
                    SET sincronizado = 1, tentativas_sync = tentativas_sync + 1 
                    WHERE id = ?
                """, (evento_id,))
            else:
                erros_sincronizacao += 1
                # Incrementa tentativas
                cursor.execute("""
                    UPDATE eventos 
                    SET tentativas_sync = tentativas_sync + 1 
                    WHERE id = ?
                """, (evento_id,))
        
        # Atualiza display do Pico
        atualizar_display_pico(pico_ip)
        
        # Atualiza status do Pico no banco
        cursor.execute("""
            UPDATE pico_devices 
            SET status = 'online', last_sync = ? 
            WHERE ip_address = ?
        """, (datetime.now().isoformat(), pico_ip))
    
    conn.commit()
    conn.close()
    
    resultado = {
        "sincronizados": eventos_sincronizados,
        "erros": erros_sincronizacao,
        "picos": picos_online,
        "eventos_total": len(eventos_hoje)
    }
    
    logger.info(f"📱 Sincronização concluída: {resultado}")
    return resultado

# ===== THREAD DE SINCRONIZAÇÃO AUTOMÁTICA =====
def thread_sincronizacao_automatica():
    """Thread que executa sincronização automática em intervalos regulares"""
    logger.info("🔄 Thread de sincronização automática iniciada")
    
    while True:
        try:
            logger.info("🕐 Iniciando sincronização automática...")
            resultado = sincronizar_todos_eventos_hoje()
            
            if resultado["picos"] > 0:
                logger.info(f"✅ Sincronização automática concluída - {resultado['sincronizados']} eventos enviados para {resultado['picos']} Picos")
            else:
                logger.warning("⚠️ Nenhum Pico online para sincronização")
            
            time.sleep(SYNC_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Erro na thread de sincronização: {e}")
            time.sleep(30)  # Aguarda menos tempo em caso de erro

def iniciar_sincronizacao_automatica():
    """Inicia a thread de sincronização em background"""
    thread = threading.Thread(target=thread_sincronizacao_automatica, daemon=True)
    thread.start()
    logger.info("🚀 Sistema de sincronização automática iniciado")

# ===== INICIALIZAÇÃO =====
init_db()
iniciar_sincronizacao_automatica()

# Descobre Picos na inicialização (em thread separada para não bloquear)
if AUTO_DISCOVER_PICOS:
    threading.Thread(target=descobrir_picos_na_rede, daemon=True).start()

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
    cursor.execute("INSERT INTO eventos (nome, data, hora, criado_em, sincronizado, tentativas_sync) VALUES (?, ?, ?, ?, ?, ?)",
                   (nome, data_evento, hora_evento, criado_em, 0, 0))
    evento_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"📝 Novo evento criado: {nome} em {data_evento} às {hora_evento}")

    # Se o evento for para hoje, tenta sincronizar imediatamente
    hoje = datetime.now().strftime('%Y-%m-%d')
    if data_evento == hoje:
        logger.info(f"🆕 Evento para hoje detectado - iniciando sincronização imediata")
        
        # Descobre Picos se lista estiver vazia
        if not PICO_IPS:
            descobrir_picos_na_rede()
        
        # Envia para todos os Picos online
        evento_data = {
            "id": evento_id,
            "nome": nome,
            "hora": hora_evento,
            "data": data_evento
        }
        
        sincronizacao_realizada = False
        for pico_ip in PICO_IPS:
            if verificar_pico_online(pico_ip):
                if enviar_evento_para_pico(pico_ip, evento_data):
                    atualizar_display_pico(pico_ip)
                    sincronizacao_realizada = True
        
        # Atualiza status de sincronização se pelo menos um Pico recebeu
        if sincronizacao_realizada:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE eventos SET sincronizado = 1, tentativas_sync = 1 WHERE id = ?", (evento_id,))
            conn.commit()
            conn.close()

    return jsonify({'mensagem': 'Evento cadastrado com sucesso!', 'id': evento_id}), 201

@app.route('/api/eventos-hoje', methods=['GET'])
@token_required
def eventos_hoje(usuario):
    hoje = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, hora, sincronizado FROM eventos WHERE data = ? ORDER BY hora", (hoje,))
    eventos = cursor.fetchall()
    conn.close()

    eventos_formatados = [
        {
            'id': id, 
            'nome': nome, 
            'hora': hora, 
            'sincronizado': bool(sincronizado)
        } 
        for id, nome, hora, sincronizado in eventos
    ]

    return jsonify(eventos_formatados)

@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
@token_required
def deletar_evento(usuario, evento_id):
    # Verifica se o evento existe
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
    
    logger.info(f"🗑️ Evento {evento_id} removido do banco de dados")
    
    # Se era de hoje e estava sincronizado, remove de todos os Picos também
    if data_evento == hoje and sincronizado:
        for pico_ip in PICO_IPS:
            if verificar_pico_online(pico_ip):
                try:
                    payload = {"id": evento_id, "acao": "deletar"}
                    requests.post(f"http://{pico_ip}:{PICO_PORT}/api/evento", json=payload, timeout=5)
                    atualizar_display_pico(pico_ip)
                    logger.info(f"🗑️ Evento {evento_id} removido do Pico {pico_ip}")
                except Exception as e:
                    logger.error(f"❌ Erro ao remover evento do Pico {pico_ip}: {e}")
    
    return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200

@app.route('/api/eventos', methods=['DELETE'])
@token_required
def deletar_todos_eventos(usuario):
    # Limpa todos os eventos de todos os Picos primeiro
    for pico_ip in PICO_IPS:
        if verificar_pico_online(pico_ip):
            try:
                limpar_eventos_pico(pico_ip)
                atualizar_display_pico(pico_ip)
                logger.info(f"🗑️ Todos os eventos removidos do Pico {pico_ip}")
            except Exception as e:
                logger.error(f"❌ Erro ao limpar Pico {pico_ip}: {e}")
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos")
    conn.commit()
    conn.close()
    
    logger.info("🗑️ Todos os eventos removidos do banco de dados")
    
    return jsonify({'mensagem': 'Todos os eventos foram excluídos com sucesso!'}), 200

# ===== ROTAS DE GERENCIAMENTO DE PICOS =====
@app.route('/api/picos/descobrir', methods=['POST'])
@token_required
def descobrir_picos_manual(usuario):
    """Força descoberta manual de Picos"""
    logger.info("🔍 Iniciando descoberta manual de Picos...")
    picos = descobrir_picos_na_rede()
    return jsonify({
        'mensagem': f'{len(picos)} Picos descobertos',
        'picos': picos
    }), 200

@app.route('/api/picos/status', methods=['GET'])
@token_required
def status_todos_picos(usuario):
    """Retorna status de todos os Picos conhecidos"""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT ip_address, name, last_sync, status FROM pico_devices")
    picos_db = cursor.fetchall()
    conn.close()
    
    status_picos = []
    
    for ip, name, last_sync, status_db in picos_db:
        online = verificar_pico_online(ip)
        status_picos.append({
            'ip': ip,
            'name': name,
            'online': online,
            'last_sync': last_sync,
            'status_db': status_db,
            'url': f'http://{ip}:{PICO_PORT}'
        })
        
        # Atualiza status no banco se mudou
        if (online and status_db != 'online') or (not online and status_db != 'offline'):
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            novo_status = 'online' if online else 'offline'
            cursor.execute("UPDATE pico_devices SET status = ? WHERE ip_address = ?", (novo_status, ip))
            conn.commit()
            conn.close()
    
    return jsonify({
        'picos': status_picos,
        'total': len(status_picos),
        'online': sum(1 for p in status_picos if p['online']),
        'descoberta_automatica': AUTO_DISCOVER_PICOS,
        'intervalo_sync': SYNC_INTERVAL
    }), 200

@app.route('/api/picos/sincronizar', methods=['POST'])
@token_required
def sincronizar_manual(usuario):
    """Força sincronização manual com todos os Picos"""
    logger.info("🔄 Iniciando sincronização manual...")
    resultado = sincronizar_todos_eventos_hoje()
    
    return jsonify({
        'mensagem': 'Sincronização manual concluída!',
        'resultado': resultado
    }), 200

@app.route('/api/picos/adicionar', methods=['POST'])
@token_required
def adicionar_pico_manual(usuario):
    """Adiciona um Pico manualmente pelo IP"""
    data = request.get_json()
    ip = data.get('ip')
    name = data.get('name', 'Pico Manual')
    
    if not ip:
        return jsonify({'erro': 'IP é obrigatório'}), 400
    
    # Verifica se o Pico responde
    if verificar_pico_online(ip):
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices (ip_address, name, status, last_sync) 
            VALUES (?, ?, ?, ?)
        ''', (ip, name, 'online', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Adiciona à lista global se não estiver
        if ip not in PICO_IPS:
            PICO_IPS.append(ip)
        
        logger.info(f"📱 Pico adicionado manualmente: {ip} - {name}")
        return jsonify({'mensagem': f'Pico {ip} adicionado com sucesso!'}), 200
    else:
        return jsonify({'erro': f'Pico {ip} não responde ou não é válido'}), 400

@app.route('/api/sistema/info', methods=['GET'])
@token_required
def info_sistema(usuario):
    """Retorna informações do sistema de sincronização"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Conta eventos de hoje
    cursor.execute("SELECT COUNT(*) FROM eventos WHERE data = ?", (hoje,))
    eventos_hoje_count = cursor.fetchone()[0]
    
    # Conta eventos sincronizados
    cursor.execute("SELECT COUNT(*) FROM eventos WHERE data = ? AND sincronizado = 1", (hoje,))
    eventos_sincronizados = cursor.fetchone()[0]
    
    # Conta Picos
    cursor.execute("SELECT COUNT(*) FROM pico_devices")
    total_picos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pico_devices WHERE status = 'online'")
    picos_online = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'eventos_hoje': eventos_hoje_count,
        'eventos_sincronizados': eventos_sincronizados,
        'total_picos': total_picos,
        'picos_online': picos_online,
        'descoberta_automatica': AUTO_DISCOVER_PICOS,
        'intervalo_sincronizacao': SYNC_INTERVAL,
        'max_tentativas': MAX_RETRY_ATTEMPTS,
        'versao': '2.0',
        'data_atual': hoje
    }), 200

if __name__ == '__main__':
    logger.info("🚀 Iniciando servidor Flask com sincronização automática Pico...")
    logger.info(f"🔧 Configurações: Auto-discover={AUTO_DISCOVER_PICOS}, Sync={SYNC_INTERVAL}s")
    app.run(host='0.0.0.0', port=5000, debug=True)
