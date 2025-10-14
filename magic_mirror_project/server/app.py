#!/usr/bin/env python3
"""
SPACE MIRROR - Backend Híbrido Inteligente
Detecta automaticamente se deve usar Application ou Delegated Permissions
Funciona com: Contas Pessoais, Corporativas e Estudantis
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

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
CORS(app, supports_credentials=True)

# Configurações
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = "space_mirror_hybrid"
GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
REDIRECT_URI = "http://localhost:5000/callback"

# Scopes para delegated permissions (IMPORTANTE: usar openid e offline_access)
DELEGATED_SCOPES = ['openid', 'profile', 'email', 'offline_access', 'Calendars.Read']

# Scopes para application permissions
APPLICATION_SCOPES = ['https://graph.microsoft.com/.default']

print("\n" + "="*70)
print("🚀 SPACE MIRROR - BACKEND HÍBRIDO INTELIGENTE")
print("="*70)
print("✨ Modo Automático:")
print("   • COM Client Secret → Application Permissions")
print("   • SEM Client Secret → Delegated Permissions (Login Interativo)")
print("="*70)
print(f"📡 MQTT: {MQTT_BROKER}:{MQTT_PORT}")
print(f"🔗 Redirect: {REDIRECT_URI}")
print("="*70 + "\n")

# Banco de dados
def init_db():
    conn = sqlite3.connect('mirror.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY,
        client_id TEXT,
        tenant_id TEXT,
        client_secret TEXT,
        user_email TEXT,
        access_token TEXT,
        refresh_token TEXT,
        expires_at TEXT,
        user_name TEXT,
        auth_mode TEXT DEFAULT 'delegated'
    )''')
    
    # Verifica e adiciona colunas necessárias
    c.execute("PRAGMA table_info(config)")
    cols = [col[1] for col in c.fetchall()]
    
    if 'user_name' not in cols:
        c.execute('ALTER TABLE config ADD COLUMN user_name TEXT')
    if 'client_secret' not in cols:
        c.execute('ALTER TABLE config ADD COLUMN client_secret TEXT')
    if 'tenant_id' not in cols:
        c.execute('ALTER TABLE config ADD COLUMN tenant_id TEXT')
    if 'auth_mode' not in cols:
        c.execute('ALTER TABLE config ADD COLUMN auth_mode TEXT DEFAULT "delegated"')
    
    c.execute('''CREATE TABLE IF NOT EXISTS devices (
        registration_id TEXT PRIMARY KEY,
        device_id TEXT,
        status TEXT DEFAULT 'pending',
        device_info TEXT,
        mac_address TEXT,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('INSERT OR IGNORE INTO config (id) VALUES (1)')
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado\n")

init_db()

def get_db():
    conn = sqlite3.connect('mirror.db')
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================================
# SISTEMA DE DETECÇÃO AUTOMÁTICA DE MODO
# ============================================================================

def detect_auth_mode():
    """Detecta automaticamente qual modo de autenticação usar"""
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    
    if not cfg or not cfg['client_id']:
        return None, "Não configurado"
    
    has_secret = bool(cfg['client_secret'])
    has_email = bool(cfg['user_email'])
    
    if has_secret and has_email:
        return 'application', "Application Permissions (Client Credentials)"
    elif has_secret:
        return 'application', "Application Permissions (mas precisa do email do usuário)"
    else:
        return 'delegated', "Delegated Permissions (Login Interativo)"

# ============================================================================
# MSAL - GERENCIAMENTO HÍBRIDO
# ============================================================================

def get_msal_app():
    """Cria o app MSAL apropriado baseado na configuração"""
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    
    if not cfg or not cfg['client_id']:
        return None, None
    
    # IMPORTANTE: Para contas pessoais, SEMPRE usar 'consumers' ou 'common'
    # 'consumers' = apenas contas pessoais (Outlook, Hotmail, Live)
    # 'common' = todos os tipos de conta
    tenant = 'consumers'  # Força uso de contas pessoais
    
    # Se configurou um tenant específico (para corporativas), usa ele
    if cfg['tenant_id'] and cfg['tenant_id'] not in ['common', 'consumers']:
        tenant = cfg['tenant_id']
    
    authority = f"https://login.microsoftonline.com/{tenant}"
    
    # Se tem Client Secret, usa ConfidentialClientApplication
    if cfg['client_secret']:
        app = msal.ConfidentialClientApplication(
            cfg['client_id'],
            authority=authority,
            client_credential=cfg['client_secret']
        )
        return app, 'application'
    
    # Se não tem Client Secret, usa PublicClientApplication
    else:
        app = msal.PublicClientApplication(
            cfg['client_id'],
            authority=authority
        )
        return app, 'delegated'

def get_valid_token():
    """Obtém token válido usando o modo apropriado"""
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    
    if not cfg or not cfg['client_id']:
        conn.close()
        return None
    
    # Verifica se tem token válido em cache
    if cfg['access_token'] and cfg['expires_at']:
        try:
            exp = datetime.fromisoformat(cfg['expires_at'])
            if datetime.now() < exp - timedelta(minutes=5):
                token = cfg['access_token']
                conn.close()
                return token
        except:
            pass
    
    # Token expirado ou não existe - precisa renovar
    app, mode = get_msal_app()
    
    if not app:
        conn.close()
        return None
    
    # ============================================================================
    # MODO APPLICATION - Client Credentials Flow
    # ============================================================================
    if mode == 'application' and cfg['client_secret']:
        try:
            result = app.acquire_token_for_client(scopes=APPLICATION_SCOPES)
            
            if result and "access_token" in result:
                token = result['access_token']
                expires_in = result.get('expires_in', 3600)
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                
                conn.execute('UPDATE config SET access_token = ?, expires_at = ?, auth_mode = ? WHERE id = 1', 
                            (token, expires_at, 'application'))
                conn.commit()
                conn.close()
                
                print("✅ Token obtido via Application Permissions")
                return token
            else:
                error = result.get('error_description', 'Erro desconhecido')
                print(f"❌ Erro Application: {error}")
                conn.close()
                return None
                
        except Exception as e:
            print(f"❌ Erro ao obter token Application: {e}")
            conn.close()
            return None
    
    # ============================================================================
    # MODO DELEGATED - Refresh Token Flow
    # ============================================================================
    elif mode == 'delegated':
        # Tenta usar refresh token se disponível
        if cfg['refresh_token']:
            try:
                result = app.acquire_token_by_refresh_token(
                    cfg['refresh_token'],
                    scopes=DELEGATED_SCOPES
                )
                
                if result and "access_token" in result:
                    token = result['access_token']
                    expires_in = result.get('expires_in', 3600)
                    expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                    
                    conn.execute('''UPDATE config SET 
                                  access_token = ?, 
                                  refresh_token = ?,
                                  expires_at = ?,
                                  auth_mode = ?
                                  WHERE id = 1''', 
                               (token,
                                result.get('refresh_token', cfg['refresh_token']),
                                expires_at,
                                'delegated'))
                    conn.commit()
                    conn.close()
                    
                    print("✅ Token renovado via Delegated Permissions")
                    return token
            except Exception as e:
                print(f"⚠️ Falha ao renovar token: {e}")
        
        # Se não tem refresh token ou falhou, precisa fazer login
        conn.close()
        return None
    
    conn.close()
    return None

# ============================================================================
# OBTENÇÃO DE EVENTOS DO CALENDÁRIO
# ============================================================================

def get_today_events():
    """Obtém eventos do dia usando o endpoint apropriado"""
    token = get_valid_token()
    if not token:
        print("❌ Token não disponível para buscar eventos")
        return []
    
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    auth_mode = cfg['auth_mode'] if cfg else 'delegated'
    user_email = cfg['user_email'] if cfg else None
    conn.close()
    
    today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time()).isoformat() + 'Z'
    end = datetime.combine(today, datetime.max.time()).isoformat() + 'Z'
    
    # Determina o endpoint correto
    if auth_mode == 'application' and user_email:
        # Application mode - precisa especificar o usuário
        url = f"{GRAPH_ENDPOINT}users/{user_email}/events"
        print(f"🔍 Buscando eventos (Application) para: {user_email}")
    else:
        # Delegated mode - usa /me
        url = f"{GRAPH_ENDPOINT}me/events"
        print("🔍 Buscando eventos (Delegated) para usuário autenticado")
    
    params = {
        '$filter': f"start/dateTime ge '{start}' and start/dateTime le '{end}'",
        '$select': 'subject,start,end,location,isAllDay',
        '$orderby': 'start/dateTime asc',
        '$top': 20
    }
    
    try:
        res = requests.get(url, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=10)
        
        if res.status_code == 200:
            events = []
            for e in res.json().get('value', []):
                sd = datetime.fromisoformat(e['start']['dateTime'].replace('Z', '+00:00'))
                events.append({
                    'title': e.get('subject', 'Sem título'),
                    'time': sd.strftime('%H:%M') if not e.get('isAllDay') else '',
                    'isAllDay': e.get('isAllDay', False)
                })
            print(f"✅ {len(events)} eventos obtidos")
            return events
        else:
            print(f"❌ Erro ao buscar eventos: {res.status_code}")
            try:
                error_data = res.json()
                print(f"   Detalhes: {error_data.get('error', {}).get('message', 'Sem detalhes')}")
            except:
                pass
            return []
    except Exception as e:
        print(f"❌ Erro na requisição de eventos: {e}")
        return []

# ============================================================================
# MQTT MANAGER
# ============================================================================

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
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ MQTT erro de conexão: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            topic = f"{self.topic_prefix}/registration"
            client.subscribe(topic)
            print(f"✅ MQTT conectado - Tópico: {topic}\n")
    
    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print("🔌 MQTT desconectado")
    
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            if 'registration' in msg.topic and payload.get('status') == 'requesting_approval':
                reg_id = payload.get('registration_id')
                if reg_id and not payload.get('device_id'):
                    print(f"\n📨 Novo dispositivo solicitando registro: {reg_id}")
                    self.handle_registration(payload)
        except Exception as e:
            print(f"❌ Erro ao processar mensagem MQTT: {e}")
    
    def handle_registration(self, payload):
        reg_id = payload.get('registration_id')
        info = payload.get('device_info', 'Dispositivo Desconhecido')
        mac = payload.get('mac_address', '')
        
        if not reg_id:
            return
        
        conn = get_db()
        
        try:
            dev = conn.execute('SELECT * FROM devices WHERE registration_id = ?', (reg_id,)).fetchone()
            
            if dev and dev['status'] == 'approved' and dev['device_id']:
                device_id = dev['device_id']
                conn.execute('UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?', (reg_id,))
                conn.commit()
                print(f"✅ Dispositivo já aprovado: {device_id}")
            else:
                device_id = f"mirror_{secrets.token_urlsafe(6)}"
                
                if dev:
                    conn.execute('''UPDATE devices SET device_id = ?, status = 'approved', 
                                    last_seen = CURRENT_TIMESTAMP WHERE registration_id = ?''', 
                                (device_id, reg_id))
                else:
                    conn.execute('''INSERT INTO devices (registration_id, device_id, device_info, 
                                    mac_address, status) VALUES (?, ?, ?, ?, 'approved')''', 
                                (reg_id, device_id, info, mac))
                
                conn.commit()
                print(f"✅ Novo dispositivo aprovado: {device_id}")
            
            resp = {
                'registration_id': reg_id,
                'status': 'approved',
                'device_id': device_id,
                'topic_prefix': self.topic_prefix,
                'events_topic': f"{self.topic_prefix}/devices/{device_id}/events"
            }
            
            self.client.publish(f"{self.topic_prefix}/registration", json.dumps(resp))
            threading.Thread(target=lambda: time.sleep(2) or self.sync_device(device_id), daemon=True).start()
            
        except Exception as e:
            print(f"❌ Erro ao processar registro: {e}")
        finally:
            conn.close()
    
    def sync_device(self, device_id):
        if not self.connected:
            print("❌ MQTT não conectado - sync abortado")
            return False
        
        print(f"🔄 Iniciando sincronização: {device_id}")
        
        events = get_today_events()
        events_sorted = sorted(events, key=lambda x: x.get('time', '23:59'))
        
        data = {
            'device_id': device_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'events': events_sorted,
            'count': len(events_sorted),
            'sync_time': datetime.now().isoformat()
        }
        
        topic = f"{self.topic_prefix}/devices/{device_id}/events"
        msg = json.dumps(data, ensure_ascii=False)
        
        try:
            self.client.publish(topic, msg)
            print(f"✅ Sincronização concluída: {len(events_sorted)} eventos enviados\n")
            return True
        except Exception as e:
            print(f"❌ Erro na sincronização: {e}")
            return False

mqtt_manager = MQTTManager()

# ============================================================================
# ROTAS DA API
# ============================================================================

@app.route('/')
def index():
    for p in ['index.html', './index.html', 'templates/index.html']:
        if os.path.exists(p):
            return send_file(p)
    return "<h1>❌ index.html não encontrado</h1>", 404

@app.route('/api/config', methods=['POST'])
def save_config():
    cfg = request.get_json()
    
    if 'clientId' not in cfg:
        return jsonify({'error': 'Client ID obrigatório'}), 400
    
    conn = get_db()
    
    # Detecta o modo automaticamente
    has_secret = bool(cfg.get('clientSecret'))
    
    conn.execute('''UPDATE config SET 
                    client_id = ?, 
                    tenant_id = ?,
                    client_secret = ?,
                    user_email = ?,
                    auth_mode = ?
                    WHERE id = 1''',
                (cfg['clientId'],
                 cfg.get('tenantId', 'common'),
                 cfg.get('clientSecret'),
                 cfg.get('userEmail'),
                 'application' if has_secret else 'delegated'))
    conn.commit()
    conn.close()
    
    mode = 'Application Permissions' if has_secret else 'Delegated Permissions'
    print(f"✅ Configuração salva - Modo: {mode}")
    
    return jsonify({
        'success': True,
        'mode': mode
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    conn.close()
    
    mode, mode_desc = detect_auth_mode()
    
    return jsonify({
        'client_id': cfg['client_id'] if cfg else None,
        'tenant_id': cfg['tenant_id'] if cfg else None,
        'user_email': cfg['user_email'] if cfg else None,
        'has_credentials': bool(cfg and cfg['client_id']),
        'has_secret': bool(cfg and cfg['client_secret']),
        'has_token': bool(cfg and cfg['access_token']),
        'user_name': cfg['user_name'] if cfg else None,
        'auth_mode': mode,
        'auth_mode_description': mode_desc
    })

@app.route('/api/status')
def status():
    conn = get_db()
    cfg = conn.execute('SELECT * FROM config WHERE id = 1').fetchone()
    dc = conn.execute('SELECT COUNT(*) as count FROM devices').fetchone()
    ac = conn.execute('SELECT COUNT(*) as count FROM devices WHERE status = "approved"').fetchone()
    conn.close()
    
    mode, mode_desc = detect_auth_mode()
    
    return jsonify({
        'online': True,
        'mqtt_connected': mqtt_manager.connected,
        'mqtt_broker': MQTT_BROKER,
        'topic_prefix': TOPIC_PREFIX,
        'has_azure_config': bool(cfg and cfg['client_id']),
        'has_token': bool(cfg and cfg['access_token']),
        'user_name': cfg['user_name'] if cfg else None,
        'user_email': cfg['user_email'] if cfg else None,
        'devices_total': dc['count'],
        'devices_approved': ac['count'],
        'auth_mode': mode,
        'auth_mode_description': mode_desc
    })

@app.route('/api/login')
def login():
    """Inicia o fluxo de login para Delegated Permissions"""
    app_msal, mode = get_msal_app()
    
    if not app_msal:
        return '<h2>❌ Configure o Client ID primeiro</h2>', 400
    
    if mode != 'delegated':
        return '<h2>⚠️ Login interativo só é necessário no modo Delegated (sem Client Secret)</h2>', 400
    
    # Adiciona prompt=select_account para forçar seleção de conta
    # Importante para contas pessoais
    url = app_msal.get_authorization_request_url(
        DELEGATED_SCOPES, 
        redirect_uri=REDIRECT_URI,
        prompt='select_account'  # Força seleção de conta
    )
    print("🔐 Iniciando fluxo de login interativo para conta pessoal...")
    return redirect(url)

@app.route('/callback')
def callback():
    """Callback do OAuth para Delegated Permissions"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        error_desc = request.args.get('error_description', 'Erro desconhecido')
        print(f"❌ OAuth erro: {error} - {error_desc}")
        return f'''
        <div style="text-align:center; margin:50px; font-family:Arial;">
            <h2 style="color:#ff0000">❌ Erro de Autenticação</h2>
            <p><strong>{error}</strong></p>
            <p>{error_desc}</p>
            <button onclick="window.close()" style="padding:10px 20px; margin-top:20px; 
                    background:#ff0000; color:white; border:none; border-radius:5px; cursor:pointer;">
                Fechar
            </button>
        </div>
        '''
    
    if not code:
        return '<h2 style="color:red">❌ Código de autorização ausente</h2>'
    
    app_msal, mode = get_msal_app()
    
    if not app_msal:
        return '<h2 style="color:red">❌ MSAL não configurado</h2>'
    
    try:
        result = app_msal.acquire_token_by_authorization_code(
            code, 
            scopes=DELEGATED_SCOPES, 
            redirect_uri=REDIRECT_URI
        )
        
        if "access_token" in result:
            # Obtém informações do usuário
            try:
                user_res = requests.get(
                    f"{GRAPH_ENDPOINT}me", 
                    headers={'Authorization': f'Bearer {result["access_token"]}'}, 
                    timeout=10
                )
                user_data = user_res.json() if user_res.status_code == 200 else {}
            except:
                user_data = {}
            
            user_name = user_data.get('displayName', 'Usuário')
            user_email = user_data.get('mail') or user_data.get('userPrincipalName') or 'N/A'
            
            expires_in = result.get('expires_in', 3600)
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            conn = get_db()
            conn.execute('''UPDATE config SET 
                            access_token = ?, 
                            refresh_token = ?, 
                            expires_at = ?,
                            user_email = ?,
                            user_name = ?,
                            auth_mode = ?
                            WHERE id = 1''',
                        (result['access_token'],
                         result.get('refresh_token'),
                         expires_at,
                         user_email,
                         user_name,
                         'delegated'))
            conn.commit()
            conn.close()
            
            print(f"✅ Login concluído: {user_name} ({user_email})\n")
            
            return '''
            <div style="text-align:center; margin:50px; font-family:Arial;">
                <h2 style="color:#00ff00">✅ Login Concluído!</h2>
                <p style="font-size:1.2em; margin:20px 0;">Autenticação realizada com sucesso</p>
                <p>Você pode fechar esta janela</p>
                <button onclick="window.close()" style="padding:12px 30px; margin-top:20px; 
                        background:#00ff00; border:none; border-radius:5px; cursor:pointer; 
                        font-weight:bold; font-size:1.1em;">
                    Fechar Janela
                </button>
                <script>setTimeout(function() { window.close(); }, 3000);</script>
            </div>
            '''
        else:
            error_msg = result.get('error_description', result.get('error', 'Erro desconhecido'))
            print(f"❌ Falha no login: {error_msg}")
            return f'''
            <div style="text-align:center; margin:50px; font-family:Arial;">
                <h2 style="color:#ff0000">❌ Falha na Autenticação</h2>
                <p>{error_msg}</p>
            </div>
            '''
            
    except Exception as e:
        print(f"❌ Erro no callback: {e}")
        return f'''
        <div style="text-align:center; margin:50px; font-family:Arial;">
            <h2 style="color:#ff0000">❌ Erro no Processamento</h2>
            <p>{str(e)}</p>
        </div>
        '''

