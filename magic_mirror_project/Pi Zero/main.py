import time
import ujson as json
import gc
import ubinascii
from time import localtime
from machine import Pin, SPI, UART, unique_id

# ======== CONFIGURAÇÕES LORA SX1278 433MHz ========
# SPI0 para comunicação com módulo LoRa SX1278
spi_lora = SPI(0, baudrate=5000000, sck=Pin(4), mosi=Pin(3), miso=Pin(2))
cs_lora = Pin(5, Pin.OUT, value=1)
rst_lora = Pin(6, Pin.OUT, value=1)
dio0 = Pin(7, Pin.IN)  # Interrupt DIO0
dio1 = Pin(8, Pin.IN)  # Interrupt DIO1 (opcional)

# ID único do dispositivo
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
CLIENT_ID = f"magic_mirror_pico_{DEVICE_ID}"

# Configurações LoRa
LORA_FREQUENCY = 433_000_000  # 433MHz
LORA_BANDWIDTH = 125_000     # 125kHz
LORA_SPREADING_FACTOR = 7    # SF7
LORA_CODING_RATE = 5         # 4/5
LORA_POWER = 20              # 20dBm
LORA_PREAMBLE = 8            # Símbolos preâmbulo

# ======== HARDWARE ILI9486 ========
# Display ILI9486 - SPI1
spi_display = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))

# Simulação básica do driver ILI9486 (você deve usar uma biblioteca real)
class ILI9486Display:
    def __init__(self, spi, dc, cs, rst):
        self.spi = spi
        self.dc = dc
        self.cs = cs
        self.rst = rst
        self.width = 480
        self.height = 320
        self._init_display()
    
    def _init_display(self):
        # Reset display
        self.rst.value(0)
        time.sleep_ms(10)
        self.rst.value(1)
        time.sleep_ms(120)
        print("Display ILI9486 inicializado")
    
    def fill(self, color):
        # Simula limpeza da tela
        pass
    
    def draw_text8x8(self, x, y, text, color):
        # Simula texto 8x8
        pass
    
    def draw_text16x32(self, x, y, text, color):
        # Simula texto 16x32
        pass
    
    def draw_hline(self, x, y, length, color):
        # Simula linha horizontal
        pass

display = ILI9486Display(spi_display, dc=Pin(15), cs=Pin(13), rst=Pin(14))

# Botão gangorra (Liga/Desliga)
botao_gangorra = Pin(21, Pin.IN, Pin.PULL_UP)
led_status = Pin(25, Pin.OUT)

# ======== VARIÁVEIS GLOBAIS ========
eventos_hoje = []
system_on = True
lora_connected = False

# Controle do botão gangorra
last_switch_state = None
debounce_time = 0
show_welcome = False
welcome_start_time = 0

# Controle de exclusão automática por horário
last_time_check = 0

# Estatísticas LoRa
last_rssi = 0
last_snr = 0.0
packets_received = 0
packets_sent = 0

# Buffer para recepção
rx_buffer = bytearray(256)

# Cores RGB565 para ILI9486
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
GRAY = 0x7BEF

# ======== REGISTRADORES SX1278 ========
# Registradores principais do SX1278
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08
REG_PA_CONFIG = 0x09
REG_LNA = 0x0C
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_TX_BASE_ADDR = 0x0E
REG_FIFO_RX_BASE_ADDR = 0x0F
REG_FIFO_RX_CURRENT_ADDR = 0x10
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_SNR_VALUE = 0x19
REG_PKT_RSSI_VALUE = 0x1A
REG_MODEM_CONFIG_1 = 0x1D
REG_MODEM_CONFIG_2 = 0x1E
REG_PREAMBLE_MSB = 0x20
REG_PREAMBLE_LSB = 0x21
REG_PAYLOAD_LENGTH = 0x22
REG_MODEM_CONFIG_3 = 0x26
REG_DIO_MAPPING_1 = 0x40
REG_VERSION = 0x42
REG_PA_DAC = 0x4D

