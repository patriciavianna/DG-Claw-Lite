# Funil Vivo — CRM de prospecção

Página única, mobile-first, para acompanhar as pessoas em prospecção
(agência e mentorias no mesmo funil, separadas pelo campo `tipo`).

- **Onde roda:** publicado como Artifact em claude.ai. Abre no celular ou no
  computador pelo mesmo link.
- **Onde os dados moram:** dentro do próprio HTML, no bloco
  `<script type="application/json" id="crm-data">`. Cada alteração republica
  a página com os dados novos. Há uma cópia de segurança em `localStorage`
  do aparelho, usada quando a publicação falha.

## Etapas do funil

`novo` → `contato` → `conversa` → `proposta` → `ganho` / `perdido`

## Ponte com o CRM financeiro

O botão **Exportar planilha** (aba Pessoas) gera um CSV com uma linha por
pessoa e estas colunas, nesta ordem:

```
nome, empresa, contato, tipo, origem, etapa, valor,
proximo_passo, proxima_data, criado_em, notas
```

- `tipo`: `agencia` | `mentoria`
- `etapa`: nome legível da etapa
- `valor`: número puro, sem símbolo de moeda (vazio quando não preenchido)
- `proxima_data` e `criado_em`: `AAAA-MM-DD`
- `notas`: histórico concatenado, no formato `AAAA-MM-DD: texto | AAAA-MM-DD: texto`
- Arquivo em UTF-8 com BOM e quebra de linha CRLF, para abrir certo no Excel
  em português.

O CSV é o formato de troca com o CRM financeiro: quem chega em `ganho` é
quem vira lançamento lá.
