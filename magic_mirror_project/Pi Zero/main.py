"""
# === CONFIGURAÇÕES WIFI ===
WIFI_SSID = "iPhone A C Dratcu"      # Altere para seu WiFi
WIFI_PASSWORD = "s7wgr4dobgdse"  # Altere para sua senha
"""

# main.py - Magic Mirror - BLE Sincronizacao com NTP e Servidor
import machine
import utime
import ujson
import ubluetooth
import gc
import network
import ntptime
import urequests
from machine import Pin, RTC

print("MAGIC MIRROR - Iniciando...")

# === CONFIGURACOES WIFI ===
WIFI_SSID = "Bruno Dratcu"
WIFI_PASSWORD = "deniederror"

# === CONFIGURACOES SERVIDOR ===
SERVER_IP = "192.168.1.100"  # IP do seu servidor Flask (altere conforme necessario)
SERVER_PORT = 5000

# === CONFIGURACOES BLE ===
SERVICE_UUID = ubluetooth.UUID("12345678-1234-5678-9abc-123456789abc")
EVENTS_CHAR_UUID = ubluetooth.UUID("12345678-1234-5678-9abc-123456789abd")
RESPONSE_CHAR_UUID = ubluetooth.UUID("12345678-1234-5678-9abc-123456789abe")

# === HARDWARE ===
rtc = RTC()

# Pinos display
rst = Pin(16, Pin.OUT, value=1)
cs = Pin(17, Pin.OUT, value=1)
rs = Pin(15, Pin.OUT, value=0)
wr = Pin(19, Pin.OUT, value=1)
rd = Pin(18, Pin.OUT, value=1)
data_pins = [Pin(i, Pin.OUT) for i in [0,1,2,3,4,5,6,7]]

# Botao
btn = Pin(21, Pin.IN, Pin.PULL_UP)

# Cores
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
YELLOW = 0xFFE0
CYAN = 0x07FF

# Estado global
display_on = True
events = []
ble_connected = False
message_buffer = ""

