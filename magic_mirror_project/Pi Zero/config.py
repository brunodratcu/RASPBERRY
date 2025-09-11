# config.py - Configuração Simplificada Magic Mirror Pico 2W
# Sistema MQTT Only - Registro via Backend
"""
Configuração simplificada para Magic Mirror
Versão 3.0 - MQTT Only + Backend Registration
"""

# ==================== IDENTIFICAÇÃO DO DISPOSITIVO ====================
# IMPORTANTE: Configure apenas estas variáveis após registro no backend

# ID de registro fornecido pelo backend após cadastro
REGISTRATION_ID = "REG_CHANGEME_12345"     # Obtido do backend após registro
DEVICE_ID = ""                             # Será definido automaticamente pelo backend
API_KEY = ""                               # Será definido automaticamente pelo backend

# Informações básicas do dispositivo (opcionais)
DEVICE_LOCATION = "Não especificado"      # Local onde está instalado
DEVICE_DESCRIPTION = "Magic Mirror Pico 2W"  # Descrição do dispositivo

# Versão do firmware
FIRMWARE_VERSION = "3.0.0-mqtt-only"

# ==================== CONFIGURAÇÕES DE REDE ====================
# WiFi
WIFI_SSID = "SUA_REDE_WIFI"
WIFI_PASSWORD = "SUA_SENHA_WIFI"

# Configurações MQTT (única forma de comunicação)
MQTT_BROKER = "broker.hivemq.com"          # Broker MQTT
MQTT_PORT = 1883
MQTT_TOPIC_BASE = "espelho_magico"
MQTT_USERNAME = None                       # Se necessário
MQTT_PASSWORD = None                       # Se necessário

# ==================== CONFIGURAÇÕES DE SINCRONIZAÇÃO ====================
# Intervalos de atualização (em segundos)
HEARTBEAT_INTERVAL = 60        # 1 minuto para heartbeat
NTP_SYNC_INTERVAL = 3600       # 1 hora para sincronização NTP
REGISTRATION_CHECK_INTERVAL = 300  # 5 minutos para verificar registro

# Configurações de retry
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5               # Delay entre tentativas (segundos)
CONNECTION_TIMEOUT = 30       # Timeout para conexões

# ==================== CONFIGURAÇÕES DE TEMPO E LOCALIZAÇÃO ====================
# Timezone do Brasil
TIMEZONE_NAME = "America/Sao_Paulo"
TIMEZONE_OFFSET = -3          # UTC-3 (Brasília)
DAYLIGHT_SAVING = False       # Ajuste automático de horário de verão

# Servidores NTP (em ordem de prioridade)
NTP_SERVERS = [
    "pool.ntp.org",
    "time.google.com", 
    "time.cloudflare.com",
    "a.ntp.br",
    "b.ntp.br"
]

# Formato de data e hora
DATE_FORMAT = "DD/MM/YYYY"    # 25/12/2024
TIME_FORMAT = "24H"           # 14:30 (ou "12H" para formato AM/PM)

# ==================== CONFIGURAÇÕES DO DISPLAY ILI9486 ====================
# Resolução
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 480

# Orientação (0=retrato, 1=paisagem, 2=retrato invertido, 3=paisagem invertida)
DISPLAY_ROTATION = 0

# Brilho do display (0-100%)
DISPLAY_BRIGHTNESS = 80

# Configurações de economia de energia
SCREEN_SAVER_ENABLED = True
SCREEN_SAVER_TIMEOUT = 3600   # 1 hora em segundos
SCREEN_SAVER_BRIGHTNESS = 10  # Brilho reduzido