# Modos de operação
MODE_LONG_RANGE_MODE = 0x80
MODE_SLEEP = 0x00
MODE_STDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05
MODE_RX_SINGLE = 0x06

# ======== COMUNICAÇÃO SX1278 ========
def spi_write(reg, value):
    """Escreve valor em registrador do SX1278"""
    cs_lora.value(0)
    spi_lora.write(bytearray([reg | 0x80, value]))
    cs_lora.value(1)

def spi_read(reg):
    """Lê valor de registrador do SX1278"""
    cs_lora.value(0)
    result = spi_lora.write_readinto(bytearray([reg & 0x7F, 0x00]), rx_buffer[:2])
    cs_lora.value(1)
    return rx_buffer[1]

def inicializar_lora():
    """Inicializa módulo LoRa SX1278"""
    global lora_connected
    
    try:
        # Reset do módulo
        rst_lora.value(0)
        time.sleep_ms(10)
        rst_lora.value(1)
        time.sleep_ms(10)
        
        # Verifica versão do chip
        version = spi_read(REG_VERSION)
        if version != 0x12:
            print(f"SX1278 não encontrado. Versão: 0x{version:02X}")
            return False
        
        print("SX1278 detectado com sucesso")
        
        # Entra em modo sleep
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP)
        
        # Configura parâmetros LoRa
        configurar_parametros_lora()
        
        # Entra em modo standby
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)
        
        lora_connected = True
        print(f"LoRa inicializado: {LORA_FREQUENCY/1000000:.1f}MHz")
        return True
        
    except Exception as e:
        lora_connected = False
        print(f"Erro ao inicializar LoRa: {e}")
        return False

def configurar_parametros_lora():
    """Configura parâmetros do LoRa"""
    
    # Configura frequência
    frf = int((LORA_FREQUENCY << 19) // 32000000)
    spi_write(REG_FRF_MSB, (frf >> 16) & 0xFF)
    spi_write(REG_FRF_MID, (frf >> 8) & 0xFF)
    spi_write(REG_FRF_LSB, frf & 0xFF)
    
    # Configura potência de transmissão
    spi_write(REG_PA_CONFIG, 0x80 | (LORA_POWER - 2))  # PA_BOOST
    spi_write(REG_PA_DAC, 0x87)  # High power mode
    
    # Configura parâmetros do modem
    # Bandwidth = 125kHz, Coding Rate = 4/5, Implicit Header Mode = off
    spi_write(REG_MODEM_CONFIG_1, 0x70 | ((LORA_CODING_RATE - 4) << 1))
    
    # Spreading Factor = 7, TX Continuous Mode = off, RX Payload CRC = on, Symb Timeout MSB = 00
    spi_write(REG_MODEM_CONFIG_2, (LORA_SPREADING_FACTOR << 4) | 0x04)
    
    # Low Data Rate Optimize = off, AGC Auto = on
    spi_write(REG_MODEM_CONFIG_3, 0x04)
    
    # Configura preâmbulo
    spi_write(REG_PREAMBLE_MSB, (LORA_PREAMBLE >> 8) & 0xFF)
    spi_write(REG_PREAMBLE_LSB, LORA_PREAMBLE & 0xFF)
    
    # Configura DIO0 para TxDone/RxDone
    spi_write(REG_DIO_MAPPING_1, 0x00)
    
    # Configura endereços base FIFO
    spi_write(REG_FIFO_TX_BASE_ADDR, 0x80)
    spi_write(REG_FIFO_RX_BASE_ADDR, 0x00)

def enviar_lora(payload):
    """Envia dados via LoRa"""
    global packets_sent
    
    if not lora_connected:
        return False
    
    try:
        # Monta pacote com cabeçalho
        packet = {
            "src": 1,  # Endereço do Pico
            "dst": 0,  # Endereço do servidor
            "msg_id": packets_sent,
            "data": payload
        }
        
        # Converte para JSON compacto
        message = json.dumps(packet, separators=(',', ':'))
        
        # Limita tamanho
        if len(message) > 200:
            payload_compactado = compactar_payload_pico(payload)
            packet["data"] = payload_compactado
            message = json.dumps(packet, separators=(',', ':'))
        
        message_bytes = message.encode('utf-8')
        
        # Envia via LoRa
        if transmitir_lora(message_bytes):
            packets_sent += 1
            print(f"Enviado LoRa: {payload.get('action', 'unknown')} ({len(message_bytes)} bytes)")
            return True
        else:
            return False
        
    except Exception as e:
        print(f"Erro envio LoRa: {e}")
        return False

def transmitir_lora(data):
    """Transmite dados pelo SX1278"""
    try:
        # Entra em modo standby
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)
        
        # Limpa flag de IRQ
        spi_write(REG_IRQ_FLAGS, 0xFF)
        
        # Configura payload length
        payload_length = len(data)
        if payload_length > 255:
            payload_length = 255
            data = data[:255]
        
        spi_write(REG_PAYLOAD_LENGTH, payload_length)
        
        # Configura FIFO pointer
        spi_write(REG_FIFO_ADDR_PTR, 0x80)
        
        # Escreve dados no FIFO
        cs_lora.value(0)
        spi_lora.write(bytearray([REG_FIFO | 0x80]))
        spi_lora.write(data)
        cs_lora.value(1)
        
        # Entra em modo TX
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_TX)
        
        # Aguarda transmissão (timeout 5 segundos)
        timeout = time.ticks_ms() + 5000
        while time.ticks_ms() < timeout:
            irq_flags = spi_read(REG_IRQ_FLAGS)
            if irq_flags & 0x08:  # TxDone
                spi_write(REG_IRQ_FLAGS, 0x08)  # Limpa flag
                # Volta para modo standby
                spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)
                return True
            time.sleep_ms(1)
        
        print("Timeout na transmissão LoRa")
        return False
        
    except Exception as e:
        print(f"Erro transmissão LoRa: {e}")
        return False

