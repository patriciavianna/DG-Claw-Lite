#!/usr/bin/env python3
"""
Editor de Reels do DG Claw Lite.

Recebe varios pedacinhos de video e entrega UM video pronto pro Instagram:
  1. poe os pedacos na ordem certa (data de gravacao, ou nome do arquivo);
  2. deixa tudo em 9:16 (1080x1920, 30 fps), com imagem mais nitida e viva;
  3. transcreve a fala (Groq ou faster-whisper local, lendo o audio.json);
  4. corta os cacoetes ("ãh", "hum", "é..."), as falas repetidas (o "deixa eu
     falar de novo" — fica sempre a ULTIMA tentativa) e os silencios;
  5. melhora a voz (tira ruido e chiado, equaliza, comprime, volume padrao
     do Instagram: -14 LUFS);
  6. exporta MP4 H.264 + AAC, do jeito que o Instagram gosta.

Uso:
  python editar.py <video1> <video2> ...   (ou uma pasta com os videos)
  python editar.py pasta/ -o meu-reel.mp4

So precisa de Python 3 e do ffmpeg. Nada de pip, a nao ser que voce escolha
transcricao local (faster-whisper).
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
import uuid

LARGURA, ALTURA, FPS = 1080, 1920, 30
EXTENSOES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"}

# Cacoetes que SEMPRE saem (hesitacao pura, nunca e palavra de verdade).
CACOETES_SEMPRE = {
    "ah", "ahn", "aham", "an", "ãh", "ã", "ãn", "ããã", "eh", "éé", "ééé", "hã",
    "hãn", "hum", "humm", "hmm", "hm", "mm", "mhm", "uh", "um", "uhm", "ehm",
    "er", "erm", "uhum",
}
# "é" so sai quando e esticado (hesitacao), nao quando e o verbo ("isso é bom").
DURACAO_E_ESTICADO = 0.45
# Prompt que faz o Whisper ESCREVER as hesitacoes em vez de limpa-las sozinho.
PROMPT_WHISPER = "Ãh, então, é... hum, tipo assim, né? Ahn, eu, eu acho que... Hã."


def log(msg):
    print(msg, flush=True)


def erro(msg):
    print("ERRO: " + msg, file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------- ffmpeg

def achar_ffmpeg():
    ff = os.environ.get("REELS_FFMPEG") or shutil.which("ffmpeg")
    fp = os.environ.get("REELS_FFPROBE") or shutil.which("ffprobe")
    if not ff or not fp:
        erro("nao achei o ffmpeg. Instale com:\n"
             "  Windows: winget install Gyan.FFmpeg   (feche e reabra o terminal)\n"
             "  Mac:     brew install ffmpeg\n"
             "  Linux:   sudo apt install ffmpeg")
    return ff, fp


def rodar(cmd, quieto=True):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        cauda = "\n".join(r.stderr.strip().splitlines()[-15:])
        erro("o ffmpeg falhou:\n" + cauda)
    return r


def sondar(ffprobe, caminho):
    r = rodar([ffprobe, "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", caminho])
    info = json.loads(r.stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not video:
        erro(f"{caminho} nao tem imagem de video.")
    w, h = int(video["width"]), int(video["height"])
    rot = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = int(video.get("tags", {}).get("rotate", rot))
    if abs(rot) % 180 == 90:  # celular gravou em pe com metadado de rotacao
        w, h = h, w
    tags = {**info["format"].get("tags", {}), **video.get("tags", {})}
    data = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate") or ""
    return {
        "largura": w, "altura": h, "tem_audio": audio is not None,
        "duracao": float(info["format"].get("duration") or video.get("duration") or 0),
        "data": data,
    }


# ---------------------------------------------------------------------- ordem

def chave_natural(nome):
    # WhatsApp: "xxxx-VID-20261110-WA0016.mp4" -> ordena pela data + numero
    m = re.search(r"(\d{8})-WA(\d+)", nome)
    if m:
        return [m.group(1), int(m.group(2))]
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nome)]


def ordenar(clipes, modo):
    if modo == "como-veio":
        return clipes
    if modo == "nome":
        return sorted(clipes, key=lambda c: chave_natural(os.path.basename(c["arquivo"])))
    # "data": data de gravacao do metadado; sem ela, cai pro nome.
    if all(c["info"]["data"] for c in clipes):
        return sorted(clipes, key=lambda c: (c["info"]["data"],
                                             chave_natural(os.path.basename(c["arquivo"]))))
    log("  (nem todo video tem data de gravacao — ordenei pelo NOME do arquivo)")
    return ordenar(clipes, "nome")


# ---------------------------------------------------------- etapa 1: 9:16 HQ

def filtro_video(info, enquadrar):
    """Leva qualquer video pra 1080x1920 e da um trato na imagem."""
    proporcao = info["largura"] / info["altura"]
    if enquadrar == "auto":
        # em pe ou quase (4:5 pra cima): corta e preenche; deitado: fundo desfocado
        enquadrar = "cortar" if proporcao <= 0.85 else "desfoque"
    trato = ("hqdn3d=1.5:1.5:6:6,"                    # tira granulado leve
             "unsharp=5:5:0.6:5:5:0.0,"               # nitidez sem halo
             "eq=contrast=1.04:saturation=1.10:gamma=1.02")
    if enquadrar == "cortar":
        return (f"[0:v]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase:"
                f"flags=lanczos,crop={LARGURA}:{ALTURA},setsar=1,fps={FPS},{trato},"
                f"format=yuv420p[v]")
    return (f"[0:v]fps={FPS},split[a][b];"
            f"[a]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
            f"crop={LARGURA}:{ALTURA},gblur=sigma=40,eq=brightness=-0.08[fundo];"
            f"[b]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=decrease:"
            f"flags=lanczos,{trato}[frente];"
            f"[fundo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")


def medir_volume(ffmpeg, arquivo):
    """Volume medio da fala (LUFS) do pedaco, ou None se nao der pra medir."""
    r = subprocess.run([ffmpeg, "-v", "info", "-i", arquivo, "-vn", "-af",
                        "highpass=f=80,loudnorm=print_format=json", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+|-inf)"', r.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


def filtro_audio_pedaco(ffmpeg, clipe, voz):
    """Limpa o ruido e iguala o volume de CADA pedaco antes de juntar.

    Celular, lapela, outro lugar da sala: cada pedaco chega num volume. Sem
    igualar, o pedaco baixinho inteiro parece "silencio" e some no corte.
    Ganho fixo (nao dinamico), pra nao inflar o chiado nas pausas.
    """
    cadeia = []
    if voz != "nenhum":
        nr = {"leve": 12, "medio": 20, "forte": 30}[voz]
        cadeia += ["highpass=f=80", f"afftdn=nr={nr}:nf=-45:tn=1"]
    lufs = medir_volume(ffmpeg, clipe["arquivo"])
    if lufs is not None:
        ganho = max(-20.0, min(30.0, -20.0 - lufs))
        clipe["ganho_db"] = round(ganho, 1)
        cadeia.append(f"volume={ganho:.2f}dB,alimiter=limit=0.95:level=disabled")
    return ",".join(cadeia) or "anull"


def normalizar(ffmpeg, clipe, saida, enquadrar, voz):
    info = clipe["info"]
    cmd = [ffmpeg, "-y", "-v", "error", "-i", clipe["arquivo"]]
    if not info["tem_audio"]:
        cmd += ["-f", "lavfi", "-t", str(info["duracao"]),
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        grafo = filtro_video(info, enquadrar)
        mapa_a = "1:a:0"
    else:
        grafo = (filtro_video(info, enquadrar) + ";[0:a:0]"
                 + filtro_audio_pedaco(ffmpeg, clipe, voz) + "[a]")
        mapa_a = "[a]"
    cmd += ["-filter_complex", grafo, "-map", "[v]", "-map", mapa_a,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-shortest", saida]
    rodar(cmd)


def juntar(ffmpeg, partes, saida, tmp):
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for p in partes:
            f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
    rodar([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista,
           "-c", "copy", saida])


# ---------------------------------------------------------- etapa 2: ouvir

def ler_audio_json(caminho_cfg):
    candidatos = [caminho_cfg] if caminho_cfg else []
    candidatos += [os.path.join(os.getcwd(), "audio.json"),
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio.json")]
    for c in candidatos:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def extrair_audio_fala(ffmpeg, video, saida):
    # mono 16 kHz em mp3: pequeno o bastante pro limite de 25 MB da Groq
    rodar([ffmpeg, "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "libmp3lame", "-b:a", "48k", saida])


def transcrever_groq(audio, chave):
    limite = "----reels" + uuid.uuid4().hex
    campos = {"model": "whisper-large-v3", "language": "pt",
              "response_format": "verbose_json", "temperature": "0",
              "prompt": PROMPT_WHISPER}
    corpo = b""
    for k, v in campos.items():
        corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                  f"{v}\r\n").encode("utf-8")
    for g in ("word", "segment"):
        corpo += (f"--{limite}\r\nContent-Disposition: form-data; "
                  f"name=\"timestamp_granularities[]\"\r\n\r\n{g}\r\n").encode()
    with open(audio, "rb") as f:
        dados = f.read()
    corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; "
              f"filename=\"fala.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode()
    corpo += dados + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions", data=corpo,
        headers={"Authorization": "Bearer " + chave,
                 "Content-Type": "multipart/form-data; boundary=" + limite,
                 "User-Agent": "dgclaw-lite-reels"})
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    return [{"palavra": w["word"], "inicio": float(w["start"]), "fim": float(w["end"])}
            for w in resp.get("words", [])]


def transcrever_local(audio, modelo):
    from faster_whisper import WhisperModel  # so importa se escolheu local
    try:
        m = WhisperModel(modelo, device="cuda", compute_type="float16")
    except Exception:
        m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="pt", word_timestamps=True,
                           initial_prompt=PROMPT_WHISPER, vad_filter=False)
    return [{"palavra": w.word, "inicio": float(w.start), "fim": float(w.end)}
            for s in segs for w in (s.words or [])]


def transcrever(ffmpeg, video, tmp, cfg):
    prov = (cfg.get("provider") or "").lower()
    chave = os.environ.get("GROQ_API_KEY") or cfg.get("groq_api_key") or ""
    if prov in ("", "off") and chave:
        prov = "groq"
    if prov in ("", "off"):
        return None, "transcricao desligada (audio.json com provider off ou ausente)"
    audio = os.path.join(tmp, "fala.mp3")
    extrair_audio_fala(ffmpeg, video, audio)
    try:
        if prov == "groq":
            if not chave:
                return None, "provider groq, mas sem groq_api_key no audio.json"
            return transcrever_groq(audio, chave), "groq"
        if prov == "local":
            return transcrever_local(audio, cfg.get("modelo_local") or "small"), "local"
    except Exception as e:  # nada trava: sem transcricao, segue so com silencio
        return None, f"a transcricao falhou ({e})"
    return None, f"provider desconhecido: {prov}"


# ----------------------------------------------------- etapa 3: o que cortar

def limpar(txt):
    txt = unicodedata.normalize("NFC", txt.lower().strip())
    return re.sub(r"[^\w\sà-úçãõâêô-]", "", txt).strip()


def sem_acento(txt):
    return "".join(c for c in unicodedata.normalize("NFD", txt)
                   if unicodedata.category(c) != "Mn")


def eh_cacoete(p, extras):
    t = limpar(p["palavra"])
    if not t:
        return False
    if t in CACOETES_SEMPRE or t in extras:
        return True
    base = sem_acento(t)
    if re.fullmatch(r"(a+h*n*|e+h*|h+[ua]+m*|u+h*m*|m{2,}|a+n+)", base):
        return True
    if base in ("e", "ee", "eee") and (p["fim"] - p["inicio"]) >= DURACAO_E_ESTICADO:
        return True  # "é..." esticado = hesitacao
    if "..." in p["palavra"] and base in ("e", "entao", "tipo") \
            and (p["fim"] - p["inicio"]) >= DURACAO_E_ESTICADO:
        return True
    return False


def frases(palavras, pausa):
    """Agrupa palavras em frases separadas por pausa ou pontuacao final."""
    grupos, atual = [], []
    for p in palavras:
        if atual and (p["inicio"] - atual[-1]["fim"] > pausa
                      or re.search(r"[.!?]$", atual[-1]["palavra"].strip())):
            grupos.append(atual)
            atual = []
        atual.append(p)
    if atual:
        grupos.append(atual)
    return grupos


def texto(grupo):
    return " ".join(sem_acento(limpar(p["palavra"])) for p in grupo).strip()


def eh_retomada(a, b, limiar):
    """A frase 'a' e uma tentativa que foi refeita em 'b'?"""
    ta, tb = texto(a), texto(b)
    wa, wb = ta.split(), tb.split()
    if len(wa) < 2 or not wb:
        return False
    # frase curta abandonada: "hoje eu vou" ... "hoje eu vou falar de X"
    if len(wa) <= 3:
        return wb[:len(wa)] == wa
    # frase maior: comeca igual (3 palavras) E a maior parte dela se repete
    if wa[:3] == wb[:3] and \
            difflib.SequenceMatcher(None, wa, wb[:len(wa)]).ratio() >= limiar:
        return True
    # mesma fala dita de novo com outras palavras pequenas no meio
    return difflib.SequenceMatcher(None, ta, tb).ratio() >= max(limiar, 0.8)


def marcar_cortes(palavras, extras, limiar, pausa, repetidas=True, olhar_adiante=3):
    """Devolve (palavras que ficam, relatorio)."""
    rel = {"cacoetes": [], "repetidas": [], "gaguejos": []}
    # 1) cacoetes
    restantes = []
    for p in palavras:
        if eh_cacoete(p, extras):
            rel["cacoetes"].append(p["palavra"].strip())
        else:
            restantes.append(p)
    # 2) gaguejo: "eu eu", "a a a" -> fica so a ultima
    sem_gaguejo = []
    for i, p in enumerate(restantes):
        prox = restantes[i + 1] if i + 1 < len(restantes) else None
        if prox and limpar(p["palavra"]) and limpar(p["palavra"]) == limpar(prox["palavra"]) \
                and prox["inicio"] - p["fim"] < 0.6:
            rel["gaguejos"].append(p["palavra"].strip())
            continue
        sem_gaguejo.append(p)
    # 3) falas repetidas: se uma frase e refeita logo adiante, fica a ULTIMA
    grupos = frases(sem_gaguejo, pausa)
    descartar = set()
    for i, g in enumerate(grupos if repetidas else []):
        for j in range(i + 1, min(len(grupos), i + 1 + olhar_adiante)):
            if eh_retomada(g, grupos[j], limiar):
                descartar.add(i)
                rel["repetidas"].append(" ".join(p["palavra"].strip() for p in g))
                break
    ficam = [p for i, g in enumerate(grupos) if i not in descartar for p in g]
    return ficam, rel


def detectar_silencios(ffmpeg, video, limiar_db, minimo):
    r = subprocess.run([ffmpeg, "-v", "info", "-i", video, "-vn", "-af",
                        f"silencedetect=noise={limiar_db}dB:d={minimo}", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    sil, ini = [], None
    for linha in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", linha)
        if m:
            ini = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", linha)
        if m and ini is not None:
            sil.append((ini, float(m.group(1))))
            ini = None
    return sil


def trechos_por_palavras(palavras, folga, juntar_se, duracao):
    trechos = []
    for p in palavras:
        a, b = max(0.0, p["inicio"] - folga), min(duracao, p["fim"] + folga)
        if trechos and a - trechos[-1][1] <= juntar_se:
            trechos[-1][1] = max(trechos[-1][1], b)
        else:
            trechos.append([a, b])
    return trechos


def trechos_por_silencio(silencios, duracao, folga):
    trechos, cursor = [], 0.0
    for a, b in silencios:
        if a - cursor > 0.05:
            trechos.append([max(0.0, cursor - folga), min(duracao, a + folga)])
        cursor = b
    if duracao - cursor > 0.05:
        trechos.append([max(0.0, cursor - folga), duracao])
    # junta sobreposicoes criadas pela folga
    unidos = []
    for t in trechos:
        if unidos and t[0] <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], t[1])
        else:
            unidos.append(t)
    return unidos


def tirar_silencios_de_dentro(trechos, silencios, folga, minimo):
    """Mesmo com a transcricao, respiro longo DENTRO de um trecho tambem sai."""
    saida = []
    for a, b in trechos:
        partes = [[a, b]]
        for sa, sb in silencios:
            if sb - sa < minimo:
                continue
            novas = []
            for pa, pb in partes:
                if sa + folga < pb and sb - folga > pa and (sa + folga) > pa and (sb - folga) < pb:
                    novas += [[pa, sa + folga], [sb - folga, pb]]
                else:
                    novas.append([pa, pb])
            partes = novas
        saida += [p for p in partes if p[1] - p[0] > 0.08]
    return saida


# ------------------------------------------------------ etapa 4: render final

def cadeia_voz(forca):
    # ronco e chiado ja sairam pedaco a pedaco (filtro_audio_pedaco)
    if forca == "nenhum":
        return "loudnorm=I=-14:TP=-1.5:LRA=11"
    return ",".join([
        "equalizer=f=250:t=q:w=1.2:g=-2",             # tira o "embolado"
        "equalizer=f=3500:t=q:w=1.0:g=3",             # presenca/clareza da voz
        "deesser=i=0.4",                              # suaviza os "sss"
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2",
        "lowpass=f=14000",
        "loudnorm=I=-14:TP=-1.5:LRA=11",              # volume padrao do Instagram
    ])


def renderizar(ffmpeg, entrada, trechos, saida, tmp, voz, zoom, legendas_ass, crf):
    linhas, rotulos = [], []
    for i, (a, b) in enumerate(trechos):
        dur = b - a
        f = min(0.012, dur / 4)
        z = zoom if (zoom > 1.0 and i % 2 == 1) else 1.0  # punch-in alternado nos cortes
        zw, zh = int(LARGURA * z) // 2 * 2, int(ALTURA * z) // 2 * 2
        vz = (f",scale={zw}:{zh}:flags=lanczos,crop={LARGURA}:{ALTURA}" if z > 1.0 else "")
        vz += ",setsar=1"
        linhas.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS{vz}[v{i}];")
        linhas.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:d={f:.3f},afade=t=out:st={dur - f:.3f}:d={f:.3f}[a{i}];")
        rotulos.append(f"[v{i}][a{i}]")
    total = sum(b - a for a, b in trechos)
    linhas.append("".join(rotulos) + f"concat=n={len(trechos)}:v=1:a=1[vc][ac];")
    pos = f"fade=t=in:d=0.25,fade=t=out:st={max(0, total - 0.35):.3f}:d=0.35"
    if legendas_ass:
        caminho = legendas_ass.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        pos += f",ass='{caminho}'"
    linhas.append(f"[vc]{pos},format=yuv420p[vf];")
    linhas.append(f"[ac]{cadeia_voz(voz)},aresample=48000[af]")
    script = os.path.join(tmp, "grafo.txt")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
    rodar([ffmpeg, "-y", "-v", "error", "-i", entrada, "-filter_complex_script", script,
           "-map", "[vf]", "-map", "[af]",
           "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-profile:v", "high",
           "-level", "4.2", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-g", str(FPS * 2), "-bf", "2",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", saida])
    return total


def novo_tempo(t, trechos):
    """Converte um tempo do video original pro tempo do video cortado."""
    acum = 0.0
    for a, b in trechos:
        if t < a:          # caiu num pedaco cortado: gruda no proximo trecho
            return acum
        if t <= b:
            return acum + (t - a)
        acum += b - a
    return acum


def gerar_ass(palavras, trechos, caminho, por_tela=3):
    def ts(s):
        h, r = divmod(s, 3600)
        m, s = divmod(r, 60)
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    blocos, atual = [], []
    for p in palavras:
        ini, fim = novo_tempo(p["inicio"], trechos), novo_tempo(p["fim"], trechos)
        if fim - ini < 0.05:
            continue
        atual.append((ini, fim, p["palavra"].strip()))
        if len(atual) >= por_tela or re.search(r"[.!?,]$", p["palavra"].strip()):
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    cab = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 0\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Reel,Arial,78,&H00FFFFFF,&H0000E5FF,&H00000000,&H64000000,-1,0,0,0,"
        "100,100,0,0,1,6,2,2,80,80,620,1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(cab)
        for i, b in enumerate(blocos):
            ini = b[0][0]
            fim = blocos[i + 1][0][0] if i + 1 < len(blocos) else b[-1][1] + 0.3
            fim = min(fim, b[-1][1] + 0.6)
            txt = " ".join(w for _, _, w in b).upper().replace("{", "").replace("}", "")
            f.write(f"Dialogue: 0,{ts(ini)},{ts(fim)},Reel,,0,0,0,,{txt}\n")


# ------------------------------------------------------------------- main

def coletar_entradas(itens):
    arquivos = []
    for it in itens:
        if os.path.isdir(it):
            arquivos += [os.path.join(it, n) for n in os.listdir(it)
                         if os.path.splitext(n)[1].lower() in EXTENSOES]
        elif os.path.isfile(it):
            arquivos.append(it)
        else:
            erro(f"nao achei: {it}")
    if not arquivos:
        erro("nenhum video encontrado.")
    return arquivos


def main():
    ap = argparse.ArgumentParser(description="Junta pedacinhos de video num Reel pronto.")
    ap.add_argument("entradas", nargs="+", help="videos ou pasta com os videos")
    ap.add_argument("-o", "--saida", default="reel.mp4")
    ap.add_argument("--ordem", choices=["data", "nome", "como-veio"], default="data",
                    help="data de gravacao (padrao), nome do arquivo, ou a ordem passada")
    ap.add_argument("--enquadrar", choices=["auto", "cortar", "desfoque"], default="auto",
                    help="video deitado: cortar as laterais ou fundo desfocado (auto decide)")
    ap.add_argument("--voz", choices=["nenhum", "leve", "medio", "forte"], default="medio",
                    help="intensidade da limpeza de voz")
    ap.add_argument("--zoom", type=float, default=1.06,
                    help="zoom leve alternado a cada corte (1.0 desliga)")
    ap.add_argument("--legendas", action="store_true", help="queima legendas no video")
    ap.add_argument("--cacoetes", default="",
                    help='palavras extras a cortar, ex: "tipo,né,então"')
    ap.add_argument("--manter-repetidas", action="store_true",
                    help="nao corta as falas repetidas")
    ap.add_argument("--manter-silencios", action="store_true",
                    help="nao corta silencios/respiros")
    ap.add_argument("--silencio", type=float, default=0.45,
                    help="pausa (s) a partir da qual o silencio e cortado")
    ap.add_argument("--silencio-db", type=float, default=-35,
                    help="volume abaixo do qual e silencio (dB)")
    ap.add_argument("--semelhanca", type=float, default=0.6,
                    help="quao parecida uma fala precisa ser pra contar como repetida (0-1)")
    ap.add_argument("--audio-json", help="caminho do audio.json do agente")
    ap.add_argument("--transcricao", help="usar esta transcricao (json) em vez de transcrever")
    ap.add_argument("--crf", type=int, default=18, help="qualidade final (menor = melhor)")
    ap.add_argument("--manter-temp", action="store_true")
    a = ap.parse_args()

    ffmpeg, ffprobe = achar_ffmpeg()
    extras = {limpar(x) for x in a.cacoetes.split(",") if x.strip()}
    tmp = tempfile.mkdtemp(prefix="reels-")
    try:
        # 1) ordem
        clipes, vistos = [], {}
        for f in coletar_entradas(a.entradas):
            h = hashlib.md5()
            with open(f, "rb") as fh:
                for bloco in iter(lambda: fh.read(1 << 20), b""):
                    h.update(bloco)
            if h.hexdigest() in vistos:
                log(f"     (ignorei {os.path.basename(f)}: e copia identica de "
                    f"{os.path.basename(vistos[h.hexdigest()])})")
                continue
            vistos[h.hexdigest()] = f
            clipes.append({"arquivo": f, "info": sondar(ffprobe, f)})
        clipes = ordenar(clipes, a.ordem)
        log(f"1/5  Ordem dos {len(clipes)} pedacos:")
        for i, c in enumerate(clipes, 1):
            log(f"     {i}. {os.path.basename(c['arquivo'])}  ({c['info']['duracao']:.1f}s)")

        # 2) 9:16 + imagem
        log("2/5  Deixando tudo em 9:16 e melhorando a imagem...")
        partes = []
        for i, c in enumerate(clipes):
            p = os.path.join(tmp, f"parte{i:03d}.mov")
            normalizar(ffmpeg, c, p, a.enquadrar, a.voz)
            partes.append(p)
        bruto = os.path.join(tmp, "bruto.mov")
        juntar(ffmpeg, partes, bruto, tmp)
        duracao = sondar(ffprobe, bruto)["duracao"]

        # 3) ouvir
        log("3/5  Ouvindo a fala...")
        if a.transcricao:
            with open(a.transcricao, encoding="utf-8") as f:
                palavras, via = json.load(f), "arquivo"
        else:
            palavras, via = transcrever(ffmpeg, bruto, tmp, ler_audio_json(a.audio_json))
        silencios = [] if a.manter_silencios else detectar_silencios(
            ffmpeg, bruto, a.silencio_db, a.silencio)

        # 4) decidir cortes
        log("4/5  Cortando cacoetes, falas repetidas e silencios...")
        rel = {"cacoetes": [], "repetidas": [], "gaguejos": []}
        if palavras:
            log(f"     transcricao: {via}, {len(palavras)} palavras")
            ficam, rel = marcar_cortes(
                palavras, extras, a.semelhanca, a.silencio + 0.25,
                repetidas=not a.manter_repetidas)
            folga = 0.10
            juntar_se = 10.0 if a.manter_silencios else a.silencio
            trechos = trechos_por_palavras(ficam, folga, juntar_se, duracao)
            if not a.manter_silencios:
                trechos = tirar_silencios_de_dentro(trechos, silencios, folga, a.silencio)
        else:
            log(f"     sem transcricao ({via}) — corto so os silencios.")
            log("     Cacoetes e falas repetidas precisam da transcricao ligada.")
            ficam = []
            trechos = ([[0.0, duracao]] if a.manter_silencios
                       else trechos_por_silencio(silencios, duracao, 0.12))
        if not trechos:
            erro("depois dos cortes nao sobrou nada — confira o volume do audio "
                 "ou use --manter-silencios.")

        legendas = None
        if a.legendas:
            if ficam:
                legendas = os.path.join(tmp, "legendas.ass")
                gerar_ass(ficam, trechos, legendas)
            else:
                log("     (legendas precisam da transcricao — saindo sem legenda)")

        # 5) render
        log("5/5  Melhorando a voz e exportando no padrao do Instagram...")
        total = renderizar(ffmpeg, bruto, trechos, a.saida, tmp, a.voz, a.zoom,
                           legendas, a.crf)

        relatorio = {
            "saida": os.path.abspath(a.saida),
            "ordem": [os.path.basename(c["arquivo"]) for c in clipes],
            "duracao_bruta": round(duracao, 2), "duracao_final": round(total, 2),
            "cortes": len(trechos) - 1, "transcricao": via,
            "cacoetes_cortados": rel["cacoetes"],
            "gaguejos_cortados": rel["gaguejos"],
            "falas_repetidas_cortadas": rel["repetidas"],
        }
        with open(os.path.splitext(a.saida)[0] + "-relatorio.json", "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)

        log("")
        log(f"Pronto: {a.saida}")
        log(f"  {duracao:.1f}s de bruto -> {total:.1f}s final ({len(trechos) - 1} cortes)")
        log(f"  cacoetes cortados: {len(rel['cacoetes'])}   gaguejos: {len(rel['gaguejos'])}"
            f"   falas repetidas: {len(rel['repetidas'])}")
        for r in rel["repetidas"]:
            log(f"    - saiu a tentativa: \"{r}\"")
        if total > 180:
            log("  Aviso: passou de 3 min — o Instagram pode nao tratar como Reel.")
    finally:
        if a.manter_temp:
            log(f"(arquivos temporarios em {tmp})")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
