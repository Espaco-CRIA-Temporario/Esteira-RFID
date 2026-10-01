#include <Servo.h>
#include <Vector.h>


// Declarando o Servo
Servo servo1;
Servo servo2;


// Configuração do Vector
const int TIPO_MAX_ITENS = 10;
String armazenamentoLista[TIPO_MAX_ITENS]; 
Vector<String> listaEsteira(armazenamentoLista);

void acaoLeitura(String dadosCard);
void andamento_esteira();

int servoAnguloInicial = 90;
int servoAnguloFinal = -90;

// Portas
int pinServo1 = 6;
int pinServo2 = 5;
int pinMotor = 7;
int pinTrig = A0;
int pinEcho = A1;
int pinDados = 5;

// Blocos
int blocoTipo = 2; 
int blocoDestino = 1; 

void setup() {
  Serial.begin(115200);
  SPI.begin();

  pinMode(buzzer, OUTPUT);
  pinMode(pinMotor, OUTPUT);
  pinMode(pinTrig, OUTPUT);
  pinMode(pinEcho, INPUT);

  servo1.attach(pinServo1);
  servo2.attach(pinServo2);

  servo1.write(servoAnguloInicial); 
  servo2.write(servoAnguloInicial);

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
  int item = analogRead(pinDados);

  if (item == 1) {
    acaoLeitura("P1");
  } else if (item == 2) {
    acaoLeitura("P2");
  }
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