def receber_lora():
    """Verifica se há dados recebidos via LoRa"""
    global packets_received, last_rssi, last_snr
    
    try:
        # Verifica se há dados disponíveis
        irq_flags = spi_read(REG_IRQ_FLAGS)
        
        if irq_flags & 0x40:  # RxDone
            # Limpa flag
            spi_write(REG_IRQ_FLAGS, 0x40)
            
            # Verifica CRC
            if irq_flags & 0x20:  # PayloadCrcError
                print("Erro CRC no pacote LoRa")
                iniciar_recepcao()
                return None
            
            # Lê tamanho do payload
            payload_length = spi_read(REG_RX_NB_BYTES)
            
            # Lê endereço atual do FIFO
            current_addr = spi_read(REG_FIFO_RX_CURRENT_ADDR)
            spi_write(REG_FIFO_ADDR_PTR, current_addr)
            
            # Lê dados do FIFO
            cs_lora.value(0)
            spi_lora.write(bytearray([REG_FIFO & 0x7F]))
            received_data = bytearray(payload_length)
            spi_lora.readinto(received_data)
            cs_lora.value(1)
            
            # Lê RSSI e SNR
            last_rssi = spi_read(REG_PKT_RSSI_VALUE) - 137
            snr_value = spi_read(REG_PKT_SNR_VALUE)
            last_snr = snr_value / 4.0 if snr_value & 0x80 == 0 else (snr_value - 256) / 4.0
            
            packets_received += 1
            
            # Reinicia recepção
            iniciar_recepcao()
            
            # Processa dados recebidos
            try:
                message = received_data.decode('utf-8')
                packet = json.loads(message)
                return packet
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"Erro decodificação LoRa: {e}")
                return None
        
        return None
        
    except Exception as e:
        print(f"Erro recepção LoRa: {e}")
        return None

def iniciar_recepcao():
    """Inicia modo de recepção contínua"""
    try:
        # Entra em modo standby
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)
        
        # Limpa flags de IRQ
        spi_write(REG_IRQ_FLAGS, 0xFF)
        
        # Configura FIFO para recepção
        spi_write(REG_FIFO_ADDR_PTR, 0x00)
        
        # Entra em modo RX contínuo
        spi_write(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_CONTINUOUS)
        
    except Exception as e:
        print(f"Erro ao iniciar recepção: {e}")

