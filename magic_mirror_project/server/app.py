from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import threading
import time
import logging
import socket
import os
import sys

# Importação condicional do Bluetooth (compatibilidade com diferentes SOs)
try:
    from bluetooth import *
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False
    print("ATENÇÃO: Biblioteca pybluez não encontrada. Instale com: pip install pybluez")

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÕES BLUETOOTH =====
BLUETOOTH_SERVICE_UUID = "94f39d29-7d6d-437d-973b-fba39e49d4ee"
BLUETOOTH_SERVICE_NAME = "Magic Mirror Events"
BLUETOOTH_PORT = 3  # Porta RFCOMM padrão

# Variáveis globais Bluetooth
bluetooth_server_socket = None
bluetooth_connected = False
connected_client_socket = None
connected_device_info = None
discovered_devices = []
scanning = False

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== BANCO DE DADOS =====
def init_db():
    """Inicializa banco de dados SQLite"""
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
    
    # Tabela de dispositivos conectados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Magic Mirror',
            bluetooth_address TEXT,
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            communication_type TEXT DEFAULT 'bluetooth',
            signal_strength INTEGER DEFAULT 0,
            firmware_version TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            events_count INTEGER DEFAULT 0,
            last_heartbeat TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado")

# ===== FUNÇÕES AUXILIARES =====
def get_bluetooth_status():
    """Retorna status atual do Bluetooth"""
    return {
        'available': BLUETOOTH_AVAILABLE,
        'connected': bluetooth_connected,
        'device': connected_device_info,
        'scanning': scanning,
        'server_running': bluetooth_server_socket is not None
    }

def safe_json_dumps(data):
    """Converte dados para JSON de forma segura"""
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao serializar JSON: {e}")
        return json.dumps({"error": "Serialization failed"})

# ===== FUNÇÕES BLUETOOTH =====
def inicializar_bluetooth_server():
    """Inicializa servidor Bluetooth RFCOMM"""
    global bluetooth_server_socket
    
    if not BLUETOOTH_AVAILABLE:
        logger.error("Bluetooth não disponível - pybluez não instalado")
        return False
    
    try:
        # Cria socket Bluetooth RFCOMM
        bluetooth_server_socket = BluetoothSocket(RFCOMM)
        bluetooth_server_socket.bind(("", BLUETOOTH_PORT))
        bluetooth_server_socket.listen(1)
        
        port = bluetooth_server_socket.getsockname()[1]
        
        # Anuncia o serviço
        advertise_service(
            bluetooth_server_socket,
            BLUETOOTH_SERVICE_NAME,
            service_id=BLUETOOTH_SERVICE_UUID,
            service_classes=[BLUETOOTH_SERVICE_UUID, SERIAL_PORT_CLASS],
            profiles=[SERIAL_PORT_PROFILE]
        )
        
        logger.info(f"Servidor Bluetooth iniciado na porta RFCOMM {port}")
        logger.info(f"Nome do serviço: {BLUETOOTH_SERVICE_NAME}")
        logger.info(f"UUID: {BLUETOOTH_SERVICE_UUID}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao inicializar servidor Bluetooth: {e}")
        bluetooth_server_socket = None
        return False

