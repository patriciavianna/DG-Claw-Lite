#!/usr/bin/env node
/**
 * Gerador de carrossel do DG Claw Lite.
 *
 * Desenha cards 1080x1350 (4:5) na identidade visual do dono e exporta PNG,
 * prontos pra postar. NAO usa IA de imagem: modelo de imagem erra texto, e card
 * de carrossel e quase so tipografia. Aqui o texto e texto de verdade — sai
 * nitido, na cor exata, de graça.
 *
 * Uso:
 *     node gerar.js <spec.json> [pasta-de-saida]
 *
 * Precisa de: Node (ja vem com o Claude Code) e um navegador da familia Chrome
 * (Edge serve, e ja vem no Windows). Fontes sao opcionais — veja o README.
 *
 * ---------------------------------------------------------------------------
 * ARMADILHAS JA RESOLVIDAS AQUI. Nao reintroduza:
 *
 * 1. ENTRELINHA. Fonte condensada em CAIXA ALTA com acento (Ê, Ã, É, Ô) tem o
 *    diacritico BEM acima da altura de maiuscula. Entrelinha < 1.18 faz o acento
 *    da linha de baixo colidir com a linha de cima. Por isso LH_TITULO = 1.2.
 *
 * 2. RODAPE. Rodape em position:absolute era empurrado pra fora do card quando
 *    o conteudo crescia, e a assinatura sumia. Agora o card e um flex column
 *    (topo / meio flex:1 / rodape) e o rodape nunca escapa.
 *
 * 3. CAMADAS. A regra `.card>*{z-index:1}` precisa vir ANTES de
 *    `.card>.bg{z-index:0}`. Invertidas, a foto cobre o card inteiro e some com
 *    o texto (mesma especificidade: quem vem depois ganha).
 *
 * 4. PROPORCAO DA FOTO. Sempre `width:auto` com altura fixa. Definir os dois
 *    deforma a pessoa — ela sai achatada ou esticada.
 *
 * 5. FUNDO DA FOTO. Foto de estudio quase nunca tem o mesmo preto do card, e a
 *    diferença aparece como um retangulo em volta da pessoa. Resolvido com
 *    mascara esfumada (mask-image) + leve aumento de contraste, tudo em CSS.
 * ---------------------------------------------------------------------------
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const os = require('os');

const L = 1080, A = 1350;           // 4:5, o formato de feed do Instagram
const LH_TITULO = 1.2;              // ver armadilha 1
const MARGEM = 88;

// ---------------------------------------------------------------------------
// Navegador
// ---------------------------------------------------------------------------
function acharNavegador() {
  if (process.env.CARROSSEL_NAVEGADOR) return process.env.CARROSSEL_NAVEGADOR;
  const candidatos = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) {
    const base = process.env.PLAYWRIGHT_BROWSERS_PATH;
    try {
      for (const d of fs.readdirSync(base).filter((x) => x.startsWith('chromium-'))) {
        candidatos.push(path.join(base, d, 'chrome-linux', 'chrome'));
        candidatos.push(path.join(base, d, 'chrome-win', 'chrome.exe'));
      }
    } catch { /* segue pros proximos candidatos */ }
  }
  if (process.platform === 'win32') {
    const pf = [process.env['PROGRAMFILES'], process.env['PROGRAMFILES(X86)'],
                process.env['LOCALAPPDATA']].filter(Boolean);
    for (const p of pf) {
      candidatos.push(path.join(p, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
      candidatos.push(path.join(p, 'Google', 'Chrome', 'Application', 'chrome.exe'));
    }
  } else if (process.platform === 'darwin') {
    candidatos.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    candidatos.push('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  } else {
    candidatos.push('/usr/bin/chromium', '/usr/bin/chromium-browser',
                    '/usr/bin/google-chrome', '/usr/bin/microsoft-edge');
  }
  for (const c of candidatos) { if (c && fs.existsSync(c)) return c; }
  throw new Error(
    'Nao achei um navegador Chrome/Edge/Chromium pra exportar as imagens.\n' +
    'No Windows o Edge ja vem instalado — se mesmo assim falhar, aponte o\n' +
    'caminho na variavel CARROSSEL_NAVEGADOR.');
}

// ---------------------------------------------------------------------------
// Fontes (opcionais)
// ---------------------------------------------------------------------------
// Sem as fontes o gerador NAO quebra: cai numa pilha do sistema e avisa. Pra ter
// o visual condensado editorial: npm install @fontsource/anton @fontsource/archivo
function carregarFontes(dir) {
  const achar = (rel) => {
    for (const base of [dir, __dirname, process.cwd()]) {
      const p = path.join(base, 'node_modules', rel);
      if (fs.existsSync(p)) return p;
    }
    return null;
  };
  const arqs = {
    titulo: achar('@fontsource/anton/files/anton-latin-400-normal.woff2'),
    corpo4: achar('@fontsource/archivo/files/archivo-latin-400-normal.woff2'),
    corpo7: achar('@fontsource/archivo/files/archivo-latin-700-normal.woff2'),
  };
  if (!arqs.titulo || !arqs.corpo4 || !arqs.corpo7) {
    console.warn('[aviso] Fontes Anton/Archivo nao encontradas — usando as do sistema.');
    console.warn('        Pra ficar igual a identidade, rode nesta pasta:');
    console.warn('        npm install @fontsource/anton @fontsource/archivo');
    return { css: '', titulo: 'Impact, "Arial Narrow", sans-serif', corpo: 'Arial, sans-serif' };
  }
  const b64 = (p) => fs.readFileSync(p).toString('base64');
  return {
    css: `
@font-face{font-family:'TituloCarrossel';src:url(data:font/woff2;base64,${b64(arqs.titulo)}) format('woff2')}
@font-face{font-family:'CorpoCarrossel';src:url(data:font/woff2;base64,${b64(arqs.corpo4)}) format('woff2');font-weight:400}
@font-face{font-family:'CorpoCarrossel';src:url(data:font/woff2;base64,${b64(arqs.corpo7)}) format('woff2');font-weight:700}`,
    titulo: "'TituloCarrossel', Impact, sans-serif",
    corpo: "'CorpoCarrossel', Arial, sans-serif",
  };
}

const dataURI = (p) => {
  const ext = path.extname(p).slice(1).toLowerCase();
  const tipo = ext === 'jpg' ? 'jpeg' : ext;
  return `data:image/${tipo};base64,${fs.readFileSync(p).toString('base64')}`;
};

const esc = (s) => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// O texto pode trazer <br> de proposito; preservo so essa tag.
const txt = (s) => esc(s).replace(/&lt;br\s*\/?&gt;/g, '<br>');

// ---------------------------------------------------------------------------
// CSS
// ---------------------------------------------------------------------------
function montarCSS(m, f) {
  return `${f.css}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:${L}px;height:${A}px;overflow:hidden}
body{background:${m.preto};color:${m.branco};font-family:${f.corpo};
  -webkit-font-smoothing:antialiased}
.card{width:${L}px;height:${A}px;padding:${MARGEM}px;display:flex;
  flex-direction:column;position:relative;overflow:hidden}
/* Camadas — ver armadilha 3: esta ordem nao pode ser invertida */
.card>*{position:relative;z-index:1}
.card>.bg{position:absolute;inset:0;z-index:0;pointer-events:none}
.bg img{position:absolute;width:auto}          /* armadilha 4 */
.veu{position:absolute;inset:0}
.head{display:flex;justify-content:space-between;align-items:flex-start}
.mid{flex:1;display:flex;flex-direction:column;justify-content:center}
.foot{display:flex;justify-content:space-between;align-items:flex-end}
.eyebrow{font-size:20px;letter-spacing:.34em;text-transform:uppercase;color:${m.cinza}}
.rule{width:92px;height:5px;background:${m.destaque};border:0;margin-top:30px}
.thin{height:1px;background:#262626;border:0;margin-bottom:34px}
.sig{font-size:19px;letter-spacing:.26em;text-transform:uppercase;color:${m.cinza};line-height:1}
.num{font-family:${f.titulo};font-size:28px;color:#333;letter-spacing:.08em;line-height:1}
.kicker{font-size:32px;line-height:1.45;color:#D8D8D8}
h1{font-family:${f.titulo};text-transform:uppercase;line-height:${LH_TITULO};
  letter-spacing:-.005em}                      /* armadilha 1 */
.am{color:${m.destaque}}
.label{font-size:22px;letter-spacing:.32em;margin-bottom:24px}
.logo{display:block;width:auto;opacity:1}
/* numero gigante atras do conteudo: preenche o vazio sem competir com o texto */
.fantasma{position:absolute;right:-26px;top:34px;font-size:400px;line-height:.82;
  color:#1C1C1C;letter-spacing:-.05em;z-index:0;font-family:${f.titulo}}
/* caixa de destaque: o realce mais forte da marca, igual a peca de referencia */
.caixa{display:inline-block;background:${m.destaque};color:${m.preto};
  padding:2px 18px 10px;line-height:${LH_TITULO}}
/* .col so existe quando ha foto: a coluna de texto estreita pra nao invadir a
   area da pessoa. Por isso o texto de apoio encolhe junto — senao ele quebra
   em linhas orfas ("...ainda / acha / que..."). */
.col{max-width:500px}
.col .kicker{font-size:29px}`;
}

// Foto: dois modos, porque o fundo da foto original decide qual funciona.
//
//   "recorte"  — pra foto com fundo ESCURO (estudio preto, ou ja recortada em
//                PNG transparente). Mascara esfumada + contraste dissolvem o
//                resto do fundo no preto do card. Ver armadilha 5.
//
//   "sangria"  — pra foto com fundo CLARO (estudio cinza, ambiente). Nao tenta
//                recortar: a foto sangra ate a borda do card e leva um
//                escurecimento forte, virando um degrade proposital. Recorte
//                automatico de fundo claro quase sempre come o cabelo e a pele
//                na sombra, que ficam perto demais do cinza — o resultado
//                parece defeito. Sangria sempre parece intencional.
function blocoFoto(m, cfg, arquivo) {
  const foto = arquivo || m.foto;
  if (!foto) return '';
  const modo = cfg.modo || 'recorte';

  if (modo === 'bloco') {
    // Bloco de foto num canto do card: preenche o vazio que sobra embaixo sem
    // roubar a leitura do texto. Sangra pras bordas mais proximas, entao nao
    // cria moldura; o degrade dissolve os dois lados que encostam no conteudo.
    const larg = cfg.largura || 520, alt = cfg.altura || 460;
    return `<div class="bg">
      <img src="${dataURI(foto)}" style="right:0;bottom:0;width:${larg}px;height:${alt}px;
        object-fit:cover;object-position:${cfg.foco || 'center'};
        filter:brightness(${cfg.brilho || .9}) contrast(1.08)
          grayscale(${cfg.cinza === undefined ? .88 : cfg.cinza})
        ;-webkit-mask-image:linear-gradient(90deg,transparent 0%,#000 46%),linear-gradient(0deg,#000 40%,transparent 96%)
        ;-webkit-mask-composite:source-in
        ;mask-image:linear-gradient(90deg,transparent 0%,#000 46%),linear-gradient(0deg,#000 40%,transparent 96%)
        ;mask-composite:intersect">
    </div>`;
  }

  if (modo === 'sangria') {
    const larg = cfg.largura || 640;
    // Aqui largura E altura sao definidas de proposito — a excecao da armadilha
    // 4. Quem impede a deformacao e o `object-fit:cover`: ele preenche a faixa
    // recortando a sobra, nunca esticando. Sem a altura de 100% a foto flutua
    // como um retangulo colado no meio do card, com bordas visiveis em cima e
    // embaixo — que e justamente o que a sangria existe pra evitar.
    return `<div class="bg">
      <img src="${dataURI(foto)}" style="right:0;top:0;height:100%;width:${larg}px;
        object-fit:cover;object-position:${cfg.foco || 'center'};
        filter:brightness(${cfg.brilho || .58}) contrast(1.2) saturate(.92)">
      <div class="veu" style="background:linear-gradient(90deg,${m.preto} ${(cfg.corte || 42) - 10}%,
        rgba(0,0,0,.90) ${cfg.corte || 42}%,rgba(0,0,0,.45) ${(cfg.corte || 42) + 22}%,
        rgba(0,0,0,.18) 100%)"></div>
    </div>`;
  }

  const alt = cfg.altura || 1035;
  const masc = 'linear-gradient(90deg,transparent 0%,rgba(0,0,0,.35) 18%,#000 45%),' +
               'linear-gradient(0deg,#000 80%,transparent 99%),' +
               'linear-gradient(180deg,transparent 0%,#000 16%)';
  return `<div class="bg">
    <img src="${dataURI(foto)}" style="right:${cfg.direita || 0}px;bottom:0;
      height:${alt}px;opacity:${cfg.opacidade || .95};
      filter:contrast(1.12) brightness(.94);
      -webkit-mask-image:${masc};-webkit-mask-composite:source-in;
      mask-image:${masc};mask-composite:intersect">
    <div class="veu" style="background:linear-gradient(95deg,${m.preto} 40%,
      rgba(0,0,0,.35) 55%,transparent 72%)"></div>
  </div>`;
}

const blocoLogo = (m, altura) =>
  m.logo ? `<img class="logo" src="${dataURI(m.logo)}" style="height:${altura}px">` : '';

// ---------------------------------------------------------------------------
// Tipos de card
// ---------------------------------------------------------------------------
const moldura = (topo, meio, rodapeEsq, rodapeDir, fundo, topoDir) => `<div class="card">
  ${fundo || ''}
  <div class="head">
    <div><div class="eyebrow">${txt(topo || '')}</div><hr class="rule"></div>
    ${topoDir || ''}
  </div>
  <div class="mid">${meio}</div>
  <div class="foot">
    <div class="sig">${rodapeEsq || ''}</div>
    <div class="num">${txt(rodapeDir || '')}</div>
  </div>
</div>`;

// destacarUltima: 'caixa' pinta o fundo (o realce mais forte, como na peca de
// referencia da marca); true so troca a cor da letra.
const linhas = (arr, destacarUltima) => arr.map((l, i) => {
  if (!destacarUltima || i !== arr.length - 1) return txt(l);
  return destacarUltima === 'caixa'
    ? `<span class="caixa">${txt(l)}</span>`
    : `<span class="am">${txt(l)}</span>`;
}).join('<br>');

function cardCapa(c, m) {
  const foto = c._foto || m.foto;
  const temFoto = c.foto !== false && !!foto;
  return moldura(c.topo,
    `<div class="${temFoto ? 'col' : ''}">
       <h1 style="font-size:${c.corpoTitulo || (temFoto ? 70 : 88)}px">
         ${linhas(c.titulo, c.destacarUltimaLinha === undefined ? true : c.destacarUltimaLinha)}</h1>
       ${c.rodape ? `<div style="margin-top:56px"><hr class="thin">
         <div class="kicker">${txt(c.rodape[0])}${c.rodape[1] ?
           `<br><span class="am" style="font-weight:700">${txt(c.rodape[1])}</span>` : ''}</div>
       </div>` : ''}
     </div>`,
    blocoLogo(m, 104) || `<span>${txt(m.assinatura || '')}</span>`, '',
    temFoto ? blocoFoto(m, c.fotoCfg || {}, foto) : '', '');
}

function cardMito(c, m) {
  const limpo = String(c.verdade).replace(/<[^>]+>/g, '');
  const fs_ = c.corpoVerdade || (limpo.length > 110 ? 46 : limpo.length > 70 ? 52 : 58);
  return moldura(c.topo,
    `<div>
       <div class="label" style="color:${m.cinza}">${txt(c.rotuloA || 'MITO')}</div>
       <h1 class="am" style="font-size:${c.corpoMito || 62}px">“${txt(c.mito)}”</h1>
     </div>
     <hr class="thin" style="margin:58px 0">
     <div>
       <div class="label" style="color:${m.cinza}">${txt(c.rotuloB || 'VERDADE')}</div>
       <div style="font-size:${fs_}px;line-height:1.36;font-weight:700">${txt(c.verdade)}</div>
     </div>`,
    blocoLogo(m, 96) || `<span>${txt(m.assinatura || '')}</span>`, '',
    (c.numero ? `<div class="bg"><div class="fantasma">${txt(c.numero)}</div></div>` : '') +
    ((c._foto || c.fotoArquivo) ? blocoFoto(m, c.fotoCfg || { modo: 'bloco' }, c._foto) : ''));
}

function cardFecho(c, m) {
  const foto = c._foto || m.foto;
  const temFoto = c.foto !== false && !!foto;
  const t = c.corpoTitulo || (temFoto ? 68 : 84);
  return moldura(c.topo,
    `<div class="${temFoto ? 'col' : ''}">
       <h1 style="font-size:${t}px">${linhas(c.titulo, false)}</h1>
       ${c.titulo2 ? `<h1 class="am" style="font-size:${t}px;margin-top:40px">
          ${linhas(c.titulo2, false)}</h1>` : ''}
       ${c.rodape ? `<div style="margin-top:56px"><hr class="thin">
          <div class="kicker">${txt(c.rodape.join('<br>'))}</div></div>` : ''}
     </div>`,
    // no fecho o logo assina o rodape; sem logo, volta pra assinatura em texto
    blocoLogo(m, 104) || `<span>${txt(m.assinatura || '')}</span>`, '',
    temFoto ? blocoFoto(m, c.fotoCfg || { altura: 1180, direita: -130 }, foto) : '',
    '');
}

const TIPOS = { capa: cardCapa, mito: cardMito, fecho: cardFecho };

// ---------------------------------------------------------------------------
// Principal
// ---------------------------------------------------------------------------
function main() {
  const specPath = process.argv[2];
  if (!specPath) {
    console.error('Uso: node gerar.js <spec.json> [pasta-de-saida]');
    process.exit(2);
  }
  const specDir = path.dirname(path.resolve(specPath));
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

  // caminhos de imagem sao relativos ao spec
  const m = Object.assign(
    { preto: '#0C0C0C', branco: '#FFFFFF', cinza: '#8E8E8E', destaque: '#F5C518' },
    spec.marca || {});
  for (const k of ['logo', 'foto']) {
    if (m[k]) {
      const p = path.resolve(specDir, m[k]);
      if (!fs.existsSync(p)) {
        console.warn(`[aviso] ${k} nao encontrado em ${p} — seguindo sem ele.`);
        m[k] = null;
      } else { m[k] = p; }
    }
  }

  // foto propria de um card (c.fotoArquivo) — caminho relativo ao spec
  for (const c of spec.cards) {
    if (c.fotoArquivo) {
      const p = path.resolve(specDir, c.fotoArquivo);
      if (!fs.existsSync(p)) {
        console.warn(`[aviso] foto "${c.fotoArquivo}" nao encontrada — usando a da marca.`);
      } else { c._foto = p; }
    }
  }

  const saida = path.resolve(process.argv[3] || spec.saida || path.join(specDir, 'cards'));
  fs.mkdirSync(saida, { recursive: true });

  const f = carregarFontes(specDir);
  const css = montarCSS(m, f);
  const navegador = acharNavegador();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'carrossel-'));

  const gerados = [];
  spec.cards.forEach((c, i) => {
    const fn = TIPOS[c.tipo];
    if (!fn) throw new Error(`Card ${i + 1}: tipo "${c.tipo}" nao existe. ` +
      `Use um de: ${Object.keys(TIPOS).join(', ')}`);
    const n = String(i + 1).padStart(2, '0');
    const html = `<!doctype html><html lang="pt-BR"><meta charset="utf-8">` +
      `<style>${css}</style>${fn(c, m)}`;
    const fHtml = path.join(tmp, `card-${n}.html`);
    const fPng = path.join(saida, `card-${n}.png`);
    fs.writeFileSync(fHtml, html);
    execFileSync(navegador, ['--headless', '--no-sandbox', '--disable-gpu',
      '--hide-scrollbars', '--force-device-scale-factor=1',
      `--window-size=${L},${A}`, `--screenshot=${fPng}`,
      'file://' + fHtml.replace(/\\/g, '/')], { stdio: 'ignore' });
    if (!fs.existsSync(fPng)) throw new Error(`Falhou ao exportar o card ${n}.`);
    gerados.push(fPng);
    console.log(`  card-${n}.png  (${c.tipo})`);
  });

  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${gerados.length} cards em ${L}x${A} gerados em:\n  ${saida}`);
  console.log('Poste na ordem card-01 ... card-' +
    String(gerados.length).padStart(2, '0') + '.');
}

if (require.main === module) {
  try { main(); } catch (e) { console.error('\nErro: ' + e.message); process.exit(1); }
}
