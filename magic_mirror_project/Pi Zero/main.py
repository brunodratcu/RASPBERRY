import time
import ujson as json
import gc
import network
import ubinascii
from time import localtime
from machine import Pin, SPI, unique_id, Timer, reset, deepsleep
from umqtt.simple import MQTTClient
import ili9488

# ======== CONFIGURAÇÕES MQTT ========
MQTT_BROKER = "192.168.1.100"  # IP do seu servidor/broker
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
MQTT_QOS = 1

# Configurações WiFi
WIFI_SSID = "lPhone de Bruno"
WIFI_PASSWORD = "deniederror"

# Gerar ID único para este dispositivo
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
CLIENT_ID = f"magic_mirror_pico_{DEVICE_ID}"

# Tópicos MQTT
TOPICS = {
    "EVENTO_ADD": "magic_mirror/eventos/add",
    "EVENTO_REMOVE": "magic_mirror/eventos/remove", 
    "EVENTO_COMPLETE": "magic_mirror/eventos/complete",
    "EVENTO_SYNC": "magic_mirror/eventos/sync",
    "DISPLAY_POWER": "magic_mirror/display/power",
    "DISPLAY_STATUS": "magic_mirror/display/status",
    "SYSTEM_HEARTBEAT": "magic_mirror/system/heartbeat",
    "DEVICE_ONLINE": "magic_mirror/device/online"
}

# ======== CONFIGURAÇÕES HARDWARE ========
# Display ILI9488 (3.5" Touch)
spi_display = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = ili9488.Display(spi_display, dc=Pin(12), cs=Pin(13), rst=Pin(14))

# Touch XPT2046 (mesmo display)
spi_touch = SPI(0, baudrate=1000000, sck=Pin(18), mosi=Pin(19), miso=Pin(16))

# Simulação do touch para este exemplo (implementação básica)
class TouchSimulator:
    def __init__(self):
        self.touched = False
        self.last_touch_time = 0
        self.touch_pin = Pin(21, Pin.IN, Pin.PULL_UP)  # Pino para simular toque
        
    def is_touched(self):
        # Simula toque quando pino é acionado
        current_time = time.ticks_ms()
        if not self.touch_pin.value() and (current_time - self.last_touch_time > 300):
            self.last_touch_time = current_time
            return True
        return False
    
    def get_position(self):
        # Retorna posição simulada baseada em regiões da tela
        # Para demonstração, vamos dividir a tela em áreas
        # Implementação real usaria XPT2046
        return (240, 160)  # Centro da tela como padrão

# Inicializar touch (simulado)
touch = TouchSimulator()

