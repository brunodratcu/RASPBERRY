"""import network
import time
import urequests
from time import localtime
from machine import Pin, SPI
from ili9488 import Display  # Certifique-se de ter a biblioteca micropython-ili9488

# ======== CONFIG Wi-Fi ========
SSID = "lPhone de Bruno"
PASSWORD = "deniederror"
URL_JSON = "http://127.0.0.1:5000/api/eventos"  # Troque pelo endereço real

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

"""
import time
import ujson
import gc
from umqtt.simple import MQTTClient
from time import localtime
from machine import Pin, SPI, unique_id, UART
import ili9488
import ubinascii

# ======== CONFIGURAÇÕES MQTT VIA SERIAL ========
MQTT_BROKER = "broker.hivemq.com"  # Broker gratuito
MQTT_PORT = 1883
MQTT_KEEP_ALIVE = 60

# Gerar ID único para este Pico
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
CLIENT_ID = f"pico2w_{DEVICE_ID}"
TOPIC_BASE = f"eventos_pico/{CLIENT_ID}"

# Tópicos MQTT
TOPIC_EVENTO = f"{TOPIC_BASE}/evento"
TOPIC_COMANDO = f"{TOPIC_BASE}/comando"
TOPIC_STATUS = f"{TOPIC_BASE}/status"
TOPIC_ACK = f"{TOPIC_BASE}/ack"

# ======== CONFIGURAÇÕES TELA ILI9488 ========
# Ajuste os pinos conforme sua ligação física
spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = ili9488.Display(spi, dc=Pin(12), cs=Pin(13), rst=Pin(14))

# ======== CONFIGURAÇÕES SERIAL (UART) ========
# Para comunicação com dispositivo que tem WiFi/Internet
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

# ======== VARIÁVEIS GLOBAIS ========
eventos_hoje = []
mqtt_connected = False
last_status_time = 0
STATUS_INTERVAL = 60  # Enviar status a cada 30 segundos
serial_buffer = ""

# ======== FUNÇÃO: Comunicação Serial ========
def ler_dados_serial():
    """Lê dados da porta serial"""
    global serial_buffer
    
    if uart.any():
        data = uart.read().decode('utf-8', 'ignore')
        serial_buffer += data
        
        # Procurar por linha completa (terminada com \n)
        while '\n' in serial_buffer:
            linha, serial_buffer = serial_buffer.split('\n', 1)
            linha = linha.strip()
            
            if linha:
                processar_comando_serial(linha)

def processar_comando_serial(comando):
    """Processa comando recebido via serial"""
    try:
        if comando.startswith('MQTT:'):
            # Comando MQTT recebido via serial
            mqtt_data = comando[5:]  # Remove 'MQTT:'
            data = ujson.loads(mqtt_data)
            
            tipo = data.get('tipo')
            payload = data.get('payload', {})
            
            if tipo == 'evento':
                processar_evento(payload)
            elif tipo == 'comando':
                processar_comando(payload)
            elif tipo == 'status_request':
                enviar_status_serial()
                
            print(f"Comando MQTT via serial processado: {tipo}")
            
        elif comando == 'STATUS':
            enviar_status_serial()
            
        elif comando == 'RESET':
            reiniciar_sistema()
            
    except Exception as e:
        print(f"Erro ao processar comando serial: {e}")

def enviar_serial(dados):
    """Envia dados via serial"""
    try:
        linha = ujson.dumps(dados) + '\n'
        uart.write(linha.encode())
        print(f"Enviado via serial: {dados}")
    except Exception as e:
        print(f"Erro ao enviar via serial: {e}")

def enviar_status_serial():
    """Envia status via serial"""
    status_data = {
        'tipo': 'status',
        'client_id': CLIENT_ID,
        'name': f'Pico_ILI9488_{DEVICE_ID[-6:]}',
        'display': 'ILI9488',
        'eventos_count': len(eventos_hoje),
        'memoria_livre': gc.mem_free(),
        'timestamp': time.time(),
        'versao': '3.0-MQTT-SERIAL',
        'topicos': {
            'evento': TOPIC_EVENTO,
            'comando': TOPIC_COMANDO,
            'status': TOPIC_STATUS,
            'ack': TOPIC_ACK
        }
    }
    
    enviar_serial(status_data)