def compactar_payload_pico(payload):
    """Compacta payload para economizar bytes"""
    try:
        if "action" in payload:
            compact = {"a": payload["action"]}
            
            if "device_id" in payload:
                compact["d"] = payload["device_id"][-8:]
            
            if "event_id" in payload:
                compact["e"] = payload["event_id"]
            
            if "timestamp" in payload:
                compact["t"] = int(time.time())
            
            for key in ["completion_reason", "events_count", "status"]:
                if key in payload:
                    compact[key[0]] = payload[key]
            
            return compact
        
        return payload
        
    except Exception as e:
        print(f"Erro compactação: {e}")
        return payload

def processar_mensagem_lora(packet):
    """Processa mensagem LoRa recebida"""
    try:
        # Verifica se pacote é para este dispositivo
        dst_addr = packet.get("dst", 255)
        if dst_addr != 1 and dst_addr != 255:  # 1 = endereço do Pico, 255 = broadcast
            return
        
        # Extrai payload
        payload = packet.get("data", packet)
        
        # Processa ações
        action = payload.get("action") or payload.get("a")
        
        if action == "add_event":
            processar_adicionar_evento_lora(payload)
        elif action == "remove_event":
            processar_remover_evento_lora(payload)
        elif action == "sync_events":
            processar_sincronizacao_lora(payload)
        elif action == "clear_events":
            eventos_hoje.clear()
            atualizar_tela()
        elif action == "ping_response":
            lora_connected = True
            print("Pong LoRa recebido")
        elif action == "system_command":
            processar_comando_sistema_lora(payload)
            
        # Atualiza tela se sistema ligado
        if system_on and not show_welcome:
            atualizar_tela()
            
    except Exception as e:
        print(f"Erro processar mensagem LoRa: {e}")

def processar_adicionar_evento_lora(payload):
    """Processa evento adicionado via LoRa - VERIFICA SE É HOJE"""
    global eventos_hoje
    
    try:
        event_data = payload.get("event", {})
        
        # IMPORTANTE: Verifica se evento é de hoje
        data_evento = event_data.get("data", "")
        hoje = obter_data_hoje()
        
        if data_evento != hoje:
            print(f"Evento não é de hoje ({data_evento} != {hoje}) - ignorado")
            return
        
        evento = {
            "id": event_data.get("id"),
            "nome": event_data.get("nome", "")[:40],
            "hora": event_data.get("hora", ""),
            "data": data_evento
        }
        
        # Remove duplicata se existir
        eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento["id"]]
        eventos_hoje.append(evento)
        
        # Ordena por hora
        eventos_hoje.sort(key=lambda x: x.get("hora", ""))
        
        print(f"Evento HOJE adicionado: {evento['nome']} às {evento['hora']}")
        
        # Confirma recebimento
        enviar_confirmacao_lora(event_data.get("id"), "received")
        
        # LED confirmação
        piscar_led(2)
        
    except Exception as e:
        print(f"Erro adicionar evento LoRa: {e}")

def processar_remover_evento_lora(payload):
    """Processa evento removido via LoRa"""
    global eventos_hoje
    
    try:
        evento_id = payload.get("event_id") or payload.get("e")
        eventos_antes = len(eventos_hoje)
        eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
        
        if len(eventos_hoje) < eventos_antes:
            print(f"Evento {evento_id} removido via LoRa")
            enviar_confirmacao_lora(evento_id, "removed")
            piscar_led(1)
        
    except Exception as e:
        print(f"Erro remover evento LoRa: {e}")

