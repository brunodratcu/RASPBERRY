import time
import ujson as json
import gc
import ubinascii
from time import localtime
from machine import Pin, SPI, UART, unique_id
import ili9486

# ======== CONFIGURAÇÕES RS-232 ========
# UART para comunicação RS-232
uart = UART(0, baudrate=9600, bits=8, parity=None, stop=1, tx=Pin(0), rx=Pin(1))

# ID único do dispositivo
DEVICE_ID = ubinascii.hexlify(unique_id()).decode()
CLIENT_ID = f"magic_mirror_pico_{DEVICE_ID}"

# ======== HARDWARE ILI9486 ========
# Display ILI9486 - SPI1
spi_display = SPI(1, baudrate=40000000, sck=Pin(10), mosi=Pin(11))
display = ili9486.Display(spi_display, dc=Pin(15), cs=Pin(13), rst=Pin(14))

# Botão gangorra (Liga/Desliga)
botao_gangorra = Pin(21, Pin.IN, Pin.PULL_UP)    # Único botão
led_status = Pin(25, Pin.OUT)                    # LED indicador

# ======== VARIÁVEIS GLOBAIS ========
eventos_hoje = []
system_on = True
uart_connected = False

# Controle do botão gangorra
last_switch_state = None
debounce_time = 0

# Controle de exclusão automática por horário
last_time_check = 0

# Buffer de comunicação RS-232
uart_buffer = ""

# Cores RGB565 para ILI9486
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
GRAY = 0x7BEF
RED_ELECTRIC = 0xF81F

# ======== COMUNICAÇÃO RS-232 ========
def verificar_uart():
    """Verifica se UART está funcionando"""
    global uart_connected
    
    try:
        # Testa envio de mensagem de ping
        enviar_rs232({"action": "ping", "device_id": CLIENT_ID})
        uart_connected = True
        return True
    except Exception as e:
        uart_connected = False
        return False

def enviar_rs232(payload):
    """Envia dados via RS-232"""
    try:
        message = json.dumps(payload) + "\n"
        uart.write(message.encode())
        return True
    except Exception as e:
        return False

def ler_rs232():
    """Lê dados do RS-232 de forma não-bloqueante"""
    global uart_buffer
    
    try:
        if uart.any():
            data = uart.read().decode('utf-8')
            uart_buffer += data
            
            # Processa mensagens completas (terminadas com \n)
            while '\n' in uart_buffer:
                line, uart_buffer = uart_buffer.split('\n', 1)
                if line.strip():
                    processar_mensagem_rs232(line.strip())
                    
    except Exception as e:
        pass

def processar_mensagem_rs232(message):
    """Processa mensagens recebidas via RS-232"""
    global eventos_hoje
    
    try:
        payload = json.loads(message)
        action = payload.get("action", "")
        
        if action == "add_event":
            processar_adicionar_evento(payload)
        elif action == "remove_event":
            processar_remover_evento(payload)
        elif action == "sync_events":
            processar_sincronizacao(payload)
        elif action == "clear_events":
            eventos_hoje.clear()
            atualizar_tela()
        elif action == "ping_response":
            # Backend respondeu ao ping
            uart_connected = True
        elif action == "get_status":
            enviar_status_rs232()
        elif action == "system_command":
            processar_comando_sistema(payload)
            
        # Atualiza tela se sistema ligado
        if system_on:
            atualizar_tela()
            
    except Exception as e:
        pass

def processar_adicionar_evento(payload):
    """Processa evento adicionado via RS-232"""
    global eventos_hoje
    
    try:
        event_data = payload.get("event", {})
        evento = {
            "id": event_data.get("id"),
            "nome": event_data.get("nome", ""),
            "hora": event_data.get("hora", ""),
            "data": event_data.get("data", "")
        }
        
        # Remove duplicata se existir
        eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento["id"]]
        eventos_hoje.append(evento)
        
        # Ordena por hora
        eventos_hoje.sort(key=lambda x: x.get("hora", ""))
        
        # Confirma recebimento
        enviar_confirmacao_rs232(event_data.get("id"), "received")
        
    except Exception as e:
        pass

def processar_remover_evento(payload):
    """Processa evento removido via RS-232"""
    global eventos_hoje
    
    try:
        evento_id = payload.get("event_id")
        eventos_hoje = [e for e in eventos_hoje if e.get("id") != evento_id]
        
        # Confirma remoção
        enviar_confirmacao_rs232(evento_id, "removed")
        
    except Exception as e:
        pass

