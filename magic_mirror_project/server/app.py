from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import threading
import time
import logging
import os
import sys
import asyncio

# Importação BLE
try:
    import bleak
    from bleak import BleakScanner, BleakClient, BleakServer, BleakGATTCharacteristic, BleakGATTService
    from bleak.backends.service import BleakGATTService
    from bleak.backends.characteristic import BleakGATTCharacteristic
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False
    print("ERRO: Biblioteca bleak não encontrada. Instale com: pip install bleak")

app = Flask(__name__)
CORS(app)

# ===== CONFIGURAÇÕES BLE =====
BLE_SERVICE_UUID = "94f39d29-7d6d-437d-973b-fba39e49d4ee"
BLE_CHAR_UUID = "94f39d29-7d6d-437d-973b-fba39e49d4ef"
BLE_SERVER_NAME = "Magic Mirror Server"

# Variáveis globais BLE
ble_server = None
ble_connected = False
ble_client_device = None
ble_message_buffer = ""
discovered_devices = []
scanning = False
ble_loop = None
ble_thread = None

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
    
    # Tabela de dispositivos BLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Magic Mirror',
            ble_address TEXT,
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            communication_type TEXT DEFAULT 'ble',
            signal_strength INTEGER DEFAULT 0,
            firmware_version TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            events_count INTEGER DEFAULT 0,
            last_heartbeat TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado para BLE")

# ===== FUNÇÕES BLE SERVIDOR =====
class BLEServer:
    def __init__(self):
        self.server = None
        self.service = None
        self.characteristic = None
        self.connected_device = None
        self.message_buffer = ""
        
    async def start_server(self):
        """Inicia servidor BLE"""
        try:
            logger.info("Iniciando servidor BLE...")
            
            # Cria serviço e característica
            service = BleakGATTService(BLE_SERVICE_UUID, "Magic Mirror Service", True)
            
            char = BleakGATTCharacteristic(
                BLE_CHAR_UUID,
                ["read", "write", "notify"],
                service,
                "Magic Mirror Data"
            )
            
            service.add_characteristic(char)
            
            # Inicia servidor
            self.server = BleakServer(name=BLE_SERVER_NAME)
            self.server.add_service(service)
            
            # Callbacks
            self.server.set_connect_callback(self.on_connect)
            self.server.set_disconnect_callback(self.on_disconnect)
            char.set_write_callback(self.on_write)
            
            await self.server.start()
            logger.info(f"Servidor BLE iniciado: {BLE_SERVER_NAME}")
            
            self.service = service
            self.characteristic = char
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao iniciar servidor BLE: {e}")
            return False
    
    async def on_connect(self, device):
        """Callback de conexão"""
        global ble_connected, ble_client_device
        
        self.connected_device = device
        ble_connected = True
        ble_client_device = {
            'address': device.address,
            'name': device.name or f"Dispositivo-{device.address[-6:]}"
        }
        
        logger.info(f"Cliente BLE conectado: {ble_client_device['name']} ({device.address})")
        
        # Registra dispositivo
        registrar_dispositivo_ble(ble_client_device)
        
        # Envia handshake
        await self.send_handshake()
    
    async def on_disconnect(self, device):
        """Callback de desconexão"""
        global ble_connected, ble_client_device
        
        logger.info(f"Cliente BLE desconectado: {device.address}")
        
        ble_connected = False
        ble_client_device = None
        self.connected_device = None
        self.message_buffer = ""
    
    async def on_write(self, characteristic, data):
        """Callback de escrita"""
        try:
            message_part = data.decode('utf-8')
            self.message_buffer += message_part
            
            # Processa mensagens completas
            while '\n' in self.message_buffer:
                line, self.message_buffer = self.message_buffer.split('\n', 1)
                if line.strip():
                    await self.processar_mensagem(line.strip())
                    
        except Exception as e:
            logger.error(f"Erro ao processar escrita BLE: {e}")
    
    async def processar_mensagem(self, message_str):
        """Processa mensagem recebida"""
        try:
            message = json.loads(message_str)
            action = message.get("action", "")
            device_id = message.get("device_id", "")
            
            logger.info(f"Mensagem BLE: {action} de {device_id}")
            
            # Atualiza heartbeat
            atualizar_heartbeat_dispositivo(device_id)
            
            if action == "ping":
                await self.send_ping_response(device_id)
            elif action == "device_info":
                await self.processar_device_info(message)
            elif action == "device_status":
                processar_status_dispositivo_ble(message)
            elif action == "event_completed":
                processar_evento_concluido(message)
            elif action == "sync_complete":
                processar_sync_completo_ble(message)
            elif action == "request_events":
                await self.sincronizar_eventos(device_id)
            else:
                logger.warning(f"Ação BLE desconhecida: {action}")
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON inválido: {e} - {message_str}")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem BLE: {e}")
    
    async def send_handshake(self):
        """Envia handshake inicial"""
        handshake = {
            "action": "handshake",
            "server": "Magic Mirror BLE Server",
            "protocol": "ble",
            "version": "2.0",
            "timestamp": datetime.now().isoformat()
        }
        
        await self.send_data(handshake)
    
    async def send_ping_response(self, device_id):
        """Responde ping"""
        response = {
            "action": "ping_response",
            "device_id": device_id,
            "server_time": datetime.now().isoformat(),
            "status": "ok"
        }
        await self.send_data(response)
    
    async def processar_device_info(self, data):
        """Processa informações do dispositivo"""
        device_id = data.get("device_id")
        
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO pico_devices 
                (device_id, name, ble_address, status, communication_type, 
                 firmware_version, last_sync, last_heartbeat) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id,
                data.get('name', 'Magic Mirror BLE'),
                ble_client_device['address'] if ble_client_device else '',
                'online',
                'ble',
                data.get('firmware_version', '2.0.0-BLE'),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Dispositivo BLE registrado: {device_id}")
            
            # Sincroniza eventos automaticamente
            await self.sincronizar_eventos(device_id)
            
        except Exception as e:
            logger.error(f"Erro ao processar device info: {e}")
    
    async def sincronizar_eventos(self, device_id):
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
            
            events_list = []
            for event_id, nome, hora, data in eventos_hoje:
                events_list.append({
                    "id": event_id,
                    "nome": nome,
                    "hora": hora,
                    "data": data
                })
            
            payload = {
                "action": "sync_events",
                "device_id": device_id,
                "events": events_list,
                "sync_time": datetime.now().isoformat(),
                "filter_date": hoje
            }
            
            await self.send_data(payload)
            logger.info(f"Sincronizados {len(events_list)} eventos para {device_id}")
            
        except Exception as e:
            logger.error(f"Erro na sincronização: {e}")
    
    async def send_data(self, data):
        """Envia dados para cliente"""
        if not self.connected_device or not self.characteristic:
            return False
        
        try:
            message = json.dumps(data, ensure_ascii=False)
            
            # Divide em chunks para respeitar MTU
            chunk_size = 20
            chunks = [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]
            
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    chunk += "\n"  # Marca fim da mensagem
                
                await self.characteristic.notify(chunk.encode('utf-8'))
                await asyncio.sleep(0.01)  # Pequeno delay
            
            logger.debug(f"Enviado BLE: {data.get('action', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao enviar BLE: {e}")
            return False

