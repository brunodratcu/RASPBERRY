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

# UUIDs CUSTOMIZADOS - DEVEM COINCIDIR COM O PICO (versão string)
SERVICE_UUID = "12345678-1234-5678-9abc-123456789abc"
EVENTS_CHAR_UUID = "12345678-1234-5678-9abc-123456789abd"  # Para receber dados
RESPONSE_CHAR_UUID = "12345678-1234-5678-9abc-123456789abe"  # Para enviar dados

# Estado global
ble_client = None
ble_connected = False
ble_device_info = None
discovered_devices = []
scanning = False
push_queue = []
message_buffer = ""

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
        devices = await BleakScanner.discover(timeout=15.0)
        
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
    """Conecta ao Magic Mirror e configura comunicação"""
    global ble_client, ble_connected, ble_device_info, message_buffer
    
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
            message_buffer = ""
            
            logger.info(f"✅ CONECTADO A {name} - PUSH ATIVO")
            
            # Registra dispositivo
            register_device(address, name)
            
            # Aguarda um pouco para estabilizar
            await asyncio.sleep(2)
            
            # Testa comunicação básica
            success = await send_message_to_pico({"action": "ping", "timestamp": time.time()})
            
            if success:
                logger.info(f"🏓 Ping enviado com sucesso")
                
                # Aguarda resposta do ping
                await asyncio.sleep(2)
                
                # Sincroniza eventos de hoje
                await sync_today_events()
            else:
                logger.warning(f"⚠️ Falha no ping inicial")
            
            return True
        else:
            logger.error(f"❌ Falha na conexão com {name}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erro ao conectar: {e}")
        ble_connected = False
        return False

async def setup_notifications():
    """Configura notificações se disponível (versão compatível)"""
    try:
        # Tenta configurar notificações de forma simples
        logger.info("⚠️  Notificações não configuradas - modo direto")
        return True
        
    except Exception as e:
        logger.error(f"Erro nas notificações: {e}")
        return False

async def handle_notification(sender, data):
    """Processa notificações do Pico"""
    global message_buffer
    
    try:
        chunk = data.decode('utf-8')
        message_buffer += chunk
        
        # Processa mensagens completas (terminadas com \n)
        while '\n' in message_buffer:
            line, message_buffer = message_buffer.split('\n', 1)
            if line.strip():
                await process_pico_response(line.strip())
                
    except Exception as e:
        logger.error(f"Erro na notificação: {e}")

async def process_pico_response(response_str):
    """Processa resposta JSON do Pico"""
    try:
        response = json.loads(response_str)
        action = response.get("action", "")
        
        logger.info(f"📨 Resposta do Pico: {action}")
        
        if action == "pong":
            logger.info("🏓 Pong recebido - conexão ativa")
            
        elif action == "events_received":
            count = response.get("count", 0)
            logger.info(f"✅ Pico recebeu {count} eventos")
            mark_events_synced()
            
        elif action == "event_displayed":
            event_name = response.get("event_name", "")
            logger.info(f"📺 Evento sendo exibido: {event_name}")
            
        elif action == "status":
            status = response.get("data", {})
            logger.info(f"📊 Status do Pico: {status}")
            
    except json.JSONDecodeError as e:
        logger.warning(f"JSON inválido recebido: {response_str}")
    except Exception as e:
        logger.error(f"Erro ao processar resposta: {e}")

async def send_message_to_pico(data):
    """Envia mensagem para o Pico via característica de escrita (versão compatível)"""
    if not ble_client or not ble_client.is_connected:
        logger.warning("⚠️  Tentativa de envio sem conexão")
        return False
    
    try:
        message = json.dumps(data, ensure_ascii=False) + "\n"
        message_bytes = message.encode('utf-8')
        
        logger.debug(f"📤 Enviando: {data.get('action', 'unknown')} ({len(message_bytes)} bytes)")
        
        # Tenta enviar diretamente para a característica de eventos
        try:
            # Envia em chunks de 20 bytes
            chunk_size = 20
            for i in range(0, len(message_bytes), chunk_size):
                chunk = message_bytes[i:i+chunk_size]
                await ble_client.write_gatt_char(EVENTS_CHAR_UUID, chunk, response=False)
                await asyncio.sleep(0.02)  # Delay entre chunks
            
            logger.debug(f"✅ Mensagem enviada com sucesso")
            return True
            
        except Exception as write_error:
            logger.error(f"❌ Erro específico no envio: {write_error}")
            
            # Tenta com UUID como string
            try:
                chunk_size = 20
                for i in range(0, len(message_bytes), chunk_size):
                    chunk = message_bytes[i:i+chunk_size]
                    await ble_client.write_gatt_char(str(EVENTS_CHAR_UUID), chunk, response=False)
                    await asyncio.sleep(0.02)
                
                logger.debug(f"✅ Mensagem enviada (UUID string)")
                return True
                
            except Exception as string_error:
                logger.error(f"❌ Erro com UUID string: {string_error}")
                return False
        
    except Exception as e:
        logger.error(f"❌ Erro no envio: {e}")
        return False

