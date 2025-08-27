import bluetooth
import time
import json
import ubinascii
from machine import Pin, SPI, unique_id
import gc
import framebuf

# Configurações do dispositivo
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
DEVICE_NAME = f"MagicMirror-{DEVICE_ID[-6:]}"

# UUIDs para BLE
SERVICE_UUID = 0x1800
EVENTS_CHAR_UUID = 0x2A00

print("=" * 40)
print("MAGIC MIRROR - ILI9486 LCD")
print(f"Device: {DEVICE_NAME}")
print(f"ID: {DEVICE_ID}")
print("=" * 40)

# Driver ILI9486 3.5" LCD
class ILI9486_LCD:
    def __init__(self, spi, cs, dc, rst):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        
        # Configuração da tela
        self.width = 480   # Landscape
        self.height = 320  # Landscape
        
        # Inicializa pinos
        self.cs.init(Pin.OUT, value=1)
        self.dc.init(Pin.OUT, value=0)
        self.rst.init(Pin.OUT, value=1)
        
        # Inicializa display
        self.init_display()
        
        # Buffer de frame (reduzido para economizar RAM)
        self.buffer_width = 480
        self.buffer_height = 320
        
        print(f"Display ILI9486 inicializado: {self.width}x{self.height}")
    
    def write_cmd(self, cmd):
        """Escreve comando"""
        self.cs(0)
        self.dc(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)
    
    def write_data(self, data):
        """Escreve dados"""
        self.cs(0)
        self.dc(1)
        if isinstance(data, int):
            self.spi.write(bytearray([data]))
        else:
            self.spi.write(data)
        self.cs(1)
    
    def init_display(self):
        """Inicializa sequência ILI9486"""
        try:
            # Reset
            self.rst(0)
            time.sleep_ms(100)
            self.rst(1)
            time.sleep_ms(100)
            
            # Sequência de inicialização ILI9486
            self.write_cmd(0x01)  # Software Reset
            time.sleep_ms(120)
            
            self.write_cmd(0x11)  # Sleep Out
            time.sleep_ms(120)
            
            # Interface Pixel Format
            self.write_cmd(0x3A)
            self.write_data(0x55)  # 16-bit RGB565
            
            # Memory Access Control - Landscape
            self.write_cmd(0x36)
            self.write_data(0x28)  # MY=0, MX=0, MV=1, ML=0, BGR=1, MH=0
            
            # Display Inversion On
            self.write_cmd(0x21)
            
            # Display On
            self.write_cmd(0x29)
            time.sleep_ms(50)
            
            print("ILI9486 inicializado com sucesso")
            
        except Exception as e:
            print(f"Erro na inicialização do display: {e}")
    
    def set_window(self, x0, y0, x1, y1):
        """Define janela de escrita"""
        # Column Address Set
        self.write_cmd(0x2A)
        self.write_data(x0 >> 8)
        self.write_data(x0 & 0xFF)
        self.write_data(x1 >> 8)
        self.write_data(x1 & 0xFF)
        
        # Page Address Set
        self.write_cmd(0x2B)
        self.write_data(y0 >> 8)
        self.write_data(y0 & 0xFF)
        self.write_data(y1 >> 8)
        self.write_data(y1 & 0xFF)
        
        # Memory Write
        self.write_cmd(0x2C)
    
    def fill_screen(self, color):
        """Preenche tela com cor - versão corrigida"""
        self.set_window(0, 0, self.width - 1, self.height - 1)
        
        # Cor RGB565 
        color_high = (color >> 8) & 0xFF
        color_low = color & 0xFF
        
        # Cria buffer de linha para economizar RAM
        line_size = 100  # Pixels por chunk
        line_buffer = []
        
        for _ in range(line_size):
            line_buffer.extend([color_high, color_low])
        
        line_data = bytes(line_buffer)
        
        self.cs(0)
        self.dc(1)
        
        # Calcula quantos chunks são necessários
        total_pixels = self.width * self.height
        chunks_needed = (total_pixels + line_size - 1) // line_size
        
        for chunk in range(chunks_needed):
            pixels_remaining = min(line_size, total_pixels - (chunk * line_size))
            
            if pixels_remaining == line_size:
                # Chunk completo
                self.spi.write(line_data)
            else:
                # Último chunk parcial
                partial_buffer = []
                for _ in range(pixels_remaining):
                    partial_buffer.extend([color_high, color_low])
                self.spi.write(bytes(partial_buffer))
        
        self.cs(1)
    
    def draw_text(self, text, x, y, color, size=2):
        """Desenha texto simples (bitmap font 8x8)"""
        try:
            # Font bitmap 8x8 simplificado
            font_8x8 = {
                ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                '0': [0x3C, 0x66, 0x6E, 0x76, 0x66, 0x66, 0x3C, 0x00],
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
                '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
                'A': [0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
                'B': [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
                'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
                'D': [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
                'E': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x7E, 0x00],
                'G': [0x3C, 0x66, 0x60, 0x6E, 0x66, 0x66, 0x3C, 0x00],
                'H': [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
                'I': [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
                'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
                'N': [0x66, 0x76, 0x7E, 0x7E, 0x6E, 0x66, 0x66, 0x00],
                'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
                'R': [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
                'S': [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
                'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
                'U': [0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
                'a': [0x00, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00],
                'e': [0x00, 0x00, 0x3C, 0x66, 0x7E, 0x60, 0x3C, 0x00],
                'i': [0x0C, 0x00, 0x1C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00],
                'n': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
                'o': [0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00],
                'r': [0x00, 0x00, 0x7C, 0x66, 0x60, 0x60, 0x60, 0x00],
                's': [0x00, 0x00, 0x3E, 0x60, 0x3C, 0x06, 0x7C, 0x00],
                't': [0x10, 0x30, 0x7C, 0x30, 0x30, 0x34, 0x18, 0x00],
                'u': [0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3E, 0x00],
                'v': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
            }
            
            char_width = 8 * size
            char_height = 8 * size
            
            for i, char in enumerate(text):
                if char in font_8x8:
                    char_x = x + (i * char_width)
                    self.draw_char(char, char_x, y, color, font_8x8[char], size)
                    
        except Exception as e:
            print(f"Erro ao desenhar texto: {e}")
    
    def draw_char(self, char, x, y, color, bitmap, size):
        """Desenha um caractere"""
        try:
            for row in range(8):
                for col in range(8):
                    if bitmap[row] & (1 << (7 - col)):
                        # Desenha pixel escalado
                        for dy in range(size):
                            for dx in range(size):
                                px = x + (col * size) + dx
                                py = y + (row * size) + dy
                                if 0 <= px < self.width and 0 <= py < self.height:
                                    self.draw_pixel(px, py, color)
        except:
            pass
    
    def draw_pixel(self, x, y, color):
        """Desenha pixel individual"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.set_window(x, y, x, y)
            self.write_data(color >> 8)
            self.write_data(color & 0xFF)

# Configuração SPI para ILI9486
try:
    spi = SPI(0, baudrate=40000000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19))
    cs = Pin(17, Pin.OUT)
    dc = Pin(16, Pin.OUT)
    rst = Pin(20, Pin.OUT)
    
    display = ILI9486_LCD(spi, cs, dc, rst)
    DISPLAY_AVAILABLE = True
    print("Display ILI9486 configurado")
    
except Exception as e:
    DISPLAY_AVAILABLE = False
    print(f"Display não disponível: {e}")

# Cores RGB565
BLACK = 0x0000
WHITE = 0xFFFF
BLUE = 0x001F
GREEN = 0x07E0
RED = 0xF800
YELLOW = 0xFFE0

class MagicMirrorDisplay:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        
        # Estado BLE
        self.connected = False
        self.conn_handle = None
        self.client_address = None
        
        # Dados da agenda
        self.eventos = []
        self.current_time = None
        self.current_date = None
        self.message_buffer = ""
        
        # Configura BLE
        self.setup_ble_service()
        self.ble.irq(self.ble_irq_handler)
        
        print("Magic Mirror Display inicializado")
    
    def setup_ble_service(self):
        """Configura serviço BLE"""
        try:
            SERVICE = (
                bluetooth.UUID(SERVICE_UUID),
                (
                    (bluetooth.UUID(EVENTS_CHAR_UUID), 
                     bluetooth.FLAG_READ | bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY),
                )
            )
            
            ((self.events_char,),) = self.ble.gatts_register_services((SERVICE,))
            print(f"Serviço BLE registrado: {self.events_char}")
            
        except Exception as e:
            print(f"Erro no serviço BLE: {e}")
    
    def start_advertising(self):
        """Inicia advertising BLE"""
        try:
            name_bytes = DEVICE_NAME.encode('utf-8')[:10]
            
            adv_data = bytearray()
            adv_data.extend([0x02, 0x01, 0x06])  # Flags
            adv_data.extend([len(name_bytes) + 1, 0x09])  # Nome
            adv_data.extend(name_bytes)
            
            self.ble.gap_advertise(100000, adv_data)  # 100ms
            print(f"Advertising: {name_bytes.decode()}")
            
        except Exception as e:
            print(f"Erro advertising: {e}")
    
    def ble_irq_handler(self, event, data):
        """Handler BLE"""
        if event == bluetooth._IRQ_CENTRAL_CONNECT:
            self.conn_handle, addr_type, addr = data
            self.connected = True
            self.client_address = ubinascii.hexlify(addr, ':').decode()
            
            print(f"Servidor conectado: {self.client_address}")
            self.ble.gap_advertise(None)  # Para advertising
            self.update_display()
            
        elif event == bluetooth._IRQ_CENTRAL_DISCONNECT:
            print("Servidor desconectado")
            self.connected = False
            self.conn_handle = None
            self.client_address = None
            self.message_buffer = ""
            
            self.update_display()
            time.sleep(2)
            self.start_advertising()
            
        elif event == bluetooth._IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self.events_char:
                self.handle_push_data()
    
    def handle_push_data(self):
        """Processa dados recebidos"""
        try:
            push_data = self.ble.gatts_read(self.events_char)
            chunk = push_data.decode('utf-8')
            self.message_buffer += chunk
            
            while '\n' in self.message_buffer:
                line, self.message_buffer = self.message_buffer.split('\n', 1)
                if line.strip():
                    self.process_message(line.strip())
                    
        except Exception as e:
            print(f"Erro push data: {e}")
    
    def process_message(self, message_str):
        """Processa mensagem JSON"""
        try:
            message = json.loads(message_str)
            action = message.get("action", "")
            
            print(f"Ação recebida: {action}")
            
            if action == "sync_events":
                self.eventos = message.get("events", [])
                print(f"Eventos sincronizados: {len(self.eventos)}")
                self.update_display()
                self.send_ack("sync_complete", len(self.eventos))
                
            elif action == "add_event":
                evento = message.get("event", {})
                self.eventos.append(evento)
                nome = evento.get("nome", "Evento")
                print(f"Evento adicionado: {nome}")
                self.update_display()
                self.send_ack("event_added", evento.get("id"))
                
            elif action == "remove_event":
                event_id = message.get("event_id")
                self.eventos = [e for e in self.eventos if e.get("id") != event_id]
                print(f"Evento removido: {event_id}")
                self.update_display()
                self.send_ack("event_removed", event_id)
                
            elif action == "remove_all_events":
                self.eventos = []
                print("Todos os eventos removidos")
                self.update_display()
                self.send_ack("all_events_removed", 0)
                
            elif action == "ping":
                self.send_ack("pong", time.time())
                
        except Exception as e:
            print(f"Erro ao processar: {e}")
    
    def send_ack(self, ack_type, data):
        """Envia confirmação"""
        if not self.connected:
            return
        
        try:
            ack = {
                "action": ack_type,
                "device_id": DEVICE_ID,
                "data": data,
                "timestamp": time.time()
            }
            
            response = json.dumps(ack) + "\n"
            
            for i in range(0, len(response), 20):
                chunk = response[i:i+20]
                self.ble.gatts_write(self.events_char, chunk.encode())
                self.ble.gatts_notify(self.conn_handle, self.events_char)
                time.sleep_ms(10)
                
        except Exception as e:
            print(f"Erro ACK: {e}")
    
    def get_current_time_date(self):
        """Obtém hora e data atuais"""
        try:
            # RTC do Pico (em UTC, ajustar se necessário)
            t = time.localtime()
            
            self.current_time = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
            self.current_date = f"{t[2]:02d}/{t[1]:02d}/{t[0]}"
            
        except:
            self.current_time = "--:--:--"
            self.current_date = "--/--/----"
    
    def update_display(self):
        """Atualiza display LCD"""
        if not DISPLAY_AVAILABLE:
            self.update_console()
            return
        
        try:
            # Atualiza hora/data
            self.get_current_time_date()
            
            # Limpa tela (fundo preto)
            display.fill_screen(BLACK)
            
            # Título centralizado no topo
            title = "MAGIC MIRROR"
            title_x = (display.width - len(title) * 8 * 3) // 2  # Centralizado, fonte tamanho 3
            display.draw_text(title, title_x, 20, WHITE, 3)
            
            # Hora grande centralizada
            time_x = (display.width - len(self.current_time) * 8 * 4) // 2  # Fonte tamanho 4
            display.draw_text(self.current_time, time_x, 80, WHITE, 4)
            
            # Data centralizada abaixo da hora
            date_x = (display.width - len(self.current_date) * 8 * 2) // 2  # Fonte tamanho 2
            display.draw_text(self.current_date, date_x, 140, WHITE, 2)
            
            # Status da conexão
            status = "CONECTADO" if self.connected else "AGUARDANDO"
            status_x = (display.width - len(status) * 8 * 1) // 2
            display.draw_text(status, status_x, 170, GREEN if self.connected else YELLOW, 1)
            
            # Eventos do dia
            if self.eventos:
                eventos_title = "EVENTOS DE HOJE:"
                eventos_x = (display.width - len(eventos_title) * 8 * 2) // 2
                display.draw_text(eventos_title, eventos_x, 200, WHITE, 2)
                
                # Lista eventos (máximo 3)
                y_pos = 230
                for i, evento in enumerate(self.eventos[:3]):
                    hora = evento.get('hora', '??:??')
                    nome = evento.get('nome', 'Evento')[:25]  # Limita tamanho
                    
                    evento_text = f"{hora} - {nome}"
                    evento_x = (display.width - len(evento_text) * 8 * 1) // 2
                    display.draw_text(evento_text, evento_x, y_pos, WHITE, 1)
                    y_pos += 20
                
                # Se há mais eventos
                if len(self.eventos) > 3:
                    mais_text = f"... e mais {len(self.eventos) - 3} eventos"
                    mais_x = (display.width - len(mais_text) * 8 * 1) // 2
                    display.draw_text(mais_text, mais_x, y_pos, YELLOW, 1)
            else:
                no_events_text = "Nenhum evento para hoje"
                no_events_x = (display.width - len(no_events_text) * 8 * 2) // 2
                display.draw_text(no_events_text, no_events_x, 220, YELLOW, 2)
            
            print("Display atualizado")
            
        except Exception as e:
            print(f"Erro ao atualizar display: {e}")
    
    def update_console(self):
        """Fallback para console"""
        self.get_current_time_date()
        
        print("\n" + "=" * 50)
        print("MAGIC MIRROR")
        print(f"Hora: {self.current_time}")
        print(f"Data: {self.current_date}")
        print(f"Status: {'CONECTADO' if self.connected else 'AGUARDANDO'}")
        print("-" * 50)
        
        if self.eventos:
            print("EVENTOS DE HOJE:")
            for evento in self.eventos:
                hora = evento.get('hora', '??:??')
                nome = evento.get('nome', 'Evento')
                print(f"  {hora} - {nome}")
        else:
            print("Nenhum evento para hoje")
        
        print("=" * 50)
    
    def run(self):
        """Loop principal"""
        print("Iniciando Magic Mirror Display...")
        
        if DISPLAY_AVAILABLE:
            # Tela de inicialização
            display.fill_screen(BLACK)
            init_text = "Iniciando..."
            init_x = (display.width - len(init_text) * 8 * 2) // 2
            display.draw_text(init_text, init_x, display.height // 2, WHITE, 2)
            time.sleep(2)
        
        self.start_advertising()
        self.update_display()
        
        last_update = time.ticks_ms()
        last_gc = time.ticks_ms()
        
        try:
            while True:
                current = time.ticks_ms()
                
                # Atualiza display a cada 10 segundos
                if time.ticks_diff(current, last_update) > 10000:
                    self.update_display()
                    last_update = current
                
                # Garbage collection a cada minuto
                if time.ticks_diff(current, last_gc) > 60000:
                    gc.collect()
                    last_gc = current
                
                time.sleep_ms(100)
                
        except KeyboardInterrupt:
            print("Finalizado pelo usuário")
        except Exception as e:
            print(f"Erro no loop: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Limpeza final"""
        try:
            if DISPLAY_AVAILABLE:
                display.fill_screen(BLACK)
                bye_text = "Finalizado"
                bye_x = (display.width - len(bye_text) * 8 * 2) // 2
                display.draw_text(bye_text, bye_x, display.height // 2, WHITE, 2)
            
            self.ble.gap_advertise(None)
            self.ble.active(False)
            
        except:
            pass
        
        print("Magic Mirror finalizado")

def main():
    """Função principal"""
    try:
        mirror = MagicMirrorDisplay()
        mirror.run()
        
    except Exception as e:
        print(f"Erro fatal: {e}")
        
        if DISPLAY_AVAILABLE:
            display.fill_screen(BLACK)
            error_text = "ERRO FATAL"
            error_x = (display.width - len(error_text) * 8 * 2) // 2
            display.draw_text(error_text, error_x, display.height // 2, RED, 2)

if __name__ == "__main__":
    main()