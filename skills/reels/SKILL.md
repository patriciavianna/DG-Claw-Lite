---
name: reels
description: Editor de Reels do DG Claw Lite — junta varios pedacinhos de video na ordem certa, deixa em 9:16 pro Instagram, melhora imagem e voz, corta cacoetes ("ãh", "hum", "é..."), gaguejos, falas repetidas (fica a ultima tentativa) e silencios, com legenda opcional. Use quando a pessoa rodar /dgclaw-lite:reels, mandar varios videos e pedir "junta esses videos", "edita meu reel", "monta o video pro Instagram", "tira os cacoetes", "tira as partes repetidas", "melhora o audio do video", "deixa no formato do Instagram". Vale tambem quando os videos chegam PELO TELEGRAM, na conversa do proprio agente.
user-invocable: true
---

# /dgclaw-lite:reels — de pedacinhos a um Reel pronto

Fale em português do Brasil, tom acolhedor, sem jargão. A ferramenta mora em
`${CLAUDE_PLUGIN_ROOT}/ferramentas/reels/editar.py` (leia o `README.md` ao lado
se precisar de detalhe).

## 1. Conferir o que precisa (uma vez só)

- `ffmpeg -version` — sem ffmpeg, entregue o comando de instalar do sistema
  dela (README) e pare aqui até ela instalar. É o único programa extra.
- `python --version` (ou `python3`).
- Transcrição: leia `<pasta do agente>/audio.json`. `provider` `groq` ou
  `local` → cacoetes e repetidas funcionam. `off` ou sem arquivo → avise em 1
  linha que **só os silêncios** serão cortados e que dá pra ligar a
  transcrição pedindo *"liga a transcrição de áudio"*. Nunca trave por isso.

## 2. Juntar os vídeos

- Vídeos vindos do Telegram: baixe cada um pra uma pasta nova
  `<pasta do agente>/reels/<data>-<tema>/brutos/`. **Mantenha a ordem em que
  ela mandou** nomeando `01.mp4`, `02.mp4`… e use `--ordem nome`.
- Vídeos numa pasta do computador: o padrão `--ordem data` usa a data de
  gravação. Mostre a ordem que saiu no passo 1/5 e pergunte se está certa
  **antes** de considerar pronto.

## 3. Rodar

De dentro da pasta do agente (assim ele acha o `audio.json`):

```
python "${CLAUDE_PLUGIN_ROOT}/ferramentas/reels/editar.py" reels/<...>/brutos -o reels/<...>/reel.mp4 --ordem nome
```

**Sem legenda**: o padrão é não colocar legenda, e assim fica — só use
`--legendas` se ela pedir legenda com todas as letras naquele vídeo.
Acrescente o que ela pediu: `--voz forte` (áudio muito ruidoso),
`--enquadrar cortar`, `--cacoetes "tipo,né"`. Na dúvida, use o padrão.

## 4. Entregar

1. Leia o `reel-relatorio.json` e conte em poucas linhas: duração antes → depois,
   quantos cacoetes saíram e **cite cada fala repetida que foi cortada** — é ali
   que pode ter cortado algo que ela queria.
2. Mande o `reel.mp4` (pelo Telegram, se o pedido veio de lá).
3. Pergunte se quer ajustar. Ajustes comuns: "voltou uma fala que eu queria" →
   `--manter-repetidas` ou `--semelhanca 0.8`; "ficou picotado" →
   `--silencio 0.8`; "voz robótica" → `--voz leve`; "sem zoom" → `--zoom 1.0`.

⚠️ Nada é postado daqui. Publicar segue a regra do `/dgclaw-lite:instagram`:
só com "pode publicar" explícito.
