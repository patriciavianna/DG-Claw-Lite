# Editor de Reels

Você manda vários pedacinhos de vídeo; ele devolve **um Reel pronto pro
Instagram**:

1. **Junta na ordem certa** — pela data de gravação de cada vídeo (ou pelo nome
   do arquivo: `01.mp4`, `02.mp4`…).
2. **Deixa em 9:16** (1080×1920, 30 fps). Vídeo em pé preenche a tela; vídeo
   deitado ganha fundo desfocado (ou corta as laterais, se você preferir).
3. **Melhora a imagem** — tira granulado, dá nitidez e um pouco de contraste e
   cor, sem exagero.
4. **Corta os cacoetes** — "ãh", "hum", "ahn", "é…" esticado — e os **gaguejos**
   ("eu eu acho" → "eu acho").
5. **Corta as falas repetidas** — quando você começa, erra e fala de novo, fica
   **só a última tentativa**. Funciona até entre um pedacinho e outro.
6. **Corta os silêncios** e respiros longos.
7. **Melhora a voz** — tira ronco e chiado, deixa a voz mais clara, iguala o
   volume e entrega no padrão do Instagram (-14 LUFS).
8. **Efeitos mínimos** — zoom leve alternado nos cortes (disfarça o "pulo"),
   entrada e saída suaves. **Sem legenda** por padrão (dá pra ligar com `--legendas`).

## Como usar

```
python editar.py pasta-com-os-videos/ -o meu-reel.mp4
```

ou passando os arquivos:

```
python editar.py parte1.mp4 parte2.mp4 parte3.mp4 -o meu-reel.mp4 --legendas
```

Junto com o vídeo sai um `meu-reel-relatorio.json` dizendo a ordem usada,
quanto tempo foi cortado e **quais falas saíram** — confira antes de postar.

## O que você precisa

- **Python 3** e **ffmpeg**. O ffmpeg é o único programa a instalar:
  - Windows: `winget install Gyan.FFmpeg` (feche e reabra o terminal)
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- **Transcrição ligada** pra cortar cacoetes e falas repetidas. Ele usa o
  mesmo `audio.json` do agente (Passo 5a do setup): Groq ou local
  (faster-whisper). Rode o comando **de dentro da pasta do agente** ou aponte
  com `--audio-json caminho/audio.json`. Sem transcrição ele **não trava**:
  corta só os silêncios e avisa.

> Privacidade: no Groq o áudio do vídeo vai pro servidor deles pra virar texto;
> no modo local nada sai do computador.

## Ajustes

| Opção | O que faz |
|---|---|
| `--ordem data\|nome\|como-veio` | ordem dos pedaços (padrão: data de gravação) |
| `--enquadrar auto\|cortar\|desfoque` | o que fazer com vídeo deitado |
| `--voz nenhum\|leve\|medio\|forte` | intensidade da limpeza de voz (padrão: medio) |
| `--legendas` | queima legenda em caixa alta no vídeo |
| `--zoom 1.0` | desliga o zoom nos cortes (padrão 1.06) |
| `--cacoetes "tipo,né,então"` | palavras extras pra cortar (cuidado: corta TODAS) |
| `--manter-repetidas` | não corta falas repetidas |
| `--manter-silencios` | não corta silêncios |
| `--silencio 0.45` | pausa mínima (s) que é cortada |
| `--semelhanca 0.6` | o quanto duas falas precisam se parecer pra contar como repetida |
| `--crf 18` | qualidade final (menor = melhor e maior) |

## Limites — conversa franca

- O corte de "fala repetida" compara frases vizinhas. Se você **repete de
  propósito** ("é grátis. É grátis mesmo."), ele pode cortar — use
  `--manter-repetidas` ou suba `--semelhanca`.
- "Tipo" e "né" **não** saem por padrão, porque muitas vezes são palavras de
  verdade. Se são cacoete seu, passe em `--cacoetes`.
- Melhorar imagem não faz milagre: vídeo escuro ou desfocado fica *melhor*, não
  *profissional*.
