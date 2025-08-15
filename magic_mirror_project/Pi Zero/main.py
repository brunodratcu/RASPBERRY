import network
import time
import urequests
from time import localtime
from machine import Pin, SPI
from ili9488 import Display  # Certifique-se de ter a biblioteca micropython-ili9488

# ======== CONFIG Wi-Fi ========
SSID = "lPhone de Bruno"
PASSWORD = "deniederror"
URL_JSON = "http://SEU_SERVIDOR/api/eventos.json"  # Troque pelo endereço real

# ======== CONFIG TELA ILI9488 ========
# Pinos SPI e controle (ajuste conforme sua ligação física)
spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = Display(spi, dc=Pin(12), cs=Pin(13), rst=Pin(14))

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
    evento = busca_evento(URL_JSON)
    mostrar_evento(evento)
    time.sleep(60)  # Atualiza a cada 1 minuto
