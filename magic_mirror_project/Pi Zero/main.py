"""
# ===== CONFIG =====
SSID = "SEU_SSID"
PASSWORD = "SUA_SENHA"
SERVER_IP = "192.168.0.100"   # IP do seu servidor Flask
SERVER_URL = "http://{}:5000".format(SERVER_IP)
TOKEN = "COLE_AQUI_O_TOKEN"  # gerado por generate_pico_token.py
POLL_INTERVAL = 15  # segundos
"""
#=========================================================
"""
# ===== Função de desenho =====
def draw(events):
    tft.fill(0x0000)  # preto
    tt = utime.localtime()
    time_str = "{:02d}:{:02d}:{:02d}".format(tt[3], tt[4], tt[5])
    date_str = "{:02d}/{:02d}/{:04d}".format(tt[2], tt[1], tt[0])

    tft.text(font, "Hora: " + time_str, 10, 10, ili9XXX.color565(0, 255, 255), 0x0000)
    tft.text(font, "Data: " + date_str, 10, 30, ili9XXX.color565(0, 255, 255), 0x0000)

    y = 60
    tft.text(font, "Eventos de Hoje:", 10, y, ili9XXX.color565(255, 255, 0), 0x0000)
    y += 20
    if not events:
        tft.text(font, "- nenhum -", 10, y, ili9XXX.color565(255, 0, 0), 0x0000)
    else:
        for ev in events:
            linha = "{} {}".format(ev.get("hora", ""), ev.get("nome", ""))
            tft.text(font, linha[:40], 10, y, ili9XXX.color565(255, 255, 255), 0x0000)
            y += 18
            if y > 300:
                break
"""
# main.py - Pico W + ILI9341/ILI9488 + Sistema de Eventos Sincronizado
import network, utime, ntptime
import urequests as requests
from machine import Pin, SPI
import ili9488  # ou ili9488 dependendo do seu display
import vga1_8x16 as font
import json
import gc
import _thread
# import glcdfont

# ===== CONFIGURAÇÕES =====
SSID = "SEU_SSID"                    # Substitua pelo nome da sua rede
PASSWORD = "SUA_SENHA"               # Substitua pela senha da sua rede
DEVICE_NAME = "Pico-Eventos-001"     # Nome único para este dispositivo
SERVER_CHECK_INTERVAL = 30           # Verifica servidor a cada 30 segundos
DISPLAY_UPDATE_INTERVAL = 60         # Atualiza display a cada 60 segundos

# ===== CONFIGURAÇÕES DO DISPLAY ILI9341 =====
# Ajuste os pinos conforme sua conexão
SCK_PIN = 10   # SCL
MOSI_PIN = 11  # SDA/MOSI  
CS_PIN = 9     # CS
DC_PIN = 8     # DC
RST_PIN = 12   # RST

# ===== VARIÁVEIS GLOBAIS =====
eventos_hoje = []
wlan = None
tft = None
servidor_online = False
ultima_sincronizacao = None
# server_socket = None

# ===== CONFIGURAÇÃO DO DISPLAY =====
def configurar_display():
    """Configura e inicializa o display TFT"""
    global tft
    
    try:
        # Configuração SPI
        spi = SPI(1, baudrate=40000000, sck=Pin(SCK_PIN), mosi=Pin(MOSI_PIN))
        
        # Inicializa o display ILI9341 (320x240)
        tft = ili9984.ILI9984(
            spi,
            cs=Pin(CS_PIN, Pin.OUT),
            dc=Pin(DC_PIN, Pin.OUT),
            rst=Pin(RST_PIN, Pin.OUT),
            width=320,
            height=240,
            rotation=1  # Orientação paisagem
        )
        
        # Limpa a tela
        tft.fill(ili9984.BLACK)
        
        # Testa o display
        tft.text(font, "Inicializando...", 10, 10, ili9984.WHITE, ili9984.BLACK)
        tft.show()
        
        print("✅ Display TFT configurado com sucesso")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao configurar display: {e}")
        return False

# ===== FUNÇÕES DE DISPLAY =====
def mostrar_tela_inicializacao():
    """Mostra tela de inicialização"""
    if not tft:
        return
        
    tft.fill(ili9984.BLACK)
    
    # Título
    tft.text(font, "SISTEMA DE EVENTOS", 60, 40, ili9984.CYAN, ili9984.BLACK)
    tft.text(font, DEVICE_NAME, 80, 70, ili9984.YELLOW, ili9984.BLACK)
    
    # Status
    tft.text(font, "Conectando WiFi...", 70, 120, ili9984.WHITE, ili9984.BLACK)
    
    # Info do dispositivo
    tft.text(font, "Pico W", 10, 200, ili9984.GRAY, ili9984.BLACK)
    tft.text(font, f"RAM: {gc.mem_free()}b", 200, 200, ili9984.GRAY, ili9984.BLACK)