# Controle de energia
POWER_BUTTON_PIN = 15
power_button = Pin(POWER_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
status_led = Pin(25, Pin.OUT)

# ======== VARIÁVEIS GLOBAIS ========
eventos_hoje = []
mqtt_client = None
wifi_connected = False
mqtt_connected = False
display_ligado = True
sistema_ativo = True
ultima_atividade = time.ticks_ms()

# Interface
buttons = []
current_screen = "main"

# Cores (RGB565)
COLORS = {
    'BLACK': 0x0000,
    'WHITE': 0xFFFF,
    'RED': 0xF800,
    'GREEN': 0x07E0,
    'BLUE': 0x001F,
    'YELLOW': 0xFFE0,
    'GRAY': 0x7BEF,
    'DARK_GRAY': 0x4208
}

# ======== CLASSES DE INTERFACE ========
class Button:
    def __init__(self, x, y, width, height, text, callback, color=COLORS['WHITE'], text_color=COLORS['BLACK']):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.callback = callback
        self.color = color
        self.text_color = text_color
        self.pressed = False
        
    def draw(self, display):
        """Desenha o botão na tela"""
        color = COLORS['GRAY'] if self.pressed else self.color
        
        # Desenha retângulo preenchido
        for i in range(self.height):
            display.draw_hline(self.x, self.y + i, self.width, color)
        
        # Borda
        display.draw_hline(self.x, self.y, self.width, COLORS['WHITE'])
        display.draw_hline(self.x, self.y + self.height - 1, self.width, COLORS['WHITE'])
        display.draw_vline(self.x, self.y, self.height, COLORS['WHITE'])
        display.draw_vline(self.x + self.width - 1, self.y, self.height, COLORS['WHITE'])
        
        # Texto centralizado
        text_x = self.x + (self.width // 2) - (len(self.text) * 4)
        text_y = self.y + (self.height // 2) - 4
        display.draw_text8x8(text_x, text_y, self.text, self.text_color)
    
    def is_touched(self, x, y):
        """Verifica se as coordenadas estão dentro do botão"""
        return (self.x <= x <= self.x + self.width and 
                self.y <= y <= self.y + self.height)
    
    def press(self):
        """Executa callback do botão"""
        self.pressed = True
        if self.callback:
            self.callback()
        time.sleep_ms(100)
        self.pressed = False

# ======== FUNÇÕES DE CONECTIVIDADE ========
def conectar_wifi():
    """Conecta ao WiFi"""
    global wifi_connected
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if wlan.isconnected():
        wifi_connected = True
        return wlan.ifconfig()[0]
    
    print(f"🌐 Conectando ao WiFi: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    # Aguarda conexão com timeout
    timeout = 20
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        print(".", end="")
    
    if wlan.isconnected():
        wifi_connected = True
        ip = wlan.ifconfig()[0]
        print(f"\n✅ WiFi conectado! IP: {ip}")
        return ip
    else:
        wifi_connected = False
        print(f"\n❌ Falha na conexão WiFi")
        return None

def conectar_mqtt():
    """Conecta ao broker MQTT"""
    global mqtt_client, mqtt_connected
    
    try:
        print(f"📡 Conectando ao MQTT: {MQTT_BROKER}:{MQTT_PORT}")
        
        mqtt_client = MQTTClient(
            client_id=CLIENT_ID,
            server=MQTT_BROKER,
            port=MQTT_PORT,
            keepalive=MQTT_KEEPALIVE
        )
        
        # Configurar callbacks
        mqtt_client.set_callback(on_mqtt_message)
        
        # Conectar
        mqtt_client.connect()
        mqtt_connected = True
        
        # Subscrever tópicos
        topics_to_subscribe = [
            TOPICS["EVENTO_ADD"],
            TOPICS["EVENTO_REMOVE"],
            TOPICS["EVENTO_SYNC"],
            TOPICS["DISPLAY_POWER"],
            TOPICS["SYSTEM_HEARTBEAT"]
        ]
        
        for topic in topics_to_subscribe:
            mqtt_client.subscribe(topic.encode(), qos=MQTT_QOS)
            print(f"📡 Subscrito: {topic}")
        
        # Anuncia dispositivo online
        anunciar_dispositivo_online()
        
        print("✅ MQTT conectado com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro MQTT: {e}")
        mqtt_connected = False
        return False

def on_mqtt_message(topic, msg):
    """Callback para mensagens MQTT recebidas"""
    global eventos_hoje, ultima_atividade
    
    try:
        topic_str = topic.decode()
        payload = json.loads(msg.decode())
        
        print(f"📥 MQTT: {topic_str}")
        ultima_atividade = time.ticks_ms()
        
        # Processa baseado no tópico
        if topic_str == TOPICS["EVENTO_ADD"]:
            processar_evento_adicionado(payload)
            
        elif topic_str == TOPICS["EVENTO_REMOVE"]:
            processar_evento_removido(payload)
            
        elif topic_str == TOPICS["EVENTO_SYNC"]:
            processar_sincronizacao(payload)
            
        elif topic_str == TOPICS["DISPLAY_POWER"]:
            processar_comando_energia(payload)
            
        elif topic_str == TOPICS["SYSTEM_HEARTBEAT"]:
            processar_heartbeat(payload)
        
        # Atualiza tela se estiver ligada
        if display_ligado and sistema_ativo:
            atualizar_interface()
            
    except Exception as e:
        print(f"❌ Erro ao processar MQTT: {e}")

def publish_mqtt(topic, payload):
    """Publica mensagem MQTT"""
    if mqtt_connected and mqtt_client:
        try:
            msg = json.dumps(payload)
            mqtt_client.publish(topic.encode(), msg.encode(), qos=MQTT_QOS)
            print(f"📤 MQTT: {topic}")
            return True
        except Exception as e:
            print(f"❌ Erro ao publicar MQTT: {e}")
            return False
    return False

def anunciar_dispositivo_online():
    """Anuncia que dispositivo está online"""
    payload = {
        "device_id": CLIENT_ID,
        "device_type": "magic_mirror_display",
        "name": f"Magic Mirror {DEVICE_ID[-6:]}",
        "capabilities": {
            "has_display": True,
            "has_touch": True,
            "display_resolution": "480x320",
            "display_type": "ILI9488"
        },
        "timestamp": time.time(),
        "version": "4.0-MQTT-TOUCH"
    }
    
    publish_mqtt(TOPICS["DEVICE_ONLINE"], payload)

# ======== PROCESSADORES DE MENSAGENS MQTT ========
def processar_evento_adicionado(payload):
    """Processa evento adicionado via MQTT"""
    global eventos_hoje
    
    try:
        action = payload.get("action")
        if action == "add_event":
            evento = payload.get("event", {})
            evento_id = evento.get("id")
            
            # Remove duplicata se existir
            eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
            
            # Adiciona novo evento
            eventos_hoje.append(evento)
            
            # Ordena por horário
            eventos_hoje.sort(key=lambda x: x.get("hora", ""))
            
            print(f"➕ Evento adicionado: {evento.get('nome', 'Sem nome')}")
            
    except Exception as e:
        print(f"❌ Erro ao processar evento adicionado: {e}")

def processar_evento_removido(payload):
    """Processa evento removido via MQTT"""
    global eventos_hoje
    
    try:
        action = payload.get("action")
        
        if action == "remove_event":
            evento_id = payload.get("evento_id")
            eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
            print(f"➖ Evento {evento_id} removido")
            
        elif action == "remove_completed":
            evento_id = payload.get("evento_id")
            eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
            print(f"✅ Evento {evento_id} concluído e removido")
            
        elif action == "clear_all_events":
            eventos_hoje.clear()
            print("🗑️ Todos os eventos removidos")
            
    except Exception as e:
        print(f"❌ Erro ao processar remoção: {e}")

def processar_sincronizacao(payload):
    """Processa sincronização completa via MQTT"""
    global eventos_hoje
    
    try:
        action = payload.get("action")
        if action == "sync_today":
            # Substitui lista completa
            eventos_hoje = payload.get("events", [])
            
            # Ordena por horário
            eventos_hoje.sort(key=lambda x: x.get("hora", ""))
            
            print(f"🔄 Sincronizado: {len(eventos_hoje)} eventos")
            
    except Exception as e:
        print(f"❌ Erro ao sincronizar: {e}")

def processar_comando_energia(payload):
    """Processa comandos de energia via MQTT"""
    global display_ligado, sistema_ativo
    
    try:
        action = payload.get("action")
        target = payload.get("target_device", "all")
        
        # Verifica se comando é para este dispositivo
        if target != "all" and target != CLIENT_ID:
            return
        
        if action == "power_off":
            desligar_sistema()
        elif action == "power_on":
            ligar_sistema()
        elif action == "power_toggle":
            alternar_sistema()
            
    except Exception as e:
        print(f"❌ Erro ao processar comando energia: {e}")

def processar_heartbeat(payload):
    """Processa heartbeat do sistema"""
    # Responde com próprio heartbeat se necessário
    device = payload.get("server")
    if device == "magic_mirror_flask":
        enviar_heartbeat()

# ======== FUNÇÕES DA INTERFACE TOUCH ========
def criar_interface():
    """Cria botões da interface"""
    global buttons
    buttons.clear()
    
    if current_screen == "main":
        # Botão DESLIGAR (vermelho, canto inferior direito)
        buttons.append(Button(
            x=380, y=280, width=80, height=30,
            text="DESLIGAR", callback=confirmar_desligamento,
            color=COLORS['RED'], text_color=COLORS['WHITE']
        ))
        
        # Botões CONCLUIR para cada evento
        y_pos = 110
        for i, evento in enumerate(eventos_hoje):
            if y_pos > 250:  # Limite da tela
                break
                
            buttons.append(Button(
                x=350, y=y_pos, width=80, height=20,
                text="CONCLUIR", callback=lambda evt=evento: concluir_evento(evt),
                color=COLORS['GREEN'], text_color=COLORS['BLACK']
            ))
            
            y_pos += 25
    
    elif current_screen == "confirm_shutdown":
        # Tela de confirmação de desligamento
        buttons.append(Button(
            x=150, y=180, width=80, height=40,
            text="SIM", callback=desligar_sistema,
            color=COLORS['RED'], text_color=COLORS['WHITE']
        ))
        
        buttons.append(Button(
            x=250, y=180, width=80, height=40,
            text="NAO", callback=cancelar_desligamento,
            color=COLORS['GREEN'], text_color=COLORS['WHITE']
        ))

def desenhar_tela_principal():
    """Desenha tela principal"""
    # Fundo preto
    display.fill(COLORS['BLACK'])
    
    # Data e hora (fonte branca)
    agora = localtime()
    hora_str = "{:02d}:{:02d}:{:02d}".format(agora[3], agora[4], agora[5])
    data_str = "{:02d}/{:02d}/{:04d}".format(agora[2], agora[1], agora[0])
    
    # Cabeçalho
    display.draw_text16x32(50, 20, hora_str, COLORS['WHITE'])
    display.draw_text8x8(70, 60, data_str, COLORS['WHITE'])
    
    # Linha separadora
    display.draw_hline(20, 90, 440, COLORS['WHITE'])
    
    # Eventos do dia
    y_pos = 110
    if eventos_hoje:
        display.draw_text8x8(20, y_pos, "EVENTOS DE HOJE:", COLORS['WHITE'])
        y_pos += 30
        
        for i, evento in enumerate(eventos_hoje):
            if y_pos > 250:  # Limite para botões
                display.draw_text8x8(20, y_pos, "... mais eventos", COLORS['GRAY'])
                break
                
            # Texto do evento (fonte branca)
            evento_texto = f"{evento.get('hora', '--:--')} - {evento.get('nome', 'Sem nome')}"
            
            # Trunca se muito longo
            if len(evento_texto) > 35:
                evento_texto = evento_texto[:32] + "..."
            
            display.draw_text8x8(30, y_pos, evento_texto, COLORS['WHITE'])
            y_pos += 25
    else:
        display.draw_text8x8(20, y_pos, "Nenhum evento hoje", COLORS['GRAY'])
        y_pos += 25
        display.draw_text8x8(20, y_pos, "Aguardando sincronizacao...", COLORS['GRAY'])
    
    # Status de conexão (canto inferior esquerdo)
    status_y = 290
    if mqtt_connected:
        display.draw_text8x8(20, status_y, "MQTT: OK", COLORS['GREEN'])
    else:
        display.draw_text8x8(20, status_y, "MQTT: OFF", COLORS['RED'])
    
    if wifi_connected:
        display.draw_text8x8(100, status_y, "WiFi: OK", COLORS['GREEN'])
    else:
        display.draw_text8x8(100, status_y, "WiFi: OFF", COLORS['RED'])

def desenhar_tela_confirmacao():
    """Desenha tela de confirmação de desligamento"""
    display.fill(COLORS['BLACK'])
    
    # Título
    display.draw_text8x8(150, 80, "DESLIGAR SISTEMA?", COLORS['WHITE'])
    
    # Aviso
    display.draw_text8x8(100, 120, "O sistema sera desligado", COLORS['YELLOW'])
    display.draw_text8x8(120, 140, "Tem certeza?", COLORS['YELLOW'])

def atualizar_interface():
    """Atualiza interface baseada na tela atual"""
    if not display_ligado:
        return
    
    if current_screen == "main":
        desenhar_tela_principal()
    elif current_screen == "confirm_shutdown":
        desenhar_tela_confirmacao()
    
    # Desenha botões
    criar_interface()
    for button in buttons:
        button.draw(display)

def verificar_toque():
    """Verifica toques na tela"""
    if touch.is_touched():
        x, y = touch.get_position()
        
        # Simula diferentes posições baseado em áreas da tela
        # Em implementação real, usar coordenadas do XPT2046
        
        # Para demonstração, mapeia área da tela para botões
        for button in buttons:
            # Verifica se toque está na área de algum botão
            # Implementação simplificada - usar coordenadas reais do touch
            if (button.x <= 400 and button.y <= 300):  # Área aproximada
                print(f"🖱️ Botão tocado: {button.text}")
                button.press()
                registrar_atividade()
                time.sleep_ms(200)  # Debounce
                break

# ======== CALLBACKS DOS BOTÕES ========
def concluir_evento(evento):
    """Marca evento como concluído"""
    global eventos_hoje
    
    evento_id = evento.get("id")
    nome = evento.get("nome", "Evento")
    
    print(f"✅ Concluindo evento: {nome}")
    
    # Remove da lista local
    eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
    
    # Publica conclusão via MQTT
    payload = {
        "evento_id": evento_id,
        "device_id": CLIENT_ID,
        "action": "complete",
        "timestamp": time.time(),
        "event_name": nome
    }
    
    publish_mqtt(TOPICS["EVENTO_COMPLETE"], payload)
    
    # Atualiza interface
    atualizar_interface()
    
    # Feedback visual
    piscar_led_confirmacao(2)

def confirmar_desligamento():
    """Mostra tela de confirmação"""
    global current_screen
    current_screen = "confirm_shutdown"
    atualizar_interface()

def cancelar_desligamento():
    """Cancela desligamento"""
    global current_screen
    current_screen = "main"
    atualizar_interface()

def desligar_sistema():
    """Desliga o sistema"""
    global display_ligado, sistema_ativo
    
    print("🔴 Desligando sistema via touch...")
    
    # Publica status de desligamento
    payload = {
        "device_id": CLIENT_ID,
        "action": "power_off",
        "source": "touch_button",
        "timestamp": time.time()
    }
    publish_mqtt(TOPICS["DISPLAY_STATUS"], payload)
    
    # Tela de despedida
    display.fill(COLORS['BLACK'])
    display.draw_text8x8(150, 100, "DESLIGANDO...", COLORS['RED'])
    display.draw_text8x8(120, 130, "Sistema sera desligado", COLORS['WHITE'])
    time.sleep(2)
    
    # Desliga display
    display.fill(COLORS['BLACK'])
    display_ligado = False
    sistema_ativo = False
    
    # Entra em deep sleep
    print("💤 Entrando em deep sleep...")
    time.sleep(1)
    deepsleep()

def ligar_sistema():
    """Liga o sistema"""
    global display_ligado, sistema_ativo, current_screen
    
    print("🔋 Ligando sistema...")
    display_ligado = True
    sistema_ativo = True
    current_screen = "main"
    
    atualizar_interface()
    piscar_led_confirmacao(2)

def alternar_sistema():
    """Alterna estado do sistema"""
    if display_ligado:
        desligar_sistema()
    else:
        ligar_sistema()

# ======== FUNÇÕES DE CONTROLE ========
def verificar_botao_fisico():
    """Verifica botão físico de energia"""
    global ultima_atividade
    
    if not power_button.value():  # Pressionado
        print("🔘 Botão físico pressionado")
        alternar_sistema()
        ultima_atividade = time.ticks_ms()
        time.sleep_ms(300)  # Debounce

def registrar_atividade():
    """Registra atividade do usuário"""
    global ultima_atividade
    ultima_atividade = time.ticks_ms()

def piscar_led_confirmacao(vezes=3):
    """Pisca LED para confirmação"""
    for _ in range(vezes):
        status_led.value(1)
        time.sleep_ms(100)
        status_led.value(0)
        time.sleep_ms(100)

def enviar_heartbeat():
    """Envia heartbeat do dispositivo"""
    if mqtt_connected:
        payload = {
            "device_id": CLIENT_ID,
            "device": "magic_mirror_display",
            "status": "online" if sistema_ativo else "sleep",
            "display_on": display_ligado,
            "events_count": len(eventos_hoje),
            "memory_free": gc.mem_free(),
            "timestamp": time.time()
        }
        
        publish_mqtt(TOPICS["SYSTEM_HEARTBEAT"], payload)

def verificar_conexoes():
    """Verifica e mantém conexões"""
    global wifi_connected, mqtt_connected
    
    # Verifica WiFi
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        wifi_connected = False
        print("⚠️ WiFi desconectado - reconectando...")
        conectar_wifi()
    
    # Verifica MQTT
    if wifi_connected and not mqtt_connected:
        print("⚠️ MQTT desconectado - reconectando...")
        conectar_mqtt()
    
    # Ping MQTT
    if mqtt_connected:
        try:
            mqtt_client.ping()
        except:
            mqtt_connected = False

# ======== LOOP PRINCIPAL ========
def loop_principal():
    """Loop principal do sistema"""
    print("🔄 Iniciando loop principal...")
    
    last_heartbeat = 0
    last_connection_check = 0
    last_interface_update = 0
    
    while True:
        try:
            current_time = time.ticks_ms()
            
            # Verifica botão físico
            verificar_botao_fisico()
            
            # Verifica toque (apenas se sistema ativo)
            if sistema_ativo and display_ligado:
                verificar_toque()
            
            # Processa mensagens MQTT
            if mqtt_connected:
                try:
                    mqtt_client.check_msg()
                except:
                    mqtt_connected = False
            
            # Heartbeat a cada 30 segundos
            if current_time - last_heartbeat > 30000:
                enviar_heartbeat()
                last_heartbeat = current_time
            
            # Verifica conexões a cada 60 segundos
            if current_time - last_connection_check > 60000:
                verificar_conexoes()
                last_connection_check = current_time
            
            # Atualiza interface a cada 5 segundos (se ativa)
            if (sistema_ativo and display_ligado and 
                current_time - last_interface_update > 5000):
                atualizar_interface()
                last_interface_update = current_time
            
            # Limpeza de memória
            if current_time % 120000 < 100:  # A cada 2 minutos
                gc.collect()
            
            time.sleep_ms(50)  # Sleep curto
            
        except KeyboardInterrupt:
            print("\n🛑 Sistema interrompido")
            break
        except Exception as e:
            print(f"❌ Erro no loop principal: {e}")
            time.sleep(1)

# ======== INICIALIZAÇÃO ========
def main():
    """Função principal"""
    global current_screen
    
    print("🪞 === MAGIC MIRROR MQTT TOUCH ===")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Client ID: {CLIENT_ID}")
    print("=====================================")
    
    try:
        # Liga LED de status
        status_led.value(1)
        
        # Tela de inicialização
        display.fill(COLORS['BLACK'])
        display.draw_text8x8(50, 50, "MAGIC MIRROR", COLORS['WHITE'])
        display.draw_text8x8(80, 80, "Iniciando...", COLORS['YELLOW'])
        display.draw_text8x8(60, 110, f"ID: {DEVICE_ID[-6:]}", COLORS['GRAY'])
        
        # Conecta WiFi
        display.draw_text8x8(60, 140, "Conectando WiFi...", COLORS['WHITE'])
        if conectar_wifi():
            display.draw_text8x8(60, 160, "WiFi: OK", COLORS['GREEN'])
        else:
            display.draw_text8x8(60, 160, "WiFi: ERRO", COLORS['RED'])
            time.sleep(5)
            reset()
        
        # Conecta MQTT
        display.draw_text8x8(60, 180, "Conectando MQTT...", COLORS['WHITE'])
        if conectar_mqtt():
            display.draw_text8x8(60, 200, "MQTT: OK", COLORS['GREEN'])
        else:
            display.draw_text8x8(60, 200, "MQTT: ERRO", COLORS['RED'])
        
        time.sleep(2)
        
        # Inicia interface principal
        current_screen = "main"
        atualizar_interface()
        
        print("✅ Sistema inicializado com sucesso!")
        print("🖱️ Use o touch screen para interagir")
        print(f"🔘 Botão físico no pino GP{POWER_BUTTON_PIN}")
        
        # Inicia loop principal
        loop_principal()
        
    except Exception as e:
        print(f"❌ Erro crítico: {e}")
        # Mostra erro na tela
        display.fill(COLORS['BLACK'])
        display.draw_text8x8(50, 100, "ERRO CRITICO:", COLORS['RED'])
        display.draw_text8x8(50, 120, str(e)[:40], COLORS['WHITE'])
        time.sleep(5)
        reset()

# Executar programa principal
if __name__ == "__main__":
    main()