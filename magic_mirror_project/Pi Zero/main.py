#!/usr/bin/env python3
"""
Magic Mirror - Main Application MQTT Only
Raspberry Pi Pico 2W - Sistema Simplificado
Versão 3.0 - MQTT Only + Backend Registration
"""

import machine
import utime
import time
import gc
import json
import network
import ntptime
from machine import Pin, SPI, PWM, Timer, WDT

# Importar módulos do projeto
from config import *
from utils import *

# Importar módulos MQTT
try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    log('ERROR', 'MQTT não disponível - sistema não funcionará')

# ==================== CLASSE DE GERENCIAMENTO DE TEMPO ====================
class TimeManager:
    def __init__(self):
        self.rtc = machine.RTC()
        self.last_ntp_sync = 0
        self.ntp_synced = False
        
    def sync_ntp(self):
        """Sincronizar horário via NTP"""
        for server in NTP_SERVERS:
            try:
                log('INFO', f'Sincronizando NTP com {server}...')
                
                ntptime.host = server
                ntptime.settime()
                
                # Ajustar para timezone local
                current_time = utime.localtime()
                adjusted_time = utime.mktime(current_time) + (TIMEZONE_OFFSET * 3600)
                
                if DAYLIGHT_SAVING:
                    adjusted_time += 3600
                
                adjusted_struct = utime.localtime(adjusted_time)
                
                # Definir no RTC
                self.rtc.datetime((
                    adjusted_struct[0],  # year
                    adjusted_struct[1],  # month  
                    adjusted_struct[2],  # day
                    adjusted_struct[6],  # weekday
                    adjusted_struct[3],  # hour
                    adjusted_struct[4],  # minute
                    adjusted_struct[5],  # second
                    0                    # subseconds
                ))
                
                self.last_ntp_sync = utime.time()
                self.ntp_synced = True
                
                formatted_time = self.get_formatted_time()
                log('INFO', f'NTP sincronizado: {formatted_time}')
                return True
                
            except Exception as e:
                log('WARN', f'Erro NTP {server}: {e}')
                continue
        
        log('ERROR', 'Falha em todos os servidores NTP')
        return False
    
    def should_sync_ntp(self):
        """Verificar se deve sincronizar NTP"""
        return (utime.time() - self.last_ntp_sync) >= NTP_SYNC_INTERVAL
    
    def get_current_time(self):
        """Obter horário atual do RTC"""
        return self.rtc.datetime()
    
    def get_formatted_time(self):
        """Obter horário formatado"""
        dt = self.rtc.datetime()
        if TIME_FORMAT == "24H":
            return f"{dt[4]:02d}:{dt[5]:02d}:{dt[6]:02d}"
        else:
            hour = dt[4]
            ampm = "AM" if hour < 12 else "PM"
            if hour == 0:
                hour = 12
            elif hour > 12:
                hour -= 12
            return f"{hour}:{dt[5]:02d}:{dt[6]:02d} {ampm}"
    
    def get_formatted_date(self):
        """Obter data formatada"""
        dt = self.rtc.datetime()
        if DATE_FORMAT == "DD/MM/YYYY":
            return f"{dt[2]:02d}/{dt[1]:02d}/{dt[0]}"
        elif DATE_FORMAT == "MM/DD/YYYY":
            return f"{dt[1]:02d}/{dt[2]:02d}/{dt[0]}"
        else:  # YYYY-MM-DD
            return f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}"
    
    def get_today_date_string(self):
        """Obter data de hoje no formato YYYY-MM-DD"""
        dt = self.rtc.datetime()
        return f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}"
    
    def is_today(self, date_str):
        """Verificar se uma data é hoje"""
        try:
            return date_str == self.get_today_date_string()
        except:
            return False

