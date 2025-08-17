from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
from auth import hash_password, verify_password, generate_token, token_required
import sqlite3
import os
import json
import threading
import time
import logging
import paho.mqtt.client as mqtt
import random

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÕES MQTT =====
MQTT_BROKER = "broker.hivemq.com"  # Broker gratuito
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"flask_server_{random.randint(1000, 9999)}"
MQTT_TOPIC_BASE = "eventos_pico"  # Tópico base
MQTT_KEEP_ALIVE = 60

# Cliente MQTT global
mqtt_client = None
mqtt_connected = False

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
    
    # Tabela de dispositivos Pico conectados (via MQTT)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Pico Desconhecido',
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            topic TEXT,
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

# ===== FUNÇÕES MQTT =====
def on_mqtt_connect(client, userdata, flags, rc):
    """Callback de conexão MQTT"""
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        logger.info("✅ Conectado ao broker MQTT!")
        
        # Subscrever aos tópicos de status dos Picos
        client.subscribe(f"{MQTT_TOPIC_BASE}/+/status")
        client.subscribe(f"{MQTT_TOPIC_BASE}/+/ack")
        logger.info(f"📡 Subscrito aos tópicos: {MQTT_TOPIC_BASE}/+/status e {MQTT_TOPIC_BASE}/+/ack")
    else:
        mqtt_connected = False
        logger.error(f"❌ Falha na conexão MQTT: {rc}")

def on_mqtt_message(client, userdata, msg):
    """Callback para mensagens MQTT recebidas"""
    try:
        topic = msg.topic
        message = msg.payload.decode('utf-8')
        
        logger.info(f"📨 Mensagem MQTT recebida: {topic} -> {message}")
        
        # Extrair client_id do tópico
        topic_parts = topic.split('/')
        if len(topic_parts) >= 3:
            client_id = topic_parts[1]
            message_type = topic_parts[2]
            
            if message_type == "status":
                processar_status_pico(client_id, message)
            elif message_type == "ack":
                processar_ack_pico(client_id, message)
                
    except Exception as e:
        logger.error(f"❌ Erro ao processar mensagem MQTT: {e}")