# ==================== CORES E TEMA ====================
# Cores em RGB565
COLORS = {
    # Cores principais
    'BACKGROUND': 0x0000,        # Preto - fundo
    'PRIMARY_TEXT': 0xFFFF,      # Branco - texto principal
    'SECONDARY_TEXT': 0xC618,    # Cinza claro - texto secundário
    
    # Hora e data
    'TIME': 0xFFFF,              # Branco - hora atual
    'DATE': 0xF7BE,              # Bege - data atual
    
    # Eventos
    'EVENT_TIME': 0xFFE0,        # Amarelo - hora do evento
    'EVENT_TITLE': 0x07FF,       # Ciano - título do evento
    'EVENT_LOCATION': 0xFB56,    # Laranja claro - local
    'EVENT_SOON': 0xF800,        # Vermelho - evento próximo
    
    # Status
    'STATUS_ONLINE': 0x07E0,     # Verde - online
    'STATUS_OFFLINE': 0xF800,    # Vermelho - offline
    'STATUS_SYNC': 0x001F,       # Azul - sincronizando
    'STATUS_WARNING': 0xFFE0,    # Amarelo - aviso
    'STATUS_PENDING': 0xFB56,    # Laranja - pendente registro
    
    # Outros
    'NO_EVENTS': 0x7BEF,         # Cinza - sem eventos
    'DIVIDER': 0x4208,           # Cinza escuro - linhas divisórias
}

# Tamanhos de fonte (multiplicador)
FONT_SIZES = {
    'TIME': 4,           # Hora atual
    'DATE': 2,           # Data atual
    'EVENT_TIME': 3,     # Hora do evento
    'EVENT_TITLE': 2,    # Título do evento
    'EVENT_LOCATION': 1, # Local do evento
    'STATUS': 1,         # Status do sistema
    'NO_EVENTS': 2,      # Mensagem sem eventos
    'HEADER': 3,         # Cabeçalhos
}

# ==================== LAYOUT E POSIÇÕES ====================
# Posições Y na tela (pixels)
LAYOUT = {
    # Cabeçalho
    'STATUS_Y': 10,          # Status de conexão
    'TIME_Y': 60,            # Hora atual
    'DATE_Y': 110,           # Data atual
    'DIVIDER_Y': 140,        # Linha divisória
    
    # Eventos
    'EVENTS_TITLE_Y': 160,   # "PRÓXIMOS EVENTOS"
    'EVENTS_START_Y': 190,   # Início da lista de eventos
    'EVENT_HEIGHT': 45,      # Altura de cada evento
    'EVENT_SPACING': 5,      # Espaçamento entre eventos
    
    # Rodapé
    'FOOTER_Y': 450,         # Informações do rodapé
    
    # Margens
    'MARGIN_X': 10,          # Margem lateral
    'CENTER_X': 160,         # Centro horizontal (320/2)
}

# Configurações de eventos
MAX_EVENTS_DISPLAY = 6       # Máximo de eventos na tela
MAX_EVENT_TITLE_LENGTH = 25  # Máximo de caracteres no título
MAX_EVENT_LOCATION_LENGTH = 20  # Máximo de caracteres no local

# ==================== CONFIGURAÇÕES DE HARDWARE ====================
# Pinos do display ILI9486 (SPI)
DISPLAY_PINS = {
    'SCK': 18,    # SPI Clock
    'MOSI': 19,   # SPI Data (MISO não usado)
    'CS': 17,     # Chip Select
    'DC': 16,     # Data/Command
    'RST': 20,    # Reset
    'BL': 21,     # Backlight (PWM)
}

# Configurações SPI
SPI_CONFIG = {
    'BAUDRATE': 40000000,    # 40 MHz
    'BUS': 0,                # SPI Bus 0
    'POLARITY': 0,           # CPOL
    'PHASE': 0,              # CPHA
}

# Pinos de controle (opcionais)
CONTROL_PINS = {
    'POWER_BUTTON': 22,      # Botão de power/wake
    'LED_STATUS': 25,        # LED de status (opcional)
}

# ==================== CONFIGURAÇÕES DE SISTEMA ====================
# Debug e logging
DEBUG_ENABLED = True
SERIAL_DEBUG = True
LOG_LEVEL = "INFO"          # DEBUG, INFO, WARN, ERROR

# Performance
AUTO_GARBAGE_COLLECT = True
GC_INTERVAL = 300           # Coleta de lixo a cada 5 minutos
MEMORY_WARNING_THRESHOLD = 50000  # Aviso se memória livre < 50KB

# Watchdog
WATCHDOG_ENABLED = True
WATCHDOG_TIMEOUT = 30       # Reset automático se travado por 30s

