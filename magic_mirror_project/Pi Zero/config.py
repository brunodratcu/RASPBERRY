# config.py - Configuração Magic Mirror v3.0
"""
Configuração principal do Magic Mirror
Sistema MQTT Only + Backend Registration
Raspberry Pi Pico 2W + Display LCD Shield 3.5"
"""

import machine
import gc

# ==================== INFORMAÇÕES DO DISPOSITIVO ====================
# CONFIGURAR MANUALMENTE - Obtenha do backend web
REGISTRATION_ID = "MIRROR_SALA_001"  # ALTERE AQUI - ID único do seu dispositivo
DEVICE_ID = ""  # Será definido após aprovação no backend
API_KEY = ""    # Será definido após aprovação no backend

# Informações do dispositivo
DEVICE_LOCATION = "Sala Principal"
DEVICE_DESCRIPTION = "Espelho Magico - Exibir agenda Outlook"
FIRMWARE_VERSION = "3.0.1"

# ==================== CONFIGURAÇÃO DE REDE ====================
WIFI_SSID = "SUA_REDE_WIFI"  # ALTERE AQUI
WIFI_PASSWORD = "SUA_SENHA_WIFI"  # ALTERE AQUI

# Timeouts de conexão
CONNECTION_TIMEOUT = 30  # segundos
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # segundos entre tentativas

# ==================== CONFIGURAÇÃO MQTT ====================
MQTT_BROKER = "192.168.1.100"  # ALTERE AQUI - IP do servidor backend
MQTT_PORT = 1883
MQTT_USERNAME = ""  # Opcional
MQTT_PASSWORD = ""  # Opcional

# Intervalos de comunicação
HEARTBEAT_INTERVAL = 300  # 5 minutos
REGISTRATION_CHECK_INTERVAL = 60  # 1 minuto
MQTT_KEEPALIVE = 60

# ==================== CONFIGURAÇÃO DE TEMPO ====================
TIMEZONE_OFFSET = -3  # Brasil (UTC-3)
TIMEZONE_NAME = "America/Sao_Paulo"
DAYLIGHT_SAVING = False  # Ajuste conforme necessário
TIME_FORMAT = "24H"  # "12H" ou "24H"
DATE_FORMAT = "DD/MM/YYYY"  # "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"

# Servidores NTP
NTP_SERVERS = [
    "pool.ntp.br",
    "time.google.com", 
    "time.cloudflare.com"
]
NTP_SYNC_INTERVAL = 3600  # 1 hora

# ==================== CONFIGURAÇÃO DO DISPLAY ====================
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

# Pinos SPI para ILI9486 (3.5" Shield)
DISPLAY_PINS = {
    'SCK': 2,    # SPI Clock
    'MOSI': 3,   # SPI Data
    'CS': 5,     # Chip Select
    'DC': 4,     # Data/Command
    'RST': 6,    # Reset
    'BL': 7      # Backlight (PWM)
}

# Configuração SPI
SPI_CONFIG = {
    'BUS': 0,           # SPI0
    'BAUDRATE': 40000000  # 40MHz
}

# Display
DISPLAY_BRIGHTNESS = 80  # 0-100%
SCREEN_SAVER_ENABLED = True
SCREEN_SAVER_TIMEOUT = 1800  # 30 minutos
SCREEN_SAVER_BRIGHTNESS = 10  # 10% durante screen saver

# ==================== CONFIGURAÇÃO DE EVENTOS ====================
MAX_EVENTS_DISPLAY = 5
FILTER_PAST_EVENTS = True
FILTER_ALL_DAY_EVENTS = False
MAX_EVENT_LOCATION_LENGTH = 25

# ==================== CORES (RGB565) ====================
COLORS = {
    'PRIMARY_TEXT': 0xFFFF,    # Branco
    'SECONDARY_TEXT': 0xC618,  # Cinza claro
    'TIME': 0x07FF,            # Ciano
    'DATE': 0xF7BE,            # Bege
    'EVENT_TITLE': 0xFFE0,     # Amarelo
    'EVENT_TIME': 0x07E0,      # Verde
    'EVENT_LOCATION': 0xFD20,  # Laranja
    'EVENT_SOON': 0xF800,      # Vermelho (eventos próximos)
    'DIVIDER': 0x8410,         # Cinza escuro
    'BACKGROUND': 0x0000,      # Preto
    'STATUS_ONLINE': 0x07E0,   # Verde
    'STATUS_OFFLINE': 0xF800,  # Vermelho
    'STATUS_SYNC': 0x07FF,     # Ciano
    'STATUS_WARNING': 0xFFE0,  # Amarelo
    'STATUS_PENDING': 0xFD20,  # Laranja
    'NO_EVENTS': 0x8410        # Cinza
}

