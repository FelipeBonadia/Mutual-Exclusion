import json
import socket
import threading
import time

# Cores para mensagens do terminal
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
UNDERLINE = "\033[4m"
R = "\033[0m"  # Reset

# Mensagens constantes
QUESTION = f"""
Digite {UNDERLINE}solicitar <nome do recurso>{R} para solicitar acesso a um recurso.
Digite {UNDERLINE}liberar <nome do recurso>{R} para liberar um recurso.
Digite {UNDERLINE}sair{R} para encerrar o processo"""
AUTOMATIC_TEST = f"{GREEN}Inicializando teste automático...{R}"
DEBUG_MESSAGE_TYPE = "\n{}DEBUG: Mensagem do tipo {} enviada para {}.{}"
DEBUG_FILA = (
    "{}DEBUG: {} adicionado à fila de espera para {}\n[recurso_ocupado = {}, {} > {}]{}"
)


# Configurações
HOST = "localhost"
PORT = 8002  # Mude para 8002 e 8003 nos outros arquivos
ID_PROCESSO = "p2"  # Mude para p1 e p3
PROCESSOS = {
    "p1": ("localhost", 8001),
    "p2": ("localhost", 8002),
    "p3": ("localhost", 8003),
}

# Modo de debug
debug_mode = True
teste_ativo = False

# Estado local
recurso_ocupado = False
fila_recurso = []
respostas_esperadas = {}  # {"recurso": set(de processos aguardando resposta)}
relogio_local = 0
esperando_recurso = None

# Gerenciamento de threads
lock = threading.Lock()
cond_fila = threading.Condition(lock)

# Função de atualização de relógio
def atualizar_relogio(timestamp_recebido):
    global relogio_local
    relogio_local = max(relogio_local, int(timestamp_recebido)) + 1

# Função para envio de mensagens
def enviar_mensagem(destino: str, mensagem):
    host, port = PROCESSOS[destino]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(json.dumps(mensagem).encode())
            if debug_mode:
                print(DEBUG_MESSAGE_TYPE.format(YELLOW, mensagem["tipo"], destino, R))
    except Exception as e:
        print(f"Erro ao enviar mensagem para {destino}: {e}")

# Multicast para requisitar acesso ao recurso
def multicast_requisicao(recurso: str):
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

# Enviar resposta (NACK) para requisições recebidas
def enviar_nack(destino, recurso):
    global relogio_local
    relogio_local += 1
    mensagem = {
        "tipo": "nack",
        "recurso": recurso,
        "timestamp": relogio_local,
        "id": ID_PROCESSO,
    }
    enviar_mensagem(destino, mensagem)

# Função para o processo de aguardar liberação do recurso
def aguardar_recurso(recurso):
    global recurso_ocupado, esperando_recurso
    while recurso_ocupado:
        time.sleep(0.1)  # Verifica periodicamente
    print(f"Recurso {recurso} foi liberado.")
    entrar_recurso_critico(recurso)

# Entrar no recurso crítico
def entrar_recurso_critico(recurso: str):
    global recurso_ocupado, esperando_recurso

    if recurso_ocupado:
        print(f"Recurso {recurso} já está ocupado. O que deseja fazer?")
        print("1. Esperar o recurso ser liberado")
        print("2. Desistir da tentativa")
        escolha = input("> ").strip()
        if escolha == "1":
            print(f"Aguardando liberação do recurso {recurso}...")
            # Cria uma thread para verificar a liberação do recurso sem travar o terminal
            threading.Thread(target=aguardar_recurso, args=(recurso,), daemon=True).start()
        else:
            print(f"Você optou por desistir do recurso {recurso}.")
        return

    print(f"Requisitando acesso ao {recurso}...")
    esperando_recurso = recurso
    if teste_ativo:
        time.sleep(2)  # Simula atraso na requisição
    multicast_requisicao(recurso)
    while respostas_esperadas[recurso]:
        time.sleep(0.1)  # Aguarda receber todos os ACKs
    recurso_ocupado = True
    print(f"Acesso concedido ao {recurso}! \n")

# Sair do recurso crítico
def sair_recurso_critico(recurso):
    global recurso_ocupado, esperando_recurso, fila_recurso

    if recurso_ocupado and esperando_recurso == recurso:
        recurso_ocupado = False
        esperando_recurso = None
        print(f"Recurso {recurso} liberado.")

        # Notifica o próximo processo na fila
        if fila_recurso:
            requisicao = fila_recurso.pop(0)  # Retira o primeiro processo da fila
            enviar_ack(requisicao["id"], recurso)
            print(f"Processo {requisicao['id']} recebeu o recurso {recurso}.")
        # Reset fila após processar
        fila_recurso.clear()

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
            if debug_mode:
                print(
                    DEBUG_FILA.format(
                        YELLOW,
                        remetente,
                        recurso,
                        recurso_ocupado,
                        (relogio_local, ID_PROCESSO),
                        (timestamp, remetente),
                        R,
                    )
                )
            # Enviar NACK se o recurso está ocupado
            enviar_nack(remetente, recurso)
        else:
            enviar_ack(remetente, recurso)
    elif tipo == "ack":
        if recurso in respostas_esperadas:
            respostas_esperadas[recurso].discard(remetente)
    elif tipo == "nack":
        print(f"Recurso {recurso} ocupado. Processando NACK de {remetente}.")
        print("O que deseja fazer?")
        print("1. Esperar o recurso ser liberado")
        print("2. Desistir da tentativa")
        escolha = input("> ").strip()
        if escolha == "1":
            print(f"Aguardando liberação do recurso {recurso}...")
            threading.Thread(target=aguardar_recurso, args=(recurso,), daemon=True).start()
        else:
            print(f"Você optou por desistir do recurso {recurso}.")
        return

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
        print(QUESTION.strip())
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

# Teste automático
def teste_automatico():
    global teste_ativo
    teste_ativo = True

    time.sleep(2)  # Espera para sincronizar a execução com o processo 3
    print("\n" + AUTOMATIC_TEST)
    entrar_recurso_critico("r1")
    time.sleep(3)  # Simula o uso do recurso
    sair_recurso_critico("r1")


# Inicialização
if __name__ == "__main__":
    threading.Thread(target=servidor, daemon=True).start()

    # Executa o teste automático
    # threading.Thread(target=teste_automatico).start()

    interface_usuario()