# ==================== CLASSE DO DISPLAY ====================
class DisplayManager:
    def __init__(self, time_manager):
        self.time_manager = time_manager
        self.current_events = []
        self.last_update = 0
        self.screen_saver_active = False
        self.last_activity = utime.time()
        self.registration_status = "pending"
        
        # Inicializar hardware
        self.init_hardware()
        self.clear_screen()
        self.show_startup_screen()
    
    def init_hardware(self):
        """Inicializar hardware do display"""
        try:
            # Configurar SPI
            self.spi = SPI(
                SPI_CONFIG['BUS'],
                baudrate=SPI_CONFIG['BAUDRATE'],
                sck=Pin(DISPLAY_PINS['SCK']),
                mosi=Pin(DISPLAY_PINS['MOSI'])
            )
            
            # Pinos de controle
            self.cs = Pin(DISPLAY_PINS['CS'], Pin.OUT)
            self.dc = Pin(DISPLAY_PINS['DC'], Pin.OUT)  
            self.rst = Pin(DISPLAY_PINS['RST'], Pin.OUT)
            self.bl = PWM(Pin(DISPLAY_PINS['BL']))
            
            # Reset do display
            self.rst.value(0)
            utime.sleep_ms(100)
            self.rst.value(1)
            utime.sleep_ms(100)
            
            # Configurar backlight
            self.bl.freq(1000)
            self.set_brightness(DISPLAY_BRIGHTNESS)
            
            log('INFO', 'Display inicializado com sucesso')
            
        except Exception as e:
            log('ERROR', f'Erro ao inicializar display: {e}')
    
    def set_brightness(self, percent):
        """Definir brilho do display"""
        if percent < 0:
            percent = 0
        elif percent > 100:
            percent = 100
            
        duty = int((percent / 100) * 65535)
        self.bl.duty_u16(duty)
    
    def clear_screen(self):
        """Limpar tela"""
        # Implementação específica do driver ILI9486
        # Esta é uma versão simplificada - adapte para seu driver específico
        if is_debug_enabled():
            print("CLEAR: Tela limpa")
    
    def draw_pixel(self, x, y, color):
        """Desenhar um pixel na tela"""
        # Implementação específica do driver
        if is_debug_enabled() and False:  # Muito verboso, desabilitado por padrão
            print(f"PIXEL: ({x}, {y}) = {hex(color)}")
    
    def draw_char_bitmap(self, char, x, y, color, scale=1):
        """Desenhar um caractere usando bitmap"""
        bitmap = get_char_bitmap(char)
        
        for row in range(8):
            for col in range(8):
                if bitmap[row] & (0x80 >> col):  # Verificar se bit está setado
                    # Desenhar pixel escalado
                    for sy in range(scale):
                        for sx in range(scale):
                            pixel_x = x + col * scale + sx
                            pixel_y = y + row * scale + sy
                            if 0 <= pixel_x < DISPLAY_WIDTH and 0 <= pixel_y < DISPLAY_HEIGHT:
                                self.draw_pixel(pixel_x, pixel_y, color)
    
    def draw_text(self, text, x, y, color=None, size=1):
        """Desenhar texto na tela usando fonte bitmap"""
        if color is None:
            color = get_color('PRIMARY_TEXT')
        
        # Normalizar texto (remover caracteres não suportados)
        text = normalize_text(text)
        
        current_x = x
        char_width = 8 * size
        char_height = 8 * size
        
        for char in text:
            # Verificar se ainda cabe na tela
            if current_x + char_width > DISPLAY_WIDTH:
                break
            
            self.draw_char_bitmap(char, current_x, y, color, size)
            current_x += char_width
        
        if is_debug_enabled():
            print(f"DRAW: '{text}' at ({x}, {y}) color={hex(color)} size={size}")
    
    def draw_text_centered(self, text, y, color=None, size=1):
        """Desenhar texto centralizado horizontalmente"""
        x = center_text_x(text, DISPLAY_WIDTH, size)
        self.draw_text(text, x, y, color, size)
    
    def draw_text_multiline(self, text, x, y, max_width, color=None, size=1, line_spacing=2):
        """Desenhar texto com quebra de linha automática"""
        if color is None:
            color = get_color('PRIMARY_TEXT')
        
        lines = split_text_to_fit(text, max_width, size)
        current_y = y
        line_height = get_text_height(size) + line_spacing
        
        for line in lines:
            if current_y + line_height > DISPLAY_HEIGHT:
                break
            self.draw_text(line, x, current_y, color, size)
            current_y += line_height
        
        return current_y
    
    def draw_line(self, x1, y1, x2, y2, color=None):
        """Desenhar linha"""
        if color is None:
            color = get_color('DIVIDER')
        
        if is_debug_enabled():
            print(f"LINE: ({x1}, {y1}) to ({x2}, {y2}) color={hex(color)}")
    
    def show_startup_screen(self):
        """Tela de inicialização"""
        self.clear_screen()
        
        # Título centralizado
        title = get_text('STARTUP')
        self.draw_text_centered(title, 80, get_color('PRIMARY_TEXT'), get_font_size('HEADER'))
        
        # Informações do dispositivo
        device_info = get_device_info()
        desc_lines = split_text_to_fit(device_info['description'], DISPLAY_WIDTH - 20, 2)
        y_pos = 130
        
        for line in desc_lines:
            self.draw_text_centered(line, y_pos, get_color('SECONDARY_TEXT'), 2)
            y_pos += 20
        
        # Registration ID (truncado)
        reg_id_display = f"REG ID: {REGISTRATION_ID[:15]}..."
        self.draw_text_centered(reg_id_display, y_pos + 20, get_color('SECONDARY_TEXT'), 1)
        
        # Versão
        version_text = f"v{FIRMWARE_VERSION}"
        self.draw_text_centered(version_text, y_pos + 40, get_color('SECONDARY_TEXT'), 1)
        
        # Status
        status_text = get_text('LOADING')
        self.draw_text_centered(status_text, y_pos + 70, get_color('STATUS_SYNC'), 2)
        
        log('INFO', 'Tela de startup exibida')
    
    def show_registration_screen(self, status="pending"):
        """Mostrar tela de registro"""
        self.clear_screen()
        self.registration_status = status
        
        # Definir cor e texto baseado no status
        if status == "pending":
            color = get_color('STATUS_PENDING')
            main_text = get_text('PENDING_REGISTRATION')
            sub_text = "Aguarde aprovacao no backend"
        elif status == "registering":
            color = get_color('STATUS_SYNC')
            main_text = get_text('REGISTERING')
            sub_text = "Enviando dados de registro"
        elif status == "registered":
            color = get_color('STATUS_ONLINE')
            main_text = get_text('REGISTERED')
            sub_text = "Dispositivo registrado com sucesso"
        elif status == "error":
            color = get_color('STATUS_OFFLINE')
            main_text = get_text('REGISTRATION_ERROR')
            sub_text = "Verifique REGISTRATION_ID"
        else:
            color = get_color('STATUS_WARNING')
            main_text = "STATUS DESCONHECIDO"
            sub_text = ""
        
        # Cabeçalho centralizado
        header_lines = split_text_to_fit(main_text, DISPLAY_WIDTH - 20, 2)
        y_pos = 60
        
        for line in header_lines:
            self.draw_text_centered(line, y_pos, color, 2)
            y_pos += 25
        
        # Registration ID
        reg_id_display = REGISTRATION_ID[:18] + "..." if len(REGISTRATION_ID) > 21 else REGISTRATION_ID
        reg_text = f"REG ID: {reg_id_display}"
        self.draw_text_centered(reg_text, y_pos + 20, get_color('SECONDARY_TEXT'), 1)
        
        # Status
        if sub_text:
            sub_lines = split_text_to_fit(sub_text, DISPLAY_WIDTH - 20, 1)
            y_pos += 50
            for line in sub_lines:
                self.draw_text_centered(line, y_pos, get_color('SECONDARY_TEXT'), 1)
                y_pos += 15
        
        # Hora atual
        current_time = self.time_manager.get_formatted_time()
        self.draw_text_centered(current_time, y_pos + 30, get_color('TIME'), 3)
        
        # Instruções (apenas se pendente)
        if status == "pending":
            instructions = [
                "1. Acesse o backend web",
                "2. Aprove este dispositivo", 
                "3. Aguarde sincronizacao"
            ]
            y_pos += 80
            for instruction in instructions:
                self.draw_text_centered(instruction, y_pos, get_color('SECONDARY_TEXT'), 1)
                y_pos += 15
        
        # Rodapé
        version_text = f"v{FIRMWARE_VERSION}"
        self.draw_text(version_text, 10, DISPLAY_HEIGHT - 20, get_color('SECONDARY_TEXT'), 1)
        
        self.update_activity()
    
    def show_main_screen(self, events_data=None):
        """Mostrar tela principal com eventos"""
        self.clear_screen()
        
        # Cabeçalho com data/hora centralizados
        current_time = self.time_manager.get_formatted_time()
        current_date = self.time_manager.get_formatted_date()
        
        # Hora centralizada
        self.draw_text_centered(current_time, get_layout_position('TIME'), 
                               get_color('TIME'), get_font_size('TIME'))
        
        # Data centralizada
        self.draw_text_centered(current_date, get_layout_position('DATE'),
                               get_color('DATE'), get_font_size('DATE'))
        
        # Linha divisória
        self.draw_line(get_layout_position('MARGIN_X'), get_layout_position('DIVIDER'),
                      DISPLAY_WIDTH - get_layout_position('MARGIN_X'), get_layout_position('DIVIDER'))
        
        # Eventos
        if events_data and events_data.get('events'):
            self.show_events_section(events_data['events'])
        else:
            self.show_no_events()
        
        # Status de conexão no rodapé
        self.show_status_footer()
        
        self.update_activity()
    
    def show_events_section(self, events):
        """Mostrar seção de eventos"""
        # Título centralizado
        title = get_text('NEXT_EVENTS')
        self.draw_text_centered(title, get_layout_position('EVENTS_TITLE'),
                               get_color('EVENT_TITLE'), get_font_size('EVENT_TITLE'))
        
        # Lista de eventos
        y_pos = get_layout_position('EVENTS_START')
        events_shown = 0
        
        current_time = self.time_manager.get_current_time()
        current_minutes = current_time[4] * 60 + current_time[5]
        
        for event in events[:MAX_EVENTS_DISPLAY]:
            if y_pos > DISPLAY_HEIGHT - 80:  # Deixar espaço para rodapé
                break
            
            # Processar horário do evento
            event_time = event.get('time', '')
            is_all_day = event.get('isAllDay', False)
            
            # Determinar cor baseada na proximidade
            event_color = get_color('EVENT_TIME')
            if not is_all_day and event_time:
                try:
                    event_hour, event_minute = map(int, event_time.split(':'))
                    event_minutes = event_hour * 60 + event_minute
                    
                    # Se o evento é em menos de 30 minutos
                    if 0 <= (event_minutes - current_minutes) <= 30:
                        event_color = get_color('EVENT_SOON')
                except:
                    pass
            
            # Horário (lado esquerdo)
            display_time = get_text('ALL_DAY') if is_all_day else event_time
            self.draw_text(display_time, get_layout_position('MARGIN_X'), y_pos,
                          event_color, get_font_size('EVENT_TIME'))
            
            # Título do evento (lado direito, com quebra de linha se necessário)
            title = event.get('title', get_text('NO_EVENTS'))
            title_x = get_layout_position('MARGIN_X') + 70
            title_width = DISPLAY_WIDTH - title_x - get_layout_position('MARGIN_X')
            
            # Desenhar título com quebra automática
            title_lines = split_text_to_fit(title, title_width, get_font_size('EVENT_TITLE'))
            title_y = y_pos
            
            for line in title_lines[:2]:  # Máximo 2 linhas por evento
                self.draw_text(line, title_x, title_y,
                              get_color('PRIMARY_TEXT'), get_font_size('EVENT_TITLE'))
                title_y += 18
            
            # Local (se houver)
            location = event.get('location', '')
            if location and len(location) > 0:
                # Truncar local se muito longo
                if len(location) > MAX_EVENT_LOCATION_LENGTH:
                    location = location[:MAX_EVENT_LOCATION_LENGTH-3] + "..."
                
                location_text = f"📍 {location}"
                self.draw_text(location_text, title_x, title_y,
                              get_color('EVENT_LOCATION'), get_font_size('EVENT_LOCATION'))
                y_pos += get_layout_position('EVENT_HEIGHT')
            else:
                y_pos += get_layout_position('EVENT_HEIGHT') - 10
            
            # Espaçamento entre eventos
            y_pos += get_layout_position('EVENT_SPACING')
            events_shown += 1
        
        # Indicador de mais eventos
        if len(events) > MAX_EVENTS_DISPLAY:
            more_text = f"+ {len(events) - MAX_EVENTS_DISPLAY} mais..."
            self.draw_text_centered(more_text, y_pos + 10,
                                   get_color('SECONDARY_TEXT'), get_font_size('STATUS'))
    
    def show_no_events(self):
        """Mostrar mensagem de sem eventos"""
        no_events_text = get_text('NO_EVENTS')
        self.draw_text_centered(no_events_text, get_layout_position('EVENTS_START') + 40,
                               get_color('NO_EVENTS'), get_font_size('NO_EVENTS'))
        
        subtitle_text = get_text('NO_EVENTS_SUBTITLE')
        self.draw_text_centered(subtitle_text, get_layout_position('EVENTS_START') + 70,
                               get_color('SECONDARY_TEXT'), get_font_size('STATUS'))
    
    def show_status_footer(self):
        """Mostrar rodapé com status"""
        y_pos = DISPLAY_HEIGHT - 25
        
        # Device ID ou Registration ID (lado esquerdo)
        if is_registered():
            device_text = f"ID: {DEVICE_ID}"
        else:
            reg_id_short = REGISTRATION_ID[:10] + "..." if len(REGISTRATION_ID) > 13 else REGISTRATION_ID
            device_text = f"REG: {reg_id_short}"
        
        self.draw_text(device_text, get_layout_position('MARGIN_X'), y_pos,
                      get_color('SECONDARY_TEXT'), get_font_size('STATUS'))
        
        # Versão (lado direito)
        version_text = f"{get_text('VERSION')}{FIRMWARE_VERSION}"
        version_width = get_text_width(version_text, get_font_size('STATUS'))
        version_x = DISPLAY_WIDTH - version_width - get_layout_position('MARGIN_X')
        self.draw_text(version_text, version_x, y_pos,
                      get_color('SECONDARY_TEXT'), get_font_size('STATUS'))
    
    def update_connection_status(self, mqtt_connected, last_sync=None):
        """Atualizar status de conexão no rodapé"""
        y_pos = DISPLAY_HEIGHT - 45
        
        # Status MQTT (lado esquerdo)
        mqtt_status = get_text('CONNECTED') if mqtt_connected else get_text('OFFLINE')
        mqtt_color = get_color('STATUS_ONLINE') if mqtt_connected else get_color('STATUS_OFFLINE')
        mqtt_text = f"MQTT: {mqtt_status}"
        
        self.draw_text(mqtt_text, get_layout_position('MARGIN_X'), y_pos,
                      mqtt_color, get_font_size('STATUS'))
        
        # Última sincronização (lado direito)
        if last_sync:
            sync_text = f"Sync: {last_sync}"
            sync_width = get_text_width(sync_text, get_font_size('STATUS'))
            sync_x = DISPLAY_WIDTH - sync_width - get_layout_position('MARGIN_X')
            self.draw_text(sync_text, sync_x, y_pos,
                          get_color('SECONDARY_TEXT'), get_font_size('STATUS'))
    
    def update_activity(self):
        """Atualizar timestamp da última atividade"""
        self.last_activity = utime.time()
        
        # Desativar screen saver se estava ativo
        if self.screen_saver_active:
            self.screen_saver_active = False
            self.set_brightness(DISPLAY_BRIGHTNESS)
    
    def check_screen_saver(self):
        """Verificar se deve ativar screen saver"""
        if not SCREEN_SAVER_ENABLED:
            return
        
        time_since_activity = utime.time() - self.last_activity
        
        if time_since_activity >= SCREEN_SAVER_TIMEOUT and not self.screen_saver_active:
            self.screen_saver_active = True
            self.set_brightness(SCREEN_SAVER_BRIGHTNESS)
            log('INFO', 'Screen saver ativado')

