#!/usr/bin/env python3
"""
Magic Mirror - Main com MQTT Público
Conecta automaticamente sem configurar IP!
"""

import machine
import utime
import json
import network
import gc
from machine import Pin, SPI, PWM

from config import *

try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("ERRO: MQTT não disponível")

# ==================== DISPLAY ====================
class Display:
    def __init__(self):
        self.init_hardware()
        self.clear()
        self.show_startup()
    
    def init_hardware(self):
        try:
            self.spi = SPI(0, baudrate=40000000, sck=Pin(DISPLAY_PINS['SCK']), mosi=Pin(DISPLAY_PINS['MOSI']))
            self.cs = Pin(DISPLAY_PINS['CS'], Pin.OUT)
            self.dc = Pin(DISPLAY_PINS['DC'], Pin.OUT)
            self.rst = Pin(DISPLAY_PINS['RST'], Pin.OUT)
            self.bl = PWM(Pin(DISPLAY_PINS['BL']))
            
            self.rst.value(0)
            utime.sleep_ms(100)
            self.rst.value(1)
            
            self.bl.freq(1000)
            self.set_brightness(DISPLAY_BRIGHTNESS)
            print("Display inicializado")
        except Exception as e:
            print(f"Erro display: {e}")
    
    def set_brightness(self, percent):
        duty = int((percent / 100) * 65535)
        self.bl.duty_u16(duty)
    
    def clear(self):
        if is_debug():
            print("DISPLAY: Tela limpa")
    
    def show_text(self, text, x=10, y=50):
        if is_debug():
            print(f"DISPLAY: '{text}' em ({x},{y})")
    
    def show_startup(self):
        self.clear()
        self.show_text("MAGIC MIRROR", 100, 50)
        self.show_text(f"ID: {REGISTRATION_ID}", 100, 80)
        self.show_text("Conectando MQTT publico...", 100, 110)
    
    def show_status(self, status):
        self.clear()
        self.show_text("MAGIC MIRROR", 100, 30)
        self.show_text(f"Status: {status}", 100, 70)
    
    def show_events(self, events):
        self.clear()
        self.show_text("EVENTOS DE HOJE", 100, 30)
        
        if not events:
            self.show_text("Nenhum evento", 100, 80)
            return
        
        y = 70
        for i, event in enumerate(events[:MAX_EVENTS_DISPLAY]):
            time_str = event.get('time', 'Todo dia')
            title = event.get('title', 'Sem título')[:30]
            text = f"{time_str}: {title}"
            self.show_text(text, 20, y)
            y += 30

# ==================== WIFI ====================
class WiFi:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.connected = False
    
    def connect(self):
        self.wlan.active(True)
        
        if self.wlan.isconnected():
            self.connected = True
            return True
        
        print(f"Conectando WiFi: {WIFI_SSID}")
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                
                timeout = 0
                while not self.wlan.isconnected() and timeout < CONNECTION_TIMEOUT:
                    utime.sleep(1)
                    timeout += 1
                
                if self.wlan.isconnected():
                    ip = self.wlan.ifconfig()[0]
                    print(f"WiFi conectado: {ip}")
                    self.connected = True
                    return True
                    
            except Exception as e:
                print(f"Erro WiFi: {e}")
        
        print("Falha no WiFi")
        return False

