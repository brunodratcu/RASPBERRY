#!/usr/bin/env python3
"""
Magic Mirror - Raspberry Pico 2W - CORRIGIDO COM FONT.PY
Sistema de relógio com sincronização MQTT e eventos do Outlook
CORREÇÃO: Importação correta do módulo font.py
"""

import machine
import utime
import network
import gc
import json
import ubinascii
from machine import Pin, RTC

# ==================== IMPORTAR CONFIG ====================
try:
    from config import *
    print("✅ Config importado")
except ImportError:
    print("⚠️  Config não encontrado - usando padrões")
    WIFI_SSID = "SuaRedeWiFi"
    WIFI_PASSWORD = "SuaSenha"
    TIMEZONE_OFFSET = -3
    DISPLAY_WIDTH = 480
    DISPLAY_HEIGHT = 320
    MQTT_BROKER = "test.mosquitto.org"
    MQTT_PORT = 1883
    TOPIC_PREFIX = "magic_mirror_stable"

# ==================== IMPORTAR FONT.PY ====================
try:
    from font import (
        get_char_bitmap, 
        get_text_width, 
        get_text_height,
        center_text_x,
        split_text_to_fit,
        normalize_text,
        has_char
    )
    FONT_AVAILABLE = True
    print("✅ Font module completo importado!")
except ImportError as e:
    print(f"❌ ERRO: font.py não encontrado! {e}")
    print("   → Coloque font.py na mesma pasta que main.py")
    FONT_AVAILABLE = False
    
    # Fallback básico se font.py não existir
    def get_char_bitmap(char):
        # Fonte 8x8 mínima apenas para dígitos
        basic = {
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
            '?': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00],
        }
        return basic.get(char.upper(), basic[' '])
    
    def get_text_width(text, scale=1):
        return len(text) * 8 * scale
    
    def get_text_height(scale=1):
        return 8 * scale
    
    def center_text_x(text, display_width, scale=1):
        return (display_width - get_text_width(text, scale)) // 2
    
    def split_text_to_fit(text, max_width, scale=1):
        char_width = 8 * scale
        max_chars = max_width // char_width
        if len(text) <= max_chars:
            return [text]
        return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
    
    def normalize_text(text):
        return text
    
    def has_char(char):
        return char in '0123456789:/ ?'

# ==================== IMPORTAR MQTT ====================
try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
    print("✅ MQTT disponível")
except ImportError:
    MQTT_AVAILABLE = False
    print("❌ MQTT não disponível!")
    class MQTTClient:
        def __init__(self, *args, **kwargs): pass
        def connect(self): raise Exception("MQTT não disponível")
        def disconnect(self): pass
        def publish(self, topic, msg): pass
        def subscribe(self, topic): pass
        def check_msg(self): pass
        def set_callback(self, callback): pass

# ==================== IMPORTAR NTP ====================
try:
    import ntptime
    NTP_AVAILABLE = True
    print("✅ NTP disponível")
except ImportError:
    NTP_AVAILABLE = False
    print("⚠️  NTP não disponível")

# ==================== HARDWARE - DISPLAY ====================
rst = Pin(16, Pin.OUT, value=1)
cs = Pin(17, Pin.OUT, value=1)
rs = Pin(15, Pin.OUT, value=0)
wr = Pin(19, Pin.OUT, value=1)
rd = Pin(18, Pin.OUT, value=1)
data_pins = [Pin(i, Pin.OUT) for i in range(8)]

rtc = RTC()

# ==================== CORES RGB565 ====================
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
CYAN = 0x07FF
YELLOW = 0xFFE0
ORANGE = 0xFD20

# ==================== FUNÇÕES DISPLAY ====================
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
    print("Inicializando display...")
    rst.value(0)
    utime.sleep_ms(50)
    rst.value(1)
    utime.sleep_ms(50)
    
    cmd(0x01); utime.sleep_ms(100)
    cmd(0x11); utime.sleep_ms(100)
    cmd(0x3A); dat(0x55)
    cmd(0x36); dat(0xE8)
    cmd(0x29); utime.sleep_ms(50)
    
    print("✅ Display inicializado")
    return True

