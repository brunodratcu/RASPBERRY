from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import threading
import time
import logging
import serial

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÕES RS-232 =====
SERIAL_PORT = "COM3"  # Windows: COM3, COM4, etc. | Linux: /dev/ttyUSB0
SERIAL_BAUDRATE = 9600
SERIAL_TIMEOUT = 1

# Cliente Serial global
serial_connection = None
serial_connected = False

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
            device_id TEXT
        )
    ''')
    
    # Tabela de dispositivos Pico conectados (via RS-232)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Magic Mirror',
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            communication_type TEXT DEFAULT 'rs232',
            serial_port TEXT,
            firmware_version TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            events_count INTEGER DEFAULT 0,
            last_heartbeat TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("📚 Banco de dados inicializado para RS-232")

# ===== FUNÇÕES RS-232 =====
def inicializar_serial():
    """Inicializa comunicação serial RS-232"""
    global serial_connection, serial_connected
    
    try:
        serial_connection = serial.Serial(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        if serial_connection.is_open:
            serial_connected = True
            logger.info(f"✅ RS-232 conectado: {SERIAL_PORT} @ {SERIAL_BAUDRATE}")
            return True
        else:
            serial_connected = False
            logger.error(f"❌ Falha ao abrir porta: {SERIAL_PORT}")
            return False
            
    except Exception as e:
        serial_connected = False
        logger.error(f"❌ Erro RS-232: {e}")
        return False

def enviar_serial(payload):
    """Envia dados via RS-232"""
    global serial_connection, serial_connected
    
    if not serial_connected or not serial_connection:
        return False
    
    try:
        message = json.dumps(payload) + "\n"
        serial_connection.write(message.encode('utf-8'))
        serial_connection.flush()
        logger.info(f"📤 Enviado RS-232: {payload.get('action', 'unknown')}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao enviar RS-232: {e}")
        serial_connected = False
        return False

def ler_serial():
    """Lê dados do RS-232 de forma não-bloqueante"""
    global serial_connection, serial_connected
    
    if not serial_connected or not serial_connection:
        return None
    
    try:
        if serial_connection.in_waiting > 0:
            line = serial_connection.readline().decode('utf-8').strip()
            if line:
                return json.loads(line)
        return None
        
    except Exception as e:
        logger.error(f"❌ Erro ao ler RS-232: {e}")
        return None

def processar_mensagem_pico(data):
    """Processa mensagens recebidas do Pico"""
    try:
        action = data.get("action", "")
        device_id = data.get("device_id", "")
        
        if not device_id:
            logger.warning("⚠️ Mensagem sem device_id")
            return
        
        # Atualiza último heartbeat
        atualizar_heartbeat_dispositivo(device_id)
        
        if action == "ping":
            processar_ping(device_id)
        elif action == "device_info":
            processar_info_dispositivo(data)
        elif action == "device_status":
            processar_status_dispositivo(data)
        elif action == "event_completed":
            processar_evento_concluido(data)
        elif action == "event_ack":
            processar_ack_evento(data)
        elif action == "sync_complete":
            processar_sync_completo(data)
        else:
            logger.warning(f"⚠️ Ação desconhecida: {action}")
            
    except Exception as e:
        logger.error(f"❌ Erro ao processar mensagem: {e}")

def processar_ping(device_id):
    """Responde ping do Pico"""
    payload = {
        "action": "ping_response",
        "device_id": device_id,
        "server_time": datetime.now().isoformat(),
        "status": "ok"
    }
    enviar_serial(payload)

def processar_info_dispositivo(data):
    """Processa informações do dispositivo"""
    device_id = data.get("device_id")
    device_info = data
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, status, communication_type, serial_port, 
             firmware_version, last_sync, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            device_info.get('name', 'Magic Mirror'),
            'online',
            'rs232',
            SERIAL_PORT,
            device_info.get('firmware_version', '2.0.0'),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📝 Dispositivo registrado: {device_id}")
        
        # Envia eventos de hoje automaticamente
        sincronizar_dispositivo(device_id)
        
    except Exception as e:
        logger.error(f"❌ Erro ao registrar dispositivo: {e}")

def processar_status_dispositivo(data):
    """Processa status do dispositivo"""
    device_id = data.get("device_id")
    status = data.get("status", "online")
    events_count = data.get("events_count", 0)
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pico_devices 
            SET status = ?, events_count = ?, last_heartbeat = ?
            WHERE device_id = ?
        ''', (status, events_count, datetime.now().isoformat(), device_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"💗 Status atualizado: {device_id} - {status}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status: {e}")

