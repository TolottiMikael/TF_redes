# utils.py
"""Funções utilitárias para roteamento: tempo, serialização e parsing."""
import time
from typing import Dict, Tuple

# Tipo da entrada na tabela: (metric:int, next_hop:str, last_updated_ts:float, origin:str)
RouteEntry = Tuple[int, str, float, str]

def now_ts() -> float:
    return time.time()

def serialize_table_for_neighbor(table: Dict[str, RouteEntry], neighbor_ip: str, self_ip: str) -> str:
    """Serializa tabela conforme especificação '*IP;METRIC*IP;METRIC...'.
    Aplica Split Horizon usando flag 'origin':
      - Não inclui rotas para self_ip.
      - Não anuncia rotas 'learned' cujo next_hop == neighbor_ip.
      - Rotas 'local' sempre podem ser anunciadas.
    """
    parts = []
    for dest, (metric, next_hop, _, origin) in table.items():
        if dest == self_ip:
            continue
        # if origin == 'learned' and next_hop == neighbor_ip:
        #     continue
        parts.append(f"*{dest};{metric}")
    return "".join(parts)

def parse_route_announcement(msg: str) -> Dict[str, int]:
    """Converte string '*IP;METRIC*IP;METRIC' em dict IP->metric."""
    res: Dict[str, int] = {}
    if not msg:
        return res
    chunks = [c for c in msg.split("*") if c]
    for c in chunks:
        try:
            ip, metric_s = c.split(";")
            res[ip] = int(metric_s)
        except Exception:
            continue
    return res
