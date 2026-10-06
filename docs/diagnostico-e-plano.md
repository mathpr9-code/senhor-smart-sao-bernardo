# Senhor Smart SBC: diagnóstico e plano para reconquistar o cliente

Base: fluxo n8n `Senhor smart - novo` (id `dLwpCiaonSWavJLj`) e schema `senhor_smart` no Supabase
(conversas de 05/05/2026 a 21/08/2026, data em que o cliente migrou para a TX Mídia).

## 1. O que a TX entrega e por que ganhou

A TX vende um **CRM com painel**: Dashboard, Atendimento, Contatos, Kanban, Ordens de Serviço,
Faturamento, Follow-up e Campanhas. O dono abre e vê na hora: total de leads, conversão,
tempo de resposta, fechamentos, origem (Google/Meta) e funil por etapa.

A IA deles (Maia) é roteirizada: saudação, "teve contato com água?", "como posso te chamar?",
"tem foto?", e uma pergunta de checklist ("quais são as 2 principais para você?").
Ela entende a foto só no nível de "não aparece quebra visível".

**Conclusão:** o cliente não trocou pela IA. Trocou pela **visibilidade e controle**.
A nossa IA rodava sem que ele visse o resultado.

Pontos de atenção na comparação:
- "Fechamentos 221" da TX são cards movidos no Kanban pela equipe, não venda medida pela IA.
- A TX cobre assistência técnica (orçamento de tela, OS). Nosso fluxo era só venda de aparelho no boleto.

**Decisões (06/10/2026):** a IA pode passar faixa de preço; o escopo inclui assistência técnica
(o fluxo novo precisa de uma trilha de orçamento de reparo com leitura da foto do aparelho).

## 2. O que os nossos dados mostram (e o cliente nunca viu)

| Indicador | Valor |
|---|---|
| Leads atendidos (109 dias) | 3.891 (≈ 36/dia) |
| Chegaram à visita (pronto p/ visita ou transferido) | 658 (16,9%) |
| Leads fora do horário da loja | 38% (1.169 de 3.088 com 1ª mensagem registrada) |
| Vieram do anúncio Meta | 66% |
| Pediram iPhone | 717 (18,4%) |
| Pediram modelo fora do catálogo | 216 conversas |
| Modelo mais procurado | Moto G35 5G (441) |

Volume de agosto (948 em 21 dias ≈ 1.350/30 dias) é da mesma ordem dos 1.304/30 dias que a TX mostra.

Painel com esses dados: `dashboard/index.html`.

## 3. Problemas reais da nossa IA (com exemplos do banco)

1. **Funil rígido ignora a pergunta do cliente.** Ticket 67555740 pediu modelos e valores 4 vezes;
   a IA insistiu em "como você usa o celular?" até ouvir "não está me ajudando". Ticket 67568313
   perguntou "onde está localizado?" e recebeu "como você se chama?".
   *Correção:* regra "responde primeiro, conduz depois". Se a pergunta é direta (endereço, preço, forma
   de pagamento), responde e só então faz um micro-passo. Decidido: pode passar faixa de preço.
2. **Usa o nome do WhatsApp apesar da regra** ("Boa noite, Ls!"). *Correção:* checagem no Pós-processador.
3. **Leitura de contexto fraca.** "Bom diaaaa" virou "Que bom que está animado para trocar de celular!".
   Modelo atual: gpt-4.1-mini, temperatura 0.3. *Correção:* migrar o agente para modelo melhor no
   turno de resposta (o extrator pode continuar barato).
4. **Formato inconsistente:** muitas respostas sem `|||` e com `\n\n`, saindo como bloco único.
5. **Nenhum follow-up.** "Vou ver se tô conseguindo" encerrou a conversa. A TX mostra 232 leads em
   Follow-up e uma etapa de Remarketing. *Correção:* workflow de reengajamento 24h e 72h para quem
   parou em CONSIDERANDO ou COLETANDO_DADOS (dentro da janela de 24h do WhatsApp ou via template).
6. **Não sabemos quem comprou.** `visita_agendada` tem 0 linhas e `valor_compra` nunca foi preenchido.
   *Correção:* o vendedor marca "vendeu / não vendeu / valor" com um comando no DeskRio ou link curto.
   Sem isso não existe "Fechamentos" nem ROI.
7. **Oportunidades jogadas fora.** Cliente quis mandar documento para pré-análise e a IA recusou.
   Já temos upload de documento para o Storage no fluxo; dá para transformar em pré-cadastro.
8. **Falhas de registro.** Estágios não gravados de 18/06 a 02/07; nenhuma mensagem `[FOTO_DO_CLIENTE]`
   no `interacao_log` (a trilha de imagem precisa ser verificada).

## 4. Proposta para levar ao cliente

**Fase 1 (1 semana): painel.**
- Função `senhor_smart.painel_cliente(inicio, fim)` (`sql/painel_cliente.sql`).
- Edge Function no Supabase que valida um token por cliente e devolve o JSON.
- O `dashboard/index.html` passa a buscar esse JSON com filtro de período (Hoje, 7d, 15d, 30d).
- n8n agendado toda segunda envia no WhatsApp do dono: resumo da semana + link do painel.

**Fase 2 (2 semanas): fechar o ciclo.**
- Registro de venda pelo vendedor → painel mostra Fechamentos, ticket médio e receita por campanha.
- Follow-up automático 24h/72h.
- Pós-processador com checagem de nome, formato e resposta direta.

**Fase 3: IA de verdade.**
- Responde primeiro, conduz depois; modelo melhor no turno de resposta.
- Visão aplicada ao aparelho (estado da tela, modelo, avaria) se a assistência entrar no escopo.
- Pré-cadastro com documento para acelerar a análise na loja.

**Argumento de venda:** a TX mostra quantos leads entraram. A gente mostra por que eles compram ou não
(iPhone, modelo fora do catálogo, horário, dor declarada) e trabalha a madrugada e o domingo,
que são 38% da demanda.

## 5. Segurança e LGPD (resolver antes de enviar qualquer link)

- O papel `anon` do Supabase tem SELECT em todas as tabelas de `senhor_smart`, sem RLS.
  Elas guardam telefone, nome e texto de conversa (inclusive número de documento enviado por cliente).
  Ver bloco comentado no fim de `sql/painel_cliente.sql`.
- O painel só usa agregados. Nunca expor telefone ou mensagem no link do cliente.
- Os 1.270 telefones no banco são dados dos clientes da Senhor Smart. Uso para remarketing só com
  autorização do dono e dentro do propósito original do atendimento.
