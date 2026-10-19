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
// Se quiser testar mais rapido, suba de 1 em 1 (16, 17...).
// Se o motor so vibrar ou travar, diminua este valor.
const int VELOCIDADE_RPM = 17;

// Aceleracao gradual: comeca devagar e sobe ate VELOCIDADE_RPM,
// o que aumenta a chance de o motor aguentar a velocidade alta.
const int RPM_INICIAL = 6;
const int PASSOS_POR_AUMENTO = 60;   // a cada N passos sobe 1 RPM

// false = depois do primeiro comando gira para sempre
// true  = cada novo comando "MOTOR" liga/desliga o motor
const bool ALTERNAR_COM_NOVO_COMANDO = false;

// A ordem dos pinos e IN1, IN3, IN2, IN4 para a sequencia correta da bobina
Stepper motor(PASSOS_POR_VOLTA, IN1, IN3, IN2, IN4);

bool girando = false;
int rpmAtual = RPM_INICIAL;
int contaPassos = 0;

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

  motor.setSpeed(RPM_INICIAL);
  desligarBobinas();
}

void loop() {
  lerSerial();

  // Gira um passo por vez para continuar escutando o Serial
  // OBS: este Arduino NAO imprime nada no Serial, para nao
  // enviar lixo para o RX do Arduino leitor.
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
