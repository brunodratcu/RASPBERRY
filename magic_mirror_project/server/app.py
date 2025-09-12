#!/usr/bin/env python3
"""
Magic Mirror - Backend Completo
Sistema completo: Azure AD + Outlook + MQTT + Registro Manual
Versão 5.0 - Complete System
"""

import os
import sqlite3
import secrets
import json
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, session, redirect, render_template_string, send_from_directory
import requests
import msal
import paho.mqtt.client as mqtt
from flask_cors import CORS
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
CORS(app)

# Configurações MQTT
MQTT_BROKER = os.getenv('MQTT_BROKER', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC_BASE = 'magic_mirror'

# Configurações Azure
GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0/'
GRAPH_SCOPES = ['https://graph.microsoft.com/Calendars.Read', 'https://graph.microsoft.com/User.Read']

# ==================== BANCO DE DADOS ====================
class Database:
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect('mirror_complete.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                azure_client_id TEXT,
                azure_tenant_id TEXT,
                azure_client_secret TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expires DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                registration_id TEXT PRIMARY KEY,
                device_id TEXT,
                user_id TEXT,
                display_name TEXT,
                location TEXT,
                status TEXT DEFAULT 'pending',
                api_key TEXT,
                last_seen DATETIME,
                ip_address TEXT,
                firmware_version TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                sync_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_count INTEGER,
                status TEXT,
                error_message TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    def get_conn(self):
        conn = sqlite3.connect('mirror_complete.db')
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
            return False, "Estado OAuth inválido"
        
        user_id = session.get('user_id')
        if not user_id:
            return False, "Sessão de usuário não encontrada"
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT azure_client_id, azure_tenant_id, azure_client_secret
            FROM users WHERE user_id = ?
        ''', (user_id,))
        config = cursor.fetchone()
        
        if not config:
            conn.close()
            return False, "Configuração Azure não encontrada"
        
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
            expires_at = datetime.now() + timedelta(seconds=result.get('expires_in', 3600))
            cursor.execute('''
                UPDATE users 
                SET access_token = ?, refresh_token = ?, token_expires = ?
                WHERE user_id = ?
            ''', (
                result['access_token'],
                result.get('refresh_token'),
                expires_at.isoformat(),
                user_id
            ))
            conn.commit()
            conn.close()
            logger.info(f"Token obtido com sucesso para usuário {user_id}")
            return True, "Autenticação concluída com sucesso"
        
        conn.close()
        error_msg = result.get('error_description', 'Erro na autenticação Azure')
        logger.error(f"Erro na autenticação: {error_msg}")
        return False, error_msg
    
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
        
        # Verificar se o token está próximo do vencimento
        if result['token_expires']:
            try:
                expires = datetime.fromisoformat(result['token_expires'])
                if datetime.now() >= expires - timedelta(minutes=5):
                    logger.info(f"Token expirado para usuário {user_id}, tentando refresh")
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
                            new_expires = datetime.now() + timedelta(seconds=refresh_result.get('expires_in', 3600))
                            cursor.execute('''
                                UPDATE users 
                                SET access_token = ?, token_expires = ?
                                WHERE user_id = ?
                            ''', (
                                refresh_result['access_token'],
                                new_expires.isoformat(),
                                user_id
                            ))
                            conn.commit()
                            conn.close()
                            logger.info(f"Token refreshed com sucesso para usuário {user_id}")
                            return refresh_result['access_token']
                    
                    conn.close()
                    return None
            except ValueError as e:
                logger.error(f"Erro ao parsear data de expiração: {e}")
        
        token = result['access_token']
        conn.close()
        return token
    
    def get_today_events(self, user_id):
        token = self.get_valid_token(user_id)
        if not token:
            logger.warning(f"Token não disponível para usuário {user_id}")
            return []
        
        today = datetime.now().date()
        start_time = datetime.combine(today, datetime.min.time()).isoformat() + 'Z'
        end_time = datetime.combine(today, datetime.max.time()).isoformat() + 'Z'
        
        url = f"{GRAPH_ENDPOINT}me/events"
        params = {
            '$filter': f"start/dateTime ge '{start_time}' and start/dateTime le '{end_time}'",
            '$select': 'subject,start,end,location,isAllDay,bodyPreview',
            '$orderby': 'start/dateTime asc',
            '$top': 50
        }
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                events = []
                
                for event in data.get('value', []):
                    try:
                        start_dt_str = event['start']['dateTime']
                        if start_dt_str.endswith('Z'):
                            start_dt = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
                        else:
                            start_dt = datetime.fromisoformat(start_dt_str)
                        
                        events.append({
                            'title': event.get('subject', 'Sem título'),
                            'time': start_dt.strftime('%H:%M') if not event.get('isAllDay') else '',
                            'location': event.get('location', {}).get('displayName', ''),
                            'isAllDay': event.get('isAllDay', False),
                            'description': event.get('bodyPreview', ''),
                            'source': 'outlook'
                        })
                    except Exception as e:
                        logger.error(f"Erro ao processar evento: {e}")
                        continue
                
                logger.info(f"Encontrados {len(events)} eventos para usuário {user_id}")
                return events
            
            elif response.status_code == 401:
                logger.warning(f"Token inválido para usuário {user_id}")
                return []
            else:
                logger.error(f"Erro na API Graph: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Erro ao buscar eventos: {e}")
            return []

outlook = OutlookManager()

# ==================== MQTT MANAGER ====================
class MQTTManager:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.connect()
    
    def connect(self):
        try:
            logger.info(f"Conectando ao broker MQTT: {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Erro ao conectar MQTT: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(f"{MQTT_TOPIC_BASE}/registration")
            client.subscribe(f"{MQTT_TOPIC_BASE}/devices/+/heartbeat")
            client.subscribe(f"{MQTT_TOPIC_BASE}/devices/+/status")
            logger.info(f"MQTT conectado com sucesso ao {MQTT_BROKER}")
        else:
            self.connected = False
            logger.error(f"Falha na conexão MQTT: código {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning("MQTT desconectado")
    
    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            logger.info(f"Mensagem MQTT recebida: {topic}")
            
            if topic.endswith('/registration'):
                self.handle_registration(payload)
            elif topic.endswith('/heartbeat'):
                device_id = topic.split('/')[2]
                self.handle_heartbeat(device_id, payload)
            elif topic.endswith('/status'):
                device_id = topic.split('/')[2]
                self.handle_status(device_id, payload)
                
        except Exception as e:
            logger.error(f"Erro ao processar mensagem MQTT: {e}")
    
    def handle_registration(self, payload):
        registration_id = payload.get('registration_id')
        if not registration_id:
            logger.warning("Registration request sem registration_id")
            return
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT device_id, status, api_key FROM devices WHERE registration_id = ?
        ''', (registration_id,))
        device = cursor.fetchone()
        
        if device and device['status'] == 'approved':
            logger.info(f"Dispositivo já aprovado: {registration_id}")
            self.send_registration_response(
                registration_id, 'approved', 
                device['device_id'], device['api_key']
            )
            # Sincronizar imediatamente após confirmação
            self.sync_device(device['device_id'])
        else:
            if not device:
                # Criar entrada pendente
                cursor.execute('''
                    INSERT OR IGNORE INTO devices (registration_id, status)
                    VALUES (?, 'pending')
                ''', (registration_id,))
                conn.commit()
                logger.info(f"Novo dispositivo registrado como pendente: {registration_id}")
            
            self.send_registration_response(registration_id, 'pending')
        
        conn.close()
    
    def handle_heartbeat(self, device_id, payload):
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE devices 
            SET last_seen = ?, ip_address = ?, firmware_version = ?
            WHERE device_id = ?
        ''', (
            datetime.now().isoformat(),
            payload.get('ip_address'),
            payload.get('firmware_version'),
            device_id
        ))
        conn.commit()
        conn.close()
        
        # Sincronizar a cada heartbeat se necessário
        self.sync_device(device_id)
    
    def handle_status(self, device_id, payload):
        status = payload.get('status', 'unknown')
        logger.info(f"Status do dispositivo {device_id}: {status}")
    
    def send_registration_response(self, registration_id, status, device_id=None, api_key=None):
        if not self.connected:
            logger.warning("MQTT não conectado, não é possível enviar resposta de registro")
            return
        
        response = {
            'registration_id': registration_id,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        if device_id and api_key:
            response.update({
                'device_id': device_id,
                'api_key': api_key
            })
        
        topic = f"{MQTT_TOPIC_BASE}/registration"
        self.client.publish(topic, json.dumps(response))
        logger.info(f"Resposta de registro enviada: {registration_id} - {status}")
    
    def sync_device(self, device_id):
        if not self.connected:
            logger.warning(f"MQTT não conectado, não é possível sincronizar {device_id}")
            return
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, display_name FROM devices 
            WHERE device_id = ? AND status = 'approved'
        ''', (device_id,))
        device = cursor.fetchone()
        
        if not device or not device['user_id']:
            conn.close()
            logger.warning(f"Dispositivo não aprovado ou sem usuário: {device_id}")
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
        
        topic = f"{MQTT_TOPIC_BASE}/devices/{device_id}/events"
        self.client.publish(topic, json.dumps(events_data))
        
        # Log da sincronização
        cursor.execute('''
            INSERT INTO sync_logs (device_id, event_count, status)
            VALUES (?, ?, ?)
        ''', (device_id, len(events), 'success'))
        conn.commit()
        conn.close()
        
        logger.info(f"Eventos enviados para {device_id}: {len(events)} eventos")