# ==================== MQTT PÚBLICO ====================
class MQTTPublic:
    def __init__(self, display):
        self.display = display
        self.client = None
        self.connected = False
        self.registered = False
        self.device_id = None
        self.topic_prefix = None  # Recebido do servidor
        
    def connect(self):
        if not MQTT_AVAILABLE:
            return False
        
        try:
            client_id = f"pico_{machine.unique_id().hex()[:8]}"
            self.client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
            self.client.set_callback(self.on_message)
            self.client.connect()
            
            self.connected = True
            print(f"MQTT público conectado: {MQTT_BROKER}")
            
            # Subscrever primeiro ao tópico de descoberta
            discovery_topic = f"magic_mirror_+/registration"
            # Como não sabemos o prefixo ainda, vamos tentar descobrir
            # Por enquanto, mandamos um broadcast para todos os prefixos possíveis
            self.discover_server()
            
            return True
            
        except Exception as e:
            print(f"Erro MQTT: {e}")
            return False
    
    def discover_server(self):
        """Tenta descobrir servidor ativo enviando ping"""
        if not self.connected:
            return
        
        # Envia descoberta para um tópico genérico
        discovery_data = {
            'action': 'discover',
            'registration_id': REGISTRATION_ID,
            'timestamp': utime.time()
        }
        
        # Publica em tópico de descoberta geral
        discovery_topic = f"magic_mirror_discovery/{REGISTRATION_ID}"
        self.client.publish(discovery_topic, json.dumps(discovery_data))
        print(f"Enviando descoberta: {discovery_topic}")
        
        # Subscreve para receber resposta
        self.client.subscribe(f"magic_mirror_discovery/{REGISTRATION_ID}/response")
    
    def send_registration(self):
        if not self.connected or not self.topic_prefix:
            return
        
        data = {
            'registration_id': REGISTRATION_ID,
            'firmware_version': FIRMWARE_VERSION,
            'timestamp': utime.time()
        }
        
        topic = f"{self.topic_prefix}/registration"
        self.client.publish(topic, json.dumps(data))
        print(f"Registro enviado: {topic}")
    
    def on_message(self, client, userdata, msg):
        try:
            topic_str = msg.topic.decode()
            payload = json.loads(msg.payload.decode())
            
            print(f"MQTT recebido: {topic_str}")
            
            if topic_str.endswith("/discovery/response"):
                self.handle_discovery_response(payload)
            elif topic_str.endswith("/registration"):
                self.handle_registration(payload)
            elif topic_str.endswith("/events"):
                self.handle_events(payload)
                
        except Exception as e:
            print(f"Erro processar MQTT: {e}")
    
    def handle_discovery_response(self, payload):
        """Recebe informações do servidor para conectar"""
        if payload.get('registration_id') != REGISTRATION_ID:
            return
        
        # Recebe o topic_prefix do servidor
        self.topic_prefix = payload.get('topic_prefix')
        if self.topic_prefix:
            print(f"Servidor descoberto! Topic: {self.topic_prefix}")
            
            # Agora subscreve aos tópicos corretos
            self.client.subscribe(f"{self.topic_prefix}/registration")
            
            # Envia registro
            self.send_registration()
    
    def handle_registration(self, payload):
        if payload.get('registration_id') != REGISTRATION_ID:
            return
        
        status = payload.get('status')
        
        if status == 'approved':
            self.device_id = payload.get('device_id')
            self.registered = True
            
            # Subscrever aos eventos
            if self.device_id:
                self.client.subscribe(f"{self.topic_prefix}/devices/{self.device_id}/events")
            
            print(f"Dispositivo aprovado: {self.device_id}")
            self.display.show_status("Aprovado - Aguardando eventos")
            
        elif status == 'pending':
            print("Aguardando aprovação")
            self.display.show_status("Aguardando aprovação no servidor")
    
    def handle_events(self, payload):
        events = payload.get('events', [])
        count = len(events)
        
        print(f"Eventos recebidos: {count}")
        self.display.show_events(events)
    
    def check_messages(self):
        if self.connected and self.client:
            try:
                self.client.check_msg()
                return True
            except:
                self.connected = False
                return False
        return False

# ==================== APLICAÇÃO PRINCIPAL ====================
class MagicMirror:
    def __init__(self):
        print("Iniciando Magic Mirror - MQTT Público")
        
        # Validar configuração
        issues = validate_config()
        if issues:
            print("ERROS DE CONFIGURAÇÃO:")
            for issue in issues:
                print(f"  - {issue}")
            return
        
        # Componentes
        self.display = Display()
        self.wifi = WiFi()
        self.mqtt = None
        self.running = True
    
    def run(self):
        # Conectar WiFi
        if not self.wifi.connect():
            self.display.show_status("ERRO: WiFi falhou")
            return
        
        # Conectar MQTT Público
        self.mqtt = MQTTPublic(self.display)
        if not self.mqtt.connect():
            self.display.show_status("ERRO: MQTT falhou")
            return
        
        self.display.show_status("Descobrindo servidor...")
        
        # Loop principal
        last_check = 0
        discovery_attempts = 0
        
        while self.running:
            try:
                current_time = utime.time()
                
                # Verificar mensagens MQTT
                if not self.mqtt.check_messages():
                    print("MQTT desconectado - reconectando")
                    self.mqtt.connect()
                
                # Reenviar descoberta se não encontrou servidor (a cada 30s)
                if not self.mqtt.topic_prefix and (current_time - last_check) > 30:
                    discovery_attempts += 1
                    print(f"Tentativa descoberta #{discovery_attempts}")
                    self.mqtt.discover_server()
                    last_check = current_time
                
                # Reenviar registro se não aprovado (a cada 30s)
                elif self.mqtt.topic_prefix and not self.mqtt.registered and (current_time - last_check) > 30:
                    self.mqtt.send_registration()
                    last_check = current_time
                
                # Coleta de lixo
                if current_time % 60 == 0:
                    gc.collect()
                
                utime.sleep(1)
                
            except KeyboardInterrupt:
                print("Parando aplicação")
                self.running = False
                break
                
            except Exception as e:
                print(f"Erro no loop: {e}")
                utime.sleep(5)

def main():
    try:
        app = MagicMirror()
        app.run()
    except Exception as e:
        print(f"Erro crítico: {e}")
        utime.sleep(10)
        machine.reset()

if __name__ == "__main__":
    main()