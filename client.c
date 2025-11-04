/*

    Este código irá criar um servidor Socket que irá se comunicar com ccliente socket de um esp32 para comunicar com 

*/

//includes
#include <stdio.h> 
#include <winsock2.h>
#include <ws2tcpip.h>


//Defines
#define MAX 80 
#define BUFFER_LENGTH 128
#define PORT 55555 
#define ENDERECO_SERVER_SOCKET "10.130.251.196"

int clearBuffer_bystring(char *string, int comprimento_string){
	for(int i = 0 ; i < comprimento_string; i++){
		string[i] = '\0';
	}
	return 0;
}


int main(){
    WSADATA wsa;

	char msg[BUFFER_LENGTH] = "digite o que enviar";
	msg[19] = '\0';
	
	printf("Inicializando a biblioteca de socket! \n");
	if(WSAStartup(MAKEWORD(2, 2), &wsa) != 0){
		printf("Falha a inciar o Winsock! \n ");
		system("PAUSE");
		return 0;
	}

    int meuSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_UDP);

	struct sockaddr_in caddr;
	struct  sockaddr_in saddr = {0};
	saddr.sin_family   = AF_INET;
	//saddr.sin_addr.s_addr = inet_addr(ENDERECO_SERVER_SOCKET);
	inet_pton(AF_INET, ENDERECO_SERVER_SOCKET, &saddr.sin_addr);
	saddr.sin_port = htons(PORT);

	printf("conectando no server : \n");
	printf(" %s : %d \n ", inet_ntoa(saddr.sin_addr), htons (saddr.sin_port));
	if (connect(meuSocket, (struct sockaddr*) &saddr, sizeof saddr) != 0)
	{
	    printf("Connection failed. error: %s\n",WSAGetLastError());
    	getchar();
    	return 1;
	}
	printf("Conexão ok digite o que enviar.\n digite /ENCERRA para sair \n ");
    
	do{
		//ENVIA VALORES AO SERVIDOR
		printf("\nYour command: " );
		clearBuffer_bystring(msg, sizeof msg);
		fgets(msg, sizeof msg, stdin);
		send(meuSocket,msg, strlen(msg),0);
		fflush(stdout);

		//RECEBE A RESPOSTA DO SERVIDOR
		clearBuffer_bystring(msg, sizeof msg);
		recv(meuSocket, msg, sizeof(msg),0);
		printf("\nServer response : %s",msg);

	}while(strncmp(msg, "/ENCERRA", 8));
	
	WSACleanup();
	closesocket(meuSocket);
    return 0;
}