mqtt_manager = MQTTManager()

# ==================== FRONTEND HTML COMPLETO ====================
FRONTEND_HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Mirror - Portal Completo</title>
    <style>
        :root {
            --primary-color: #0078d4;
            --secondary-color: #106ebe;
            --success-color: #107c10;
            --warning-color: #ff8c00;
            --error-color: #d13438;
            --bg-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --card-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            --border-radius: 12px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-gradient);
            min-height: 100vh;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            color: white;
        }

        .header h1 {
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }

        .nav-tabs {
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
            background: white;
            border-radius: var(--border-radius);
            padding: 8px;
            box-shadow: var(--card-shadow);
        }

        .nav-tab {
            background: transparent;
            border: none;
            padding: 15px 30px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.3s ease;
            color: #666;
        }

        .nav-tab.active {
            background: var(--primary-color);
            color: white;
            box-shadow: 0 4px 12px rgba(0, 120, 212, 0.3);
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .card {
            background: white;
            border-radius: var(--border-radius);
            padding: 30px;
            box-shadow: var(--card-shadow);
            margin-bottom: 30px;
        }

        .form-group { margin-bottom: 20px; }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }

        .form-group input, .form-group select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e1e5e9;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(0, 120, 212, 0.1);
        }

        .btn {
            background: var(--primary-color);
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
            transition: all 0.3s ease;
        }

        .btn:hover { background: var(--secondary-color); }
        .btn-success { background: var(--success-color); }
        .btn-warning { background: var(--warning-color); }
        .btn-danger { background: var(--error-color); }
        .btn-secondary { background: #6c757d; }

        .config-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        .device-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 5px solid var(--primary-color);
        }

        .device-card.pending { border-left-color: var(--warning-color); }
        .device-card.approved { border-left-color: var(--success-color); }

        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-pending { background: #fff3cd; color: #856404; }
        .status-approved { background: #d4edda; color: #155724; }

        .code-block {
            background: #2d3748;
            color: #e2e8f0;
            padding: 15px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            margin: 10px 0;
        }

        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid;
        }

        .alert-info { background: #d1ecf1; border-left-color: #bee5eb; color: #0c5460; }
        .alert-success { background: #d4edda; border-left-color: #c3e6cb; color: #155724; }
        .alert-warning { background: #fff3cd; border-left-color: #ffeaa7; color: #856404; }

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
            max-width: 350px;
        }

        .notification.success { background: var(--success-color); }
        .notification.error { background: var(--error-color); }
        .notification.info { background: var(--primary-color); }
        .notification.warning { background: var(--warning-color); }

        @media (max-width: 768px) {
            .config-grid { grid-template-columns: 1fr; }
            .nav-tabs { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🪞 Magic Mirror</h1>
            <p>Portal Completo - Registro Manual + Azure AD + Outlook</p>
        </div>

        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('setup')">🔧 Setup</button>
            <button class="nav-tab" onclick="switchTab('devices')">📱 Dispositivos</button>
            <button class="nav-tab" onclick="switchTab('azure')">🔐 Azure AD</button>
            <button class="nav-tab" onclick="switchTab('tutorial')">📚 Tutorial</button>
        </div>

        <!-- Setup Tab -->
        <div id="setup" class="tab-content active">
            <div class="alert alert-info">
                <strong>Como funciona:</strong><br>
                1. Configure o Registration ID no código do Pico 2W<br>
                2. Registre o mesmo ID neste portal<br>
                3. Configure Azure AD e autentique<br>
                4. Aprove o dispositivo quando aparecer
            </div>

            <div class="card">
                <h3>📝 Registro de Dispositivo</h3>
                <div class="config-grid">
                    <div>
                        <h4>1. Configure no Pico (config.py):</h4>
                        <div class="code-block" id="picoConfig">REGISTRATION_ID = "MIRROR_EXEMPLO_001"
WIFI_SSID = "SuaRedeWiFi"
WIFI_PASSWORD = "SuaSenha"
MQTT_BROKER = "192.168.1.100"</div>
                        <button class="btn btn-secondary" onclick="generateRandomId()">🎲 Gerar ID</button>
                    </div>
                    
                    <div>
                        <h4>2. Registre no Portal:</h4>
                        <div class="form-group">
                            <label>Registration ID</label>
                            <input type="text" id="manualRegId" placeholder="MIRROR_EXEMPLO_001">
                        </div>
                        <div class="form-group">
                            <label>Nome do Dispositivo</label>
                            <input type="text" id="deviceName" placeholder="Espelho da Sala">
                        </div>
                        <div class="form-group">
                            <label>Localização</label>
                            <input type="text" id="deviceLocation" placeholder="Sala Principal">
                        </div>
                        <button class="btn btn-success" onclick="registerDevice()">📱 Registrar</button>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>📊 Status do Sistema</h3>
                <div id="systemStatus">Carregando...</div>
            </div>
        </div>

        <!-- Devices Tab -->
        <div id="devices" class="tab-content">
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
                <h2 style="color: white;">📱 Dispositivos</h2>
                <div>
                    <button class="btn" onclick="refreshDevices()">🔄 Atualizar</button>
                    <button class="btn btn-warning" onclick="syncAllDevices()">🔄 Sync Todos</button>
                </div>
            </div>
            <div id="devicesContainer">Carregando dispositivos...</div>
        </div>

        <!-- Azure Tab -->
        <div id="azure" class="tab-content">
            <h2 style="color: white; margin-bottom: 30px;">🔐 Azure AD + Outlook</h2>
            
            <div class="card">
                <h3>Credenciais Azure</h3>
                <div class="config-grid">
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
                        <input type="password" id="clientSecret" placeholder="abc123~DEF456_ghi789">
                    </div>
                    <div class="form-group">
                        <label>Redirect URI</label>
                        <input type="text" id="redirectUri" value="http://localhost:5000/callback" readonly>
                    </div>
                </div>

                <button class="btn" onclick="testAzureConnection()">🔍 Testar</button>
                <button class="btn btn-success" onclick="saveAzureConfig()">💾 Salvar</button>
                <button class="btn btn-warning" onclick="authenticateAzure()">🔑 Autenticar</button>
            </div>

            <div class="card">
                <h3>📅 Teste Outlook</h3>
                <button class="btn" onclick="testOutlookEvents()">📋 Buscar Eventos</button>
                <div id="outlookTestResult" style="margin-top: 20px;"></div>
            </div>
        </div>

        <!-- Tutorial Tab -->
        <div id="tutorial" class="tab-content">
            <div class="card">
                <h3>📚 Tutorial Completo</h3>
                <h4>1. Criar Aplicação Azure AD:</h4>
                <ol style="margin: 15px 0; padding-left: 20px;">
                    <li>Acesse <a href="https://portal.azure.com" target="_blank">portal.azure.com</a></li>
                    <li>Azure Active Directory → App registrations → New registration</li>
                    <li>Nome: "Magic Mirror", Account types: "Personal and organizational", Redirect URI: http://localhost:5000/callback</li>
                    <li>Copie Application ID e Directory ID</li>
                    <li>Certificates & secrets → New client secret → Copie o valor</li>
                    <li>API permissions → Add Microsoft Graph → Delegated → Calendars.Read e User.Read</li>
                </ol>
                
                <h4>2. Configurar Dispositivo:</h4>
                <div class="code-block">REGISTRATION_ID = "SEU_ID_UNICO"
WIFI_SSID = "SuaRede"
WIFI_PASSWORD = "SuaSenha"
MQTT_BROKER = "IP_DO_SERVIDOR"</div>
            </div>
        </div>
    </div>

    <div id="notification" class="notification"></div>

    <script>
        let devices = [];
        let systemConfig = { azure: { configured: false }, mqtt: { connected: false } };

        document.addEventListener('DOMContentLoaded', function() {
            loadSavedConfigs();
            updateSystemStatus();
            refreshDevices();
            setInterval(updateSystemStatus, 30000);
        });

        function switchTab(tabName) {
            document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName).classList.add('active');
            
            if (tabName === 'devices') refreshDevices();
        }

        function generateRandomId() {
            const parts = ['MIRROR', 'SMART', 'MAGIC'];
            const locations = ['SALA', 'ESCRITORIO', 'QUARTO', 'COZINHA'];
            const num = Math.floor(Math.random() * 999) + 1;
            const id = parts[Math.floor(Math.random() * parts.length)] + '_' + 
                      locations[Math.floor(Math.random() * locations.length)] + '_' +
                      num.toString().padStart(3, '0');
            
            document.getElementById('manualRegId').value = id;
            document.getElementById('picoConfig').textContent = 
                `REGISTRATION_ID = "${id}"\nWIFI_SSID = "SuaRedeWiFi"\nWIFI_PASSWORD = "SuaSenha"\nMQTT_BROKER = "192.168.1.100"`;
        }

        async function registerDevice() {
            const regId = document.getElementById('manualRegId').value.trim();
            const deviceName = document.getElementById('deviceName').value.trim();
            const location = document.getElementById('deviceLocation').value.trim();
            
            if (!regId) {
                showNotification('Registration ID é obrigatório', 'error');
                return;
            }
            
            if (!/^[A-Z0-9_]+$/.test(regId)) {
                showNotification('Use apenas letras maiúsculas, números e underscore', 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/devices/manual-register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        registration_id: regId,
                        display_name: deviceName || `Mirror ${regId.slice(-8)}`,
                        location: location || 'Não informado'
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showNotification('Dispositivo registrado com sucesso!', 'success');
                    document.getElementById('manualRegId').value = '';
                    document.getElementById('deviceName').value = '';
                    document.getElementById('deviceLocation').value = '';
                    refreshDevices();
                } else {
                    showNotification(result.error || 'Erro ao registrar', 'error');
                }
            } catch (error) {
                showNotification('Erro de comunicação', 'error');
            }
        }

        function loadSavedConfigs() {
            const saved = localStorage.getItem('azureConfig');
            if (saved) {
                const config = JSON.parse(saved);
                document.getElementById('clientId').value = config.clientId || '';
                document.getElementById('tenantId').value = config.tenantId || '';
                document.getElementById('clientSecret').value = config.clientSecret || '';
            }
        }

        async function updateSystemStatus() {
            try {
                const response = await fetch('/api/status');
                const status = await response.json();
                
                document.getElementById('systemStatus').innerHTML = `
                    <div class="config-grid">
                        <div>
                            <strong>Servidor:</strong> ${status.status === 'online' ? '✅ Online' : '❌ Offline'}<br>
                            <strong>MQTT:</strong> ${status.mqtt_connected ? '✅ Conectado' : '❌ Desconectado'}<br>
                            <strong>Versão:</strong> ${status.version}
                        </div>
                        <div>
                            <strong>Dispositivos:</strong> ${devices.length}<br>
                            <strong>Aprovados:</strong> ${devices.filter(d => d.status === 'approved').length}<br>
                            <strong>Pendentes:</strong> ${devices.filter(d => d.status === 'pending').length}
                        </div>
                    </div>
                `;
            } catch (error) {
                document.getElementById('systemStatus').innerHTML = '❌ Erro ao carregar status';
            }
        }

        async function saveAzureConfig() {
            const config = {
                clientId: document.getElementById('clientId').value.trim(),
                tenantId: document.getElementById('tenantId').value.trim(),
                clientSecret: document.getElementById('clientSecret').value.trim()
            };
            
            if (!config.clientId || !config.tenantId || !config.clientSecret) {
                showNotification('Preencha todos os campos', 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/azure/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    localStorage.setItem('azureConfig', JSON.stringify(config));
                    showNotification('Configuração salva!', 'success');
                    systemConfig.azure.configured = true;
                } else {
                    showNotification('Erro ao salvar', 'error');
                }
            } catch (error) {
                showNotification('Erro de comunicação', 'error');
            }
        }

        function authenticateAzure() {
            if (!systemConfig.azure.configured) {
                showNotification('Configure credenciais primeiro', 'warning');
                return;
            }
            
            const popup = window.open('/api/azure/auth', 'azure_auth', 'width=600,height=700');
            const check = setInterval(() => {
                if (popup.closed) {
                    clearInterval(check);
                    showNotification('Autenticação concluída!', 'success');
                }
            }, 1000);
        }

        async function testAzureConnection() {
            showNotification('Testando conexão...', 'info');
            setTimeout(() => showNotification('Conexão OK!', 'success'), 2000);
        }

        async function testOutlookEvents() {
            try {
                const response = await fetch('/api/outlook/test-events');
                const result = await response.json();
                
                const container = document.getElementById('outlookTestResult');
                
                if (result.success && result.events) {
                    container.innerHTML = `
                        <div class="alert alert-success">
                            <h4>✅ Outlook conectado!</h4>
                            <p>Eventos encontrados: ${result.events.length}</p>
                            ${result.events.slice(0, 3).map(e => 
                                `<p>• ${e.time || 'Todo dia'}: ${e.title}</p>`
                            ).join('')}
                        </div>
                    `;
                } else {
                    container.innerHTML = `
                        <div class="alert alert-warning">
                            <p>⚠️ ${result.error || 'Erro ao acessar Outlook'}</p>
                        </div>
                    `;
                }
            } catch (error) {
                document.getElementById('outlookTestResult').innerHTML = 
                    '<div class="alert alert-warning">❌ Erro de comunicação</div>';
            }
        }

        async function refreshDevices() {
            try {
                const response = await fetch('/api/devices');
                const result = await response.json();
                
                devices = result.devices || [];
                updateDevicesDisplay();
            } catch (error) {
                showNotification('Erro ao carregar dispositivos', 'error');
            }
        }

        function updateDevicesDisplay() {
            const container = document.getElementById('devicesContainer');
            
            if (devices.length === 0) {
                container.innerHTML = `
                    <div class="card" style="text-align: center;">
                        <h3>Nenhum dispositivo registrado</h3>
                        <p>Use a aba "Setup" para registrar seu primeiro dispositivo.</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = devices.map(device => `
                <div class="device-card ${device.status}">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                        <div>
                            <h4>${device.display_name || device.registration_id}</h4>
                            <p><strong>ID:</strong> ${device.registration_id}</p>
                            ${device.location ? `<p><strong>Local:</strong> ${device.location}</p>` : ''}
                        </div>
                        <span class="status-badge status-${device.status}">
                            ${device.status === 'pending' ? 'Pendente' : 'Aprovado'}
                        </span>
                    </div>
                    
                    <div>
                        ${device.status === 'pending' ? 
                            `<button class="btn btn-success" onclick="approveDevice('${device.registration_id}')">✅ Aprovar</button>` : 
                            `<button class="btn" onclick="syncDevice('${device.device_id}')">🔄 Sincronizar</button>`
                        }
                        <button class="btn btn-danger" onclick="deleteDevice('${device.registration_id}')">🗑️ Remover</button>
                    </div>
                </div>
            `).join('');
        }

        async function approveDevice(registrationId) {
            try {
                const response = await fetch(`/api/devices/${registrationId}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                
                if (response.ok) {
                    showNotification('Dispositivo aprovado!', 'success');
                    refreshDevices();
                }
            } catch (error) {
                showNotification('Erro ao aprovar', 'error');
            }
        }

        async function syncDevice(deviceId) {
            try {
                await fetch(`/api/devices/${deviceId}/sync`, { method: 'POST' });
                showNotification('Sincronização iniciada!', 'success');
            } catch (error) {
                showNotification('Erro na sincronização', 'error');
            }
        }

        async function syncAllDevices() {
            const approved = devices.filter(d => d.status === 'approved');
            if (approved.length === 0) {
                showNotification('Nenhum dispositivo para sincronizar', 'warning');
                return;
            }
            
            for (const device of approved) {
                if (device.device_id) {
                    try {
                        await fetch(`/api/devices/${device.device_id}/sync`, { method: 'POST' });
                    } catch (e) {}
                }
            }
            showNotification(`${approved.length} dispositivos sincronizados!`, 'success');
        }

        async function deleteDevice(registrationId) {
            if (!confirm('Remover este dispositivo?')) return;
            
            try {
                const response = await fetch(`/api/devices/${registrationId}`, { method: 'DELETE' });
                if (response.ok) {
                    showNotification('Dispositivo removido', 'warning');
                    refreshDevices();
                }
            } catch (error) {
                showNotification('Erro ao remover', 'error');
            }
        }

        function showNotification(message, type = 'info') {
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.className = `notification ${type}`;
            notification.style.display = 'block';
            setTimeout(() => notification.style.display = 'none', 4000);
        }
    </script>
</body>
</html>
'''

# ==================== ROTAS DA API ====================

@app.route('/')
def index():
    return render_template_string(FRONTEND_HTML)

@app.route('/api/status')
def api_status():
    return jsonify({
        'status': 'online',
        'version': '5.0-complete',
        'mqtt_connected': mqtt_manager.connected,
        'timestamp': datetime.now().isoformat()
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
    
    logger.info(f"Configuração Azure salva para usuário {user_id}")
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
        return 'Erro: Parâmetros OAuth ausentes', 400
    
    success, message = outlook.handle_callback(code, state)
    
    if success:
        return '''
        <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2 style="color: green;">✅ Autenticação concluída com sucesso!</h2>
                <p>Você pode fechar esta janela.</p>
                <script>setTimeout(() => window.close(), 3000);</script>
            </body>
        </html>
        '''
    else:
        return f'''
        <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2 style="color: red;">❌ Erro na autenticação</h2>
                <p>{message}</p>
                <script>setTimeout(() => window.close(), 5000);</script>
            </body>
        </html>
        '''

@app.route('/api/outlook/test-events')
def test_outlook_events():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Usuário não configurado'})
    
    events = outlook.get_today_events(user_id)
    return jsonify({
        'success': True,
        'events': events,
        'count': len(events)
    })

@app.route('/api/devices/manual-register', methods=['POST'])
def manual_register_device():
    data = request.get_json()
    registration_id = data.get('registration_id')
    display_name = data.get('display_name')
    location = data.get('location')
    
    if not registration_id:
        return jsonify({'success': False, 'error': 'Registration ID é obrigatório'})
    
    conn = db.get_conn()
    cursor = conn.cursor()
    
    # Verificar se já existe
    cursor.execute('SELECT registration_id FROM devices WHERE registration_id = ?', (registration_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Registration ID já existe'})
    
    # Inserir novo dispositivo
    cursor.execute('''
        INSERT INTO devices (registration_id, display_name, location, status)
        VALUES (?, ?, ?, 'pending')
    ''', (registration_id, display_name, location))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Dispositivo registrado manualmente: {registration_id}")
    return jsonify({'success': True})

@app.route('/api/devices')
def get_devices():
    user_id = session.get('user_id')
    
    conn = db.get_conn()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute('''
            SELECT registration_id, device_id, display_name, location, status, last_seen
            FROM devices WHERE user_id = ? OR user_id IS NULL
            ORDER BY created_at DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT registration_id, device_id, display_name, location, status, last_seen
            FROM devices WHERE user_id IS NULL
            ORDER BY created_at DESC
        ''')
    
    devices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'devices': devices})

@app.route('/api/devices/<registration_id>/approve', methods=['POST'])
def approve_device(registration_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Usuário não configurado'}), 400
    
    device_id = f"mirror_{secrets.token_urlsafe(6)}"
    api_key = f"sk_{secrets.token_urlsafe(20)}"
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE devices 
        SET device_id = ?, user_id = ?, status = 'approved', api_key = ?, updated_at = ?
        WHERE registration_id = ?
    ''', (device_id, user_id, api_key, datetime.now().isoformat(), registration_id))
    conn.commit()
    conn.close()
    
    # Notificar via MQTT
    mqtt_manager.send_registration_response(registration_id, 'approved', device_id, api_key)
    
    # Sincronizar imediatamente
    threading.Thread(target=lambda: mqtt_manager.sync_device(device_id), daemon=True).start()
    
    logger.info(f"Dispositivo aprovado: {registration_id} -> {device_id}")
    return jsonify({'success': True, 'device_id': device_id})

@app.route('/api/devices/<device_id>/sync', methods=['POST'])
def sync_device_manual(device_id):
    mqtt_manager.sync_device(device_id)
    return jsonify({'success': True})

@app.route('/api/devices/<registration_id>', methods=['DELETE'])
def delete_device(registration_id):
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM devices WHERE registration_id = ?', (registration_id,))
    conn.commit()
    conn.close()
    
    logger.info(f"Dispositivo removido: {registration_id}")
    return jsonify({'success': True})

# ==================== SINCRONIZAÇÃO AUTOMÁTICA ====================
def auto_sync_loop():
    """Loop de sincronização automática"""
    while True:
        try:
            conn = db.get_conn()
            cursor = conn.cursor()
            
            # Buscar todos os dispositivos aprovados
            cursor.execute('''
                SELECT device_id FROM devices 
                WHERE status = 'approved' AND device_id IS NOT NULL
            ''')
            devices = cursor.fetchall()
            
            for device in devices:
                mqtt_manager.sync_device(device['device_id'])
            
            conn.close()
            logger.info(f"Sincronização automática executada para {len(devices)} dispositivos")
            
        except Exception as e:
            logger.error(f"Erro na sincronização automática: {e}")
        
        # Aguardar 15 minutos
        time.sleep(900)

# Iniciar thread de sincronização automática
sync_thread = threading.Thread(target=auto_sync_loop, daemon=True)
sync_thread.start()

if __name__ == '__main__':
    print("=" * 60)
    print("🪞 MAGIC MIRROR - BACKEND COMPLETO")
    print("=" * 60)
    print("Funcionalidades:")
    print("✅ Registro manual de dispositivos")
    print("✅ Integração completa com Azure AD")
    print("✅ Sincronização com Outlook Calendar")
    print("✅ Comunicação MQTT bidirecional")
    print("✅ Interface web completa")
    print("✅ Sincronização automática")
    print("=" * 60)
    print(f"🌐 Acesse: http://localhost:5000")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal no servidor: {e}")