from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import threading
import time
import logging
import serial
import struct

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÕES LORA 433MHz =====
LORA_SERIAL_PORT = "COM3"  # Windows: COM3, COM4, etc. | Linux: /dev/ttyUSB0
LORA_BAUDRATE = 9600
LORA_TIMEOUT = 2

# Configurações LoRa específicas
LORA_FREQUENCY = 433  # MHz
LORA_POWER = 20      # dBm (máximo)
LORA_BANDWIDTH = 125 # kHz
LORA_SPREADING_FACTOR = 7
LORA_CODING_RATE = 5

# Cliente LoRa global
lora_connection = None
lora_connected = False

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
    
    # Tabela de dispositivos Pico conectados (via LoRa)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Magic Mirror',
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            communication_type TEXT DEFAULT 'lora',
            lora_frequency INTEGER DEFAULT 433,
            rssi INTEGER DEFAULT 0,
            snr REAL DEFAULT 0.0,
            firmware_version TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            events_count INTEGER DEFAULT 0,
            last_heartbeat TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado para LoRa 433MHz")

# ===== FUNÇÕES LORA =====
def inicializar_lora():
    """Inicializa comunicação LoRa SX1278 433MHz"""
    global lora_connection, lora_connected
    
    try:
        lora_connection = serial.Serial(
            port=LORA_SERIAL_PORT,
            baudrate=LORA_BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=LORA_TIMEOUT,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        if lora_connection.is_open:
            # Configura módulo LoRa
            if configurar_modulo_lora():
                lora_connected = True
                logger.info(f"LoRa conectado: {LORA_SERIAL_PORT} @ {LORA_FREQUENCY}MHz")
                return True
            else:
                lora_connected = False
                logger.error("Falha na configuração do módulo LoRa")
                return False
        else:
            lora_connected = False
            logger.error(f"Falha ao abrir porta: {LORA_SERIAL_PORT}")
            return False
            
    except Exception as e:
        lora_connected = False
        logger.error(f"Erro LoRa: {e}")
        return False

def configurar_modulo_lora():
    """Configura parâmetros do módulo LoRa SX1278"""
    try:
        time.sleep(1)  # Aguarda estabilização
        
        # Comandos AT para configurar LoRa (exemplo genérico)
        comandos_config = [
            f"AT+MODE=LORA",                    # Modo LoRa
            f"AT+FREQUENCY={LORA_FREQUENCY}",   # Frequência 433MHz
            f"AT+POWER={LORA_POWER}",          # Potência 20dBm
            f"AT+BANDWIDTH={LORA_BANDWIDTH}",   # Largura banda 125kHz
            f"AT+SF={LORA_SPREADING_FACTOR}",   # Spreading Factor 7
            f"AT+CR={LORA_CODING_RATE}",       # Coding Rate 4/5
            f"AT+PREAMBLE=8",                  # Preâmbulo
            f"AT+SYNCWORD=18",                 # Palavra sincronização
            f"AT+CRC=1",                       # Habilita CRC
        ]
        
        for cmd in comandos_config:
            enviar_comando_at(cmd)
            time.sleep(0.1)
        
        # Testa comunicação
        response = enviar_comando_at("AT")
        if "OK" in response:
            logger.info("Módulo LoRa configurado com sucesso")
            return True
        else:
            logger.error("Módulo LoRa não responde")
            return False
            
    except Exception as e:
        logger.error(f"Erro na configuração LoRa: {e}")
        return False

def enviar_comando_at(comando):
    """Envia comando AT para módulo LoRa e aguarda resposta"""
    try:
        cmd = comando + "\r\n"
        lora_connection.write(cmd.encode())
        lora_connection.flush()
        
        # Aguarda resposta
        time.sleep(0.5)
        response = ""
        while lora_connection.in_waiting > 0:
            response += lora_connection.read().decode('utf-8', errors='ignore')
        
        return response.strip()
        
    except Exception as e:
        logger.error(f"Erro comando AT: {e}")
        return ""

def enviar_lora(payload, target_device_id="BROADCAST"):
    """Envia dados via LoRa com protocolo próprio"""
    global lora_connection, lora_connected
    
    if not lora_connected or not lora_connection:
        return False
    
    try:
        # Monta pacote LoRa
        packet = montar_pacote_lora(payload, target_device_id)
        
        # Comando para transmitir (exemplo genérico)
        cmd = f"AT+SEND={len(packet)},{packet}\r\n"
        lora_connection.write(cmd.encode())
        lora_connection.flush()
        
        logger.info(f"Enviado LoRa: {payload.get('action', 'unknown')} -> {target_device_id}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao enviar LoRa: {e}")
        lora_connected = False
        return False

def montar_pacote_lora(payload, target_device_id):
    """Monta pacote LoRa com cabeçalho e dados"""
    try:
        # Converte payload para JSON compacto
        data_json = json.dumps(payload, separators=(',', ':'))
        
        # Cabeçalho do pacote
        header = {
            "target": target_device_id[:8],  # 8 chars max
            "source": "SERVER",
            "msg_id": int(time.time()) % 65535,  # ID único
            "type": "EVENT_DATA",
            "len": len(data_json)
        }
        
        # Monta pacote completo
        packet_data = {
            "hdr": header,
            "data": payload
        }
        
        # Converte para string compacta
        packet_str = json.dumps(packet_data, separators=(',', ':'))
        
        # Limita tamanho (LoRa tem limite de payload)
        if len(packet_str) > 200:
            logger.warning(f"Pacote muito grande: {len(packet_str)} bytes")
            # Compacta payload removendo campos opcionais
            payload_compactado = compactar_payload(payload)
            packet_data["data"] = payload_compactado
            packet_str = json.dumps(packet_data, separators=(',', ':'))
        
        return packet_str
        
    except Exception as e:
        logger.error(f"Erro ao montar pacote: {e}")
        return ""

def compactar_payload(payload):
    """Compacta payload para economizar bytes"""
    try:
        if payload.get("action") == "sync_events":
            # Compacta lista de eventos
            events = payload.get("events", [])
            compact_events = []
            
            for event in events:
                compact_event = {
                    "i": event.get("id"),         # id
                    "n": event.get("nome", "")[:30],  # nome (max 30 chars)
                    "h": event.get("hora", ""),   # hora
                    "d": event.get("data", "")    # data
                }
                compact_events.append(compact_event)
            
            return {
                "action": "sync_events",
                "events": compact_events,
                "device_id": payload.get("device_id", ""),
                "sync_time": payload.get("sync_time", "")
            }
        
        return payload
        
    except Exception as e:
        logger.error(f"Erro ao compactar: {e}")
        return payload

def ler_lora():
    """Lê dados do LoRa de forma não-bloqueante"""
    global lora_connection, lora_connected
    
    if not lora_connected or not lora_connection:
        return None
    
    try:
        if lora_connection.in_waiting > 0:
            # Lê resposta completa
            response = ""
            while lora_connection.in_waiting > 0:
                chunk = lora_connection.read().decode('utf-8', errors='ignore')
                response += chunk
                time.sleep(0.01)
            
            # Processa dados recebidos
            return processar_dados_lora(response)
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao ler LoRa: {e}")
        return None

def processar_dados_lora(response):
    """Processa dados recebidos do LoRa"""
    try:
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Verifica se é dados recebidos (formato específico do módulo)
            if "+RCV=" in line or "RECV:" in line:
                # Extrai dados do pacote (formato depende do módulo)
                # Exemplo: +RCV=25,{"action":"ping","device_id":"ABC123"},123,-45
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        # Extrai JSON dos dados
                        json_start = line.find('{')
                        json_end = line.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            json_data = line[json_start:json_end]
                            packet = json.loads(json_data)
                            
                            # Extrai RSSI e SNR se disponível
                            rssi = int(parts[-2]) if len(parts) >= 4 else 0
                            snr = float(parts[-1]) if len(parts) >= 5 else 0.0
                            
                            # Adiciona informações de sinal
                            packet["rssi"] = rssi
                            packet["snr"] = snr
                            
                            return packet
                            
                    except (json.JSONDecodeError, ValueError, IndexError) as e:
                        logger.warning(f"Erro ao decodificar pacote LoRa: {e}")
                        continue
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao processar dados LoRa: {e}")
        return None

def processar_mensagem_pico(data):
    """Processa mensagens recebidas do Pico via LoRa"""
    try:
        # Verifica se é pacote com cabeçalho
        if "hdr" in data and "data" in data:
            header = data.get("hdr", {})
            payload = data.get("data", {})
        else:
            # Pacote simples
            payload = data
            header = {}
        
        action = payload.get("action", "")
        device_id = payload.get("device_id", "")
        rssi = data.get("rssi", 0)
        snr = data.get("snr", 0.0)
        
        if not device_id:
            logger.warning("Mensagem sem device_id")
            return
        
        # Atualiza último heartbeat com dados de sinal
        atualizar_heartbeat_dispositivo(device_id, rssi, snr)
        
        if action == "ping":
            processar_ping_lora(device_id)
        elif action == "device_info":
            processar_info_dispositivo_lora(payload, rssi, snr)
        elif action == "device_status":
            processar_status_dispositivo_lora(payload, rssi, snr)
        elif action == "event_completed":
            processar_evento_concluido(payload)
        elif action == "event_ack":
            processar_ack_evento(payload)
        elif action == "sync_complete":
            processar_sync_completo_lora(payload)
        else:
            logger.warning(f"Ação desconhecida: {action}")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

def processar_ping_lora(device_id):
    """Responde ping do Pico via LoRa"""
    payload = {
        "action": "ping_response",
        "device_id": device_id,
        "server_time": datetime.now().isoformat(),
        "status": "ok",
        "protocol": "lora_433mhz"
    }
    enviar_lora(payload, device_id)

def processar_info_dispositivo_lora(data, rssi, snr):
    """Processa informações do dispositivo via LoRa"""
    device_id = data.get("device_id")
    device_info = data
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, status, communication_type, lora_frequency, 
             rssi, snr, firmware_version, last_sync, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            device_info.get('name', 'Magic Mirror'),
            'online',
            'lora',
            LORA_FREQUENCY,
            rssi,
            snr,
            device_info.get('firmware_version', '2.0.0'),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Dispositivo LoRa registrado: {device_id} (RSSI: {rssi}dBm)")
        
        # Envia eventos de hoje automaticamente
        sincronizar_dispositivo_lora(device_id)
        
    except Exception as e:
        logger.error(f"Erro ao registrar dispositivo: {e}")

def processar_status_dispositivo_lora(data, rssi, snr):
    """Processa status do dispositivo via LoRa"""
    device_id = data.get("device_id")
    status = data.get("status", "online")
    events_count = data.get("events_count", 0)
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pico_devices 
            SET status = ?, events_count = ?, rssi = ?, snr = ?, last_heartbeat = ?
            WHERE device_id = ?
        ''', (status, events_count, rssi, snr, datetime.now().isoformat(), device_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Status LoRa: {device_id} - {status} (RSSI: {rssi}dBm)")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar status: {e}")

def processar_sync_completo_lora(data):
    """Processa confirmação de sincronização via LoRa"""
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
        
        logger.info(f"Sincronização LoRa completa: {device_id} ({events_count} eventos)")
        
    except Exception as e:
        logger.error(f"Erro ao processar sync: {e}")

def atualizar_heartbeat_dispositivo(device_id, rssi=0, snr=0.0):
    """Atualiza heartbeat com dados de sinal LoRa"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pico_devices 
            SET last_heartbeat = ?, rssi = ?, snr = ?
            WHERE device_id = ?
        ''', (datetime.now().isoformat(), rssi, snr, device_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        pass  # Erro silencioso

def sincronizar_dispositivo_lora(device_id):
    """Sincroniza eventos via LoRa - APENAS EVENTOS DE HOJE"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # IMPORTANTE: Filtra apenas eventos de HOJE
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
        
        # Enviar sincronização via LoRa
        payload = {
            "action": "sync_events",
            "device_id": device_id,
            "events": events_list,
            "sync_time": datetime.now().isoformat(),
            "filter_date": hoje  # Confirma que são eventos de hoje
        }
        
        if enviar_lora(payload, device_id):
            logger.info(f"Sincronização LoRa enviada: {len(events_list)} eventos de hoje para {device_id}")
        else:
            logger.error(f"Falha na sincronização LoRa: {device_id}")
            
    except Exception as e:
        logger.error(f"Erro na sincronização LoRa: {e}")

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
                logger.info(f"Evento {event_id} concluído via LoRa ({reason})")
            else:
                logger.warning(f"Evento {event_id} não encontrado")
                
        except Exception as e:
            logger.error(f"Erro ao processar evento concluído: {e}")

def processar_ack_evento(data):
    """Processa confirmação de evento"""
    event_id = data.get("event_id")
    ack_action = data.get("ack_action", "")
    
    logger.info(f"ACK LoRa: Evento {event_id} - {ack_action}")

# ===== THREAD DE COMUNICAÇÃO LORA =====
def thread_comunicacao_lora():
    """Thread que monitora comunicação LoRa"""
    global lora_connection, lora_connected
    
    logger.info("Thread LoRa iniciada")
    
    while True:
        try:
            # Tenta reconectar se desconectado
            if not lora_connected:
                logger.info("Tentando reconectar LoRa...")
                if inicializar_lora():
                    time.sleep(2)
                else:
                    time.sleep(15)  # Aguarda mais tempo para LoRa
                    continue
            
            # Lê mensagens do Pico via LoRa
            data = ler_lora()
            if data:
                processar_mensagem_pico(data)
            
            time.sleep(0.2)  # Delay um pouco maior para LoRa
            
        except Exception as e:
            logger.error(f"Erro na thread LoRa: {e}")
            lora_connected = False
            time.sleep(5)

def iniciar_comunicacao_lora():
    """Inicia thread de comunicação LoRa em background"""
    thread = threading.Thread(target=thread_comunicacao_lora, daemon=True)
    thread.start()
    logger.info("Sistema de comunicação LoRa 433MHz iniciado")

# ===== INICIALIZAÇÃO =====
init_db()
iniciar_comunicacao_lora()

# ===== ROTAS DA API =====
@app.route('/')
def serve_index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/eventos', methods=['POST'])
def adicionar_evento():
    """Adiciona novo evento e envia via LoRa SE FOR HOJE"""
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

        logger.info(f"Novo evento criado: {nome} em {data_evento} às {hora_evento}")

        # VERIFICA SE É EVENTO DE HOJE
        hoje = datetime.now().strftime('%Y-%m-%d')
        if data_evento == hoje:
            logger.info(f"Evento para HOJE - enviando via LoRa")
            
            payload = {
                "action": "add_event",
                "event": {
                    "id": evento_id,
                    "nome": nome,
                    "hora": hora_evento,
                    "data": data_evento
                },
                "timestamp": datetime.now().isoformat(),
                "is_today": True  # Flag confirma que é hoje
            }
            
            if enviar_lora(payload):
                # Marca como sincronizado
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE id = ?", (evento_id,))
                conn.commit()
                conn.close()
        else:
            logger.info(f"Evento não é de hoje ({data_evento}) - não enviado via LoRa")

        return jsonify({'mensagem': 'Evento cadastrado com sucesso!', 'id': evento_id}), 201
    
    except Exception as e:
        logger.error(f"Erro ao adicionar evento: {e}")
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
        logger.error(f"Erro ao listar eventos: {e}")
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
        logger.error(f"Erro ao listar eventos de hoje: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/eventos', methods=['DELETE'])
def deletar_todos_eventos():
    """Deleta todos os eventos"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos")
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        if rows_affected > 0:
            # Envia comando de remoção via LoRa
            payload = {
                "action": "remove_all_events",
                "timestamp": datetime.now().isoformat()
            }
            enviar_lora(payload)
            
            logger.info("Todos os eventos deletados")
            return jsonify({'mensagem': 'Todos os eventos deletados com sucesso!'}), 200
        else:
            return jsonify({"erro": "Nenhum evento para deletar"}), 404
    
    except Exception as e:
        logger.error(f"Erro ao deletar todos os eventos: {e}")
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
            # Envia comando de remoção via LoRa
            payload = {
                "action": "remove_event",
                "event_id": evento_id,
                "timestamp": datetime.now().isoformat()
            }
            enviar_lora(payload)
            
            logger.info(f"Evento {evento_id} deletado")
            return jsonify({'mensagem': 'Evento deletado com sucesso!'}), 200
        else:
            return jsonify({"erro": "Evento não encontrado"}), 404
    
    except Exception as e:
        logger.error(f"Erro ao deletar evento: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/sistema/info', methods=['GET'])
def info_sistema():
    """Retorna informações do sistema LoRa"""
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
            'protocolo': 'LoRa',
            'lora_conectado': lora_connected,
            'lora_frequency': f"{LORA_FREQUENCY}MHz",
            'lora_power': f"{LORA_POWER}dBm",
            'versao': '2.0-LoRa433',
            'modo': 'OFFLINE',
            'data_atual': hoje
        }), 200
    
    except Exception as e:
        logger.error(f"Erro ao obter informações do sistema: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/sincronizar', methods=['POST'])
def sincronizar_manual():
    """Força sincronização manual de todos os dispositivos via LoRa"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT device_id FROM pico_devices WHERE status = 'online'")
        dispositivos = cursor.fetchall()
        conn.close()
        
        sincronizados = 0
        for (device_id,) in dispositivos:
            sincronizar_dispositivo_lora(device_id)
            sincronizados += 1
        
        return jsonify({
            'mensagem': f'Sincronização LoRa iniciada para {sincronizados} dispositivo(s)',
            'dispositivos_sincronizados': sincronizados
        }), 200
    
    except Exception as e:
        logger.error(f"Erro na sincronização manual: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

@app.route('/api/dispositivos', methods=['GET'])
def listar_dispositivos():
    """Lista dispositivos Pico conectados via LoRa"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT device_id, name, status, last_sync, events_count, 
                   firmware_version, last_heartbeat, created_at, rssi, snr
            FROM pico_devices 
            ORDER BY created_at DESC
        """)
        dispositivos = cursor.fetchall()
        conn.close()

        dispositivos_formatados = []
        for device_id, name, status, last_sync, events_count, firmware_version, last_heartbeat, created_at, rssi, snr in dispositivos:
            dispositivos_formatados.append({
                'device_id': device_id,
                'name': name,
                'status': status,
                'last_sync': last_sync,
                'events_count': events_count,
                'firmware_version': firmware_version,
                'last_heartbeat': last_heartbeat,
                'created_at': created_at,
                'rssi': rssi,
                'snr': snr,
                'signal_quality': 'Forte' if rssi > -70 else 'Médio' if rssi > -90 else 'Fraco'
            })

        return jsonify(dispositivos_formatados)
    
    except Exception as e:
        logger.error(f"Erro ao listar dispositivos: {e}")
        return jsonify({"erro": "Erro interno do servidor"}), 500

if __name__ == '__main__':
    logger.info("Iniciando servidor Flask com LoRa 433MHz...")
    logger.info(f"Frequência LoRa: {LORA_FREQUENCY}MHz @ {LORA_POWER}dBm")
    logger.info("Modo: OFFLINE - Comunicação LoRa")
    app.run(host='0.0.0.0', port=5000, debug=False)