def processar_sincronizacao_lora(payload):
    """Processa sincronização completa via LoRa - APENAS EVENTOS DE HOJE"""
    global eventos_hoje
    
    try:
        # Verifica data de filtro
        filter_date = payload.get("filter_date", "")
        hoje = obter_data_hoje()
        
        if filter_date and filter_date != hoje:
            print(f"Sincronização não é para hoje ({filter_date} != {hoje}) - ignorada")
            return
        
        # Substitui lista completa
        new_events = payload.get("events", [])
        eventos_hoje = []
        eventos_hoje_count = 0
        
        for event_data in new_events:
            # Verifica novamente se evento é de hoje
            data_evento = event_data.get("data", event_data.get("d", ""))
            
            if data_evento == hoje:
                evento = {
                    "id": event_data.get("id", event_data.get("i")),
                    "nome": (event_data.get("nome", event_data.get("n", "")))[:40],
                    "hora": event_data.get("hora", event_data.get("h", "")),
                    "data": data_evento
                }
                eventos_hoje.append(evento)
                eventos_hoje_count += 1
        
        # Ordena por hora
        eventos_hoje.sort(key=lambda x: x.get("hora", ""))
        
        print(f"Sincronização LoRa: {eventos_hoje_count} eventos de hoje recebidos")
        
        # Confirma sincronização
        enviar_lora({
            "action": "sync_complete",
            "device_id": CLIENT_ID,
            "events_count": len(eventos_hoje),
            "timestamp": time.time()
        })
        
        piscar_led(3)
        
    except Exception as e:
        print(f"Erro sincronização LoRa: {e}")

def processar_comando_sistema_lora(payload):
    """Processa comandos do sistema via LoRa"""
    global system_on
    
    try:
        command = payload.get("command", "")
        
        if command == "power_on" and not system_on:
            ligar_sistema()
        elif command == "power_off" and system_on:
            desligar_sistema()
        elif command == "restart":
            import machine
            machine.reset()
        elif command == "get_info":
            enviar_info_dispositivo_lora()
        elif command == "ping":
            enviar_ping_lora()
            
    except Exception as e:
        print(f"Erro comando sistema LoRa: {e}")

def enviar_confirmacao_lora(evento_id, action):
    """Envia confirmação de ação via LoRa"""
    payload = {
        "action": "event_ack",
        "device_id": CLIENT_ID,
        "event_id": evento_id,
        "ack_action": action,
        "timestamp": time.time()
    }
    enviar_lora(payload)

def enviar_ping_lora():
    """Envia ping via LoRa"""
    payload = {
        "action": "ping",
        "device_id": CLIENT_ID,
        "timestamp": time.time(),
        "signal_rssi": last_rssi,
        "signal_snr": last_snr
    }
    enviar_lora(payload)

def enviar_status_lora():
    """Envia status do dispositivo via LoRa"""
    payload = {
        "action": "device_status",
        "device_id": CLIENT_ID,
        "status": "online" if system_on else "sleep",
        "events_count": len(eventos_hoje),
        "free_memory": gc.mem_free(),
        "packets_rx": packets_received,
        "packets_tx": packets_sent,
        "rssi": last_rssi,
        "snr": last_snr,
        "timestamp": time.time()
    }
    enviar_lora(payload)

def enviar_info_dispositivo_lora():
    """Envia informações completas do dispositivo via LoRa"""
    payload = {
        "action": "device_info",
        "device_id": CLIENT_ID,
        "name": f"Magic Mirror {DEVICE_ID[-6:]}",
        "firmware_version": "2.0.0-LoRa433",
        "display_type": "ili9486_3.5",
        "display_resolution": "480x320",
        "lora_frequency": int(LORA_FREQUENCY / 1000000),
        "lora_power": LORA_POWER,
        "capabilities": {
            "has_display": True,
            "has_buttons": 1,
            "auto_remove_events": True,
            "communication": "lora_433mhz",
            "today_filter": True
        },
        "system_status": "online" if system_on else "sleep",
        "events_count": len(eventos_hoje),
        "uptime": time.ticks_ms(),
        "free_memory": gc.mem_free(),
        "signal_quality": {
            "rssi": last_rssi,
            "snr": last_snr,
            "packets_rx": packets_received,
            "packets_tx": packets_sent
        },
        "timestamp": time.time()
    }
    enviar_lora(payload)

