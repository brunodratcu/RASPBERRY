#!/usr/bin/env python3
"""
Magic Mirror - Raspberry Pico 2W - VERSÃO CORRIGIDA
Sistema de relógio com sincronização MQTT e eventos do Outlook
Correções: Topic prefix dinâmico e sincronização adequada
"""

import machine
import utime
import network
import gc
import json
import ubinascii
from machine import Pin, RTC

# Importar configurações
try:
    from config import *
except ImportError:
    pass

# Definir todas as variáveis obrigatórias
if 'WIFI_SSID' not in globals():
    WIFI_SSID = "SuaRedeWiFi"
if 'WIFI_PASSWORD' not in globals():
    WIFI_PASSWORD = "SuaSenha"
if 'TIMEZONE_OFFSET' not in globals():
    TIMEZONE_OFFSET = -3
if 'DISPLAY_WIDTH' not in globals():
    DISPLAY_WIDTH = 480
if 'DISPLAY_HEIGHT' not in globals():
    DISPLAY_HEIGHT = 320
if 'MQTT_BROKER' not in globals():
    MQTT_BROKER = "test.mosquitto.org"
if 'MQTT_PORT' not in globals():
    MQTT_PORT = 1883
if 'TOPIC_PREFIX' not in globals():
    TOPIC_PREFIX = "magic_mirror_default"

# Importar MQTT
try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("AVISO: umqtt.simple não encontrado")

# Importar NTP
try:
    import ntptime
    NTP_AVAILABLE = True
except ImportError:
    NTP_AVAILABLE = False

# Importar fontes (mesmo código anterior)
try:
    from font import FONT_8X8, get_char_bitmap
