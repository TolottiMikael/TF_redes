import socket

def send_message(ip: str, port: int, message: str) -> None:
	"""Envia uma única mensagem UDP ao servidor."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		sock.sendto(message.encode('utf-8'), (ip, port))
	finally:
		sock.close()


if __name__ == '__main__':
	# Obtém IP e porta (usa valores padrão se usuário apenas pressionar Enter)
	ip_input = input('IP do servidor (Enter para local): ').strip()
	ip = ip_input or socket.gethostbyname(socket.gethostname())

	port_input = input('Porta do servidor (Enter para 5000): ').strip()
	port = int(port_input) if port_input else 5000

	print(f'Cliente UDP conectado a {ip}:{port}')
	print('Digite mensagens para enviar. Use "sair" para encerrar.')

	while True:
		msg = input('Mensagem: ').strip()
		if not msg:
			continue
		if msg.lower() in ('sair'):
			break
		send_message(ip, port, msg)
		print('> enviada')

	print('Cliente finalizado.')
