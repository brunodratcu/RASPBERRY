print("=== MAGIC MIRROR v2.0 - VERSÃO ESTÁVEL ===")

# Importações
import machine
import utime
import ujson
import ubluetooth
import gc
from machine import Pin, RTC

# Configuração dos pinos
lcd_rst = Pin(16, Pin.OUT, value=1)
lcd_cs = Pin(17, Pin.OUT, value=1)
lcd_rs = Pin(15, Pin.OUT, value=0)
lcd_wr = Pin(19, Pin.OUT, value=1)
lcd_rd = Pin(18, Pin.OUT, value=1)

data_pins = [
    Pin(8, Pin.OUT), Pin(9, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT),
    Pin(4, Pin.OUT), Pin(5, Pin.OUT), Pin(6, Pin.OUT), Pin(7, Pin.OUT)
]

# Constantes
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
CYAN = 0x07FF
GRAY = 0x8410

WIDTH = 480
HEIGHT = 320

# Variáveis globais
ble_on = False
events = []
server_events = []
rtc = RTC()

# Funções básicas do display
def write_byte(data):
    for i in range(8):
        data_pins[i].value((data >> i) & 1)

def send_command(cmd):
    lcd_cs.value(0)
    lcd_rs.value(0)
    write_byte(cmd)
    lcd_wr.value(0)
    utime.sleep_us(1)
    lcd_wr.value(1)
    lcd_cs.value(1)

def send_data(data):
    lcd_cs.value(0)
    lcd_rs.value(1)
    write_byte(data)
    lcd_wr.value(0)
    utime.sleep_us(1)
    lcd_wr.value(1)
    lcd_cs.value(1)

def init_display():
    print("Inicializando display...")
    
    # Reset
    lcd_rst.value(0)
    utime.sleep_ms(100)
    lcd_rst.value(1)
    utime.sleep_ms(100)
    
    # Comandos básicos
    send_command(0x01)  # Software Reset
    utime.sleep_ms(200)
    send_command(0x11)  # Sleep Out
    utime.sleep_ms(200)
    send_command(0x3A)  # Pixel Format
    send_data(0x55)
    send_command(0x36)  # Orientação
    send_data(0xE8)
    send_command(0x29)  # Display ON
    utime.sleep_ms(100)
    
    print("Display inicializado!")

def set_window(x0, y0, x1, y1):
    send_command(0x2A)  # Column
    send_data(x0 >> 8)
    send_data(x0 & 0xFF)
    send_data(x1 >> 8)
    send_data(x1 & 0xFF)
    
    send_command(0x2B)  # Row
    send_data(y0 >> 8)
    send_data(y0 & 0xFF)
    send_data(y1 >> 8)
    send_data(y1 & 0xFF)
    
    send_command(0x2C)  # Memory Write

def fill_screen(color):
    set_window(0, 0, WIDTH-1, HEIGHT-1)
    
    color_high = (color >> 8) & 0xFF
    color_low = color & 0xFF
    
    lcd_cs.value(0)
    lcd_rs.value(1)
    
    # Preenche em blocos para evitar travamento
    total_pixels = WIDTH * HEIGHT
    for i in range(total_pixels):
        write_byte(color_high)
        lcd_wr.value(0)
        lcd_wr.value(1)
        write_byte(color_low)
        lcd_wr.value(0)
        lcd_wr.value(1)
        
        # Pequena pausa a cada 5000 pixels
        if i % 5000 == 0:
            utime.sleep_us(1)
    
    lcd_cs.value(1)

def fill_rect(x, y, w, h, color):
    if x + w > WIDTH: w = WIDTH - x
    if y + h > HEIGHT: h = HEIGHT - y
    if w <= 0 or h <= 0: return
    
    set_window(x, y, x + w - 1, y + h - 1)
    
    color_high = (color >> 8) & 0xFF
    color_low = color & 0xFF
    
    lcd_cs.value(0)
    lcd_rs.value(1)
    
    for i in range(w * h):
        write_byte(color_high)
        lcd_wr.value(0)
        lcd_wr.value(1)
        write_byte(color_low)
        lcd_wr.value(0)
        lcd_wr.value(1)
    
    lcd_cs.value(1)