def obter_data_hoje():
    """Obtém data de hoje no formato YYYY-MM-DD"""
    try:
        agora = localtime()
        return "{:04d}-{:02d}-{:02d}".format(agora[0], agora[1], agora[2])
    except:
        return "2024-01-01"

# ======== EXCLUSÃO AUTOMÁTICA POR HORÁRIO ========
def verificar_eventos_vencidos():
    """Verifica e remove eventos que já passaram do horário - APENAS HOJE"""
    global eventos_hoje, last_time_check
    
    current_time = time.ticks_ms()
    
    # Verifica apenas a cada 30 segundos
    if current_time - last_time_check < 30000:
        return False
    
    last_time_check = current_time
    
    # Pega hora atual
    try:
        agora = localtime()
        hora_atual = "{:02d}:{:02d}".format(agora[3], agora[4])
        data_hoje = obter_data_hoje()
    except:
        return False
    
    eventos_removidos = 0
    eventos_restantes = []
    
    for evento in eventos_hoje:
        hora_evento = evento.get("hora", "")
        data_evento = evento.get("data", "")
        
        # Remove apenas se for evento de hoje E já passou da hora
        if data_evento == data_hoje and hora_evento and hora_evento < hora_atual:
            # Notifica servidor da remoção automática
            enviar_evento_concluido_lora(evento.get("id"), "expired")
            eventos_removidos += 1
            print(f"Evento vencido removido: {evento.get('nome')} ({hora_evento})")
        else:
            eventos_restantes.append(evento)
    
    # Atualiza lista se houve mudanças
    if eventos_removidos > 0:
        eventos_hoje = eventos_restantes
        piscar_led(1)
        return True
    
    return False

def enviar_evento_concluido_lora(evento_id, reason="manual"):
    """Notifica servidor que evento foi concluído via LoRa"""
    payload = {
        "action": "event_completed",
        "device_id": CLIENT_ID,
        "event_id": evento_id,
        "completion_reason": reason,
        "timestamp": time.time()
    }
    enviar_lora(payload)

# ======== CONTROLE DO BOTÃO GANGORRA ========
def verificar_botao_gangorra():
    """Verifica estado do botão gangorra (Liga/Desliga)"""
    global system_on, show_welcome, last_switch_state, debounce_time, welcome_start_time
    
    current_time = time.ticks_ms()
    current_state = botao_gangorra.value()
    
    # Debounce: ignora mudanças muito rápidas
    if current_time - debounce_time < 300:
        return
    
    # Verifica mudança de estado
    if current_state != last_switch_state:
        debounce_time = current_time
        last_switch_state = current_state
        
        if current_state == 0:  # Botão pressionado (ON)
            if not system_on:
                # Liga sistema com tela de boas-vindas
                system_on = True
                show_welcome = True
                welcome_start_time = current_time
                mostrar_tela_bem_vindo()
                piscar_led(2)
                enviar_status_lora()
                
        else:  # Botão solto (OFF)
            if system_on:
                # Desliga sistema imediatamente
                desligar_sistema()

def mostrar_tela_bem_vindo():
    """Mostra tela de boas-vindas por 2 segundos"""
    display.fill(BLACK)
    
    # "BEM-VINDO" grande e centralizado
    texto = "BEM-VINDO"
    largura_texto = len(texto) * 14
    x_pos = (480 - largura_texto) // 2
    y_pos = (320 - 32) // 2
    
    display.draw_text16x32(x_pos, y_pos, texto, WHITE)
    
    # Informação LoRa
    display.draw_text8x8(160, y_pos + 50, "Sistema LoRa 433MHz", YELLOW)
    
    print("Tela BEM-VINDO exibida")

def verificar_tempo_bem_vindo():
    """Verifica se deve sair da tela de boas-vindas"""
    global show_welcome, welcome_start_time
    
    if show_welcome:
        current_time = time.ticks_ms()
        if current_time - welcome_start_time >= 2000:  # 2 segundos
            show_welcome = False
            atualizar_tela()
            print("Saindo da tela BEM-VINDO para agenda")

