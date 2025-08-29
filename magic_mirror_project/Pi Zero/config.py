# config.py - Configuração Simplificada Magic Mirror
# Versão sem WiFi - Sistema 100% offline

# ==================== CONFIGURAÇÕES DO BRASIL ====================
# Timezone do Brasil (apenas para referência)
TIMEZONE_NAME = "America/Sao_Paulo"
TIMEZONE_OFFSET = -3  # UTC-3 (Brasília)

# Formato brasileiro
DATE_FORMAT = "DD/MM/YYYY"  # 25/12/2024
TIME_FORMAT = "24H"         # 14:30

# ==================== CONFIGURAÇÕES DO DISPLAY ILI9486 ====================
# Resolução
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 480

# Cores em RGB565
COLORS = {
    'BACKGROUND': 0x0000,    # Preto - fundo
    'TIME': 0xFFFF,          # Branco - hora
    'DATE': 0xFFFF,          # Branco - data
    'EVENT_TIME': 0xFFE0,    # Amarelo - hora do evento
    'EVENT_NAME': 0xFFFF,    # Branco - nome do evento
    'BLE_ON': 0x07E0,        # Verde - BLE conectado
    'BLE_OFF': 0xF800,       # Vermelho - BLE desconectado
    'NO_EVENT': 0x7BEF,      # Cinza - sem eventos
    'EVENT_TITLE': 0x07FF,   # Ciano - título evento
}

# Tamanhos de fonte (multiplicador)
FONT_SIZES = {
    'TIME': 4,        # Hora
    'DATE': 2,        # Data
    'EVENT_TIME': 3,  # Hora do evento
    'EVENT_NAME': 2,  # Nome do evento
    'STATUS': 1,      # Status BLE
    'NO_EVENT': 2,    # Sem eventos
}

# Posições Y na tela
POSITIONS = {
    'TIME_Y': 80,        # Hora
    'DATE_Y': 140,       # Data
    'EVENT_TITLE_Y': 200, # "PRÓXIMO EVENTO"
    'EVENT_TIME_Y': 240,  # Hora do evento
    'EVENT_NAME_Y': 290,  # Nome do evento
    'NO_EVENT_Y': 230,    # "Sem eventos"
    'STATUS_Y': 10,       # Status BLE
}

# ==================== CONFIGURAÇÕES DE HARDWARE ====================
# Pinos do display ILI9486
DISPLAY_PINS = {
    'SCK': 18,   # SPI Clock
    'MOSI': 19,  # SPI Data
    'CS': 17,    # Chip Select
    'DC': 16,    # Data/Command
    'RST': 20,   # Reset
}

# Pino do botão power
POWER_BUTTON_PIN = 21

# SPI
SPI_BAUDRATE = 40000000  # 40 MHz
SPI_BUS = 0

# ==================== CONFIGURAÇÕES BLE ====================
# Nome que aparece no scan BLE
BLE_DEVICE_NAME = "MagicMirror"

# UUIDs compatíveis com seu servidor Python
BLE_SERVICE_UUID = "00001800-0000-1000-8000-00805f9b34fb"
BLE_CHAR_UUID = "00002a00-0000-1000-8000-00805f9b34fb"

# ==================== CONFIGURAÇÕES DE SISTEMA ====================
# Atualizações
DISPLAY_UPDATE_INTERVAL = 1000  # 1 segundo
BUTTON_CHECK_INTERVAL = 50      # 50ms

# Eventos
MAX_EVENTS = 10                 # Máximo de eventos
MAX_EVENT_NAME_LENGTH = 15      # Máximo 15 caracteres no nome

# Debug
DEBUG_ENABLED = False

# ==================== CONFIGURAÇÃO INICIAL DE DATA/HORA ====================
# Configure AQUI com a data/hora atual do Brasil
# Formato: (ano, mês, dia, dia_semana, hora, minuto, segundo, subsegundo)
# dia_semana: 0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado, 6=domingo

# ALTERE ESTA LINHA COM A DATA/HORA ATUAL DO BRASIL:
INITIAL_DATETIME_BRASIL = (2024, 12, 25, 2, 14, 30, 0, 0)

# ==================== TEXTOS DA INTERFACE ====================
INTERFACE_TEXTS = {
    'NEXT_EVENT': "PROXIMO EVENTO",
    'NO_EVENTS': "Sem eventos hoje", 
    'BLE_CONNECTED': "BLE",
    'STARTUP': "MAGIC MIRROR",
}

# ==================== FUNÇÕES UTILITÁRIAS ====================
def get_color(name):
    """Retorna cor por nome"""
    return COLORS.get(name, 0xFFFF)

def get_font_size(element):
    """Retorna tamanho da fonte"""
    return FONT_SIZES.get(element, 2)

def get_position_y(element):
    """Retorna posição Y"""
    return POSITIONS.get(f"{element}_Y", 100)

def debug_print(message):
    """Print condicional"""
    if DEBUG_ENABLED:
        print(f"[DEBUG] {message}")