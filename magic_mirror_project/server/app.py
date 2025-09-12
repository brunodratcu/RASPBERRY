#!/usr/bin/env python3
"""
Magic Mirror - Backend com MQTT Público
Usando test.mosquitto.org - Zero configuração de IP
"""

import sqlite3
import secrets
import json
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, session, redirect, render_template_string
import requests
import msal
import paho.mqtt.client as mqtt
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
CORS(app)

# Configurações - MQTT Público
MQTT_BROKER = "test.mosquitto.org"  # Broker público - sem IP!
MQTT_PORT = 1883
TOPIC_PREFIX = f"magic_mirror_{secrets.token_urlsafe(8)}"  # Único por instância

GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
GRAPH_SCOPES = ['https://graph.microsoft.com/Calendars.Read']

# ==================== BANCO ====================
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
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('mirror.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== OUTLOOK ====================
def get_msal_app():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    if not config:
        return None
    
    return msal.ConfidentialClientApplication(
        config['client_id'],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
        client_credential=config['client_secret']
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
            return events
    except Exception as e:
        print(f"Erro ao buscar eventos: {e}")
    
    return []

# ==================== MQTT ====================
class MQTTManager:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.connect()
    
    def connect(self):
        try:
            print(f"Conectando MQTT público: {MQTT_BROKER}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Erro MQTT: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(f"{TOPIC_PREFIX}/registration")
            print(f"MQTT conectado - Tópico: {TOPIC_PREFIX}")
        else:
            print(f"Erro MQTT: código {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if msg.topic == f"{TOPIC_PREFIX}/registration":
                self.handle_registration(payload)
        except Exception as e:
            print(f"Erro MQTT: {e}")
    
    def handle_registration(self, payload):
        reg_id = payload.get('registration_id')
        if not reg_id:
            return
        
        conn = get_db()
        device = conn.execute('SELECT * FROM devices WHERE registration_id = ?', (reg_id,)).fetchone()
        
        if device and device['status'] == 'approved':
            response = {
                'registration_id': reg_id,
                'status': 'approved',
                'device_id': device['device_id'],
                'topic_prefix': TOPIC_PREFIX
            }
            self.client.publish(f"{TOPIC_PREFIX}/registration", json.dumps(response))
            self.sync_device(device['device_id'])
        else:
            if not device:
                conn.execute('INSERT OR IGNORE INTO devices (registration_id) VALUES (?)', (reg_id,))
                conn.commit()
            response = {
                'registration_id': reg_id, 
                'status': 'pending',
                'topic_prefix': TOPIC_PREFIX
            }
            self.client.publish(f"{TOPIC_PREFIX}/registration", json.dumps(response))
        
        conn.close()
    
    def sync_device(self, device_id):
        if not self.connected:
            return
        
        events = get_today_events()
        events_data = {
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'events': events,
            'count': len(events)
        }
        
        self.client.publish(f"{TOPIC_PREFIX}/devices/{device_id}/events", json.dumps(events_data))
        print(f"Eventos enviados para {device_id}: {len(events)}")

mqtt_manager = MQTTManager()

# ==================== FRONTEND HTML ====================
FRONTEND_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Magic Mirror - MQTT Público</title>
    <style>
        body { font-family: Arial; margin: 40px; background: #f5f5f5; }
        .card { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; }
        .btn:hover { background: #0056b3; }
        .btn-success { background: #28a745; }
        .btn-danger { background: #dc3545; }
        .device { padding: 15px; border-left: 4px solid #007bff; background: #f8f9fa; margin: 10px 0; }
        .pending { border-color: #ffc107; }
        .approved { border-color: #28a745; }
        .config-box { background: #e9ecef; padding: 15px; border-radius: 4px; font-family: monospace; font-size: 14px; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Magic Mirror - MQTT Público</h1>
    
    <div class="card">
        <h3>📋 Configuração do Pico 2W</h3>
        <p>Use esta configuração no seu arquivo <strong>config.py</strong>:</p>
        <div class="config-box">
MQTT_BROKER = "test.mosquitto.org"<br>
TOPIC_PREFIX = "<span id="topicPrefix">{{TOPIC_PREFIX}}</span>"<br>
REGISTRATION_ID = "SEU_ID_UNICO"  # Altere aqui
        </div>
        <button class="btn" onclick="copyConfig()">📋 Copiar Configuração</button>
    </div>
    
    <div class="card">
        <h3>🔐 Azure AD</h3>
        <div class="form-group">
            <label>Client ID</label>
            <input type="text" id="clientId" placeholder="Client ID do Azure">
        </div>
        <div class="form-group">
            <label>Tenant ID</label>
            <input type="text" id="tenantId" placeholder="Tenant ID do Azure">
        </div>
        <div class="form-group">
            <label>Client Secret</label>
            <input type="password" id="clientSecret" placeholder="Client Secret do Azure">
        </div>
        <button class="btn" onclick="saveConfig()">💾 Salvar</button>
        <button class="btn" onclick="authenticate()">🔑 Autenticar</button>
        <button class="btn" onclick="testEvents()">📋 Testar Eventos</button>
    </div>
    
    <div class="card">
        <h3>📱 Dispositivos</h3>
        <button class="btn" onclick="loadDevices()">🔄 Atualizar</button>
        <div id="devices"></div>
    </div>
    
    <div class="card">
        <h3>📊 Status</h3>
        <div id="status">Carregando...</div>
    </div>

    <script>
        // Definir o tópico prefix no JavaScript
        document.getElementById('topicPrefix').textContent = '{{TOPIC_PREFIX}}';
        
        function copyConfig() {
            const config = `MQTT_BROKER = "test.mosquitto.org"
TOPIC_PREFIX = "{{TOPIC_PREFIX}}"
REGISTRATION_ID = "SEU_ID_UNICO"  # Altere aqui`;
            
            navigator.clipboard.writeText(config).then(() => {
                alert('Configuração copiada! Cole no arquivo config.py do Pico 2W');
            });
        }

        async function saveConfig() {
            const config = {
                clientId: document.getElementById('clientId').value,
                tenantId: document.getElementById('tenantId').value,
                clientSecret: document.getElementById('clientSecret').value,
                topicPrefix: '{{TOPIC_PREFIX}}'
            };
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            if (response.ok) {
                alert('Configuração salva!');
            }
        }

        function authenticate() {
            window.open('/api/auth', 'auth', 'width=600,height=700');
        }

        async function testEvents() {
            const response = await fetch('/api/events');
            const events = await response.json();
            alert(`Eventos encontrados: ${events.length}`);
        }

        async function loadDevices() {
            const response = await fetch('/api/devices');
            const devices = await response.json();
            
            const html = devices.map(d => `
                <div class="device ${d.status}">
                    <strong>${d.registration_id}</strong> - ${d.status}
                    ${d.status === 'pending' ? 
                        `<button class="btn btn-success" onclick="approve('${d.registration_id}')">✅ Aprovar</button>` : 
                        `<button class="btn" onclick="sync('${d.device_id}')">🔄 Sincronizar</button>`
                    }
                </div>
            `).join('');
            
            document.getElementById('devices').innerHTML = html || '<p>Nenhum dispositivo encontrado</p>';
        }

        async function approve(regId) {
            await fetch(`/api/devices/${regId}/approve`, { method: 'POST' });
            loadDevices();
        }

        async function sync(deviceId) {
            await fetch(`/api/sync/${deviceId}`, { method: 'POST' });
            alert('Sincronização iniciada');
        }

        async function updateStatus() {
            const response = await fetch('/api/status');
            const status = await response.json();
            document.getElementById('status').innerHTML = `
                Servidor: ${status.online ? '✅ Online' : '❌ Offline'}<br>
                MQTT Público: ${status.mqtt ? '✅ Conectado' : '❌ Desconectado'}<br>
                Tópico: ${status.topic_prefix || 'Não definido'}
            `;
        }

        setInterval(updateStatus, 10000);
        updateStatus();
        loadDevices();
    </script>
</body>
</html>
'''.replace('{{TOPIC_PREFIX}}', TOPIC_PREFIX)

# ==================== ROTAS ====================
@app.route('/')
def index():
    return render_template_string(FRONTEND_HTML)

@app.route('/api/config', methods=['POST'])
def save_config():
    config = request.get_json()
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO config (id, topic_prefix, client_id, tenant_id, client_secret)
        VALUES (1, ?, ?, ?, ?)
    ''', (config.get('topicPrefix', TOPIC_PREFIX), config['clientId'], config['tenantId'], config['clientSecret']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/auth')
def auth():
    app_msal = get_msal_app()
    if not app_msal:
        return 'Configure credenciais primeiro', 400
    
    state = secrets.token_urlsafe(16)
    session['state'] = state
    
    auth_url = app_msal.get_authorization_request_url(
        GRAPH_SCOPES,
        state=state,
        redirect_uri='http://localhost:5000/callback'
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if session.get('state') != state:
        return 'Estado inválido', 400
    
    app_msal = get_msal_app()
    result = app_msal.acquire_token_by_authorization_code(
        code,
        scopes=GRAPH_SCOPES,
        redirect_uri='http://localhost:5000/callback'
    )
    
    if "access_token" in result:
        conn = get_db()
        conn.execute('''
            UPDATE config SET access_token = ?, refresh_token = ?, expires_at = ?
            WHERE id = 1
        ''', (result['access_token'], result.get('refresh_token'), 
              (datetime.now() + timedelta(seconds=result.get('expires_in', 3600))).isoformat()))
        conn.commit()
        conn.close()
        return '<h2>✅ Autenticação concluída!</h2><script>window.close();</script>'
    
    return f'Erro: {result.get("error_description")}', 400

@app.route('/api/events')
def events():
    return jsonify(get_today_events())

@app.route('/api/devices')
def devices():
    conn = get_db()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    conn.close()
    return jsonify([dict(d) for d in devices])

@app.route('/api/devices/<registration_id>/approve', methods=['POST'])
def approve_device(registration_id):
    device_id = f"mirror_{secrets.token_urlsafe(6)}"
    conn = get_db()
    conn.execute('UPDATE devices SET device_id = ?, status = ? WHERE registration_id = ?', 
                (device_id, 'approved', registration_id))
    conn.commit()
    conn.close()
    
    response = {
        'registration_id': registration_id, 
        'status': 'approved', 
        'device_id': device_id,
        'topic_prefix': TOPIC_PREFIX
    }
    mqtt_manager.client.publish(f"{TOPIC_PREFIX}/registration", json.dumps(response))
    mqtt_manager.sync_device(device_id)
    
    return jsonify({'success': True})

@app.route('/api/sync/<device_id>', methods=['POST'])
def sync_device(device_id):
    mqtt_manager.sync_device(device_id)
    return jsonify({'success': True})

@app.route('/api/status')
def status():
    return jsonify({
        'online': True, 
        'mqtt': mqtt_manager.connected,
        'topic_prefix': TOPIC_PREFIX
    })

def auto_sync():
    while True:
        time.sleep(1800)  # 30 minutos
        try:
            conn = get_db()
            devices = conn.execute('SELECT device_id FROM devices WHERE status = "approved"').fetchall()
            conn.close()
            for device in devices:
                mqtt_manager.sync_device(device['device_id'])
        except:
            pass

threading.Thread(target=auto_sync, daemon=True).start()

if __name__ == '__main__':
    print("=" * 50)
    print("Magic Mirror Backend - MQTT Público")
    print("=" * 50)
    print("✅ Sem necessidade de configurar IP!")
    print(f"📡 MQTT: {MQTT_BROKER} (público)")
    print(f"🏷️ Tópico: {TOPIC_PREFIX}")
    print("🌐 Acesse: http://localhost:5000")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)