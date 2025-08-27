import bluetooth
import time
import json
import ubinascii
from machine import Pin, I2C, unique_id
import asyncio

# Configurações BLE
BLE_SERVICE_UUID = bluetooth.UUID("94f39d29-7d6d-437d-973b-fba39e49d4ee")
BLE_CHAR_UUID = bluetooth.UUID("94f39d29-7d6d-437d-973b-fba39e49d4ef")

# ID único do dispositivo
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
DEVICE_NAME = f"MagicMirror-{DEVICE_ID[-6:]}"

print(f"Device: {DEVICE_NAME}")
print(f"ID: {DEVICE_ID}")

# Display (opcional)
try:
    from ssd1306 import SSD1306_I2C
    i2c = I2C(0, sda=Pin(0), scl=Pin(1))
    display = SSD1306_I2C(128, 64, i2c)
    DISPLAY_AVAILABLE = True
    print("Display SSD1306 inicializado")
except:
    DISPLAY_AVAILABLE = False
    print("Display não disponível - usando console")

class BLEClient:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        
        self.connected = False
        self.connection = None
        self.char_handle = None
        self.eventos = []
        
        # Registra callbacks
        self.ble.irq(self.ble_irq_handler)
        
    def ble_irq_handler(self, event, data):
        """Handler para eventos BLE"""
        if event == bluetooth._IRQ_SCAN_RESULT:
            # Resultado do scan
            addr_type, addr, connectable, rssi, adv_data = data
            if self.decode_name(adv_data) and "Magic Mirror" in self.decode_name(adv_data):
                print(f"Servidor encontrado: {ubinascii.hexlify(addr).decode()}")
                self.ble.gap_scan(None)  # Para o scan
                self.connect_to_server(addr_type, addr)
                
        elif event == bluetooth._IRQ_SCAN_DONE:
            print("Scan finalizado")
            
        elif event == bluetooth._IRQ_PERIPHERAL_CONNECT:
            # Conectado
            conn_handle, addr_type, addr = data
            self.connection = conn_handle
            print("Conectado via BLE")
            self.discover_services()
            
        elif event == bluetooth._IRQ_PERIPHERAL_DISCONNECT:
            # Desconectado
            self.connected = False
            self.connection = None
            self.char_handle = None
            print("Desconectado do servidor BLE")
            
        elif event == bluetooth._IRQ_GATTC_SERVICE_RESULT:
            # Serviço descoberto
            conn_handle, start_handle, end_handle, uuid = data
            if uuid == BLE_SERVICE_UUID:
                print("Serviço Magic Mirror encontrado")
                self.discover_characteristics(start_handle, end_handle)
                
        elif event == bluetooth._IRQ_GATTC_CHARACTERISTIC_RESULT:
            # Característica descoberta
            conn_handle, def_handle, value_handle, properties, uuid = data
            if uuid == BLE_CHAR_UUID:
                self.char_handle = value_handle
                print("Característica encontrada")
                self.connected = True
                self.send_device_info()
                
        elif event == bluetooth._IRQ_GATTC_NOTIFY:
            # Dados recebidos
            conn_handle, value_handle, notify_data = data
            self.process_received_data(notify_data)
    
    def decode_name(self, adv_data):
        """Decodifica nome do dispositivo dos dados de advertisement"""
        try:
            i = 0
            while i < len(adv_data):
                length = adv_data[i]
                if length == 0:
                    break
                ad_type = adv_data[i + 1]
                if ad_type == 0x08 or ad_type == 0x09:  # Nome completo ou parcial
                    return adv_data[i + 2:i + 1 + length].decode('utf-8')
                i += 1 + length
        except:
            pass
        return None
    
    def start_scan(self):
        """Inicia scan por dispositivos BLE"""
        print("Procurando servidor Magic Mirror...")
        self.ble.gap_scan(10000, 30000, 30000)  # 10s scan
    
    def connect_to_server(self, addr_type, addr):
        """Conecta ao servidor"""
        try:
            self.ble.gap_connect(addr_type, addr)
        except Exception as e:
            print(f"Erro ao conectar: {e}")
    
    def discover_services(self):
        """Descobre serviços do servidor"""
        if self.connection:
            self.ble.gattc_discover_services(self.connection)
    
    def discover_characteristics(self, start_handle, end_handle):
        """Descobre características do serviço"""
        if self.connection:
            self.ble.gattc_discover_characteristics(self.connection, start_handle, end_handle)
    
    def send_data(self, data):
        """Envia dados para o servidor"""
        if self.connected and self.char_handle:
            try:
                json_data = json.dumps(data)
                # BLE tem limite de MTU, divide mensagens grandes
                self.send_chunks(json_data)
                return True
            except Exception as e:
                print(f"Erro ao enviar: {e}")
                return False
        return False
    
    def send_chunks(self, data):
        """Envia dados em pedaços para respeitar MTU"""
        chunk_size = 20  # MTU padrão - headers
        chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                chunk += "\n"  # Marca fim da mensagem
            
            self.ble.gattc_write(self.connection, self.char_handle, chunk.encode(), 1)
            time.sleep_ms(10)  # Pequeno delay entre chunks
    
    def send_device_info(self):
        """Envia informações do dispositivo"""
        device_info = {
            "action": "device_info",
            "device_id": DEVICE_ID,
            "name": DEVICE_NAME,
            "firmware_version": "2.0.0-BLE",
            "capabilities": ["display", "events", "ble"],
            "protocol": "ble",
            "timestamp": time.time()
        }
        
        self.send_data(device_info)
        print("Device info enviado")
    
    def process_received_data(self, data):
        """Processa dados recebidos do servidor"""
        try:
            message_str = data.decode('utf-8')
            
            # Reconstrói mensagens divididas em chunks
            if not hasattr(self, 'message_buffer'):
                self.message_buffer = ""
            
            self.message_buffer += message_str
            
            # Processa mensagens completas (terminam com \n)
            while '\n' in self.message_buffer:
                line, self.message_buffer = self.message_buffer.split('\n', 1)
                if line.strip():
                    self.process_message(line.strip())
                    
        except Exception as e:
            print(f"Erro ao processar dados: {e}")
    
    def process_message(self, message_str):
        """Processa mensagem JSON recebida"""
        try:
            message = json.loads(message_str)
            action = message.get("action", "")
            
            print(f"Recebido: {action}")
            
            if action == "handshake":
                print("Handshake recebido")
                
            elif action == "sync_events":
                self.eventos = message.get("events", [])
                print(f"Sincronizados {len(self.eventos)} eventos")
                self.update_display()
                self.confirm_sync()
                
            elif action == "add_event":
                evento = message.get("event", {})
                self.eventos.append(evento)
                print(f"+ {evento.get('nome', 'Evento')}")
                self.update_display()
                
            elif action == "remove_event":
                event_id = message.get("event_id")
                self.eventos = [e for e in self.eventos if e.get("id") != event_id]
                print(f"- Evento {event_id}")
                self.update_display()
                
            elif action == "remove_all_events":
                self.eventos = []
                print("Todos os eventos removidos")
                self.update_display()
                
            elif action == "ping":
                self.send_data({
                    "action": "ping_response",
                    "device_id": DEVICE_ID,
                    "timestamp": time.time()
                })
                
        except Exception as e:
            print(f"Erro ao processar mensagem: {e}")
    
    def confirm_sync(self):
        """Confirma sincronização"""
        self.send_data({
            "action": "sync_complete",
            "device_id": DEVICE_ID,
            "events_count": len(self.eventos),
            "timestamp": time.time()
        })
    
    def update_display(self):
        """Atualiza display com eventos"""
        if not DISPLAY_AVAILABLE:
            print("\n=== AGENDA DE HOJE ===")
            if not self.eventos:
                print("Nenhum evento")
            else:
                for evento in self.eventos:
                    hora = evento.get('hora', '??:??')
                    nome = evento.get('nome', 'Evento')
                    print(f"{hora} - {nome}")
            print("=" * 22)
            return
        
        try:
            # Limpa display
            display.fill(0)
            
            # Título
            display.text("AGENDA HOJE", 0, 0, 1)
            display.hline(0, 10, 128, 1)
            
            # Eventos (máximo 5)
            y_pos = 15
            for i, evento in enumerate(self.eventos[:5]):
                hora = evento.get('hora', '??:??')[:5]
                nome = evento.get('nome', 'Evento')[:12]  # Limite do display
                
                display.text(f"{hora} {nome}", 0, y_pos, 1)
                y_pos += 10
            
            # Mensagens de status
            if len(self.eventos) == 0:
                display.text("Sem eventos", 0, 25, 1)
            elif len(self.eventos) > 5:
                display.text(f"+{len(self.eventos)-5} mais", 0, y_pos, 1)
            
            # Status da conexão
            status = "OK" if self.connected else "OFF"
            display.text(f"BLE:{status}", 85, 55, 1)
            
            # Atualiza display
            display.show()
            
        except Exception as e:
            print(f"Erro no display: {e}")

def main():
    """Função principal"""
    print("=== MAGIC MIRROR BLE CLIENT ===")
    print(f"Dispositivo: {DEVICE_NAME}")
    
    client = BLEClient()
    
    # Loop principal
    while True:
        if not client.connected:
            print("Tentando conectar...")
            client.start_scan()
            
            # Aguarda conexão
            timeout = 30  # 30 segundos
            while not client.connected and timeout > 0:
                time.sleep(1)
                timeout -= 1
            
            if not client.connected:
                print("Timeout - tentando novamente em 10s...")
                time.sleep(10)
        else:
            # Conectado - mantém vivo
            time.sleep(5)

# Executa
main()
