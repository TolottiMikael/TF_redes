/*

    Este código irá criar um servidor Socket que irá se comunicar com ccliente socket de um esp32 para comunicar com 

*/

//includes
#include <stdio.h> 
#include <winsock2.h>
#include <ws2tcpip.h>


//Defines
#define MAX 80 
#define BUFFER_LENGTH 1024

#define ENDERECO_SERVER_SOCKET "10.130.251.196"
#define PORT 55555 

int clearBuffer_bystring(char *string, int comprimento_string){
	for(int i = 0 ; i < comprimento_string; i++){
		string[i] = '\0';
	}
	return 0;
}

int main(){
    char buff[BUFFER_LENGTH];
    WSADATA wsa;
	printf("Inicializando a biblioteca de socket! \n");
	if(WSAStartup(MAKEWORD(2, 2), &wsa) != 0){
		printf("Falha a inciar o Winsock! \n ");
		system("PAUSE");
		return 0;
	}

    struct sockaddr_in caddr;
	struct  sockaddr_in saddr = {0};
	saddr.sin_family   = AF_INET;
	saddr.sin_addr.s_addr = inet_addr(ENDERECO_SERVER_SOCKET);
	saddr.sin_port = htons(PORT);
	


    int server = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    int client, x;
    int csize  = sizeof caddr;
	int error;

	x = 0;
    
	error = bind(server, (struct sockaddr *) &saddr, sizeof saddr);
	if(error != 0){
		printf("Falha a bindar o Socket! \n ");
		printf("Erro : %d \n ", error);
		printf("\nCould not create socket: %d \n", WSAGetLastError());
		system("PAUSE");
		return 0;
	}
	printf("Socket criado e bindado no endereco : %s : %d \n ", inet_ntoa(saddr.sin_addr), htons (saddr.sin_port));

	char flag = 1; // flag para encerramento do socket
	do{

		printf("Escutando alguma conexão! \n");
		if(listen(server, 5) != 0){
			printf("Falha a escutar clientes! \n ");
			system("PAUSE");
			return 0;
		}

		//loop para aceitar uma comunicação
		client = SOCKET_ERROR;
		while(client == SOCKET_ERROR)
    	{
			client = accept(server, (struct sockaddr *)&caddr, &csize);
   		}
		printf("Cliente conectado pelo endereco : %s : %d \n ", inet_ntoa(caddr.sin_addr), htons (caddr.sin_port)) ;

		do{
		//recebe a informação
			clearBuffer_bystring(buff, sizeof buff);
			x = recv(client, buff, sizeof (buff), 0);
			printf("User comand: %s \n",buff);


			//verifica o comando, resolve e então responde
			if( !(strncmp(buff, "/ENCERRA_SERVER", 15)) ){
				//cliente solicita o desligamento do server
				printf("cliente solicitou desligamento do server!: %s", buff);
    	    	send(client, buff, strlen(buff) , 0);
    	    	fflush(stdout);
				flag = 0;
				x=-1;
			}else if( !(strncmp(buff, "/ENCERRA", 8)) ){
				//o cliente se desconectará
				printf("cliente desconectado: %s", buff);
    	    	send(client, buff, strlen(buff) , 0);
    	    	fflush(stdout);
				x=-1;
			}
			else{
				//Nesta condição o usuário solicitou um informação
				
				/* Código de teste.
				Neste código o servidor apenas ecooa a informação recebida
				
				printf("Sua Resposta: %s", buff);
    	    	send(client, buff, strlen(buff) , 0);
    	    	fflush(stdout);
				*/

				/*
				código de teste que implementa um chat
				//inicio
	

				clearBuffer_bystring(buff, sizeof buff);
				fgets(buff, sizeof buff, stdin);
				send(client,buff, strlen(buff),0);
				fflush(stdout);

				printf("Sua Resposta: %s", buff);
    	    	send(client, buff, strlen(buff) , 0);
    	    	fflush(stdout);
				
				//fim
				*/ 

			}

		}while (x >= 0); // loop que trava a conexão com echo

	printf("ULTIMO COMANDO : %s", buff);
	}while(flag);



	WSACleanup();
    closesocket(client);
    return 0;
}