def processar_sincronizacao(payload):
    """Processa sincronização completa via RS-232"""
    global eventos_hoje
    
    try:
        # Substitui lista completa
        new_events = payload.get("events", [])
        eventos_hoje = []
        
        for event_data in new_events:
            evento = {
                "id": event_data.get("id"),
                "nome": event_data.get("nome", ""),
                "hora": event_data.get("hora", ""),
                "data": event_data.get("data", "")
            }
            eventos_hoje.append(evento)
        
        # Ordena por hora
        eventos_hoje.sort(key=lambda x: x.get("hora", ""))
        
        # Confirma sincronização
        enviar_rs232({
            "action": "sync_complete",
            "device_id": CLIENT_ID,
            "events_count": len(eventos_hoje),
            "timestamp": time.time()
        })
        
    except Exception as e:
        pass

def processar_comando_sistema(payload):
    """Processa comandos do sistema via RS-232"""
    global system_on
    
    try:
        command = payload.get("command", "")
        
        if command == "power_on" and not system_on:
            ligar_sistema()
        elif command == "power_off" and system_on:
            desligar_sistema()
        elif command == "restart":
            # Reinicia o sistema
            machine.reset()
        elif command == "get_info":
            enviar_info_dispositivo()
            
    except Exception as e:
        pass

def enviar_confirmacao_rs232(evento_id, action):
    """Envia confirmação de ação via RS-232"""
    payload = {
        "action": "event_ack",
        "device_id": CLIENT_ID,
        "event_id": evento_id,
        "ack_action": action,
        "timestamp": time.time()
    }
    enviar_rs232(payload)

def enviar_status_rs232():
    """Envia status do dispositivo via RS-232"""
    payload = {
        "action": "device_status",
        "device_id": CLIENT_ID,
        "status": "online" if system_on else "sleep",
        "events_count": len(eventos_hoje),
        "free_memory": gc.mem_free(),
        "display_type": "ili9486_3.5",
        "timestamp": time.time()
    }
    enviar_rs232(payload)

def enviar_info_dispositivo():
    """Envia informações completas do dispositivo"""
    payload = {
        "action": "device_info",
        "device_id": CLIENT_ID,
        "name": f"Magic Mirror {DEVICE_ID[-6:]}",
        "firmware_version": "2.0.0-RS232",
        "display_type": "ili9486_3.5",
        "display_resolution": "480x320",
        "capabilities": {
            "has_display": True,
            "has_buttons": 3,
            "auto_remove_events": True,
            "communication": "rs232"
        },
        "system_status": "online" if system_on else "sleep",
        "events_count": len(eventos_hoje),
        "uptime": time.ticks_ms(),
        "free_memory": gc.mem_free(),
        "timestamp": time.time()
    }
    enviar_rs232(payload)

# ======== EXCLUSÃO AUTOMÁTICA POR HORÁRIO ========
def verificar_eventos_vencidos():
    """Verifica e remove eventos que já passaram do horário"""
    global eventos_hoje, last_time_check
    
    current_time = time.ticks_ms()
    
    # Verifica apenas a cada 30 segundos
    if current_time - last_time_check < 30000:
        return False
    
    last_time_check = current_time
    
    # Pega hora atual
    agora = localtime()
    hora_atual = "{:02d}:{:02d}".format(agora[3], agora[4])
    
    eventos_removidos = 0
    eventos_restantes = []
    
    for evento in eventos_hoje:
        hora_evento = evento.get("hora", "")
        
        # Se o evento já passou
        if hora_evento and hora_evento < hora_atual:
            # Notifica backend da remoção automática
            enviar_evento_concluido_rs232(evento.get("id"), "expired")
            eventos_removidos += 1
            piscar_led(1)
        else:
            eventos_restantes.append(evento)
    
    # Atualiza lista se houve mudanças
    if eventos_removidos > 0:
        eventos_hoje = eventos_restantes
        return True
    
    return False

def enviar_evento_concluido_rs232(evento_id, reason="manual"):
    """Notifica backend que evento foi concluído"""
    payload = {
        "action": "event_completed",
        "device_id": CLIENT_ID,
        "event_id": evento_id,
        "completion_reason": reason,  # "manual", "expired"
        "timestamp": time.time()
    }
    enviar_rs232(payload)

# ======== CONTROLE DO BOTÃO GANGORRA ========
def verificar_botao_gangorra():
    """Verifica estado do botão gangorra (Liga/Desliga)"""
    global system_on, show_welcome, last_switch_state, debounce_time, welcome_start_time
    
    current_time = time.ticks_ms()
    current_state = botao_gangorra.value()
    
    # Debounce: ignora mudanças muito rápidas
    if current_time - debounce_time < 300:
        return
    
    # Verifica mudança de estado
    if current_state != last_switch_state:
        debounce_time = current_time
        last_switch_state = current_state
        
        if current_state == 0:  # Botão pressionado (ON)
            if not system_on:
                # Liga sistema com tela de boas-vindas
                system_on = True
                show_welcome = True
                welcome_start_time = current_time
                mostrar_tela_bem_vindo()
                piscar_led(2)  # LED confirma ligada
                enviar_status_rs232()  # Notifica backend
                
        else:  # Botão solto (OFF)
            if system_on:
                # Desliga sistema imediatamente
                desligar_sistema()

