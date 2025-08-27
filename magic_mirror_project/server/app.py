from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import json
import threading
import time
import logging
import os
import asyncio

# BLE
try:
    import bleak
    from bleak import BleakScanner, BleakClient
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False
    print("ERRO: Instale bleak com: pip install bleak")

app = Flask(__name__)
CORS(app)

# Configurações BLE - DEVEM COINCIDIR COM O PICO
SERVICE_UUID = "00001800-0000-1000-8000-00805f9b34fb"  # Generic Access Service
EVENTS_CHAR_UUID = "00002a00-0000-1000-8000-00805f9b34fb"  # Device Name
RESPONSE_CHAR_UUID = "00002a01-0000-1000-8000-00805f9b34fb"  # Appearance

# Estado global
ble_client = None
ble_connected = False
ble_device_info = None
discovered_devices = []
scanning = False
push_queue = []
response_buffer = ""

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_db():
    """Inicializa banco de dados"""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pico_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT 'Magic Mirror',
            ble_address TEXT,
            last_sync TEXT,
            status TEXT DEFAULT 'offline',
            events_count INTEGER DEFAULT 0,
            last_heartbeat TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado")

# FUNÇÕES BLE PUSH
async def scan_magic_mirrors():
    """Escaneia Magic Mirrors"""
    global discovered_devices, scanning
    
    if not BLE_AVAILABLE:
        return []
    
    scanning = True
    discovered_devices = []
    
    try:
        logger.info("Escaneando Magic Mirrors...")
        devices = await BleakScanner.discover(timeout=12.0)
        
        for device in devices:
            name = device.name or ""
            
            # Log todos os dispositivos para debug
            if name:
                logger.debug(f"Encontrado: '{name}' ({device.address})")
            
            # Filtra Magic Mirror
            if "MagicMirror" in name or "Magic" in name:
                discovered_devices.append({
                    'address': device.address,
                    'name': name,
                    'rssi': getattr(device, 'rssi', -50),
                    'type': 'BLE-Push'
                })
                logger.info(f"*** MAGIC MIRROR ENCONTRADO: {name} ({device.address}) ***")
        
        logger.info(f"Scan concluído - {len(discovered_devices)} Magic Mirrors encontrados")
        
    except Exception as e:
        logger.error(f"Erro no scan: {e}")
    finally:
        scanning = False
    
    return discovered_devices

async def connect_and_push(address, name):
    """Conecta ao Magic Mirror e configura push notifications"""
    global ble_client, ble_connected, ble_device_info, response_buffer
    
    try:
        logger.info(f"Conectando a {name} ({address})")
        
        # Desconecta anterior
        if ble_client:
            try:
                await ble_client.disconnect()
            except:
                pass
        
        # Nova conexão
        ble_client = BleakClient(address)
        await ble_client.connect(timeout=30)
        
        if ble_client.is_connected:
            ble_connected = True
            ble_device_info = {'address': address, 'name': name}
            response_buffer = ""
            
            logger.info(f"✅ CONECTADO A {name} - PUSH ATIVO")
            
            # Registra dispositivo
            register_device(address, name)
            
            # Configura notificações de resposta
            await setup_response_notifications()
            
            # Envia ping inicial
            await push_message({"action": "ping"})
            
            # Sincroniza eventos de hoje
            await push_today_events()
            
            return True
        else:
            logger.error(f"❌ Falha na conexão com {name}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erro ao conectar: {e}")
        ble_connected = False
        return False

async def setup_response_notifications():
    """Configura recebimento de respostas do Pico"""
    try:
        await ble_client.start_notify(RESPONSE_CHAR_UUID, handle_response_notification)
        logger.info("Notificações de resposta configuradas")
    except Exception as e:
        logger.error(f"Erro nas notificações: {e}")

async def handle_response_notification(sender, data):
    """Processa respostas do Pico"""
    global response_buffer
    
    try:
        chunk = data.decode('utf-8')
        response_buffer += chunk
        
        # Processa respostas completas
        while '\n' in response_buffer:
            line, response_buffer = response_buffer.split('\n', 1)
            if line.strip():
                await process_pico_response(line.strip())
                
    except Exception as e:
        logger.error(f"Erro na resposta: {e}")

