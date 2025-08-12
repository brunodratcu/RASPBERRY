# main.py - Pico W + ILI9341/ILI9488 + Sistema de Eventos Sincronizado
import network, utime, ntptime
import urequests as requests
from machine import Pin, SPI
import ili9341  # Use ili9341, ili9488 ou ili9984 dependendo do seu display
import vga1_8x16 as font
import json
import gc
import _thread
import math

# ===== CONFIGURAÇÕES =====
SSID = "SEU_SSID"                    # Substitua pelo nome da sua rede
PASSWORD = "SUA_SENHA"               # Substitua pela senha da sua rede
DEVICE_NAME = "Pico-Eventos-001"     # Nome único para este dispositivo
DISPLAY_UPDATE_INTERVAL = 60         # Atualiza display a cada 60 segundos
MEMORY_CLEANUP_INTERVAL = 300        # Limpeza de memória a cada 5 minutos
MAX_EVENTS_DISPLAY = 8               # Máximo de eventos mostrados na tela

# ===== CONFIGURAÇÕES DO DISPLAY =====
# Para ILI9341 (320x240)
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
DISPLAY_ROTATION = 1  # 0=portrait, 1=landscape

# Pinos SPI - ajuste conforme sua conexão
SCK_PIN = 10   # SCL/Clock
MOSI_PIN = 11  # SDA/MOSI/Data  
CS_PIN = 9     # Chip Select
DC_PIN = 8     # Data/Command
RST_PIN = 12   # Reset

# ===== VARIÁVEIS GLOBAIS =====
eventos_hoje = []
wlan = None
tft = None
sistema_ativo = True
ultima_atualizacao = None
contador_atualizacoes = 0
memoria_inicial = 0

