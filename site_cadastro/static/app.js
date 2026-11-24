// Pequenos comportamentos do site. Sem bibliotecas.

// 1) Quando o leitor le uma tag nova (modo CADASTRO), preenche o campo de UID sozinho.
(function () {
  var campo = document.getElementById('campo-uid');
  var rotulo = document.getElementById('ultima-uid');
  if (!campo && !rotulo) return;
  var ultima = campo ? Number(campo.dataset.seq || 0) : null;

  setInterval(function () {
    fetch('/api/ultima-leitura').then(function (r) { return r.json(); }).then(function (r) {
      if (ultima === null) ultima = r.seq;           // pagina sem campo: so mostra a ultima tag
      if (r.seq > ultima || (campo === null && rotulo)) {
        ultima = r.seq;
        if (campo) campo.value = r.uid;
        if (rotulo && r.uid) rotulo.textContent = r.uid;
      }
    }).catch(function () {});
  }, 1000);
})();

// 2) Atualiza sozinho (a cada 4 s) os blocos marcados com data-auto, sem recarregar a pagina
//    e sem atrapalhar quem esta digitando ou escolhendo algo dentro do bloco.
setInterval(function () {
  var blocos = document.querySelectorAll('[data-auto]');
  if (!blocos.length) return;
  fetch(location.href).then(function (r) { return r.text(); }).then(function (html) {
    var novo = new DOMParser().parseFromString(html, 'text/html');
    blocos.forEach(function (bloco) {
      var outro = bloco.id && novo.getElementById(bloco.id);
      if (outro && !bloco.contains(document.activeElement) && !bloco.dataset.sujo) bloco.innerHTML = outro.innerHTML;
    });
  }).catch(function () {});
}, 4000);

// Se o usuario mudou algum campo dentro de um bloco, esse bloco para de se atualizar (nao perde a escolha).
document.addEventListener('change', function (e) {
  var bloco = e.target.closest ? e.target.closest('[data-auto]') : null;
  if (bloco) bloco.dataset.sujo = '1';
});

// 3) Pede confirmacao antes de acoes marcadas com data-confirmar="texto" (ex.: excluir).
document.addEventListener('click', function (e) {
  var alvo = e.target.closest ? e.target.closest('[data-confirmar]') : null;
  if (alvo && !confirm(alvo.getAttribute('data-confirmar'))) e.preventDefault();
});
