# boot.py - Script de inicialização automática
"""
Magic Mirror - Boot Script v3.0 CORRIGIDO
Sem dependência de REGISTRATION_ID (removido)
"""
import machine
import utime
import gc

# LED interno para indicação visual
led = machine.Pin("LED", machine.Pin.OUT)

def boot_sequence():
    """Sequência de boot com indicações visuais"""
    print("\n" + "="*50)
    print("MAGIC MIRROR - BOOT v3.0 CORRIGIDO")
    print("Sistema MQTT com Device ID automático")
    print("="*50)
    
    stages = [
        "Inicializando hardware...",
        "Verificando configuração...", 
        "Preparando sistema MQTT...",
        "Carregando aplicação principal..."
    ]
    
    for i, stage in enumerate(stages):
        print(f"[{i+1}/4] {stage}")
        led.on()
        utime.sleep_ms(300)
        led.off()
        utime.sleep_ms(200)
    
    gc.collect()
    print(f"Memoria livre: {gc.mem_free()} bytes")
    
    led.on()
    print("Boot completo")
    print("="*50)

def check_config():
    """Verificação básica de configuração"""
    try:
        from config import WIFI_SSID, MQTT_BROKER, TOPIC_PREFIX
        
        if WIFI_SSID == "SuaRedeWiFi":
            print("ATENCAO: WiFi nao configurado!")
            print("Configure WIFI_SSID no config.py")
            return False
        
        print(f"WiFi: {WIFI_SSID}")
        print(f"MQTT: {MQTT_BROKER}")
        print(f"Topic: {TOPIC_PREFIX}")
        return True
        
    except ImportError as e:
        print(f"Erro importando config: {e}")
        return False

# Executa boot
boot_sequence()

# Verifica configuração
if check_config():
    print("Configuracao OK")
else:
    print("Verifique config.py")

print("="*50)