# ==================== CONFIGURAÇÕES DE EVENTOS ====================
# Filtros de eventos
FILTER_PAST_EVENTS = True   # Não mostrar eventos que já passaram
FILTER_ALL_DAY_EVENTS = False  # Mostrar eventos de dia inteiro
SHOW_ORGANIZER = False      # Mostrar organizador do evento

# Notificações
NOTIFICATION_ENABLED = True
NOTIFICATION_MINUTES = [30, 15, 5]  # Notificar 30, 15 e 5 min antes
NOTIFICATION_BLINK_LED = True

# Cache
CACHE_EVENTS = True
CACHE_DURATION = 600        # Cache por 10 minutos

# ==================== TEXTOS DA INTERFACE ====================
INTERFACE_TEXTS = {
    # Português Brasil
    'STARTUP': "MAGIC MIRROR",
    'LOADING': "Carregando...",
    'NEXT_EVENTS': "PROXIMOS EVENTOS",
    'NO_EVENTS': "Sem eventos hoje",
    'NO_EVENTS_SUBTITLE': "Aproveite seu dia livre!",
    'CONNECTING': "Conectando...",
    'CONNECTED': "Conectado",
    'OFFLINE': "Offline",
    'SYNCING': "Sincronizando...",
    'ERROR': "Erro",
    'RETRY': "Tentando novamente...",
    'TODAY': "HOJE",
    'TOMORROW': "AMANHA",
    'IN_PROGRESS': "EM ANDAMENTO",
    'STARTING_SOON': "INICIANDO",
    'ALL_DAY': "DIA INTEIRO",
    'MINUTES_SHORT': "min",
    'HOURS_SHORT': "h",
    'NOW': "AGORA",
    'REGISTRATION_ID': "REG ID",
    'VERSION': "v",
    'UPTIME': "Ativo",
    'MEMORY': "Mem",
    'PENDING_REGISTRATION': "AGUARDANDO REGISTRO",
    'REGISTERING': "Registrando...",
    'REGISTERED': "Registrado",
    'REGISTRATION_ERROR': "Erro no Registro",
}

# ==================== CONFIGURAÇÕES MQTT ====================
# Configurações MQTT
MQTT_CONFIG = {
    'KEEP_ALIVE': 60,
    'QOS': 1,
    'RETAIN': False,
    'CLEAN_SESSION': True
}

# Tópicos MQTT (serão definidos após receber device_id)
MQTT_TOPICS = {
    'REGISTRATION': f"{MQTT_TOPIC_BASE}/registration",
    'EVENTS': f"{MQTT_TOPIC_BASE}/{{device_id}}/events",
    'CONFIG': f"{MQTT_TOPIC_BASE}/{{device_id}}/config", 
    'STATUS': f"{MQTT_TOPIC_BASE}/{{device_id}}/status",
    'HEARTBEAT': f"{MQTT_TOPIC_BASE}/{{device_id}}/heartbeat",
    'RESPONSE': f"{MQTT_TOPIC_BASE}/{{device_id}}/response"
}

# ==================== FUNÇÕES UTILITÁRIAS ====================

def get_color(name):
    """Retorna cor por nome"""
    return COLORS.get(name.upper(), COLORS['PRIMARY_TEXT'])

def get_font_size(element):
    """Retorna tamanho da fonte"""
    return FONT_SIZES.get(element.upper(), 2)

def get_layout_position(element):
    """Retorna posição Y do layout"""
    return LAYOUT.get(f"{element.upper()}_Y", 100)

def get_text(key):
    """Retorna texto da interface"""
    return INTERFACE_TEXTS.get(key.upper(), key)