def processar_evento_concluido(data):
    """Processa evento concluído pelo Pico"""
    event_id = data.get("event_id")
    reason = data.get("completion_reason", "unknown")
    
    if event_id:
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            
            # Remove evento do banco
            cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
            rows_affected = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                logger.info(f"✅ Evento {event_id} concluído ({reason})")
            else:
                logger.warning(f"⚠️ Evento {event_id} não encontrado para remoção")
                
        except Exception as e:
            logger.error(f"❌ Erro ao processar evento concluído: {e}")

def processar_ack_evento(data):
    """Processa confirmação de evento"""
    event_id = data.get("event_id")
    ack_action = data.get("ack_action", "")
    
    logger.info(f"📨 ACK recebido: Evento {event_id} - {ack_action}")

def processar_sync_completo(data):
    """Processa confirmação de sincronização completa"""
    device_id = data.get("device_id")
    events_count = data.get("events_count", 0)
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pico_devices 
            SET last_sync = ?, events_count = ?
            WHERE device_id = ?
        ''', (datetime.now().isoformat(), events_count, device_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"🔄 Sincronização completa: {device_id} ({events_count} eventos)")
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar sync completo: {e}")

def atualizar_heartbeat_dispositivo(device_id):
    """Atualiza timestamp do último heartbeat"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pico_devices 
            SET last_heartbeat = ?
            WHERE device_id = ?
        ''', (datetime.now().isoformat(), device_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        pass  # Erro silencioso para não poluir logs

def sincronizar_dispositivo(device_id):
    """Sincroniza eventos de hoje com dispositivo específico"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        
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
        
        # Formatar eventos para envio
        events_list = []
        for event_id, nome, hora, data in eventos_hoje:
            events_list.append({
                "id": event_id,
                "nome": nome,
                "hora": hora,
                "data": data
            })
        
        # Enviar sincronização completa
        payload = {
            "action": "sync_events",
            "device_id": device_id,
            "events": events_list,
            "sync_time": datetime.now().isoformat()
        }
        
        if enviar_serial(payload):
            logger.info(f"📤 Sincronização enviada: {len(events_list)} eventos para {device_id}")
        else:
            logger.error(f"❌ Falha na sincronização: {device_id}")
            
    except Exception as e:
        logger.error(f"❌ Erro na sincronização: {e}")

# ===== THREAD DE COMUNICAÇÃO RS-232 =====
def thread_comunicacao_rs232():
    """Thread que monitora comunicação RS-232"""
    global serial_connection, serial_connected
    
    logger.info("🔄 Thread RS-232 iniciada")
    
    while True:
        try:
            # Tenta reconectar se desconectado
            if not serial_connected:
                logger.info("🔄 Tentando reconectar RS-232...")
                if inicializar_serial():
                    time.sleep(2)
                else:
                    time.sleep(10)  # Aguarda 10s antes de tentar novamente
                    continue
            
            # Lê mensagens do Pico
            data = ler_serial()
            if data:
                processar_mensagem_pico(data)
            
            time.sleep(0.1)  # Pequeno delay
            
        except Exception as e:
            logger.error(f"❌ Erro na thread RS-232: {e}")
            serial_connected = False
            time.sleep(5)

def iniciar_comunicacao_rs232():
    """Inicia thread de comunicação RS-232 em background"""
    thread = threading.Thread(target=thread_comunicacao_rs232, daemon=True)
    thread.start()
    logger.info("🚀 Sistema de comunicação RS-232 iniciado")

# ===== INICIALIZAÇÃO =====
init_db()
iniciar_comunicacao_rs232()

# ===== ROTAS DA API =====
@app.route('/')
def serve_index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/eventos', methods=['POST'])
def adicionar_evento():
    """Adiciona novo evento ao banco de dados"""
    data = request.get_json()
    nome = data.get('nome')
    data_evento = data.get('data')
    hora_evento = data.get('hora')
    criado_em = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not nome or not data_evento or not hora_evento:
        return jsonify({"erro": "Preencha todos os campos"}), 400

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO eventos (nome, data, hora, criado_em, sincronizado) VALUES (?, ?, ?, ?, ?)",
                       (nome, data_evento, hora_evento, criado_em, 0))
        evento_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"📝 Novo evento criado: {nome} em {data_evento} às {hora_evento}")

        # Se o evento for para hoje, envia via RS-232
        hoje = datetime.now().strftime('%Y-%m-%d')
        if data_evento == hoje:
            logger.info(f"🆕 Evento para hoje - enviando via RS-232")
            
            payload = {
                "action": "add_event",
                "event": {
                    "id": evento_id,
                    "nome": nome,
                    "hora": hora_evento,
                    "data": data_evento
                },
                "timestamp": datetime.now().isoformat()
            }
            
            if enviar_serial(payload):
                # Marca como sincronizado
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE id = ?", (evento_id,))
                conn.commit()
                conn.close()

        return jsonify({'mensagem': 'Evento cadastrado com sucesso!', 'id': evento_id}), 201
    
    except Exception as e:
        logger.error(f"❌ Erro ao adicionar evento: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/eventos', methods=['GET'])
def listar_eventos():
    """Lista todos os eventos"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, data, hora, sincronizado FROM eventos ORDER BY data, hora")
        eventos = cursor.fetchall()
        conn.close()

        eventos_formatados = [
            {
                'id': id,
                'nome': nome,
                'data': data,
                'hora': hora,
                'sincronizado': bool(sincronizado)
            }
            for id, nome, data, hora, sincronizado in eventos
        ]

        return jsonify(eventos_formatados)
    
    except Exception as e:
        logger.error(f"❌ Erro ao listar eventos: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/eventos-hoje', methods=['GET'])
def eventos_hoje():
    """Lista eventos de hoje"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    try:
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
    
    except Exception as e:
        logger.error(f"❌ Erro ao listar eventos de hoje: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
def deletar_evento(evento_id):
    """Deleta um evento"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        if rows_affected > 0:
            # Envia comando de remoção via RS-232
            payload = {
                "action": "remove_event",
                "event_id": evento_id,
                "timestamp": datetime.now().isoformat()
            }
            enviar_serial(payload)
            
            logger.info(f"🗑️ Evento {evento_id} deletado")
            return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200
        else:
            return jsonify({"erro": "Evento não encontrado"}), 404
    
    except Exception as e:
        logger.error(f"❌ Erro ao deletar evento: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/dispositivos', methods=['GET'])
def listar_dispositivos():
    """Lista dispositivos Pico conectados"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT device_id, name, status, last_sync, events_count, 
                   firmware_version, last_heartbeat, created_at
            FROM pico_devices 
            ORDER BY created_at DESC
        """)
        dispositivos = cursor.fetchall()
        conn.close()

        dispositivos_formatados = []
        for device_id, name, status, last_sync, events_count, firmware_version, last_heartbeat, created_at in dispositivos:
            dispositivos_formatados.append({
                'device_id': device_id,
                'name': name,
                'status': status,
                'last_sync': last_sync,
                'events_count': events_count,
                'firmware_version': firmware_version,
                'last_heartbeat': last_heartbeat,
                'created_at': created_at
            })

        return jsonify(dispositivos_formatados)
    
    except Exception as e:
        logger.error(f"❌ Erro ao listar dispositivos: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/sistema/info', methods=['GET'])
def info_sistema():
    """Retorna informações do sistema RS-232"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM eventos WHERE data = ?", (hoje,))
        eventos_hoje_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM pico_devices")
        total_dispositivos = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM eventos")
        total_eventos = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'eventos_hoje': eventos_hoje_count,
            'total_eventos': total_eventos,
            'total_dispositivos': total_dispositivos,
            'protocolo': 'RS-232',
            'rs232_conectado': serial_connected,
            'porta_serial': SERIAL_PORT,
            'baudrate': SERIAL_BAUDRATE,
            'versao': '2.0-RS232',
            'modo': 'OFFLINE',
            'data_atual': hoje
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Erro ao obter informações do sistema: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/sincronizar', methods=['POST'])
def sincronizar_manual():
    """Força sincronização manual de todos os dispositivos"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT device_id FROM pico_devices WHERE status = 'online'")
        dispositivos = cursor.fetchall()
        conn.close()
        
        sincronizados = 0
        for (device_id,) in dispositivos:
            sincronizar_dispositivo(device_id)
            sincronizados += 1
        
        return jsonify({
            'mensagem': f'Sincronização iniciada para {sincronizados} dispositivo(s)',
            'dispositivos_sincronizados': sincronizados
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Erro na sincronização manual: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

if __name__ == '__main__':
    logger.info("🚀 Iniciando servidor Flask com RS-232...")
    logger.info(f"📡 Porta Serial: {SERIAL_PORT} @ {SERIAL_BAUDRATE}")
    logger.info("🔌 Modo: OFFLINE - Comunicação RS-232")
    app.run(host='0.0.0.0', port=5000, debug=False)