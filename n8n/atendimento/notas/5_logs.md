# Zona 5 — Logs do Turno + Métricas do Painel

Registra o turno para o painel do Denis, para o resumo do dia e para auditoria, e formata a fala antes do envio. Nada aqui decide negócio.

**Montar Log do Turno** (Code) — junta as metricas da máquina (fonte única: etapa do funil, eventos, canal e campanha, aparelho, serviço, preço, objeção, transferência, visita, fora do horário) com os dados do turno: mensagem do cliente, resposta da Sofia, latência desde a mensagem do cliente, tokens e custo do extrator.

**Registrar Turno e Métricas** (Postgres) — uma chamada a `senhor_smart_at.v1_registrar_turno(payload)` grava três coisas: `atendimento` (uma linha por ticket, atualizada a cada turno; etapas lançadas pelo vendedor — na loja, OS aberta, fechado, perdido — nunca são sobrescritas), `evento_funil` (cada avanço: triagem → diagnóstico → orçamento → agendado) e `turno_log` (entrada, saída, intenção, estratégia, latência, custo). Duplicata não grava. O SQL só escreve o que a máquina mandou. É daqui que saem o `painel()` e o `v1_resumo_dia()`.

**Pós-processador** (Code) — só mecânica: separa a resposta em até 3 bolhas (|||), tira markdown, e barra vazamento de campo interno (nome com underline, JSON, "Contexto recebido"). Se a resposta vier vazia ou vazar, troca por uma frase de espera e marca transferência para a fila humano. Transferência e fila vêm da máquina, nunca do texto.
