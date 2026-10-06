# Zona 4 — IA: Sofia (só narra)

Única zona em que um modelo escreve para o cliente. A decisão já veio pronta da Máquina de Estado; a Sofia transforma em conversa, como a melhor vendedora de shopping: entende o problema, mostra como fica a vida com o aparelho resolvido e deixa a ida à loja fácil.

**Sofia** (AI Agent) — recebe "Contexto recebido" (a conducao limpa: sem campos nulos, falsos ou vazios e sem os internos duplicata, etapa, fila, transferir_para, motivo_transferencia, resumo_encaminhamento) + a mensagem do cliente. O prompt (`prompts/narrador.md`) segue o modelo do GPT-4.1: papel, instruções, passos, glossário de cada campo, situações comuns, formato, 7 exemplos com conducao real da máquina e regras finais. **A máquina passa dado e orientação, nunca frase pronta** — o 4.1-mini é literal e copiaria. Preço, parcelamento, prazo e fatos da loja só saem se vierem no contexto; o que está em nao_afirmar a Sofia não afirma.

**GPT 4.1 mini** (OpenRouter, openai/gpt-4.1-mini) — temperature 0.4, maxTokens 350, frequencyPenalty 0.2.

**Memória Sofia** (Postgres Chat Memory) — histórico da conversa por ticketId na tabela `senhor_smart_at.sofia_memoria` (RLS ligado), janela de 12 mensagens. Serve para a Sofia não se repetir; a decisão nunca vem da memória, vem da máquina.
