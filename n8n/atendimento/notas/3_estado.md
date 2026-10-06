# Zona 3 — Controle de Estado: Extrator + Máquina de Estado

A espinha dorsal de decisão. Princípio do Framework v1.2: **o banco guarda dado, a máquina decide, a IA só narra.** Nenhum nó desta zona escreve texto para o cliente.

**Carregar Estado + Catálogo** (Postgres) — `senhor_smart_at.v1_carregar_estado(ticketId)` devolve o estado salvo da conversa (null no 1º turno) e `v1_catalogo_extrator()` devolve, ao vivo do banco, as categorias, os serviços e as objeções. Serviço novo cadastrado no banco já é reconhecido sem editar prompt.

**Extrair Intenção** (HTTP → OpenRouter, GPT-5.4-mini, reasoning none, json_schema strict; prompt em `prompts/extrator.md`) — lê a mensagem e um resumo curto do estado (aparelhos já falados e a última pergunta da Sofia, para entender respostas soltas como "Michele" ou "é um A52s"). Devolve intenção, aparelhos (categoria, marca, modelo, defeito, serviço sugerido, evidência), perguntas, nome informado, visita, sentimento, objeção e impacto. Os enums vêm do catálogo do banco. Só extrai, não decide. Se falhar, a máquina recebe intenção "outro" e segue.

**Carregar Contexto** (Postgres) — `v1_carregar_contexto(now())` devolve os dados da loja: fatos confirmados e a confirmar, horário, feriados, categorias, padrões de modelo, serviços com detalhes, preços fixos, condição de pagamento (entrada R$ 240 + até 18x no boleto), regras de origem, biblioteca de objeções e filas da DeskRio. **Regra de ouro: este SQL nunca lê o estado da conversa.**

**Máquina de Estado** (HTTP → `https://senhor-smart-estado.mpstudio.ia.br/processar`; container senhor-smart-maquina no Droplet 192.241.144.247, atrás do Caddy compartilhado; código em `senhor-smart-estado/maquina.py`, com testes) — recebe leitura, foto, contexto, estado anterior, nome do WhatsApp, hora e dados do anúncio. Devolve **conducao** (a decisão do turno, que a Sofia narra), **estado_novo** e **metricas** (o que vai para o painel). Decide: nome válido ou perguntar, modelo e serviço (resolvido, ambíguo ou avaliação), preço fixo e condição de pagamento, objeção e argumentos autorizados, convite para a loja, visita combinada, horário aberto ou fechado, origem (Google, Meta, orgânico), duplicata e transferência. Se a máquina não responder, a saída de erro solta o lock (**Liberar próxima mensagem do cliente**) para o próximo turno não travar.

**Dedup OK?** — lê conducao.duplicata (mesmo lastMessage + lastMessageDate do turno anterior). Duplicata não gera nova resposta: **Liberar próxima mensagem do cliente** solta o lock e encerra.
