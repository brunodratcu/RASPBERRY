#!/usr/bin/env python3
"""
Magic Mirror - Backend CORRIGIDO
Sistema completo para sincronização de eventos do Outlook
CORREÇÃO: Topic único e sincronização garantida
"""

import sqlite3
import secrets
import json
import threading
import time
from datetime import datetime, timedelta
import os

from flask import Flask, request, jsonify, redirect, send_file
import requests
import msal
import paho.mqtt.client as mqtt
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = secrets.token_urlsafe(32)

app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)

CORS(app, supports_credentials=True)

# Configurações MQTT - TOPIC ÚNICO FIXO
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = "magic_mirror_stable"  # ÚNICO E FIXO

GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
GRAPH_SCOPES = ['https://graph.microsoft.com/Calendars.Read']

print(f"🔧 TOPIC PREFIX: {TOPIC_PREFIX}")

# ==================== BANCO DE DADOS ====================
def init_db():
    conn = sqlite3.connect('mirror.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY,
            topic_prefix TEXT,
            client_id TEXT,
            tenant_id TEXT,
            client_secret TEXT,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            registration_id TEXT PRIMARY KEY,
            device_id TEXT,
            status TEXT DEFAULT 'pending',
            device_info TEXT,
            mac_address TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('INSERT OR IGNORE INTO config (id, topic_prefix) VALUES (1, ?)', (TOPIC_PREFIX,))
    cursor.execute('UPDATE config SET topic_prefix = ? WHERE id = 1', (TOPIC_PREFIX,))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('mirror.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== MICROSOFT OUTLOOK ====================
def get_msal_app():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    if not config or not config['client_id']:
        return None
    
    return msal.PublicClientApplication(
        config['client_id'],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}"
    )

def get_valid_token():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    if not config or not config['access_token']:
        conn.close()
        return None
    
    if config['expires_at']:
        expires = datetime.fromisoformat(config['expires_at'])
        if datetime.now() >= expires - timedelta(minutes=5):
            if config['refresh_token']:
                app = get_msal_app()
                if app:
                    result = app.acquire_token_by_refresh_token(config['refresh_token'], scopes=GRAPH_SCOPES)
                    if "access_token" in result:
                        conn.execute('''UPDATE config SET access_token = ?, expires_at = ? WHERE id = 1''', 
                                   (result['access_token'], (datetime.now() + timedelta(seconds=result.get('expires_in', 3600))).isoformat()))
                        conn.commit()
                        conn.close()
                        return result['access_token']
            conn.close()
            return None
    
    token = config['access_token']
    conn.close()
    return token

def get_today_events():
    token = get_valid_token()
    if not token:
        print("⚠️  Token não disponível")
        return []
    
    today = datetime.now().date()
    start_time = datetime.combine(today, datetime.min.time()).isoformat() + 'Z'
    end_time = datetime.combine(today, datetime.max.time()).isoformat() + 'Z'
    
    url = f"{GRAPH_ENDPOINT}me/events"
    params = {
        '$filter': f"start/dateTime ge '{start_time}' and start/dateTime le '{end_time}'",
        '$select': 'subject,start,end,location,isAllDay',
        '$orderby': 'start/dateTime asc',
        '$top': 10
    }
    
    try:
        response = requests.get(url, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=10)
        if response.status_code == 200:
            events = []
            for event in response.json().get('value', []):
                start_dt = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                events.append({
                    'title': event.get('subject', 'Sem título'),
                    'time': start_dt.strftime('%H:%M') if not event.get('isAllDay') else '',
                    'isAllDay': event.get('isAllDay', False)
                })
            print(f"✅ {len(events)} eventos obtidos do Outlook")
            return events
        else:
            print(f"❌ Erro Graph API: {response.status_code}")
            if response.status_code == 401:
                print("   → Token expirado - reautentique no navegador")
            return []
    except Exception as e:
        print(f"❌ Erro ao buscar eventos: {e}")
    
    return []

# ==================== MQTT MANAGER ====================
class MQTTManager:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.topic_prefix = TOPIC_PREFIX
        self.connect()
    
    def connect(self):
        try:
            print(f"🔌 Conectando MQTT: {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ Erro MQTT: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            
            # Subscrever APENAS ao topic correto
            registration_topic = f"{self.topic_prefix}/registration"
            client.subscribe(registration_topic)
            
            print(f"✅ MQTT conectado")
            print(f"👂 Escutando: {registration_topic}")
        else:
            print(f"❌ Falha MQTT: código {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"🔌 MQTT desconectado: código {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            topic_str = msg.topic
            payload = json.loads(msg.payload.decode())
            
            # Processar apenas registration requests
            if 'registration' in topic_str:
                reg_id = payload.get('registration_id')
                status = payload.get('status', '')
                
                # Ignorar echos das próprias aprovações
                if status == 'approved' and 'device_id' in payload:
                    return
                
                # Processar solicitações do Pico
                if reg_id and status == 'requesting_approval':
                    print(f"\n📨 NOVA SOLICITAÇÃO: {reg_id}")
                    self.handle_registration(payload)
                    
        except Exception as e:
            print(f"❌ Erro MQTT: {e}")
    
    def handle_registration(self, payload):
        """Auto-aprovar dispositivo e enviar confirmação"""
        reg_id = payload.get('registration_id')
        device_info = payload.get('device_info', 'Dispositivo desconhecido')
        mac_address = payload.get('mac_address', '')
        
        if not reg_id:
            return
        
        conn = get_db()
        
        try:
            device = conn.execute('SELECT * FROM devices WHERE registration_id = ?', (reg_id,)).fetchone()
            
            if device and device['status'] == 'approved' and device['device_id']:
                # Dispositivo já aprovado - reenviar aprovação
                device_id = device['device_id']
                print(f"✓ Re-aprovando: {reg_id} → {device_id}")
                
                conn.execute('UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?', (reg_id,))
                conn.commit()
            else:
                # Novo dispositivo ou pendente - aprovar
                device_id = f"mirror_{secrets.token_urlsafe(6)}"
                
                if device:
                    conn.execute('''UPDATE devices SET device_id = ?, status = 'approved', 
                                    last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?''', 
                                (device_id, reg_id))
                else:
                    conn.execute('''INSERT INTO devices (registration_id, device_id, device_info, 
                                    mac_address, status) VALUES (?, ?, ?, ?, 'approved')''', 
                                (reg_id, device_id, device_info, mac_address))
                
                conn.commit()
                print(f"✅ APROVADO: {reg_id} → {device_id}")
            
            # Enviar aprovação
            response = {
                'registration_id': reg_id,
                'status': 'approved',
                'device_id': device_id,
                'topic_prefix': self.topic_prefix,
                'events_topic': f"{self.topic_prefix}/devices/{device_id}/events"
            }
            
            approval_topic = f"{self.topic_prefix}/registration"
            self.client.publish(approval_topic, json.dumps(response))
            print(f"📤 Aprovação enviada em: {approval_topic}")
            
            # Sincronizar eventos após 2 segundos
            threading.Thread(target=lambda: time.sleep(2) or self.sync_device(device_id), daemon=True).start()
            
        except Exception as e:
            print(f"❌ Erro no registro: {e}")
        finally:
            conn.close()
    
    def sync_device(self, device_id):
        """Sincronizar eventos com dispositivo"""
        if not self.connected:
            return False
        
        print(f"🔄 Sincronizando: {device_id}")
        
        events = get_today_events()
        events_sorted = sorted(events, key=lambda x: x.get('time', '23:59'))
        
        events_data = {
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'events': events_sorted,
            'count': len(events_sorted),
            'sync_time': datetime.now().isoformat(),
            'server_info': {
                'topic_prefix': self.topic_prefix,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'server_version': '3.0'
            }
        }
        
        topic = f"{self.topic_prefix}/devices/{device_id}/events"
        message = json.dumps(events_data, ensure_ascii=False)
        
        try:
            self.client.publish(topic, message)
            print(f"✅ Publicado em: {topic}")
            print(f"   {len(events_sorted)} eventos enviados")
            return True
        except Exception as e:
            print(f"❌ Erro ao publicar: {e}")
            return False
    
    def approve_device(self, registration_id):
        """Aprovar dispositivo manualmente"""
        device_id = f"mirror_{secrets.token_urlsafe(6)}"
        
        conn = get_db()
        conn.execute('''UPDATE devices SET device_id = ?, status = 'approved', 
                        last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?''', 
                    (device_id, registration_id))
        conn.commit()
        conn.close()
        
        response = {
            'registration_id': registration_id,
            'status': 'approved',
            'device_id': device_id,
            'topic_prefix': self.topic_prefix,
            'events_topic': f"{self.topic_prefix}/devices/{device_id}/events"
        }
        
        self.client.publish(f"{self.topic_prefix}/registration", json.dumps(response))
        threading.Thread(target=lambda: time.sleep(2) or self.sync_device(device_id), daemon=True).start()
        
        return device_id

mqtt_manager = MQTTManager()

# ==================== ROTAS WEB ====================
@app.route('/')
def index():
    possible_paths = ['index.html', './index.html', 'templates/index.html']
    
    for path in possible_paths:
        if os.path.exists(path):
            return send_file(path)
    
    return """
    <h1>Frontend não encontrado</h1>
    <p>Coloque o arquivo index.html na mesma pasta que app.py</p>
    <p><strong>Diretório atual:</strong> """ + os.getcwd() + """</p>
    """, 404

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/config', methods=['POST'])
def save_config():
    config = request.get_json()
    
    if not all(k in config for k in ['clientId', 'tenantId', 'clientSecret']):
        return jsonify({'error': 'Campos obrigatórios ausentes'}), 400
    
    conn = get_db()
    conn.execute('''UPDATE config SET client_id = ?, tenant_id = ?, client_secret = ? WHERE id = 1''',
                (config['clientId'], config['tenantId'], config['clientSecret']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    
    if config:
        return jsonify({
            'topic_prefix': config['topic_prefix'] or TOPIC_PREFIX,
            'client_id': config['client_id'],
            'tenant_id': config['tenant_id'],
            'has_credentials': bool(config['client_id'] and config['tenant_id'] and config['client_secret']),
            'has_token': bool(config['access_token'])
        })
    return jsonify({'topic_prefix': TOPIC_PREFIX, 'has_credentials': False, 'has_token': False})

@app.route('/api/status')
def status():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    devices_count = conn.execute('SELECT COUNT(*) as count FROM devices').fetchone()
    approved_count = conn.execute('SELECT COUNT(*) as count FROM devices WHERE status = "approved"').fetchone()
    conn.close()
    
    has_credentials = bool(config and config['client_id'] and config['tenant_id'] and config['client_secret'])
    has_token = bool(config and config['access_token'] and len(config['access_token']) > 10)
    
    return jsonify({
        'online': True,
        'mqtt': mqtt_manager.connected,
        'topic_prefix': TOPIC_PREFIX,
        'has_azure_config': has_credentials,
        'has_token': has_token,
        'devices_total': devices_count['count'] if devices_count else 0,
        'devices_approved': approved_count['count'] if approved_count else 0
    })

@app.route('/api/auth')
def auth():
    try:
        app_msal = get_msal_app()
        if not app_msal:
            return '<h2>Configure suas credenciais Azure primeiro</h2>', 400
        
        auth_url = app_msal.get_authorization_request_url(GRAPH_SCOPES, redirect_uri='http://localhost:5000/callback')
        return redirect(auth_url)
    except Exception as e:
        return f'<h2>Erro: {str(e)}</h2>', 500

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error or not code:
            return f'<h2>Erro: {error or "Código ausente"}</h2>'
        
        app_msal = get_msal_app()
        if not app_msal:
            return '<h2>Aplicação MSAL não configurada</h2>'
        
        result = app_msal.acquire_token_by_authorization_code(code, scopes=GRAPH_SCOPES, redirect_uri='http://localhost:5000/callback')
        
        if "access_token" in result:
            conn = get_db()
            conn.execute('''UPDATE config SET access_token = ?, refresh_token = ?, expires_at = ? WHERE id = 1''',
                        (result['access_token'], result.get('refresh_token'),
                         (datetime.now() + timedelta(seconds=result.get('expires_in', 3600))).isoformat()))
            conn.commit()
            conn.close()
            
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial; color: #2e7d32;">
                <h2>Autenticação Concluída!</h2>
                <p>Sistema pronto para sincronizar eventos do Outlook</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px; 
                       background: #2e7d32; color: white; border: none; border-radius: 5px;">Fechar</button>
            </div>
            '''
        else:
            return f'<h2>Falha: {result.get("error_description", "Erro desconhecido")}</h2>'
    except Exception as e:
        return f'<h2>Erro no callback: {str(e)}</h2>'

@app.route('/api/events')
def events():
    events_list = get_today_events()
    return jsonify({
        'events': events_list,
        'count': len(events_list),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/devices')
def devices():
    conn = get_db()
    devices = conn.execute('''SELECT registration_id, device_id, status, device_info, mac_address, 
                              first_seen, last_seen FROM devices ORDER BY first_seen DESC''').fetchall()
    conn.close()
    
    return jsonify([{
        'registration_id': d['registration_id'],
        'device_id': d['device_id'],
        'status': d['status'],
        'device_info': d['device_info'],
        'mac_address': d['mac_address'],
        'first_seen': d['first_seen'],
        'last_seen': d['last_seen']
    } for d in devices])

@app.route('/api/devices/<registration_id>/approve', methods=['POST'])
def approve_device_route(registration_id):
    try:
        device_id = mqtt_manager.approve_device(registration_id)
        return jsonify({'success': True, 'device_id': device_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sync/<device_id>', methods=['POST'])
def sync_device_route(device_id):
    try:
        success = mqtt_manager.sync_device(device_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clean-devices', methods=['POST'])
def clean_devices_route():
    try:
        conn = get_db()
        count = conn.execute('SELECT COUNT(*) as count FROM devices').fetchone()['count']
        conn.execute('DELETE FROM devices')
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'{count} dispositivos removidos'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== SINCRONIZAÇÃO AUTOMÁTICA ====================
def auto_sync():
    while True:
        time.sleep(3600)
        try:
            conn = get_db()
            devices = conn.execute('SELECT device_id FROM devices WHERE status = "approved"').fetchall()
            conn.close()
            
            for device in devices:
                mqtt_manager.sync_device(device['device_id'])
                time.sleep(2)
        except Exception as e:
            print(f"❌ Erro sync automático: {e}")

threading.Thread(target=auto_sync, daemon=True).start()

# ==================== INICIALIZAÇÃO ====================
if __name__ == '__main__':
    print("=" * 60)
    print("MAGIC MIRROR - BACKEND v3.0 CORRIGIDO")
    print("=" * 60)
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic: {TOPIC_PREFIX}")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nSistema interrompido")
    finally:
        if mqtt_manager.client:
            mqtt_manager.client.loop_stop()
            mqtt_manager.client.disconnect()