def set_area(x0, y0, x1, y1):
    cmd(0x2A)
    dat(x0>>8); dat(x0&0xFF); dat(x1>>8); dat(x1&0xFF)
    cmd(0x2B)
    dat(y0>>8); dat(y0&0xFF); dat(y1>>8); dat(y1&0xFF)
    cmd(0x2C)

def fill_rect(x, y, w, h, color):
    if w <= 0 or h <= 0:
        return
    
    set_area(x, y, x+w-1, y+h-1)
    ch, cl = color >> 8, color & 0xFF
    cs.value(0)
    rs.value(1)
    
    for _ in range(w*h):
        write_byte(ch); wr.value(0); wr.value(1)
        write_byte(cl); wr.value(0); wr.value(1)
    
    cs.value(1)

def clear_screen(color=BLACK):
    fill_rect(0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT, color)

def draw_char(x, y, char, color, size=1):
    """Desenha um caractere usando font.py"""
    bitmap = get_char_bitmap(char)
    for row in range(8):
        byte = bitmap[row]
        for col in range(8):
            if byte & (0x80 >> col):
                px = x + col * size
                py = y + row * size
                if px < DISPLAY_WIDTH and py < DISPLAY_HEIGHT:
                    fill_rect(px, py, size, size, color)

def draw_text(x, y, text, color, size=1):
    """Desenha texto usando font.py"""
    char_width = 8 * size
    char_spacing = 2 * size
    
    for i, char in enumerate(str(text)):
        char_x = x + i * (char_width + char_spacing)
        if char_x < DISPLAY_WIDTH - char_width:
            draw_char(char_x, y, char, color, size)

def draw_centered(y, text, color, size=1):
    """Desenha texto centralizado usando font.py"""
    text_str = str(text)
    x = center_text_x(text_str, DISPLAY_WIDTH, size)
    draw_text(x, y, text_str, color, size)

def draw_text_multiline(x, y, text, color, size=1, max_width=None):
    """Desenha texto com quebra de linha automática"""
    if max_width is None:
        max_width = DISPLAY_WIDTH - x - 10
    
    lines = split_text_to_fit(text, max_width, size)
    line_height = get_text_height(size) + 2
    
    for i, line in enumerate(lines):
        line_y = y + (i * line_height)
        if line_y + get_text_height(size) < DISPLAY_HEIGHT:
            draw_text(x, line_y, line, color, size)

# ==================== DEVICE ID ====================
def get_unique_device_id():
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        mac = wlan.config('mac')
        mac_str = ubinascii.hexlify(mac).decode()[-6:]
        return f"PICO_{mac_str.upper()}"
    except:
        return f"PICO_{utime.ticks_ms() % 100000}"

# ==================== NETWORK MANAGER ====================
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
            print(f"✅ WiFi conectado: {self.ip_address}")
            return True
        
        try:
            self.wlan.connect(ssid, password)
            
            for i in range(timeout):
                if self.wlan.isconnected():
                    self.connected = True
                    self.ip_address = self.wlan.ifconfig()[0]
                    print(f"✅ WiFi conectado: {self.ip_address}")
                    return True
                print(".", end="")
                utime.sleep(1)
            
            print(f"\n❌ Timeout WiFi ({timeout}s)")
            return False
        except Exception as e:
            print(f"❌ Erro WiFi: {e}")
            return False
    
    def is_connected(self):
        return self.wlan.isconnected()
    
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
                local_timestamp = utc_timestamp + (TIMEZONE_OFFSET * 3600)
                local_time = utime.localtime(local_timestamp)
                
                rtc.datetime((
                    local_time[0], local_time[1], local_time[2],
                    local_time[6], local_time[3], local_time[4],
                    local_time[5], 0
                ))
                
                self.ntp_synced = True
                current = rtc.datetime()
                print(f"✅ Horário: {current[2]:02d}/{current[1]:02d}/{current[0]} {current[4]:02d}:{current[5]:02d}")
                return True
            except Exception as e:
                print(f"⚠️  Falha NTP {server}: {e}")
                continue
        
        return False

