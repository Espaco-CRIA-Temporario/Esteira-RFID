#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN 10
#define RST_PIN 9

// Declarando o rfid
MFRC522 mfrc522(SS_PIN, RST_PIN);

// Cria a chave de autenticação
MFRC522::MIFARE_Key key;


// Declaração prévia
bool autenticacao(int bloco);
void escrever_dados(int bloco, String texto); 

// portas 
int buzzer = 8;

// Blocos
int blocoTipo = 2; 
int blocoDestino = 1; 

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();

  pinMode(buzzer, OUTPUT);

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

  tone(buzzer, 500);
  delay(500);
  noTone(buzzer);
  delay(1500); 
}