@app.route('/api/logout', methods=['POST'])
def logout():
    conn = get_db()
    conn.execute('''UPDATE config SET 
                    access_token = NULL, 
                    refresh_token = NULL, 
                    user_email = NULL, 
                    user_name = NULL 
                    WHERE id = 1''')
    conn.commit()
    conn.close()
    print("👋 Logout realizado")
    return jsonify({'success': True})

@app.route('/api/events')
def events():
    evts = get_today_events()
    return jsonify({
        'success': True,
        'events': evts,
        'count': len(evts),
        'date': datetime.now().strftime('%Y-%m-%d')
    })

@app.route('/api/devices')
def devices():
    conn = get_db()
    devs = conn.execute('SELECT * FROM devices ORDER BY last_seen DESC').fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'devices': [{
            'registration_id': d['registration_id'],
            'device_id': d['device_id'],
            'status': d['status'],
            'device_info': d['device_info'],
            'mac_address': d['mac_address'],
            'first_seen': d['first_seen'],
            'last_seen': d['last_seen']
        } for d in devs],
        'count': len(devs)
    })

@app.route('/api/sync/<device_id>', methods=['POST'])
def sync_device(device_id):
    try:
        success = mqtt_manager.sync_device(device_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sync/all', methods=['POST'])
def sync_all():
    conn = get_db()
    devs = conn.execute('SELECT device_id FROM devices WHERE status = "approved"').fetchall()
    conn.close()
    
    count = 0
    for d in devs:
        try:
            if mqtt_manager.sync_device(d['device_id']):
                count += 1
            time.sleep(1)
        except:
            pass
    
    return jsonify({'success': True, 'count': count})

# ============================================================================
# SINCRONIZAÇÃO AUTOMÁTICA
# ============================================================================

def auto_sync():
    """Sincroniza todos os dispositivos a cada 15 minutos"""
    while True:
        time.sleep(900)  # 15 minutos
        try:
            conn = get_db()
            devs = conn.execute('SELECT device_id FROM devices WHERE status = "approved"').fetchall()
            conn.close()
            
            if devs:
                print(f"\n⏰ Sincronização automática: {len(devs)} dispositivo(s)")
                for d in devs:
                    mqtt_manager.sync_device(d['device_id'])
                    time.sleep(2)
        except Exception as e:
            print(f"❌ Erro na sincronização automática: {e}")

threading.Thread(target=auto_sync, daemon=True).start()

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

if __name__ == '__main__':
    try:
        print("\n🌟 Servidor iniciando...")
        print("📍 Acesse: http://localhost:5000\n")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\n👋 Encerrando servidor...")
    finally:
        mqtt_manager.client.loop_stop()
        mqtt_manager.client.disconnect()
        print("✅ Desconectado com sucesso\n")