except ImportError:
    FONT_8X8 = {
        '0': [0x3C, 0x66, 0x6E, 0x7E, 0x76, 0x66, 0x3C, 0x00],
        '1': [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x7E, 0x00],
        '2': [0x3C, 0x66, 0x06, 0x1C, 0x30, 0x60, 0x7E, 0x00],
        '3': [0x3C, 0x66, 0x06, 0x1C, 0x06, 0x66, 0x3C, 0x00],
        '4': [0x0E, 0x1E, 0x36, 0x66, 0x7F, 0x06, 0x06, 0x00],
        '5': [0x7E, 0x60, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
        '6': [0x1C, 0x30, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
        '7': [0x7E, 0x06, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x00],
        '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
        '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x0C, 0x38, 0x00],
        ':': [0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00, 0x00],
        '/': [0x00, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x00, 0x00],
        ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
        'A': [0x18, 0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x00],
        'G': [0x3C, 0x66, 0x60, 0x6E, 0x66, 0x66, 0x3C, 0x00],
        'I': [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
        'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
        'R': [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
        'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
        'H': [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
        'S': [0x3E, 0x60, 0x60, 0x3E, 0x06, 0x06, 0x7C, 0x00],
        'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
        'E': [0x7E, 0x60, 0x60, 0x7C, 0x60, 0x60, 0x7E, 0x00],
        'N': [0x66, 0x76, 0x7E, 0x7E, 0x6E, 0x66, 0x66, 0x00],
        'D': [0x7C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x00],
        'L': [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
        'Z': [0x7E, 0x0E, 0x1C, 0x38, 0x70, 0x60, 0x7E, 0x00],
        '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    }
    
    def get_char_bitmap(char):
        return FONT_8X8.get(char, FONT_8X8[' '])

# Hardware - Pinos do display
rst = Pin(16, Pin.OUT, value=1)
cs = Pin(17, Pin.OUT, value=1) 
rs = Pin(15, Pin.OUT, value=0)
wr = Pin(19, Pin.OUT, value=1)
rd = Pin(18, Pin.OUT, value=1)
data_pins = [Pin(i, Pin.OUT) for i in range(8)]

# RTC
rtc = RTC()

# Cores
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
CYAN = 0x07FF
YELLOW = 0xFFE0
ORANGE = 0xFD20

# ==================== UTILITÁRIOS ====================
def get_unique_device_id():
    """Gerar ID único baseado na MAC address"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        mac = wlan.config('mac')
        mac_str = ubinascii.hexlify(mac).decode()[-6:]
        return f"PICO_{mac_str.upper()}"
    except:
        return f"PICO_{utime.ticks_ms() % 100000}"

# ==================== DISPLAY (mesmo código anterior) ====================
def write_byte(data):
    for i in range(8):
        data_pins[i].value((data >> i) & 1)

def cmd(c):
    cs.value(0)
    rs.value(0)
    write_byte(c)
    wr.value(0)
    wr.value(1)
    cs.value(1)

def dat(d):
    cs.value(0)
    rs.value(1)
    write_byte(d)
    wr.value(0)
    wr.value(1)
    cs.value(1)

def init_display():
    rst.value(0)
    utime.sleep_ms(50)
    rst.value(1)
    utime.sleep_ms(50)
    
    cmd(0x01); utime.sleep_ms(100)
    cmd(0x11); utime.sleep_ms(100)
    cmd(0x3A); dat(0x55)
    cmd(0x36); dat(0xE8)
    cmd(0x29); utime.sleep_ms(50)
    return True

def set_area(x0, y0, x1, y1):
    cmd(0x2A)
    dat(x0>>8); dat(x0&0xFF); dat(x1>>8); dat(x1&0xFF)
    cmd(0x2B) 
    dat(y0>>8); dat(y0&0xFF); dat(y1>>8); dat(y1&0xFF)
    cmd(0x2C)

def fill_rect(x, y, w, h, color):
    if w <= 0 or h <= 0: return
    set_area(x, y, x+w-1, y+h-1)
    ch, cl = color >> 8, color & 0xFF
    cs.value(0); rs.value(1)
    for _ in range(w*h):
        write_byte(ch); wr.value(0); wr.value(1)
        write_byte(cl); wr.value(0); wr.value(1)
    cs.value(1)

def clear_screen(color=BLACK):
    fill_rect(0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT, color)

def draw_char(x, y, char, color, size=1):
    try:
        bitmap = get_char_bitmap(char)
    except:
        if char not in FONT_8X8: 
            char = ' '
        bitmap = FONT_8X8[char]
    
    for row in range(8):
        byte = bitmap[row]
        for col in range(8):
            px = x + col * size
            py = y + row * size
            pixel_color = color if (byte & (0x80 >> col)) else BLACK
            if px < DISPLAY_WIDTH and py < DISPLAY_HEIGHT:
                fill_rect(px, py, size, size, pixel_color)

def draw_text(x, y, text, color, size=1):
    char_width = 8 * size
    char_spacing = 2 * size
    
    for i, char in enumerate(str(text)):
        char_x = x + i * (char_width + char_spacing)
        if char_x < DISPLAY_WIDTH - char_width:
            draw_char(char_x, y, char.upper(), color, size)

def draw_centered(y, text, color, size=1):
    char_width = 8 * size
    char_spacing = 2 * size
    text_width = len(str(text)) * char_width + (len(str(text)) - 1) * char_spacing
    x = max(0, (DISPLAY_WIDTH - text_width) // 2)
    draw_text(x, y, text, color, size)

# ==================== REDE ====================
class NetworkManager:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.connected = False
        self.ip_address = None
        self.ntp_synced = False
        
    def connect_wifi(self, ssid, password, timeout=20):
        print(f"Conectando WiFi: {ssid}")
        self.wlan.active(True)
        
        if self.wlan.isconnected():
            self.connected = True
            self.ip_address = self.wlan.ifconfig()[0]
            print(f"WiFi já conectado: {self.ip_address}")
            return True
        
        try:
            self.wlan.connect(ssid, password)
            
            for i in range(timeout):
                if self.wlan.isconnected():
                    self.connected = True
                    self.ip_address = self.wlan.ifconfig()[0]
                    print(f"WiFi conectado: {self.ip_address}")
                    return True
                utime.sleep(1)
            
            print("Timeout WiFi")
            return False
            
        except Exception as e:
            print(f"Erro WiFi: {e}")
            return False
    
    def sync_ntp_brasilia(self):
        if not self.connected or not NTP_AVAILABLE:
            return False
        
        ntp_servers = ["a.ntp.br", "pool.ntp.br", "time.cloudflare.com"]
        
        for server in ntp_servers:
            try:
                print(f"Sincronizando NTP: {server}")
                ntptime.host = server
                ntptime.settime()
                
                utc_timestamp = utime.time()
                brasilia_timestamp = utc_timestamp + (TIMEZONE_OFFSET * 3600)
                brasilia_time = utime.localtime(brasilia_timestamp)
                
                rtc.datetime((
                    brasilia_time[0], brasilia_time[1], brasilia_time[2], 
                    brasilia_time[6], brasilia_time[3], brasilia_time[4], 
                    brasilia_time[5], 0
                ))
                
                self.ntp_synced = True
                current = rtc.datetime()
                print(f"Horário sincronizado: {current[2]:02d}/{current[1]:02d}/{current[0]} {current[4]:02d}:{current[5]:02d}")
                return True
                
            except Exception as e:
                print(f"Falha NTP {server}: {e}")
                continue
        
        print("Todos servidores NTP falharam")
        return False

# ==================== MQTT CORRIGIDO ====================
class MQTTHandler:
    def __init__(self, device_id, initial_topic_prefix):
        self.device_id = device_id
        self.registration_id = device_id  # ID usado para registro inicial
        self.initial_topic_prefix = initial_topic_prefix
        self.current_topic_prefix = initial_topic_prefix
        self.assigned_device_id = None  # ID atribuído pelo servidor
        self.client = None
        self.connected = False
        self.approved = False
        self.last_ping = 0
        self.events = []
        self.last_registration_attempt = 0
        
    def connect(self, network_manager):
        if not MQTT_AVAILABLE or not network_manager.connected:
            print("MQTT não disponível ou WiFi desconectado")
            return False
            
        try:
            print(f"Conectando MQTT: {MQTT_BROKER}:{MQTT_PORT}")
            print(f"Device ID inicial: {self.device_id}")
            print(f"Topic Prefix inicial: {self.initial_topic_prefix}")
            
            client_id = f"{self.device_id}_{utime.ticks_ms()}"
            self.client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
            self.client.set_callback(self.on_message)
            self.client.connect()
            
            # Subscrever ao tópico de registro inicial
            registration_topic = f"{self.initial_topic_prefix}/registration"
            self.client.subscribe(registration_topic)
            print(f"Subscrito em: {registration_topic}")
            
            self.connected = True
            self.last_ping = utime.ticks_ms()
            
            print("MQTT conectado - enviando registro")
            self.send_registration()
            return True
            
        except Exception as e:
            print(f"Erro MQTT: {e}")
            self.connected = False
            return False
    
    def on_message(self, topic, msg):
        try:
            topic_str = topic.decode()
            msg_str = msg.decode()
            
            print(f"=== MQTT RECEBIDO ===")
            print(f"Topic: {topic_str}")
            print(f"Tamanho mensagem: {len(msg_str)} bytes")
            
            data = json.loads(msg_str)
            
            # Processar resposta de registro
            if "/registration" in topic_str:
                self.handle_registration_response(data)
            
            # Processar eventos
            elif "/events" in topic_str:
                print("Processando eventos...")
                self.events = data.get('events', [])
                self.events.sort(key=lambda x: x.get('time', '23:59'))
                print(f"✅ {len(self.events)} eventos recebidos e ordenados")
                
                # Debug dos eventos recebidos
                for i, event in enumerate(self.events[:3]):
                    time_str = event.get('time', 'Todo dia')
                    title = event.get('title', 'Sem título')
                    print(f"  {i+1}. {time_str} - {title}")
                    
            print("==================")
                    
        except Exception as e:
            print(f"Erro processando MQTT: {e}")
    
    def handle_registration_response(self, data):
        """Processar resposta do servidor para registro"""
        status = data.get('status', '')
        reg_id = data.get('registration_id', '')
        
        # Verificar se a resposta é para este dispositivo
        if reg_id != self.registration_id:
            return
        
        print(f"Status de registro: {status}")
        
        if status == 'approved':
            # Dispositivo aprovado!
            self.approved = True
            self.assigned_device_id = data.get('device_id')
            new_topic_prefix = data.get('topic_prefix')
            
            if new_topic_prefix and self.assigned_device_id:
                print(f"✅ APROVADO!")
                print(f"Novo device ID: {self.assigned_device_id}")
                print(f"Topic prefix: {new_topic_prefix}")
                
                # Atualizar configurações
                self.current_topic_prefix = new_topic_prefix
                
                # Subscrever ao tópico de eventos específico
                events_topic = f"{new_topic_prefix}/devices/{self.assigned_device_id}/events"
                self.client.subscribe(events_topic)
                print(f"Subscrito em eventos: {events_topic}")
                
                # Se houver tópico de eventos na resposta, subscrever também
                events_topic_from_response = data.get('events_topic')
                if events_topic_from_response and events_topic_from_response != events_topic:
                    self.client.subscribe(events_topic_from_response)
                    print(f"Subscrito adicional: {events_topic_from_response}")
        
        elif status == 'pending':
            print("⏳ Dispositivo em aprovação pendente")
        
        else:
            print(f"❌ Status desconhecido: {status}")
    
    def send_registration(self):
        """Enviar pedido de registro"""
        if not self.connected:
            return
            
        # Evitar spam de registros
        now = utime.ticks_ms()
        if utime.ticks_diff(now, self.last_registration_attempt) < 5000:  # 5 segundos
            return
        
        try:
            registration_data = {
                'registration_id': self.registration_id,
                'device_info': f'Pico 2W Magic Mirror',
                'timestamp': utime.time(),
                'type': 'pico_2w',
                'mac_address': ubinascii.hexlify(network.WLAN().config('mac')).decode()
            }
            
            topic = f"{self.current_topic_prefix}/registration"
            message = json.dumps(registration_data)
            self.client.publish(topic, message)
            
            self.last_registration_attempt = now
            print(f"Registro enviado para: {topic}")
            
        except Exception as e:
            print(f"Erro enviando registro: {e}")
    
    def check_messages(self):
        if not self.connected or not self.client:
            return
            
        try:
            # Verificar mensagens
            self.client.check_msg()
            
            # Ping periódico
            now = utime.ticks_ms()
            if utime.ticks_diff(now, self.last_ping) > 30000:  # 30 segundos
                self.client.ping()
                self.last_ping = now
            
            # Re-enviar registro se ainda não aprovado
            if not self.approved and utime.ticks_diff(now, self.last_registration_attempt) > 30000:  # 30 segundos
                print("Re-enviando registro (ainda não aprovado)")
                self.send_registration()
                
        except Exception as e:
            print(f"Erro MQTT check: {e}")
            self.connected = False
    
    def get_events(self):
        return self.events
    
    def is_approved(self):
        return self.approved

# ==================== CLASSE PRINCIPAL ====================
class MagicMirror:
    def __init__(self):
        self.network_manager = NetworkManager()
        self.mqtt_handler = None
        
        # Gerar device ID único
        self.unique_device_id = get_unique_device_id()
        print(f"🆔 Device ID único: {self.unique_device_id}")
        
        # Estado anterior para otimização
        self.last_display = {
            'h1': None, 'h2': None, 'm1': None, 'm2': None, 
            's1': None, 's2': None, 'date': None, 'status': None, 'events': None
        }
        
        # Posições dos dígitos
        self.positions = {
            'h1': (100, 60), 'h2': (140, 60),
            'm1': (200, 60), 'm2': (240, 60),
            's1': (300, 60), 's2': (340, 60),
        }
        
        self.init_system()
    
    def init_system(self):
        print("Inicializando Magic Mirror...")
        
        # Display
        init_display()
        self.show_splash_screen()
        
        # WiFi
        wifi_success = self.network_manager.connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        if wifi_success:
            # NTP
            ntp_success = self.network_manager.sync_ntp_brasilia()
            if not ntp_success:
                rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))
            
            # MQTT
            self.mqtt_handler = MQTTHandler(self.unique_device_id, TOPIC_PREFIX)
            mqtt_success = self.mqtt_handler.connect(self.network_manager)
            
            if mqtt_success:
                self.show_connection_status("CONECTADO - AGUARDANDO APROVACAO", YELLOW)
            else:
                self.show_connection_status("MQTT FALHOU", RED)
        else:
            rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))
            self.show_connection_status("WIFI FALHOU", RED)
        
        utime.sleep(3)
        self.setup_main_screen()
    
    def show_splash_screen(self):
        clear_screen(BLACK)
        draw_centered(80, "MAGIC MIRROR", WHITE, 3)
        draw_centered(120, "PICO 2W v2.0", CYAN, 2)
        draw_centered(150, f"ID: {self.unique_device_id}", YELLOW, 1)
        draw_centered(180, "INICIALIZANDO...", WHITE, 1)
    
    def show_connection_status(self, message, color):
        fill_rect(0, 200, DISPLAY_WIDTH, 30, BLACK)
        draw_centered(210, message, color, 1)
    
    def setup_main_screen(self):
        clear_screen(BLACK)
        
        # Desenhar separadores do relógio
        draw_text(180, 60, ":", WHITE, 4)
        draw_text(280, 60, ":", WHITE, 4)
        
        # Limpar cache de display
        for key in self.last_display:
            self.last_display[key] = None
    
    def update_single_digit(self, position_key, new_digit):
        if self.last_display[position_key] != new_digit:
            x, y = self.positions[position_key]
            fill_rect(x, y, 32, 32, BLACK)
            draw_char(x, y, new_digit, WHITE, 4)
            self.last_display[position_key] = new_digit
    
    def update_events(self):
        if not self.mqtt_handler:
            return
            
        events = self.mqtt_handler.get_events()
        events_start_y = 170
        events_area_height = 120
        line_height = 18
        max_events = min(6, events_area_height // line_height)  # Máximo 6 eventos
        
        # Preparar lista de eventos para exibição
        events_display = []
        for i, event in enumerate(events[:max_events]):
            time_str = event.get('time', '').strip()
            title = event.get('title', 'Evento sem título').strip()
            
            # Limitar tamanho do título
            if len(title) > 35:
                title = title[:32] + "..."
            
            if time_str:
                display_text = f"{time_str} {title}"
            else:
                display_text = f"Dia todo: {title}"
                
            events_display.append(display_text)
        
        # Comparar com exibição anterior
        current_events_text = "\n".join(events_display)
        if self.last_display['events'] != current_events_text:
            print(f"🔄 Atualizando display de eventos ({len(events_display)} eventos)")
            
            # Limpar área de eventos
            fill_rect(0, events_start_y, DISPLAY_WIDTH, events_area_height, BLACK)
            
            if events_display:
                # Cabeçalho
                draw_text(10, events_start_y, "EVENTOS DE HOJE:", YELLOW, 1)
                
                # Listar eventos
                for i, event_text in enumerate(events_display):
                    y_pos = events_start_y + 15 + (i * line_height)
                    color = WHITE if i % 2 == 0 else CYAN
                    
                    # Garantir que não ultrapasse a tela
                    if y_pos + 8 < events_start_y + events_area_height:
                        draw_text(10, y_pos, event_text, color, 1)
            else:
                # Nenhum evento
                draw_text(10, events_start_y, "NENHUM EVENTO HOJE", ORANGE, 1)
            
            self.last_display['events'] = current_events_text
            print("✅ Display de eventos atualizado")
    
    def update_clock(self):
        current = rtc.datetime()
        h, m, s = current[4], current[5], current[6]
        d, month, y = current[2], current[1], current[0]
        
        # Dígitos do relógio
        h1, h2 = f"{h:02d}"[0], f"{h:02d}"[1]
        m1, m2 = f"{m:02d}"[0], f"{m:02d}"[1]  
        s1, s2 = f"{s:02d}"[0], f"{s:02d}"[1]
        
        self.update_single_digit('h1', h1)
        self.update_single_digit('h2', h2)
        self.update_single_digit('m1', m1)
        self.update_single_digit('m2', m2)
        self.update_single_digit('s1', s1)
        self.update_single_digit('s2', s2)
        
        # Data
        date_str = f"{d:02d}/{month:02d}/{y}"
        if self.last_display['date'] != date_str:
            fill_rect(0, 120, DISPLAY_WIDTH, 30, BLACK)
            draw_centered(125, date_str, CYAN, 2)
            self.last_display['date'] = date_str
        
        # Status de conexão
        self.update_connection_status()
    
    def update_connection_status(self):
        network_connected = self.network_manager.connected
        mqtt_connected = self.mqtt_handler and self.mqtt_handler.connected
        mqtt_approved = self.mqtt_handler and self.mqtt_handler.is_approved()
        
        if network_connected and mqtt_connected and mqtt_approved:
            status_text = "SINCRONIZADO"
            status_color = GREEN
        elif network_connected and mqtt_connected:
            status_text = "AGUARDANDO APROVACAO"
            status_color = YELLOW
        elif network_connected:
            status_text = "WIFI - SEM MQTT"
            status_color = ORANGE
        else:
            status_text = "DESCONECTADO"
            status_color = RED
        
        if self.last_display['status'] != (status_text, status_color):
            fill_rect(0, 295, DISPLAY_WIDTH, 20, BLACK)
            draw_centered(300, status_text, status_color, 1)
            self.last_display['status'] = (status_text, status_color)
    
    def run(self):
        sync_counter = 0
        event_check_counter = 0
        
        print("🚀 Iniciando loop principal...")
        
        while True:
            try:
                # Verificar mensagens MQTT
                if self.mqtt_handler:
                    self.mqtt_handler.check_messages()
                
                # Atualizar relógio (sempre)
                self.update_clock()
                
                # Atualizar eventos (menos frequente para economizar recursos)
                event_check_counter += 1
                if event_check_counter >= 10:  # A cada 5 segundos (10 * 500ms)
                    self.update_events()
                    event_check_counter = 0
                
                # Re-sincronizar NTP a cada hora
                sync_counter += 1
                if sync_counter >= 7200:  # 1 hora em ciclos de 500ms
                    if self.network_manager.connected:
                        print("🕐 Re-sincronizando NTP...")
                        self.network_manager.sync_ntp_brasilia()
                    sync_counter = 0
                
                # Garbage collection periódico
                if sync_counter % 240 == 0:  # A cada 2 minutos
                    gc.collect()
                    
                    # Log de status a cada 2 minutos
                    if self.mqtt_handler:
                        events_count = len(self.mqtt_handler.get_events())
                        approved = self.mqtt_handler.is_approved()
                        print(f"📊 Status: {events_count} eventos | Aprovado: {approved}")
                
                utime.sleep_ms(500)
                
            except KeyboardInterrupt:
                print("🛑 Interrompido pelo usuário")
                break
            except Exception as e:
                print(f"❌ Erro no loop principal: {e}")
                utime.sleep(2)  # Pausa maior em caso de erro

# ==================== EXECUÇÃO ====================
def main():
    print("=" * 50)
    print("🪐 MAGIC MIRROR - PICO 2W v2.0")
    print("Sistema corrigido com MQTT dinâmico")
    print("=" * 50)
    
    try:
        mirror = MagicMirror()
        mirror.run()
    except Exception as e:
        print(f"❌ Erro fatal: {e}")
        try:
            # Tentar mostrar erro no display
            clear_screen(BLACK)
            draw_centered(100, "ERRO FATAL", RED, 3)
            draw_centered(140, "VERIFIQUE CONSOLE", WHITE, 1)
            draw_centered(160, str(e)[:30], YELLOW, 1)
            
            while True:
                utime.sleep(10)
        except:
            # Se nem o display funcionar
            print("💀 Erro crítico - sistema parado")
            while True:
                utime.sleep(10)

if __name__ == "__main__":
    main()