def desligar_sistema():
    global system_on, show_welcome
    
    print("Desligando sistema...")
    
    # Desliga imediatamente
    system_on = False
    show_welcome = False
    
    # Tela preta
    display.fill(BLACK)
    
    # LED apagado
    led_status.value(0)
    
    # Notifica servidor
    enviar_status_lora()
    
    print("Sistema desligado - tela preta")

def piscar_led(vezes=3):
    for _ in range(vezes):
        led_status.value(1)
        time.sleep_ms(100)
        led_status.value(0)
        time.sleep_ms(100)

# ======== INTERFACE VISUAL ILI9486 ========
def atualizar_tela():
    """Atualiza interface baseada no estado atual"""
    
    # Se sistema desligado: tela preta
    if not system_on:
        display.fill(BLACK)
        led_status.value(0)
        return
    
    # Se em modo boas-vindas: não atualizar
    if show_welcome:
        led_status.value(1)
        return
    
    # Modo normal: mostra agenda
    led_status.value(1)
    
    # Limpa tela
    display.fill(BLACK)
    
    # Data e hora no topo
    desenhar_data_hora()
    
    # Linha separadora
    display.draw_hline(20, 90, 440, WHITE)
    
    # Lista de eventos
    desenhar_eventos()
    
    # Instruções na parte inferior
    desenhar_instrucoes()
    
    # Status LoRa
    desenhar_status_lora()

def desenhar_data_hora():
    # Pega hora atual
    try:
        agora = localtime()
        hora_str = "{:02d}:{:02d}:{:02d}".format(agora[3], agora[4], agora[5])
        data_str = "{:02d}/{:02d}/{:04d}".format(agora[2], agora[1], agora[0])
    except:
        hora_str = "--:--:--"
        data_str = "--/--/----"
    
    # Título "Minha agenda"
    display.draw_text16x32(140, 10, "Minha agenda", WHITE)
    
    # Hora grande e centralizada
    display.draw_text16x32(160, 45, hora_str, WHITE)
    
    # Data menor abaixo
    display.draw_text8x8(200, 75, data_str, GRAY)

def desenhar_eventos():
    y_pos = 110
    
    if eventos_hoje:
        # Título da seção
        display.draw_text8x8(20, y_pos, "EVENTOS DE HOJE:", WHITE)
        y_pos += 25
        
        # Lista eventos (máximo 9 visíveis)
        for i, evento in enumerate(eventos_hoje[:9]):
            if y_pos > 260:
                display.draw_text8x8(20, y_pos, "... mais eventos", GRAY)
                break
            
            # Todos os eventos com mesmo destaque
            cor_texto = WHITE
            evento_texto = f"{evento.get('hora', '--:--')} - {evento.get('nome', 'Sem nome')}"
            
            # Trunca texto se muito longo
            if len(evento_texto) > 50:
                evento_texto = evento_texto[:47] + "..."
            
            display.draw_text8x8(30, y_pos, evento_texto, cor_texto)
            y_pos += 16
            
    else:
        display.draw_text8x8(20, y_pos, "NENHUM EVENTO HOJE", GRAY)
        y_pos += 20
        display.draw_text8x8(20, y_pos, "Aguardando sincronizacao LoRa...", GRAY)

def desenhar_instrucoes():
    # Instruções de uso na parte inferior
    y_base = 270
    
    display.draw_text8x8(20, y_base, "CONTROLES:", WHITE)
    display.draw_text8x8(20, y_base + 15, "Botao Gangorra: Liga/Desliga sistema", GREEN)
    display.draw_text8x8(20, y_base + 30, "Eventos removidos automaticamente", BLUE)

