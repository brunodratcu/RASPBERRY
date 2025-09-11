#!/usr/bin/env python3
"""
Magic Mirror - Backend Simplificado FUNCIONANDO
Apenas o essencial: Azure AD + Outlook + MQTT
Versão 4.1 - Minimal Fixed
"""

import os
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

# Configurações
app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
CORS(app)

# Configurações MQTT
MQTT_BROKER = os.getenv('MQTT_BROKER', 'broker.hivemq.com')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC_BASE = 'espelho_magico'

# Configurações Azure
GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
GRAPH_SCOPES = ['https://graph.microsoft.com/Calendars.Read', 'https://graph.microsoft.com/User.Read']

# ==================== BANCO DE DADOS ====================
class Database:
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect('mirror_minimal.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                azure_client_id TEXT,
                azure_tenant_id TEXT,
                azure_client_secret TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expires DATETIME
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                registration_id TEXT PRIMARY KEY,
                device_id TEXT,
                user_id TEXT,
                display_name TEXT,
                status TEXT DEFAULT 'pending',
                api_key TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_conn(self):
        conn = sqlite3.connect('mirror_minimal.db')
        conn.row_factory = sqlite3.Row
        return conn

db = Database()

# ==================== OUTLOOK MANAGER ====================
class OutlookManager:
    def get_msal_app(self, azure_config):
        authority = f"https://login.microsoftonline.com/{azure_config['tenantId']}"
        return msal.ConfidentialClientApplication(
            azure_config['clientId'],
            authority=authority,
            client_credential=azure_config['clientSecret']
        )
    
    def get_auth_url(self, user_id, azure_config):
        app = self.get_msal_app(azure_config)
        state = secrets.token_urlsafe(16)
        session['oauth_state'] = state
        session['user_id'] = user_id
        
        return app.get_authorization_request_url(
            scopes=GRAPH_SCOPES,
            state=state,
            redirect_uri='http://localhost:5000/callback'
        )
    
    def handle_callback(self, code, state):
        if session.get('oauth_state') != state:
            return False, "Estado inválido"
        
        user_id = session.get('user_id')
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT azure_client_id, azure_tenant_id, azure_client_secret
            FROM users WHERE user_id = ?
        ''', (user_id,))
        config = cursor.fetchone()
        
        if not config:
            conn.close()
            return False, "Configuração não encontrada"
        
        azure_config = {
            'clientId': config['azure_client_id'],
            'tenantId': config['azure_tenant_id'],
            'clientSecret': config['azure_client_secret']
        }
        
        app = self.get_msal_app(azure_config)
        result = app.acquire_token_by_authorization_code(
            code,
            scopes=GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        if "access_token" in result:
            cursor.execute('''
                UPDATE users 
                SET access_token = ?, refresh_token = ?, token_expires = ?
                WHERE user_id = ?
            ''', (
                result['access_token'],
                result.get('refresh_token'),
                datetime.now() + timedelta(seconds=result.get('expires_in', 3600)),
                user_id
            ))
            conn.commit()
            conn.close()
            return True, "Autenticação concluída"
        
        conn.close()
        return False, result.get('error_description', 'Erro na autenticação')
    
    def get_valid_token(self, user_id):
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT access_token, refresh_token, token_expires, 
                   azure_client_id, azure_tenant_id, azure_client_secret
            FROM users WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result['access_token']:
            conn.close()
            return None
        
        if result['token_expires']:
            expires = datetime.fromisoformat(result['token_expires'])
            if datetime.now() >= expires - timedelta(minutes=5):
                if result['refresh_token']:
                    azure_config = {
                        'clientId': result['azure_client_id'],
                        'tenantId': result['azure_tenant_id'],
                        'clientSecret': result['azure_client_secret']
                    }
                    app = self.get_msal_app(azure_config)
                    refresh_result = app.acquire_token_by_refresh_token(
                        result['refresh_token'], scopes=GRAPH_SCOPES
                    )
                    
                    if "access_token" in refresh_result:
                        cursor.execute('''
                            UPDATE users 
                            SET access_token = ?, token_expires = ?
                            WHERE user_id = ?
                        ''', (
                            refresh_result['access_token'],
                            datetime.now() + timedelta(seconds=refresh_result.get('expires_in', 3600)),
                            user_id
                        ))
                        conn.commit()
                        conn.close()
                        return refresh_result['access_token']
                
                conn.close()
                return None
        
        token = result['access_token']
        conn.close()
        return token
    
    def get_today_events(self, user_id):
        token = self.get_valid_token(user_id)
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
            '$top': 20
        }
        
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                events = []
                
                for event in data.get('value', []):
                    start_dt = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                    
                    events.append({
                        'title': event.get('subject', 'Sem título'),
                        'time': start_dt.strftime('%H:%M') if not event.get('isAllDay') else '',
                        'location': event.get('location', {}).get('displayName', ''),
                        'isAllDay': event.get('isAllDay', False),
                        'source': 'outlook'
                    })
                
                return events
            return []
        except Exception as e:
            print(f"Erro ao buscar eventos: {e}")
            return []

outlook = OutlookManager()

# ==================== MQTT MANAGER ====================
class MQTTManager:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Erro MQTT: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(f"{MQTT_TOPIC_BASE}/registration")
            client.subscribe(f"{MQTT_TOPIC_BASE}/+/heartbeat")
            print(f"MQTT conectado ao {MQTT_BROKER}")
        else:
            print(f"Erro MQTT: {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            if topic.endswith('/registration'):
                self.handle_registration(payload)
            elif topic.endswith('/heartbeat'):
                device_id = topic.split('/')[1]
                self.sync_device(device_id)
        except Exception as e:
            print(f"Erro mensagem MQTT: {e}")
    
    def handle_registration(self, payload):
        registration_id = payload.get('registration_id')
        if not registration_id:
            return
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT device_id, status FROM devices WHERE registration_id = ?
        ''', (registration_id,))
        device = cursor.fetchone()
        
        if device and device['status'] == 'approved':
            cursor.execute('''
                SELECT device_id, api_key FROM devices WHERE registration_id = ?
            ''', (registration_id,))
            device_data = cursor.fetchone()
            
            if device_data:
                self.send_registration_response(
                    registration_id, 'approved', 
                    device_data['device_id'], device_data['api_key']
                )
                self.sync_device(device_data['device_id'])
        else:
            if not device:
                cursor.execute('''
                    INSERT INTO devices (registration_id, status)
                    VALUES (?, 'pending')
                ''', (registration_id,))
                conn.commit()
            
            self.send_registration_response(registration_id, 'pending')
        
        conn.close()
    
    def send_registration_response(self, registration_id, status, device_id=None, api_key=None):
        if not self.connected:
            return
        
        response = {
            'registration_id': registration_id,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        if device_id and api_key:
            response.update({'device_id': device_id, 'api_key': api_key})
        
        self.client.publish(f"{MQTT_TOPIC_BASE}/registration", json.dumps(response))
    
    def sync_device(self, device_id):
        if not self.connected:
            return
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id FROM devices WHERE device_id = ? AND status = 'approved'
        ''', (device_id,))
        device = cursor.fetchone()
        conn.close()
        
        if not device:
            return
        
        events = outlook.get_today_events(device['user_id'])
        
        events_data = {
            'status': 'success',
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'count': len(events),
            'events': events,
            'last_sync': datetime.now().isoformat(),
            'source': 'outlook'
        }
        
        topic = f"{MQTT_TOPIC_BASE}/{device_id}/events"
        self.client.publish(topic, json.dumps(events_data))
        print(f"Eventos enviados para {device_id}: {len(events)} eventos")

mqtt_manager = MQTTManager()

# ==================== FRONTEND HTML ====================
FRONTEND_HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Mirror - Portal</title>
    <style>
        :root {
            --primary: #0078d4;
            --success: #107c10;
            --warning: #ff8c00;
            --error: #d13438;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 40px; color: white; }
        .header h1 { font-size: 3em; margin-bottom: 10px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
        .card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; }
        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e1e5e9;
            border-radius: 8px;
            font-size: 16px;
        }
        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(0,120,212,0.1);
        }
        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .btn:hover { background: #106ebe; }
        .btn-success { background: var(--success); }
        .btn-warning { background: var(--warning); }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
        .device-card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; margin-bottom: 15px; }
        .status-pending { border-left: 4px solid var(--warning); }
        .status-approved { border-left: 4px solid var(--success); }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            display: none;
        }
        .notification.success { background: var(--success); }
        .notification.error { background: var(--error); }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🪞 Magic Mirror</h1>
            <p>Portal Simplificado - Azure AD + Outlook + MQTT</p>
        </div>

        <div class="grid">
            <!-- Configuração Azure -->
            <div class="card">
                <h3>🔐 Configuração Azure AD</h3>
                <p style="margin-bottom: 20px; color: #666;">Configure suas credenciais do Azure AD para acessar o Outlook.</p>
                
                <div class="form-group">
                    <label>Client ID</label>
                    <input type="text" id="clientId" placeholder="12345678-1234-1234-1234-123456789012">
                </div>
                <div class="form-group">
                    <label>Tenant ID</label>
                    <input type="text" id="tenantId" placeholder="87654321-4321-4321-4321-210987654321">
                </div>
                <div class="form-group">
                    <label>Client Secret</label>
                    <input type="password" id="clientSecret" placeholder="abc123~DEF456_ghi789.JKL012">
                </div>
                
                <button class="btn" onclick="saveAzureConfig()">💾 Salvar Configuração</button>
                <button class="btn btn-success" onclick="authenticateAzure()">🔑 Autenticar</button>
            </div>

            <!-- Dispositivos -->
            <div class="card">
                <h3>📱 Dispositivos</h3>
                <p style="margin-bottom: 20px; color: #666;">Gerencie seus dispositivos Magic Mirror.</p>
                
                <button class="btn" onclick="generateRegistration()">📋 Gerar Registration ID</button>
                <button class="btn btn-warning" onclick="loadDevices()">🔄 Atualizar Lista</button>
                
                <div id="registrationResult" style="margin: 20px 0;"></div>
                <div id="devicesList"></div>
            </div>
        </div>

        <!-- Status -->
        <div class="card">
            <h3>📊 Status do Sistema</h3>
            <div id="systemStatus">Carregando...</div>
        </div>
    </div>

    <div id="notification" class="notification"></div>

    <script>
        function showNotification(message, type = 'success') {
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.className = `notification ${type}`;
            notification.style.display = 'block';
            setTimeout(() => {
                notification.style.display = 'none';
            }, 4000);
        }

        async function apiCall(url, method = 'GET', data = null) {
            try {
                const options = {
                    method,
                    headers: {'Content-Type': 'application/json'}
                };
                if (data) options.body = JSON.stringify(data);
                
                const response = await fetch(url, options);
                return await response.json();
            } catch (error) {
                console.error('API Error:', error);
                showNotification('Erro na comunicação com o servidor', 'error');
                return null;
            }
        }

        async function saveAzureConfig() {
            const config = {
                clientId: document.getElementById('clientId').value,
                tenantId: document.getElementById('tenantId').value,
                clientSecret: document.getElementById('clientSecret').value
            };

            if (!config.clientId || !config.tenantId || !config.clientSecret) {
                showNotification('Preencha todos os campos', 'error');
                return;
            }

            const result = await apiCall('/api/azure/config', 'POST', config);
            if (result && result.success) {
                showNotification('Configuração salva com sucesso!');
            }
        }

        function authenticateAzure() {
            window.open('/api/azure/auth', '_blank', 'width=600,height=700');
        }

        async function generateRegistration() {
            const result = await apiCall('/api/devices/generate-registration');
            if (result) {
                document.getElementById('registrationResult').innerHTML = `
                    <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; border-left: 4px solid var(--primary);">
                        <h4>Registration ID Gerado:</h4>
                        <code style="background: #333; color: #0f0; padding: 10px; display: block; margin: 10px 0; border-radius: 4px;">${result.registration_id}</code>
                        <p><strong>Configure no Pico 2W:</strong><br>
                        REGISTRATION_ID = "${result.registration_id}"</p>
                    </div>
                `;
            }
        }

        async function loadDevices() {
            const result = await apiCall('/api/devices');
            const container = document.getElementById('devicesList');
            
            if (result && result.devices) {
                if (result.devices.length === 0) {
                    container.innerHTML = '<p style="color: #666;">Nenhum dispositivo registrado.</p>';
                    return;
                }

                container.innerHTML = result.devices.map(device => `
                    <div class="device-card status-${device.status}">
                        <h4>${device.display_name || device.registration_id}</h4>
                        <p><strong>Registration ID:</strong> ${device.registration_id}</p>
                        <p><strong>Status:</strong> ${device.status}</p>
                        ${device.device_id ? `<p><strong>Device ID:</strong> ${device.device_id}</p>` : ''}
                        ${device.status === 'pending' ? 
                            `<button class="btn btn-success" onclick="approveDevice('${device.registration_id}')">✅ Aprovar</button>` : 
                            `<button class="btn" onclick="syncDevice('${device.device_id}')">🔄 Sincronizar</button>`
                        }
                    </div>
                `).join('');
            }
        }

        async function approveDevice(registrationId) {
            const displayName = prompt('Nome do dispositivo:', `Mirror ${registrationId.slice(-8)}`);
            if (!displayName) return;

            const result = await apiCall(`/api/devices/${registrationId}/approve`, 'POST', {displayName});
            if (result && result.success) {
                showNotification('Dispositivo aprovado com sucesso!');
                loadDevices();
            }
        }

        async function syncDevice(deviceId) {
            const result = await apiCall(`/api/devices/${deviceId}/sync`, 'POST');
            if (result && result.success) {
                showNotification('Sincronização iniciada!');
            }
        }

        async function updateSystemStatus() {
            const result = await apiCall('/api/status');
            if (result) {
                document.getElementById('systemStatus').innerHTML = `
                    <p><strong>Status:</strong> ${result.status}</p>
                    <p><strong>Versão:</strong> ${result.version}</p>
                    <p><strong>MQTT:</strong> ${result.mqtt_connected ? '✅ Conectado' : '❌ Desconectado'}</p>
                `;
            }
        }

        document.addEventListener('DOMContentLoaded', function() {
            updateSystemStatus();
            loadDevices();
            setInterval(updateSystemStatus, 30000);
        });
    </script>
</body>
</html>
'''

# ==================== ROTAS ====================

@app.route('/')
def index():
    return render_template_string(FRONTEND_HTML)

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'online',
        'version': '4.1-minimal-fixed',
        'mqtt_connected': mqtt_manager.connected
    })

