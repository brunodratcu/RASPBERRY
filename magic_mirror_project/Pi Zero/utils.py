# utils.py - Utilitários Corrigidos Magic Mirror
"""
Funções utilitárias para o Magic Mirror
Versão 3.0 - MQTT Only + Backend Registration
"""

import utime
import gc
import machine
import json
from config import *

# Importar funções da fonte
try:
    from font import (
        get_char_bitmap, get_text_width, get_text_height, 
        split_text_to_fit, center_text_x, normalize_text, has_char
    )
    FONT_AVAILABLE = True
except ImportError:
    FONT_AVAILABLE = False
    print("AVISO: font.py não encontrado - funcionalidades de texto limitadas")

# ==================== FORMATAÇÃO DE TEMPO E DATA ====================

def format_time(hour, minute, format_24h=None):
    """Formata hora conforme configuração"""
    if format_24h is None:
        format_24h = (TIME_FORMAT == "24H")
    
    if format_24h:
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

def format_date(year, month, day, format_type=None):
    """Formata data conforme configuração"""
    if format_type is None:
        format_type = DATE_FORMAT
    
    if format_type == 'DD/MM/YYYY':
        return f"{day:02d}/{month:02d}/{year}"
    elif format_type == 'MM/DD/YYYY':
        return f"{month:02d}/{day:02d}/{year}"
    elif format_type == 'YYYY-MM-DD':
        return f"{year}-{month:02d}-{day:02d}"
    else:
        return f"{day:02d}/{month:02d}/{year}"  # Default

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

def format_datetime_string(dt_tuple=None):
    """Formata datetime completo em string"""
    if dt_tuple is None:
        dt_tuple = get_local_time()
    
    date_str = format_date(dt_tuple[0], dt_tuple[1], dt_tuple[2])
    time_str = format_time(dt_tuple[3], dt_tuple[4])
    
    return f"{date_str} {time_str}"

def get_iso_date_string(dt_tuple=None):
    """Retorna data no formato ISO (YYYY-MM-DD)"""
    if dt_tuple is None:
        dt_tuple = get_local_time()
    
    return f"{dt_tuple[0]}-{dt_tuple[1]:02d}-{dt_tuple[2]:02d}"

def time_until_event(event_hour, event_minute):
    """Calcula tempo até um evento"""
    now = get_local_time()
    current_minutes = now[3] * 60 + now[4]
    event_minutes = event_hour * 60 + event_minute
    
    diff = event_minutes - current_minutes
    
    if diff < 0:
        # Evento passou ou é para o próximo dia
        diff += 24 * 60  # Assumir próximo dia
        if diff > 12 * 60:  # Se for mais de 12h, provavelmente passou
            return None
    
    if diff == 0:
        return "AGORA"
    elif diff < 60:
        return f"em {diff} min"
    else:
        hours = diff // 60
        minutes = diff % 60
        if minutes > 0:
            return f"em {hours}h {minutes}m"
        else:
            return f"em {hours}h"

def is_same_day(time1, time2):
    """Verifica se duas estruturas de tempo são do mesmo dia"""
    return (time1[0] == time2[0] and  # ano
            time1[1] == time2[1] and  # mês
            time1[2] == time2[2])     # dia

def is_event_today(event_date_str):
    """Verifica se um evento é hoje"""
    try:
        today = get_iso_date_string()
        return event_date_str == today
    except:
        return False

def is_event_soon(event_time_str, minutes_threshold=30):
    """Verifica se um evento está próximo (dentro de X minutos)"""
    try:
        if not event_time_str or ':' not in event_time_str:
            return False
        
        event_hour, event_minute = map(int, event_time_str.split(':'))
        now = get_local_time()
        current_minutes = now[3] * 60 + now[4]
        event_minutes = event_hour * 60 + event_minute
        
        diff = event_minutes - current_minutes
        return 0 <= diff <= minutes_threshold
        
    except:
        return False

# ==================== SISTEMA DE LOGGING ====================