def validate_config():
    """Valida configurações obrigatórias"""
    issues = []
    
    # Validações críticas
    if REGISTRATION_ID == "REG_CHANGEME_12345":
        issues.append("REGISTRATION_ID não configurado - obtenha do backend")
    
    if WIFI_SSID == "SUA_REDE_WIFI":
        issues.append("WIFI_SSID não configurado")
    
    if WIFI_PASSWORD == "SUA_SENHA_WIFI":
        issues.append("WIFI_PASSWORD não configurado")
    
    # Validações de parâmetros
    if TIMEZONE_OFFSET < -12 or TIMEZONE_OFFSET > 12:
        issues.append("TIMEZONE_OFFSET inválido (-12 a +12)")
    
    if TIME_FORMAT not in ["12H", "24H"]:
        issues.append("TIME_FORMAT deve ser '12H' ou '24H'")
    
    if DATE_FORMAT not in ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]:
        issues.append("DATE_FORMAT inválido")
    
    if DISPLAY_BRIGHTNESS < 0 or DISPLAY_BRIGHTNESS > 100:
        issues.append("DISPLAY_BRIGHTNESS deve estar entre 0 e 100")
    
    if MAX_EVENTS_DISPLAY < 1 or MAX_EVENTS_DISPLAY > 10:
        issues.append("MAX_EVENTS_DISPLAY deve estar entre 1 e 10")
    
    return issues

def get_mqtt_topic(topic_type, device_id=None):
    """Retorna tópico MQTT específico"""
    if device_id is None:
        device_id = DEVICE_ID
    
    topic_template = MQTT_TOPICS.get(topic_type.upper())
    if topic_template and '{device_id}' in topic_template:
        return topic_template.format(device_id=device_id)
    elif topic_template:
        return topic_template
    else:
        return f"{MQTT_TOPIC_BASE}/{device_id}/{topic_type.lower()}"

def is_debug_enabled():
    """Verifica se debug está habilitado"""
    return DEBUG_ENABLED and SERIAL_DEBUG

def get_display_config():
    """Retorna configurações do display"""
    return {
        'width': DISPLAY_WIDTH,
        'height': DISPLAY_HEIGHT,
        'rotation': DISPLAY_ROTATION,
        'brightness': DISPLAY_BRIGHTNESS,
        'pins': DISPLAY_PINS,
        'spi': SPI_CONFIG
    }

def get_network_config():
    """Retorna configurações de rede"""
    return {
        'wifi_ssid': WIFI_SSID,
        'wifi_password': WIFI_PASSWORD,
        'mqtt_broker': MQTT_BROKER,
        'mqtt_port': MQTT_PORT,
        'timeout': CONNECTION_TIMEOUT
    }

def get_device_info():
    """Retorna informações do dispositivo"""
    return {
        'registration_id': REGISTRATION_ID,
        'device_id': DEVICE_ID,
        'location': DEVICE_LOCATION,
        'description': DEVICE_DESCRIPTION,
        'firmware_version': FIRMWARE_VERSION
    }

def is_registered():
    """Verifica se dispositivo está registrado"""
    return DEVICE_ID != "" and API_KEY != ""

def set_device_credentials(device_id: str, api_key: str):
    """Define credenciais do dispositivo após registro"""
    global DEVICE_ID, API_KEY
    DEVICE_ID = device_id
    API_KEY = api_key

# ==================== CONFIGURAÇÕES ESPECÍFICAS POR AMBIENTE ====================

# Configuração para desenvolvimento
DEV_CONFIG = {
    'DEBUG_ENABLED': True,
    'SERIAL_DEBUG': True,
    'LOG_LEVEL': 'DEBUG',
    'HEARTBEAT_INTERVAL': 30,
    'DISPLAY_BRIGHTNESS': 50,
}

# Configuração para produção
PROD_CONFIG = {
    'DEBUG_ENABLED': False,
    'SERIAL_DEBUG': False,
    'LOG_LEVEL': 'INFO',
    'HEARTBEAT_INTERVAL': 60,
    'DISPLAY_BRIGHTNESS': 80,
}

# Configuração para demonstração
DEMO_CONFIG = {
    'DEBUG_ENABLED': True,
    'SERIAL_DEBUG': True,
    'LOG_LEVEL': 'INFO',
    'HEARTBEAT_INTERVAL': 15,
    'DISPLAY_BRIGHTNESS': 100,
    'SHOW_ALL_INFO': True,
}