def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if wlan.isconnected():
        print("WiFi ja conectado!")
        return True
    
    print("Conectando WiFi: " + WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    timeout = 10
    while timeout > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        timeout -= 1
        print("Conectando...")
        utime.sleep(1)
    
    if wlan.isconnected():
        print("WiFi conectado! IP: " + str(wlan.ifconfig()[0]))
        return True
    else:
        print("ERRO: Falha ao conectar WiFi!")
        return False

def inicializar_horario():
    print("=== INICIALIZANDO HORARIO ===")
    
    if conectar_wifi():
        try:
            print("Sincronizando horario via NTP...")
            ntptime.settime()
            
            # Ajusta para horario de Brasilia (UTC-3)
            timestamp_utc = utime.time()
            timestamp_brasilia = timestamp_utc - (3 * 3600)  # 3 horas em segundos
            
            # Converte timestamp para tupla de data/hora
            brasilia_time = utime.localtime(timestamp_brasilia)
            
            # Configura RTC com horario de Brasilia
            rtc.datetime((brasilia_time[0], brasilia_time[1], brasilia_time[2], 
                         brasilia_time[6], brasilia_time[3], brasilia_time[4], 
                         brasilia_time[5], 0))
            
            t = rtc.datetime()
            print("Horario Brasilia: " + str(t[2]) + "/" + str(t[1]) + "/" + str(t[0]) + " " + str(t[4]) + ":" + str(t[5]))
            return True
            
        except Exception as e:
            print("ERRO NTP: " + str(e))
            print("Falha na sincronizacao")
    else:
        print("Sem WiFi disponivel")
    
    print("Usando horario padrao...")
    rtc.datetime((2024, 12, 25, 2, 16, 30, 0, 0))
    return False

def detectar_ip_servidor():
    """Tenta detectar IP do servidor automaticamente"""
    global SERVER_IP
    
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ip_local = wlan.ifconfig()[0]
            rede = ".".join(ip_local.split(".")[:-1])
            
            print("Tentando detectar servidor na rede " + rede + ".x")
            
            ips_teste = [
                rede + ".1",
                rede + ".100",
                rede + ".101",
                rede + ".10",
                "192.168.1.100",
                "192.168.0.100"
            ]
            
            for ip_teste in ips_teste:
                try:
                    print("Testando servidor em: " + ip_teste)
                    url = "http://" + ip_teste + ":" + str(SERVER_PORT) + "/api/sistema/info"
                    response = urequests.get(url, timeout=3)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'eventos_hoje' in data:
                            SERVER_IP = ip_teste
                            print("Servidor encontrado em: " + SERVER_IP)
                            response.close()
                            return True
                    response.close()
                    
                except:
                    continue
            
            print("Servidor nao encontrado automaticamente")
            return False
            
    except Exception as e:
        print("Erro na deteccao: " + str(e))
        return False

def buscar_eventos_servidor():
    """Busca eventos do dia atual no servidor Flask"""
    try:
        if not network.WLAN(network.STA_IF).isconnected():
            print("WiFi desconectado - nao e possivel buscar eventos")
            return False
        
        print("Buscando eventos do dia no servidor...")
        
        url = "http://" + SERVER_IP + ":" + str(SERVER_PORT) + "/api/eventos-hoje"
        response = urequests.get(url, timeout=10)
        
        if response.status_code == 200:
            eventos_json = response.json()
            response.close()
            
            global events
            events = []
            
            for evento in eventos_json:
                events.append({
                    'id': evento.get('id'),
                    'nome': evento.get('nome', 'Sem nome'),
                    'hora': evento.get('hora', '--:--')
                })
            
            print("Eventos carregados do servidor: " + str(len(events)))
            for i, evt in enumerate(events):
                print("  " + str(i+1) + ". " + evt['hora'] + " - " + evt['nome'])
            
            return True
            
        else:
            print("Servidor respondeu com status: " + str(response.status_code))
            response.close()
            return False
            
    except Exception as e:
        print("Erro ao buscar eventos: " + str(e))
        return False

def inicializar_eventos():
    """Inicializa eventos buscando do servidor ou mantendo lista vazia"""
    print("=== INICIALIZANDO EVENTOS ===")
    
    if detectar_ip_servidor():
        if buscar_eventos_servidor():
            print("Eventos sincronizados com servidor!")
            return True
        else:
            print("Falha ao buscar eventos do servidor")
    else:
        print("Servidor nao encontrado - modo offline")
    
    global events
    events = []
    print("Iniciando sem eventos - aguardando sincronizacao BLE")
    return False

# === DISPLAY ===
def write_byte(data):
    for i in range(8):
        data_pins[i].value((data >> i) & 1)

def cmd(c):
    cs.value(0); rs.value(0); write_byte(c)
    wr.value(0); wr.value(1); cs.value(1)

def dat(d):
    cs.value(0); rs.value(1); write_byte(d)
    wr.value(0); wr.value(1); cs.value(1)

def init_lcd():
    rst.value(0); utime.sleep_ms(50); rst.value(1); utime.sleep_ms(50)
    cmd(0x01); utime.sleep_ms(100)
    cmd(0x11); utime.sleep_ms(100)
    cmd(0x3A); dat(0x55)
    cmd(0x36); dat(0xE8)
    cmd(0x29); utime.sleep_ms(50)

def set_area(x0, y0, x1, y1):
    cmd(0x2A); dat(x0>>8); dat(x0&0xFF); dat(x1>>8); dat(x1&0xFF)
    cmd(0x2B); dat(y0>>8); dat(y0&0xFF); dat(y1>>8); dat(y1&0xFF)
    cmd(0x2C)

def fill_rect(x, y, w, h, color):
    if not display_on or w<=0 or h<=0: 
        return
    set_area(x, y, x+w-1, y+h-1)
    ch, cl = color>>8, color&0xFF
    cs.value(0); rs.value(1)
    for _ in range(w*h):
        write_byte(ch); wr.value(0); wr.value(1)
        write_byte(cl); wr.value(0); wr.value(1)
    cs.value(1)

# === FONTE BITMAP ===
font = {
    # NÚMEROS
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
    
    # SÍMBOLOS
    ':': [0x00, 0x00, 0x18, 0x00, 0x00, 0x18, 0x00, 0x00],
    '/': [0x00, 0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x00],
    '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    
    # MAIÚSCULAS
    'A': [0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'B': [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
    'D': [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
    'E': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x7E, 0x00],
    'F': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x60, 0x00],
    'G': [0x3C, 0x66, 0x60, 0x6E, 0x66, 0x66, 0x3C, 0x00],
    'H': [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'I': [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'J': [0x1E, 0x0C, 0x0C, 0x0C, 0x0C, 0x6C, 0x38, 0x00],
    'K': [0x66, 0x6C, 0x78, 0x70, 0x78, 0x6C, 0x66, 0x00],
    'L': [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
    'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
    'N': [0x66, 0x76, 0x7E, 0x7E, 0x6E, 0x66, 0x66, 0x00],
    'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'P': [0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 0x60, 0x00],
    'Q': [0x3C, 0x66, 0x66, 0x66, 0x6A, 0x6C, 0x36, 0x00],
    'R': [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
    'S': [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
    'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    'U': [0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'V': [0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'W': [0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00],
    'X': [0x66, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x66, 0x00],
    'Y': [0x66, 0x66, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x00],
    'Z': [0x7E, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x7E, 0x00],
    
    # MINÚSCULAS
    'a': [0x00, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00],
    'b': [0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x7C, 0x00],
    'c': [0x00, 0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x00],
    'd': [0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x3E, 0x00],
    'e': [0x00, 0x00, 0x3C, 0x66, 0x7E, 0x60, 0x3C, 0x00],
    'f': [0x0E, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x18, 0x00],
    'g': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x7C],
    'h': [0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    'i': [0x18, 0x00, 0x38, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'j': [0x06, 0x00, 0x0E, 0x06, 0x06, 0x06, 0x66, 0x3C],
    'k': [0x60, 0x60, 0x66, 0x6C, 0x78, 0x6C, 0x66, 0x00],
    'l': [0x38, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'm': [0x00, 0x00, 0x66, 0x7F, 0x7F, 0x6B, 0x63, 0x00],
    'n': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    'o': [0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'p': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60],
    'q': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06],
    'r': [0x00, 0x00, 0x7C, 0x66, 0x60, 0x60, 0x60, 0x00],
    's': [0x00, 0x00, 0x3E, 0x60, 0x3C, 0x06, 0x7C, 0x00],
    't': [0x18, 0x18, 0x7E, 0x18, 0x18, 0x18, 0x0E, 0x00],
    'u': [0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3E, 0x00],
    'v': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'w': [0x00, 0x00, 0x63, 0x6B, 0x7F, 0x7F, 0x36, 0x00],
    'x': [0x00, 0x00, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x00],
    'y': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x0C, 0x78],
    'z': [0x00, 0x00, 0x7E, 0x0C, 0x18, 0x30, 0x7E, 0x00],
}

def draw_char(x, y, char, color, size):
    if not display_on or char not in font: 
        return
    bitmap = font[char]
    for row in range(8):
        byte = bitmap[row]
        for col in range(8):
            if byte & (0x80 >> col):
                fill_rect(x + col*size, y + row*size, size, size, color)

def draw_text(x, y, text, color, size):
    if not display_on: 
        return
    for i, c in enumerate(text):
        draw_char(x + i*(8*size + 2*size), y, c.upper(), color, size)

def draw_centered(y, text, color, size):
    if not display_on: 
        return
    w = len(text) * (8*size + 2*size) - 2*size
    x = (480 - w) // 2
    draw_text(x, y, text, color, size)

def format_time(h, m):
    h_str = "0" + str(h) if h < 10 else str(h)
    m_str = "0" + str(m) if m < 10 else str(m)
    return h_str + ":" + m_str

def format_date(d, m, y):
    d_str = "0" + str(d) if d < 10 else str(d)
    m_str = "0" + str(m) if m < 10 else str(m)
    return d_str + "/" + m_str + "/" + str(y)

def hora_para_minutos(hora_str):
    """Converte hora no formato HH:MM para minutos desde meia-noite"""
    try:
        h, m = hora_str.split(":")
        return int(h) * 60 + int(m)
    except:
        return 9999  # Valor alto para eventos com hora inválida ficarem no final

def ordenar_eventos_por_horario():
    """Ordena eventos por horário (mais próximo primeiro)"""
    global events
    
    # Pega horário atual
    t = rtc.datetime()
    hora_atual = t[4] * 60 + t[5]  # Converte para minutos
    
    # Ordena eventos por proximidade com horário atual
    eventos_ordenados = []
    
    for evento in events:
        hora_evento = hora_para_minutos(evento.get('hora', ''))
        diferenca = hora_evento - hora_atual
        
        # Se o evento já passou hoje, considera para amanhã (adiciona 24h)
        if diferenca < 0:
            diferenca += 24 * 60
            
        eventos_ordenados.append((diferenca, evento))
    
    # Ordena por diferença de tempo (mais próximo primeiro)
    eventos_ordenados.sort(key=lambda x: x[0])
    
    # Atualiza lista global mantendo apenas os eventos ordenados
    events = [evento for _, evento in eventos_ordenados]

# === BLE ===
class BLE:
    def __init__(self):
        try:
            print("Inicializando BLE...")
            self.ble = ubluetooth.BLE()
            self.ble.active(True)
            self.ble.irq(self._irq)
            
            events_char = (EVENTS_CHAR_UUID, ubluetooth.FLAG_WRITE | ubluetooth.FLAG_WRITE_NO_RESPONSE)
            response_char = (RESPONSE_CHAR_UUID, ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY)
            
            service = (SERVICE_UUID, (events_char, response_char))
            ((self.events_handle, self.response_handle),) = self.ble.gatts_register_services((service,))
            
            self._advertise()
            print("BLE inicializado!")
            
        except Exception as e:
            print("ERRO BLE: " + str(e))
    
    def _advertise(self):
        try:
            name = b'MagicMirror'
            payload = bytearray()
            payload.extend(b'\x02\x01\x06')
            payload.extend(bytes([len(name) + 1, 0x09]) + name)
            self.ble.gap_advertise(100, payload)
        except Exception as e:
            print("Erro anuncio: " + str(e))
    
    def _irq(self, event, data):
        global ble_connected, message_buffer
        
        try:
            if event == 1:
                ble_connected = True
                print("Cliente conectado!")
                
            elif event == 2:
                ble_connected = False
                print("Cliente desconectado!")
                self._advertise()
                
            elif event == 3:
                conn_handle, attr_handle = data
                if attr_handle == self.events_handle:
                    written_data = self.ble.gatts_read(attr_handle)
                    self._handle_received_data(written_data)
                    
        except Exception as e:
            print("Erro IRQ: " + str(e))
    
    def _handle_received_data(self, data):
        global message_buffer
        
        try:
            chunk = data.decode('utf-8')
            message_buffer += chunk
            
            while '\n' in message_buffer:
                line, message_buffer = message_buffer.split('\n', 1)
                line = line.strip()
                
                if line and line.startswith('{'):
                    self._process_json_message(line)
                    
        except Exception as e:
            print("Erro dados: " + str(e))
    
    def _process_json_message(self, json_str):
        global events
        
        try:
            message = ujson.loads(json_str)
            action = message.get("action", "")
            
            print("Recebido: " + action)
            
            if action == "ping":
                print("Ping - enviando Pong")
                
            elif action == "sync_events":
                new_events = message.get("events", [])
                server_date = message.get("date", "")
                count = message.get("count", 0)
                
                print("Recebidos " + str(count) + " eventos do servidor para " + server_date)
                
                # Pega a data atual do RTC (a que esta sendo exibida na tela)
                t = rtc.datetime()
                current_year = t[0]
                current_month = t[1] 
                current_day = t[2]
                
                # Formata data atual no formato YYYY-MM-DD
                current_date_str = str(current_year) + "-" + ("0" + str(current_month) if current_month < 10 else str(current_month)) + "-" + ("0" + str(current_day) if current_day < 10 else str(current_day))
                
                print("Data na tela: " + current_date_str)
                
                # Filtra eventos apenas para a data sendo exibida na tela
                events = []
                for event in new_events:
                    event_date = event.get('data', '')
                    if event_date == current_date_str:
                        events.append(event)
                
                # Ordena eventos por horário
                ordenar_eventos_por_horario()
                
                # Limita a 5 eventos
                events = events[:5]
                
                print("Eventos filtrados e ordenados para hoje (" + current_date_str + "): " + str(len(events)))
                for i, event in enumerate(events):
                    nome = event.get('nome', 'Sem nome')
                    hora = event.get('hora', '--:--')
                    print("  " + str(i+1) + ". " + hora + " - " + nome)
                
        except Exception as e:
            print("Erro JSON: " + str(e))

# === CONTROLES ===
last_time = {'h': None, 'm': None, 's': None}
last_date = {'d': None, 'm': None, 'y': None}
last_events_display = []
last_ble = None
last_btn = 1

def update_display():
    global last_time, last_date, last_events_display, last_ble
    
    if not display_on: 
        return
    
    try:
        t = rtc.datetime()
        h, m, s = t[4], t[5], t[6]
        d, mo, y = t[2], t[1], t[0]
        
        # Posições do relógio
        pos_h = 80
        pos_m = 200
        pos_s = 320
        
        # Atualiza horas se mudou
        if h != last_time['h']:
            fill_rect(pos_h, 80, 80, 40, BLACK)
            h_str = "0" + str(h) if h < 10 else str(h)
            draw_text(pos_h, 80, h_str, WHITE, 4)
            last_time['h'] = h
        
        # Atualiza minutos se mudou
        if m != last_time['m']:
            fill_rect(pos_m, 80, 80, 40, BLACK)
            m_str = "0" + str(m) if m < 10 else str(m)
            draw_text(pos_m, 80, m_str, WHITE, 4)
            last_time['m'] = m
            
            # Reordena eventos a cada mudança de minuto
            ordenar_eventos_por_horario()
        
        # Atualiza segundos se mudou
        if s != last_time['s']:
            fill_rect(pos_s, 80, 80, 40, BLACK)
            s_str = "0" + str(s) if s < 10 else str(s)
            draw_text(pos_s, 80, s_str, WHITE, 4)
            last_time['s'] = s
        
        # Atualiza data se mudou
        if d != last_date['d'] or mo != last_date['m'] or y != last_date['y']:
            fill_rect(120, 140, 240, 25, BLACK)
            date_str = format_date(d, mo, y)
            draw_centered(140, date_str, WHITE, 2)
            last_date = {'d': d, 'm': mo, 'y': y}
        
        # Atualiza status BLE se mudou
        if ble_connected != last_ble:
            fill_rect(10, 10, 50, 20, BLACK)
            draw_text(10, 10, "BLE", GREEN if ble_connected else RED, 2)
            last_ble = ble_connected
        
        # Verifica se lista de eventos mudou
        eventos_atuais = []
        for evt in events[:4]:  # Máximo 4 eventos para caber na tela
            eventos_atuais.append({
                'nome': evt.get('nome', ''),
                'hora': evt.get('hora', '')
            })
        
        # Só redesenha se a lista mudou
        if eventos_atuais != last_events_display:
            # Limpa área dos eventos
            fill_rect(10, 180, 460, 130, BLACK)
            
            if eventos_atuais:
                # Título
                draw_centered(185, "PROXIMOS EVENTOS", CYAN, 2)
                
                # Lista de eventos (máximo 4 para caber na tela)
                y_inicial = 210
                altura_linha = 22
                
                for i, evt in enumerate(eventos_atuais):
                    if i >= 4:  # Limita a 4 eventos
                        break
                        
                    nome = evt['nome']
                    hora = evt['hora']
                    
                    if nome and hora:
                        y_pos = y_inicial + (i * altura_linha)
                        
                        # Trunca nome se muito longo
                        max_chars = 35  # Máximo de caracteres por linha
                        nome_display = nome[:max_chars] + "..." if len(nome) > max_chars else nome
                        
                        # Monta texto da linha: HORA - NOME
                        linha_texto = hora + " - " + nome_display
                        
                        # Desenha linha do evento
                        draw_text(15, y_pos, linha_texto, WHITE, 1)
                        
                        print("Evento " + str(i+1) + ": " + linha_texto)
                
                print("Total de eventos exibidos: " + str(min(len(eventos_atuais), 4)))
                
            else:
                # Sem eventos
                draw_centered(205, "SEM EVENTOS HOJE", WHITE, 2)
                draw_centered(230, "ADICIONE VIA APP", CYAN, 2)
            
            last_events_display = eventos_atuais[:]  # Copia a lista
    
    except Exception as e:
        print("Erro update_display: " + str(e))

def check_button():
    global last_btn, display_on, last_time, last_date, last_events_display, last_ble
    
    try:
        b = btn.value()
        if last_btn == 1 and b == 0:
            display_on = not display_on
            status = "ON" if display_on else "OFF"
            print("Display: " + status)
            
            if display_on:
                fill_rect(0, 0, 480, 320, BLACK)
                draw_text(160, 80, ":", WHITE, 4)
                draw_text(280, 80, ":", WHITE, 4)
                
                last_time = {'h': None, 'm': None, 's': None}
                last_date = {'d': None, 'm': None, 'y': None}
                last_events_display = []
                last_ble = None
            else:
                fill_rect(0, 0, 480, 320, BLACK)
        
        last_btn = b
        
    except Exception as e:
        print("Erro botao: " + str(e))

# === INICIALIZACAO ===
print("=" * 50)
print("MAGIC MIRROR - INICIALIZANDO")
print("=" * 50)

inicializar_horario()

print("Inicializando LCD...")
init_lcd()

print("Tela inicial...")
fill_rect(0, 0, 480, 320, BLACK)
draw_centered(100, "BEM-VINDO", WHITE, 4)
draw_centered(150, "INICIALIZANDO...", CYAN, 2)
utime.sleep(2)

print("Inicializando eventos...")
inicializar_eventos()
utime.sleep(1)

print("Iniciando BLE...")
ble_handler = BLE()
utime.sleep(1)

print("Interface principal...")
fill_rect(0, 0, 480, 320, BLACK)
draw_text(160, 80, ":", WHITE, 4)
draw_text(280, 80, ":", WHITE, 4)

print("SISTEMA PRONTO!")
print("=" * 50)

# === LOOP PRINCIPAL ===
loop_count = 0

while True:
    try:
        check_button()
        update_display()
        
        loop_count += 1
        if loop_count % 150 == 0:
            ble_status = "ON" if ble_connected else "OFF"
            print("Status: BLE=" + ble_status + ", Eventos=" + str(len(events)))
        
        utime.sleep_ms(200)
        
        if loop_count % 50 == 0:
            gc.collect()
            
    except KeyboardInterrupt:
        print("Interrompido")
        break
        
    except Exception as e:
        print("ERRO: " + str(e))
        utime.sleep(1)
        
        try:
            if display_on:
                fill_rect(0, 0, 480, 320, BLACK)
                draw_centered(160, "ERRO - REINICIANDO", RED, 2)
                utime.sleep(2)
                
                fill_rect(0, 0, 480, 320, BLACK)
                draw_text(160, 80, ":", WHITE, 4)
                draw_text(280, 80, ":", WHITE, 4)
                
                last_time = {'h': None, 'm': None, 's': None}
                last_date = {'d': None, 'm': None, 'y': None}
                last_events_display = []
                last_ble = None
        except:
            pass

print("Finalizado")
