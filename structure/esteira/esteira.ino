#include <Stepper.h>

// ===== CONFIGURACOES DO MOTOR =====
// Motor 28BYJ-48 (5V) com driver ULN2003
// IN1 = 8 | IN2 = 9 | IN3 = 10 | IN4 = 11
#define IN1 8
#define IN2 9
#define IN3 10
#define IN4 11

// Passos por volta completa do eixo (28BYJ-48 = 2048 no modo full-step)
const int PASSOS_POR_VOLTA = 2048;

// Velocidade final em RPM.
// O limite pratico do 28BYJ-48 em 5V e ~15 a 17 RPM.
// Se o motor so vibrar ou travar, diminua este valor.
const int VELOCIDADE_RPM = 17;

// Aceleracao gradual: comeca devagar e sobe ate VELOCIDADE_RPM
const int RPM_INICIAL = 6;
const int PASSOS_POR_AUMENTO = 60;   // a cada N passos sobe 1 RPM

// false = depois do primeiro comando gira para sempre
// true  = cada novo comando "MOTOR" liga/desliga o motor
const bool ALTERNAR_COM_NOVO_COMANDO = false;

// ===== CONFIGURACOES DO SENSOR HC-SR04 =====
#define TRIG A0
#define ECHO A1

// Distancia (cm) em que o objeto faz o motor parar
const int DISTANCIA_PARADA_CM = 10;

// Intervalo entre medicoes (ms)
const unsigned long INTERVALO_MEDICAO = 50;

// Quantas medicoes seguidas precisam detectar o objeto (evita falso positivo)
const uint8_t LEITURAS_PARA_PARAR = 2;

// false = depois de parar, so volta a girar com um novo comando "MOTOR"
// true  = volta a girar sozinho quando o objeto sair da frente do sensor
const bool RETOMAR_QUANDO_LIBERAR = false;

// A ordem dos pinos e IN1, IN3, IN2, IN4 para a sequencia correta da bobina
Stepper motor(PASSOS_POR_VOLTA, IN1, IN3, IN2, IN4);

bool girando = false;
int rpmAtual = RPM_INICIAL;
int contaPassos = 0;
bool objetoDetectado = false;
uint8_t contaDeteccoes = 0;
unsigned long ultimaMedicao = 0;

// ===== RECEPCAO SERIAL =====
char buffer[16];
uint8_t tamanho = 0;

// Desliga as bobinas para o motor e o driver nao esquentarem parado
void desligarBobinas() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

// Retorna true se houver objeto a DISTANCIA_PARADA_CM ou menos
bool objetoPerto() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  // Timeout curto para o motor nao ficar travado esperando o eco
  unsigned long timeout = (unsigned long)DISTANCIA_PARADA_CM * 58UL + 500UL;
  unsigned long duracao = pulseIn(ECHO, HIGH, timeout);

  if (duracao == 0) return false;   // nada dentro do alcance
  return (duracao / 58UL) <= DISTANCIA_PARADA_CM;
}

// Mede de tempos em tempos e para/retoma o motor
void verificarSensor() {
  if (millis() - ultimaMedicao < INTERVALO_MEDICAO) return;
  ultimaMedicao = millis();

  if (objetoPerto()) {
    if (contaDeteccoes < LEITURAS_PARA_PARAR) contaDeteccoes++;
  } else {
    contaDeteccoes = 0;
  }

  bool detectado = (contaDeteccoes >= LEITURAS_PARA_PARAR);

  if (detectado && girando) {
    girando = false;            // para o motor
    desligarBobinas();
  }
  else if (!detectado && objetoDetectado && RETOMAR_QUANDO_LIBERAR) {
    // objeto saiu: retoma o giro
    girando = true;
    rpmAtual = RPM_INICIAL;
    contaPassos = 0;
    motor.setSpeed(rpmAtual);
  }

  objetoDetectado = detectado;
}

void tratarComando() {
  if (!girando) {
    girando = true;
    rpmAtual = RPM_INICIAL;      // sempre arranca com a rampa
    contaPassos = 0;
    motor.setSpeed(rpmAtual);
  } else if (ALTERNAR_COM_NOVO_COMANDO) {
    girando = false;
    desligarBobinas();
  }
}

// Le o Serial sem travar o motor
void lerSerial() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      buffer[tamanho] = '\0';

      // Ignora qualquer linha que nao seja exatamente "MOTOR"
      if (strcmp(buffer, "MOTOR") == 0) {
        tratarComando();
      }
      tamanho = 0;
    }
    else if (c != '\r') {
      if (tamanho < sizeof(buffer) - 1) buffer[tamanho++] = c;
      else tamanho = 0;  // linha longa demais (texto de debug): descarta
    }
  }
}

void setup() {
  // Mesma velocidade do outro Arduino
  Serial.begin(9600);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  digitalWrite(TRIG, LOW);

  motor.setSpeed(RPM_INICIAL);
  desligarBobinas();
}

void loop() {
  lerSerial();
  verificarSensor();

  // Gira um passo por vez para continuar escutando o Serial
  // OBS: este Arduino NAO imprime nada no Serial
  if (girando) {
    motor.step(1);

    // Rampa de aceleracao ate a velocidade final
    if (rpmAtual < VELOCIDADE_RPM && ++contaPassos >= PASSOS_POR_AUMENTO) {
      contaPassos = 0;
      rpmAtual++;
      motor.setSpeed(rpmAtual);
    }
  }
}