def mostrar_tela_erro_wifi():
    """Mostra tela de erro de WiFi"""
    if not tft:
        return
        
    tft.fill(ili9984.BLACK)
    tft.text(font, "ERRO DE CONEXAO", 80, 80, ili9984.RED, ili9984.BLACK)
    tft.text(font, "Verifique o WiFi", 70, 110, ili9984.YELLOW, ili9841.BLACK)
    tft.text(font, "Tentando novamente...", 50, 140, ili9984.WHITE, ili9984.BLACK)
    tft.show()

def mostrar_eventos():
    """Mostra os eventos na tela TFT"""
    global eventos_hoje, tft, servidor_online, ultima_sincronizacao
    
    if not tft:
        return
        
    tft.fill(ili9984.BLACK)
    
    # ===== CABEÇALHO =====
    # Data e hora atual
    try:
        agora = utime.localtime()
        data_str = f"{agora[2]:02d}/{agora[1]:02d}/{agora[0]}"
        hora_str = f"{agora[3]:02d}:{agora[4]:02d}:{agora[5]:02d}"
    except:
        data_str = "00/00/0000"
        hora_str = "00:00:00"
    
    # Linha do cabeçalho
    tft.hline(0, 30, 320, ili9984.WHITE)
    
    # Título e data/hora
    tft.text(font, "EVENTOS DE HOJE", 80, 5, ili9984.CYAN, ili9984.BLACK)
    tft.text(font, data_str, 10, 15, ili9984.YELLOW, ili9984.BLACK)
    tft.text(font, hora_str, 220, 15, ili9984.YELLOW, ili9984.BLACK)
    
    # ===== ÁREA DE EVENTOS =====
    y_pos = 45
    max_eventos = 9  # Máximo de eventos que cabem na tela
    
    if not eventos_hoje:
        # Nenhum evento
        tft.text(font, "Nenhum evento hoje", 70, 100, ili9984.WHITE, ili9984.BLACK)
        if servidor_online:
            tft.text(font, "Aguardando novos eventos...", 40, 130, ili9984.GRAY, ili9984.BLACK)
        else:
            tft.text(font, "Servidor offline", 80, 130, ili9984.RED, ili9984.BLACK)
    else:
        # Lista de eventos
        for i, evento in enumerate(eventos_hoje[:max_eventos]):
            if y_pos > 200:  # Limite da tela
                break
                
            # Cor alternada para melhor leitura
            cor_hora = ili9984.YELLOW
            cor_nome = ili9984.WHITE if i % 2 == 0 else ili9984.CYAN
            
            # Hora do evento (primeiros 5 caracteres)
            hora_evento = evento.get('hora', '00:00')[:5]
            tft.text(font, hora_evento, 10, y_pos, cor_hora, ili9984.BLACK)
            
            # Nome do evento (truncado se muito longo)
            nome = evento.get('nome', 'Evento')
            if len(nome) > 28:  # Ajusta conforme a largura do display
                nome = nome[:25] + "..."
                
            tft.text(font, nome, 70, y_pos, cor_nome, ili9984.BLACK)
            
            y_pos += 18
        
        # Indicador se há mais eventos
        if len(eventos_hoje) > max_eventos:
            tft.text(font, f"+ {len(eventos_hoje) - max_eventos} mais", 180, 200, ili9984.GRAY, ili9984.BLACK)
    
    # ===== BARRA DE STATUS =====
    # Linha separadora
    tft.hline(0, 215, 320, ili9984.WHITE)

    # Status de conexão
    if servidor_online:
        tft.text(font, "● ONLINE", 250, 225, ili9984.GREEN, ili9984.BLACK)
    else:
        tft.text(font, "● OFFLINE", 240, 225, ili9984.RED, ili9984.BLACK)
    
    # Contador de eventos
    tft.text(font, f"Eventos: {len(eventos_hoje)}", 10, 225, ili9984.GRAY, ili9984.BLACK)

    # Última sincronização
    if ultima_sincronizacao:
        sync_str = f"Sync: {ultima_sincronizacao[3]:02d}:{ultima_sincronizacao[4]:02d}"
        tft.text(font, sync_str, 120, 225, ili9984.GRAY, ili9984.BLACK)

    print(f"🖥️ Display atualizado: {len(eventos_hoje)} eventos mostrados")