# ===== CONFIGURAÇÃO DO DISPLAY =====
def configurar_display():
    """Configura e inicializa o display TFT"""
    global tft, memoria_inicial
    
    try:
        print("🖥️ Configurando display TFT...")
        
        # Configuração SPI otimizada
        spi = SPI(1, 
                  baudrate=40000000, 
                  sck=Pin(SCK_PIN), 
                  mosi=Pin(MOSI_PIN))
        
        # Inicializa o display - ajuste a classe conforme seu display
        tft = ili9341.ILI9341(
            spi,
            cs=Pin(CS_PIN, Pin.OUT),
            dc=Pin(DC_PIN, Pin.OUT),
            rst=Pin(RST_PIN, Pin.OUT),
            width=DISPLAY_WIDTH,
            height=DISPLAY_HEIGHT,
            rotation=DISPLAY_ROTATION
        )
        
        # Teste inicial do display
        tft.fill(ili9341.BLACK)
        tft.text(font, "Iniciando sistema...", 10, 10, ili9341.WHITE, ili9341.BLACK)
        
        # Verifica se o display responde
        try:
            tft.pixel(0, 0, ili9341.WHITE)
            tft.pixel(0, 0, ili9341.BLACK)
        except:
            raise Exception("Display não responde")
        
        memoria_inicial = gc.mem_free()
        print(f"✅ Display TFT configurado - Resolução: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
        print(f"💾 Memória disponível: {memoria_inicial} bytes")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao configurar display: {e}")
        return False

# ===== FUNÇÕES DE DISPLAY =====
def limpar_tela():
    """Limpa a tela completamente"""
    if tft:
        tft.fill(ili9341.BLACK)

def desenhar_header():
    """Desenha cabeçalho com informações do sistema"""
    if not tft:
        return
        
    try:
        # Obter data/hora atual
        agora = utime.localtime()
        data_str = f"{agora[2]:02d}/{agora[1]:02d}/{agora[0]}"
        hora_str = f"{agora[3]:02d}:{agora[4]:02d}:{agora[5]:02d}"
        
        # Título principal
        tft.text(font, "EVENTOS DE HOJE", 80, 5, ili9341.CYAN, ili9341.BLACK)
        
        # Data e hora
        tft.text(font, data_str, 10, 20, ili9341.YELLOW, ili9341.BLACK)
        tft.text(font, hora_str, 220, 20, ili9341.YELLOW, ili9341.BLACK)
        
        # Linha separadora
        tft.hline(0, 35, DISPLAY_WIDTH, ili9341.WHITE)
        
    except Exception as e:
        print(f"❌ Erro ao desenhar header: {e}")

def desenhar_status_bar():
    """Desenha barra de status na parte inferior"""
    if not tft:
        return
        
    try:
        y_status = DISPLAY_HEIGHT - 25
        
        # Linha separadora
        tft.hline(0, y_status - 5, DISPLAY_WIDTH, ili9341.WHITE)
        
        # Status de conexão WiFi
        if wlan and wlan.isconnected():
            tft.text(font, "● WiFi", 10, y_status, ili9341.GREEN, ili9341.BLACK)
        else:
            tft.text(font, "● WiFi", 10, y_status, ili9341.RED, ili9341.BLACK)
        
        # Contador de eventos
        tft.text(font, f"Eventos: {len(eventos_hoje)}", 70, y_status, ili9341.GRAY, ili9341.BLACK)
        
        # Memória livre
        mem_free = gc.mem_free()
        mem_kb = mem_free // 1024
        tft.text(font, f"RAM: {mem_kb}KB", 180, y_status, ili9341.GRAY, ili9341.BLACK)
        
        # Status do sistema
        tft.text(font, "ONLINE" if sistema_ativo else "OFFLINE", 250, y_status, 
                ili9341.GREEN if sistema_ativo else ili9341.RED, ili9341.BLACK)
        
    except Exception as e:
        print(f"❌ Erro ao desenhar status bar: {e}")

def mostrar_eventos():
    """Exibe lista de eventos na tela"""
    global contador_atualizacoes, ultima_atualizacao
    
    if not tft:
        return
        
    try:
        # Limpa tela
        limpar_tela()
        
        # Desenha header
        desenhar_header()
        
        # Área principal de eventos
        y_inicio = 45
        y_pos = y_inicio
        altura_linha = 18
        max_y = DISPLAY_HEIGHT - 35
        
        if not eventos_hoje:
            # Mensagem quando não há eventos
            tft.text(font, "Nenhum evento hoje", 80, 100, ili9341.WHITE, ili9341.BLACK)
            tft.text(font, "Aguardando sincronizacao...", 50, 130, ili9341.GRAY, ili9341.BLACK)
            
            # Animação de carregamento simples
            dots = "." * ((contador_atualizacoes % 4) + 1)
            tft.text(font, f"Conectando{dots}", 90, 160, ili9341.CYAN, ili9341.BLACK)
            
        else:
            # Lista de eventos
            eventos_mostrados = 0
            
            for i, evento in enumerate(eventos_hoje[:MAX_EVENTS_DISPLAY]):
                if y_pos > max_y:
                    break
                    
                # Cores alternadas para melhor legibilidade
                cor_hora = ili9341.YELLOW
                if i % 2 == 0:
                    cor_nome = ili9341.WHITE
                    # Fundo sutil para linhas pares
                    tft.rect(0, y_pos-2, DISPLAY_WIDTH, altura_linha, ili9341.color565(20, 20, 20))
                else:
                    cor_nome = ili9341.CYAN
                
                # Hora do evento
                hora_evento = evento.get('hora', '00:00')
                if len(hora_evento) > 5:
                    hora_evento = hora_evento[:5]  # Apenas HH:MM
                
                tft.text(font, hora_evento, 15, y_pos, cor_hora, ili9341.BLACK)
                
                # Nome do evento (com truncamento inteligente)
                nome = evento.get('nome', 'Evento')
                max_chars = 25  # Ajustado para largura do display
                
                if len(nome) > max_chars:
                    # Trunca preservando palavras quando possível
                    nome_truncado = nome[:max_chars-3]
                    if ' ' in nome_truncado:
                        ultimo_espaco = nome_truncado.rfind(' ')
                        nome = nome[:ultimo_espaco] + "..."
                    else:
                        nome = nome_truncado + "..."
                
                tft.text(font, nome, 75, y_pos, cor_nome, ili9341.BLACK)
                
                y_pos += altura_linha
                eventos_mostrados += 1
            
            # Indicador de mais eventos se necessário
            if len(eventos_hoje) > MAX_EVENTS_DISPLAY:
                eventos_restantes = len(eventos_hoje) - MAX_EVENTS_DISPLAY
                tft.text(font, f"+ {eventos_restantes} eventos...", 160, max_y, ili9341.GRAY, ili9341.BLACK)
        
        # Desenha barra de status
        desenhar_status_bar()
        
        # Atualiza contadores
        contador_atualizacoes += 1
        ultima_atualizacao = utime.localtime()
        
        print(f"🖥️ Display atualizado #{contador_atualizacoes}: {len(eventos_hoje)} eventos")
        
    except Exception as e:
        print(f"❌ Erro ao mostrar eventos: {e}")
        # Tela de erro simples
        limpar_tela()
        tft.text(font, "ERRO NO DISPLAY", 80, 100, ili9341.RED, ili9341.BLACK)
        tft.text(font, str(e)[:30], 10, 130, ili9341.WHITE, ili9341.BLACK)

def mostrar_tela_inicializacao():
    """Tela de inicialização do sistema"""
    if not tft:
        return
        
    limpar_tela()
    
    # Logo/título
    tft.text(font, "SISTEMA DE EVENTOS", 60, 60, ili9341.CYAN, ili9341.BLACK)
    tft.text(font, DEVICE_NAME, 80, 85, ili9341.YELLOW, ili9341.BLACK)
    
    # Informações do dispositivo
    tft.text(font, "Raspberry Pico W", 70, 120, ili9341.WHITE, ili9341.BLACK)
    tft.text(font, f"Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}", 70, 140, ili9341.GRAY, ili9341.BLACK)
    
    # Status
    tft.text(font, "Inicializando...", 80, 170, ili9341.GREEN, ili9341.BLACK)

def mostrar_erro_wifi():
    """Tela de erro de conexão WiFi"""
    if not tft:
        return
        
    limpar_tela()
    
    # Título de erro
    tft.text(font, "ERRO DE CONEXAO", 70, 80, ili9341.RED, ili9341.BLACK)
    
    # Detalhes
    tft.text(font, f"Rede: {SSID}", 10, 110, ili9341.YELLOW, ili9341.BLACK)
    tft.text(font, "Verifique configuracoes", 40, 130, ili9341.WHITE, ili9341.BLACK)
    
    # Status
    tft.text(font, "Tentando reconectar...", 50, 160, ili9341.CYAN, ili9341.BLACK)
    
    # Indicador visual
    for i in range(3):
        x = 130 + (i * 20)
        tft.circle(x, 190, 5, ili9341.RED, True)

# ===== CONEXÃO WIFI =====
def conectar_wifi():
    """Estabelece conexão WiFi com retry automático"""
    global wlan
    
    print(f"🔗 Conectando ao WiFi: {SSID}")
    mostrar_tela_inicializacao()
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Se já conectado, retorna IP
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"✅ WiFi já conectado - IP: {ip}")
        return ip
    
    # Tenta conectar
    wlan.connect(SSID, PASSWORD)
    
    # Aguarda conexão com timeout
    timeout = 30
    while timeout > 0:
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"✅ WiFi conectado! IP: {ip}")
            
            # Sincroniza horário via NTP
            try:
                print("🕐 Sincronizando horário...")
                ntptime.settime()
                print("✅ Horário sincronizado via NTP")
            except Exception as e:
                print(f"⚠️ Falha ao sincronizar horário: {e}")
            
            return ip
        
        utime.sleep(1)
        timeout -= 1
        
        # Atualiza tela de loading
        if tft and timeout % 5 == 0:
            dots = "." * (4 - (timeout // 5) % 4)
            tft.text(font, f"Conectando{dots}    ", 80, 170, ili9341.GREEN, ili9341.BLACK)
    
    print("❌ Timeout na conexão WiFi")
    mostrar_erro_wifi()
    return None

def verificar_conexao_wifi():
    """Verifica e reconecta WiFi se necessário"""
    global wlan
    
    if not wlan or not wlan.isconnected():
        print("⚠️ WiFi desconectado - tentando reconectar...")
        return conectar_wifi()
    return wlan.ifconfig()[0]

# ===== SERVIDOR HTTP =====
def criar_servidor_http():
    """Servidor HTTP para receber comandos do backend"""
    import socket
    
    try:
        # Cria socket do servidor
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(5)
        
        print("🌐 Servidor HTTP iniciado na porta 80")
        print("🎯 Pronto para receber eventos!")
        
        while sistema_ativo:
            try:
                # Aceita conexões
                conn, addr = server_socket.accept()
                
                # Recebe dados com timeout
                conn.settimeout(10)
                request_data = conn.recv(2048)
                
                if request_data:
                    # Processa requisição
                    response = processar_requisicao_http(request_data.decode('utf-8'))
                    
                    # Envia resposta
                    conn.send(response.encode('utf-8'))
                    print(f"📨 Requisição processada de {addr[0]}")
                
                conn.close()
                
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"❌ Erro na conexão HTTP: {e}")
                try:
                    conn.close()
                except:
                    pass
            
            # Pequena pausa para não sobrecarregar
            utime.sleep(0.1)
            
            # Verificação periódica de WiFi
            if contador_atualizacoes % 100 == 0:
                verificar_conexao_wifi()
            
    except Exception as e:
        print(f"💥 Erro crítico no servidor HTTP: {e}")
    finally:
        try:
            server_socket.close()
        except:
            pass

def processar_requisicao_http(request_str):
    """Processa requisições HTTP recebidas"""
    global eventos_hoje, ultima_atualizacao
    
    try:
        # Parse básico da requisição
        lines = request_str.split('\n')
        if not lines:
            return criar_resposta_http({"erro": "Requisição vazia"}, 400)
        
        primeira_linha = lines[0].strip()
        partes = primeira_linha.split(' ')
        
        if len(partes) < 2:
            return criar_resposta_http({"erro": "Formato inválido"}, 400)
            
        metodo = partes[0].upper()
        path = partes[1]
        
        print(f"📨 {metodo} {path}")
        
        # Rota de identificação do dispositivo
        if path == "/api/pico-id" and metodo == "GET":
            return criar_resposta_http({
                "device_type": "pico",
                "name": DEVICE_NAME,
                "version": "2.0",
                "display": f"ILI9341 {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}",
                "eventos_carregados": len(eventos_hoje),
                "memoria_livre": gc.mem_free(),
                "uptime_counter": contador_atualizacoes
            })
        
        # Status do dispositivo
        elif path == "/api/status" and metodo == "GET":
            return criar_resposta_http({
                "status": "online",
                "eventos": len(eventos_hoje),
                "memoria_livre": gc.mem_free(),
                "memoria_inicial": memoria_inicial,
                "wifi_conectado": wlan.isconnected() if wlan else False,
                "wifi_ip": wlan.ifconfig()[0] if wlan and wlan.isconnected() else None,
                "uptime_updates": contador_atualizacoes,
                "ultima_atualizacao": "{:02d}:{:02d}:{:02d}".format(
                    ultima_atualizacao[3], ultima_atualizacao[4], ultima_atualizacao[5]
                ) if ultima_atualizacao else None,
                "sistema_ativo": sistema_ativo
            })
        
        # Receber evento individual
        elif path == "/api/evento" and metodo == "POST":
            return processar_comando_evento(request_str)
        
        # Limpar todos os eventos
        elif path == "/api/limpar" and metodo == "POST":
            eventos_hoje.clear()
            print("🗑️ Todos os eventos limpos")
            gc.collect()  # Limpa memória
            return criar_resposta_http({
                "mensagem": "Eventos limpos",
                "memoria_livre": gc.mem_free()
            })
        
        # Forçar atualização do display
        elif path == "/api/atualizar" and metodo == "POST":
            mostrar_eventos()
            return criar_resposta_http({
                "mensagem": "Display atualizado",
                "eventos_mostrados": len(eventos_hoje),
                "contador_atualizacoes": contador_atualizacoes
            })
        
        # Reiniciar sistema
        elif path == "/api/reiniciar" and metodo == "POST":
            return criar_resposta_http({"mensagem": "Reiniciando sistema..."})
            # Reinicia após responder
            utime.sleep(1)
            machine.reset()
        
        # Informações de debug
        elif path == "/api/debug" and metodo == "GET":
            return criar_resposta_http({
                "eventos_detalhados": eventos_hoje,
                "configuracoes": {
                    "ssid": SSID,
                    "device_name": DEVICE_NAME,
                    "display_size": f"{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}",
                    "max_events": MAX_EVENTS_DISPLAY
                },
                "sistema": {
                    "memoria_inicial": memoria_inicial,
                    "memoria_atual": gc.mem_free(),
                    "contador_updates": contador_atualizacoes
                }
            })
        
        else:
            return criar_resposta_http({"erro": f"Endpoint {path} não encontrado"}, 404)
            
    except Exception as e:
        print(f"❌ Erro ao processar requisição: {e}")
        return criar_resposta_http({"erro": f"Erro interno: {str(e)}"}, 500)

def processar_comando_evento(request_str):
    """Processa comandos específicos de eventos"""
    global eventos_hoje, ultima_atualizacao
    
    try:
        # Encontra o JSON no corpo da requisição
        body_start = request_str.find('\r\n\r\n')
        if body_start == -1:
            body_start = request_str.find('\n\n')
        
        if body_start == -1:
            return criar_resposta_http({"erro": "Corpo da requisição não encontrado"}, 400)
        
        json_data = request_str[body_start:].strip()
        
        try:
            data = json.loads(json_data)
        except Exception as e:
            return criar_resposta_http({"erro": f"JSON inválido: {e}"}, 400)
        
        acao = data.get('acao', 'adicionar')
        evento_id = data.get('id')
        
        if acao == 'adicionar':
            # Remove evento existente com mesmo ID
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
            ultima_atualizacao = utime.localtime()
            
            # Atualiza display automaticamente
            _thread.start_new_thread(mostrar_eventos, ())
            
            return criar_resposta_http({
                "mensagem": f"Evento {evento_id} adicionado",
                "total_eventos": len(eventos_hoje),
                "evento": evento
            })
            
        elif acao == 'deletar':
            # Remove evento pelo ID
            eventos_anteriores = len(eventos_hoje)
            eventos_hoje = [e for e in eventos_hoje if e.get('id') != evento_id]
            
            if len(eventos_hoje) < eventos_anteriores:
                print(f"🗑️ Evento {evento_id} removido")
                ultima_atualizacao = utime.localtime()
                
                # Atualiza display
                _thread.start_new_thread(mostrar_eventos, ())
                
                return criar_resposta_http({
                    "mensagem": f"Evento {evento_id} removido",
                    "total_eventos": len(eventos_hoje)
                })
            else:
                return criar_resposta_http({"erro": "Evento não encontrado"}, 404)
        
        else:
            return criar_resposta_http({"erro": f"Ação '{acao}' não reconhecida"}, 400)
            
    except Exception as e:
        return criar_resposta_http({"erro": f"Erro ao processar evento: {str(e)}"}, 500)

def criar_resposta_http(data, codigo=200):
    """Cria resposta HTTP com JSON"""
    try:
        json_str = json.dumps(data)
        
        status_messages = {
            200: "OK",
            400: "Bad Request", 
            404: "Not Found",
            500: "Internal Server Error"
        }
        
        status_text = status_messages.get(codigo, "Unknown")
        
        response = f"HTTP/1.1 {codigo} {status_text}\r\n"
        response += "Content-Type: application/json\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"
        response += "Connection: close\r\n"
        response += f"Content-Length: {len(json_str)}\r\n\r\n"
        response += json_str
        
        return response
        
    except Exception as e:
        # Resposta de emergência em caso de erro
        error_msg = f'{{"erro": "Erro ao criar resposta: {str(e)}"}}'
        return f"HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\nContent-Length: {len(error_msg)}\r\n\r\n{error_msg}"

# ===== THREADS DE MANUTENÇÃO =====
def thread_atualizacao_display():
    """Thread que atualiza o display periodicamente"""
    print("🔄 Thread de atualização do display iniciada")
    
    while sistema_ativo:
        try:
            # Verifica conexão WiFi
            if not verificar_conexao_wifi():
                mostrar_erro_wifi()
                utime.sleep(30)  # Aguarda mais tempo quando sem WiFi
                continue
            
            # Atualiza display
            mostrar_eventos()
            
            # Aguarda próxima atualização
            utime.sleep(DISPLAY_UPDATE_INTERVAL)
            
        except Exception as e:
            print(f"❌ Erro na thread de atualização: {e}")
            utime.sleep(30)

def thread_limpeza_memoria():
    """Thread para limpeza periódica de memória"""
    print("🧹 Thread de limpeza de memória iniciada")
    
    while sistema_ativo:
        try:
            utime.sleep(MEMORY_CLEANUP_INTERVAL)
            
            # Coleta de lixo
            memoria_antes = gc.mem_free()
            gc.collect()
            memoria_depois = gc.mem_free()
            
            memoria_liberada = memoria_depois - memoria_antes
            if memoria_liberada > 0:
                print(f"🧹 Memória limpa: +{memoria_liberada} bytes (total: {memoria_depois})")
            
            # Verifica se memória está muito baixa
            if memoria_depois < 50000:  # Menos de 50KB
                print(f"⚠️ Memória baixa: {memoria_depois} bytes")
                
        except Exception as e:
            print(f"❌ Erro na limpeza de memória: {e}")
            utime.sleep(60)

# ===== FUNÇÃO PRINCIPAL =====
def main():
    """Função principal do sistema"""
    global sistema_ativo, memoria_inicial
    
    print("="*50)
    print("🚀 SISTEMA DE EVENTOS - RASPBERRY PICO W")
    print(f"📱 Dispositivo: {DEVICE_NAME}")
    print(f"🖥️ Display: ILI9341 {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print("="*50)
    
    try:
        # Configura display
        if not configurar_display():
            print("💥 ERRO CRÍTICO: Display não configurado")
            return False
        
        # Conecta WiFi
        ip = conectar_wifi()
        if not ip:
            print("💥 ERRO CRÍTICO: WiFi não conectado")
            mostrar_erro_wifi()
            return False
        
        print(f"🌐 Sistema online no IP: {ip}")
        print(f"🔗 Acesse: http://{ip}/api/status")
        
        # Mostra tela inicial
        mostrar_eventos()
        
        # Inicia threads auxiliares
        _thread.start_new_thread(thread_atualizacao_display, ())
        _thread.start_new_thread(thread_limpeza_memoria, ())
        
        print("✅ Threads auxiliares iniciadas")
        print("🎯 Sistema pronto para receber eventos!")
        
        # Inicia servidor HTTP (blocking)
        criar_servidor_http()
        
    except KeyboardInterrupt:
        print("\n🛑 Sistema interrompido pelo usuário")
        sistema_ativo = False
        return True
        
    except Exception as e:
        print(f"💥 Erro crítico no sistema: {e}")
        sistema_ativo = False
        
        # Mostra erro na tela se possível
        if tft:
            try:
                limpar_tela()
                tft.text(font, "ERRO CRITICO", 80, 80, ili9341.RED, ili9341.BLACK)
                tft.text(font, "Sistema falhou", 70, 110, ili9341.WHITE, ili9341.BLACK)
                tft.text(font, str(e)[:25], 10, 140, ili9341.YELLOW, ili9341.BLACK)
                tft.text(font, "Reinicie o dispositivo", 40, 170, ili9341.CYAN, ili9341.BLACK)
            except:
                pass
                
        return False

# ===== EXECUÇÃO =====
if __name__ == "__main__":
    print("\n🎬 Iniciando sistema...")
    
    try:
        sucesso = main()
        if sucesso:
            print("✅ Sistema encerrado com sucesso")
        else:
            print("❌ Sistema encerrado com erro")
            
    except Exception as e:
        print(f"💥 Exceção não tratada: {e}")
        
    finally:
        sistema_ativo = False
        print("🏁 Fim da execução")
        
        # Tenta limpar recursos
        try:
            if tft:
                limpar_tela()
                tft.text(font, "Sistema encerrado", 60, 120, ili9341.RED, ili9341.BLACK)
        except:
            pass
        