# ==================== LAYOUT ====================
LAYOUT = {
    'MARGIN_X': 15,
    'MARGIN_Y': 15,
    'TIME': 40,           # Posição Y da hora
    'DATE': 80,           # Posição Y da data
    'DIVIDER': 120,       # Posição Y da linha divisória
    'EVENTS_TITLE': 140,  # Posição Y do título "Próximos Eventos"
    'EVENTS_START': 170,  # Início da lista de eventos
    'EVENT_HEIGHT': 35,   # Altura de cada evento
    'EVENT_SPACING': 5    # Espaçamento entre eventos
}

# ==================== FONTES ====================
FONTS = {
    'TIME': 4,        # Tamanho da fonte para hora
    'DATE': 2,        # Tamanho da fonte para data
    'HEADER': 3,      # Cabeçalhos
    'EVENT_TITLE': 2, # Títulos de eventos
    'EVENT_TIME': 2,  # Horários de eventos
    'EVENT_LOCATION': 1, # Local dos eventos
    'STATUS': 1,      # Texto de status
    'NO_EVENTS': 2    # Mensagem "sem eventos"
}

# ==================== TEXTOS LOCALIZADOS ====================
TEXTS = {
    'STARTUP': 'MAGIC MIRROR',
    'LOADING': 'Carregando...',
    'CONNECTED': 'Conectado',
    'OFFLINE': 'Offline',
    'VERSION': 'v',
    'NEXT_EVENTS': 'Proximos Eventos',
    'NO_EVENTS': 'Sem eventos hoje',
    'NO_EVENTS_SUBTITLE': 'Aproveite seu dia livre!',
    'ALL_DAY': 'Todo dia',
    'PENDING_REGISTRATION': 'AGUARDANDO REGISTRO',
    'REGISTERING': 'REGISTRANDO...',
    'REGISTERED': 'REGISTRADO',
    'REGISTRATION_ERROR': 'ERRO DE REGISTRO'
}

# ==================== CONFIGURAÇÕES DE SISTEMA ====================
# Debugging
DEBUG_ENABLED = True
SERIAL_DEBUG = True
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARN, ERROR

# Gerenciamento de memória
AUTO_GARBAGE_COLLECT = True
GC_INTERVAL = 300  # 5 minutos
MEMORY_WARNING_THRESHOLD = 50000  # bytes

# Watchdog
WATCHDOG_ENABLED = False  # Desabilitado para debug
WATCHDOG_TIMEOUT = 30  # segundos

# ==================== FUNÇÕES UTILITÁRIAS DE CONFIGURAÇÃO ====================

def get_color(name):
    """Obter cor por nome"""
    return COLORS.get(name, COLORS['PRIMARY_TEXT'])

def get_layout_position(name):
    """Obter posição do layout por nome"""
    return LAYOUT.get(name, 0)

def get_font_size(name):
    """Obter tamanho da fonte por nome"""
    return FONTS.get(name, 1)

def get_text(name):
    """Obter texto localizado por nome"""
    return TEXTS.get(name, name)

def get_mqtt_topic(topic_type):
    """Gerar tópicos MQTT baseados no device ID"""
    base = f"magic_mirror"
    
    if topic_type == 'REGISTRATION':
        return f"{base}/registration"
    elif DEVICE_ID and topic_type in ['EVENTS', 'CONFIG', 'STATUS', 'HEARTBEAT', 'RESPONSE']:
        return f"{base}/devices/{DEVICE_ID}/{topic_type.lower()}"
    else:
        return f"{base}/general"

def is_registered():
    """Verificar se o dispositivo está registrado"""
    return bool(DEVICE_ID and API_KEY)

def set_device_credentials(device_id, api_key):
    """Definir credenciais do dispositivo após registro"""
    global DEVICE_ID, API_KEY
    DEVICE_ID = device_id
    API_KEY = api_key

def get_device_info():
    """Obter informações do dispositivo"""
    return {
        'registration_id': REGISTRATION_ID,
        'device_id': DEVICE_ID,
        'api_key': API_KEY[:10] + "..." if API_KEY else "",
        'location': DEVICE_LOCATION,
        'description': DEVICE_DESCRIPTION,
        'firmware_version': FIRMWARE_VERSION,
        'registered': is_registered()
    }