# ==================== MQTT MANAGER ====================
class MQTTManager:
    def __init__(self, device_id, topic_prefix):
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.client = None
        self.connected = False
        self.approved = False
        self.events = []
        
        self.last_ping = 0
        self.last_registration = 0
        self.ping_interval = 30000
        self.registration_interval = 60000
        
        print(f"MQTT configurado:")
        print(f"  Device ID: {device_id}")
        print(f"  Topic: {topic_prefix}")
    
    def mqtt_callback(self, topic, msg):
        try:
            topic_str = topic.decode('utf-8')
            payload_str = msg.decode('utf-8')
            
            print(f"\n📨 MQTT:")
            print(f"  Topic: {topic_str}")
            
            if 'registration' in topic_str:
                self._handle_registration(payload_str)
            elif 'events' in topic_str:
                self._handle_events(payload_str)
        except Exception as e:
            print(f"❌ Erro callback: {e}")
    
    def _handle_registration(self, payload):
        try:
            data = json.loads(payload)
            reg_id = data.get('registration_id')
            
            if reg_id != self.device_id:
                return
            
            status = data.get('status', 'unknown')
            
            if status == 'approved':
                self.approved = True
                device_id = data.get('device_id', 'default')
                
                new_prefix = data.get('topic_prefix')
                if new_prefix:
                    self.topic_prefix = new_prefix
                
                print(f"\n✅ DISPOSITIVO APROVADO!")
                print(f"  Device ID: {device_id}")
                print(f"  Topic: {self.topic_prefix}")
                
                events_topic = f"{self.topic_prefix}/devices/{device_id}/events"
                try:
                    self.client.subscribe(events_topic)
                    print(f"  👂 Inscrito: {events_topic}")
                except Exception as e:
                    print(f"  ❌ Erro subscribe: {e}")
                
        except Exception as e:
            print(f"❌ Erro registro: {e}")
    
    def _handle_events(self, payload):
        try:
            data = json.loads(payload)
            
            if isinstance(data, dict) and 'events' in data:
                self.events = data['events']
            elif isinstance(data, list):
                self.events = data
            else:
                self.events = [data]
            
            print(f"\n✅ {len(self.events)} eventos recebidos")
            for i, event in enumerate(self.events[:3]):
                title = event.get('title', 'Sem título')
                time_str = event.get('time', '')
                print(f"  {i+1}. {time_str} {title}")
        except Exception as e:
            print(f"❌ Erro eventos: {e}")
    
    def connect(self, network_manager):
        if not MQTT_AVAILABLE:
            print("❌ MQTT não disponível")
            return False
        
        if not network_manager.is_connected():
            print("❌ WiFi não conectado")
            return False
        
        try:
            print(f"Conectando MQTT: {MQTT_BROKER}:{MQTT_PORT}")
            
            client_id = f"{self.device_id}_{utime.ticks_ms()}"
            self.client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
            self.client.set_callback(self.mqtt_callback)
            self.client.connect()
            self.connected = True
            
            print(f"✅ MQTT conectado! ID: {client_id}")
            
            registration_topic = f"{self.topic_prefix}/registration"
            self.client.subscribe(registration_topic)
            print(f"👂 Inscrito: {registration_topic}")
            
            self._send_registration()
            
            self.last_ping = utime.ticks_ms()
            return True
        except Exception as e:
            print(f"❌ Erro MQTT: {e}")
            self.connected = False
            return False
    
    def _send_registration(self):
        if not self.client or not self.connected:
            return
        
        now = utime.ticks_ms()
        if utime.ticks_diff(now, self.last_registration) < self.registration_interval:
            return
        
        try:
            mac_address = ''
            try:
                wlan = network.WLAN(network.STA_IF)
                mac = ubinascii.hexlify(wlan.config('mac')).decode()
                mac_address = mac
            except:
                pass
            
            registration_data = {
                'registration_id': self.device_id,
                'device_info': 'Magic Mirror Pico 2W',
                'timestamp': utime.time(),
                'type': 'magic_mirror',
                'version': '3.0',
                'capabilities': ['display', 'clock', 'calendar', 'events'],
                'status': 'requesting_approval',
                'mac_address': mac_address
            }
            
            message = json.dumps(registration_data)
            topic = f"{self.topic_prefix}/registration"
            
            self.client.publish(topic, message)
            print(f"📤 Registro enviado: {topic}")
            
            self.last_registration = now
        except Exception as e:
            print(f"❌ Erro enviando registro: {e}")
    
    def process_messages(self):
        if not self.client or not self.connected:
            return False
        
        try:
            self.client.check_msg()
            
            now = utime.ticks_ms()
            if utime.ticks_diff(now, self.last_ping) > self.ping_interval:
                self.client.ping()
                self.last_ping = now
            
            if not self.approved and utime.ticks_diff(now, self.last_registration) > self.registration_interval:
                self._send_registration()
            
            return True
        except Exception as e:
            print(f"❌ Erro processando: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        if self.client:
            try:
                self.client.disconnect()
            except:
                pass
            self.client = None
            self.connected = False
    
    def get_events(self):
        return self.events.copy()
    
    def is_connected(self):
        return self.connected
    
    def is_approved(self):
        return self.approved

# ==================== MAGIC MIRROR ====================
class MagicMirror:
    def __init__(self):
        print("Inicializando Magic Mirror...")
        
        self.network = NetworkManager()
        self.mqtt = None
        self.device_id = get_unique_device_id()
        
        print(f"Device ID: {self.device_id}")
        
        self.last_display_state = {
            'h1': None, 'h2': None,
            'm1': None, 'm2': None,
            's1': None, 's2': None,
            'date': None,
            'events': None,
            'status': None
        }
        
        self.digit_positions = {
            'h1': (120, 60), 'h2': (160, 60),
            'm1': (220, 60), 'm2': (260, 60),
            's1': (320, 60), 's2': (360, 60),
        }
        
        self.init_system()
    
    def init_system(self):
        print("=" * 50)
        print("MAGIC MIRROR - INICIALIZAÇÃO")
        print("=" * 50)
        
        if not init_display():
            print("❌ Falha display")
            return
        
        self.show_splash()
        
        wifi_ok = self.network.connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        if wifi_ok:
            self.show_status("WiFi conectado", GREEN)
            
            ntp_ok = self.network.sync_ntp_brasilia()
            if ntp_ok:
                self.show_status("Horário sincronizado", GREEN)
            else:
                self.show_status("NTP falhou", YELLOW)
                rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))
            
            self.mqtt = MQTTManager(self.device_id, TOPIC_PREFIX)
            mqtt_ok = self.mqtt.connect(self.network)
            
            if mqtt_ok:
                self.show_status("MQTT OK - aguardando", YELLOW)
            else:
                self.show_status("MQTT falhou", RED)
        else:
            self.show_status("WiFi falhou", RED)
            rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))
        
        utime.sleep(3)
        self.setup_main_screen()
        
        gc.collect()
        print(f"Memória livre: {gc.mem_free()}")
        print("✅ Inicialização completa!")
    
    def show_splash(self):
        clear_screen(BLACK)
        draw_centered(80, "MAGIC MIRROR", WHITE, 3)
        draw_centered(140, "Inicializando...", CYAN, 2)
    
    def show_status(self, message, color):
        fill_rect(0, 200, DISPLAY_WIDTH, 40, BLACK)
        draw_centered(210, message, color, 1)
        print(f"Status: {message}")
    
    def setup_main_screen(self):
        clear_screen(BLACK)
        draw_text(200, 60, ":", WHITE, 4)
        draw_text(300, 60, ":", WHITE, 4)
        for key in self.last_display_state:
            self.last_display_state[key] = None
        print("✅ Tela principal configurada")
    
    def update_single_digit(self, digit_key, new_digit):
        if self.last_display_state[digit_key] != new_digit:
            x, y = self.digit_positions[digit_key]
            fill_rect(x, y, 32, 32, BLACK)
            draw_char(x, y, new_digit, WHITE, 4)
            self.last_display_state[digit_key] = new_digit
    
    def update_clock_display(self):
        current = rtc.datetime()
        h, m, s = current[4], current[5], current[6]
        
        h1, h2 = f"{h:02d}"[0], f"{h:02d}"[1]
        m1, m2 = f"{m:02d}"[0], f"{m:02d}"[1]
        s1, s2 = f"{s:02d}"[0], f"{s:02d}"[1]
        
        self.update_single_digit('h1', h1)
        self.update_single_digit('h2', h2)
        self.update_single_digit('m1', m1)
        self.update_single_digit('m2', m2)
        self.update_single_digit('s1', s1)
        self.update_single_digit('s2', s2)
    
    def update_date_display(self):
        current = rtc.datetime()
        day, month, year = current[2], current[1], current[0]
        weekday = current[3]
        
        weekdays = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM']
        weekday_name = weekdays[weekday]
        
        date_str = f"{weekday_name} {day:02d}/{month:02d}/{year}"
        
        if self.last_display_state['date'] != date_str:
            fill_rect(0, 130, DISPLAY_WIDTH, 25, BLACK)
            draw_centered(130, date_str, CYAN, 2)
            self.last_display_state['date'] = date_str
    
    def update_events_display(self):
        if not self.mqtt:
            return
        
        events = self.mqtt.get_events()
        start_y = 170
        area_height = 120
        line_height = 18
        max_events = min(6, area_height // line_height)
        
        events_text_lines = []
        
        if events:
            events_text_lines.append("EVENTOS DE HOJE:")
            for i, event in enumerate(events[:max_events]):
                if isinstance(event, dict):
                    time_str = event.get('time', '').strip()
                    title = event.get('title', 'Evento').strip()
                    
                    # Normalizar texto para caracteres suportados
                    title = normalize_text(title)
                    
                    if len(title) > 32:
                        title = title[:29] + "..."
                    
                    if time_str:
                        line = f"{time_str} {title}"
                    else:
                        line = f"Todo dia: {title}"
                else:
                    line = normalize_text(str(event)[:40])
                
                events_text_lines.append(line)
        else:
            events_text_lines.append("NENHUM EVENTO HOJE")
        
        events_display_text = "\n".join(events_text_lines)
        
        if self.last_display_state['events'] != events_display_text:
            fill_rect(0, start_y, DISPLAY_WIDTH, area_height, BLACK)
            
            for i, line in enumerate(events_text_lines):
                y_pos = start_y + (i * line_height)
                
                if y_pos + 10 < start_y + area_height:
                    if i == 0:
                        color = YELLOW
                        x_pos = 10
                    else:
                        color = WHITE if (i % 2) == 1 else CYAN
                        x_pos = 15
                    
                    draw_text(x_pos, y_pos, line, color, 1)
            
            self.last_display_state['events'] = events_display_text
            print(f"✅ Eventos atualizados ({len(events)})")
    
    def update_status_display(self):
        wifi_ok = self.network.is_connected()
        mqtt_ok = self.mqtt and self.mqtt.is_connected()
        approved = self.mqtt and self.mqtt.is_approved()
        
        if wifi_ok and mqtt_ok and approved:
            status_text = "SINCRONIZADO"
            status_color = GREEN
        elif wifi_ok and mqtt_ok:
            status_text = "AGUARDANDO APROVACAO"
            status_color = YELLOW
        elif wifi_ok:
            status_text = "WIFI OK - MQTT OFF"
            status_color = ORANGE
        else:
            status_text = "DESCONECTADO"
            status_color = RED
        
        if self.last_display_state['status'] != status_text:
            fill_rect(0, 300, DISPLAY_WIDTH, 20, BLACK)
            draw_centered(300, status_text, status_color, 1)
            self.last_display_state['status'] = status_text
    
    def run_main_loop(self):
        print("Iniciando loop principal...")
        
        loop_count = 0
        ntp_sync_counter = 0
        gc_counter = 0
        
        while True:
            try:
                if self.mqtt and self.mqtt.is_connected():
                    if not self.mqtt.process_messages():
                        print("⚠️  Falha MQTT")
                
                self.update_clock_display()
                self.update_date_display()
                self.update_status_display()
                
                if loop_count % 10 == 0:
                    self.update_events_display()
                
                ntp_sync_counter += 1
                if ntp_sync_counter >= 7200:
                    if self.network.is_connected():
                        print("🔄 Re-sincronizando NTP...")
                        self.network.sync_ntp_brasilia()
                    ntp_sync_counter = 0
                
                gc_counter += 1
                if gc_counter >= 240:
                    gc.collect()
                    gc_counter = 0
                    
                    if loop_count % 240 == 0:
                        free_mem = gc.mem_free()
                        events_count = len(self.mqtt.get_events()) if self.mqtt else 0
                        print(f"💾 Memória: {free_mem} | Eventos: {events_count}")
                
                loop_count += 1
                utime.sleep_ms(500)
                
            except KeyboardInterrupt:
                print("\n⚠️  Interrompido pelo usuário")
                break
            except Exception as e:
                print(f"❌ Erro loop: {e}")
                utime.sleep(2)
        
        if self.mqtt:
            self.mqtt.disconnect()
        print("✅ Sistema finalizado")

# ==================== MAIN ====================
def main():
    print("=" * 60)
    print("MAGIC MIRROR - PICO 2W v3.0")
    print("COM SUPORTE COMPLETO A FONT.PY")
    print("=" * 60)
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic: {TOPIC_PREFIX}")
    print(f"Timezone: UTC{TIMEZONE_OFFSET:+d}")
    print(f"Font.py: {'✅ DISPONÍVEL' if FONT_AVAILABLE else '⚠️  BÁSICO'}")
    print("=" * 60)
    
    try:
        if WIFI_SSID == "SuaRedeWiFi":
            print("❌ ERRO: Configure WiFi no config.py")
            clear_screen(BLACK)
            draw_centered(80, "CONFIGURE WIFI", RED, 2)
            draw_centered(120, "Edite config.py", WHITE, 1)
            while True:
                utime.sleep(10)
        
        if not MQTT_AVAILABLE:
            print("❌ ERRO: umqtt.simple não encontrado!")
            clear_screen(BLACK)
            draw_centered(80, "MQTT NAO DISPONIVEL", RED, 2)
            draw_centered(120, "Instale umqtt.simple", WHITE, 1)
            while True:
                utime.sleep(10)
        
        if not FONT_AVAILABLE:
            print("⚠️  AVISO: font.py não encontrado!")
            print("   → Usando fonte básica (apenas dígitos)")
            print("   → Coloque font.py na pasta para suporte completo")
        
        mirror = MagicMirror()
        mirror.run_main_loop()
        
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}")
        try:
            clear_screen(BLACK)
            draw_centered(80, "ERRO FATAL", RED, 3)
            draw_centered(120, "Verifique console", WHITE, 1)
            draw_centered(150, str(e)[:40], YELLOW, 1)
            while True:
                utime.sleep(10)
        except:
            while True:
                utime.sleep(10)

if __name__ == "__main__":
    main()