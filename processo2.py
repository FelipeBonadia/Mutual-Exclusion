import socket
import threading
import json
import time

# Configurações
HOST = "localhost"
PORT = 8002  # Mude para 8002 e 8003 nos outros arquivos
ID_PROCESSO = "processo2"  # Mude para processo2 e processo3
PROCESSOS = {
    "processo1": ("localhost", 8001),
    "processo2": ("localhost", 8002),
    "processo3": ("localhost", 8003),
}

# Estado local
recurso_ocupado = False
fila_recurso = []
respostas_esperadas = {}  # {"recurso": set(de processos aguardando resposta)}
relogio_local = 0
esperando_recurso = None

# Função de atualização de relógio
def atualizar_relogio(timestamp_recebido):
    global relogio_local
    relogio_local = max(relogio_local, timestamp_recebido) + 1

# Função para envio de mensagens
def enviar_mensagem(destino, mensagem):
    host, port = PROCESSOS[destino]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(json.dumps(mensagem).encode())
    except Exception as e:
        print(f"Erro ao enviar mensagem para {destino}: {e}")

# Multicast para requisitar acesso ao recurso
def multicast_requisicao(recurso):
    global relogio_local, respostas_esperadas
    relogio_local += 1
    mensagem = {
        "tipo": "requisicao",
        "recurso": recurso,
        "timestamp": relogio_local,
        "id": ID_PROCESSO,
    }
    respostas_esperadas[recurso] = set(PROCESSOS.keys()) - {ID_PROCESSO}
    for destino in PROCESSOS:
        if destino != ID_PROCESSO:
            enviar_mensagem(destino, mensagem)

# Enviar resposta (ACK) para requisições recebidas
def enviar_ack(destino, recurso):
    global relogio_local
    relogio_local += 1
    mensagem = {
        "tipo": "ack",
        "recurso": recurso,
        "timestamp": relogio_local,
        "id": ID_PROCESSO,
    }
    enviar_mensagem(destino, mensagem)

# Entrar no recurso crítico
def entrar_recurso_critico(recurso):
    global recurso_ocupado, esperando_recurso
    if recurso_ocupado:
        print(f"Recurso {recurso} já está ocupado. O que deseja fazer?")
        print("1. Esperar o recurso ser liberado")
        print("2. Desistir da tentativa")
        escolha = input("> ").strip()
        if escolha == "1":
            print(f"Aguardando liberação do recurso {recurso}...")
            while recurso_ocupado:
                time.sleep(0.1)
            entrar_recurso_critico(recurso)
        else:
            print(f"Você optou por desistir do recurso {recurso}.")
        return

    print(f"Requisitando acesso ao {recurso}...")
    esperando_recurso = recurso
    multicast_requisicao(recurso)
    while respostas_esperadas[recurso]:
        time.sleep(0.1)  # Aguarda receber todos os ACKs
    recurso_ocupado = True
    print(f"Acesso concedido ao {recurso}!")

# Sair do recurso crítico
def sair_recurso_critico(recurso):
    global recurso_ocupado, esperando_recurso, fila_recurso
    if recurso_ocupado and esperando_recurso == recurso:
        recurso_ocupado = False
        esperando_recurso = None
        print(f"Recurso {recurso} liberado.")
        # Responde para processos na fila
        while fila_recurso:
            requisicao = fila_recurso.pop(0)
            enviar_ack(requisicao["id"], recurso)

# Processar mensagens recebidas
def processar_mensagem(mensagem):
    global relogio_local, fila_recurso, respostas_esperadas
    tipo = mensagem["tipo"]
    recurso = mensagem["recurso"]
    remetente = mensagem["id"]
    timestamp = mensagem["timestamp"]

    atualizar_relogio(timestamp)

    if tipo == "requisicao":
        # Recurso ocupado ou prioridade do remetente maior
        if recurso_ocupado or (
            esperando_recurso == recurso
            and (relogio_local, ID_PROCESSO) > (timestamp, remetente)
        ):
            fila_recurso.append(mensagem)
        else:
            enviar_ack(remetente, recurso)
    elif tipo == "ack":
        if recurso in respostas_esperadas:
            respostas_esperadas[recurso].discard(remetente)

# Thread para receber conexões
def servidor():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    while True:
        conn, addr = server.accept()
        with conn:
            data = conn.recv(1024)
            if data:
                mensagem = json.loads(data.decode())
                processar_mensagem(mensagem)

# Interface para comandos do usuário
def interface_usuario():
    while True:
        print("digite solicitar <nome do curso> para seleciona-lo, digite liberar <nome do recurso> para libera-lo, ou digite sair ")
        comando = input("> ").strip()
        if comando.startswith("solicitar"):
            _, recurso = comando.split()
            entrar_recurso_critico(recurso)
        elif comando.startswith("liberar"):
            _, recurso = comando.split()
            sair_recurso_critico(recurso)
        elif comando == "sair":
            print(f"Encerrando {ID_PROCESSO}...")
            break

# Inicialização
if __name__ == "__main__":
    threading.Thread(target=servidor, daemon=True).start()
    interface_usuario()