def is_debug_enabled():
    """Verificar se debug está habilitado"""
    return DEBUG_ENABLED and SERIAL_DEBUG

def reset_system():
    """Reiniciar sistema"""
    machine.reset()

def get_memory_info():
    """Informações de memória"""
    return {
        'free': gc.mem_free(),
        'allocated': gc.mem_alloc()
    }

# ==================== VALIDAÇÃO DE CONFIGURAÇÃO ====================

def validate_config():
    """Validar configurações obrigatórias"""
    issues = []
    
    # Validações críticas
    if REGISTRATION_ID == "MIRROR_SALA_001":
        issues.append("REGISTRATION_ID deve ser personalizado")
    
    if WIFI_SSID == "SUA_REDE_WIFI":
        issues.append("WIFI_SSID não configurado")
    
    if WIFI_PASSWORD == "SUA_SENHA_WIFI":
        issues.append("WIFI_PASSWORD não configurado")
    
    if MQTT_BROKER == "192.168.1.100":
        issues.append("MQTT_BROKER deve ser configurado com IP do servidor")
    
    # Validações de formato
    if not isinstance(REGISTRATION_ID, str) or len(REGISTRATION_ID) < 5:
        issues.append("REGISTRATION_ID deve ser string com pelo menos 5 caracteres")
    
    return issues

# ==================== AUTO-CONFIGURAÇÃO POR AMBIENTE ====================

def apply_environment_config(env='dev'):
    """Aplicar configuração por ambiente"""
    global DEBUG_ENABLED, LOG_LEVEL, HEARTBEAT_INTERVAL
    
    if env == 'dev':
        DEBUG_ENABLED = True
        LOG_LEVEL = "DEBUG"
        HEARTBEAT_INTERVAL = 60  # 1 minuto para desenvolvimento
    elif env == 'prod':
        DEBUG_ENABLED = False
        LOG_LEVEL = "WARN"
        HEARTBEAT_INTERVAL = 300  # 5 minutos para produção
    elif env == 'demo':
        DEBUG_ENABLED = True
        LOG_LEVEL = "INFO"
        HEARTBEAT_INTERVAL = 120  # 2 minutos para demo

# ==================== CONFIGURAÇÃO INICIAL ====================

def startup_check():
    """Verificação na inicialização"""
    print("=" * 50)
    print("MAGIC MIRROR - BOOT SEQUENCE v3.0")
    print("Sistema MQTT Only + Registration")
    print("=" * 50)
    print("[1/4] Inicializando hardware...")
    print("[2/4] Verificando configuração...")
    
    # Verificar configuração
    issues = validate_config()
    if issues:
        print("⚠️  ATENÇÃO: Problemas de configuração detectados!")
        for issue in issues[:3]:  # Mostrar apenas os 3 primeiros
            print(f"   • {issue}")
        if len(issues) > 3:
            print(f"   • ... e mais {len(issues) - 3} problemas")
        print("   Configure adequadamente o config.py")
    
    print("[3/4] Preparando sistema MQTT...")
    print("[4/4] Carregando aplicação principal...")
    
    # Informações de memória
    memory = get_memory_info()
    print(f"Memória livre após boot: {memory['free']} bytes")
    print("✅ Boot completo - iniciando main.py")
    print("=" * 50)
    
    if issues:
        print("⚠️  CONFIGURAÇÃO INCOMPLETA!")
        print("   Alguns recursos podem não funcionar")
        print("   Verifique o arquivo config.py")
        print("=" * 50)

# Executar verificação no import (exceto se for módulo principal)
if __name__ != "__main__":
    startup_check()

# ==================== TESTE DE CONFIGURAÇÃO ====================
if __name__ == "__main__":
    print("Teste de configuração Magic Mirror")
    print("=" * 40)
    
    print(f"Registration ID: {REGISTRATION_ID}")
    print(f"Device ID: {DEVICE_ID if DEVICE_ID else 'Não configurado'}")
    print(f"Registrado: {'Sim' if is_registered() else 'Não'}")
    print(f"WiFi SSID: {WIFI_SSID}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    
    # Testar validação
    issues = validate_config()
    if issues:
        print("\n❌ Problemas encontrados:")
        for issue in issues:
            print(f"  • {issue}")
    else:
        print("\n✅ Configuração válida!")
    
    # Informações de sistema
    memory = get_memory_info()
    print(f"\nMemória livre: {memory['free']} bytes")
    print(f"Memória alocada: {memory['allocated']} bytes")