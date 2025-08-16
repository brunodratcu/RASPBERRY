import network
import time
import urequests
from time import localtime
from machine import Pin, SPI
from ili9488 import Display  # Biblioteca micropython-ili9488

# ======== CONFIG Wi-Fi ========
SSID = "lPhone de Bruno"
PASSWORD = "deniederror"
URL_JSON = "http://SEU_SERVIDOR/api/eventos.json"  # Troque pelo endereço real

# ======== CONFIG TELA ILI9488 ========
spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = Display(spi, dc=Pin(12), cs=Pin(13), rst=Pin(14))

# ======== CONFIG BOTÃO INTERRUPTOR (gangorra) ========
# Conecte um lado do botão ao GND e o outro no GPIO escolhido (exemplo: GPIO15)
# Ativa PULL_UP -> botão pressionado = 0 / solto = 1
botao = Pin(15, Pin.IN, Pin.PULL_UP)

# ======== FUNÇÃO: Conectar Wi-Fi ========
def conecta_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    
    print("Conectando ao Wi-Fi...")
    while not wlan.isconnected():
        time.sleep(1)
        print("Tentando...")
    
    ip = wlan.ifconfig()[0]
    print("Conectado com sucesso! IP Local:", ip)
    return ip

# ======== FUNÇÃO: Buscar evento do dia ========
def busca_evento(url):
    try:
        r = urequests.get(url)
        dados = r.json()
        r.close()

        hoje = "{:04d}-{:02d}-{:02d}".format(*localtime()[0:3])
        
        for item in dados:
            if item["data"] == hoje:
                return item
        return None
    except Exception as e:
        print("Erro ao buscar JSON:", e)
        return None

# ======== FUNÇÃO: Mostrar evento na tela ========
def mostrar_evento(evento):
    display.clear()
    
    agora = localtime()
    hora_str = "{:02d}:{:02d}:{:02d}".format(agora[3], agora[4], agora[5])
    data_str = "{:04d}-{:02d}-{:02d}".format(agora[0], agora[1], agora[2])
    
    if evento:
        texto_evento = evento["evento"]
        texto_hora_evento = evento["hora"]
    else:
        texto_evento = "Nenhum evento hoje"
        texto_hora_evento = "--:--"
    
    # Desenha texto na tela
    display.draw_text8x8(10, 10, "Hora: " + hora_str, color=0xFFFF)
    display.draw_text8x8(10, 30, "Data: " + data_str, color=0xFFFF)
    display.draw_text8x8(10, 50, "Evento:", color=0xFFE0)
    display.draw_text8x8(10, 70, texto_evento, color=0xFFE0)
    display.draw_text8x8(10, 90, "Horario evento: " + texto_hora_evento, color=0xF800)

# ======== PROGRAMA PRINCIPAL ========
ip_local = conecta_wifi()

while True:
    if botao.value() == 0:  # Botão ligado (nível baixo porque está em PULL_UP)
        evento = busca_evento(URL_JSON)
        mostrar_evento(evento)
    else:
        # Se o botão estiver desligado -> apaga a tela
        display.clear()
        display.draw_text8x8(50, 120, "MagicMirror OFF", color=0xF800)
    
    time.sleep(1)  # Checa a cada 1s
