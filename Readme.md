Instruções de execução

Copie router.py, main.py e roteadores.txt para cada máquina.

Ajuste roteadores.txt com os IPs dos vizinhos daquela máquina.

Execute em cada máquina:
'''
python main.py
'''

Ao iniciar, cada roteador:

- anuncia-se com @<meu_ip> para os vizinhos;

- envia sua tabela a cada 10s;

- exibe tabela ao receber mudanças;

- detecta vizinho inativo após 15s sem anúncios.

Para enviar mensagem de texto via CLI: digite IP_destino;mensagem (ex.: 192.168.1.12;Oi tudo bem?).