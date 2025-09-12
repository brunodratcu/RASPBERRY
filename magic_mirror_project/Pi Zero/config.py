# config.py - Magic Mirror com MQTT Público
"""
Configuração usando broker MQTT público - Zero IP config!
"""

# ==================== MQTT PÚBLICO - SEM IP! ====================
MQTT_BROKER = "test.mosquitto.org"  # Broker público
MQTT_PORT = 1883
TOPIC_PREFIX = ""  # Será definido pelo backend automaticamente

# ==================== CONFIGURAÇÃO ÚNICA ====================
REGISTRATION_ID = "MIRROR_001"  # ALTERE AQUI - Deve ser único
WIFI_SSID = "SuaRedeWiFi"       # ALTERE AQUI
WIFI_PASSWORD = "SuaSenha"      # ALTERE AQUI

# ==================== RESTO IGUAL ====================
FIRMWARE_VERSION = "1.0"
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320
DISPLAY_BRIGHTNESS = 80

DISPLAY_PINS = {
    'SCK': 2, 'MOSI': 3, 'CS': 5, 'DC': 4, 'RST': 6, 'BL': 7
}

CONNECTION_TIMEOUT = 30
MAX_RETRY_ATTEMPTS = 3
TIMEZONE_OFFSET = -3
TIME_FORMAT = "24H"
MAX_EVENTS_DISPLAY = 5
DEBUG_ENABLED = True

def validate_config():
    issues = []
    if REGISTRATION_ID == "MIRROR_001":
        issues.append("Configure REGISTRATION_ID único")
    if WIFI_SSID == "SuaRedeWiFi":
        issues.append("Configure WIFI_SSID")
    if WIFI_PASSWORD == "SuaSenha":
        issues.append("Configure WIFI_PASSWORD")
    return issues

def is_debug():
    return DEBUG_ENABLED