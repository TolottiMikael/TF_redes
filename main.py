# main.py
import queue
import socket
import sys
import threading
import time
from roteador import Router
from logging_utils import safe_print

ROUTERS_FILENAME = "roteadores.txt"

def get_dynamic_ip() -> str:
    # obtem o seu propro ip local
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # não precisa de conexão real, só um jeito de obter o ip local
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1" # fallback ip local
    finally:
        s.close()
    return ip

def load_neighbors(filename: str) -> set:
    # lê o arquivo de vizinhos e retorna um set de IPs
    neighbors = set()
    try:
        with open(filename, "r") as f:
            print(f"arquivo f {f} ")
            for line in f:
                print(f"resolvendo {line} agora mesmo")
                ip = line.strip()
                if ip:
                    neighbors.add(ip)
    except FileNotFoundError:
        safe_print(f"Arquivo {filename} não encontrado. Crie com os IPs dos vizinhos (um por linha).")
    return neighbors
def cli_loop(router: Router):
    safe_print("CLI: digite '<IP_destino>;<mensagem>' ou 'sair' para encerrar.")

    cmd_queue = queue.Queue()
    stop_cli = threading.Event()

    def input_thread():
        """Thread dedicada para leitura do teclado (não bloqueia o programa)."""
        while not stop_cli.is_set():
            try:
                line = input().strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                safe_print("\n[CLI] Interrompido pelo usuário (Ctrl+C).")
                stop_cli.set()
                break
            cmd_queue.put(line)

    t_input = threading.Thread(target=input_thread, daemon=True)
    t_input.start()

    try:
        while not stop_cli.is_set():
            try:
                line = cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not line:
                continue

            # Comando para imprimir a tabela de roteamento atual
            if line.strip().upper() == 'R':
                safe_print("[CLI] Tabela de roteamento atual:")
                router.print_table()
                continue

            if line.lower() in ("sair", "exit", "quit"):
                safe_print("[CLI] Encerrando interação do usuário.")
                stop_cli.set()
                break

            if ";" not in line:
                safe_print("Formato inválido. Use: 192.168.x.y;mensagem ou 'R' para mostrar a tabela")
                continue

            dest, text = line.split(";", 1)
            dest, text = dest.strip(), text.strip()
            if not dest or not text:
                safe_print("Destino ou mensagem vazios.")
                continue

            origin = router.ip
            raw = f"!{origin};{dest};{text}"

            if dest == origin:
                router.handle_text_message(raw, origin)
            else:
                with router.lock:
                    entry = router.table.get(dest)
                    if not entry:
                        safe_print(f"Sem rota conhecida para {dest}.")
                        continue
                    next_hop = entry[1]
                router.send_to(next_hop, raw)
                safe_print(f"Mensagem enviada para {dest} via {next_hop}.")
    finally:
        stop_cli.set()
        router.stop()
        safe_print("[CLI] Finalizado.")
def main():
    ip = get_dynamic_ip()
    safe_print(f"MEU IP: {ip}")
    neighs = load_neighbors(ROUTERS_FILENAME)
    safe_print(f"MEUS VIZINHOS: {neighs}")
    router = Router(ip, neighs)
    router.start()
    try:
        cli_loop(router)
    finally:
        safe_print("POWER OFF...")
        router.stop()

if __name__ == "__main__":
    main()