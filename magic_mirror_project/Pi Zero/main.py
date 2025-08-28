import machine
import utime
import ujson
import ubluetooth
import gc
from machine import Pin, Timer

# Hardware - sem prints
rst = Pin(16, Pin.OUT, value=1)
cs = Pin(17, Pin.OUT, value=1) 
rs = Pin(15, Pin.OUT, value=0)
wr = Pin(19, Pin.OUT, value=1)
rd = Pin(18, Pin.OUT, value=1)
data = [Pin(i, Pin.OUT) for i in range(8)]
btn = Pin(21, Pin.IN, Pin.PULL_UP)

# Variáveis
running = True
events = []
time_str = "12:34"
date_str = "25/12/24"
ble_on = False
initialized = False

# Cores
WHITE, GREEN, RED, YELLOW, GRAY, BLACK = 0xFFFF, 0x07E0, 0xF800, 0xFFE0, 0x7BEF, 0x0000

def write_byte(b):
    for i in range(8):
        data[i].value(b & (1 << i))

def cmd(c):
    cs.value(0); rs.value(0); write_byte(c)
    wr.value(0); wr.value(1); cs.value(1)

def dat(d):
    cs.value(0); rs.value(1)
    if isinstance(d, list):
        for b in d:
            write_byte(b); wr.value(0); wr.value(1)
    else:
        write_byte(d); wr.value(0); wr.value(1)
    cs.value(1)

def init_lcd():
    global initialized
    rst.value(0); utime.sleep_ms(50); rst.value(1); utime.sleep_ms(50)
    cmd(0x3A); dat(0x55)
    cmd(0x36); dat(0x48)
    cmd(0x11); utime.sleep_ms(100)
    cmd(0x29)
    initialized = True
    clear()

def set_area(x0, y0, x1, y1):
    cmd(0x2A); dat([x0>>8, x0&0xFF, x1>>8, x1&0xFF])
    cmd(0x2B); dat([y0>>8, y0&0xFF, y1>>8, y1&0xFF])
    cmd(0x2C)

def fill(x, y, w, h, color):
    if not initialized or w <= 0 or h <= 0:
        return
    set_area(x, y, x+w-1, y+h-1)
    hi, lo = color >> 8, color & 0xFF
    cs.value(0); rs.value(1)
    for _ in range(w*h):
        write_byte(hi); wr.value(0); wr.value(1)
        write_byte(lo); wr.value(0); wr.value(1)
    cs.value(1)

def clear():
    if initialized:
        for i in range(16):
            fill(0, i*30, 320, 30, BLACK)

def char(x, y, c, color, size):
    w = 6 * size
    if c == ':':
        fill(x+2*size, y+2*size, 2*size, 2*size, color)
        fill(x+2*size, y+5*size, 2*size, 2*size, color)
    elif c == '/':
        for i in range(8*size):
            fill(x+i//2, y+i, 1, 1, color)
    elif c.isdigit() or c.isalpha():
        fill(x, y, w, 8*size, color)

def text(x, y, txt, color, size):
    for i, c in enumerate(str(txt)[:15]):
        char(x + i*6*size, y, c, color, size)

def centerx(txt, size):
    return (320 - len(str(txt))*6*size) // 2

class FastBLE:
    def __init__(self):
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)
        self.buf = ""
        
        char = (ubluetooth.UUID("00002a00-0000-1000-8000-00805f9b34fb"), ubluetooth.FLAG_WRITE)
        svc = (ubluetooth.UUID("00001800-0000-1000-8000-00805f9b34fb"), (char,))
        ((self.handle,),) = self.ble.gatts_register_services((svc,))
        
        self.ble.gap_advertise(100, b'\x02\x01\x06\x0c\x09MagicMirror')
    
    def _irq(self, event, data):
        global ble_on, events
        
        if event == 1:  # CENTRAL_CONNECT
            ble_on = True
        elif event == 2:  # CENTRAL_DISCONNECT
            ble_on = False
            self.ble.gap_advertise(100, b'\x02\x01\x06\x0c\x09MagicMirror')
        elif event == 3:  # GATTS_WRITE
            try:
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
                        elif action == "remove_all_events":
                            events = []
            except:
                pass

def update_time():
    global time_str, date_str
    t = utime.localtime()
    time_str = f"{t[3]:02d}:{t[4]:02d}"
    date_str = f"{t[2]:02d}/{t[1]:02d}/{t[0]-2000}"

def update_screen():
    if not running or not initialized:
        return
    
    # Limpa áreas
    fill(0, 80, 320, 50, BLACK)
    fill(0, 140, 320, 30, BLACK)
    fill(0, 220, 320, 60, BLACK)
    fill(0, 430, 150, 30, BLACK)
    
    # Hora
    text(centerx(time_str, 4), 100, time_str, WHITE, 4)
    
    # Data  
    text(centerx(date_str, 2), 160, date_str, WHITE, 2)
    
    # Evento
    if events:
        evt = events[0]
        text(centerx("EVENTO", 1), 230, "EVENTO", GREEN, 1)
        hora = evt.get("hora", "")
        if hora:
            text(centerx(hora, 2), 250, hora, YELLOW, 2)
        nome = str(evt.get("nome", ""))[:12]
        if nome:
            text(centerx(nome, 1), 270, nome, WHITE, 1)
    else:
        text(centerx("Sem eventos", 1), 250, "Sem eventos", GRAY, 1)
    
    # BLE
    status = "BLE:ON" if ble_on else "BLE:OFF"
    color = GREEN if ble_on else RED
    text(10, 440, status, color, 1)

def check_btn():
    global running
    if not btn.value():
        utime.sleep_ms(50)
        if not btn.value():
            while not btn.value():
                utime.sleep_ms(5)
            running = not running
            if running:
                update_screen()
            else:
                clear()

def timer_cb(t):
    update_time()
    if running:
        update_screen()
    gc.collect()

# Boot rápido
print("BOOT")
gc.collect()
print("LCD INIT")
init_lcd()
print("BLE INIT") 
ble = FastBLE()
print("TIMER START")
timer = Timer(mode=Timer.PERIODIC, period=2000, callback=timer_cb)
update_time()
update_screen()
print("READY")

# Loop
while True:
    check_btn()
    utime.sleep_ms(50)