# ===== CONEXÃO WIFI =====
def conectar_wifi():
    """Conecta à rede WiFi"""
    global wlan
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"✅ WiFi já conectado. IP: {ip}")
        return ip
    
    print(f"🔗 Conectando ao WiFi: {SSID}")
    mostrar_tela_inicializacao()
    
    wlan.connect(SSID, PASSWORD)
    
    # Aguarda conexão (timeout 20 segundos)
    timeout = 20
    while timeout > 0:
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"✅ WiFi conectado! IP: {ip}")
            
            # Sincroniza horário via NTP
            try:
                ntptime.settime()
                print("🕐 Horário sincronizado via NTP")
            except:
                print("⚠️ Falha ao sincronizar horário NTP")
            
            return ip
        
        utime.sleep(1)
        timeout -= 1
    
    print("❌ Falha ao conectar WiFi")
    mostrar_tela_erro_wifi()
    return None

# ===== SERVIDOR HTTP INTERNO =====
def criar_servidor_http():
    """Cria servidor HTTP para receber comandos do backend"""
    import socket
    
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(3)
        
        print("🌐 Servidor HTTP iniciado na porta 80")
        
        while True:
            try:
                conn, addr = server_socket.accept()
                request_data = conn.recv(1024)
                
                if request_data:
                    response = processar_requisicao_http(request_data.decode('utf-8'))
                    conn.send(response.encode('utf-8'))
                
                conn.close()
                
            except Exception as e:
                print(f"❌ Erro na conexão HTTP: {e}")
                try:
                    conn.close()
                except:
                    pass
            
            utime.sleep(0.1)  # Pequena pausa
            
    except Exception as e:
        print(f"❌ Erro no servidor HTTP: {e}")

def processar_requisicao_http(request_str):
    """Processa requisições HTTP recebidas"""
    global eventos_hoje, ultima_sincronizacao
    
    try:
        lines = request_str.split('\n')
        if not lines:
            return criar_resposta_http({"erro": "Requisição inválida"}, 400)
        
        primeira_linha = lines[0].strip()
        partes = primeira_linha.split(' ')
        
        if len(partes) < 2:
            return criar_resposta_http({"erro": "Formato inválido"}, 400)
            
        metodo = partes[0]
        path = partes[1]
        
        print(f"📨 {metodo} {path}")
        
        # Identificação do dispositivo
        if path == "/api/pico-id" and metodo == "GET":
            return criar_resposta_http({
                "device_type": "pico",
                "name": DEVICE_NAME,
                "version": "1.0",
                "display": "ILI9341",
                "eventos_carregados": len(eventos_hoje)
            })
        
        # Status do dispositivo
        elif path == "/api/status" and metodo == "GET":
            return criar_resposta_http({
                "status": "online",
                "eventos": len(eventos_hoje),
                "memoria_livre": gc.mem_free(),
                "wifi_conectado": wlan.isconnected() if wlan else False,
                "uptime": utime.ticks_ms()
            })
        
        # Receber evento individual
        elif path == "/api/evento" and metodo == "POST":
            # Encontra o JSON no corpo da requisição
            body_start = request_str.find('\r\n\r\n')
            if body_start == -1:
                body_start = request_str.find('\n\n')
            
            if body_start != -1:
                json_data = request_str[body_start:].strip()
                try:
                    data = json.loads(json_data)
                    return processar_comando_evento(data)
                except Exception as e:
                    return criar_resposta_http({"erro": f"JSON inválido: {e}"}, 400)
            else:
                return criar_resposta_http({"erro": "Corpo não encontrado"}, 400)
        
        # Limpar todos os eventos
        elif path == "/api/limpar" and metodo == "POST":
            eventos_hoje.clear()
            print("🗑️ Todos os eventos foram limpos")
            return criar_resposta_http({"mensagem": "Eventos limpos"})
        
        # Atualizar display
        elif path == "/api/atualizar" and metodo == "POST":
            mostrar_eventos()
            return criar_resposta_http({"mensagem": "Display atualizado"})
        
        else:
            return criar_resposta_http({"erro": "Endpoint não encontrado"}, 404)
            
    except Exception as e:
        print(f"❌ Erro ao processar requisição: {e}")
        return criar_resposta_http({"erro": f"Erro interno: {e}"}, 500)

