# config.py - Configuração Magic Mirror v3.0 CORRIGIDO
"""
Configuração corrigida - Device ID automático
Compatível com backend v3.0
"""

# ==================== CONFIGURAÇÃO ESSENCIAL ====================
# Configure apenas estas linhas com seus dados reais
WIFI_SSID = "Bruno Dratcu"        # Sua rede WiFi
WIFI_PASSWORD = "deniederror"     # Senha do WiFi
TIMEZONE_OFFSET = -3              # Brasília = -3

# ==================== MQTT - TOPIC FIXO ====================
# IMPORTANTE: Deve ser EXATAMENTE igual ao backend
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = "magic_mirror_stable"  # FIXO - IGUAL AO SERVIDOR

# ==================== DISPLAY ====================
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

# Posições dos elementos
CLOCK_Y_POSITION = 60
DATE_Y_POSITION = 130
EVENTS_START_Y = 170
STATUS_Y_POSITION = 300

# ==================== CONFIGURAÇÕES AVANÇADAS ====================
MAX_RETRY_ATTEMPTS = 3
CONNECTION_TIMEOUT = 20
MQTT_KEEPALIVE = 60
MQTT_RECONNECT_DELAY = 5

# Intervalos (em segundos)
NTP_SYNC_INTERVAL = 3600      # 1 hora
EVENT_UPDATE_INTERVAL = 5     # 5 segundos
GC_INTERVAL = 120             # 2 minutos

# Debug
DEBUG_ENABLED = True
SHOW_MQTT_MESSAGES = True
LOG_EVENTS = True

# Cores RGB565
COLOR_PRIMARY = 0xFFFF     # Branco
COLOR_SECONDARY = 0x07FF   # Ciano
COLOR_SUCCESS = 0x07E0     # Verde
COLOR_WARNING = 0xFFE0     # Amarelo
COLOR_ERROR = 0xF800       # Vermelho

# ==================== FUNÇÕES AUXILIARES ====================
def validate_config():
    """Valida configuração essencial"""
    errors = []
    
    if WIFI_SSID == "SuaRedeWiFi":
        errors.append("Configure WIFI_SSID")
    
    if WIFI_PASSWORD == "SuaSenha":
        errors.append("Configure WIFI_PASSWORD")
    
    if not MQTT_BROKER:
        errors.append("MQTT_BROKER vazio")
    
    return errors

def get_mqtt_config():
    """Retorna config MQTT"""
    return {
        'broker': MQTT_BROKER,
        'port': MQTT_PORT,
        'topic_prefix': TOPIC_PREFIX,
        'keepalive': MQTT_KEEPALIVE
    }

# ==================== INFO DO SISTEMA ====================
FIRMWARE_VERSION = "3.0"
CONFIG_VERSION = "3.0"

# ==================== TESTE ====================
if __name__ == "__main__":
    print("="*50)
    print("MAGIC MIRROR - CONFIG v3.0")
    print("="*50)
    print(f"WiFi: {WIFI_SSID}")
    print(f"MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic: {TOPIC_PREFIX}")
    print(f"Timezone: UTC{TIMEZONE_OFFSET:+d}")
    print()
    
    errors = validate_config()
    if errors:
        print("PROBLEMAS:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("CONFIGURACAO OK!")
    print("="*50)
