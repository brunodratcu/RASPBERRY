#!/usr/bin/env python3
"""
Magic Mirror - Versão Otimizada
Redesenha apenas os dígitos que mudaram
"""

import machine
import utime
import network
import gc
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

# ==================== CLASSE PRINCIPAL ====================
class MagicMirror:
    def __init__(self):
        self.wifi_connected = False
        self.ntp_synced = False
        
        # Controle de estado anterior para otimização
        self.last_display = {
            'h1': None, 'h2': None,  # Dígitos das horas
            'm1': None, 'm2': None,  # Dígitos dos minutos  
            's1': None, 's2': None,  # Dígitos dos segundos
            'date': None,            # Data completa
            'status': None           # Status de conexão
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
        
        # Mostrar startup
        clear_screen(BLACK)
        draw_centered(140, "MAGIC MIRROR", WHITE, 3)
        utime.sleep(2)
        
        # Configurar horário manual (simulação)
        rtc.datetime((2024, 12, 25, 2, 15, 30, 0, 0))  # 25/12/2024 15:30:00
        
        # Configurar tela principal
        self.setup_main_screen()
        
        # Tentar WiFi em background
        self.try_wifi_background()
    
    def setup_main_screen(self):
        clear_screen(BLACK)
        # Desenhar separadores fixos do relógio (dois pontos)
        draw_text(180, 60, ":", WHITE, 4)
        draw_text(280, 60, ":", WHITE, 4)
        
        # Forçar redesenho completo na próxima atualização
        self.last_display = {
            'h1': None, 'h2': None, 'm1': None, 'm2': None, 
            's1': None, 's2': None, 'date': None, 'status': None
        }
    
    def try_wifi_background(self):
        """Tenta WiFi sem bloquear interface"""
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
                    # Redesenhar tela após conexão
                    self.setup_main_screen()
        except:
            pass
    
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
        
        # Status - atualizar apenas se mudou
        status_color = GREEN if self.wifi_connected else YELLOW
        status_text = "WIFI" if self.wifi_connected else "LOCAL"
        if self.ntp_synced: 
            status_text += " NTP"
        
        if self.last_display['status'] != status_text:
            fill_rect(0, 290, DISPLAY_WIDTH, 20, BLACK)  # Limpar área do status
            draw_centered(295, status_text, status_color, 1)
            self.last_display['status'] = status_text
    
    def run(self):
        """Loop principal simplificado"""
        while True:
            try:
                self.update_clock()
                
                # Coleta de lixo ocasional
                if utime.ticks_ms() % 60000 < 100:  # ~1 minuto
                    gc.collect()
                
                utime.sleep(1)
                
            except KeyboardInterrupt:
                break
            except:
                # Em caso de erro, continuar
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
            draw_centered(100, "ERRO", RED, 4)
            draw_centered(150, str(e)[:15], WHITE, 2)
            draw_centered(200, "REINICIANDO", YELLOW, 2)
            utime.sleep(3)
        except:
            pass
        machine.reset()

if __name__ == "__main__":
    main()
