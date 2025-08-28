# boot.py - Script de inicialização automática
"""
Script executado automaticamente na inicialização do Pico
"""

import machine
import utime
import gc

# LED interno para indicação visual
led = machine.Pin("LED", machine.Pin.OUT)

def boot_sequence():
    """Sequência de boot com indicações visuais"""
    print("\n" + "="*40)
    print("MAGIC MIRROR - BOOT SEQUENCE")
    print("="*40)
    
    # Pisca LED 3 vezes
    for i in range(3):
        led.on()
        utime.sleep_ms(200)
        led.off()
        utime.sleep_ms(200)
        print(f"Boot stage {i+1}/3")
    
    # Coleta de lixo inicial
    gc.collect()
    print(f"Memória livre: {gc.mem_free()} bytes")
    
    # LED fica ligado indicando boot completo
    led.on()
    print("Boot completo - iniciando main.py")
    print("="*40)

# Executa sequência de boot
boot_sequence()

