#!/usr/bin/env python3
"""
Script para testar comunicação MQTT com o Pico 2W
Execute este script para enviar eventos de teste
"""

import paho.mqtt.client as mqtt
import json
import time
import random
from datetime import datetime

# Configurações MQTT
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
CLIENT_ID = f"test_client_{random.randint(1000, 9999)}"

# Substitua pelo Client ID do seu Pico (aparece no display)
PICO_CLIENT_ID = "pico2w_XXXXXXXX"  # SUBSTITUA AQUI!
TOPIC_BASE = f"eventos_pico/{PICO_CLIENT_ID}"

class MQTTTester:
    def __init__(self):
        self.client = mqtt.Client(CLIENT_ID)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.connected = False
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print("✅ Conectado ao broker MQTT!")
            
            # Subscrever aos tópicos de resposta
            client.subscribe(f"{TOPIC_BASE}/ack")
            client.subscribe(f"{TOPIC_BASE}/status")
            print(f"📡 Subscrito aos tópicos de resposta")
        else:
            print(f"❌ Falha na conexão: {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            message = json.loads(msg.payload.decode())
            print(f"📨 Resposta do Pico: {topic} -> {message}")
        except:
            print(f"📨 Mensagem recebida: {msg.topic} -> {msg.payload}")
    
    def connect(self):
        try:
            print(f"Conectando ao broker: {MQTT_BROKER}")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            
            # Aguardar conexão
            timeout = 10
            while not self.connected and timeout > 0:
                time.sleep(1)
                timeout -= 1
            
            return self.connected
        except Exception as e:
            print(f"Erro na conexão: {e}")
            return False
    
    def enviar_evento_teste(self, evento_id, nome, hora):
        """Envia um evento de teste para o Pico"""
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        evento = {
            "id": evento_id,
            "nome": nome,
            "hora": hora,
            "data": hoje,
            "acao": "adicionar",
            "timestamp": datetime.now().isoformat()
        }
        
        topic = f"{TOPIC_BASE}/evento"
        payload = json.dumps(evento)
        
        result = self.client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"🚀 Evento enviado: '{nome}' às {hora}")
            return True
        else:
            print(f"❌ Falha no envio: {result.rc}")
            return False
    
    def enviar_comando(self, acao):
        """Envia comando para o Pico"""
        comando = {
            "acao": acao,
            "timestamp": datetime.now().isoformat()
        }
        
        topic = f"{TOPIC_BASE}/comando"
        payload = json.dumps(comando)
        
        result = self.client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Comando enviado: {acao}")
            return True
        else:
            print(f"❌ Falha no envio do comando: {result.rc}")
            return False
    
    def deletar_evento(self, evento_id):
        """Deleta um evento específico"""
        evento = {
            "id": evento_id,
            "acao": "deletar",
            "timestamp": datetime.now().isoformat()
        }
        
        topic = f"{TOPIC_BASE}/evento"
        payload = json.dumps(evento)
        
        result = self.client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"🗑️ Comando de deleção enviado para evento {evento_id}")
            return True
        else:
            print(f"❌ Falha na deleção: {result.rc}")
            return False
    
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("🔌 Desconectado")

def main():
    print("=== TESTE MQTT PARA PICO 2W ===")
    print(f"Cliente: {CLIENT_ID}")
    print(f"Pico Target: {PICO_CLIENT_ID}")
    print(f"Tópico base: {TOPIC_BASE}")
    print("================================")
    
    if PICO_CLIENT_ID == "pico2w_XXXXXXXX":
        print("❌ ERRO: Você precisa substituir PICO_CLIENT_ID pelo ID real do seu Pico!")
        print("   O ID aparece no display do Pico quando ele inicia")
        return
    
    # Criar tester
    tester = MQTTTester()
    
    if not tester.connect():
        print("❌ Não foi possível conectar ao broker")
        return
    
    try:
        while True:
            print("\n=== MENU DE TESTE ===")
            print("1. Enviar evento de teste")
            print("2. Enviar múltiplos eventos")
            print("3. Limpar todos os eventos")
            print("4. Atualizar display")
            print("5. Solicitar status")
            print("6. Deletar evento específico")
            print("0. Sair")
            
            opcao = input("\nEscolha uma opção: ").strip()
            
            if opcao == "1":
                nome = input("Nome do evento: ").strip() or "Evento Teste"
                hora = input("Hora (HH:MM): ").strip() or "14:30"
                evento_id = random.randint(1000, 9999)
                tester.enviar_evento_teste(evento_id, nome, hora)
            
            elif opcao == "2":
                eventos_teste = [
                    (1, "Reunião de equipe", "09:00"),
                    (2, "Ligação importante", "10:30"),
                    (3, "Almoço de negócios", "12:00"),
                    (4, "Apresentação", "15:30"),
                    (5, "Revisão do projeto", "17:00")
                ]
                
                print("Enviando múltiplos eventos...")
                for evento_id, nome, hora in eventos_teste:
                    tester.enviar_evento_teste(evento_id, nome, hora)
                    time.sleep(0.5)  # Pequena pausa entre envios
            
            elif opcao == "3":
                tester.enviar_comando("limpar")
            
            elif opcao == "4":
                tester.enviar_comando("atualizar_display")
            
            elif opcao == "5":
                tester.enviar_comando("status")
            
            elif opcao == "6":
                try:
                    evento_id = int(input("ID do evento para deletar: "))
                    tester.deletar_evento(evento_id)
                except ValueError:
                    print("❌ ID inválido")
            
            elif opcao == "0":
                break
            
            else:
                print("❌ Opção inválida")
            
            # Aguardar um pouco para ver as respostas
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n⏹️ Teste interrompido pelo usuário")
    
    finally:
        tester.disconnect()

if __name__ == "__main__":
    main()