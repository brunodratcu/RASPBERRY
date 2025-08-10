# main.py - Pico W + ILI9488 (480x320) + fetch de eventos
import network, utime
import ntptime
import urequests as requests
from machine import Pin, SPI
import ili9948
import vga1_8x16 as font

# ===== CONFIG =====
SSID = "SEU_SSID"
PASSWORD = "SUA_SENHA"
SERVER_IP = "192.168.0.100"   # IP do seu servidor Flask
SERVER_URL = "http://{}:5000".format(SERVER_IP)
TOKEN = "COLE_AQUI_O_TOKEN"  # gerado por generate_pico_token.py
POLL_INTERVAL = 15  # segundos

# ===== Wi-Fi =====
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        start = utime.time()
        while not wlan.isconnected():
            utime.sleep(0.5)
            if utime.time() - start > 20:
                break
    print("WiFi:", wlan.ifconfig())

# ===== Hora =====
def sync_time():
    try:
        ntptime.settime()
    except Exception as e:
        print("NTP falhou:", e)

# ===== HTTP =====
def fetch_events():
    url = SERVER_URL + "/api/eventos-hoje"
    headers = {"Authorization": "Bearer {}".format(TOKEN)}
    try:
        r = requests.get(url, headers=headers)
        data = r.json()
        r.close()
        return data
    except Exception as e:
        print("Erro fetch:", e)
        return []

# ===== Inicializa Display ILI9488 =====
spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
tft = ili9948.ILI9488(
    spi=spi,
    cs=Pin(9, Pin.OUT),
    dc=Pin(8, Pin.OUT),
    rst=Pin(12, Pin.OUT),
    width=480,
    height=320,
    rot=0  # 0 ou 1 dependendo da orientação desejada
)

# ===== Função de desenho =====
def draw(events):
    tft.fill(0x0000)  # preto
    tt = utime.localtime()
    time_str = "{:02d}:{:02d}:{:02d}".format(tt[3], tt[4], tt[5])
    date_str = "{:02d}/{:02d}/{:04d}".format(tt[2], tt[1], tt[0])

    tft.text(font, "Hora: " + time_str, 10, 10, ili9XXX.color565(0, 255, 255), 0x0000)
    tft.text(font, "Data: " + date_str, 10, 30, ili9XXX.color565(0, 255, 255), 0x0000)

    y = 60
    tft.text(font, "Eventos de Hoje:", 10, y, ili9XXX.color565(255, 255, 0), 0x0000)
    y += 20
    if not events:
        tft.text(font, "- nenhum -", 10, y, ili9XXX.color565(255, 0, 0), 0x0000)
    else:
        for ev in events:
            linha = "{} {}".format(ev.get("hora", ""), ev.get("nome", ""))
            tft.text(font, linha[:40], 10, y, ili9XXX.color565(255, 255, 255), 0x0000)
            y += 18
            if y > 300:
                break

# ===== Loop principal =====
def main():
    connect_wifi()
    sync_time()
    last = None
    while True:
        events = fetch_events()
        if events != last:
            draw(events)
            last = events
        for _ in range(POLL_INTERVAL):
            utime.sleep(1)

if __name__ == "__main__":
    main()
