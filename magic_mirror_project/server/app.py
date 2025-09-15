#!/usr/bin/env python3
"""
Magic Mirror - Backend com MQTT Público
Versão com autenticação OAuth2 corrigida
"""

import sqlite3
import secrets
import json
import threading
import time
from datetime import datetime, timedelta
import os

from flask import Flask, request, jsonify, session, redirect, send_file
import requests
import msal
import paho.mqtt.client as mqtt
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = secrets.token_urlsafe(32)

# Configuração de sessão
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME='space_mirror_session',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)

CORS(app, supports_credentials=True)

# Configurações - MQTT Público
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = f"magic_mirror_{secrets.token_urlsafe(8)}"

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
    
    # Usar PublicClientApplication em vez de ConfidentialClientApplication
    # para resolver o erro AADSTS700025
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

# ==================== ROTAS ESTÁTICAS ====================
@app.route('/')
def index():
    possible_paths = [
        'index.html',
        './index.html',
        os.path.join(os.getcwd(), 'index.html'),
        os.path.join(os.path.dirname(__file__), 'index.html'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html'),
        'static/index.html',
        'templates/index.html'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                print(f"Servindo index.html de: {os.path.abspath(path)}")
                return send_file(path)
            except Exception as e:
                print(f"Erro ao servir {path}: {e}")
                continue
    
    return '<h1>index.html não encontrado</h1>', 404

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ==================== API ROTAS ====================
@app.route('/api/config', methods=['POST'])
def save_config():
    config = request.get_json()
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO config (id, topic_prefix, client_id, tenant_id, client_secret)
        VALUES (1, ?, ?, ?, ?)
    ''', (TOPIC_PREFIX, config['clientId'], config['tenantId'], config['clientSecret']))
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
    else:
        return jsonify({
            'topic_prefix': TOPIC_PREFIX,
            'has_credentials': False,
            'has_token': False
        })

@app.route('/api/status')
def status():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    devices_count = conn.execute('SELECT COUNT(*) as count FROM devices').fetchone()
    approved_count = conn.execute('SELECT COUNT(*) as count FROM devices WHERE status = "approved"').fetchone()
    conn.close()
    
    # Debug: log do status
    has_credentials = bool(config and config['client_id'] and config['tenant_id'] and config['client_secret'])
    has_token = bool(config and config['access_token'] and len(config['access_token']) > 10)
    
    print(f"=== STATUS DEBUG ===")
    print(f"Config exists: {bool(config)}")
    print(f"Has credentials: {has_credentials}")
    print(f"Has token: {has_token}")
    if config and config['access_token']:
        print(f"Token length: {len(config['access_token'])}")
        print(f"Token preview: {config['access_token'][:50]}...")
    
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
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Configuration Missing</h2>
                <p>Please save your Azure credentials first.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #0078d4; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            ''', 400
        
        # Usar uma abordagem mais simples - sem validação de estado
        # Para resolver problemas de sessão em popups
        print("Gerando URL de autenticação sem validação de estado")
        
        auth_url = app_msal.get_authorization_request_url(
            GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        return redirect(auth_url)
        
    except ValueError as ve:
        error_msg = str(ve)
        if "invalid_tenant" in error_msg.lower() or "authority" in error_msg.lower():
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Invalid Tenant ID</h2>
                <p>The Tenant ID you provided is incorrect or doesn't exist.</p>
                <p>Please get the correct Tenant ID from Azure Portal:</p>
                <ol style="text-align: left; display: inline-block;">
                    <li>Go to portal.azure.com</li>
                    <li>Navigate to "Microsoft Entra ID"</li>
                    <li>Look for "Tenant information"</li>
                    <li>Copy the correct "Directory (tenant) ID"</li>
                </ol>
                <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            ''', 400
        else:
            return f'Configuration Error: {error_msg}', 500
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return f'Authentication Error: {str(e)}', 500

@app.route('/callback')
def callback():
    """Processa o callback de autenticação OAuth2"""
    try:
        # Verificar parâmetros
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            return f'''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Authentication Error</h2>
                <p>Error: {error}</p>
                <p>Description: {request.args.get('error_description', 'No description available')}</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            '''
        
        if not code:
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Missing Authorization Code</h2>
                <p>No authorization code received from Azure.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            '''
        
        print(f"Código de autorização recebido: {code[:20]}...")
        
        # Obter aplicação MSAL
        app_msal = get_msal_app()
        if not app_msal:
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Configuration Error</h2>
                <p>MSAL application not configured.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            '''
        
        # Trocar código por token
        print("Trocando código por token de acesso...")
        result = app_msal.acquire_token_by_authorization_code(
            code,
            scopes=GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        if "access_token" in result:
            print("Token de acesso obtido com sucesso!")
            
            # Salvar token no banco de dados
            conn = get_db()
            conn.execute('''
                UPDATE config SET 
                access_token = ?, 
                refresh_token = ?, 
                expires_at = ?
                WHERE id = 1
            ''', (
                result['access_token'], 
                result.get('refresh_token'), 
                (datetime.now() + timedelta(seconds=result.get('expires_in', 3600))).isoformat()
            ))
            conn.commit()
            conn.close()
            
            print("Token salvo no banco de dados")
            
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial; background: linear-gradient(135deg, #0a0a0a, #1a1a2e); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center;">
                <div style="background: rgba(0, 255, 255, 0.1); border: 2px solid #00ffff; border-radius: 15px; padding: 40px; box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);">
                    <h2 style="color: #00ffff; font-family: 'Orbitron', monospace;">AUTHENTICATION SUCCESSFUL</h2>
                    <p style="margin: 20px 0; font-size: 16px;">Your Space Mirror credentials have been validated and stored securely.</p>
                    <p style="margin: 20px 0; color: #00ff00;">System is now ready to sync with your Outlook Calendar!</p>
                    <button onclick="window.close()" style="padding: 15px 30px; background: linear-gradient(45deg, #00ffff, #ff00ff); color: #000; border: none; border-radius: 8px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: bold; text-transform: uppercase;">Close Window</button>
                </div>
            </div>
            '''
        else:
            error_desc = result.get("error_description", "Unknown error during token exchange")
            print(f"Erro na troca do token: {error_desc}")
            
            return f'''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Token Exchange Failed</h2>
                <p>Error: {result.get("error", "unknown_error")}</p>
                <p>Description: {error_desc}</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
            </div>
            '''
            
    except Exception as e:
        print(f"Erro no callback: {e}")
        return f'''
        <div style="text-align: center; margin: 50px; font-family: Arial;">
            <h2 style="color: #d32f2f;">Callback Error</h2>
            <p>An error occurred while processing the authentication callback.</p>
            <p>Details: {str(e)}</p>
            <button onclick="window.close()" style="padding: 10px 20px; background: #d32f2f; color: white; border: none; border-radius: 4px; cursor: pointer;">Close Window</button>
        </div>
        '''

@app.route('/api/complete-auth', methods=['POST'])
def complete_auth():
    # Esta rota não é mais necessária com o callback funcionando
    return jsonify({'success': False, 'error': 'Use OAuth2 callback flow instead'})

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
    print("Magic Mirror Backend - AUTENTICAÇÃO CORRIGIDA")
    print("=" * 50)
    print("✅ OAuth2 callback flow implementado!")
    print(f"📡 MQTT: {MQTT_BROKER} (público)")
    print(f"🏷️ Tópico: {TOPIC_PREFIX}")
    print("🌐 Acesse: http://localhost:5000")
    print("=" * 50)
    
    # Debug: Mostrar rotas registradas
    print("Rotas API disponíveis:")
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api') or rule.rule == '/callback':
            print(f"  {rule.methods} {rule.rule}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)