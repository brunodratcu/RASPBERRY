import network
import urequests
import utime
from machine import Pin, SPI
import ili9341  # biblioteca da tela TFT ILI9341
import vga1_8x16 as font  # fonte compatível

# ======== CONFIG WIFI ========
SSID = 'SEU_WIFI'
PASSWORD = 'SENHA_WIFI'
SERVER_URL = 'http://SEU_SERVIDOR:5000/api/eventos-hoje'

# ======== CONEXÃO COM A TELA TFT ========
spi = SPI(1, baudrate=20000000, sck=Pin(10), mosi=Pin(11))
display = ili9341.ILI9341(spi, cs=Pin(13), dc=Pin(14), rst=Pin(15),
                          width=320, height=240, rotation=90)

# ======== CONECTAR AO WIFI ========
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    print("Conectando ao Wi-Fi...", end="")
    while not wlan.isconnected():
        print(".", end="")
        utime.sleep(1)
    print("\nWi-Fi conectado! IP:", wlan.ifconfig()[0])

# ======== FORMATADOR DE DATA ========
def formatar_data():
    t = utime.localtime()
    return "{:02d}/{:02d}/{:04d}".format(t[2], t[1], t[0])

def formatar_hora():
    t = utime.localtime()
    return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])

# ======== FUNÇÃO PARA ATUALIZAR A TELA ========
def atualizar_tela(eventos):
    display.fill(ili9341.color565(0, 0, 0))  # fundo preto

    hora = formatar_hora()
    data = formatar_data()

    display.text(font, "Hora: " + hora, 10, 10, ili9341.color565(0, 255, 0))
    display.text(font, "Data: " + data, 10, 30, ili9341.color565(0, 255, 255))

    display.text(font, "Eventos de hoje:", 10, 60, ili9341.color565(255, 255, 0))

    y = 80
    if eventos:
        for evento in eventos:
            texto = f"{evento['hora']} - {evento['nome']}"
            display.text(font, texto[:40], 10, y, ili9341.color565(255, 255, 255))
            y += 20
    else:
        display.text(font, "Nenhum evento.", 10, y, ili9341.color565(255, 0, 0))

# ======== LOOP PRINCIPAL ========
def main():
    conectar_wifi()

    while True:
        try:
            resposta = urequests.get(SERVER_URL)
            eventos = resposta.json()
            resposta.close()

            atualizar_tela(eventos)

        except Exception as e:
            print("Erro ao buscar eventos:", e)
            display.fill(ili9341.color565(0, 0, 0))
            display.text(font, "Erro de conexao.", 10, 10, ili9341.color565(255, 0, 0))

        utime.sleep(15)

main()
