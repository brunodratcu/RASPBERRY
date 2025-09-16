#!/usr/bin/env python3
"""
Magic Mirror - Backend com MQTT
Sistema completo para sincronização de eventos do Outlook
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

# Configurações MQTT
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = f"magic_mirror_{secrets.token_urlsafe(8)}"

GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
GRAPH_SCOPES = ['https://graph.microsoft.com/Calendars.Read']

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

# ==================== MICROSOFT OUTLOOK ====================
def get_msal_app():
    conn = get_db()
    config = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    if not config:
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

# ==================== MQTT MANAGER ====================
class MQTTManager:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.connect()
    
    def connect(self):
        try:
            print(f"Conectando MQTT: {MQTT_BROKER}:{MQTT_PORT}")
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
            print(f"Dispositivo aprovado reconectado: {device['device_id']}")
            self.sync_device(device['device_id'])
        else:
            if not device:
                conn.execute('INSERT OR IGNORE INTO devices (registration_id) VALUES (?)', (reg_id,))
                conn.commit()
                print(f"Novo dispositivo registrado: {reg_id}")
            response = {
                'registration_id': reg_id, 
                'status': 'pending',
                'topic_prefix': TOPIC_PREFIX
            }
            self.client.publish(f"{TOPIC_PREFIX}/registration", json.dumps(response))
        
        conn.close()
    
    def sync_device(self, device_id):
        if not self.connected:
            print("❌ MQTT não conectado - não é possível sincronizar")
            return False
        
        print(f"🔄 Iniciando sincronização para dispositivo: {device_id}")
        
        # Obter eventos do Outlook
        events = get_today_events()
        print(f"📅 Obtidos {len(events)} eventos do Outlook")
        
        # Ordenar eventos por horário (crescente)
        events_sorted = sorted(events, key=lambda x: x.get('time', '23:59'))
        
        events_data = {
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'events': events_sorted,
            'count': len(events_sorted),
            'sync_time': datetime.now().isoformat(),
            'server_info': {
                'topic_prefix': self.topic_prefix,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
        }
        
        topic = f"{self.topic_prefix}/devices/{device_id}/events"
        message = json.dumps(events_data)
        
        try:
            result = self.client.publish(topic, message)
            print(f"📡 Mensagem MQTT publicada:")
            print(f"   Tópico: {topic}")
            print(f"   Tamanho: {len(message)} bytes")
            print(f"   Eventos: {len(events_sorted)}")
            
            # Log dos primeiros eventos para verificação
            for i, event in enumerate(events_sorted[:3]):
                time_str = event.get('time', 'Todo dia')
                title = event.get('title', 'Sem título')
                print(f"   {i+1}. {time_str} - {title}")
            
            if len(events_sorted) > 3:
                print(f"   ... e mais {len(events_sorted) - 3} eventos")
            
            print(f"✅ Sincronização concluída para {device_id}")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao publicar mensagem MQTT: {e}")
            return False

mqtt_manager = MQTTManager()

# ==================== ROTAS WEB ====================
@app.route('/')
def index():
    html_paths = ['index.html', './index.html', 'templates/index.html']
    for path in html_paths:
        if os.path.exists(path):
            return send_file(path)
    return '<h1>Interface não encontrada</h1>', 404

@app.route('/favicon.ico')
def favicon():
    return '', 204

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
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">Configuração Ausente</h2>
                <p>Configure suas credenciais Azure primeiro.</p>
                <button onclick="window.close()">Fechar</button>
            </div>
            ''', 400
        
        auth_url = app_msal.get_authorization_request_url(
            GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return f'Erro de autenticação: {str(e)}', 500

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            return f'<h2>Erro de Autenticação</h2><p>{error}</p>'
        
        if not code:
            return '<h2>Código de autorização ausente</h2>'
        
        app_msal = get_msal_app()
        if not app_msal:
            return '<h2>Erro de configuração MSAL</h2>'
        
        result = app_msal.acquire_token_by_authorization_code(
            code,
            scopes=GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        if "access_token" in result:
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
            
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial; color: green;">
                <h2>Autenticação Concluída</h2>
                <p>Sistema pronto para sincronizar com Outlook Calendar</p>
                <button onclick="window.close()">Fechar</button>
            </div>
            '''
        else:
            return f'<h2>Falha na troca do token</h2><p>{result.get("error_description", "Erro desconhecido")}</p>'
            
    except Exception as e:
        return f'<h2>Erro no callback</h2><p>{str(e)}</p>'

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
    
    return jsonify({'success': True, 'device_id': device_id})

@app.route('/api/sync/<device_id>', methods=['POST'])
def sync_device(device_id):
    success = mqtt_manager.sync_device(device_id)
    return jsonify({'success': success})

# Sincronização automática a cada hora
def auto_sync():
    while True:
        time.sleep(3600)
        try:
            conn = get_db()
            devices = conn.execute('SELECT device_id FROM devices WHERE status = "approved"').fetchall()
            conn.close()
            
            for device in devices:
                mqtt_manager.sync_device(device['device_id'])
                time.sleep(1)
        except Exception as e:
            print(f"Erro na sincronização automática: {e}")

threading.Thread(target=auto_sync, daemon=True).start()

if __name__ == '__main__':
    print("=" * 50)
    print("Magic Mirror Backend - Sistema de Produção")
    print("=" * 50)
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Tópico: {TOPIC_PREFIX}")
    print("Acesse: http://localhost:5000")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)