def desenhar_status_lora():
    # Status LoRa na parte inferior
    y_status = 305
    
    # Monta string de status
    status_text = f"Eventos: {len(eventos_hoje)} | "
    
    if lora_connected:
        # Qualidade do sinal
        if last_rssi > -70:
            signal_quality = "Forte"
            cor_sinal = GREEN
        elif last_rssi > -90:
            signal_quality = "Medio"
            cor_sinal = YELLOW
        else:
            signal_quality = "Fraco"
            cor_sinal = RED
        
        status_text += f"LoRa: {signal_quality} ({last_rssi}dBm)"
        display.draw_text8x8(20, y_status, status_text, cor_sinal)
    else:
        status_text += "LoRa: OFFLINE"
        display.draw_text8x8(20, y_status, status_text, RED)

# ======== LOOP PRINCIPAL ========
def main():
    global system_on, show_welcome, lora_connected
    
    # Tela de inicialização
    display.fill(BLACK)
    display.draw_text16x32(140, 80, "Minha agenda", WHITE)
    display.draw_text8x8(160, 120, "ILI9486 3.5\" - LoRa 433MHz", YELLOW)
    display.draw_text8x8(160, 140, f"ID: {DEVICE_ID[-8:]}", GRAY)
    display.draw_text8x8(170, 170, "Iniciando...", WHITE)
    
    time.sleep(2)
    
    # Inicializa LoRa
    display.draw_text8x8(170, 190, "LoRa 433MHz...", YELLOW)
    if inicializar_lora():
        display.draw_text8x8(280, 190, "OK", GREEN)
        # Inicia recepção
        iniciar_recepcao()
        # Envia informações do dispositivo
        time.sleep(1)
        enviar_info_dispositivo_lora()
    else:
        display.draw_text8x8(280, 190, "ERRO", RED)
    
    time.sleep(2)
    
    # Sistema pronto
    display.draw_text8x8(160, 220, "Sistema Pronto!", GREEN)
    display.draw_text8x8(130, 240, f"Freq: {int(LORA_FREQUENCY/1000000)}MHz | SF: {LORA_SPREADING_FACTOR}", BLUE)
    display.draw_text8x8(120, 260, "Botao gangorra: Liga/Desliga", GRAY)
    
    # LED indicação de pronto
    piscar_led(5)
    
    time.sleep(2)
    
    # Sistema inicia DESLIGADO
    system_on = False
    show_welcome = False
    display.fill(BLACK)
    led_status.value(0)
    
    print("Sistema pronto - DESLIGADO")
    print("Pressione botao gangorra para ligar")
    print(f"LoRa: {int(LORA_FREQUENCY/1000000)}MHz, SF{LORA_SPREADING_FACTOR}, {LORA_POWER}dBm")
    
    # Loop principal
    last_update = 0
    last_heartbeat = 0
    last_ping = 0
    
    while True:
        try:
            current_time = time.ticks_ms()
            
            # Lê comunicação LoRa sempre
            if lora_connected:
                packet = receber_lora()
                if packet:
                    processar_mensagem_lora(packet)
            
            # Verifica botão gangorra sempre
            verificar_botao_gangorra()
            
            # Verifica tempo de boas-vindas
            if show_welcome:
                verificar_tempo_bem_vindo()
            
            # Processa apenas se sistema ligado e não em boas-vindas
            if system_on and not show_welcome:
                
                # Verifica eventos vencidos (apenas eventos de hoje)
                eventos_alterados = verificar_eventos_vencidos()
                
                # Atualiza tela se houve alteração ou a cada 5 segundos
                if eventos_alterados or (current_time - last_update > 5000):
                    atualizar_tela()
                    last_update = current_time
            
            # Heartbeat a cada 60 segundos
            if current_time - last_heartbeat > 60000:
                if lora_connected:
                    enviar_status_lora()
                last_heartbeat = current_time
            
            # Ping a cada 5 minutos para manter conexão
            if current_time - last_ping > 300000:  # 5 minutos
                if lora_connected:
                    enviar_ping_lora()
                last_ping = current_time
            
            # Limpeza de memória a cada 2 minutos
            if current_time % 120000 < 100:
                gc.collect()
            
            time.sleep_ms(100)  # Loop otimizado para LoRa
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Erro no loop principal: {e}")
            time.sleep(1)

# Executar programa principal
if __name__ == "__main__":
    main()