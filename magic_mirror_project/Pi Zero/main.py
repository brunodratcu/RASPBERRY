#!/usr/bin/env python3
"""
Magic Mirror - Versão Simplificada com MQTT
Apenas relógio e status de conexão MQTT
"""

import machine
import utime
import network
import gc
import json
from machine import Pin, RTC

# Importar configurações
try:
    from config import *
except ImportError:
    WIFI_SSID = "SuaRedeWiFi"
    WIFI_PASSWORD = "SuaSenha"
    TIMEZONE_OFFSET = -3
    DISPLAY_WIDTH = 480
    DISPLAY_HEIGHT = 320
    # MQTT Config
    MQTT_BROKER = "test.mosquitto.org"
    MQTT_PORT = 1883
    TOPIC_PREFIX = "magic_mirror_default"
    DEVICE_ID = "mirror_001"

# Importar MQTT
try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

# Importar fontes
try:
    from font import FONT_8X8
except ImportError:
    # Fonte mínima se não conseguir importar
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
    }

try:
    import ntptime
    NTP_AVAILABLE = True
except ImportError:
    NTP_AVAILABLE = False

# ==================== HARDWARE SETUP ====================
# Pinos do display
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

# ==================== FUNÇÕES DO DISPLAY ====================
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
    
    cmd(0x01); utime.sleep_ms(100)  # Reset
    cmd(0x11); utime.sleep_ms(100)  # Sleep out
    cmd(0x3A); dat(0x55)            # 16-bit
    cmd(0x36); dat(0xE8)            # Orientation  
    cmd(0x29); utime.sleep_ms(50)   # Display on
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
    if char not in FONT_8X8: char = ' '
    bitmap = FONT_8X8[char]
    
    # Desenhar caractere pixel por pixel
    for row in range(8):
        byte = bitmap[row]
        for col in range(8):
            px = x + col * size
            py = y + row * size
            
            # Sempre desenhar - pixel aceso ou apagado
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

# ==================== CLASSE MQTT ====================
class MQTTHandler:
    def __init__(self, device_id, topic_prefix):
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.client = None
        self.connected = False
        self.last_ping = 0
        self.events = []
        
    def connect(self):
        """Conecta ao broker MQTT"""
        if not MQTT_AVAILABLE:
            return False
            
        try:
            client_id = f"{self.device_id}_{utime.ticks_ms()}"
            self.client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
            
            # Configurar callback de mensagens
            self.client.set_callback(self.on_message)
            
            # Conectar
            self.client.connect()
            
            # Inscrever-se nos tópicos
            self.client.subscribe(f"{self.topic_prefix}/devices/{self.device_id}/events")
            self.client.subscribe(f"{self.topic_prefix}/registration")
            
            self.connected = True
            self.last_ping = utime.ticks_ms()
            
            # Enviar registro
            self.send_registration()
            
            return True
            
        except Exception as e:
            self.connected = False
            return False
    
    def on_message(self, topic, msg):
        """Callback para mensagens MQTT recebidas"""
        try:
            topic_str = topic.decode()
            msg_str = msg.decode()
            data = json.loads(msg_str)
            
            # Processar eventos do calendário
            if f"/devices/{self.device_id}/events" in topic_str:
                self.events = data.get('events', [])
                print(f"Eventos recebidos: {len(self.events)}")
                
        except Exception as e:
            print(f"Erro processando mensagem MQTT: {e}")
    
    def send_registration(self):
        """Envia mensagem de registro para o servidor"""
        if not self.connected:
            return
            
        try:
            registration_data = {
                'registration_id': self.device_id,
                'timestamp': utime.time(),
                'type': 'pico_2w'
            }
            
            topic = f"{self.topic_prefix}/registration"
            message = json.dumps(registration_data)
            self.client.publish(topic, message)
            
        except Exception as e:
            print(f"Erro enviando registro: {e}")
    
    def check_messages(self):
        """Verifica mensagens MQTT (não bloqueante)"""
        if not self.connected or not self.client:
            return
            
        try:
            self.client.check_msg()
            
            # Ping periódico para manter conexão
            now = utime.ticks_ms()
            if utime.ticks_diff(now, self.last_ping) > 30000:  # 30 segundos
                self.client.ping()
                self.last_ping = now
                
        except Exception as e:
            print(f"Erro MQTT: {e}")
            self.connected = False
    
    def get_events(self):
        """Retorna eventos do calendário"""
        return self.events