# ==================== CLASSE DE CONECTIVIDADE ====================
class NetworkManager:
    def __init__(self, display_manager):
        self.display_manager = display_manager
        self.wlan = None
        self.is_connected = False
        self.connection_attempts = 0
        self.max_attempts = MAX_RETRY_ATTEMPTS
    
    def connect_wifi(self):
        """Conectar ao WiFi"""
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        
        if self.wlan.isconnected():
            self.is_connected = True
            return True
        
        log('INFO', f'Conectando ao WiFi: {WIFI_SSID}')
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                log('INFO', f'Tentativa WiFi {attempt}/{self.max_attempts}')
                
                self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                
                timeout = 0
                while not self.wlan.isconnected() and timeout < CONNECTION_TIMEOUT:
                    utime.sleep(1)
                    timeout += 1
                
                if self.wlan.isconnected():
                    ip_info = self.wlan.ifconfig()
                    self.is_connected = True
                    
                    log('INFO', f'WiFi conectado: {ip_info[0]}')
                    return True
                else:
                    log('WARN', f'Tentativa {attempt} falhou')
                    utime.sleep(RETRY_DELAY)
                    
            except Exception as e:
                log('ERROR', f'Erro na conexão WiFi: {e}')
                self.connection_attempts += 1
        
        self.is_connected = False
        log('ERROR', f'Falha WiFi após {self.max_attempts} tentativas')
        return False
    
    def check_connection(self):
        """Verificar status da conexão"""
        if self.wlan and self.wlan.isconnected():
            self.is_connected = True
            return True
        else:
            self.is_connected = False
            return False
    
    def get_connection_info(self):
        """Obter informações da conexão"""
        if self.wlan and self.wlan.isconnected():
            return {
                'ip': self.wlan.ifconfig()[0],
                'connected': True,
                'ssid': WIFI_SSID
            }
        return {'connected': False}