@app.route('/api/azure/config', methods=['POST'])
def save_azure_config():
    azure_config = request.get_json()
    user_id = session.get('user_id', str(secrets.token_urlsafe(8)))
    session['user_id'] = user_id
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, azure_client_id, azure_tenant_id, azure_client_secret)
        VALUES (?, ?, ?, ?)
    ''', (user_id, azure_config['clientId'], azure_config['tenantId'], azure_config['clientSecret']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'user_id': user_id})

@app.route('/api/azure/auth')
def azure_auth():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Configure credenciais primeiro'}), 400
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT azure_client_id, azure_tenant_id, azure_client_secret
        FROM users WHERE user_id = ?
    ''', (user_id,))
    config = cursor.fetchone()
    conn.close()
    
    if not config:
        return jsonify({'error': 'Configuração não encontrada'}), 400
    
    azure_config = {
        'clientId': config['azure_client_id'],
        'tenantId': config['azure_tenant_id'],
        'clientSecret': config['azure_client_secret']
    }
    
    auth_url = outlook.get_auth_url(user_id, azure_config)
    return redirect(auth_url)

@app.route('/callback')
def oauth_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code or not state:
        return 'Erro nos parâmetros OAuth', 400
    
    success, message = outlook.handle_callback(code, state)
    
    if success:
        return '<h2>Autenticação concluída!</h2><script>setTimeout(() => window.close(), 2000);</script>'
    else:
        return f'<h2>Erro: {message}</h2>'

