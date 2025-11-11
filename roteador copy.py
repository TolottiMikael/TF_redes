import socket
import threading
import time
from typing import Dict, Tuple, Set, Optional
from constants import PORT, ROUTE_ANNOUNCE_INTERVAL, NEIGHBOR_TIMEOUT, TABLE_PRINT_INTERVAL
from utils import now_ts, serialize_table_for_neighbor, parse_route_announcement
from logging_utils import format_table

class Router:
    def __init__(self, ip: str, neighbors: Set[str]):
        self.ip = ip
        self.neighbors = neighbors  # ips (strings)
        # tabela: dest_ip -> (metric:int, next_hop:str, last_updated_ts:float, origin:str)
        # origin: 'local' (configuração direta / vizinho físico) ou 'learned' (recebida de anúncio)
        self.table: Dict[str, Tuple[int, str, float, str]] = {}
        # não incluir rota para ele mesmo
        # inicializar tabela com vizinhos (métrica 1)
        for n in self.neighbors:
            if n != self.ip:
                self.table[n] = (1, n, now_ts(), 'local')

        # dados por vizinho: o último conjunto de rotas que esse vizinho anunciou
        self.neigh_adv: Dict[str, Set[str]] = {n: set() for n in self.neighbors}
        self.neigh_last_heard: Dict[str, float] = {n: 0.0 for n in self.neighbors}
        self.lock = threading.Lock()

        # socket UDP usado para enviar/receber na porta definida
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, PORT))
        self.sock.settimeout(1.0)


        # control
        self._stop_event = threading.Event()

    # ------------------------
    # Serialização / Parsers
    # ------------------------

    # ------------------------
    # Envio de mensagens
    # ------------------------
    def send_to(self, dest_ip: str, message: str):
        try:
            print(f"enviando msg para ({dest_ip},{PORT}) : => {message}")
            self.sock.sendto(message.encode('utf-8'), (dest_ip, PORT))
        except OSError as e:
            print(f"[WARN] Erro ao enviar para {dest_ip}: {e}")

    def broadcast_routes(self, immediate=False):
        """
        Envia a tabela atual para todos os vizinhos.
        Se immediate=True, usado quando tabela mudou e precisa notificar imediatamente.
        """
        with self.lock:
            table_copy = dict(self.table)
        for n in list(self.neighbors):
            payload = serialize_table_for_neighbor(table_copy, n, self.ip)
            self.send_to(n, payload)
        if immediate:
            print("[ROUTER] Enviado anúncio imediato de rotas para vizinhos.")

    def send_announcement_self(self):
        """
        Envia @<meu_ip> para os vizinhos para anunciar chegada.
        """
        msg = f"@{self.ip}"
        for n in list(self.neighbors):
            self.send_to(n, msg)
        print("[ROUTER] Anúncio @ enviado aos vizinhos.")

    # ------------------------
    # Recepção e processamento
    # ------------------------
    def handle_route_announcement(self, neighbor_ip: str, payload: str):
        """
        Recebe um anúncio de rotas de neighbor_ip com payload "*IP;METRIC..."
        Atualiza tabela conforme regras (métrica+1 para rotas aprendidas).
        """
        parsed = parse_route_announcement(payload)
        now = now_ts()
        changes = {"added": [], "updated": [], "removed": []}
        with self.lock:
            self.neigh_last_heard[neighbor_ip] = now
            prev_adv = self.neigh_adv.get(neighbor_ip, set())
            new_adv_set = set(parsed.keys())

            self.neigh_adv[neighbor_ip] = new_adv_set

            if neighbor_ip not in self.table:
                print(f"rota {neighbor_ip} adicionada")
                self.table[neighbor_ip] = (1, neighbor_ip, now, 'learned')
                self.neighbors.add(neighbor_ip)
                changes["added"].append((neighbor_ip, 1, neighbor_ip))
            



            # print(f"atualizei isto : {self.neigh_adv[neighbor_ip]}")
            # 1) Processar rotas recebidas -> add/update
            for dest, recv_metric in parsed.items():
                candidate_metric = recv_metric + 1
                if dest == self.ip:
                    print(f"[DEBUG] rota para nós mesmo check : {dest}")
                    # continue  # não incluir rotas para nós mesmos
                elif dest not in self.table:
                    # adicionar rota aprendida
                    # print(f"[DEBUG] rota aprendida: {dest}")
                    print(f"rota {dest} adicionada")
                    self.table[dest] = (candidate_metric, neighbor_ip, now, 'learned')
                    changes["added"].append((dest, candidate_metric, neighbor_ip))
                else:
                    cur_metric, cur_next, _, cur_origin = self.table[dest]
                    # se a rota vier do mesmo next_hop, atualizamos timestamp e métrica (se necessário)
                    print(f"self.table[dest]: {self.table[dest]}")
                    if neighbor_ip == cur_next:
                        if dest not in new_adv_set:
                            print(f"link {dest} perdido")
                            del self.table[dest]
                            changes["removed"].append(dest)

                        if candidate_metric < cur_metric:
                            self.table[dest] = (candidate_metric, neighbor_ip, now, cur_origin)
                            print(f"[DEBUG] atualizei a métrica para {dest} : m: {candidate_metric}")
                            changes["updated"].append((dest, candidate_metric, neighbor_ip))
                        else:
                            # só atualizar timestamp
                            print(f"[DEBUG] atualizei o timestamp p/ {dest}")
                            self.table[dest] = (cur_metric, cur_next, now, cur_origin)
                    else:
                        # se a nova rota for melhor, substituir (mantém origin learned)
                        if candidate_metric < cur_metric:
                            print(f"[DEBUG] atualizado rota para {dest}")
                            self.table[dest] = (candidate_metric, neighbor_ip, now, 'learned')
                            changes["updated"].append((dest, candidate_metric, neighbor_ip))

        
        # se houve mudanças, exibir e enviar atualização imediata
        if changes["added"] or changes["updated"] or changes["removed"]:
            self.print_table(changes)
            # enviar imediatamente tabela atualizada aos vizinhos
            self.broadcast_routes(immediate=True)

    def handle_router_announcement(self, neighbor_ip: str, advertised_ip: str):
        """
        Recebe '@<ip>' de neighbor_ip (o vizinho acaba de anunciar sua chegada).
        Deve incluir esse IP com métrica 1 (se ainda não existir)
        """
        now = now_ts()
        with self.lock:
            # garantir que advertised_ip seja tratado como vizinho informado. Note: vizinho real deve existir em roteadores.txt
            if advertised_ip != self.ip:
                # adiciona/atualiza entrada diretamente
                if (advertised_ip not in self.table or
                    self.table[advertised_ip][0] != 1 or
                    self.table[advertised_ip][1] != neighbor_ip):
                    self.table[advertised_ip] = (1, neighbor_ip, now, 'local')
                    changes = {"added": [(advertised_ip, 1, neighbor_ip)], "updated": [], "removed": []}
                    self.print_table(changes)
                    # enviar imediata
                    self.broadcast_routes(immediate=True)
            # atualizar last heard e adv set empty
            self.neigh_last_heard[neighbor_ip] = now
            # neighbor may include us in its list: not necessary to set neigh_adv here

    def handle_text_message(self, raw_msg: str, from_ip: str):
        """
        Mensagem do tipo: !orig;dest;texto
        If dest==self.ip => print and indicate arrived
        else => forward according to routing table (next_hop)
        """
        try:
            if not raw_msg.startswith("!"):
                return
            body = raw_msg[1:]
            origin, dest, message = body.split(";", 2)
        except Exception:
            print(f"[WARN] Mensagem de texto mal formada de {from_ip}: {raw_msg}")
            return

        if dest == self.ip:
            print(f"[MSG] Recebida mensagem para mim. Origem={origin} | Mensagem='{message}'")
            return

        # procurar rota
        with self.lock:
            entry = self.table.get(dest)
            if not entry:
                print(f"[ROUTE] Sem rota para {dest}. Mensagem descartada. Origem={origin}")
                return
            next_hop = entry[1]

        # repassar
        print(f"[ROUTE] Encaminhando mensagem para {dest} via {next_hop} (origem {origin})")
        self.send_to(next_hop, raw_msg)

    # ------------------------
    # Thread: listener
    # ------------------------
    def listener_loop(self):
        print(f"[LISTENER] Escutando em {self.ip}:{PORT} ...")
        while not self._stop_event.is_set():
            
            if self.sock is None:
                # recria o socket
                print("recriando o socket")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.bind((self.ip, PORT))
                self.sock.settimeout(1.0)

            try:
                data, addr = self.sock.recvfrom(4096)
                # print(f"[debug] (data, addr) : ({data}, {addr})")
            except socket.timeout:
                # print(f"[SYSTEM] SOCKET TIMEOUT")
                continue
            except OSError as e:
                print(f"[ERROR] SOCKET ERROR :  {e}")
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                time.sleep(1)
                continue

            msg = data.decode('utf-8', errors='replace') if data else ""
            src_ip = addr[0]
            # decidir tipo
            if msg.startswith("@"):
                advertised_ip = msg[1:].strip()
                print(f"[RECV] Anúncio @ de {src_ip}: {advertised_ip}")
                self.handle_router_announcement(src_ip, advertised_ip)
            elif msg.startswith("!"):
                # mensagem de texto roteadar
                print(f"[RECV] Mensagem de texto de {src_ip}: {msg}")
                self.handle_text_message(msg, src_ip)
            else:
                # rota announcement (pode ser vazia string)
                print(f"[RECV] Anúncio de rotas de {src_ip}: '{msg[:80]}'")
                self.handle_route_announcement(src_ip, msg)
        print(f"[SYSTEM] Não Tô escutando mais!")
    # ------------------------
    # Thread: periodic announcer
    # ------------------------
    def announcer_loop(self):
        next_send = time.time() + ROUTE_ANNOUNCE_INTERVAL
        while not self._stop_event.is_set():
            now = time.time()
            if now >= next_send:
                print(f"[ANNOUNCER] Enviando anúncio de rotas.")
                self.broadcast_routes()
                next_send = now + ROUTE_ANNOUNCE_INTERVAL
            time.sleep(0.2)

    # ------------------------
    # Thread: neighbor monitor (detect failures)
    # ------------------------
    def monitor_loop(self):
        while not self._stop_event.is_set():
            now = now_ts()
            removed_neighbors = []

            with self.lock:
                for n in list(self.neighbors):
                    # print(f"[MONITOR] checando se {n} está ativo")
                    last = self.neigh_last_heard.get(n, 0.0)
                    # print(f"{last} != 0.0 and ({now} - {last}) > {NEIGHBOR_TIMEOUT}")
                    if last != 0.0 and (now - last) > NEIGHBOR_TIMEOUT:
                        # neighbor considered inactive
                        removed_neighbors.append(n)

            # para vizinhos inativos: remover rotas que são via eles e marcar last_heard=0
            for n in removed_neighbors:
                print(f"[MONITOR] Vizinho {n} considerado INATIVO (sem anúncios há {NEIGHBOR_TIMEOUT}s).")
                # remover rotas cujo next_hop == n
                to_del = [dest for dest, (metric, next_hop, _, origin) in self.table.items() if next_hop == n]
                for dest in to_del:
                    del self.table[dest]
                # limpar o registro do vizinho
                self.neigh_last_heard[n] = 0.0
                self.neigh_adv[n] = set()
                # not removing n from self.neighbors, porque arquivo roteadores.txt define os vizinhos possíveis.
                if to_del:
                    print("teste de exclusão")
                    self.print_table({"added": [], "updated": [], "removed": to_del})
                    # notificar vizinhos imediatamente
                    print("notificando que um saiu")
                    self.broadcast_routes(immediate=True)
                    print("notifiquei que um saiu")
                 
            time.sleep(1.0)

    # ------------------------
    # Util: exibir tabela e diffs
    # ------------------------
    def print_table(self, changes=None):
        with self.lock:
            lines = []
            lines.append("=== TABELA DE ROTEAMENTO ===")
            lines.append(f"Roteador: {self.ip}")
            # Exibição simplificada conforme enunciado (sem coluna de idade)
            lines.append(f"{'Destino':<16} {'Métrica':<7} {'Saída':<16} {'Origem':<8}")
            for dest, (metric, next_hop, ts, origin) in sorted(self.table.items()):
                lines.append(f"{dest:<16} {metric:<7} {next_hop:<16} {origin:<8}")
            lines.append("===========================")
        # print
        print("\n".join(lines))
        # se houver mudanças, destacar
        if changes:
            added = changes.get("added", [])
            updated = changes.get("updated", [])
            removed = changes.get("removed", [])
            if added:
                print("[CHANGE] Adicionadas:")
                for d, m, nh in added:
                    print(f"  + {d} via {nh} (metric={m})")
            if updated:
                print("[CHANGE] Atualizadas:")
                for d, m, nh in updated:
                    print(f"  ~ {d} via {nh} (metric={m})")
            if removed:
                for r in removed:
                    print(f"  - {r}")

    # ------------------------
    # Start / Stop
    # ------------------------
    def start(self):
        self._stop_event.clear()
        self.threads = []
        t_listener = threading.Thread(target=self.listener_loop, daemon=True)
        t_announcer = threading.Thread(target=self.announcer_loop, daemon=True)
        t_monitor = threading.Thread(target=self.monitor_loop, daemon=True)
        # thread adicional para impressão periódica da tabela
        t_table_printer = threading.Thread(target=self.table_printer_loop, daemon=True)
        self.threads.extend([t_listener, t_announcer, t_monitor, t_table_printer])
        for t in self.threads:
            t.start()

        # announce self when starting
        self.send_announcement_self()
        # print initial table
        self.print_table()

    def stop(self, timeout=2.0):
        self._stop_event.set()
        # close socket to wake recvfrom
        try:
            self.sock.close()
        except Exception:
            pass
        for t in self.threads:
            t.join(timeout=0.5)

    # ------------------------
    # Thread: impressão periódica da tabela
    # ------------------------
    def table_printer_loop(self, interval: float = TABLE_PRINT_INTERVAL):
        next_print = time.time() + interval
        while not self._stop_event.is_set():
            now = time.time()
            if now >= next_print:
                self.print_table()
                next_print = now + interval
            time.sleep(0.5)