# ==================== CLASSE MQTT ====================
class MQTTManager:
    def __init__(self, display_manager, time_manager):
        self.display_manager = display_manager
        self.time_manager = time_manager
        self.client = None
        self.connected = False
        self.registered = False
        self.last_heartbeat = 0
        self.last_message = 0
        self.last_registration_attempt = 0
        self.current_events = None
    
    def connect(self):
        """Conectar ao broker MQTT"""
        if not MQTT_AVAILABLE:
            log('ERROR', 'MQTT não disponível')
            return False
        
        try:
            log('INFO', f'Conectando MQTT: {MQTT_BROKER}')
            
            # Criar cliente
            client_id = f"magic_mirror_{machine.unique_id().hex()[:8]}"
            self.client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
            
            # Configurar callback
            self.client.set_callback(self.on_message)
            
            # Configurar credenciais se necessário
            if MQTT_USERNAME and MQTT_PASSWORD:
                self.client.set_username_password(MQTT_USERNAME, MQTT_PASSWORD)
            
            # Conectar
            self.client.connect()
            
            # Subscrever ao tópico de registro
            self.client.subscribe(get_mqtt_topic('REGISTRATION'))
            
            # Se já registrado, subscrever aos tópicos específicos
            if is_registered():
                self.subscribe_device_topics()
                self.registered = True
            
            self.connected = True
            log('INFO', f'MQTT conectado: {MQTT_BROKER}')
            
            return True
            
        except Exception as e:
            self.connected = False
            log('ERROR', f'Erro MQTT: {e}')
            return False
    
    def subscribe_device_topics(self):
        """Subscrever aos tópicos específicos do dispositivo"""
        if not self.connected or not is_registered():
            return
        
        try:
            self.client.subscribe(get_mqtt_topic('EVENTS'))
            self.client.subscribe(get_mqtt_topic('CONFIG'))
            log('INFO', f'Subscrito aos tópicos do dispositivo: {DEVICE_ID}')
        except Exception as e:
            log('ERROR', f'Erro ao subscrever tópicos: {e}')
    
    def on_message(self, topic, msg):
        """Callback para mensagens recebidas"""
        try:
            topic_str = topic.decode()
            payload = json.loads(msg.decode())
            
            log('INFO', f'MQTT recebido: {topic_str}')
            
            if topic_str == get_mqtt_topic('REGISTRATION'):
                self.handle_registration_response(payload)
            elif topic_str == get_mqtt_topic('EVENTS'):
                self.handle_events(payload)
            elif topic_str == get_mqtt_topic('CONFIG'):
                self.handle_config(payload)
            
            self.last_message = utime.time()
            
        except Exception as e:
            log('ERROR', f'Erro ao processar MQTT: {e}')
    
    def handle_registration_response(self, payload):
        """Processar resposta de registro"""
        try:
            if payload.get('registration_id') == REGISTRATION_ID:
                if payload.get('status') == 'approved':
                    # Registro aprovado - receber credenciais
                    device_id = payload.get('device_id')
                    api_key = payload.get('api_key')
                    
                    if device_id and api_key:
                        # Definir credenciais globalmente
                        set_device_credentials(device_id, api_key)
                        
                        # Subscrever aos novos tópicos
                        self.subscribe_device_topics()
                        self.registered = True
                        
                        log('INFO', f'Registro aprovado! Device ID: {device_id}')
                        self.display_manager.show_registration_screen("registered")
                        
                        # Enviar status inicial
                        utime.sleep(2)
                        self.send_status("online")
                        
                elif payload.get('status') == 'pending':
                    log('INFO', 'Registro ainda pendente de aprovação')
                    self.display_manager.show_registration_screen("pending")
                    
                elif payload.get('status') == 'rejected':
                    log('ERROR', f'Registro rejeitado: {payload.get("reason", "Motivo não especificado")}')
                    self.display_manager.show_registration_screen("error")
                    
        except Exception as e:
            log('ERROR', f'Erro ao processar registro: {e}')
    
    def handle_events(self, events_data):
        """Processar eventos recebidos"""
        try:
            log('INFO', f'Eventos recebidos: {events_data.get("count", 0)}')
            
            # Verificar se é para hoje
            event_date = events_data.get('date', '')
            if not self.time_manager.is_today(event_date):
                log('WARN', f'Eventos não são para hoje: {event_date}')
                return
            
            # Armazenar eventos
            self.current_events = events_data
            
            # Mostrar na tela
            self.display_manager.show_main_screen(events_data)
            
            # Confirmar recebimento
            self.send_response("sync_complete", {
                "event_count": events_data.get('count', 0),
                "date": event_date
            })
            
        except Exception as e:
            log('ERROR', f'Erro ao processar eventos: {e}')
            self.send_response("error", {"message": str(e)})
    
    def handle_config(self, config_data):
        """Processar configuração recebida"""
        try:
            log('INFO', f'Configuração recebida: {config_data}')
            
            # Aplicar configurações dinâmicas
            if 'brightness' in config_data:
                brightness = config_data['brightness']
                self.display_manager.set_brightness(brightness)
                log('INFO', f'Brilho ajustado para {brightness}%')
            
            if 'screen_saver_timeout' in config_data:
                global SCREEN_SAVER_TIMEOUT
                SCREEN_SAVER_TIMEOUT = config_data['screen_saver_timeout']
                log('INFO', f'Screen saver timeout: {SCREEN_SAVER_TIMEOUT}s')
            
            # Confirmar aplicação da configuração
            self.send_response("config_applied", config_data)
            
        except Exception as e:
            log('ERROR', f'Erro ao processar configuração: {e}')
    
    def send_registration_request(self):
        """Enviar solicitação de registro"""
        if not self.connected or self.registered:
            return False
        
        # Verificar intervalo mínimo entre tentativas
        current_time = utime.time()
        if (current_time - self.last_registration_attempt) < REGISTRATION_CHECK_INTERVAL:
            return False
        
        try:
            # Obter informações do hardware
            unique_id = machine.unique_id().hex()
            memory_info = get_memory_info()
            
            registration_data = {
                'registration_id': REGISTRATION_ID,
                'hardware_id': unique_id,
                'firmware_version': FIRMWARE_VERSION,
                'location': DEVICE_LOCATION,
                'description': DEVICE_DESCRIPTION,
                'timestamp': utime.time(),
                'ip_address': get_device_ip(),
                'free_memory': memory_info['free'],
                'action': 'register'
            }
            
            topic = get_mqtt_topic('REGISTRATION')
            self.client.publish(topic, json.dumps(registration_data))
            self.last_registration_attempt = current_time
            
            log('INFO', 'Solicitação de registro enviada')
            self.display_manager.show_registration_screen("registering")
            return True
            
        except Exception as e:
            log('ERROR', f'Erro ao enviar registro: {e}')
            return False
    
    def send_status(self, status):
        """Enviar status do dispositivo"""
        if not self.connected or not self.registered:
            return False
        
        try:
            # Obter informações do sistema
            memory_info = get_memory_info()
            uptime = utime.ticks_ms() // 1000
            
            status_data = {
                'device_id': DEVICE_ID,
                'registration_id': REGISTRATION_ID,
                'status': status,
                'timestamp': utime.time(),
                'uptime': uptime,
                'free_memory': memory_info['free'],
                'firmware_version': FIRMWARE_VERSION,
                'current_time': self.time_manager.get_formatted_time(),
                'ip_address': get_device_ip(),
                'last_sync': self.last_message,
                'ntp_synced': self.time_manager.ntp_synced
            }
            
            topic = get_mqtt_topic('STATUS')
            self.client.publish(topic, json.dumps(status_data))
            return True
            
        except Exception as e:
            log('ERROR', f'Erro ao enviar status: {e}')
            return False
    
    def send_heartbeat(self):
        """Enviar heartbeat"""
        if not self.connected or not self.registered:
            return False
        
        try:
            memory_info = get_memory_info()
            uptime = utime.ticks_ms() // 1000
            
            heartbeat_data = {
                'device_id': DEVICE_ID,
                'registration_id': REGISTRATION_ID,
                'timestamp': utime.time(),
                'uptime': uptime,
                'free_memory': memory_info['free'],
                'ntp_synced': self.time_manager.ntp_synced
            }
            
            topic = get_mqtt_topic('HEARTBEAT')
            self.client.publish(topic, json.dumps(heartbeat_data))
            self.last_heartbeat = utime.time()
            return True
            
        except Exception as e:
            log('ERROR', f'Erro ao enviar heartbeat: {e}')
            return False
    
    def send_response(self, response_type, data=None):
        """Enviar resposta para o servidor"""
        if not self.connected or not self.registered:
            return False
        
        try:
            response_data = {
                'device_id': DEVICE_ID,
                'registration_id': REGISTRATION_ID,
                'type': response_type,
                'timestamp': utime.time(),
                'data': data or {}
            }
            
            topic = get_mqtt_topic('RESPONSE')
            self.client.publish(topic, json.dumps(response_data))
            return True
            
        except Exception as e:
            log('ERROR', f'Erro ao enviar resposta: {e}')
            return False
    
    def check_messages(self):
        """Verificar mensagens MQTT"""
        if self.connected and self.client:
            try:
                self.client.check_msg()
                return True
            except Exception as e:
                log('ERROR', f'Erro ao verificar mensagens: {e}')
                self.connected = False
                return False
        return False
    
    def disconnect(self):
        """Desconectar MQTT"""
        if self.client:
            try:
                if self.registered:
                    self.send_status("offline")
                self.client.disconnect()
            except:
                pass
        self.connected = False