# ======== PROCESSAMENTO DE EVENTOS ========
def processar_evento(data):
    """Processa evento recebido"""
    global eventos_hoje
    
    try:
        acao = data.get('acao', 'adicionar')
        evento_id = data.get('id')
        
        if acao == 'adicionar':
            # Verificar se é evento de hoje
            data_evento = data.get('data')
            hoje = "{:04d}-{:02d}-{:02d}".format(*localtime()[0:3])
            
            if data_evento == hoje:
                # Remover evento duplicado
                eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
                
                # Adicionar novo evento
                evento = {
                    'id': evento_id,
                    'nome': data.get('nome'),
                    'hora': data.get('hora'),
                    'data': data_evento
                }
                
                eventos_hoje.append(evento)
                
                # Ordenar por horário
                eventos_hoje.sort(key=lambda x: x['hora'])
                
                # Limitar a 8 eventos para economizar memória
                if len(eventos_hoje) > 8:
                    eventos_hoje = eventos_hoje[:8]
                
                print(f"Evento adicionado: {evento['nome']} às {evento['hora']}")
                
                # Enviar confirmação via serial
                enviar_ack_serial(evento_id)
                
                # Atualizar display
                atualizar_display()
        
        elif acao == 'deletar':
            # Remover evento específico
            eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
            print(f"Evento {evento_id} removido")
            
            # Enviar confirmação via serial
            enviar_ack_serial(evento_id)
            
            # Atualizar display
            atualizar_display()
            
    except Exception as e:
        print(f"Erro ao processar evento: {e}")

def processar_comando(data):
    """Processa comando recebido"""
    global eventos_hoje
    
    try:
        acao = data.get('acao')
        
        if acao == 'limpar':
            eventos_hoje.clear()
            print("Todos os eventos limpos")
            atualizar_display()
            
        elif acao == 'atualizar_display':
            print("Atualizando display...")
            atualizar_display()
            
        elif acao == 'status':
            enviar_status_serial()
            
        elif acao == 'reiniciar':
            reiniciar_sistema()
            
    except Exception as e:
        print(f"Erro ao processar comando: {e}")

def enviar_ack_serial(evento_id):
    """Envia confirmação de recebimento via serial"""
    ack_data = {
        'tipo': 'ack',
        'evento_id': evento_id,
        'timestamp': time.time(),
        'client_id': CLIENT_ID
    }
    
    enviar_serial(ack_data)
    print(f"ACK enviado via serial para evento {evento_id}")

# ======== FUNÇÃO: Atualizar Display ========
def atualizar_display():
    """Atualiza a tela ILI9488 com eventos do dia"""
    try:
        # Limpar tela
        display.clear()
        
        # Obter hora atual
        agora = localtime()
        hora_str = "{:02d}:{:02d}:{:02d}".format(agora[3], agora[4], agora[5])
        data_str = "{:02d}/{:02d}/{:04d}".format(agora[2], agora[1], agora[0])
        
        # Cabeçalho
        display.draw_text8x8(10, 10, f"EVENTOS - {data_str}", color=0xFFFF)
        display.draw_text8x8(10, 30, f"Hora: {hora_str}", color=0x07E0)
        
        # Linha separadora
        display.draw_hline(10, 50, 460, 0xFFFF)
        
        # Status do protocolo
        display.draw_text8x8(10, 60, "PROTOCOLO: MQTT via SERIAL", color=0x07E0)
        
        # ID do dispositivo
        display.draw_text8x8(10, 80, f"ID: {CLIENT_ID}", color=0x001F)
        
        # Informações dos tópicos
        display.draw_text8x8(10, 90, f"Base: {TOPIC_BASE}", color=0xF81F)
        
        # Linha separadora
        display.draw_hline(10, 110, 460, 0xFFFF)
        
        # Eventos
        y_pos = 130
        
        if eventos_hoje:
            display.draw_text8x8(10, y_pos, f"EVENTOS HOJE ({len(eventos_hoje)}):", color=0xFFE0)
            y_pos += 25
            
            for i, evento in enumerate(eventos_hoje):
                if y_pos > 280:  # Limite da tela
                    display.draw_text8x8(10, y_pos, "... mais eventos", color=0xF81F)
                    break
                
                # Texto do evento
                evento_texto = f"{evento['hora']} - {evento['nome']}"
                
                # Truncar se muito longo
                if len(evento_texto) > 45:
                    evento_texto = evento_texto[:42] + "..."
                
                # Cores alternadas
                cores = [0x07E0, 0x001F, 0xF800, 0xFFE0]  # Verde, Azul, Vermelho, Amarelo
                cor = cores[i % 4]
                
                display.draw_text8x8(15, y_pos, evento_texto, color=cor)
                y_pos += 20
        else:
            display.draw_text8x8(10, y_pos, "NENHUM EVENTO HOJE", color=0xF800)
            y_pos += 25
            display.draw_text8x8(10, y_pos, "Aguardando via SERIAL...", color=0x07E0)
        
        # Rodapé
        memoria = gc.mem_free()
        display.draw_text8x8(10, 300, f"Mem: {memoria}B | Broker: {MQTT_BROKER}", color=0xF81F)
        
        print(f"Display atualizado: {len(eventos_hoje)} eventos")
        
    except Exception as e:
        print(f"Erro ao atualizar display: {e}")

