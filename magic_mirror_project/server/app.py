#!/usr/bin/env python3
"""
Magic Mirror - Backend Atualizado com MQTT
Sistema completo para sincronização de eventos do Outlook
CORREÇÕES: Melhor handling de dispositivos e topic prefix dinâmico
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

print(f"🆔 TOPIC PREFIX GERADO: {TOPIC_PREFIX}")

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
    
    # Inserir topic_prefix na configuração se não existir
    cursor.execute('''
        INSERT OR IGNORE INTO config (id, topic_prefix) VALUES (1, ?)
    ''', (TOPIC_PREFIX,))
    
    # Atualizar topic_prefix se mudou
    cursor.execute('''
        UPDATE config SET topic_prefix = ? WHERE id = 1
    ''', (TOPIC_PREFIX,))
    
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
        print("⚠️ Nenhum token válido disponível")
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
            print(f"📅 Obtidos {len(events)} eventos do Outlook")
            return events
        else:
            print(f"⚠️ Erro Graph API: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Erro ao buscar eventos: {e}")
    
    return []

# ==================== MQTT MANAGER MELHORADO ====================
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
            print(f"🏷️ Topic Prefix: {self.topic_prefix}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ Erro MQTT: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            # Subscrever ao tópico de registro
            registration_topic = f"{self.topic_prefix}/registration"
            client.subscribe(registration_topic)
            print(f"✅ MQTT conectado")
            print(f"👂 Escutando registros em: {registration_topic}")
        else:
            print(f"❌ Falha MQTT: código {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"🔌 MQTT desconectado: código {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            topic_str = msg.topic
            payload = json.loads(msg.payload.decode())
            
            print(f"📨 MQTT recebido em: {topic_str}")
            
            if f"{self.topic_prefix}/registration" == topic_str:
                self.handle_registration(payload)
            else:
                print(f"⚠️ Tópico não reconhecido: {topic_str}")
                
        except Exception as e:
            print(f"❌ Erro processando MQTT: {e}")
    
    def handle_registration(self, payload):
        print(f"=== DEBUG REGISTRATION ===")
        print(f"Payload recebido: {payload}")
        print(f"Payload type: {type(payload)}")
        
        reg_id = payload.get('registration_id')
        device_info = payload.get('device_info', 'Dispositivo desconhecido')
        mac_address = payload.get('mac_address', '')
        
        print(f"Registration ID extraído: {reg_id}")
        print(f"Device info: {device_info}")
        print("===========================")
    
        if not reg_id:
            print("Registration ID ausente")
            return

            reg_id = payload.get('registration_id')
            device_info = payload.get('device_info', 'Dispositivo desconhecido')
            mac_address = payload.get('mac_address', '')
            
            if not reg_id:
                print("⚠️ Registration ID ausente")
                return
            
            print(f"📝 Processando registro: {reg_id}")
            print(f"   Info: {device_info}")
            if mac_address:
                print(f"   MAC: {mac_address}")
            
            conn = get_db()
            
            # Verificar se dispositivo já existe
            device = conn.execute('SELECT * FROM devices WHERE registration_id = ?', (reg_id,)).fetchone()
            
            if device:
                # Atualizar último contato
                conn.execute('UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?', (reg_id,))
                conn.commit()
                
                if device['status'] == 'approved':
                    # Dispositivo já aprovado - enviar confirmação completa
                    response = {
                        'registration_id': reg_id,
                        'status': 'approved',
                        'device_id': device['device_id'],
                        'topic_prefix': self.topic_prefix,
                        'events_topic': f"{self.topic_prefix}/devices/{device['device_id']}/events"
                    }
                    
                    # Publicar resposta
                    self.client.publish(f"{self.topic_prefix}/registration", json.dumps(response))
                    print(f"✅ Dispositivo aprovado reconectado: {device['device_id']}")
                    
                    # Forçar sincronização imediata
                    threading.Thread(target=lambda: time.sleep(1) or self.sync_device(device['device_id']), daemon=True).start()
                else:
                    # Dispositivo ainda pendente
                    response = {
                        'registration_id': reg_id,
                        'status': 'pending',
                        'topic_prefix': self.topic_prefix
                    }
                    self.client.publish(f"{self.topic_prefix}/registration", json.dumps(response))
                    print(f"⏳ Dispositivo ainda pendente: {reg_id}")
            else:
                # Novo dispositivo - inserir como pendente
                conn.execute('''
                    INSERT INTO devices (registration_id, device_info, mac_address, status) 
                    VALUES (?, ?, ?, 'pending')
                ''', (reg_id, device_info, mac_address))
                conn.commit()
                
                response = {
                    'registration_id': reg_id,
                    'status': 'pending',
                    'topic_prefix': self.topic_prefix,
                    'message': 'Dispositivo registrado. Aguardando aprovação.'
                }
                self.client.publish(f"{self.topic_prefix}/registration", json.dumps(response))
                print(f"🆕 Novo dispositivo registrado: {reg_id}")
            
            conn.close()
        
    def sync_device(self, device_id):
        if not self.connected:
            print("❌ MQTT não conectado - não é possível sincronizar")
            return False
        
        print(f"🔄 Iniciando sincronização para: {device_id}")
        
        # Obter eventos do Outlook
        events = get_today_events()
        
        # Ordenar eventos por horário
        events_sorted = sorted(events, key=lambda x: x.get('time', '23:59'))
        
        # Preparar dados para envio
        events_data = {
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'events': events_sorted,
            'count': len(events_sorted),
            'sync_time': datetime.now().isoformat(),
            'server_info': {
                'topic_prefix': self.topic_prefix,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'server_version': '2.0'
            }
        }
        
        # Publicar eventos
        topic = f"{self.topic_prefix}/devices/{device_id}/events"
        message = json.dumps(events_data, ensure_ascii=False)
        
        try:
            result = self.client.publish(topic, message)
            
            print(f"📡 Dados publicados em: {topic}")
            print(f"📦 Tamanho da mensagem: {len(message)} bytes")
            print(f"📅 Eventos enviados: {len(events_sorted)}")
            
            # Log dos primeiros eventos
            for i, event in enumerate(events_sorted[:3]):
                time_str = event.get('time', 'Todo dia')
                title = event.get('title', 'Sem título')
                print(f"   {i+1}. {time_str} - {title}")
            
            if len(events_sorted) > 3:
                print(f"   ... e mais {len(events_sorted) - 3} eventos")
            
            print(f"✅ Sincronização concluída para {device_id}")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao publicar: {e}")
            return False
    
    def approve_device(self, registration_id):
        """Aprovar dispositivo e gerar device_id"""
        device_id = f"mirror_{secrets.token_urlsafe(6)}"
        
        conn = get_db()
        
        # Atualizar status do dispositivo
        conn.execute('''
            UPDATE devices SET device_id = ?, status = 'approved', last_seen = CURRENT_TIMESTAMP 
            WHERE registration_id = ?
        ''', (device_id, registration_id))
        conn.commit()
        
        print(f"✅ Dispositivo aprovado: {registration_id} → {device_id}")
        
        # Enviar confirmação de aprovação
        response = {
            'registration_id': registration_id,
            'status': 'approved',
            'device_id': device_id,
            'topic_prefix': self.topic_prefix,
            'events_topic': f"{self.topic_prefix}/devices/{device_id}/events",
            'message': 'Dispositivo aprovado com sucesso!'
        }
        
        self.client.publish(f"{self.topic_prefix}/registration", json.dumps(response))
        
        # Aguardar um pouco e sincronizar
        threading.Thread(target=lambda: time.sleep(2) or self.sync_device(device_id), daemon=True).start()
        
        conn.close()
        return device_id

# Instanciar MQTT Manager
mqtt_manager = MQTTManager()

# ==================== ROTAS WEB ====================
@app.route('/')
def index():
    # Lista de possíveis locais para o arquivo HTML
    possible_paths = [
        'index.html',
        './index.html', 
        'templates/index.html',
        os.path.join(os.path.dirname(__file__), 'index.html'),
        os.path.join(os.path.dirname(__file__), '', 'index.html')
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"Servindo frontend de: {path}")
            return send_file(path)
    
    # Se não encontrou, retorna o HTML inline
    return """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Mirror - Interface não encontrada</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            margin: 50px; 
            background: #f0f0f0;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            max-width: 600px;
            margin: 0 auto;
        }
        h1 { color: #d32f2f; }
        .info { 
            background: #e3f2fd; 
            padding: 20px; 
            border-radius: 5px; 
            margin: 20px 0; 
            text-align: left;
        }
        .paths { 
            background: #f5f5f5; 
            padding: 15px; 
            border-radius: 5px; 
            font-family: monospace;
            text-align: left;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Interface Magic Mirror não encontrada</h1>
        
        <div class="info">
            <strong>O frontend HTML não foi encontrado.</strong>
            <p>Para resolver:</p>
            <ol>
                <li>Salve o arquivo HTML como <code>index.html</code> na mesma pasta que app.py</li>
                <li>Ou coloque na pasta <code>static/index.html</code></li>
                <li>Reinicie o servidor</li>
            </ol>
        </div>
        
        <div class="paths">
            <strong>Locais verificados:</strong><br>""" + "<br>".join([f"• {path}" for path in possible_paths]) + """
        </div>
        
        <p>
            <strong>Diretório atual:</strong> """ + os.getcwd() + """<br>
            <strong>Arquivos na pasta:</strong> """ + ", ".join([f for f in os.listdir('.') if f.endswith('.html')]) + """
        </p>
        
        <div style="margin-top: 30px;">
            <button onclick="location.reload()" style="padding: 10px 20px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer;">
                Tentar Novamente
            </button>
        </div>
    </div>
</body>
</html>
    """

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/config', methods=['POST'])
def save_config():
    config = request.get_json()
    
    if not all(k in config for k in ['clientId', 'tenantId', 'clientSecret']):
        return jsonify({'error': 'Campos obrigatórios ausentes'}), 400
    
    conn = get_db()
    conn.execute('''
        UPDATE config SET client_id = ?, tenant_id = ?, client_secret = ?
        WHERE id = 1
    ''', (config['clientId'], config['tenantId'], config['clientSecret']))
    conn.commit()
    conn.close()
    
    print(f"💾 Configuração salva: Client ID = {config['clientId'][:8]}...")
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
                <h2 style="color: #d32f2f;">❌ Configuração Ausente</h2>
                <p>Configure suas credenciais Azure primeiro na aba "Configuração do Passe".</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
            </div>
            ''', 400
        
        auth_url = app_msal.get_authorization_request_url(
            GRAPH_SCOPES,
            redirect_uri='http://localhost:5000/callback'
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"❌ Erro na autenticação: {e}")
        return f'''
        <div style="text-align: center; margin: 50px; font-family: Arial;">
            <h2 style="color: #d32f2f;">❌ Erro de Autenticação</h2>
            <p>Erro: {str(e)}</p>
            <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
        </div>
        ''', 500

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            return f'''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">❌ Erro de Autenticação</h2>
                <p>Erro retornado pela Microsoft: {error}</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
            </div>
            '''
        
        if not code:
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">❌ Código Ausente</h2>
                <p>Código de autorização não recebido.</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
            </div>
            '''
        
        app_msal = get_msal_app()
        if not app_msal:
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">❌ Erro de Configuração</h2>
                <p>Aplicação MSAL não configurada corretamente.</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
            </div>
            '''
        
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
            
            print("✅ Tokens salvos com sucesso")
            
            return '''
            <div style="text-align: center; margin: 50px; font-family: Arial; color: #2e7d32;">
                <h2>✅ Autenticação Concluída</h2>
                <p><strong>Sistema pronto para sincronizar com Outlook Calendar!</strong></p>
                <p>Agora você pode:</p>
                <ul style="text-align: left; max-width: 400px; margin: 20px auto;">
                    <li>Aprovar dispositivos Pico 2W na aba "Sincronização de Dispositivos"</li>
                    <li>Ver seus eventos sincronizados automaticamente</li>
                    <li>Fechar esta janela</li>
                </ul>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px; background: #2e7d32; color: white; border: none; border-radius: 5px;">Fechar</button>
            </div>
            '''
        else:
            error_desc = result.get("error_description", "Erro desconhecido na troca do token")
            print(f"❌ Falha na troca do token: {error_desc}")
            return f'''
            <div style="text-align: center; margin: 50px; font-family: Arial;">
                <h2 style="color: #d32f2f;">❌ Falha na Autenticação</h2>
                <p>Erro na troca do token: {error_desc}</p>
                <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
            </div>
            '''
            
    except Exception as e:
        print(f"❌ Erro no callback: {e}")
        return f'''
        <div style="text-align: center; margin: 50px; font-family: Arial;">
            <h2 style="color: #d32f2f;">❌ Erro no Callback</h2>
            <p>Erro interno: {str(e)}</p>
            <button onclick="window.close()" style="padding: 10px 20px; margin-top: 20px;">Fechar</button>
        </div>
        '''

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
    devices = conn.execute('''
        SELECT registration_id, device_id, status, device_info, mac_address, 
               first_seen, last_seen 
        FROM devices 
        ORDER BY first_seen DESC
    ''').fetchall()
    conn.close()
    
    devices_list = []
    for device in devices:
        devices_list.append({
            'registration_id': device['registration_id'],
            'device_id': device['device_id'],
            'status': device['status'],
            'device_info': device['device_info'],
            'mac_address': device['mac_address'],
            'first_seen': device['first_seen'],
            'last_seen': device['last_seen']
        })
    
    return jsonify(devices_list)

@app.route('/api/devices/<registration_id>/approve', methods=['POST'])
def approve_device_route(registration_id):
    try:
        device_id = mqtt_manager.approve_device(registration_id)
        return jsonify({
            'success': True, 
            'device_id': device_id,
            'message': f'Dispositivo {registration_id} aprovado como {device_id}'
        })
    except Exception as e:
        print(f"❌ Erro ao aprovar dispositivo: {e}")
        return jsonify({
            'success': False, 
            'error': str(e)
        }), 500

@app.route('/api/sync/<device_id>', methods=['POST'])
def sync_device_route(device_id):
    try:
        success = mqtt_manager.sync_device(device_id)
        return jsonify({
            'success': success,
            'message': f'Sincronização {"bem-sucedida" if success else "falhada"} para {device_id}'
        })
    except Exception as e:
        print(f"❌ Erro na sincronização manual: {e}")
        return jsonify({
            'success': False, 
            'error': str(e)
        }), 500

# ==================== SINCRONIZAÇÃO AUTOMÁTICA ====================
def auto_sync():
    """Sincronização automática a cada hora"""
    while True:
        time.sleep(3600)  # 1 hora
        
        try:
            print("🕐 Iniciando sincronização automática...")
            
            conn = get_db()
            devices = conn.execute('''
                SELECT device_id FROM devices WHERE status = "approved"
            ''').fetchall()
            conn.close()
            
            if devices:
                print(f"Sincronizando {len(devices)} dispositivos aprovados...")
                for device in devices:
                    mqtt_manager.sync_device(device['device_id'])
                    time.sleep(2)  # Pausa entre sincronizações
                print("Sincronização automática concluída")
            else:
                print("Nenhum dispositivo aprovado para sincronizar")
                
        except Exception as e:
            print(f"Erro na sincronização automática: {e}")

# Iniciar thread de sincronização automática
threading.Thread(target=auto_sync, daemon=True).start()

# ==================== INICIALIZAÇÃO ====================
if __name__ == '__main__':
    print("=" * 60)
    print("MAGIC MIRROR - BACKEND v2.0 CORRIGIDO")
    print("Sistema de Sincronização com MQTT Dinâmico")
    print("=" * 60)
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic Prefix: {TOPIC_PREFIX}")
    print("=" * 60)
    print("ROTAS DISPONÍVEIS:")
    print("  • Web Interface: http://localhost:5000")
    print("  • Status API: http://localhost:5000/api/status")
    print("  • Dispositivos: http://localhost:5000/api/devices")
    print("  • Eventos: http://localhost:5000/api/events")
    print("=" * 60)
    print()
    print("INSTRUÇÕES PARA USO:")
    print("1. Configure credenciais Azure na interface web")
    print("2. Execute autenticação OAuth2")
    print("3. Conecte o Pico 2W ao WiFi")
    print("4. Aprove o dispositivo na aba 'Sincronização de Dispositivos'")
    print("5. Eventos serão sincronizados automaticamente a cada hora")
    print()
    print("CORREÇÕES IMPLEMENTADAS:")
    print("• Topic prefix dinâmico compartilhado entre backend e Pico")
    print("• Melhor handling de registro e aprovação de dispositivos")
    print("• Logs detalhados para debugging")
    print("• Sincronização forçada após aprovação")
    print("• Resposta completa com todos os dados necessários")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nSistema interrompido pelo usuário")
    except Exception as e:
        print(f"Erro fatal no servidor: {e}")
    finally:
        if mqtt_manager.client:
            mqtt_manager.client.loop_stop()
            mqtt_manager.client.disconnect()
        print("Sistema encerrado")