# ==================== APLICAÇÃO PRINCIPAL ====================
class MagicMirrorApp:
    def __init__(self):
        # Inicializar componentes
        self.time_manager = TimeManager()
        self.display_manager = DisplayManager(self.time_manager)
        self.network_manager = NetworkManager(self.display_manager)
        self.mqtt_manager = MQTTManager(self.display_manager, self.time_manager)
        
        # Estado da aplicação
        self.running = True
        self.error_count = 0
        self.max_errors = 5
        
        # Watchdog (se habilitado)
        self.wdt = None
        if WATCHDOG_ENABLED:
            self.wdt = WDT(timeout=WATCHDOG_TIMEOUT * 1000)
        
        # Timers
        self.setup_timers()
    
    def setup_timers(self):
        """Configurar timers periódicos"""
        # Timer para heartbeat
        self.heartbeat_timer = Timer(-1)
        self.heartbeat_timer.init(
            period=HEARTBEAT_INTERVAL * 1000,
            mode=Timer.PERIODIC,
            callback=lambda t: self.send_heartbeat()
        )
        
        # Timer para sincronização NTP
        self.ntp_timer = Timer(-1)
        self.ntp_timer.init(
            period=NTP_SYNC_INTERVAL * 1000,
            mode=Timer.PERIODIC,
            callback=lambda t: self.sync_ntp()
        )
        
        # Timer para coleta de lixo
        if AUTO_GARBAGE_COLLECT:
            self.gc_timer = Timer(-1)
            self.gc_timer.init(
                period=GC_INTERVAL * 1000,
                mode=Timer.PERIODIC,
                callback=lambda t: self.garbage_collect()
            )
    
    def validate_configuration(self):
        """Validar configuração do dispositivo"""
        issues = validate_config()
        
        if issues:
            log('ERROR', 'Problemas de configuração encontrados:')
            for issue in issues:
                log('ERROR', f'  - {issue}')
            return False
        
        return True
    
    def send_heartbeat(self):
        """Enviar heartbeat via MQTT"""
        if self.mqtt_manager.connected and self.mqtt_manager.registered:
            self.mqtt_manager.send_heartbeat()
    
    def sync_ntp(self):
        """Sincronizar horário via NTP"""
        if self.network_manager.is_connected:
            self.time_manager.sync_ntp()
    
    def garbage_collect(self):
        """Executar coleta de lixo"""
        auto_garbage_collect()
        
        # Verificar limite de memória
        memory_info = get_memory_info()
        if memory_info['free'] < MEMORY_WARNING_THRESHOLD:
            log('WARN', f'Memória baixa: {memory_info["free"]} bytes')
    
    def run(self):
        """Loop principal da aplicação"""
        log('INFO', 'Iniciando Magic Mirror MQTT Only...')
        startup_banner()
        
        # Validar configuração
        if not self.validate_configuration():
            log('ERROR', 'Configuração inválida - parando execução')
            return
        
        # Conectar WiFi
        if not self.network_manager.connect_wifi():
            log('ERROR', 'Falha no WiFi - parando execução')
            return
        
        # Sincronizar horário
        if self.time_manager.sync_ntp():
            log('INFO', 'Horário sincronizado via NTP')
        else:
            log('WARN', 'Falha na sincronização NTP - usando horário do sistema')
        
        # Conectar MQTT
        if not self.mqtt_manager.connect():
            log('ERROR', 'Falha no MQTT - parando execução')
            return
        
        log('INFO', 'Sistema iniciado com sucesso!')
        
        # Loop principal
        last_connectivity_check = 0
        last_screen_update = 0
        last_status_update = 0
        last_registration_check = 0
        
        while self.running:
            try:
                current_time = utime.time()
                
                # Alimentar watchdog
                if self.wdt:
                    self.wdt.feed()
                
                # Verificar conectividade WiFi (a cada 30s)
                if current_time - last_connectivity_check >= 30:
                    if not self.network_manager.check_connection():
                        log('WARN', 'WiFi desconectado, tentando reconectar...')
                        if self.network_manager.connect_wifi():
                            # Reconectar MQTT após WiFi
                            self.mqtt_manager.connect()
                        else:
                            self.error_count += 1
                    
                    last_connectivity_check = current_time
                
                # Verificar mensagens MQTT
                if self.mqtt_manager.connected:
                    if not self.mqtt_manager.check_messages():
                        log('WARN', 'MQTT desconectado, tentando reconectar...')
                        self.mqtt_manager.connect()
                
                # Verificar/solicitar registro (se não registrado)
                if not self.mqtt_manager.registered and current_time - last_registration_check >= 30:
                    self.mqtt_manager.send_registration_request()
                    last_registration_check = current_time
                
                # Atualizar tela principal (a cada minuto)
                if current_time - last_screen_update >= 60:
                    if self.mqtt_manager.registered and self.mqtt_manager.current_events:
                        self.display_manager.show_main_screen(self.mqtt_manager.current_events)
                    elif self.mqtt_manager.registered:
                        self.display_manager.show_main_screen()
                    else:
                        # Mostrar tela de registro se não registrado
                        if self.mqtt_manager.connected:
                            self.display_manager.show_registration_screen("pending")
                        else:
                            self.display_manager.show_registration_screen("error")
                    
                    last_screen_update = current_time
                
                # Atualizar status de conexão na tela (a cada 10s)
                if current_time - last_status_update >= 10:
                    if self.mqtt_manager.registered:
                        last_sync = format_time(*self.time_manager.get_current_time()[3:5]) if self.mqtt_manager.last_message else None
                        self.display_manager.update_connection_status(self.mqtt_manager.connected, last_sync)
                    last_status_update = current_time
                
                # Verificar screen saver
                self.display_manager.check_screen_saver()
                
                # Verificar erros consecutivos
                if self.error_count >= self.max_errors:
                    log('ERROR', f'Muitos erros consecutivos ({self.error_count})')
                    self.display_manager.show_registration_screen("error")
                    utime.sleep(30)
                    
                    # Reiniciar sistema
                    self.cleanup()
                    reset_system()
                
                # Reset contador de erros se sistema estável
                if self.mqtt_manager.connected and (current_time - self.mqtt_manager.last_message < 3600):
                    self.error_count = 0
                
                # Aguardar antes da próxima iteração
                utime.sleep(1)
                
            except KeyboardInterrupt:
                log('INFO', 'Parando aplicação...')
                self.running = False
                break
                
            except Exception as e:
                self.error_count += 1
                log('ERROR', f'Erro no loop principal: {e}')
                self.display_manager.show_registration_screen("error")
                utime.sleep(5)
        
        # Limpeza final
        self.cleanup()
    
    def cleanup(self):
        """Limpeza antes de parar"""
        log('INFO', 'Fazendo limpeza...')
        
        # Parar timers
        try:
            self.heartbeat_timer.deinit()
            self.ntp_timer.deinit()
            if hasattr(self, 'gc_timer'):
                self.gc_timer.deinit()
        except:
            pass
        
        # Desconectar MQTT
        if self.mqtt_manager:
            self.mqtt_manager.disconnect()
        
        # Desconectar WiFi
        if self.network_manager.wlan:
            self.network_manager.wlan.disconnect()
            self.network_manager.wlan.active(False)
        
        # Apagar display
        if self.display_manager:
            self.display_manager.clear_screen()
            self.display_manager.set_brightness(0)

# ==================== FUNÇÕES UTILITÁRIAS ====================

def get_device_ip():
    """Obter IP do dispositivo"""
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            return wlan.ifconfig()[0]
    except:
        pass
    return "0.0.0.0"

def main():
    """Função principal"""
    try:
        # Aplicar configuração de ambiente se necessário
        # apply_environment_config('prod')  # dev, demo, prod
        
        # Verificar se está registrado
        if not is_registered():
            log('INFO', 'Dispositivo não registrado - iniciando processo de registro')
        else:
            log('INFO', f'Dispositivo registrado: {DEVICE_ID}')
        
        # Iniciar aplicação
        app = MagicMirrorApp()
        app.run()
        
    except Exception as e:
        log('ERROR', f'Erro crítico: {e}')
        # Tentar reiniciar em caso de erro crítico
        utime.sleep(10)
        reset_system()

# ==================== EXECUÇÃO ====================
if __name__ == "__main__":
    main()