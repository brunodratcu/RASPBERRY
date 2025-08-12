# config.py - Configurações centralizadas para o Pico W

# ===== CONFIGURAÇÕES DE REDE =====
WIFI_SSID = "SUA_REDE_WIFI"         # Nome da sua rede WiFi
WIFI_PASSWORD = "SUA_SENHA_WIFI"     # Senha da sua rede WiFi

# ===== CONFIGURAÇÕES DO DISPOSITIVO =====
DEVICE_NAME = "Pico-Eventos-001"     # Nome único para este dispositivo
DEVICE_LOCATION = "Escritorio"       # Localização do dispositivo (opcional)

# ===== CONFIGURAÇÕES DO DISPLAY =====
# Tipo de display - descomente apenas o que você está usando
DISPLAY_TYPE = "ILI9341"  # 320x240
# DISPLAY_TYPE = "ILI9488"  # 480x320
# DISPLAY_TYPE = "ILI9984"  # Outro modelo

# Resolução baseada no tipo
DISPLAY_CONFIGS = {
    "ILI9341": {"width": 320, "height": 240},
    "ILI9488": {"width": 480, "height": 320}, 
    "ILI9984": {"width": 480, "height": 320}
}

DISPLAY_WIDTH = DISPLAY_CONFIGS[DISPLAY_TYPE]["width"]
DISPLAY_HEIGHT = DISPLAY_CONFIGS[DISPLAY_TYPE]["height"]
DISPLAY_ROTATION = 1  # 0=portrait, 1=landscape

# ===== PINOS SPI DO DISPLAY =====
# Ajuste conforme sua conexão física
SPI_PINS = {
    "SCK": 10,    # Clock
    "MOSI": 11,   # Data
    "CS": 9,      # Chip Select
    "DC": 8,      # Data/Command
    "RST": 12     # Reset
}

# ===== CONFIGURAÇÕES DE FUNCIONAMENTO =====
DISPLAY_UPDATE_INTERVAL = 60         # Atualiza display a cada 60 segundos
MEMORY_CLEANUP_INTERVAL = 300        # Limpeza de memória a cada 5 minutos
MAX_EVENTS_DISPLAY = 8               # Máximo de eventos mostrados na tela
WIFI_TIMEOUT = 30                    # Timeout para conexão WiFi em segundos
HTTP_TIMEOUT = 10                    # Timeout para requisições HTTP
SERVER_PORT = 80                     # Porta do servidor HTTP interno

# ===== CONFIGURAÇÕES DE CORES (RGB565) =====
COLORS = {
    "BLACK": 0x0000,
    "WHITE": 0xFFFF,
    "RED": 0xF800,
    "GREEN": 0x07E0,
    "BLUE": 0x001F,
    "CYAN": 0x07FF,
    "MAGENTA": 0xF81F,
    "YELLOW": 0xFFE0,
    "GRAY": 0x8410,
    "DARK_GRAY": 0x4208,
    "LIGHT_GRAY": 0xC618,
    "ORANGE": 0xFD20,
    "PURPLE": 0x8010
}

# ===== CONFIGURAÇÕES DE TEXTO =====
TEXT_CONFIG = {
    "HEADER_COLOR": COLORS["CYAN"],
    "TIME_COLOR": COLORS["YELLOW"], 
    "EVENT_COLOR_1": COLORS["WHITE"],
    "EVENT_COLOR_2": COLORS["CYAN"],
    "STATUS_ONLINE": COLORS["GREEN"],
    "STATUS_OFFLINE": COLORS["RED"],
    "ERROR_COLOR": COLORS["RED"],
    "INFO_COLOR": COLORS["GRAY"]
}

# ===== CONFIGURAÇÕES DE DEBUG =====
DEBUG_MODE = True                    # Ativa logs detalhados
SHOW_MEMORY_INFO = True              # Mostra informações de memória
SHOW_WIFI_DETAILS = True             # Mostra detalhes de conexão WiFi

# ===== CONFIGURAÇÕES AVANÇADAS =====
HTTP_BUFFER_SIZE = 2048              # Tamanho do buffer para requisições HTTP
MAX_RETRY_ATTEMPTS = 3               # Máximo de tentativas de reconexão
RECONNECT_DELAY = 5                  # Delay entre tentativas de reconexão
ENABLE_WATCHDOG = False              # Ativa watchdog (experimental)

# ===== MENSAGENS PERSONALIZADAS =====
MESSAGES = {
    "NO_EVENTS": "Nenhum evento hoje",
    "WAITING_SYNC": "Aguardando sincronizacao...",
    "WIFI_ERROR": "Erro de conexao WiFi",
    "CONNECTING": "Conectando",
    "SYSTEM_ERROR": "Erro do sistema",
    "LOADING": "Carregando",
    "ONLINE": "ONLINE",
    "OFFLINE": "OFFLINE"
}

# ===== VALIDAÇÃO DE CONFIGURAÇÕES =====
def validate_config():
    """Valida se as configurações estão corretas"""
    errors = []
    
    # Verifica WiFi
    if not WIFI_SSID or WIFI_SSID == "SUA_REDE_WIFI":
        errors.append("Configure WIFI_SSID com o nome da sua rede")
    
    if not WIFI_PASSWORD or WIFI_PASSWORD == "SUA_SENHA_WIFI":
        errors.append("Configure WIFI_PASSWORD com a senha da sua rede")
    
    # Verifica display
    if DISPLAY_TYPE not in DISPLAY_CONFIGS:
        errors.append(f"DISPLAY_TYPE '{DISPLAY_TYPE}' não suportado")
    
    # Verifica pinos
    pinos_usados = []
    for nome, pino in SPI_PINS.items():
        if pino in pinos_usados:
            errors.append(f"Pino {pino} usado mais de uma vez")
        pinos_usados.append(pino)
    
    # Verifica intervalos
    if DISPLAY_UPDATE_INTERVAL < 10:
        errors.append("DISPLAY_UPDATE_INTERVAL muito baixo (mínimo 10s)")
    
    if MAX_EVENTS_DISPLAY > 15:
        errors.append("MAX_EVENTS_DISPLAY muito alto (máximo 15)")
    
    return errors