# Instância global do servidor BLE
ble_server_instance = None

# ===== FUNÇÕES BLE CLIENTE (DESCOBERTA) =====
async def scan_ble_devices():
    """Escaneia dispositivos BLE"""
    global discovered_devices
    
    if not BLE_AVAILABLE:
        return []
    
    try:
        logger.info("Escaneando dispositivos BLE...")
        devices = await BleakScanner.discover(timeout=10.0)
        
        ble_devices = []
        for device in devices:
            if device.name and ("MagicMirror" in device.name or "Magic" in device.name):
                device_info = {
                    'address': device.address,
                    'name': device.name,
                    'rssi': getattr(device, 'rssi', -50),
                    'type': 'BLE'
                }
                ble_devices.append(device_info)
                logger.info(f"Dispositivo BLE encontrado: {device.name} ({device.address})")
        
        discovered_devices.extend(ble_devices)
        return ble_devices
        
    except Exception as e:
        logger.error(f"Erro no scan BLE: {e}")
        return []

# ===== FUNÇÕES AUXILIARES =====
def registrar_dispositivo_ble(device_info):
    """Registra dispositivo BLE no banco"""
    try:
        device_id = device_info['address'].replace(':', '').replace('-', '')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, ble_address, status, communication_type, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            device_info['name'],
            device_info['address'],
            'online',
            'ble',
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Dispositivo BLE registrado: {device_info['name']}")
        
    except Exception as e:
        logger.error(f"Erro ao registrar dispositivo BLE: {e}")

def processar_status_dispositivo_ble(data):
    """Processa status do dispositivo BLE"""
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
        
        logger.info(f"Status BLE atualizado: {device_id} - {status}")
        
    except Exception as e:
        logger.error(f"Erro ao atualizar status BLE: {e}")

