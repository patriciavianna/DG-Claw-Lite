# Gerador de carrossel

Desenha os cards do seu carrossel em **1080×1350 (4:5)** na sua identidade
visual e exporta PNG prontos pra postar.

## Por que não usar IA de imagem aqui

Card de carrossel é quase só **texto em caixa alta**. Modelo de imagem erra
texto — sai torto, borrado, com letra inventada. Aqui o texto é texto de
verdade: sai nítido, na cor exata da marca, e **não custa nada** (gerar 7 cards
numa API de imagem custaria alguns dólares).

A IA de imagem continua útil pra **fundo e ilustração** — só não pra palavra
grande na tela.

## Como usar

```
node gerar.js meu-carrossel.json
```

Sai uma pasta `cards/` com `card-01.png`, `card-02.png`… Poste nessa ordem.

Pra mandar a saída pra outro lugar: `node gerar.js meu-carrossel.json ../posts/`

## O que você precisa

- **Node** — já vem com o Claude Code, não instale nada.
- **Um navegador Chrome, Edge ou Chromium** — é ele que exporta o PNG. No
  Windows o **Edge já vem instalado**, então normalmente funciona direto. Se o
  gerador não achar, aponte o caminho:
  `set CARROSSEL_NAVEGADOR=C:\caminho\do\navegador.exe`
- **Fontes (opcional, mas recomendado).** Sem elas o gerador **não quebra** —
  cai numa fonte do sistema e avisa. Pra ficar com o peso condensado editorial:

  ```
  npm install @fontsource/anton @fontsource/archivo
  ```

## O arquivo de spec

Veja `exemplo.json`. A estrutura é:

```json
{
  "marca": { "destaque": "#F5C518", "assinatura": "@perfil",
             "logo": "logo.png", "foto": "foto.png" },
  "cards": [ { "tipo": "capa", ... }, { "tipo": "mito", ... } ]
}
```

Os caminhos de `logo` e `foto` são **relativos ao arquivo de spec**. Faltando
algum, o gerador avisa e segue sem ele.

### Foto: dois modos, e como escolher

O fundo da **foto original** decide qual funciona. Escolher errado é o defeito
mais visível que um card pode ter.

| Modo | Quando usar | O que faz |
|---|---|---|
| `recorte` (padrão) | foto com **fundo escuro**, ou PNG já recortado | esfuma as bordas e dissolve o resto do fundo no preto do card |
| `sangria` | foto com **fundo claro** (estúdio cinza, ambiente, evento) | não tenta recortar: a foto vai até a borda do card e leva escurecimento, virando um degradê proposital |

> **Por que não recortar fundo claro automaticamente.** Cabelo e pele na sombra
> ficam a uma distância pequena do cinza de estúdio — numa foto real testada
> aqui, a diferença era de apenas 65 (numa escala de 765). Qualquer tolerância
> que remova o fundo inteiro também come o rosto; qualquer tolerância que
> preserve o rosto deixa manchas de fundo. **Sangria sempre parece intencional;
> recorte malfeito sempre parece defeito.**

Ajustes da `sangria`: `largura` (px da faixa), `brilho` (0 a 1 — quanto menor,
mais escuro), `corte` (onde o degradê preto termina, em %) e `foco`
(`object-position`, ex.: `"62% 38%"`, pra centralizar no rosto).

### Foto diferente por card

`fotoArquivo` num card usa outra imagem só ali. Útil pra abrir com um retrato e
fechar com uma foto de chamada pra ação:

```json
{ "tipo": "fecho", "fotoArquivo": "apontando.jpg",
  "fotoCfg": { "modo": "sangria", "largura": 600, "brilho": 0.72 } }
```

### Bloco `marca`

| Campo | O que faz | Padrão |
|---|---|---|
| `preto` | fundo dos cards | `#0C0C0C` |
| `destaque` | a cor de realce — **uma só** | `#F5C518` |
| `cinza` | rótulos e texto secundário | `#8E8E8E` |
| `assinatura` | o `@` no rodapé | — |
| `logo` | PNG, de preferência **branco com fundo transparente** | — |
| `foto` | PNG ou JPG da pessoa, de corpo ou meio-corpo | — |

> **Uma cor de destaque só.** Duas cores brigando é o que faz um feed parecer
> improvisado. Se o seu logo tem outra cor, use o logo em versão branca nos
> cards e guarde a versão colorida pra outros usos.

### Tipos de card

**`capa`** — a que ganha o arraste.

| Campo | O que é |
|---|---|
| `topo` | a linha fina de cima (pilares, categoria) |
| `titulo` | array de linhas, uma por quebra |
| `destacarUltimaLinha` | última linha na cor de destaque (padrão: sim) |
| `rodape` | `[linha normal, linha em destaque]` |
| `foto` | `false` remove a foto deste card |
| `logo` | `false` remove o logo do topo |
| `corpoTitulo` | força o tamanho da fonte, se precisar |

**`mito`** — a estrutura crença → correção.

| Campo | O que é |
|---|---|
| `mito` | a crença, entre aspas, em cinza |
| `verdade` | a correção, em branco e negrito |
| `rotuloA` / `rotuloB` | trocam "MITO" e "VERDADE" por outros rótulos |
| `numero` | o número discreto no canto |

**`fecho`** — o último card, o que é salvo e compartilhado.

| Campo | O que é |
|---|---|
| `titulo` | primeira metade do contraste, em branco |
| `titulo2` | segunda metade, na cor de destaque |
| `rodape` | array de linhas: o pedido (salve / compartilhe) |

O logo, quando existe, assina o rodapé deste card no lugar do `@`.

## Dicas de conteúdo

- **3 a 8 cards.** Menos de 3 é post de imagem única; mais de 8, a pessoa
  abandona no meio.
- **Uma ideia por card**, legível em 2 segundos numa tela de celular.
- **O melhor argumento vai no card 2 ou 3**, nunca no fim — muita gente não
  chega lá.
- **O último card precisa valer sozinho**: é ele que a pessoa salva.

## Se algo sair errado

| Sintoma | Causa | Conserto |
|---|---|---|
| Letras sobrepostas | entrelinha apertada numa fonte com acento | já resolvido no gerador; se você mexeu, `LH_TITULO` não pode ficar abaixo de 1.18 |
| Assinatura sumiu do rodapé | conteúdo maior que o card | reduza `corpoTitulo` ou tire uma linha do título |
| A foto cobriu o texto | ordem das camadas no CSS | `.card>*` tem que vir **antes** de `.card>.bg` |
| A pessoa saiu achatada | largura e altura definidas juntas | no modo `recorte` a foto usa `width:auto`; não defina largura |
| Foto virou um retângulo flutuando | `sangria` sem cobrir a altura toda | já resolvido com `object-fit:cover` + `height:100%` |
| Rosto com o olho virando buraco preto | escurecimento aplicado na imagem antes | não escureça sombras na foto; use `brilho` no `fotoCfg` |
| Retângulo claro atrás da pessoa | foto de fundo claro no modo `recorte` | troque para `"modo": "sangria"` |
| Retângulo visível em volta da foto | fundo da foto mais claro que o card | aumente a suavização em `blocoFoto` |
| Não achou navegador | Chrome/Edge fora do lugar padrão | `CARROSSEL_NAVEGADOR=<caminho>` |

## Conferir antes de postar

**Abra os PNG e olhe.** Sempre. Vale conferir três coisas: nenhuma linha
sobreposta, a assinatura no lugar, e a pessoa com as proporções certas. Foram
exatamente esses três os erros que apareceram quando este gerador foi escrito.