async def sync_today_events():
    """Sincroniza eventos de hoje para o Pico"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, hora, data FROM eventos WHERE data = ? ORDER BY hora", (hoje,))
        eventos = cursor.fetchall()
        conn.close()
        
        events_list = []
        for eid, nome, hora, data in eventos:
            events_list.append({
                "id": eid,
                "nome": nome,
                "hora": hora,
                "data": data
            })
        
        sync_data = {
            "action": "sync_events",
            "events": events_list,
            "date": hoje,
            "count": len(events_list),
            "timestamp": time.time()
        }
        
        success = await send_message_to_pico(sync_data)
        
        if success:
            logger.info(f"📅 SINCRONIZAÇÃO enviada: {len(events_list)} eventos de {hoje}")
        else:
            logger.error("❌ Falha na sincronização")
        
        return success
        
    except Exception as e:
        logger.error(f"Erro na sincronização: {e}")
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
        
        logger.info(f"📱 Dispositivo registrado: {name}")
        
    except Exception as e:
        logger.error(f"Erro ao registrar: {e}")

def mark_events_synced():
    """Marca eventos de hoje como sincronizados"""
    try:
        hoje = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE eventos SET sincronizado = 1 WHERE data = ?", (hoje,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"✅ {rows_affected} eventos marcados como sincronizados")
        
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
    """Wrapper síncrono para envio"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_message_to_pico(data))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Erro no wrapper push: {e}")
        return False

def run_async_sync():
    """Wrapper síncrono para sincronização"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(sync_today_events())
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Erro no wrapper sync: {e}")
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
    
    return f'''
    <h1>Magic Mirror - BLE Push Server</h1>
    <p>Status: {"✅ Conectado" if ble_connected else "❌ Desconectado"}</p>
    <p>Dispositivo: {ble_device_info['name'] if ble_device_info else "Nenhum"}</p>
    <p>BLE Disponível: {"✅ Sim" if BLE_AVAILABLE else "❌ Não"}</p>
    '''

@app.route('/api/eventos', methods=['POST'])
def add_event():
    """Adiciona evento e sincroniza com Pico se conectado"""
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
        
        logger.info(f"📅 Evento criado: {nome} ({data_evento} {hora_evento})")
        
        # Se for evento de hoje e estiver conectado, sincroniza imediatamente
        hoje = datetime.now().strftime('%Y-%m-%d')
        if data_evento == hoje and ble_connected:
            def sync_new_event():
                success = run_async_sync()
                if success:
                    logger.info(f"🔄 Sincronização automática realizada")
                else:
                    logger.error(f"❌ Falha na sincronização automática")
            
            threading.Thread(target=sync_new_event, daemon=True).start()
        
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
    """Deleta evento e ressincroniza"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos WHERE id = ?", (event_id,))
        rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows > 0:
            logger.info(f"🗑️  Evento {event_id} deletado")
            
            # Ressincroniza se conectado
            if ble_connected:
                def resync_after_delete():
                    run_async_sync()
                
                threading.Thread(target=resync_after_delete, daemon=True).start()
            
            return jsonify({'mensagem': 'Evento deletado'}), 200
        else:
            return jsonify({"erro": "Evento não encontrado"}), 404
            
    except Exception as e:
        logger.error(f"Erro ao deletar evento: {e}")
        return jsonify({"erro": "Erro interno"}), 500

@app.route('/api/eventos', methods=['DELETE'])
def delete_all_events():
    """Deleta todos os eventos"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos")
        rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows > 0:
            logger.info(f"🗑️  {rows} eventos deletados")
            
            # Ressincroniza lista vazia se conectado
            if ble_connected:
                def resync_after_clear():
                    run_async_sync()
                
                threading.Thread(target=resync_after_clear, daemon=True).start()
            
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
            'versao': '2.1-BLE-Fixed',
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
    name = data.get('name', 'Magic Mirror')
    
    if not address:
        return jsonify({"erro": "Endereço obrigatório"}), 400
    
    def connect_thread():
        success = run_async_connect(address, name)
        if success:
            logger.info(f"✅ Conexão estabelecida com {name}")
        else:
            logger.error(f"❌ Falha na conexão com {name}")
    
    threading.Thread(target=connect_thread, daemon=True).start()
    return jsonify({'mensagem': f'Conectando a {name}...'}), 200

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
    """Sincronização manual"""
    if not ble_connected:
        return jsonify({"erro": "Dispositivo não conectado"}), 400
    
    def sync_thread():
        success = run_async_sync()
        if success:
            logger.info(f"🔄 Sincronização manual realizada")
        else:
            logger.error(f"❌ Falha na sincronização manual")
    
    threading.Thread(target=sync_thread, daemon=True).start()
    
    return jsonify({
        'mensagem': f'Sincronização iniciada para {ble_device_info.get("name", "dispositivo")}',
        'dispositivos_sincronizados': 1
    }), 200

@app.route('/api/bluetooth/test', methods=['POST'])
def test_connection():
    """Testa conexão com ping"""
    if not ble_connected:
        return jsonify({"erro": "Dispositivo não conectado"}), 400
    
    def test_thread():
        test_data = {
            "action": "ping",
            "timestamp": time.time(),
            "test": True
        }
        success = run_async_push(test_data)
        logger.info(f"🏓 Teste de conexão: {'✅ Sucesso' if success else '❌ Falha'}")
    
    threading.Thread(target=test_thread, daemon=True).start()
    return jsonify({'mensagem': 'Teste de conexão enviado'}), 200

if __name__ == '__main__':
    print("=" * 60)
    print("🪞 MAGIC MIRROR - SERVIDOR BLE PUSH (COMPATÍVEL)")
    print("=" * 60)
    print(f"🔵 BLE disponível: {'✅ Sim' if BLE_AVAILABLE else '❌ Não'}")
    if BLE_AVAILABLE:
        print("📡 Modo: Cliente BLE simplificado")
        print("🔄 Funcionamento: Servidor conecta ao Pico e envia dados")
        print(f"🆔 Serviço UUID: {SERVICE_UUID}")
        print(f"📤 Eventos UUID: {EVENTS_CHAR_UUID}")
        print(f"📥 Resposta UUID: {RESPONSE_CHAR_UUID}")
        print("⚠️  Versão compatível - sem get_services()")
    else:
        print("❌ ERRO: Instale bleak com: pip install bleak")
    print("=" * 60)
    print("🌐 Servidor HTTP: http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)