def processar_comando_evento(data):
    """Processa comandos de eventos"""
    global eventos_hoje, ultima_sincronizacao
    
    try:
        acao = data.get('acao', 'adicionar')
        evento_id = data.get('id')
        
        if acao == 'adicionar':
            # Remove evento existente com mesmo ID (se houver)
            eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
            
            # Adiciona novo evento
            evento = {
                'id': evento_id,
                'nome': data.get('nome', 'Evento sem nome'),
                'hora': data.get('hora', '00:00'),
                'data': data.get('data')
            }
            
            eventos_hoje.append(evento)
            
            # Ordena eventos por hora
            eventos_hoje.sort(key=lambda x: x.get('hora', '00:00'))
            
            print(f"✅ Evento adicionado: {evento['nome']} às {evento['hora']}")
            ultima_sincronizacao = utime.localtime()
            
            return criar_resposta_http({
                "mensagem": f"Evento {evento_id} adicionado",
                "total_eventos": len(eventos_hoje)
            })
            
        elif acao == 'deletar':
            # Remove evento pelo ID
            eventos_anteriores = len(eventos_hoje)
            eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
            
            if len(eventos_hoje) < eventos_anteriores:
                print(f"🗑️ Evento {evento_id} removido")
                ultima_sincronizacao = utime.localtime()
                return criar_resposta_http({
                    "mensagem": f"Evento {evento_id} removido",
                    "total_eventos": len(eventos_hoje)
                })
            else:
                return criar_resposta_http({"erro": "Evento não encontrado"}, 404)
        
        else:
            return criar_resposta_http({"erro": "Ação não reconhecida"}, 400)
            
    except Exception as e:
        return criar_resposta_http({"erro": f"Erro ao processar evento: {e}"}, 500)

def criar_resposta_http(data, codigo=200):
    """Cria resposta HTTP com JSON"""
    json_str = json.dumps(data)
    
    status_text = "OK" if codigo == 200 else "Error"
    response = f"HTTP/1.1 {codigo} {status_text}\r\n"
    response += "Content-Type: application/json\r\n"
    response += "Access-Control-Allow-Origin: *\r\n"
    response += f"Content-Length: {len(json_str)}\r\n"
    response += "Connection: close\r\n\r\n"
    response += json_str
    
    return response

# ===== THREAD DE ATUALIZAÇÃO =====
def thread_atualizacao_display():
    """Thread que atualiza o display periodicamente"""
    while True:
        try:
            # Verifica conexão WiFi
            if wlan and not wlan.isconnected():
                mostrar_tela_erro_wifi()
                # Tenta reconectar
                ip = conectar_wifi()
                if ip:
                    mostrar_eventos()
            else:
                # Atualiza display normal
                mostrar_eventos()
            
            # Coleta de lixo para liberar memória
            gc.collect()
            
            # Aguarda próxima atualização
            utime.sleep(DISPLAY_UPDATE_INTERVAL)
            
        except Exception as e:
            print(f"❌ Erro na thread de atualização: {e}")
            utime.sleep(30)

# ===== FUNÇÃO PRINCIPAL =====
def main():
    """Função principal do sistema"""
    print("🚀 Iniciando sistema de eventos Pico W...")
    print(f"📱 Dispositivo: {DEVICE_NAME}")
    
    # Configura display
    if not configurar_display():
        print("❌ Falha ao configurar display - sistema não pode continuar")
        return
    
    # Conecta WiFi
    ip = conectar_wifi()
    if not ip:
        print("❌ Falha ao conectar WiFi - modo offline")
        mostrar_tela_erro_wifi()
        return
    
    print(f"🌐 Sistema online no IP: {ip}")
    
    # Mostra tela inicial
    mostrar_eventos()
    
    # Inicia thread de atualização do display
    _thread.start_new_thread(thread_atualizacao_display, ())
    
    # Inicia servidor HTTP (blocking)
    print("🎯 Pronto para receber eventos!")
    criar_servidor_http()

# ===== EXECUÇÃO =====
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Sistema interrompido pelo usuário")
    except Exception as e:
        print(f"💥 Erro crítico: {e}")
        if tft:
            tft.fill(ili9984.BLACK)
            tft.text(font, "ERRO CRITICO", 100, 100, ili9984.RED, ili9984.BLACK)
            tft.text(font, str(e)[:30], 10, 130, ili9984.WHITE, ili9984.BLACK)
