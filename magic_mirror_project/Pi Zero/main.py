"""import time
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
STATUS_INTERVAL = 30  # Enviar status a cada 30 segundos
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
"""




import time
import ujson
import gc
from umqtt.simple import MQTTClient
from time import localtime
from machine import Pin, SPI, unique_id, UART, Timer
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

# ======== CONFIGURAÇÕES HARDWARE ========
# Pinos do display ILI9488
spi = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = ili9488.Display(spi, dc=Pin(12), cs=Pin(13), rst=Pin(14))

# UART para comunicação serial
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

# ======== CONFIGURAÇÕES DE ENERGIA ========
# Pino do botão gangorra (ON/OFF)
POWER_BUTTON_PIN = 15  # Ajuste conforme sua ligação
power_button = Pin(POWER_BUTTON_PIN, Pin.IN, Pin.PULL_UP)

# Pino do LED de status (opcional)
STATUS_LED_PIN = 25  # LED interno do Pico
status_led = Pin(STATUS_LED_PIN, Pin.OUT)

# Pino de controle do backlight (se disponível)
BACKLIGHT_PIN = 2  # Ajuste conforme seu hardware
try:
    backlight = Pin(BACKLIGHT_PIN, Pin.OUT, value=1)
    backlight_available = True
except:
    backlight_available = False
    print("⚠️ Controle de backlight não disponível")

# ======== VARIÁVEIS GLOBAIS DE ENERGIA ========
display_ligado = True           # Estado do display
sistema_ativo = True           # Estado geral do sistema
ultima_atividade = time.ticks_ms()
ultimo_estado_botao = power_button.value()
debounce_time = 0
modo_economia = False

# Configurações de energia
AUTO_SLEEP_TIMEOUT = 300       # 5 minutos para sleep automático
DEBOUNCE_DELAY = 200          # 200ms de debounce
STATUS_INTERVAL = 30          # Enviar status a cada 30 segundos

# ======== VARIÁVEIS GLOBAIS DO SISTEMA ========
eventos_hoje = []
mqtt_connected = False
last_status_time = 0
serial_buffer = ""

# ======== FUNÇÕES DE CONTROLE DE ENERGIA ========
def verificar_botao_power():
    """Verifica o estado do botão de energia com debounce"""
    global display_ligado, sistema_ativo, ultimo_estado_botao, debounce_time, ultima_atividade, modo_economia
    
    # Lê estado atual do botão
    estado_atual = power_button.value()
    tempo_atual = time.ticks_ms()
    
    # Verifica se houve mudança e se passou o tempo de debounce
    if estado_atual != ultimo_estado_botao:
        if time.ticks_diff(tempo_atual, debounce_time) > DEBOUNCE_DELAY:
            # Botão foi pressionado (transição HIGH->LOW devido ao PULL_UP)
            if estado_atual == 0:  # Pressionado
                alternar_estado_display()
                debounce_time = tempo_atual
                ultima_atividade = tempo_atual
            
            ultimo_estado_botao = estado_atual

def alternar_estado_display():
    """Alterna o estado do display (liga/desliga)"""
    global display_ligado, sistema_ativo, modo_economia
    
    display_ligado = not display_ligado
    sistema_ativo = display_ligado
    modo_economia = not display_ligado
    
    if display_ligado:
        ligar_display()
    else:
        desligar_display()

def ligar_display():
    """Liga o display e sistema"""
    global display_ligado, sistema_ativo, modo_economia
    
    print("🔋 DISPLAY LIGADO")
    
    # Liga LED de status
    status_led.value(1)
    
    # Liga backlight se disponível
    if backlight_available:
        backlight.value(1)
    
    # Atualiza estados
    display_ligado = True
    sistema_ativo = True
    modo_economia = False
    
    # Limpa e atualiza display
    try:
        display.clear()
        atualizar_display()
    except Exception as e:
        print(f"Erro ao ligar display: {e}")
    
    # Envia status via serial
    enviar_status_serial()
    
    # Pisca LED para confirmar
    piscar_led_confirmacao(2)

def desligar_display():
    """Desliga o display para economizar bateria"""
    global display_ligado, sistema_ativo, modo_economia
    
    print("💤 DISPLAY DESLIGADO - Modo Economia")
    
    # Mostra tela de economia antes de desligar
    try:
        mostrar_tela_economia()
        time.sleep(1)  # Deixa visível por 1 segundo
        
        # Limpa display (tela preta)
        display.clear()
    except Exception as e:
        print(f"Erro ao desligar display: {e}")
    
    # Desliga backlight se disponível
    if backlight_available:
        backlight.value(0)
    
    # Desliga LED de status
    status_led.value(0)
    
    # Atualiza estados
    display_ligado = False
    sistema_ativo = False
    modo_economia = True
    
    # Envia status via serial
    enviar_status_serial()
    
    # Pisca LED para confirmar (mesmo com display off)
    piscar_led_confirmacao(5, delay=0.1)

def mostrar_tela_economia():
    """Mostra tela de modo economia antes de desligar"""
    try:
        display.clear()
        
        # Texto centralizado
        display.draw_text8x8(150, 100, "MODO ECONOMIA", color=0xF800)
        display.draw_text8x8(120, 130, "Display Desligando...", color=0xFFE0)
        display.draw_text8x8(100, 160, "Pressione botao para ligar", color=0x07E0)
        
        # Hora atual
        agora = localtime()
        hora_str = "{:02d}:{:02d}".format(agora[3], agora[4])
        display.draw_text8x8(200, 200, hora_str, color=0xFFFF)
        
    except Exception as e:
        print(f"Erro na tela economia: {e}")