def reiniciar_sistema():
    """Reinicia o sistema"""
    print("Reiniciando sistema...")
    display.clear()
    display.draw_text8x8(10, 10, "REINICIANDO...", color=0xF800)
    time.sleep(2)
    
    # Limpar dados
    global eventos_hoje
    eventos_hoje.clear()
    
    # Atualizar display
    atualizar_display()
    
    print("Sistema reiniciado")

# ======== FUNÇÃO: Loop Principal ========
def loop_principal():
    """Loop principal do sistema"""
    global last_status_time
    
    print("=== SISTEMA DE EVENTOS MQTT VIA SERIAL ===")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Broker: {MQTT_BROKER}")
    print(f"Tópico Base: {TOPIC_BASE}")
    print("==========================================")
    print("Protocolo: MQTT via comunicação SERIAL")
    print("Aguardando comandos via UART...")
    print("==========================================")
    
    # Display inicial
    atualizar_display()
    
    # Enviar status inicial
    enviar_status_serial()
    
    while True:
        try:
            # Ler dados da porta serial
            ler_dados_serial()
            
            # Enviar status periodicamente
            now = time.time()
            if now - last_status_time > STATUS_INTERVAL:
                enviar_status_serial()
                last_status_time = now
            
            # Atualizar display periodicamente
            if int(time.time()) % 60 == 0:  # A cada minuto
                atualizar_display()
                time.sleep(1)  # Evitar múltiplas atualizações no mesmo segundo
            
            # Pequena pausa para não sobrecarregar
            time.sleep_ms(10)
            
        except KeyboardInterrupt:
            print("\nSistema interrompido pelo usuário")
            break
            
        except Exception as e:
            print(f"Erro inesperado: {e}")
            time.sleep(1)
    
    print("Sistema finalizado")

# ======== PROGRAMA PRINCIPAL ========
def main():
    """Função principal"""
    try:
        print("Iniciando sistema MQTT via SERIAL...")
        
        # Configurar UART
        print(f"UART configurado: TX=Pin(0), RX=Pin(1), Baudrate=115200")
        
        # Inicializar display
        print("Inicializando display ILI9488...")
        display.clear()
        display.draw_text8x8(10, 10, "INICIANDO SISTEMA...", color=0xFFFF)
        display.draw_text8x8(10, 30, "MQTT via SERIAL", color=0x07E0)
        display.draw_text8x8(10, 50, f"ID: {CLIENT_ID}", color=0x001F)
        
        print("Sistema inicializado com sucesso!")
        print("\nInformações dos tópicos MQTT:")
        print(f"  - Eventos: {TOPIC_EVENTO}")
        print(f"  - Comandos: {TOPIC_COMANDO}")
        print(f"  - Status: {TOPIC_STATUS}")
        print(f"  - ACK: {TOPIC_ACK}")
        print("\nFormato de comando serial:")
        print("MQTT:{\"tipo\":\"evento\",\"payload\":{\"id\":1,\"nome\":\"Teste\",\"hora\":\"14:30\",\"data\":\"2025-08-17\",\"acao\":\"adicionar\"}}")
        print("\nComandos diretos:")
        print("STATUS - Solicita status")
        print("RESET - Reinicia sistema")
        
        # Iniciar loop principal
        loop_principal()
        
    except Exception as e:
        print(f"Erro crítico no main: {e}")
        # Tentar mostrar erro na tela
        try:
            display.clear()
            display.draw_text8x8(10, 10, "ERRO CRITICO:", color=0xF800)
            display.draw_text8x8(10, 30, str(e)[:50], color=0xF800)
            display.draw_text8x8(10, 50, "Verifique conexao serial", color=0xFFE0)
        except:
            pass

# Executar programa principal
if __name__ == "__main__":
    main()