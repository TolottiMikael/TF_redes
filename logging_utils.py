# logging_utils.py
import sys
import threading
from typing import Dict, Tuple
from utils import now_ts

print_lock = threading.Lock()

RouteEntry = Tuple[int, str, float, str]

def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)
        sys.stdout.flush()

def format_table(table: Dict[str, RouteEntry], self_ip: str) -> str:
    lines = []
    lines.append("=== TABELA DE ROTEAMENTO ===")
    lines.append(f"Roteador: {self_ip}")
    lines.append(f"{'Destino':<16} {'Métrica':<7} {'Saída':<16} {'Origem':<8}")
    for dest, (metric, next_hop, ts, origin) in sorted(table.items()):
        lines.append(f"{dest:<16} {metric:<7} {next_hop:<16} {origin:<8}")
    lines.append("===========================")
    return "\n".join(lines)