@app.route('/api/devices/generate-registration')
def generate_registration():
    return jsonify({
        'registration_id': f"REG_{secrets.token_urlsafe(12)}",
        'instructions': 'Configure este ID no Pico e conecte'
    })

@app.route('/api/devices/<registration_id>/approve', methods=['POST'])
def approve_device(registration_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Usuário não encontrado'}), 400
    
    data = request.get_json() or {}
    display_name = data.get('displayName', f'Mirror {registration_id[:8]}')
    
    device_id = f"mirror_{secrets.token_urlsafe(6)}"
    api_key = f"sk_{secrets.token_urlsafe(20)}"
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE devices 
        SET device_id = ?, user_id = ?, display_name = ?, status = 'approved', api_key = ?
        WHERE registration_id = ?
    ''', (device_id, user_id, display_name, api_key, registration_id))
    conn.commit()
    conn.close()
    
    mqtt_manager.send_registration_response(registration_id, 'approved', device_id, api_key)
    mqtt_manager.sync_device(device_id)
    
    return jsonify({'success': True, 'device_id': device_id})

@app.route('/api/devices')
def get_devices():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'devices': []})
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT registration_id, device_id, display_name, status
        FROM devices WHERE user_id = ? OR user_id IS NULL
    ''', (user_id,))
    devices = cursor.fetchall()
    conn.close()
    
    return jsonify({'devices': [dict(d) for d in devices]})

@app.route('/api/devices/<device_id>/sync', methods=['POST'])
def sync_device(device_id):
    mqtt_manager.sync_device(device_id)
    return jsonify({'success': True})

# ==================== SINCRONIZAÇÃO AUTOMÁTICA ====================
def auto_sync():
    while True:
        try:
            conn = db.get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT user_id FROM users WHERE access_token IS NOT NULL
            ''')
            users = cursor.fetchall()
            
            for user in users:
                cursor.execute('''
                    SELECT device_id FROM devices 
                    WHERE user_id = ? AND status = 'approved'
                ''', (user['user_id'],))
                devices = cursor.fetchall()
                
                for device in devices:
                    mqtt_manager.sync_device(device['device_id'])
            
            conn.close()
        except Exception as e:
            print(f"Erro na sincronização: {e}")
        
        time.sleep(900)  # 15 minutos

threading.Thread(target=auto_sync, daemon=True).start()

if __name__ == '__main__':
    print("="*50)
    print("Magic Mirror Backend Simplificado FUNCIONANDO")
    print("="*50)
    print("Funcionalidades: Azure AD + Outlook + MQTT")
    print("Acesse: http://localhost:5000")
    print("="*50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)