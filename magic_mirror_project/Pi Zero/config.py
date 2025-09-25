# config.py - Configuração Magic Mirror com MQTT v2.0
"""
Configuração atualizada para o sistema corrigido com topic prefix dinâmico
Compatível com o main.py atualizado
"""

# ==================== CONFIGURAÇÃO ESSENCIAL ====================
# Configure apenas estas linhas com seus dados
WIFI_SSID = "Bruno Dratcu"        # Nome da sua rede WiFi
WIFI_PASSWORD = "deniederror"     # Senha da sua rede WiFi  
TIMEZONE_OFFSET = -3              # Fuso horário (Brasil = -3)

# ==================== CONFIGURAÇÃO MQTT DINÂMICA ====================
# O TOPIC_PREFIX inicial - será atualizado automaticamente pelo servidor
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
TOPIC_PREFIX = "magic_mirror_h9Vcvfx4ZLM"  # Valor inicial - servidor enviará o correto

# DEVICE_ID será gerado automaticamente baseado na MAC address
# Não defina manualmente - será criado como PICO_XXXXXX

# ==================== CONFIGURAÇÕES TÉCNICAS ====================
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320

# ==================== CONFIGURAÇÕES DE COMPATIBILIDADE ====================
# Configurações para o sistema atualizado
MAX_RETRY_ATTEMPTS = 3
CONNECTION_TIMEOUT = 20          # Aumentado para 20 segundos
MQTT_KEEPALIVE = 60
MQTT_RECONNECT_DELAY = 5

# Configurações de sincronização
NTP_SYNC_INTERVAL = 3600         # 1 hora em segundos
EVENT_UPDATE_INTERVAL = 5        # Atualizar eventos a cada 5 segundos
GC_INTERVAL = 120               # Garbage collection a cada 2 minutos

# ==================== CONFIGURAÇÕES DE DEBUG ====================
DEBUG_ENABLED = True
SHOW_MQTT_MESSAGES = True        # Mostrar mensagens MQTT detalhadas
SHOW_MEMORY_INFO = False
LOG_EVENTS = True               # Log de eventos recebidos

# ==================== CONFIGURAÇÕES DE DISPLAY ====================
# Posições dos elementos na tela
CLOCK_Y_POSITION = 60
DATE_Y_POSITION = 125
EVENTS_START_Y = 170
STATUS_Y_POSITION = 300

# Cores personalizadas (formato RGB565)
COLOR_PRIMARY = 0xFFFF     # Branco
COLOR_SECONDARY = 0x07FF   # Ciano
COLOR_SUCCESS = 0x07E0     # Verde
COLOR_WARNING = 0xFFE0     # Amarelo
COLOR_ERROR = 0xF800       # Vermelho

# ==================== FUNÇÕES NECESSÁRIAS ====================
def validate_config():
    """Valida configuração essencial"""
    errors = []
    
    if WIFI_SSID in ["SuaRedeWiFi", "Bruno Dratcu"]:
        if WIFI_SSID == "SuaRedeWiFi":
            errors.append("Configure WIFI_SSID com o nome da sua rede")
    
    if WIFI_PASSWORD in ["SuaSenha", ""]:
        errors.append("Configure WIFI_PASSWORD com a senha da sua rede")
    
    if not MQTT_BROKER:
        errors.append("MQTT_BROKER não pode estar vazio")
    
    if MQTT_PORT <= 0 or MQTT_PORT > 65535:
        errors.append("MQTT_PORT deve estar entre 1 e 65535")
    
    return errors

def is_debug():
    """Verifica se debug está habilitado"""
    return DEBUG_ENABLED

def get_display_config():
    """Retorna configurações do display"""
    return {
        'width': DISPLAY_WIDTH,
        'height': DISPLAY_HEIGHT,
        'clock_y': CLOCK_Y_POSITION,
        'date_y': DATE_Y_POSITION,
        'events_y': EVENTS_START_Y,
        'status_y': STATUS_Y_POSITION
    }