def draw_pixel(x, y, color):
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    
    set_window(x, y, x, y)
    
    color_high = (color >> 8) & 0xFF
    color_low = color & 0xFF
    
    lcd_cs.value(0)
    lcd_rs.value(1)
    write_byte(color_high)
    lcd_wr.value(0)
    lcd_wr.value(1)
    write_byte(color_low)
    lcd_wr.value(0)
    lcd_wr.value(1)
    lcd_cs.value(1)

# Fonte bitmap simples
font = {
    '0': [0x3C, 0x66, 0x6A, 0x72, 0x66, 0x66, 0x3C, 0x00],
    '1': [0x18, 0x18, 0x38, 0x18, 0x18, 0x18, 0x7E, 0x00],
    '2': [0x3C, 0x66, 0x06, 0x0C, 0x30, 0x60, 0x7E, 0x00],
    '3': [0x3C, 0x66, 0x06, 0x1C, 0x06, 0x66, 0x3C, 0x00],
    '4': [0x06, 0x0E, 0x1E, 0x66, 0x7F, 0x06, 0x06, 0x00],
    '5': [0x7E, 0x60, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    '6': [0x3C, 0x66, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
    '7': [0x7E, 0x66, 0x0C, 0x18, 0x18, 0x18, 0x18, 0x00],
    '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x66, 0x3C, 0x00],
    ':': [0x00, 0x00, 0x18, 0x00, 0x00, 0x18, 0x00, 0x00],
    '/': [0x00, 0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x00],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    'A': [0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'B': [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
    'D': [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
    'E': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x7E, 0x00],
    'G': [0x3C, 0x66, 0x60, 0x6E, 0x66, 0x66, 0x3C, 0x00],
    'I': [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'L': [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
    'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
    'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'R': [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
    'S': [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
    'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    'V': [0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'W': [0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00],
}

def draw_char(x, y, char, color, size=1):
    bitmap = font.get(char.upper(), font[' '])
    
    for row in range(8):
        byte = bitmap[row]
        for col in range(8):
            if byte & (0x80 >> col):
                for sy in range(size):
                    for sx in range(size):
                        px = x + col * size + sx
                        py = y + row * size + sy
                        if px < WIDTH and py < HEIGHT:
                            draw_pixel(px, py, color)

def draw_text(x, y, text, color, size=1):
    char_x = x
    char_width = 8 * size + 2 * size  # 8 pixels + espaçamento
    
    for char in text:
        if char_x + char_width >= WIDTH:
            break
        draw_char(char_x, y, char, color, size)
        char_x += char_width

def draw_text_centered(y, text, color, size=1):
    text_width = len(text) * (8 * size + 2 * size)
    x = (WIDTH - text_width) // 2
    if x < 0: x = 0
    draw_text(x, y, text, color, size)

def show_welcome():
    print("Exibindo boas-vindas...")
    fill_screen(BLACK)
    
    # Barra superior
    fill_rect(0, 0, WIDTH, 60, CYAN)
    draw_text_centered(20, "BEM-VINDO", BLACK, 3)
    
    # Mensagem central
    draw_text_centered(HEIGHT//2 - 20, "MAGIC MIRROR", WHITE, 4)
    draw_text_centered(HEIGHT//2 + 20, "SISTEMA INICIADO", GREEN, 2)
    
    # Barra inferior
    fill_rect(0, HEIGHT-60, WIDTH, 60, CYAN)
    draw_text_centered(HEIGHT-40, "CARREGANDO...", BLACK, 2)
    
    utime.sleep(2)

# BLE Simplificado
class SimpleBLE:
    def __init__(self):
        try:
            self.ble = ubluetooth.BLE()
            self.ble.active(True)
            self.ble.irq(self._irq)
            self.buf = ""
            
            char = (ubluetooth.UUID("00002a00-0000-1000-8000-00805f9b34fb"), ubluetooth.FLAG_WRITE)
            svc = (ubluetooth.UUID("00001800-0000-1000-8000-00805f9b34fb"), (char,))
            ((self.handle,),) = self.ble.gatts_register_services((svc,))
            
            self.ble.gap_advertise(100, b'\x02\x01\x06\x0c\x09MagicMirror')
            print("BLE iniciado")
        except:
            print("BLE falhou, mas continuando...")
    
    def _irq(self, event, data):
        global ble_on, events, server_events
        
        try:
            if event == 1:  # Conectado
                ble_on = True
            elif event == 2:  # Desconectado
                ble_on = False
                self.ble.gap_advertise(100, b'\x02\x01\x06\x0c\x09MagicMirror')
            elif event == 3:  # Dados recebidos
                self.buf += self.ble.gatts_read(self.handle).decode()
                while '\n' in self.buf:
                    msg, self.buf = self.buf.split('\n', 1)
                    if msg.strip():
                        j = ujson.loads(msg.strip())
                        action = j.get("action")
                        
                        if action == "sync_events":
                            events = j.get("events", [])[:3]
                        elif action == "add_event":
                            e = j.get("event")
                            if e and len(events) < 3:
                                events.append(e)
                        elif action == "server_event":
                            server_event = j.get("message", "Evento")
                            server_events.append(server_event)
        except:
            pass

def get_next_event():
    if not events:
        return None
    
    try:
        now = utime.localtime()
        now_min = now[3] * 60 + now[4]
        for e in events:
            hora_str = e.get("hora", "0:0")
            if ':' in hora_str:
                h, m = map(int, hora_str.split(":"))
                if h * 60 + m >= now_min:
                    return e
        return events[0]
    except:
        return events[0] if events else None

def display_server_event(event_text):
    # Overlay simples
    fill_rect(50, 100, WIDTH-100, 120, BLACK)
    
    # Borda
    fill_rect(50, 100, WIDTH-100, 3, CYAN)
    fill_rect(50, 217, WIDTH-100, 3, CYAN)
    fill_rect(50, 100, 3, 120, CYAN)
    fill_rect(WIDTH-53, 100, 3, 120, CYAN)
    
    draw_text_centered(120, "SERVIDOR WEB", CYAN, 2)
    draw_text_centered(150, event_text[:20], WHITE, 2)
    draw_text_centered(180, "PROCESSANDO...", GREEN, 1)
    
    utime.sleep(3000)

def check_server_events():
    if server_events:
        event = server_events.pop(0)
        display_server_event(event)
        return True
    return False

# PROGRAMA PRINCIPAL
def main():
    print("=== INICIANDO MAGIC MIRROR ===")
    
    # Configura RTC
    rtc.datetime((2024, 8, 28, 2, 14, 30, 0, 0))
    
    # Inicializa display
    init_display()
    
    # Boas-vindas
    show_welcome()
    
    # BLE
    ble = SimpleBLE()
    
    print("Sistema operacional!")
    
    # Loop principal
    last_minute = -1
    
    while True:
        try:
            year, month, day, weekday, hours, minutes, seconds, _ = rtc.datetime()
            
            # Verifica eventos do servidor
            if check_server_events():
                last_minute = -1  # Força atualização
            
            # Atualiza display a cada minuto
            if minutes != last_minute:
                last_minute = minutes
                
                print(f"Atualizando: {hours:02d}:{minutes:02d}")
                
                # Limpa tela
                fill_screen(BLACK)
                
                # BLE Status - Canto superior esquerdo
                draw_text(10, 10, "BLE", GREEN if ble_on else RED, 2)
                
                # Hora GRANDE - Centro
                time_str = f"{hours:02d}:{minutes:02d}"
                draw_text_centered(80, time_str, WHITE, 6)
                
                # Segundos
                seconds_str = f":{seconds:02d}"
                draw_text_centered(140, seconds_str, GRAY, 3)
                
                # Data
                date_str = f"{day:02d}/{month:02d}/{year}"
                draw_text_centered(180, date_str, WHITE, 3)
                
                # Evento do dia
                next_event = get_next_event()
                if next_event:
                    draw_text_centered(230, "EVENTO DO DIA", CYAN, 2)
                    evt_time = next_event.get("hora", "")
                    if evt_time:
                        draw_text_centered(260, evt_time, YELLOW, 3)
                    evt_name = str(next_event.get("nome", ""))[:25]
                    if evt_name:
                        draw_text_centered(290, evt_name, WHITE, 2)
                else:
                    draw_text_centered(250, "SEM EVENTOS HOJE", GRAY, 2)
                
                print("Display atualizado!")
            
            utime.sleep(1)
            gc.collect()
            
        except Exception as e:
            print(f"Erro: {e}")
            utime.sleep(5)

# Executa
main()