def piscar_led_confirmacao(vezes=3, delay=0.2):
    """Pisca LED para confirmar ação"""
    for _ in range(vezes):
        status_led.value(1)
        time.sleep(delay)
        status_led.value(0)
        time.sleep(delay)

def gerenciar_economia_automatica():
    """Gerencia entrada automática em modo economia"""
    global ultima_atividade, modo_economia
    
    if not display_ligado:
        return  # Já está em economia manual
    
    tempo_inativo = time.ticks_diff(time.ticks_ms(), ultima_atividade)
    
    # Se muito tempo inativo, sugere economia
    if tempo_inativo > AUTO_SLEEP_TIMEOUT * 1000:
        print("⏰ Timeout de inatividade - entrando em modo economia automático")
        desligar_display()

def registrar_atividade():
    """Registra atividade do usuário"""
    global ultima_atividade
    ultima_atividade = time.ticks_ms()

# ======== FUNÇÃO: Comunicação Serial ========
def ler_dados_serial():
    """Lê dados da porta serial"""
    global serial_buffer
    
    if uart.any():
        data = uart.read().decode('utf-8', 'ignore')
        serial_buffer += data
        
        # Registra atividade
        registrar_atividade()
        
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
            
        elif comando == 'POWER_ON':
            # Comando remoto para ligar display
            if not display_ligado:
                ligar_display()
            
        elif comando == 'POWER_OFF':
            # Comando remoto para desligar display
            if display_ligado:
                desligar_display()
                
        elif comando == 'POWER_TOGGLE':
            # Comando remoto para alternar display
            alternar_estado_display()
            
        # Registra atividade para qualquer comando
        registrar_atividade()
            
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
    """Envia status completo via serial"""
    status_data = {
        'tipo': 'status',
        'client_id': CLIENT_ID,
        'name': f'Pico_ILI9488_{DEVICE_ID[-6:]}',
        'display': 'ILI9488',
        'eventos_count': len(eventos_hoje),
        'memoria_livre': gc.mem_free(),
        'timestamp': time.time(),
        'versao': '3.1-MQTT-SERIAL-POWER',
        'energia': {
            'display_ligado': display_ligado,
            'sistema_ativo': sistema_ativo,
            'modo_economia': modo_economia,
            'backlight_disponivel': backlight_available,
            'auto_sleep_timeout': AUTO_SLEEP_TIMEOUT
        },
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
        
        # Registra atividade
        registrar_atividade()
        
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
                
                # Atualizar display se estiver ligado
                if display_ligado:
                    atualizar_display()
                else:
                    print("Display desligado - evento armazenado para exibição posterior")
        
        elif acao == 'deletar':
            # Remover evento específico
            eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
            print(f"Evento {evento_id} removido")
            
            # Enviar confirmação via serial
            enviar_ack_serial(evento_id)
            
            # Atualizar display se estiver ligado
            if display_ligado:
                atualizar_display()
            
    except Exception as e:
        print(f"Erro ao processar evento: {e}")

def processar_comando(data):
    """Processa comando recebido"""
    global eventos_hoje
    
    try:
        acao = data.get('acao')
        
        # Registra atividade
        registrar_atividade()
        
        if acao == 'limpar':
            eventos_hoje.clear()
            print("Todos os eventos limpos")
            if display_ligado:
                atualizar_display()
            
        elif acao == 'atualizar_display':
            print("Atualizando display...")
            if display_ligado:
                atualizar_display()
            else:
                print("Display desligado - não é possível atualizar")
            
        elif acao == 'status':
            enviar_status_serial()
            
        elif acao == 'reiniciar':
            reiniciar_sistema()
            
        elif acao == 'power_on':
            if not display_ligado:
                ligar_display()
                
        elif acao == 'power_off':
            if display_ligado:
                desligar_display()
                
        elif acao == 'power_toggle':
            alternar_estado_display()
            
    except Exception as e:
        print(f"Erro ao processar comando: {e}")

def enviar_ack_serial(evento_id):
    """Envia confirmação de recebimento via serial"""
    ack_data = {
        'tipo': 'ack',
        'evento_id': evento_id,
        'timestamp': time.time(),
        'client_id': CLIENT_ID,
        'display_ligado': display_ligado
    }
    
    enviar_serial(ack_data)
    print(f"ACK enviado via serial para evento {evento_id}")

# ======== FUNÇÃO: Atualizar Display ========
def atualizar_display():
    """Atualiza a tela ILI9488 com eventos do dia"""
    if not display_ligado:
        print("Display desligado - não atualizando")
        return
    
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
        
        # Status do protocolo e energia
        display.draw_text8x8(10, 60, "PROTOCOLO: MQTT via SERIAL", color=0x07E0)
        
        # Status de energia
        if display_ligado:
            status_energia = "DISPLAY: LIGADO"
            cor_energia = 0x07E0  # Verde
        else:
            status_energia = "DISPLAY: ECONOMIA"
            cor_energia = 0xFFE0  # Amarelo
            
        display.draw_text8x8(250, 60, status_energia, color=cor_energia)
        
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
                if y_pos > 260:  # Limite da tela (deixa espaço para rodapé)
                    display.draw_text8x8(10, y_pos, "... mais eventos", color=0xF81F)
                    break
                
                # Texto do evento
                evento_texto = f"{evento['hora']} - {evento['nome']}"
                
                # Truncar se muito longo
                if len(evento_texto) > 45:
                    evento_texto = evento_texto[:42] + "..."
                
                #