# ===== FUNÇÃO DE HELP =====
def print_config_help():
    """Imprime ajuda sobre as configurações"""
    print("="*60)
    print("📋 GUIA DE CONFIGURAÇÃO DO PICO W")
    print("="*60)
    print()
    print("🔧 CONFIGURAÇÕES OBRIGATÓRIAS:")
    print(f"   WIFI_SSID: '{WIFI_SSID}'")
    print(f"   WIFI_PASSWORD: '{WIFI_PASSWORD}'")
    print()
    print("🖥️ DISPLAY CONFIGURADO:")
    print(f"   Tipo: {DISPLAY_TYPE}")
    print(f"   Resolução: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print(f"   Rotação: {DISPLAY_ROTATION}")
    print()
    print("📌 PINOS SPI:")
    for nome, pino in SPI_PINS.items():
        print(f"   {nome}: GPIO {pino}")
    print()
    print("⚙️ FUNCIONAMENTO:")
    print(f"   Atualização display: {DISPLAY_UPDATE_INTERVAL}s")
    print(f"   Máximo eventos: {MAX_EVENTS_DISPLAY}")
    print(f"   Porta servidor: {SERVER_PORT}")
    print()
    
    # Verifica configuração
    errors = validate_config()
    if errors:
        print("❌ ERROS DE CONFIGURAÇÃO:")
        for error in errors:
            print(f"   • {error}")
    else:
        print("✅ Configuração válida!")
    
    print("="*60)

# ===== CONFIGURAÇÕES AUTOMÁTICAS =====
def get_display_module():
    """Retorna o módulo correto do display baseado no tipo"""
    display_modules = {
        "ILI9341": "ili9341",
        "ILI9488": "ili9488", 
        "ILI9984": "ili9984"
    }
    return display_modules.get(DISPLAY_TYPE, "ili9341")

def get_color_depth():
    """Retorna profundidade de cor baseada no display"""
    return 16  # RGB565 para todos os displays suportados

# ===== CONFIGURAÇÕES DE REDE ESPECÍFICAS =====
NTP_SERVERS = [
    "pool.ntp.org",
    "time.nist.gov",
    "br.pool.ntp.org"  # Servidor brasileiro
]

# Configurações de DNS (caso necessário)
DNS_SERVERS = [
    "8.8.8.8",      # Google
    "1.1.1.1",      # Cloudflare
    "208.67.222.222" # OpenDNS
]

# ===== CONFIGURAÇÕES DE SERVIDOR BACKEND =====
# Essas configurações são opcionais - o sistema usa descoberta automática
BACKEND_CONFIG = {
    "AUTO_DISCOVER": True,           # Descoberta automática do servidor
    "SERVER_IP": None,               # IP fixo do servidor (se não usar descoberta)
    "SERVER_PORT": 5000,             # Porta do servidor Flask
    "POLL_INTERVAL": 30,             # Intervalo para verificar servidor (se usado)
    "TIMEOUT": 10                    # Timeout para requisições ao servidor
}

# ===== CONFIGURAÇÕES DE LOG =====
LOG_CONFIG = {
    "LEVEL": "INFO",                 # DEBUG, INFO, WARNING, ERROR
    "SHOW_TIMESTAMP": True,          # Mostra timestamp nos logs
    "SHOW_MEMORY": True,             # Mostra uso de memória nos logs
    "MAX_LOG_LINES": 100             # Máximo de linhas de log em memória
}

# ===== CONFIGURAÇÕES EXPERIMENTAIS =====
EXPERIMENTAL = {
    "DEEP_SLEEP": False,             # Modo deep sleep (experimental)
    "BRIGHTNESS_CONTROL": False,     # Controle de brilho (se suportado)
    "TOUCH_SUPPORT": False,          # Suporte a toque (se disponível)
    "SOUND_ALERTS": False            # Alertas sonoros (se buzzer conectado)
}

# ===== EXPORTAR CONFIGURAÇÕES =====
def get_config_dict():
    """Retorna todas as configurações como dicionário"""
    return {
        "wifi": {
            "ssid": WIFI_SSID,
            "password": "***",  # Não expor senha
            "timeout": WIFI_TIMEOUT
        },
        "device": {
            "name": DEVICE_NAME,
            "location": DEVICE_LOCATION
        },
        "display": {
            "type": DISPLAY_TYPE,
            "width": DISPLAY_WIDTH,
            "height": DISPLAY_HEIGHT,
            "rotation": DISPLAY_ROTATION,
            "pins": SPI_PINS
        },
        "intervals": {
            "display_update": DISPLAY_UPDATE_INTERVAL,
            "memory_cleanup": MEMORY_CLEANUP_INTERVAL
        },
        "limits": {
            "max_events": MAX_EVENTS_DISPLAY,
            "http_buffer": HTTP_BUFFER_SIZE,
            "retry_attempts": MAX_RETRY_ATTEMPTS
        },
        "debug": {
            "debug_mode": DEBUG_MODE,
            "show_memory": SHOW_MEMORY_INFO,
            "show_wifi": SHOW_WIFI_DETAILS
        }
    }

# ===== FUNÇÃO DE INICIALIZAÇÃO =====
if __name__ == "__main__":
    print_config_help()