def mostrar_tela_bem_vindo():
    """Mostra tela de boas-vindas por 2 segundos"""
    display.fill(BLACK)
    
    # "BEM-VINDO" grande e centralizado ocupando toda linha horizontal
    # Usar fonte 16x32 para texto grande
    texto = "BEM-VINDO"
    
    # Centralizar horizontalmente (480 pixels / 2 - largura_texto / 2)
    # Cada caractere 16x32 tem ~14px de largura efetiva
    largura_texto = len(texto) * 14
    x_pos = (480 - largura_texto) // 2
    
    # Centralizar verticalmente (320 pixels / 2 - altura / 2)
    y_pos = (320 - 32) // 2
    
    display.draw_text16x32(x_pos, y_pos, texto, WHITE)
    
    print("🎉 Tela BEM-VINDO exibida")

def verificar_tempo_bem_vindo():
    """Verifica se deve sair da tela de boas-vindas"""
    global show_welcome, welcome_start_time
    
    if show_welcome:
        current_time = time.ticks_ms()
        if current_time - welcome_start_time >= 2000:  # 2 segundos
            show_welcome = False
            atualizar_tela()  # Vai para tela principal
            print("⏰ Saindo da tela BEM-VINDO para agenda")

def ligar_sistema():
    """Chamada quando sistema está sendo ligado (não usar diretamente)"""
    # Esta função agora é chamada indiretamente via botão
    # A lógica principal está em verificar_botao_gangorra()
    pass

def desligar_sistema():
    global system_on, show_welcome
    
    print("🔴 Desligando sistema...")
    
    # Desliga imediatamente
    system_on = False
    show_welcome = False  # Cancela boas-vindas se ativa
    
    # Tela preta
    display.fill(BLACK)
    
    # LED apagado
    led_status.value(0)
    
    # Notifica backend
    enviar_status_rs232()
    
    print("💤 Sistema desligado - tela preta")

def concluir_primeiro_evento():
    global eventos_hoje
    
    if eventos_hoje:
        evento = eventos_hoje[0]
        evento_id = evento.get("id")
        
        # Remove da lista local
        eventos_hoje.pop(0)
        
        # Notifica backend
        enviar_evento_concluido_rs232(evento_id, "manual")
        
        # Atualiza tela
        atualizar_tela()
        
        # LED confirmação
        piscar_led(3)

def piscar_led(vezes=3):
    for _ in range(vezes):
        led_status.value(1)
        time.sleep_ms(100)
        led_status.value(0)
        time.sleep_ms(100)

# ======== INTERFACE VISUAL ILI9486 ========
def atualizar_tela():
    """Atualiza interface baseada no estado atual"""
    
    # Se sistema desligado: tela preta
    if not system_on:
        display.fill(BLACK)
        led_status.value(0)  # LED apagado
        return
    
    # Se em modo boas-vindas: não atualizar (já está mostrando)
    if show_welcome:
        led_status.value(1)  # LED aceso
        return
    
    # Modo normal: mostra agenda
    led_status.value(1)  # LED aceso
    
    # Limpa tela
    display.fill(BLACK)
    
    # Data e hora no topo
    desenhar_data_hora()
    
    # Linha separadora
    display.draw_hline(20, 90, 440, WHITE)
    
    # Lista de eventos
    desenhar_eventos()
    
    # Instruções na parte inferior
    desenhar_instrucoes()
    
    # Status de conexão
    desenhar_status_conexao()

def desenhar_data_hora():
    # Pega hora atual
    agora = localtime()
    hora_str = "{:02d}:{:02d}:{:02d}".format(agora[3], agora[4], agora[5])
    data_str = "{:02d}/{:02d}/{:04d}".format(agora[2], agora[1], agora[0])
    
    # Título "Minha agenda"
    display.draw_text16x32(140, 10, "Minha agenda", WHITE)
    
    # Hora grande e centralizada
    display.draw_text16x32(160, 45, hora_str, WHITE)
    
    # Data menor abaixo
    display.draw_text8x8(200, 75, data_str, GRAY)

