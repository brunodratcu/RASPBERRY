# boot.py - Script de inicialização automática
"""
Script executado automaticamente na inicialização do Pico
Versão 3.0 - MQTT Only + Registration System
"""
import machine
import utime
import gc

# LED interno para indicação visual
led = machine.Pin("LED", machine.Pin.OUT)

def boot_sequence():
    """Sequência de boot com indicações visuais"""
    print("\n" + "="*50)
    print("MAGIC MIRROR - BOOT SEQUENCE v3.0")
    print("Sistema MQTT Only + Registration")
    print("="*50)
    
    # Pisca LED para indicar estágios do boot
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
    
    # Coleta de lixo inicial
    gc.collect()
    print(f"Memória livre após boot: {gc.mem_free()} bytes")
    
    # LED fica ligado indicando boot completo
    led.on()
    print("✅ Boot completo - iniciando main.py")
    print("="*50)

def check_config():
    """Verificação básica de configuração"""
    try:
        from config import REGISTRATION_ID, WIFI_SSID, MQTT_BROKER
        
        if REGISTRATION_ID == "REG_CHANGEME_12345":
            print("⚠️  ATENÇÃO: REGISTRATION_ID não configurado!")
            print("   Configure um ID válido no config.py")
            return False
        
        if WIFI_SSID == "SUA_REDE_WIFI":
            print("⚠️  ATENÇÃO: WiFi não configurado!")
            print("   Configure WIFI_SSID e WIFI_PASSWORD no config.py")
            return False
        
        print(f"📋 Registration ID: {REGISTRATION_ID[:20]}...")
        print(f"📶 WiFi SSID: {WIFI_SSID}")
        print(f"📡 MQTT Broker: {MQTT_BROKER}")
        return True
        
    except ImportError as e:
        print(f"❌ Erro ao importar configuração: {e}")
        return False

# Executa sequência de boot
boot_sequence()

# Verifica configuração básica
if check_config():
    print("🚀 Configuração OK - prosseguindo com main.py")
else:
    print("⚠️  Problemas na configuração detectados")
    print("   O sistema pode não funcionar corretamente")
    print("   Verifique o arquivo config.py")

print("="*50)