async def process_pico_response(response_str):
    """Processa resposta JSON do Pico"""
    try:
        response = json.loads(response_str)
        action = response.get("action", "")
        
        logger.info(f"Resposta do Pico: {action}")
        
        if action == "sync_complete":
            events_count = response.get("data", 0)
            logger.info(f"Sincronização confirmada: {events_count} eventos")
            mark_events_synced()
            
        elif action == "event_added":
            event_id = response.get("data")
            logger.info(f"Evento adicionado confirmado: ID {event_id}")
            mark_event_synced(event_id)
            
        elif action == "event_removed":
            event_id = response.get("data")
            logger.info(f"Evento removido confirmado: ID {event_id}")
            
        elif action == "all_events_removed":
            logger.info("Limpeza de eventos confirmada")
            
        elif action == "pong":
            logger.info("Pong recebido - conexão ativa")
            
    except Exception as e:
        logger.error(f"Erro ao processar resposta: {e}")

async def push_message(data):
    """Envia mensagem via push notification para o Pico"""
    if not ble_client or not ble_client.is_connected:
        logger.warning("Tentativa de push sem conexão")
        return False
    
    try:
        message = json.dumps(data) + "\n"
        
        # Envia em chunks de 20 bytes via característica de eventos
        for i in range(0, len(message), 20):
            chunk = message[i:i+20]
            await ble_client.write_gatt_char(EVENTS_CHAR_UUID, chunk.encode('utf-8'))
            await asyncio.sleep(0.01)  # Delay pequeno entre chunks
        
        logger.debug(f"PUSH enviado: {data.get('action', 'unknown')}")
        return True
        
    except Exception as e:
        logger.error(f"Erro no PUSH: {e}")
        return False

async def push_today_events():
    """Push dos eventos de hoje para o Pico"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, hora, data FROM eventos WHERE data = ? ORDER BY hora", (hoje,))
        eventos = cursor.fetchall()
        conn.close()
        
        events_list = [
            {"id": eid, "nome": nome, "hora": hora, "data": data}
            for eid, nome, hora, data in eventos
        ]
        
        push_data = {
            "action": "sync_events",
            "events": events_list,
            "filter_date": hoje,
            "sync_time": datetime.now().isoformat()
        }
        
        success = await push_message(push_data)
        
        if success:
            logger.info(f"PUSH enviado: {len(events_list)} eventos de hoje")
        else:
            logger.error("Falha no PUSH de eventos")
        
        return success
        
    except Exception as e:
        logger.error(f"Erro no push de eventos: {e}")
        return False

def register_device(address, name):
    """Registra dispositivo no banco"""
    try:
        device_id = address.replace(':', '').replace('-', '')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pico_devices 
            (device_id, name, ble_address, status, last_heartbeat) 
            VALUES (?, ?, ?, ?, ?)
        ''', (device_id, name, address, 'online', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        logger.info(f"Dispositivo registrado: {name}")
        
    except Exception as e:
        logger.error(f"Erro ao registrar: {e}")

def mark_events_synced():
    """Marca eventos de hoje como sincronizados"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE data = ?", (hoje,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao marcar sync: {e}")

def mark_event_synced(event_id):
    """Marca evento específico como sincronizado"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao marcar evento sync: {e}")

# WRAPPERS SÍNCRONOS
def run_async_scan():
    """Wrapper síncrono para scan"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(scan_magic_mirrors())
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Erro no wrapper scan: {e}")
        return []

def run_async_connect(address, name):
    """Wrapper síncrono para conexão"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(connect_and_push(address, name))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Erro no wrapper connect: {e}")
        return False

def run_async_push(data):
    """Wrapper síncrono para push"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(push_message(data))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Erro no wrapper push: {e}")
        return False

# INICIALIZAÇÃO
init_db()