def aceitar_conexoes_bluetooth():
    """Loop principal para aceitar conexões Bluetooth"""
    global bluetooth_server_socket, connected_client_socket, bluetooth_connected, connected_device_info
    
    logger.info("Aguardando conexões Bluetooth...")
    
    while True:
        try:
            if not bluetooth_server_socket:
                logger.warning("Socket Bluetooth não disponível, tentando reinicializar...")
                time.sleep(10)
                inicializar_bluetooth_server()
                continue
            
            # Aceita conexão
            logger.info("Esperando cliente conectar...")
            client_socket, client_address = bluetooth_server_socket.accept()
            logger.info(f"Cliente Bluetooth conectado: {client_address}")
            
            # Desconecta cliente anterior se existir
            if connected_client_socket:
                try:
                    connected_client_socket.close()
                except:
                    pass
            
            # Configura nova conexão
            connected_client_socket = client_socket
            bluetooth_connected = True
            
            # Obtém nome do dispositivo
            try:
                device_name = lookup_name(client_address, timeout=5)
                connected_device_info = {
                    'address': client_address,
                    'name': device_name or f'Dispositivo-{client_address}'
                }
            except:
                connected_device_info = {
                    'address': client_address,
                    'name': f'Dispositivo-{client_address}'
                }
            
            logger.info(f"Dispositivo conectado: {connected_device_info['name']} ({client_address})")
            
            # Registra dispositivo no banco
            registrar_dispositivo_bluetooth(connected_device_info)
            
            # Thread para comunicação com este cliente
            client_thread = threading.Thread(
                target=gerenciar_cliente_bluetooth,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()
            
        except Exception as e:
            logger.error(f"Erro ao aceitar conexão: {e}")
            time.sleep(5)

def gerenciar_cliente_bluetooth(client_socket, client_address):
    """Gerencia comunicação com um cliente específico"""
    global bluetooth_connected, connected_client_socket, connected_device_info
    
    try:
        # Configura timeout do socket
        client_socket.settimeout(30.0)
        
        # Envia handshake
        enviar_handshake_bluetooth(client_socket)
        
        buffer = ""
        
        while True:
            try:
                # Recebe dados
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    logger.info(f"Cliente {client_address} desconectou (sem dados)")
                    break
                
                buffer += data
                
                # Processa mensagens completas (separadas por \n)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        processar_mensagem_bluetooth(line.strip(), client_socket, client_address)
                
            except socket.timeout:
                # Envia ping para verificar conexão
                ping_payload = {
                    "action": "ping",
                    "timestamp": datetime.now().isoformat()
                }
                if not enviar_bluetooth(client_socket, ping_payload):
                    logger.warning(f"Falha no ping para {client_address}")
                    break
                continue
                
            except Exception as e:
                logger.error(f"Erro na comunicação com {client_address}: {e}")
                break
        
    except Exception as e:
        logger.error(f"Erro no gerenciamento do cliente {client_address}: {e}")
    
    finally:
        # Cleanup da conexão
        try:
            client_socket.close()
        except:
            pass
        
        if connected_client_socket == client_socket:
            connected_client_socket = None
            bluetooth_connected = False
            connected_device_info = None
            logger.info("Dispositivo principal desconectado")
        
        logger.info(f"Cliente {client_address} desconectado")

def enviar_handshake_bluetooth(client_socket):
    """Envia handshake inicial"""
    try:
        handshake = {
            "action": "handshake",
            "server": "Magic Mirror Events Server",
            "protocol": "bluetooth_rfcomm",
            "version": "2.0",
            "service_uuid": BLUETOOTH_SERVICE_UUID,
            "timestamp": datetime.now().isoformat()
        }
        
        enviar_bluetooth(client_socket, handshake)
        logger.info("Handshake enviado")
        
    except Exception as e:
        logger.error(f"Erro no handshake: {e}")

def processar_mensagem_bluetooth(message_str, client_socket, client_address):
    """Processa mensagem recebida"""
    try:
        message = json.loads(message_str)
        action = message.get("action", "")
        device_id = message.get("device_id", client_address.replace(':', ''))
        
        logger.info(f"Mensagem recebida: {action} de {client_address}")
        
        # Atualiza heartbeat
        atualizar_heartbeat_dispositivo(device_id)
        
        # Roteamento de ações
        if action == "ping":
            processar_ping_bluetooth(client_socket, device_id)
        elif action == "device_info":
            processar_info_dispositivo_bluetooth(message, client_socket, client_address)
        elif action == "device_status":
            processar_status_dispositivo_bluetooth(message)
        elif action == "event_completed":
            processar_evento_concluido(message)
        elif action == "event_ack":
            processar_ack_evento(message)
        elif action == "sync_complete":
            processar_sync_completo_bluetooth(message)
        elif action == "request_events":
            sincronizar_dispositivo_bluetooth(client_socket, device_id)
        else:
            logger.warning(f"Ação desconhecida: {action}")
            
    except json.JSONDecodeError as e:
        logger.warning(f"JSON inválido recebido: {e} - Data: {message_str}")
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

def processar_ping_bluetooth(client_socket, device_id):
    """Responde a ping"""
    response = {
        "action": "ping_response",
        "device_id": device_id,
        "server_time": datetime.now().isoformat(),
        "status": "ok"
    }
    enviar_bluetooth(client_socket, response)

def processar_info_dispositivo_bluetooth(data, client_socket, client_address):
    """Processa informações do dispositivo"""
    device_id = data.get("device_id", client_address.replace(':', ''))
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, bluetooth_address, status, communication_type, 
             firmware_version, last_sync, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            data.get('name', 'Magic Mirror'),
            client_address,
            'online',
            'bluetooth',
            data.get('firmware_version', '2.0.0'),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Dispositivo registrado: {device_id}")
        
        # Sincroniza eventos automaticamente
        sincronizar_dispositivo_bluetooth(client_socket, device_id)
        
    except Exception as e:
        logger.error(f"Erro ao registrar dispositivo: {e}")

def processar_status_dispositivo_bluetooth(data):
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
        
        logger.info(f"Status atualizado: {device_id} - {status}")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar status: {e}")

def processar_sync_completo_bluetooth(data):
    """Processa confirmação de sincronização"""
    device_id = data.get("device_id")
    events_count = data.get("events_count", 0)
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Atualiza dispositivo
        cursor.execute('''
            UPDATE pico_devices 
            SET last_sync = ?, events_count = ?
            WHERE device_id = ?
        ''', (datetime.now().isoformat(), events_count, device_id))
        
        # Marca eventos como sincronizados
        hoje = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE eventos 
            SET sincronizado = 1 
            WHERE data = ? AND sincronizado = 0
        ''', (hoje,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Sincronização completa: {device_id} ({events_count} eventos)")
        
    except Exception as e:
        logger.error(f"Erro ao processar sync: {e}")

def processar_evento_concluido(data):
    """Remove evento concluído"""
    event_id = data.get("event_id")
    
    if event_id:
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                logger.info(f"Evento {event_id} concluído e removido")
                
        except Exception as e:
            logger.error(f"Erro ao processar evento concluído: {e}")

def processar_ack_evento(data):
    """Processa confirmação de evento"""
    event_id = data.get("event_id")
    logger.info(f"ACK recebido para evento {event_id}")

def enviar_bluetooth(client_socket, data):
    """Envia dados via Bluetooth"""
    try:
        message = safe_json_dumps(data) + "\n"
        client_socket.send(message.encode('utf-8'))
        logger.debug(f"Enviado: {data.get('action', 'unknown')}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao enviar via Bluetooth: {e}")
        return False

def sincronizar_dispositivo_bluetooth(client_socket, device_id):
    """Sincroniza eventos de hoje"""
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
        
        # Formata eventos
        events_list = []
        for event_id, nome, hora, data in eventos_hoje:
            events_list.append({
                "id": event_id,
                "nome": nome,
                "hora": hora,
                "data": data
            })
        
        # Envia sincronização
        payload = {
            "action": "sync_events",
            "device_id": device_id,
            "events": events_list,
            "sync_time": datetime.now().isoformat(),
            "filter_date": hoje
        }
        
        if enviar_bluetooth(client_socket, payload):
            logger.info(f"Enviados {len(events_list)} eventos para {device_id}")
        
    except Exception as e:
        logger.error(f"Erro na sincronização: {e}")

def registrar_dispositivo_bluetooth(device_info):
    """Registra dispositivo no banco"""
    try:
        device_id = device_info['address'].replace(':', '')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, bluetooth_address, status, communication_type, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            device_info['name'],
            device_info['address'],
            'online',
            'bluetooth',
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Erro ao registrar: {e}")

def atualizar_heartbeat_dispositivo(device_id):
    """Atualiza último heartbeat"""
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
    except:
        pass

def descobrir_dispositivos_bluetooth():
    """Descobre dispositivos Bluetooth"""
    global discovered_devices, scanning
    
    if not BLUETOOTH_AVAILABLE:
        logger.error("Bluetooth não disponível")
        return []
    
    if scanning:
        return discovered_devices
    
    scanning = True
    discovered_devices = []
    
    try:
        logger.info("Iniciando descoberta de dispositivos...")
        
        nearby_devices = discover_devices(
            duration=10, 
            lookup_names=True, 
            flush_cache=True
        )
        
        for addr, name in nearby_devices:
            device_info = {
                'address': addr,
                'name': name or f'Dispositivo-{addr}',
                'rssi': -50  # Valor padrão
            }
            discovered_devices.append(device_info)
            logger.info(f"Encontrado: {name} ({addr})")
        
        logger.info(f"Descoberta finalizada: {len(discovered_devices)} dispositivos")
        
    except Exception as e:
        logger.error(f"Erro na descoberta: {e}")
    finally:
        scanning = False
    
    return discovered_devices

# ===== THREAD BLUETOOTH =====
def iniciar_comunicacao_bluetooth():
    """Inicia sistema Bluetooth"""
    if not BLUETOOTH_AVAILABLE:
        logger.error("Sistema Bluetooth não disponível - pybluez não instalado")
        return
    
    def servidor_bluetooth():
        if inicializar_bluetooth_server():
            aceitar_conexoes_bluetooth()
        else:
            logger.error("Falha ao inicializar servidor Bluetooth")
    
    thread = threading.Thread(target=servidor_bluetooth, daemon=True)
    thread.start()
    logger.info("Sistema Bluetooth iniciado")

# ===== INICIALIZAÇÃO =====
init_db()
iniciar_comunicacao_bluetooth()

# ===== ROTAS HTTP =====
@app.route('/')
def serve_index():
    """Serve página principal"""
    # Procura index.html em diferentes locais
    for path in ['.', 'templates', 'static']:
        index_path = os.path.join(path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(path, 'index.html')
    
    # Se não encontrar, retorna HTML básico
    return '''
    <html>
    <head><title>Magic Mirror</title></head>
    <body>
    <h1>Magic Mirror Server</h1>
    <p>Servidor rodando. Interface web não encontrada.</p>
    <p>Status Bluetooth: ''' + str(get_bluetooth_status()) + '''</p>
    </body>
    </html>
    '''

# EVENTOS
@app.route('/api/eventos', methods=['POST'])
def adicionar_evento():
    """Adiciona novo evento"""
    data = request.get_json()
    nome = data.get('nome')
    data_evento = data.get('data')
    hora_evento = data.get('hora')
    
    if not all([nome, data_evento, hora_evento]):
        return jsonify({"erro": "Campos obrigatórios faltando"}), 400

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO eventos (nome, data, hora, criado_em, sincronizado) VALUES (?, ?, ?, ?, ?)",
            (nome, data_evento, hora_evento, datetime.now().isoformat(), 0)
        )
        evento_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Evento criado: {nome} em {data_evento} às {hora_evento}")

        # Envia para dispositivo se for hoje e conectado
        hoje = datetime.now().strftime('%Y-%m-%d')
        if data_evento == hoje and connected_client_socket and bluetooth_connected:
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
            
            if enviar_bluetooth(connected_client_socket, payload):
                # Marca como sincronizado
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE id = ?", (evento_id,))
                conn.commit()
                conn.close()

        return jsonify({'mensagem': 'Evento cadastrado!', 'id': evento_id}), 201
    
    except Exception as e:
        logger.error(f"Erro ao adicionar evento: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos', methods=['GET'])
def listar_eventos():
    """Lista todos os eventos"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, data, hora, sincronizado FROM eventos ORDER BY data, hora")
        eventos = cursor.fetchall()
        conn.close()

        return jsonify([
            {
                'id': id, 'nome': nome, 'data': data, 
                'hora': hora, 'sincronizado': bool(sincronizado)
            }
            for id, nome, data, hora, sincronizado in eventos
        ])
    
    except Exception as e:
        logger.error(f"Erro ao listar eventos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos-hoje', methods=['GET'])
def eventos_hoje():
    """Lista eventos de hoje"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, nome, hora, sincronizado FROM eventos WHERE data = ? ORDER BY hora", 
            (hoje,)
        )
        eventos = cursor.fetchall()
        conn.close()

        return jsonify([
            {'id': id, 'nome': nome, 'hora': hora, 'sincronizado': bool(sincronizado)}
            for id, nome, hora, sincronizado in eventos
        ])
    
    except Exception as e:
        logger.error(f"Erro ao listar eventos de hoje: {e}")
        return jsonify({"erro": "Erro interno"}), 500

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
            # Notifica dispositivo
            if connected_client_socket and bluetooth_connected:
                payload = {
                    "action": "remove_all_events",
                    "timestamp": datetime.now().isoformat()
                }
                enviar_bluetooth(connected_client_socket, payload)
            
            return jsonify({'mensagem': f'{rows_affected} eventos deletados'}), 200
        else:
            return jsonify({"erro": "Nenhum evento para deletar"}), 404
    
    except Exception as e:
        logger.error(f"Erro ao deletar eventos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos/<int:evento_id>', methods=['DELETE'])
def deletar_evento(evento_id):
    """Deleta um evento específico"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        if rows_affected > 0:
            # Notifica dispositivo
            if connected_client_socket and bluetooth_connected:
                payload = {
                    "action": "remove_event",
                    "event_id": evento_id,
                    "timestamp": datetime.now().isoformat()
                }
                enviar_bluetooth(connected_client_socket, payload)
            
            return jsonify({'mensagem': 'Evento deletado'}), 200
        else:
            return jsonify({"erro": "Evento não encontrado"}), 404
    
    except Exception as e:
        logger.error(f"Erro ao deletar evento: {e}")
        return jsonify({"erro": "Erro interno"}), 500

# SISTEMA
@app.route('/api/sistema/info', methods=['GET'])
def info_sistema():
    """Informações do sistema"""
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
        
        status = get_bluetooth_status()
        
        return jsonify({
            'eventos_hoje': eventos_hoje_count,
            'total_eventos': total_eventos,
            'total_dispositivos': total_dispositivos,
            'protocolo': 'Bluetooth RFCOMM',
            'bluetooth_conectado': status['connected'],
            'bluetooth_disponivel': status['available'],
            'dispositivo_conectado': connected_device_info['name'] if connected_device_info else None,
            'versao': '2.0-Bluetooth',
            'modo': 'OFFLINE',
            'data_atual': hoje
        }), 200
    
    except Exception as e:
        logger.error(f"Erro ao obter info do sistema: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/sincronizar', methods=['POST'])
def sincronizar_manual():
    """Sincronização manual"""
    try:
        if not connected_client_socket or not bluetooth_connected:
            return jsonify({"erro": "Nenhum dispositivo conectado"}), 400
        
        device_id = connected_device_info['address'].replace(':', '') if connected_device_info else 'unknown'
        sincronizar_dispositivo_bluetooth(connected_client_socket, device_id)
        
        return jsonify({
            'mensagem': f'Sincronização iniciada para {connected_device_info.get("name", "dispositivo")}',
            'dispositivos_sincronizados': 1
        }), 200
    
    except Exception as e:
        logger.error(f"Erro na sincronização: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/dispositivos', methods=['GET'])
def listar_dispositivos():
    """Lista dispositivos registrados"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT device_id, name, bluetooth_address, status, last_sync, events_count, 
                   firmware_version, last_heartbeat, created_at
            FROM pico_devices 
            ORDER BY created_at DESC
        """)
        dispositivos = cursor.fetchall()
        conn.close()

        dispositivos_formatados = []
        for row in dispositivos:
            device_id, name, bt_addr, status, last_sync, events_count, fw_ver, last_hb, created = row
            
            # Verifica se está conectado atualmente
            current_status = 'online' if (
                bluetooth_connected and 
                connected_device_info and 
                connected_device_info['address'] == bt_addr
            ) else 'offline'
            
            dispositivos_formatados.append({
                'device_id': device_id,
                'name': name,
                'bluetooth_address': bt_addr,
                'status': current_status,
                'last_sync': last_sync,
                'events_count': events_count or 0,
                'firmware_version': fw_ver or 'Unknown',
                'last_heartbeat': last_hb,
                'created_at': created,
                'connection_type': 'Bluetooth RFCOMM'
            })

        return jsonify(dispositivos_formatados)
    
    except Exception as e:
        logger.error(f"Erro ao listar dispositivos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

# BLUETOOTH ESPECÍFICO
@app.route('/api/bluetooth/scan', methods=['POST'])
def iniciar_scan_bluetooth():
    """Inicia descoberta de dispositivos"""
    if not BLUETOOTH_AVAILABLE:
        return jsonify({"erro": "Bluetooth não disponível"}), 400
    
    try:
        # Inicia em thread separada
        scan_thread = threading.Thread(target=descobrir_dispositivos_bluetooth, daemon=True)
        scan_thread.start()
        
        return jsonify({'mensagem': 'Descoberta iniciada'}), 200
    
    except Exception as e:
        logger.error(f"Erro ao iniciar scan: {e}")
        return jsonify({"erro": "Erro ao iniciar descoberta"}), 500

@app.route('/api/bluetooth/scan/stop', methods=['POST'])
def parar_scan_bluetooth():
    """Para descoberta"""
    global scanning
    scanning = False
    return jsonify({'mensagem': 'Descoberta interrompida'}), 200

@app.route('/api/bluetooth/devices', methods=['GET'])
def listar_dispositivos_descobertos():
    """Lista dispositivos descobertos"""
    return jsonify(discovered_devices)

@app.route('/api/bluetooth/connect', methods=['POST'])
def conectar_bluetooth():
    """Conecta a dispositivo específico (modo cliente ativo)"""
    if not BLUETOOTH_AVAILABLE:
        return jsonify({"erro": "Bluetooth não disponível"}), 400
    
    try:
        data = request.get_json()
        address = data.get('address')
        name = data.get('name', 'Dispositivo')
        
        if not address:
            return jsonify({"erro": "Endereço obrigatório"}), 400
        
        # Conecta em thread separada para não bloquear
        def conectar_async():
            try:
                logger.info(f"Tentando conectar a {name} ({address})")
                
                # Busca serviços disponíveis
                services = find_service(address=address)
                
                if not services:
                    logger.warning(f"Nenhum serviço encontrado em {address}")
                    return False
                
                # Procura serviço RFCOMM
                target_service = None
                for service in services:
                    if service.get('protocol') == 'RFCOMM':
                        target_service = service
                        break
                
                if not target_service:
                    target_service = services[0]  # Usa primeiro disponível
                
                # Conecta
                sock = BluetoothSocket(RFCOMM)
                sock.connect((address, target_service['port']))
                sock.settimeout(30.0)
                
                # Atualiza estado global
                global connected_client_socket, bluetooth_connected, connected_device_info
                
                # Fecha conexão anterior
                if connected_client_socket:
                    try:
                        connected_client_socket.close()
                    except:
                        pass
                
                connected_client_socket = sock
                bluetooth_connected = True
                connected_device_info = {'address': address, 'name': name}
                
                logger.info(f"Conectado a {name} ({address})")
                
                # Registra no banco
                registrar_dispositivo_bluetooth(connected_device_info)
                
                # Gerencia comunicação
                gerenciar_cliente_bluetooth(sock, address)
                
            except Exception as e:
                logger.error(f"Erro ao conectar: {e}")
        
        connect_thread = threading.Thread(target=conectar_async, daemon=True)
        connect_thread.start()
        
        return jsonify({'mensagem': f'Conectando a {name}...'}), 200
    
    except Exception as e:
        logger.error(f"Erro na conexão: {e}")
        return jsonify({"erro": "Erro de conexão"}), 500

@app.route('/api/bluetooth/status', methods=['GET'])
def status_bluetooth():
    """Status da conexão"""
    return jsonify(get_bluetooth_status()), 200

@app.route('/api/bluetooth/disconnect', methods=['POST'])
def desconectar_bluetooth():
    """Desconecta dispositivo atual"""
    global connected_client_socket, bluetooth_connected, connected_device_info
    
    try:
        device_name = connected_device_info.get('name', 'dispositivo') if connected_device_info else 'dispositivo'
        
        if connected_client_socket:
            connected_client_socket.close()
            connected_client_socket = None
        
        bluetooth_connected = False
        connected_device_info = None
        
        return jsonify({'mensagem': f'Desconectado de {device_name}'}), 200
    
    except Exception as e:
        logger.error(f"Erro ao desconectar: {e}")
        return jsonify({"erro": "Erro na desconexão"}), 500

# MAIN
if __name__ == '__main__':
    print("=" * 60)
    print("MAGIC MIRROR - SERVIDOR BLUETOOTH")
    print("=" * 60)
    print(f"Bluetooth disponível: {BLUETOOTH_AVAILABLE}")
    if BLUETOOTH_AVAILABLE:
        print(f"Serviço: {BLUETOOTH_SERVICE_NAME}")
        print(f"UUID: {BLUETOOTH_SERVICE_UUID}")
        print(f"Porta RFCOMM: {BLUETOOTH_PORT}")
    else:
        print("ATENÇÃO: Instale pybluez com: pip install pybluez")
    print("=" * 60)
    print("Servidor iniciando em http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)