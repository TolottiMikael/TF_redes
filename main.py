"""Orquestra servidor e cliente UDP básicos.

Executa o servidor UDP em uma thread e permite enviar mensagens
interativas para ele usando o mesmo processo.

Porta padrão: 5000
IP dinâmico obtido via socket.gethostbyname(socket.gethostname()).

Comandos de saída: sair / exit / quit
"""

import socket
import threading
import time

PORT = 5000


def get_dynamic_ip() -> str:
	# Em alguns ambientes gethostname pode retornar um nome que resolve para 127.0.0.1.
	# Caso isso ocorra e você precise do IP local da interface, pode adaptar.
	return socket.gethostbyname(socket.gethostname())


def server_loop(ip: str, port: int, stop_event: threading.Event):
	"""Loop do servidor UDP: recebe e imprime mensagens até stop_event ser sinalizado."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind((ip, port))
	print(f'[SERVIDOR] UDP ativo em {ip}:{port}')
	sock.settimeout(0.5)
	while not stop_event.is_set():
		try:
			data, addr = sock.recvfrom(1024)
		except socket.timeout:
			continue
		except OSError:
			break
		else:
			print(f'[SERVIDOR] Mensagem de {addr}: {data.decode(errors="replace")}')
	sock.close()
	print('[SERVIDOR] Encerrado.')


def send_message(ip: str, port: int, message: str) -> None:
	"""Envia mensagem UDP única ao servidor."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		sock.sendto(message.encode('utf-8'), (ip, port))
	finally:
		sock.close()


def main():
	ip = get_dynamic_ip()
	stop_event = threading.Event()

	# Inicia servidor em thread
	t = threading.Thread(target=server_loop, args=(ip, PORT, stop_event), daemon=True)
	t.start()

	print(f'[CLIENTE] Enviando para {ip}:{PORT}')
	print('Digite mensagens. Use "sair" para terminar.')

	try:
		while True:
			msg = input('Mensagem: ').strip()
			if not msg:
				continue
			if msg.lower() in ('sair'):
				break
			send_message(ip, PORT, msg)
			print('[CLIENTE] > enviada')
	except KeyboardInterrupt:
		print('\n[CLIENTE] Interrompido pelo usuário.')
	finally:
		print('[MAIN] Encerrando servidor...')
		stop_event.set()
		# Aguarda a thread do servidor terminar
		t.join(timeout=2)
		print('[MAIN] Fim.')


if __name__ == '__main__':
	main()