def log(level, message, data=None):
    """Sistema de logging simplificado"""
    if not SERIAL_DEBUG:
        return
    
    levels = {'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3}
    config_level = levels.get(LOG_LEVEL, 1)
    msg_level = levels.get(level, 1)
    
    if msg_level >= config_level:
        timestamp = format_time(*get_local_time()[3:5])
        prefix = f"[{timestamp}] {level}"
        
        # Adicionar identificação do dispositivo
        if DEVICE_ID:
            prefix += f" [{DEVICE_ID}]"
        elif REGISTRATION_ID != "MIRROR_SALA_001":
            reg_short = REGISTRATION_ID[:8] + "..."
            prefix += f" [{reg_short}]"
        
        print(f"{prefix}: {message}")
        
        # Se há dados adicionais, imprimir também
        if data and DEBUG_ENABLED:
            try:
                data_str = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
                print(f"  └─ Data: {data_str}")
            except:
                print(f"  └─ Data: {data}")

def log_error(message, exception=None):
    """Log específico para erros"""
    if exception:
        log('ERROR', f"{message}: {exception}")
    else:
        log('ERROR', message)

def log_info(message):
    """Log específico para informações"""
    log('INFO', message)

def log_debug(message, data=None):
    """Log específico para debug"""
    log('DEBUG', message, data)

def log_warn(message):
    """Log específico para avisos"""
    log('WARN', message)

# ==================== GERENCIAMENTO DE MEMÓRIA ====================

def auto_garbage_collect():
    """Coleta de lixo automática com logging"""
    if AUTO_GARBAGE_COLLECT:
        free_before = gc.mem_free()
        gc.collect()
        free_after = gc.mem_free()
        freed = free_after - free_before
        
        if freed > 0:
            log_debug(f"GC: {free_before} -> {free_after} bytes (+{freed})")
        
        return freed
    return 0

def get_memory_info():
    """Informações detalhadas de memória"""
    free = gc.mem_free()
    allocated = gc.mem_alloc()
    total = free + allocated
    
    return {
        'free': free,
        'allocated': allocated,
        'total': total,
        'usage_percent': round((allocated / total) * 100, 1) if total > 0 else 0
    }

def check_memory_health():
    """Verifica saúde da memória"""
    memory_info = get_memory_info()
    
    if memory_info['free'] < MEMORY_WARNING_THRESHOLD:
        log_warn(f"Memória baixa: {memory_info['free']} bytes livres ({memory_info['usage_percent']}% usado)")
        return False
    
    return True

def force_garbage_collect():
    """Força coleta de lixo e retorna bytes liberados"""
    free_before = gc.mem_free()
    gc.collect()
    free_after = gc.mem_free()
    freed = free_after - free_before
    
    log_info(f"GC forçado: liberados {freed} bytes")
    return freed

# ==================== VALIDAÇÃO E CONFIGURAÇÃO ====================

def validate_config():
    """Valida configurações obrigatórias"""
    issues = []
    
    # Validações críticas - usar isinstance para verificar tipo antes de métodos
    if not isinstance(REGISTRATION_ID, str):
        issues.append("REGISTRATION_ID deve ser uma string")
    elif REGISTRATION_ID == "MIRROR_SALA_001":
        issues.append("REGISTRATION_ID deve ser personalizado")
    elif len(REGISTRATION_ID) < 5:
        issues.append("REGISTRATION_ID deve ter pelo menos 5 caracteres")
    else:
        # Verificar se contém apenas caracteres válidos
        valid_chars = True
        for char in REGISTRATION_ID:
            if not (char.isalnum() or char in '_-'):
                valid_chars = False
                break
        if not valid_chars:
            issues.append("REGISTRATION_ID deve conter apenas letras, números, _ e -")
    
    if WIFI_SSID == "SUA_REDE_WIFI":
        issues.append("WIFI_SSID não configurado")
    
    if WIFI_PASSWORD == "SUA_SENHA_WIFI":
        issues.append("WIFI_PASSWORD não configurado")
    
    # Validações de parâmetros
    if TIMEZONE_OFFSET < -12 or TIMEZONE_OFFSET > 12:
        issues.append("TIMEZONE_OFFSET inválido (-12 a +12)")
    
    if TIME_FORMAT not in ["12H", "24H"]:
        issues.append("TIME_FORMAT deve ser '12H' ou '24H'")
    
    if DISPLAY_BRIGHTNESS < 0 or DISPLAY_BRIGHTNESS > 100:
        issues.append("DISPLAY_BRIGHTNESS deve estar entre 0 e 100")
    
    if MAX_EVENTS_DISPLAY < 1 or MAX_EVENTS_DISPLAY > 10:
        issues.append("MAX_EVENTS_DISPLAY deve estar entre 1 e 10")
    
    return issues

def is_config_valid():
    """Verifica se configuração é válida"""
    return len(validate_config()) == 0

# ==================== SISTEMA E HARDWARE ====================

def reset_system(delay_ms=3000):
    """Reset seguro do sistema"""
    log_info(f"Sistema será reiniciado em {delay_ms/1000}s")
    
    # Tentar salvar estado antes do reset
    try:
        save_system_state()
    except:
        pass
    
    utime.sleep_ms(delay_ms)
    machine.reset()

def save_system_state():
    """Salvar estado do sistema antes de reset"""
    try:
        state = {
            'last_restart': utime.time(),
            'restart_reason': 'manual_reset',
            'registration_id': REGISTRATION_ID,
            'device_id': DEVICE_ID,
            'registered': is_registered(),
            'memory_free': gc.mem_free(),
            'uptime': utime.ticks_ms() // 1000
        }
        safe_json_write('system_state.json', state)
        log_debug("Estado do sistema salvo")
    except Exception as e:
        log_error("Erro ao salvar estado", e)

def load_system_state():
    """Carregar estado anterior do sistema"""
    try:
        state = safe_json_read('system_state.json')
        if state:
            log_info(f"Estado anterior carregado: uptime {state.get('uptime', 0)}s")
        return state
    except Exception as e:
        log_error("Erro ao carregar estado", e)
        return {}

def get_system_info():
    """Informações completas do sistema"""
    try:
        info = {
            'registration_id': REGISTRATION_ID,
            'device_id': DEVICE_ID,
            'registered': is_registered(),
            'firmware_version': FIRMWARE_VERSION,
            'freq': machine.freq(),
            'unique_id': machine.unique_id().hex(),
            'memory': get_memory_info(),
            'uptime_ms': utime.ticks_ms(),
            'uptime_seconds': utime.ticks_ms() // 1000,
            'current_time': get_local_time(),
            'timezone_offset': TIMEZONE_OFFSET,
            'ntp_synced': hasattr(utime, 'time') and utime.time() > 1000000000,
        }
        return info
    except Exception as e:
        log_error("Erro ao obter info do sistema", e)
        return {}

def get_device_status():
    """Status detalhado do dispositivo"""
    memory_info = get_memory_info()
    
    return {
        'registration_id': REGISTRATION_ID,
        'device_id': DEVICE_ID if DEVICE_ID else 'Not assigned',
        'registered': is_registered(),
        'firmware_version': FIRMWARE_VERSION,
        'uptime_seconds': utime.ticks_ms() // 1000,
        'free_memory': memory_info['free'],
        'memory_usage_percent': memory_info['usage_percent'],
        'current_time': format_datetime_string(),
        'timezone': f"UTC{TIMEZONE_OFFSET:+d}",
        'wifi_connected': False,  # Será atualizado pela aplicação
        'mqtt_connected': False,  # Será atualizado pela aplicação
        'last_sync': None,        # Será atualizado pela aplicação
    }

# ==================== FORMATAÇÃO E APRESENTAÇÃO ====================

def startup_banner():
    """Banner de inicialização simplificado"""
    info = get_system_info()
    
    print("=" * 60)
    print("   MAGIC MIRROR - RASPBERRY PICO 2W")
    print("   Sistema MQTT Only v3.0")
    print("=" * 60)
    print(f"Registration ID: {REGISTRATION_ID}")
    if DEVICE_ID:
        print(f"Device ID: {DEVICE_ID}")
        print(f"Status: Registrado")
    else:
        print(f"Device ID: Aguardando registro")
        print(f"Status: Não registrado")
    print(f"Firmware: {FIRMWARE_VERSION}")
    print(f"Unique ID: {info['unique_id'][:16]}...")
    print(f"Frequência: {info['freq']/1000000:.1f} MHz")
    print(f"Memória livre: {info['memory']['free']:,} bytes")
    print(f"Uso de memória: {info['memory']['usage_percent']}%")
    print(f"Uptime: {format_uptime(info['uptime_seconds'])}")
    print("-" * 60)
    print(f"WiFi SSID: {WIFI_SSID}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Timezone: UTC{TIMEZONE_OFFSET:+d} ({TIMEZONE_NAME})")
    print(f"Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT} @ {DISPLAY_BRIGHTNESS}%")
    print("=" * 60)
    
    # Validar configuração
    config_issues = validate_config()
    if config_issues:
        print("⚠️  AVISOS DE CONFIGURAÇÃO:")
        for issue in config_issues[:5]:  # Máximo 5 avisos
            print(f"  • {issue}")
        if len(config_issues) > 5:
            print(f"  • ... e mais {len(config_issues) - 5} avisos")
        print("=" * 60)
    else:
        print("✅ Configuração válida!")
        if is_registered():
            print("✅ Dispositivo registrado!")
        else:
            print("⏳ Aguardando registro no backend")
        print("=" * 60)

def format_uptime(seconds):
    """Formata tempo de funcionamento"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"

def format_bytes(bytes_value):
    """Formata bytes em unidades legíveis"""
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.1f} KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.1f} GB"

def truncate_text(text, max_length, suffix="..."):
    """Trunca texto mantendo legibilidade"""
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

# ==================== UTILITÁRIOS DE EVENTOS ====================

def filter_events_by_time(events, start_time=None, end_time=None):
    """Filtra eventos por horário"""
    if not events:
        return []
    
    filtered = []
    now = get_local_time()
    current_minutes = now[3] * 60 + now[4]
    
    for event in events:
        event_time = event.get('time', '')
        is_all_day = event.get('isAllDay', False)
        
        # Pular eventos de dia inteiro se filtro estiver ativo
        if is_all_day and not FILTER_ALL_DAY_EVENTS:
            continue
        
        # Pular eventos passados se filtro estiver ativo
        if FILTER_PAST_EVENTS and event_time and ':' in event_time:
            try:
                event_hour, event_minute = map(int, event_time.split(':'))
                event_minutes = event_hour * 60 + event_minute
                
                if event_minutes < current_minutes:
                    continue
            except:
                pass
        
        # Aplicar filtros de horário se fornecidos
        if start_time and event_time < start_time:
            continue
        if end_time and event_time > end_time:
            continue
        
        filtered.append(event)
    
    return filtered

def sort_events_by_time(events):
    """Ordena eventos por horário"""
    def event_sort_key(event):
        time_str = event.get('time', '23:59')
        
        # Eventos de dia inteiro vão para o final
        if event.get('isAllDay', False):
            return 9999
        
        try:
            if ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
                return hour * 60 + minute
        except:
            pass
        
        return 9999  # Se não conseguir parsear, vai para o final
    
    return sorted(events, key=event_sort_key)

def group_events_by_status(events):
    """Agrupa eventos por status (atual, próximo, futuro)"""
    now = get_local_time()
    current_minutes = now[3] * 60 + now[4]
    
    current = []
    soon = []
    future = []
    
    for event in events:
        event_time = event.get('time', '')
        
        if event.get('isAllDay', False):
            future.append(event)
            continue
        
        if not event_time or ':' not in event_time:
            future.append(event)
            continue
        
        try:
            event_hour, event_minute = map(int, event_time.split(':'))
            event_minutes = event_hour * 60 + event_minute
            
            diff = event_minutes - current_minutes
            
            if -15 <= diff <= 15:  # Evento atual (±15 min)
                current.append(event)
            elif 15 < diff <= 60:  # Evento próximo (próxima hora)
                soon.append(event)
            else:
                future.append(event)
        except:
            future.append(event)
    
    return {
        'current': current,
        'soon': soon,
        'future': future
    }

# ==================== MANIPULAÇÃO DE ARQUIVOS SIMPLIFICADA ====================

def safe_file_read(filename, default_content="", encoding='utf-8'):
    """Leitura segura de arquivo"""
    try:
        with open(filename, 'r', encoding=encoding) as f:
            content = f.read()
            log_debug(f"Arquivo lido: {filename} ({len(content)} chars)")
            return content
    except OSError as e:
        log_warn(f"Arquivo não encontrado: {filename}")
        return default_content
    except Exception as e:
        log_error(f"Erro ao ler {filename}", e)
        return default_content

def safe_file_write(filename, content, encoding='utf-8'):
    """Escrita segura de arquivo"""
    try:
        with open(filename, 'w', encoding=encoding) as f:
            f.write(content)
        log_debug(f"Arquivo escrito: {filename} ({len(content)} chars)")
        return True
    except Exception as e:
        log_error(f"Erro ao escrever {filename}", e)
        return False

def safe_json_read(filename, default_data=None):
    """Leitura segura de arquivo JSON"""
    if default_data is None:
        default_data = {}
    
    try:
        content = safe_file_read(filename)
        if content:
            data = json.loads(content)
            log_debug(f"JSON lido: {filename}")
            return data
        else:
            return default_data
    except Exception as e:
        log_error(f"Erro ao ler JSON {filename}", e)
        return default_data

def safe_json_write(filename, data):
    """Escrita segura de arquivo JSON"""
    try:
        content = json.dumps(data)
        return safe_file_write(filename, content)
    except Exception as e:
        log_error(f"Erro ao escrever JSON {filename}", e)
        return False

# ==================== DEBUGGING E DIAGNÓSTICO ====================

def debug_print(message, data=None):
    """Print condicional para debug"""
    if DEBUG_ENABLED and SERIAL_DEBUG:
        print(f"[DEBUG] {message}")
        if data:
            try:
                if isinstance(data, (dict, list)):
                    print(f"[DEBUG] Data: {json.dumps(data)}")
                else:
                    print(f"[DEBUG] Data: {data}")
            except:
                print(f"[DEBUG] Data: {str(data)}")

def system_diagnostics():
    """Diagnóstico completo do sistema"""
    print("\n" + "="*50)
    print("DIAGNÓSTICO DO SISTEMA")
    print("="*50)
    
    # Informações básicas
    info = get_system_info()
    print(f"Registration ID: {info.get('registration_id', 'N/A')}")
    print(f"Device ID: {info.get('device_id', 'Não atribuído')}")
    print(f"Registrado: {'Sim' if info.get('registered') else 'Não'}")
    print(f"Firmware: {info.get('firmware_version', 'N/A')}")
    print(f"Uptime: {format_uptime(info.get('uptime_seconds', 0))}")
    print(f"Memória: {format_bytes(info['memory']['free'])} livre / {format_bytes(info['memory']['total'])} total")
    print(f"Uso de memória: {info['memory']['usage_percent']}%")
    
    # Configuração
    print("\nCONFIGURAÇÃO:")
    print(f"  WiFi SSID: {WIFI_SSID}")
    print(f"  MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Timezone: UTC{TIMEZONE_OFFSET:+d}")
    print(f"  Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    
    # Validação
    issues = validate_config()
    if issues:
        print("\nPROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("\n✅ Configuração válida")
    
    # Estado dos arquivos
    print("\nARQUIVOS:")
    files = ['config.py', 'utils.py', 'main.py', 'font.py', 'system_state.json']
    for filename in files:
        try:
            with open(filename, 'r') as f:
                size = len(f.read())
            print(f"  ✅ {filename} ({format_bytes(size)})")
        except:
            print(f"  ❌ {filename} (não encontrado)")
    
    print("="*50 + "\n")

# ==================== FUNÇÕES DE COMPATIBILIDADE ====================

def compat_check():
    """Verifica compatibilidade de módulos"""
    modules = {
        'umqtt.simple': 'MQTT',
        'ujson': 'JSON',
        'ntptime': 'NTP sync',
        'network': 'WiFi'
    }
    
    available = {}
    for module, description in modules.items():
        try:
            __import__(module)
            available[module] = True
            log_debug(f"Módulo {module} disponível")
        except ImportError:
            available[module] = False
            log_warn(f"Módulo {module} não disponível - {description} não funcionará")
    
    return available

# ==================== WRAPPERS PARA FUNÇÕES DE FONT ====================

def safe_get_text_width(text, scale=1):
    """Wrapper seguro para get_text_width"""
    if FONT_AVAILABLE:
        return get_text_width(text, scale)
    else:
        return len(text) * 8 * scale  # Fallback básico

def safe_get_text_height(scale=1):
    """Wrapper seguro para get_text_height"""
    if FONT_AVAILABLE:
        return get_text_height(scale)
    else:
        return 8 * scale  # Fallback básico

def safe_split_text_to_fit(text, max_width, scale=1):
    """Wrapper seguro para split_text_to_fit"""
    if FONT_AVAILABLE:
        return split_text_to_fit(text, max_width, scale)
    else:
        # Fallback básico
        char_width = 8 * scale
        max_chars = max_width // char_width
        if len(text) <= max_chars:
            return [text]
        else:
            return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

def safe_center_text_x(text, display_width, scale=1):
    """Wrapper seguro para center_text_x"""
    if FONT_AVAILABLE:
        return center_text_x(text, display_width, scale)
    else:
        # Fallback básico
        text_width = len(text) * 8 * scale
        return (display_width - text_width) // 2

def safe_normalize_text(text):
    """Wrapper seguro para normalize_text"""
    if FONT_AVAILABLE:
        return normalize_text(text)
    else:
        # Fallback básico - remover acentos comuns
        replacements = {
            'ã': 'a', 'á': 'a', 'ç': 'c', 'é': 'e', 'ê': 'e',
            'í': 'i', 'ó': 'o', 'ô': 'o', 'ú': 'u',
            'Ã': 'A', 'Á': 'A', 'Ç': 'C', 'É': 'E', 'Ê': 'E',
            'Í': 'I', 'Ó': 'O', 'Ô': 'O', 'Ú': 'U'
        }
        result = text
        for accented, normal in replacements.items():
            result = result.replace(accented, normal)
        return result

# ==================== INICIALIZAÇÃO DOS UTILITÁRIOS ====================

def init_utils():
    """Inicializar utilitários"""
    log_info("Utilitários inicializados - MQTT Only")
    
    # Verificar compatibilidade
    compat_check()
    
    # Carregar estado anterior se existir
    load_system_state()
    
    # Executar coleta de lixo inicial
    auto_garbage_collect()
    
    # Log do status de registro
    if is_registered():
        log_info(f"Dispositivo registrado: {DEVICE_ID}")
    else:
        log_info(f"Dispositivo não registrado: {REGISTRATION_ID}")

# Auto-inicialização quando módulo é importado
if __name__ != "__main__":
    init_utils()

# ==================== TESTES (quando executado diretamente) ====================
if __name__ == "__main__":
    print("Teste dos utilitários Magic Mirror - MQTT Only")
    print("="*40)
    
    # Teste de formatação de tempo
    now = get_local_time()
    print(f"Hora atual: {format_time(now[3], now[4])}")
    print(f"Data atual: {format_date(now[0], now[1], now[2])}")
    print(f"DateTime: {format_datetime_string()}")
    
    # Teste de memória
    memory = get_memory_info()
    print(f"Memória livre: {format_bytes(memory['free'])}")
    print(f"Uso de memória: {memory['usage_percent']}%")
    
    # Teste de registro
    print(f"Registration ID: {REGISTRATION_ID}")
    print(f"Device ID: {DEVICE_ID if DEVICE_ID else 'Não atribuído'}")
    print(f"Registrado: {'Sim' if is_registered() else 'Não'}")
    
    # Teste de validação
    issues = validate_config()
    if issues:
        print("Problemas de configuração:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("Configuração válida!")
    
    # Diagnóstico completo
    system_diagnostics()