def processar_status_pico(client_id, message):
    """Processa mensagem de status de um Pico"""
    try:
        data = json.loads(message)
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Atualizar ou inserir Pico no banco
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices (client_id, name, status, last_sync, topic) 
            VALUES (?, ?, ?, ?, ?)
        ''', (
            client_id,
            data.get('name', f'Pico_{client_id}'),
            'online',
            datetime.now().isoformat(),
            f"{MQTT_TOPIC_BASE}/{client_id}"
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📱 Pico {client_id} registrado: {data.get('name', 'Sem nome')}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar status do Pico {client_id}: {e}")

def processar_ack_pico(client_id, message):
    """Processa confirmação de recebimento de evento"""
    try:
        data = json.loads(message)
        evento_id = data.get('evento_id')
        
        if evento_id:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE eventos 
                SET sincronizado = 1, tentativas_sync = tentativas_sync + 1 
                WHERE id = ?
            """, (evento_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Evento {evento_id} confirmado pelo Pico {client_id}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar ACK do Pico {client_id}: {e}")

def inicializar_mqtt():
    """Inicializa cliente MQTT"""
    global mqtt_client
    
    try:
        mqtt_client = mqtt.Client(MQTT_CLIENT_ID)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_message = on_mqtt_message
        
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEP_ALIVE)
        mqtt_client.loop_start()
        
        logger.info(f"🚀 Cliente MQTT iniciado: {MQTT_CLIENT_ID}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar MQTT: {e}")
        return False

def enviar_evento_mqtt(evento_data):
    """Envia evento via MQTT para todos os Picos"""
    global mqtt_client, mqtt_connected
    
    if not mqtt_connected or not mqtt_client:
        logger.error("❌ MQTT não conectado")
        return False
    
    try:
        # Buscar todos os Picos online no banco
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT client_id, topic FROM pico_devices WHERE status = 'online'")
        picos = cursor.fetchall()
        conn.close()
        
        if not picos:
            logger.warning("⚠️ Nenhum Pico online encontrado")
            return False
        
        eventos_enviados = 0
        
        for client_id, topic in picos:
            # Tópico específico para eventos
            evento_topic = f"{topic}/evento"
            
            # Payload do evento
            payload = json.dumps({
                "id": evento_data["id"],
                "nome": evento_data["nome"],
                "hora": evento_data["hora"],
                "data": evento_data["data"],
                "acao": "adicionar",
                "timestamp": datetime.now().isoformat()
            })
            
            # Publicar evento
            result = mqtt_client.publish(evento_topic, payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📤 Evento {evento_data['id']} enviado para Pico {client_id}")
                eventos_enviados += 1
            else:
                logger.error(f"❌ Falha ao enviar evento para Pico {client_id}")
        
        return eventos_enviados > 0
        
    except Exception as e:
        logger.error(f"❌ Erro ao enviar evento via MQTT: {e}")
        return False

def sincronizar_eventos_hoje_mqtt():
    """Sincroniza todos os eventos de hoje via MQTT"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Busca eventos de hoje
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, hora, data 
        FROM eventos 
        WHERE data = ? 
        ORDER BY hora
    """, (hoje,))
    eventos_hoje = cursor.fetchall()
    conn.close()
    
    if not eventos_hoje:
        logger.info("📅 Nenhum evento para hoje")
        return {"sincronizados": 0, "erros": 0, "picos": 0}
    
    eventos_sincronizados = 0
    erros_sincronizacao = 0
    
    # Enviar comando de limpeza primeiro
    limpar_eventos_mqtt()
    time.sleep(1)  # Aguardar processamento
    
    # Enviar cada evento
    for evento_id, nome, hora, data in eventos_hoje:
        evento_data = {
            "id": evento_id,
            "nome": nome,
            "hora": hora,
            "data": data
        }
        
        if enviar_evento_mqtt(evento_data):
            eventos_sincronizados += 1
        else:
            erros_sincronizacao += 1
    
    # Enviar comando de atualização de display
    atualizar_display_mqtt()
    
    resultado = {
        "sincronizados": eventos_sincronizados,
        "erros": erros_sincronizacao,
        "eventos_total": len(eventos_hoje)
    }
    
    logger.info(f"📱 Sincronização MQTT concluída: {resultado}")
    return resultado

def limpar_eventos_mqtt():
    """Envia comando para limpar eventos nos Picos via MQTT"""
    global mqtt_client, mqtt_connected
    
    if not mqtt_connected or not mqtt_client:
        return False
    
    try:
        # Buscar Picos online
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT client_id, topic FROM pico_devices WHERE status = 'online'")
        picos = cursor.fetchall()
        conn.close()
        
        for client_id, topic in picos:
            comando_topic = f"{topic}/comando"
            payload = json.dumps({"acao": "limpar"})
            mqtt_client.publish(comando_topic, payload, qos=1)
            logger.info(f"🗑️ Comando de limpeza enviado para Pico {client_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao enviar comando de limpeza: {e}")
        return False

def atualizar_display_mqtt():
    """Envia comando para atualizar display nos Picos via MQTT"""
    global mqtt_client, mqtt_connected
    
    if not mqtt_connected or not mqtt_client:
        return False
    
    try:
        # Buscar Picos online
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT client_id, topic FROM pico_devices WHERE status = 'online'")
        picos = cursor.fetchall()
        conn.close()
        
        for client_id, topic in picos:
            comando_topic = f"{topic}/comando"
            payload = json.dumps({"acao": "atualizar_display"})
            mqtt_client.publish(comando_topic, payload, qos=1)
            logger.info(f"🔄 Comando de atualização enviado para Pico {client_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao enviar comando de atualização: {e}")
        return False

def deletar_evento_mqtt(evento_id):
    """Envia comando para deletar evento específico nos Picos"""
    global mqtt_client, mqtt_connected
    
    if not mqtt_connected or not mqtt_client:
        return False
    
    try:
        # Buscar Picos online
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT client_id, topic FROM pico_devices WHERE status = 'online'")
        picos = cursor.fetchall()
        conn.close()
        
        for client_id, topic in picos:
            evento_topic = f"{topic}/evento"
            payload = json.dumps({
                "id": evento_id,
                "acao": "deletar",
                "timestamp": datetime.now().isoformat()
            })
            mqtt_client.publish(evento_topic, payload, qos=1)
            logger.info(f"🗑️ Comando de deleção do evento {evento_id} enviado para Pico {client_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao enviar comando de deleção: {e}")
        return False

# ===== THREAD DE SINCRONIZAÇÃO AUTOMÁTICA =====
def thread_sincronizacao_automatica():
    """Thread que executa sincronização automática em intervalos regulares"""
    logger.info("🔄 Thread de sincronização automática MQTT iniciada")
    
    while True:
        try:
            if mqtt_connected:
                logger.info("🕐 Iniciando sincronização automática via MQTT...")
                resultado = sincronizar_eventos_hoje_mqtt()
                logger.info(f"✅ Sincronização automática concluída: {resultado}")
            else:
                logger.warning("⚠️ MQTT desconectado - pulando sincronização")
            
            time.sleep(60)  # Sincronização a cada 60 segundos
            
        except Exception as e:
            logger.error(f"❌ Erro na thread de sincronização: {e}")
            time.sleep(30)

def iniciar_sincronizacao_automatica():
    """Inicia a thread de sincronização em background"""
    thread = threading.Thread(target=thread_sincronizacao_automatica, daemon=True)
    thread.start()
    logger.info("🚀 Sistema de sincronização automática MQTT iniciado")

# ===== INICIALIZAÇÃO =====
init_db()
inicializar_mqtt()
iniciar_sincronizacao_automatica()

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

    # Se o evento for para hoje, tenta sincronizar imediatamente via MQTT
    hoje = datetime.now().strftime('%Y-%m-%d')
    if data_evento == hoje:
        logger.info(f"🆕 Evento para hoje detectado - enviando via MQTT")
        
        evento_data = {
            "id": evento_id,
            "nome": nome,
            "hora": hora_evento,
            "data": data_evento
        }
        
        if enviar_evento_mqtt(evento_data):
            atualizar_display_mqtt()

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
    
    # Se era de hoje e estava sincronizado, remove dos Picos via MQTT
    if data_evento == hoje and sincronizado:
        deletar_evento_mqtt(evento_id)
        atualizar_display_mqtt()
    
    return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200

@app.route('/api/eventos', methods=['DELETE'])
@token_required
def deletar_todos_eventos(usuario):
    # Limpa todos os eventos dos Picos via MQTT primeiro
    limpar_eventos_mqtt()
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos")
    conn.commit()
    conn.close()
    
    logger.info("🗑️ Todos os eventos removidos do banco de dados")
    
    # Atualiza displays
    atualizar_display_mqtt()
    
    return jsonify({'mensagem': 'Todos os eventos foram excluídos com sucesso!'}), 200

# ===== ROTAS DE GERENCIAMENTO MQTT =====
@app.route('/api/mqtt/status', methods=['GET'])
@token_required
def status_mqtt(usuario):
    """Retorna status da conexão MQTT"""
    return jsonify({
        'conectado': mqtt_connected,
        'broker': MQTT_BROKER,
        'client_id': MQTT_CLIENT_ID,
        'topico_base': MQTT_TOPIC_BASE
    }), 200

@app.route('/api/picos/status', methods=['GET'])
@token_required
def status_todos_picos(usuario):
    """Retorna status de todos os Picos conectados via MQTT"""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT client_id, name, last_sync, status, topic FROM pico_devices")
    picos_db = cursor.fetchall()
    conn.close()
    
    status_picos = []
    
    for client_id, name, last_sync, status, topic in picos_db:
        status_picos.append({
            'client_id': client_id,
            'name': name,
            'status': status,
            'last_sync': last_sync,
            'topic': topic
        })
    
    return jsonify({
        'picos': status_picos,
        'total': len(status_picos),
        'online': sum(1 for p in status_picos if p['status'] == 'online'),
        'mqtt_conectado': mqtt_connected,
        'broker': MQTT_BROKER
    }), 200

@app.route('/api/picos/sincronizar', methods=['POST'])
@token_required
def sincronizar_manual(usuario):
    """Força sincronização manual via MQTT"""
    logger.info("🔄 Iniciando sincronização manual via MQTT...")
    resultado = sincronizar_eventos_hoje_mqtt()
    
    return jsonify({
        'mensagem': 'Sincronização manual via MQTT concluída!',
        'resultado': resultado
    }), 200

@app.route('/api/sistema/info', methods=['GET'])
@token_required
def info_sistema(usuario):
    """Retorna informações do sistema MQTT"""
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
        'protocolo': 'MQTT',
        'mqtt_conectado': mqtt_connected,
        'broker': MQTT_BROKER,
        'topico_base': MQTT_TOPIC_BASE,
        'versao': '3.0-MQTT',
        'data_atual': hoje
    }), 200

if __name__ == '__main__':
    logger.info("🚀 Iniciando servidor Flask com MQTT...")
    logger.info(f"📡 MQTT Broker: {MQTT_BROKER}")
    logger.info(f"📡 Tópico base: {MQTT_TOPIC_BASE}")
    app.run(host='0.0.0.0', port=5000, debug=True)
