# config.py - Configuração Mínima Magic Mirror

# ==================== CONFIGURAÇÃO ESSENCIAL ====================
# ⚠️ ALTERE APENAS ESTAS LINHAS ⚠️

WIFI_SSID = "Bruno Dratcu"        # Nome da sua rede WiFi
WIFI_PASSWORD = "deniederror"       # Senha da sua rede WiFi  
TIMEZONE_OFFSET = -3             # Fuso horário (Brasil = -3)

# ==================== CONFIGURAÇÕES TÉCNICAS ====================
# ⚠️ SÓ ALTERE SE NECESSÁRIO ⚠️

DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

# ==================== CONFIGURAÇÕES PARA COMPATIBILIDADE ====================
# Variáveis que o main.py espera encontrar

REGISTRATION_ID = "MIRROR_001"
MAX_RETRY_ATTEMPTS = 3
CONNECTION_TIMEOUT = 15
FIRMWARE_VERSION = "2.0"
DEBUG_ENABLED = True

# Configurações MQTT (mesmo que não usado)
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883

# ==================== FUNÇÕES NECESSÁRIAS ====================
def validate_config():
    """Valida configuração - função necessária para o main.py"""
    errors = []
    
    if WIFI_SSID == "SuaRedeWiFi":
        errors.append("Configure WIFI_SSID")
    
    if WIFI_PASSWORD == "SuaSenha":
        errors.append("Configure WIFI_PASSWORD")
    
    return errors

def is_debug():
    """Função necessária para o main.py"""
    return DEBUG_ENABLED

# ==================== TESTE ====================
if __name__ == "__main__":
    print("Configuração Magic Mirror")
    print("-" * 30)
    print(f"WiFi: {WIFI_SSID}")
    print(f"Fuso: UTC{TIMEZONE_OFFSET:+d}")
    print(f"Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    
    errors = validate_config()
    if errors:
        print("\n❌ Configurar:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ Configuração OK")