# ==================== CLASSE PRINCIPAL ====================
class MagicMirror:
    def __init__(self):
        self.wifi_connected = False
        self.ntp_synced = False
        self.mqtt_handler = None
        
        # Controle de estado anterior para otimização
        self.last_display = {
            'h1': None, 'h2': None,  # Dígitos das horas
            'm1': None, 'm2': None,  # Dígitos dos minutos  
            's1': None, 's2': None,  # Dígitos dos segundos
            'date': None,            # Data completa
            'status': None,          # Status de conexão
            'events': None           # Eventos
        }
        
        # Posições fixas dos dígitos no display
        self.positions = {
            'h1': (100, 60),  # Primeiro dígito da hora
            'h2': (140, 60),  # Segundo dígito da hora
            'm1': (200, 60),  # Primeiro dígito do minuto
            'm2': (240, 60),  # Segundo dígito do minuto
            's1': (300, 60),  # Primeiro dígito do segundo
            's2': (340, 60),  # Segundo dígito do segundo
        }
        
        # Inicializar display
        init_display()
        
        # Mostrar tela de inicialização
        clear_screen(BLACK)
        draw_centered(140, "INICIALIZANDO MQTT", CYAN, 2)
        utime.sleep(2)
        
        # Configurar horário manual (simulação)
        rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))  # 25/12/2024 15:30:00
        
        # Configurar tela principal
        self.setup_main_screen()
        
        # Tentar WiFi e MQTT em background
        self.try_wifi_background()
    
    def setup_main_screen(self):
        clear_screen(BLACK)
        # Desenhar separadores fixos do relógio (dois pontos)
        draw_text(180, 60, ":", WHITE, 4)
        draw_text(280, 60, ":", WHITE, 4)
        
        # Forçar redesenho completo na próxima atualização
        self.last_display = {
            'h1': None, 'h2': None, 'm1': None, 'm2': None, 
            's1': None, 's2': None, 'date': None, 'status': None,
            'events': None
        }
    
    def try_wifi_background(self):
        """Tenta WiFi e MQTT sem bloquear interface"""
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            
            if not wlan.isconnected():
                wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                
                # Aguardar conexão (máximo 15 segundos)
                for _ in range(15):
                    if wlan.isconnected():
                        break
                    utime.sleep(1)
                
                if wlan.isconnected():
                    self.wifi_connected = True
                    self.sync_ntp()
                    self.setup_mqtt()
                    # Redesenhar tela após conexão
                    self.setup_main_screen()
        except:
            pass
    
    def setup_mqtt(self):
        """Configura conexão MQTT"""
        if not self.wifi_connected:
            return
            
        try:
            self.mqtt_handler = MQTTHandler(DEVICE_ID, TOPIC_PREFIX)
            mqtt_connected = self.mqtt_handler.connect()
            
            if mqtt_connected:
                print("MQTT conectado com sucesso")
            else:
                print("Falha na conexão MQTT")
                
        except Exception as e:
            print(f"Erro configurando MQTT: {e}")
    
    def sync_ntp(self):
        """Sincroniza horário via NTP"""
        if not self.wifi_connected or not NTP_AVAILABLE:
            return
        
        try:
            ntptime.settime()
            # Ajustar fuso horário
            timestamp_utc = utime.time()
            timestamp_local = timestamp_utc + (TIMEZONE_OFFSET * 3600)
            local_time = utime.localtime(timestamp_local)
            
            rtc.datetime((local_time[0], local_time[1], local_time[2], 
                         local_time[6], local_time[3], local_time[4], 
                         local_time[5], 0))
            
            self.ntp_synced = True
        except:
            pass
    
    def update_single_digit(self, position_key, new_digit):
        """Atualiza um único dígito se ele mudou"""
        if self.last_display[position_key] != new_digit:
            x, y = self.positions[position_key]
            
            # Limpar área do dígito (32x32 pixels para tamanho 4)
            fill_rect(x, y, 32, 32, BLACK)
            
            # Desenhar novo dígito
            draw_char(x, y, new_digit, WHITE, 4)
            
            # Atualizar estado
            self.last_display[position_key] = new_digit
    
    def update_events(self):
        """Atualiza eventos do calendário na tela"""
        if not self.mqtt_handler:
            return
            
        events = self.mqtt_handler.get_events()
        events_text = f"EVENTOS: {len(events)}" if events else "SEM EVENTOS"
        
        if self.last_display['events'] != events_text:
            # Limpar área dos eventos
            fill_rect(0, 240, DISPLAY_WIDTH, 25, BLACK)
            
            # Mostrar quantidade de eventos
            draw_centered(245, events_text, YELLOW, 2)
            
            # Mostrar primeiro evento se existir
            if events:
                first_event = events[0]
                event_title = first_event.get('title', 'Sem título')[:20]  # Limitar tamanho
                fill_rect(0, 265, DISPLAY_WIDTH, 20, BLACK)
                draw_centered(268, event_title, WHITE, 1)
            
            self.last_display['events'] = events_text
    
    def update_clock(self):
        """Atualiza relógio - VERSÃO OTIMIZADA"""
        current = rtc.datetime()
        h, m, s = current[4], current[5], current[6]
        d, month, y = current[2], current[1], current[0]
        
        # Separar dígitos individuais
        h1, h2 = f"{h:02d}"[0], f"{h:02d}"[1]
        m1, m2 = f"{m:02d}"[0], f"{m:02d}"[1]  
        s1, s2 = f"{s:02d}"[0], f"{s:02d}"[1]
        
        # Atualizar apenas dígitos que mudaram
        self.update_single_digit('h1', h1)
        self.update_single_digit('h2', h2)
        self.update_single_digit('m1', m1)
        self.update_single_digit('m2', m2)
        self.update_single_digit('s1', s1)
        self.update_single_digit('s2', s2)
        
        # Data - atualizar apenas se mudou
        date_str = f"{d:02d}/{month:02d}/{y}"
        if self.last_display['date'] != date_str:
            fill_rect(0, 130, DISPLAY_WIDTH, 30, BLACK)  # Limpar área da data
            draw_centered(130, date_str, CYAN, 3)
            self.last_display['date'] = date_str
        
        # Status - mostrar apenas "LOCAL" em amarelo ou verde quando MQTT conectado
        if self.mqtt_handler and self.mqtt_handler.connected:
            status_text = "LOCAL"
            status_color = GREEN
        else:
            status_text = "LOCAL"
            status_color = YELLOW
        
        if self.last_display['status'] != (status_text, status_color):
            fill_rect(0, 290, DISPLAY_WIDTH, 20, BLACK)  # Limpar área do status
            draw_centered(295, status_text, status_color, 1)
            self.last_display['status'] = (status_text, status_color)
    
    def run(self):
        """Loop principal"""
        while True:
            try:
                # Verificar mensagens MQTT
                if self.mqtt_handler:
                    self.mqtt_handler.check_messages()
                
                # Atualizar display
                self.update_clock()
                self.update_events()
                
                # Coleta de lixo ocasional
                if utime.ticks_ms() % 60000 < 100:  # ~1 minuto
                    gc.collect()
                
                utime.sleep_ms(500)  # Loop mais lento sem blink
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Erro no loop principal: {e}")
                utime.sleep(1)

# ==================== EXECUÇÃO ====================
def main():
    try:
        mirror = MagicMirror()
        mirror.run()
    except Exception as e:
        # Mostrar erro e reiniciar
        try:
            clear_screen(BLACK)
            draw_centered(150, "ERRO DISPLAY", RED, 3)
            utime.sleep(3)
        except:
            pass
        machine.reset()

if __name__ == "__main__":
    main()