def apply_environment_config(env='prod'):
    """Aplica configurações específicas do ambiente"""
    global DEBUG_ENABLED, SERIAL_DEBUG, LOG_LEVEL, HEARTBEAT_INTERVAL, DISPLAY_BRIGHTNESS
    
    if env == 'dev':
        config = DEV_CONFIG
    elif env == 'demo':
        config = DEMO_CONFIG
    else:
        config = PROD_CONFIG
    
    # Aplica configurações
    DEBUG_ENABLED = config.get('DEBUG_ENABLED', DEBUG_ENABLED)
    SERIAL_DEBUG = config.get('SERIAL_DEBUG', SERIAL_DEBUG)
    LOG_LEVEL = config.get('LOG_LEVEL', LOG_LEVEL)
    HEARTBEAT_INTERVAL = config.get('HEARTBEAT_INTERVAL', HEARTBEAT_INTERVAL)
    DISPLAY_BRIGHTNESS = config.get('DISPLAY_BRIGHTNESS', DISPLAY_BRIGHTNESS)

# ==================== CONFIGURAÇÃO DE EXEMPLO ====================
"""
EXEMPLO DE CONFIGURAÇÃO PARA UM NOVO DISPOSITIVO:

1. No backend (http://seu-servidor:5000):
   - Acesse a interface web
   - Cadastre um novo dispositivo
   - Defina o local e descrição
   - Copie o REGISTRATION_ID gerado

2. Configure este arquivo:
   REGISTRATION_ID = "REG_abc123def456ghi789"  # ID copiado do backend
   DEVICE_LOCATION = "Sala A, 2º Andar"
   DEVICE_DESCRIPTION = "Magic Mirror - Escritório"
   
   WIFI_SSID = "MinhaRedeEmpresa"
   WIFI_PASSWORD = "MinhaSenh@123"
   
   MQTT_BROKER = "broker.hivemq.com"  # Ou seu broker local

3. Carregue este arquivo no Pico 2W

4. Execute o main.py

5. No backend, aprove o registro do dispositivo

RESULTADO:
- Pico conecta WiFi automaticamente
- Registra-se no backend via MQTT
- Recebe device_id e api_key automaticamente
- Sincroniza horário via NTP
- Recebe eventos da agenda automaticamente via MQTT
- Exibe eventos na tela LCD em tempo real

FLUXO AUTOMÁTICO:
1. Pico inicia e conecta WiFi
2. Envia registro via MQTT: "espelho_magico/registration"
3. Backend aprova e envia device_id + api_key
4. Pico subscreve aos tópicos específicos do device_id
5. Backend publica eventos: "espelho_magico/{device_id}/events"
6. Pico recebe e atualiza display
7. Pico envia heartbeat: "espelho_magico/{device_id}/heartbeat"
8. Horário sincronizado via NTP automaticamente
"""

# ==================== VALIDAÇÃO AUTOMÁTICA ====================
if __name__ == "__main__":
    # Auto-validação quando arquivo é executado
    print("=" * 50)
    print("MAGIC MIRROR - VALIDAÇÃO DE CONFIGURAÇÃO")
    print("=" * 50)
    
    # Informações do dispositivo
    print(f"Registration ID: {REGISTRATION_ID}")
    print(f"Device ID: {DEVICE_ID if DEVICE_ID else 'Aguardando registro'}")
    print(f"Localização: {DEVICE_LOCATION}")
    print(f"Descrição: {DEVICE_DESCRIPTION}")
    print(f"Firmware: {FIRMWARE_VERSION}")
    print(f"Registrado: {'Sim' if is_registered() else 'Não'}")
    print()
    
    # Configurações de rede
    print(f"WiFi: {WIFI_SSID}")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print()
    
    # Validação
    issues = validate_config()
    if issues:
        print("❌ PROBLEMAS DE CONFIGURAÇÃO:")
        for issue in issues:
            print(f"  • {issue}")
        print()
        print("Configure as variáveis antes de usar!")
    else:
        print("✅ Configuração válida!")
        if is_registered():
            print("✅ Dispositivo registrado - pronto para uso!")
        else:
            print("⏳ Aguardando registro no backend")
    
    print("=" * 50)