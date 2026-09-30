#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
#include <Vector.h>

#define SS_PIN 10
#define RST_PIN 9

// Declarando o rfid
MFRC522 mfrc522(SS_PIN, RST_PIN);

// Declarando o Servo
Servo servo1;
Servo servo2;

// Cria a chave de autenticação
MFRC522::MIFARE_Key key;

// Configuração do Vector
const int TIPO_MAX_ITENS = 10;
String armazenamentoLista[TIPO_MAX_ITENS]; 
Vector<String> listaEsteira(armazenamentoLista);

// Declaração prévia
bool autenticacao(int bloco);
void escrever_dados(int bloco, String texto); 
void ler_dados(int bloco);
void acaoLeitura(String dadosCard);
void andamento_esteira();

// variáveis
int modo = 0; // 0 = leitura; 1 = gravação
int servoAnguloInicial = 90;
int servoAnguloFinal = -90;

// portas 
int buzzer = 8;
int pinServo1 = 6;
int pinServo2 = 5;
int pinMotor = 7;
int pinTrig = A0;
int pinEcho = A1;

// Blocos
int blocoTipo = 2; 
int blocoDestino = 1; 

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();

  pinMode(buzzer, OUTPUT);
  pinMode(pinMotor, OUTPUT);
  pinMode(pinTrig, OUTPUT);
  pinMode(pinEcho, INPUT);

  servo1.attach(pinServo1);
  servo2.attach(pinServo2);

  servo1.write(servoAnguloInicial); 
  servo2.write(servoAnguloInicial);

  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }
  
  Serial.println(F("Sistema iniciado."));

  tone(buzzer, 1000);
  delay(200);
  noTone(buzzer);
  delay(200);
  tone(buzzer, 1000);
  delay(200);
  noTone(buzzer);
}

void loop() {
  if (modo == 1) {
    Serial.println(F("\n--- MODO DE GRAVACAO ---"));
    Serial.println(F("Digite o texto (max 16 caracteres) e pressione Enter:"));
    
    while (Serial.available() == 0) {
      // Aguarda entrada
    }
    
    String textoDigitado = Serial.readStringUntil('\n'); 
    textoDigitado.trim(); 
    textoDigitado.toUpperCase(); 

    Serial.print(F("Texto capturado: "));
    Serial.println(textoDigitado);
    Serial.println(F("Aproxime o cartao para gravar..."));

    while (true) {
      if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
        escrever_dados(blocoTipo, textoDigitado);
        break; 
      }
    }
  } 
  else {
    // Modo de Leitura limpo usando o loop principal do Arduino
    if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
      ler_dados(blocoTipo);
      
      mfrc522.PICC_HaltA();
      mfrc522.PCD_StopCrypto1();
      delay(1500); 
    }
  }

  andamento_esteira();
}

bool autenticacao(int bloco){
  MFRC522::StatusCode status; 
  status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, bloco, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    return false;    
  }
  return true;
}

void escrever_dados(int bloco, String texto){
  byte dadosParaGravar[16] = {0}; 
  for (int i = 0; i < 16; i++) {
    if (i < texto.length()) {
      dadosParaGravar[i] = texto[i];
    } else {
      dadosParaGravar[i] = ' ';
    }
  }

  if (!autenticacao(bloco)) return;

  MFRC522::StatusCode status = mfrc522.MIFARE_Write(bloco, dadosParaGravar, 16);
  if (status != MFRC522::STATUS_OK) {
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    return;
  }
  
  Serial.println(F("Dados gravados com SUCESSO! Retire o cartao."));
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(2000); 
}

void ler_dados(int bloco){
  String dadosBloco = "";

  if (!autenticacao(bloco)) {
    return;
  }

  byte blocoBuffer[18];
  byte tamanhoBuffer = sizeof(blocoBuffer);

  MFRC522::StatusCode status = mfrc522.MIFARE_Read(bloco, blocoBuffer, &tamanhoBuffer);
  if (status != MFRC522::STATUS_OK) {
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    return;
  }

  for (uint8_t i = 0; i < 16; i++) {
    dadosBloco += (char)blocoBuffer[i];
  }

  dadosBloco.trim();
  
  tone(buzzer, 500);
  delay(100);
  noTone(buzzer);

  acaoLeitura(dadosBloco);
}

void acaoLeitura(String dados){
  String dadosBloco = dados;
  dadosBloco.trim(); 

  if (!listaEsteira.full()) {
    listaEsteira.push_back(dadosBloco);
    Serial.print(F("Produto Lido: ["));
    Serial.print(listaEsteira.back());
    Serial.println(F("]"));
  } else {
    Serial.println(F("Aviso: Lista da esteira cheia!"));
  }
} 

void andamento_esteira() {
  // Se a lista estiver vazia, desliga o motor e para por aqui
  if (listaEsteira.empty()) {
      digitalWrite(pinMotor, LOW);
      return;
  } 

  // Se tem itens, liga o motor para movimentar a esteira
  digitalWrite(pinMotor, HIGH);

  // Pega o primeiro item da fila (FIFO)
  String itemAtual = listaEsteira[0];

  // Leitura do sensor de proximidade (Ultrassônico)
  digitalWrite(pinTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(pinTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(pinTrig, LOW);

  long duracao = pulseIn(pinEcho, HIGH);
  int distanciaCm = duracao * 0.0343 / 2; // Corrigido para 'distanciaCm'

  // Se o objeto chegar perto do sensor (<= 3 cm)
  if (distanciaCm > 0 && distanciaCm <= 3) {
    Serial.print(F("Objeto detectado! Processando: "));
    Serial.println(itemAtual);

    if (itemAtual == "P1") {
      digitalWrite(pinMotor, LOW); // Para o motor para o servo atuar
      servo1.write(servoAnguloFinal);
      delay(1000);
      servo1.write(servoAnguloInicial);
      delay(500);
    } 
    else if (itemAtual == "P2") {
      digitalWrite(pinMotor, LOW);
      servo2.write(servoAnguloFinal);
      delay(1000);
      servo2.write(servoAnguloInicial);
      delay(500);
    }

    // Remove o item da lista após ser processado com sucesso
    listaEsteira.remove(0);
  }
}