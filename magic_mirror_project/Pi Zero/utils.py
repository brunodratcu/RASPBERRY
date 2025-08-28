# utils.py - Utilitários diversos
"""
Funções utilitárias para o Magic Mirror
"""

import utime
import gc
import machine
from config import *

def format_time(hour, minute, format_24h=True):
    """Formata hora conforme configuração"""
    if format_24h or TIME_FORMAT == 24:
        return f"{hour:02d}:{minute:02d}"
    else:
        # Formato 12h
        if hour == 0:
            return f"12:{minute:02d} AM"
        elif hour < 12:
            return f"{hour}:{minute:02d} AM"
        elif hour == 12:
            return f"12:{minute:02d} PM"
        else:
            return f"{hour-12}:{minute:02d} PM"

def format_date(year, month, day, format_type='BR'):
    """Formata data conforme configuração"""
    if format_type == 'BR' or DATE_FORMAT == 'BR':
        return f"{day:02d}/{month:02d}/{year}"
    elif format_type == 'US' or DATE_FORMAT == 'US':
        return f"{month:02d}/{day:02d}/{year}"
    elif format_type == 'ISO' or DATE_FORMAT == 'ISO':
        return f"{year}-{month:02d}-{day:02d}"
    else:
        return f"{day:02d}/{month:02d}/{year}"  # Default BR

def get_local_time():
    """Retorna hora local ajustada com timezone"""
    try:
        utc_time = utime.localtime()
        # Ajusta timezone
        timestamp = utime.mktime(utc_time) + (TIMEZONE_OFFSET * 3600)
        if DAYLIGHT_SAVING:
            timestamp += 3600  # Adiciona 1 hora no horário de verão
        
        return utime.localtime(timestamp)
    except:
        # Fallback para hora do sistema
        return utime.localtime()

def log(level, message):
    """Sistema de logging simples"""
    levels = {'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3}
    config_level = levels.get(LOG_LEVEL, 1)
    msg_level = levels.get(level, 1)
    
    if msg_level >= config_level and SERIAL_DEBUG:
        timestamp = format_time(*get_local_time()[3:5])
        print(f"[{timestamp}] {level}: {message}")

def auto_garbage_collect():
    """Coleta de lixo automática"""
    if AUTO_GARBAGE_COLLECT:
        free_before = gc.mem_free()
        gc.collect()
        free_after = gc.mem_free()
        log('DEBUG', f"GC: {free_before} -> {free_after} bytes (+{free_after-free_before})")

def get_memory_info():
    """Informações de memória"""
    return {
        'free': gc.mem_free(),
        'allocated': gc.mem_alloc(),
    }

def safe_file_read(filename, default_content=""):
    """Leitura segura de arquivo"""
    try:
        with open(filename, 'r') as f:
            return f.read()
    except:
        log('WARN', f"Arquivo não encontrado: {filename}")
        return default_content

def safe_file_write(filename, content):
    """Escrita segura de arquivo"""
    try:
        with open(filename, 'w') as f:
            f.write(content)
        return True
    except Exception as e:
        log('ERROR', f"Erro ao escrever {filename}: {e}")
        return False

def reset_system(delay_ms=3000):
    """Reset seguro do sistema"""
    log('INFO', f"Sistema será reiniciado em {delay_ms/1000}s")
    utime.sleep_ms(delay_ms)
    machine.reset()

def get_system_info():
    """Informações do sistema"""
    return {
        'freq': machine.freq(),
        'unique_id': machine.unique_id().hex(),
        'memory': get_memory_info(),
        'uptime': utime.ticks_ms() // 1000,  # segundos
    }

def validate_config():
    """Valida configurações"""
    issues = []
    
    if WIFI_SSID == "SEU_WIFI_AQUI":
        issues.append("WiFi SSID não configurado")
    
    if WIFI_PASSWORD == "SUA_SENHA_AQUI":
        issues.append("WiFi PASSWORD não configurado")
    
    if TIMEZONE_OFFSET < -12 or TIMEZONE_OFFSET > 12:
        issues.append("TIMEZONE_OFFSET inválido (-12 a +12)")
    
    if TIME_FORMAT not in [12, 24]:
        issues.append("TIME_FORMAT deve ser 12 ou 24")
    
    if DATE_FORMAT not in ['BR', 'US', 'ISO']:
        issues.append("DATE_FORMAT deve ser BR, US ou ISO")
    
    return issues

def startup_banner():
    """Banner de inicialização"""
    info = get_system_info()
    print("=" * 50)
    print("   MAGIC MIRROR - RASPBERRY PICO 2W")
    print("=" * 50)
    print(f"Versão: 2.0-BLE-Push")
    print(f"Device ID: {info['unique_id'][:8]}")
    print(f"Frequência: {info['freq']/1000000:.1f} MHz")
    print(f"Memória livre: {info['memory']['free']} bytes")
    print(f"WiFi: {WIFI_SSID}")
    print(f"Timezone: UTC{TIMEZONE_OFFSET:+d}")
    print(f"Display: 320x480 ILI9486")
    print("=" * 50)
    
    # Valida configuração
    config_issues = validate_config()
    if config_issues:
        print("AVISOS DE CONFIGURAÇÃO:")
        for issue in config_issues:
            print(f"  • {issue}")
        print("=" * 50)

def format_uptime(seconds):
    """Formata tempo de funcionamento"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def is_same_day(time1, time2):
    """Verifica se duas estruturas de tempo são do mesmo dia"""
    return (time1[0] == time2[0] and  # ano
            time1[1] == time2[1] and  # mês
            time1[2] == time2[2])     # dia

def time_until_event(event_hour, event_minute):
    """Calcula tempo até um evento"""
    now = get_local_time()
    current_minutes = now[3] * 60 + now[4]
    event_minutes = event_hour * 60 + event_minute
    
    diff = event_minutes - current_minutes
    
    if diff < 0:
        # Evento passou
        return None
    elif diff == 0:
        return "AGORA"
    elif diff < 60:
        return f"em {diff} min"
    else:
        hours = diff // 60
        minutes = diff % 60
        return f"em {hours}h {minutes}m" if minutes > 0 else f"em {hours}h"