def get_mqtt_config():
    """Retorna configurações MQTT"""
    return {
        'broker': MQTT_BROKER,
        'port': MQTT_PORT,
        'topic_prefix': TOPIC_PREFIX,
        'keepalive': MQTT_KEEPALIVE,
        'reconnect_delay': MQTT_RECONNECT_DELAY
    }

def get_network_config():
    """Retorna configurações de rede"""
    return {
        'ssid': WIFI_SSID,
        'password': WIFI_PASSWORD,
        'timeout': CONNECTION_TIMEOUT,
        'max_retries': MAX_RETRY_ATTEMPTS
    }

def get_timing_config():
    """Retorna configurações de tempo"""
    return {
        'timezone_offset': TIMEZONE_OFFSET,
        'ntp_sync_interval': NTP_SYNC_INTERVAL,
        'event_update_interval': EVENT_UPDATE_INTERVAL,
        'gc_interval': GC_INTERVAL
    }

# ==================== INFORMAÇÕES DO SISTEMA ====================
FIRMWARE_VERSION = "2.0"
CONFIG_VERSION = "2.0"
SUPPORTED_FEATURES = [
    "dynamic_topic_prefix",
    "unique_device_id", 
    "automatic_registration",
    "event_synchronization",
    "ntp_sync",
    "mqtt_reconnect"
]

# ==================== TESTE DA CONFIGURAÇÃO ====================
if __name__ == "__main__":
    print("=" * 50)
    print("MAGIC MIRROR - CONFIGURAÇÃO v2.0")
    print("=" * 50)
    print("REDE:")
    print(f"  WiFi SSID: {WIFI_SSID}")
    print(f"  Timeout: {CONNECTION_TIMEOUT}s")
    print(f"  Fuso horário: UTC{TIMEZONE_OFFSET:+d}")
    print()
    print("DISPLAY:")
    print(f"  Resolução: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print(f"  Posições configuradas: OK")
    print()
    print("MQTT:")
    print(f"  Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Topic inicial: {TOPIC_PREFIX}")
    print(f"  Keepalive: {MQTT_KEEPALIVE}s")
    print()
    print("RECURSOS:")
    print(f"  Debug: {'Habilitado' if DEBUG_ENABLED else 'Desabilitado'}")
    print(f"  Log MQTT: {'Sim' if SHOW_MQTT_MESSAGES else 'Não'}")
    print(f"  Versão: {FIRMWARE_VERSION}")
    print()
    
    # Validação
    errors = validate_config()
    if errors:
        print("PROBLEMAS DE CONFIGURAÇÃO:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        print()
        print("Corrija os problemas acima antes de usar o sistema.")
    else:
        print("CONFIGURAÇÃO VALIDADA: OK")
        print("Sistema pronto para uso!")
    
    print("=" * 50)

# ==================== NOTAS IMPORTANTES ====================
"""
INSTRUÇÕES DE USO:

1. CONFIGURAÇÃO OBRIGATÓRIA:
   - Altere WIFI_SSID e WIFI_PASSWORD com os dados da sua rede
   - Mantenha TOPIC_PREFIX como "magic_mirror_default" 
   - O sistema atualizará automaticamente para o topic correto

2. FUNCIONAMENTO:
   - O Pico gerará um DEVICE_ID único baseado na MAC address
   - O servidor enviará o topic prefix correto durante o registro
   - Eventos serão sincronizados automaticamente após aprovação

3. DEBUG:
   - Mantenha DEBUG_ENABLED = True para acompanhar o funcionamento
   - Logs detalhados aparecerão no console do Thonny/terminal

4. COMPATIBILIDADE:
   - Este config é compatível com o main.py atualizado (v2.0)
   - Suporta topic prefix dinâmico e device ID único
   - Inclui todas as correções para sincronização MQTT

5. RESOLUÇÃO DE PROBLEMAS:
   - Se eventos não aparecerem, verifique se o dispositivo foi aprovado
   - Confira se o backend está rodando e conectado ao MQTT
   - Verifique os logs para mensagens de erro

Para suporte, verifique os logs do sistema e garanta que:
- WiFi está conectado
- MQTT broker está acessível  
- Backend Python está rodando
- Dispositivo foi aprovado na interface web
"""
