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
void ler_dados(int bloco);

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

  Serial.println("__MODO DE LEITURA___");
  Serial.println("\n\nInsira o cartão para ser lido...");
}

void loop() {
  // Modo de Leitura limpo usando o loop principal do Arduino


  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    ler_dados(blocoTipo);
    
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    delay(1500); 
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

void ler_dados(int bloco){
  String dadosBloco = "";
  
  Serial.println("\nCartão identificado...");

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

  Serial.println("informaçao no bloco");
  Serial.println(bloco);
  
  for (uint8_t i = 0; i < 16; i++) {
    dadosBloco += (char)blocoBuffer[i];
  }

  dadosBloco.trim();
  Serial.println(dadosBloco);

  tone(buzzer, 500);
  delay(100);
  noTone(buzzer);
}
