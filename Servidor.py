

import socket

def create_server_udp(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ip, port))
    return sock

if __name__ == '__main__':
    ip = socket.gethostbyname(socket.gethostname())
    port = 5000
    server = create_server_udp(ip, port)
    print(f'Server UDP/IP running on {ip}:{port}')
    while True:
        data, addr = server.recvfrom(1024)
        print(f'Received message from {addr}: {data}')