def processar_sync_completo_ble(data):
    """Processa confirmação de sincronização BLE"""
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
        
        # Marca eventos como sincronizados
        hoje = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE eventos 
            SET sincronizado = 1 
            WHERE data = ? AND sincronizado = 0
        ''', (hoje,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Sincronização BLE completa: {device_id} ({events_count} eventos)")
        
    except Exception as e:
        logger.error(f"Erro ao processar sync BLE: {e}")

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

# ===== THREAD BLE =====
def run_ble_loop():
    """Roda loop BLE em thread separada"""
    global ble_loop, ble_server_instance
    
    ble_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ble_loop)
    
    async def main_ble():
        if BLE_AVAILABLE:
            ble_server_instance = BLEServer()
            await ble_server_instance.start_server()
            
            # Mantém servidor rodando
            while True:
                await asyncio.sleep(1)
        else:
            logger.error("BLE não disponível")
    
    try:
        ble_loop.run_until_complete(main_ble())
    except Exception as e:
        logger.error(f"Erro no loop BLE: {e}")

def iniciar_comunicacao_ble():
    """Inicia sistema BLE"""
    global ble_thread
    
    if not BLE_AVAILABLE:
        logger.error("Sistema BLE não disponível - bleak não instalado")
        return
    
    ble_thread = threading.Thread(target=run_ble_loop, daemon=True)
    ble_thread.start()
    logger.info("Sistema BLE iniciado")

def descobrir_dispositivos_ble():
    """Descobre dispositivos BLE"""
    global discovered_devices, scanning
    
    if not BLE_AVAILABLE:
        logger.error("BLE não disponível")
        return []
    
    if scanning:
        return discovered_devices
    
    scanning = True
    discovered_devices = []
    
    try:
        # Executa scan em loop próprio
        def run_scan():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scan_ble_devices())
            loop.close()
        
        scan_thread = threading.Thread(target=run_scan, daemon=True)
        scan_thread.start()
        scan_thread.join(timeout=15)
        
    except Exception as e:
        logger.error(f"Erro na descoberta BLE: {e}")
    finally:
        scanning = False
    
    return discovered_devices

# ===== INICIALIZAÇÃO =====
init_db()
iniciar_comunicacao_ble()

# ===== ROTAS HTTP =====
@app.route('/')
def serve_index():
    """Serve página principal"""
    for path in ['.', 'templates', 'static']:
        index_path = os.path.join(path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(path, 'index.html')
    
    return f'''
    <html>
    <head><title>Magic Mirror BLE</title></head>
    <body>
    <h1>Magic Mirror BLE Server</h1>
    <p>Servidor BLE rodando</p>
    <p>BLE Disponível: {BLE_AVAILABLE}</p>
    <p>Conectado: {ble_connected}</p>
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
        if data_evento == hoje and ble_connected and ble_server_instance:
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
            
            # Envia assincronamente
            def send_async():
                if ble_loop:
                    asyncio.run_coroutine_threadsafe(
                        ble_server_instance.send_data(payload), 
                        ble_loop
                    )
            
            threading.Thread(target=send_async, daemon=True).start()

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
            # Notifica dispositivo BLE
            if ble_connected and ble_server_instance:
                payload = {
                    "action": "remove_all_events",
                    "timestamp": datetime.now().isoformat()
                }
                
                def send_async():
                    if ble_loop:
                        asyncio.run_coroutine_threadsafe(
                            ble_server_instance.send_data(payload), 
                            ble_loop
                        )
                
                threading.Thread(target=send_async, daemon=True).start()
            
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
            # Notifica dispositivo BLE
            if ble_connected and ble_server_instance:
                payload = {
                    "action": "remove_event",
                    "event_id": evento_id,
                    "timestamp": datetime.now().isoformat()
                }
                
                def send_async():
                    if ble_loop:
                        asyncio.run_coroutine_threadsafe(
                            ble_server_instance.send_data(payload), 
                            ble_loop
                        )
                
                threading.Thread(target=send_async, daemon=True).start()
            
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
        
        return jsonify({
            'eventos_hoje': eventos_hoje_count,
            'total_eventos': total_eventos,
            'total_dispositivos': total_dispositivos,
            'protocolo': 'Bluetooth Low Energy (BLE)',
            'bluetooth_conectado': ble_connected,
            'bluetooth_disponivel': BLE_AVAILABLE,
            'dispositivo_conectado': ble_client_device['name'] if ble_client_device else None,
            'versao': '2.0-BLE',
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
        if not ble_connected or not ble_server_instance:
            return jsonify({"erro": "Nenhum dispositivo BLE conectado"}), 400
        
        device_id = ble_client_device['address'].replace(':', '').replace('-', '') if ble_client_device else 'unknown'
        
        # Sincroniza assincronamente
        def sync_async():
            if ble_loop:
                asyncio.run_coroutine_threadsafe(
                    ble_server_instance.sincronizar_eventos(device_id), 
                    ble_loop
                )
        
        threading.Thread(target=sync_async, daemon=True).start()
        
        return jsonify({
            'mensagem': f'Sincronização BLE iniciada para {ble_client_device.get("name", "dispositivo")}',
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
            SELECT device_id, name, ble_address, status, last_sync, events_count, 
                   firmware_version, last_heartbeat, created_at
            FROM pico_devices 
            ORDER BY created_at DESC
        """)
        dispositivos = cursor.fetchall()
        conn.close()

        dispositivos_formatados = []
        for row in dispositivos:
            device_id, name, ble_addr, status, last_sync, events_count, fw_ver, last_hb, created = row
            
            # Verifica se está conectado atualmente
            current_status = 'online' if (
                ble_connected and 
                ble_client_device and 
                ble_client_device['address'] == ble_addr
            ) else 'offline'
            
            dispositivos_formatados.append({
                'device_id': device_id,
                'name': name,
                'ble_address': ble_addr,
                'status': current_status,
                'last_sync': last_sync,
                'events_count': events_count or 0,
                'firmware_version': fw_ver or 'Unknown',
                'last_heartbeat': last_hb,
                'created_at': created,
                'connection_type': 'Bluetooth Low Energy (BLE)'
            })

        return jsonify(dispositivos_formatados)
    
    except Exception as e:
        logger.error(f"Erro ao listar dispositivos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

# BLE ESPECÍFICO
@app.route('/api/bluetooth/scan', methods=['POST'])
def iniciar_scan_ble():
    """Inicia descoberta de dispositivos BLE"""
    if not BLE_AVAILABLE:
        return jsonify({"erro": "BLE não disponível"}), 400
    
    try:
        # Inicia scan em thread separada
        scan_thread = threading.Thread(target=descobrir_dispositivos_ble, daemon=True)
        scan_thread.start()
        
        return jsonify({'mensagem': 'Descoberta BLE iniciada'}), 200
    
    except Exception as e:
        logger.error(f"Erro ao iniciar scan BLE: {e}")
        return jsonify({"erro": "Erro ao iniciar descoberta BLE"}), 500

@app.route('/api/bluetooth/scan/stop', methods=['POST'])
def parar_scan_ble():
    """Para descoberta BLE"""
    global scanning
    scanning = False
    return jsonify({'mensagem': 'Descoberta BLE interrompida'}), 200

@app.route('/api/bluetooth/devices', methods=['GET'])
def listar_dispositivos_descobertos():
    """Lista dispositivos BLE descobertos"""
    return jsonify(discovered_devices)

@app.route('/api/bluetooth/status', methods=['GET'])
def status_ble():
    """Status da conexão BLE"""
    return jsonify({
        'connected': ble_connected,
        'device': ble_client_device,
        'scanning': scanning,
        'server_running': ble_server_instance is not None,
        'ble_available': BLE_AVAILABLE
    }), 200

@app.route('/api/bluetooth/disconnect', methods=['POST'])
def desconectar_ble():
    """Desconecta dispositivo BLE atual"""
    global ble_connected, ble_client_device
    
    try:
        device_name = ble_client_device.get('name', 'dispositivo') if ble_client_device else 'dispositivo'
        
        # Força desconexão
        if ble_server_instance and ble_server_instance.connected_device:
            def disconnect_async():
                if ble_loop:
                    # BLE desconecta automaticamente quando cliente para
                    pass
            
            threading.Thread(target=disconnect_async, daemon=True).start()
        
        ble_connected = False
        ble_client_device = None
        
        return jsonify({'mensagem': f'Desconectado de {device_name}'}), 200
    
    except Exception as e:
        logger.error(f"Erro ao desconectar BLE: {e}")
        return jsonify({"erro": "Erro na desconexão BLE"}), 500

# MAIN
if __name__ == '__main__':
    print("=" * 60)
    print("MAGIC MIRROR - SERVIDOR BLE")
    print("=" * 60)
    print(f"BLE disponível: {BLE_AVAILABLE}")
    if BLE_AVAILABLE:
        print(f"Serviço: {BLE_SERVER_NAME}")
        print(f"UUID Serviço: {BLE_SERVICE_UUID}")
        print(f"UUID Característica: {BLE_CHAR_UUID}")
    else:
        print("ATENÇÃO: Instale bleak com: pip install bleak")
    print("=" * 60)
    print("Servidor iniciando em http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)