# ROTAS HTTP
@app.route('/')
def home():
    """Página principal"""
    for path in ['.', 'templates', 'static']:
        index_path = os.path.join(path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(path, 'index.html')
    
    return '''
    <h1>Magic Mirror - BLE Push Server</h1>
    <p>Status: ''' + ("Conectado" if ble_connected else "Desconectado") + '''</p>
    <p>Dispositivo: ''' + (ble_device_info['name'] if ble_device_info else "Nenhum") + '''</p>
    '''

@app.route('/api/eventos', methods=['POST'])
def add_event():
    """Adiciona evento e faz push para Pico"""
    data = request.json
    nome = data.get('nome')
    data_evento = data.get('data')
    hora_evento = data.get('hora')
    
    if not all([nome, data_evento, hora_evento]):
        return jsonify({"erro": "Campos obrigatórios"}), 400
    
    try:
        # Adiciona no banco
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO eventos (nome, data, hora, criado_em, sincronizado) VALUES (?, ?, ?, ?, ?)",
            (nome, data_evento, hora_evento, datetime.now().isoformat(), 0)
        )
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Evento criado: {nome} ({data_evento} {hora_evento})")
        
        # Push para Pico se for evento de hoje e estiver conectado
        hoje = datetime.now().strftime('%Y-%m-%d')
        if data_evento == hoje and ble_connected:
            def push_event():
                push_data = {
                    "action": "add_event",
                    "event": {
                        "id": event_id,
                        "nome": nome,
                        "hora": hora_evento,
                        "data": data_evento
                    }
                }
                
                success = run_async_push(push_data)
                if success:
                    logger.info(f"PUSH enviado: evento {event_id}")
                else:
                    logger.error(f"Falha no PUSH: evento {event_id}")
            
            threading.Thread(target=push_event, daemon=True).start()
        
        return jsonify({'mensagem': 'Evento criado!', 'id': event_id}), 201
        
    except Exception as e:
        logger.error(f"Erro ao criar evento: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos-hoje')
def get_today_events():
    """Lista eventos de hoje"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, hora, sincronizado FROM eventos WHERE data = ? ORDER BY hora", (hoje,))
        eventos = cursor.fetchall()
        conn.close()
        
        return jsonify([
            {'id': id, 'nome': nome, 'hora': hora, 'sincronizado': bool(sync)}
            for id, nome, hora, sync in eventos
        ])
        
    except Exception as e:
        logger.error(f"Erro ao listar eventos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Deleta evento e faz push para Pico"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
        rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows > 0:
            logger.info(f"Evento {event_id} deletado")
            
            # Push remoção para Pico
            if ble_connected:
                def push_remove():
                    push_data = {"action": "remove_event", "event_id": event_id}
                    run_async_push(push_data)
                
                threading.Thread(target=push_remove, daemon=True).start()
            
            return jsonify({'mensagem': 'Evento deletado'}), 200
        else:
            return jsonify({"erro": "Evento não encontrado"}), 404
            
    except Exception as e:
        logger.error(f"Erro ao deletar evento: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos', methods=['DELETE'])
def delete_all_events():
    """Deleta todos os eventos e faz push para Pico"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos")
        rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows > 0:
            logger.info(f"{rows} eventos deletados")
            
            # Push limpeza para Pico
            if ble_connected:
                def push_clear():
                    push_data = {"action": "remove_all_events"}
                    run_async_push(push_data)
                
                threading.Thread(target=push_clear, daemon=True).start()
            
            return jsonify({'mensagem': f'{rows} eventos deletados'}), 200
        else:
            return jsonify({'mensagem': 'Nenhum evento para deletar'}), 200
            
    except Exception as e:
        logger.error(f"Erro ao deletar eventos: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/sistema/info')
def system_info():
    """Informações do sistema"""
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM eventos WHERE data = ?", (hoje,))
        eventos_hoje = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM eventos")
        total_eventos = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM pico_devices")
        total_devices = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'eventos_hoje': eventos_hoje,
            'total_eventos': total_eventos,
            'total_dispositivos': total_devices,
            'bluetooth_conectado': ble_connected,
            'bluetooth_disponivel': BLE_AVAILABLE,
            'dispositivo_conectado': ble_device_info['name'] if ble_device_info else None,
            'protocolo': 'BLE Push Notifications',
            'versao': '2.0-BLE-Push',
            'modo': 'PUSH',
            'data_atual': hoje
        }), 200
        
    except Exception as e:
        logger.error(f"Erro info sistema: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/bluetooth/scan', methods=['POST'])
def start_scan():
    """Inicia scan BLE"""
    if not BLE_AVAILABLE:
        return jsonify({"erro": "BLE não disponível"}), 400
    
    def scan_thread():
        run_async_scan()
    
    threading.Thread(target=scan_thread, daemon=True).start()
    return jsonify({'mensagem': 'Scan BLE iniciado'}), 200

@app.route('/api/bluetooth/devices')
def list_devices():
    """Lista dispositivos descobertos"""
    return jsonify(discovered_devices)

@app.route('/api/bluetooth/connect', methods=['POST'])
def connect_device():
    """Conecta ao Magic Mirror"""
    if not BLE_AVAILABLE:
        return jsonify({"erro": "BLE não disponível"}), 400
    
    data = request.json
    address = data.get('address')
    name = data.get('name')
    
    if not address:
        return jsonify({"erro": "Endereço obrigatório"}), 400
    
    def connect_thread():
        success = run_async_connect(address, name)
        if success:
            logger.info(f"Conexão PUSH estabelecida com {name}")
        else:
            logger.error(f"Falha na conexão PUSH com {name}")
    
    threading.Thread(target=connect_thread, daemon=True).start()
    return jsonify({'mensagem': f'Conectando via PUSH a {name}...'}), 200

@app.route('/api/bluetooth/status')
def bluetooth_status():
    """Status da conexão BLE"""
    return jsonify({
        'connected': ble_connected,
        'device': ble_device_info,
        'scanning': scanning,
        'ble_available': BLE_AVAILABLE,
        'push_enabled': ble_connected,
        'connection_type': 'BLE Push Notifications'
    }), 200

@app.route('/api/bluetooth/disconnect', methods=['POST'])
def disconnect_device():
    """Desconecta dispositivo BLE"""
    global ble_client, ble_connected, ble_device_info
    
    try:
        if ble_client:
            def disconnect_thread():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(ble_client.disconnect())
                    loop.close()
                except:
                    pass
            
            threading.Thread(target=disconnect_thread, daemon=True).start()
        
        device_name = ble_device_info['name'] if ble_device_info else 'dispositivo'
        
        ble_connected = False
        ble_device_info = None
        
        return jsonify({'mensagem': f'Desconectado de {device_name}'}), 200
        
    except Exception as e:
        logger.error(f"Erro ao desconectar: {e}")
        return jsonify({"erro": "Erro na desconexão"}), 500

@app.route('/api/sincronizar', methods=['POST'])
def manual_sync():
    """Sincronização manual via push"""
    if not ble_connected:
        return jsonify({"erro": "Dispositivo não conectado"}), 400
    
    def sync_thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(push_today_events())
            loop.close()
        except Exception as e:
            logger.error(f"Erro sync manual: {e}")
    
    threading.Thread(target=sync_thread, daemon=True).start()
    
    return jsonify({
        'mensagem': f'Sincronização PUSH iniciada para {ble_device_info.get("name", "dispositivo")}',
        'dispositivos_sincronizados': 1
    }), 200

@app.route('/api/bluetooth/push/test', methods=['POST'])
def test_push():
    """Testa push notification"""
    if not ble_connected:
        return jsonify({"erro": "Dispositivo não conectado"}), 400
    
    def test_thread():
        test_data = {
            "action": "ping",
            "test": True,
            "timestamp": time.time()
        }
        success = run_async_push(test_data)
        logger.info(f"Teste de PUSH: {'Sucesso' if success else 'Falha'}")
    
    threading.Thread(target=test_thread, daemon=True).start()
    return jsonify({'mensagem': 'Teste de PUSH enviado'}), 200

if __name__ == '__main__':
    print("=" * 60)
    print("MAGIC MIRROR - SERVIDOR BLE PUSH")
    print("=" * 60)
    print(f"BLE disponível: {BLE_AVAILABLE}")
    if BLE_AVAILABLE:
        print("Modo: Cliente BLE com Push Notifications")
        print("Funcionamento: Servidor conecta ao Pico e empurra dados")
        print(f"Serviço UUID: {SERVICE_UUID}")
        print(f"Eventos UUID: {EVENTS_CHAR_UUID}")
        print(f"Resposta UUID: {RESPONSE_CHAR_UUID}")
    else:
        print("ERRO: Instale bleak com: pip install bleak")
    print("=" * 60)
    print("Servidor HTTP: http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)