def desenhar_eventos():
    y_pos = 110
    
    if eventos_hoje:
        # Título da seção
        display.draw_text8x8(20, y_pos, "EVENTOS DE HOJE:", WHITE)
        y_pos += 25
        
        # Lista eventos (máximo 9 visíveis - mais espaço sem botões)
        for i, evento in enumerate(eventos_hoje[:9]):
            if y_pos > 260:
                display.draw_text8x8(20, y_pos, "... mais eventos", GRAY)
                break
            
            # Todos os eventos com mesmo destaque (sem botão CONCLUIR)
            cor_texto = WHITE
            evento_texto = f"{evento.get('hora', '--:--')} - {evento.get('nome', 'Sem nome')}"
            
            # Trunca texto se muito longo
            if len(evento_texto) > 50:
                evento_texto = evento_texto[:47] + "..."
            
            display.draw_text8x8(30, y_pos, evento_texto, cor_texto)
            y_pos += 16  # Espaçamento menor para mais eventos
            
    else:
        display.draw_text8x8(20, y_pos, "NENHUM EVENTO HOJE", GRAY)
        y_pos += 20
        display.draw_text8x8(20, y_pos, "Aguardando sincronização...", GRAY)

def desenhar_instrucoes():
    # Instruções de uso na parte inferior
    y_base = 270
    
    display.draw_text8x8(20, y_base, "CONTROLES:", WHITE)
    display.draw_text8x8(20, y_base + 15, "Botao Gangorra: Liga/Desliga sistema", GREEN)
    display.draw_text8x8(20, y_base + 30, "Eventos removidos automaticamente por horario", BLUE)

def desenhar_status_conexao():
    # Apenas contador de eventos no canto inferior esquerdo
    y_status = 305
    
    # Status RS-232
    if uart_connected:
        display.draw_text8x8(20, y_status, f"Eventos: {len(eventos_hoje)} | RS232: OK", BLUE)
    else:
        display.draw_text8x8(20, y_status, f"Eventos: {len(eventos_hoje)} | RS232: OFF", RED)

# ======== LOOP PRINCIPAL ========
def main():
    global system_on, show_welcome
    
    # Tela de inicialização
    display.fill(BLACK)
    display.draw_text16x32(140, 80, "Minha agenda", WHITE)
    display.draw_text8x8(180, 120, "ILI9486 3.5\" - RS232", YELLOW)
    display.draw_text8x8(160, 140, f"ID: {DEVICE_ID[-8:]}", GRAY)
    display.draw_text8x8(170, 170, "Iniciando...", WHITE)
    
    time.sleep(2)
    
    # Testa comunicação RS-232
    display.draw_text8x8(170, 190, "RS232...", YELLOW)
    if verificar_uart():
        display.draw_text8x8(230, 190, "OK", GREEN)
        # Envia informações do dispositivo
        enviar_info_dispositivo()
    else:
        display.draw_text8x8(230, 190, "OFF", RED)
    
    time.sleep(2)
    
    # Sistema pronto
    display.draw_text8x8(160, 220, "Sistema Pronto!", GREEN)
    display.draw_text8x8(130, 240, "Modo Offline - RS232", BLUE)
    display.draw_text8x8(120, 260, "Botao gangorra: Liga/Desliga", GRAY)
    
    # LED indicação de pronto
    piscar_led(5)
    
    time.sleep(2)
    
    # Sistema inicia DESLIGADO (tela preta)
    system_on = False
    show_welcome = False
    display.fill(BLACK)
    led_status.value(0)
    
    print("💤 Sistema pronto - DESLIGADO (tela preta)")
    print("🔘 Pressione botão gangorra para ligar")
    
    # Loop principal
    last_update = 0
    last_heartbeat = 0
    
    while True:
        try:
            current_time = time.ticks_ms()
            
            # Lê comunicação RS-232
            ler_rs232()
            
            # Verifica botão gangorra sempre (mesmo sistema desligado)
            verificar_botao_gangorra()
            
            # Verifica tempo de boas-vindas
            if show_welcome:
                verificar_tempo_bem_vindo()
            
            # Processa apenas se sistema ligado e não em boas-vindas
            if system_on and not show_welcome:
                
                # Verifica eventos vencidos
                eventos_alterados = verificar_eventos_vencidos()
                
                # Atualiza tela se houve alteração ou a cada 5 segundos
                if eventos_alterados or (current_time - last_update > 5000):
                    atualizar_tela()
                    last_update = current_time
            
            # Heartbeat a cada 60 segundos (sempre, mesmo desligado)
            if current_time - last_heartbeat > 60000:
                enviar_status_rs232()
                last_heartbeat = current_time
            
            # Limpeza de memória a cada 2 minutos
            if current_time % 120000 < 100:
                gc.collect()
            
            time.sleep_ms(50)  # Loop mais rápido para responsividade
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            time.sleep(1)

# Executar programa principal
if __name__ == "__main__":
    main()