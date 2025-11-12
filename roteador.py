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
            print(f"[DEBUG] Enviando para ({dest_ip},{PORT}) : => {message}")
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
            # if payload:
            # print(f"mandando para {n}")
            self.send_to(n, payload)
            # print(f"enviei : {payload} para o {n}")
            # else:
                # enviar mensagem vazia (nenhuma rota anunciada) é aceitável — porém enviar string vazia não trafega, então mandamos um marker vazio
                # self.send_to(n, "")  # socket sendto permite "", será ignorado do outro lado
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
        Processa um anúncio de rotas recebido de um vizinho (neighbor_ip).
    
        O payload tem o formato: "*DEST_IP;METRIC..."
        - Incrementa a métrica em +1 para rotas aprendidas.
        - Atualiza, adiciona ou remove rotas conforme necessário.
        - Envia atualizações se houver alterações.
        """
        parsed = parse_route_announcement(payload)
        now = now_ts()
    
        changes = {"added": [], "updated": [], "removed": []}
    
        with self.lock:
            # Atualiza timestamp de último contato do vizinho
            self.neigh_last_heard[neighbor_ip] = now
    
            # Mantém o conjunto de rotas anunciadas por esse vizinho
            previous_adv = self.neigh_adv.get(neighbor_ip, set())
            current_adv = set(parsed.keys())
            self.neigh_adv[neighbor_ip] = current_adv
    
            # Garante que o vizinho esteja registrado na tabela
            if neighbor_ip not in self.table:
                print(f"[INFO] Vizinho {neighbor_ip} adicionado à tabela")
                self.table[neighbor_ip] = (1, neighbor_ip, now, 'learned')
                self.neighbors.add(neighbor_ip)
                changes["added"].append((neighbor_ip, 1, neighbor_ip))
    
            # --- Processa cada rota recebida ---
            for dest, recv_metric in parsed.items():
                if dest == self.ip:
                    # Ignora anúncios de rota para si próprio
                    continue
                
                candidate_metric = recv_metric + 1
                existing_entry = self.table.get(dest)
    
                if not existing_entry:
                    # Rota nova — adiciona
                    self.table[dest] = (candidate_metric, neighbor_ip, now, 'learned')
                    print(f"[ADD] Rota {dest} via {neighbor_ip} (métrica {candidate_metric})")
                    changes["added"].append((dest, candidate_metric, neighbor_ip))
                    continue
                
                cur_metric, cur_next, _, cur_origin = existing_entry
    
                if neighbor_ip == cur_next:
                    # Atualiza rota existente com o mesmo next-hop
                    if dest not in current_adv:
                        # Vizinho deixou de anunciar esta rota
                        print(f"[REMOVE] Rota {dest} perdida via {neighbor_ip}")
                        del self.table[dest]
                        changes["removed"].append(dest)
                        continue
                    
                    # Atualiza métrica se melhorar
                    if candidate_metric < cur_metric:
                        print(f"[UPDATE] Métrica melhorada para {dest}: {cur_metric} → {candidate_metric}")
                        self.table[dest] = (candidate_metric, neighbor_ip, now, cur_origin)
                        changes["updated"].append((dest, candidate_metric, neighbor_ip))
                    else:
                        # Apenas renova timestamp
                        self.table[dest] = (cur_metric, cur_next, now, cur_origin)
                else:
                    # Nova rota por outro vizinho — substitui se for melhor
                    if candidate_metric < cur_metric:
                        print(f"[UPDATE] Rota para {dest} substituída: via {cur_next} → {neighbor_ip}")
                        self.table[dest] = (candidate_metric, neighbor_ip, now, 'learned')
                        changes["updated"].append((dest, candidate_metric, neighbor_ip))
    
            # --- Verifica rotas que sumiram deste anúncio ---
            # (rotas que o vizinho anunciava antes, mas não anuncia mais)
            missing_routes = previous_adv - current_adv
            for lost in missing_routes:
                entry = self.table.get(lost)
                if entry and entry[1] == neighbor_ip:
                    print(f"[REMOVE] {lost} não mais anunciado por {neighbor_ip}")
                    del self.table[lost]
                    changes["removed"].append(lost)
        # Se houve mudanças, imprime tabela e envia atualização
        if any(changes.values()):
            self.print_table(changes)
            self.broadcast_routes(immediate=True)


    def handle_router_announcement(self, neighbor_ip: str, advertised_ip: str):
        """
        Processa uma mensagem '@<ip>' recebida de neighbor_ip,
        indicando que advertised_ip (um roteador) está ativo.
        Se advertised_ip ainda não estiver na tabela, adiciona-o com métrica 1.
        """

        now = now_ts()
        changes = {"added": [], "updated": [], "removed": []}

        with self.lock:
            print("[DEBUG] Entrando em handle_router_announcement lock")

            # Ignora anúncios do próprio roteador
            if advertised_ip == self.ip:
                print("[DEBUG] Ignorando anúncio do próprio IP.")
            else:
                # Verifica se precisa inserir ou atualizar rota
                current_entry = self.table.get(advertised_ip)
                new_entry = (1, neighbor_ip, now, 'learned')

                if current_entry is None:
                    # Nova rota descoberta
                    self.table[advertised_ip] = new_entry
                    self.neighbors.add(advertised_ip)
                    changes["added"].append((advertised_ip, 1, neighbor_ip))
                    print(f"[INFO] Novo vizinho aprendido: {advertised_ip} via {neighbor_ip}")

                elif current_entry[0] != 1 or current_entry[1] != neighbor_ip:
                    # Atualização de rota existente
                    self.table[advertised_ip] = new_entry
                    changes["updated"].append((advertised_ip, 1, neighbor_ip))
                    print(f"[INFO] Rota atualizada: {advertised_ip} via {neighbor_ip}")

            # Atualiza o timestamp do último contato com o vizinho
            self.neigh_last_heard[neighbor_ip] = now

        print("[DEBUG] Saindo do lock")

        # Caso tenha havido alterações, imprime tabela e propaga atualização
        if any(changes.values()):
            print("[DEBUG] Mudanças detectadas na tabela de rotas.")
            self.print_table(changes)
            self.broadcast_routes(immediate=True)
        else:
            print("[DEBUG] Nenhuma mudança detectada.")

        print("[DEBUG] Fim de handle_router_announcement\n")



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
        print(f"[ROUTE] Encaminhando {message} para {dest} via {next_hop} (origem {origin})")
        self.send_to(next_hop, raw_msg)

    # ------------------------
    # Thread: listener
    # ------------------------
    def listener_loop(self):
        print(f"[LISTENER] Escutando em {self.ip}:{PORT} ...")
        while not self._stop_event.is_set():
            
            if self.sock is None:
                # recria o socket
                # print("recriando o socket")
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
                # print(f"[ERROR] SOCKET ERROR :  {e}")
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
                    # print(f"checando para {n}")
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
                    # removendo apenas os learned
                    if self.table[dest][3] == "learned":
                        self.neighbors.remove(n)
                        # print(f"{self.neighbors}  ")
                    del self.table[dest]

                # limpar o registro do vizinho
                self.neigh_last_heard[n] = 0.0
                self.neigh_adv[n] = set()
                # not removing n from self.neighbors, porque arquivo roteadores.txt define os vizinhos possíveis.
                if to_del:
                    # print("teste de exclusão")
                    self.print_table({"added": [], "updated": [], "removed": to_del})
                    # notificar vizinhos imediatamente
                    # print("notificando que um saiu")
                    self.broadcast_routes(immediate=True)
                    # print("notifiquei que um saiu")
                 
            time.sleep(1.0)

    # ------------------------
    # Util: exibir tabela e diffs
    # ------------------------
    def print_table(self, changes=None):
        # print("posso entrar no self lock pelo print table?")
        with self.lock:
            # print("ENTREI no self lock pelo print table?")
            tabelosa = self.table.items()
            IP_print = self.ip
        lines = []
        lines.append("=== TABELA DE ROTEAMENTO ===")
        lines.append(f"Roteador: {IP_print}")
        # Exibição simplificada conforme enunciado (sem coluna de idade)
        lines.append(f"{'Destino':<16} {'Métrica':<7} {'Saída':<16} {'Origem':<8}")
        for dest, (metric, next_hop, ts, origin) in sorted(tabelosa):
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
