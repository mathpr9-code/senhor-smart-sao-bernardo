"""Gera o código SDK do fluxo "Painel Senhor Smart" (link ao vivo). Uso: python build_painel.py <token>"""
import json, sys
from pathlib import Path
AQUI = Path(__file__).parent
TOKEN = sys.argv[1]
J = lambda v: json.dumps(v, ensure_ascii=False)
filtros = (AQUI / "ler_filtros.js").read_text().replace("__TOKEN__", TOKEN)
painel = (AQUI / "montar_painel.js").read_text()
PG = {"id": "O9soLH536pVD9my1", "name": "Postgres account"}
q = "SELECT senhor_smart_at.painel(($1::jsonb->>'inicio')::date, ($1::jsonb->>'fim')::date, null, ($1::jsonb->>'teste')::boolean) AS p;"
print(f"""import {{ workflow, node, trigger, ifElse }} from '@n8n/workflow-sdk';

const webhook = trigger({{ type: 'n8n-nodes-base.webhook', version: 2.1, config: {{ name: 'Webhook', parameters: {{ httpMethod: 'GET', path: 'painel-senhor-smart', responseMode: 'responseNode', options: {{}} }} }} }});
const filtros = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Ler filtros', parameters: {{ jsCode: {J(filtros)} }} }} }});
const valido = ifElse({{ version: 2.3, config: {{ name: 'Link válido?', parameters: {{ conditions: {{ options: {{ caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 3 }}, conditions: [{{ id: 'ok', leftValue: '={{{{ $json.ok }}}}', rightValue: '', operator: {{ type: 'boolean', operation: 'true', singleValue: true }} }}], combinator: 'and' }}, looseTypeValidation: true, options: {{}} }} }} }});
const consulta = node({{ type: 'n8n-nodes-base.postgres', version: 2.6, config: {{ name: 'Painel', parameters: {{ operation: 'executeQuery', query: {J(q)}, options: {{ queryReplacement: "={{{{ JSON.stringify({{ inicio: $json.inicio, fim: $json.fim, teste: $json.teste }}) }}}}" }} }}, credentials: {{ postgres: {J(PG)} }} }} }});
const montar = node({{ type: 'n8n-nodes-base.code', version: 2, config: {{ name: 'Montar Painel', parameters: {{ jsCode: {J(painel)} }} }} }});
const responder = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: 'Mostrar Painel', parameters: {{ respondWith: 'text', responseBody: '={{{{ $json.html }}}}', options: {{ responseCode: 200, responseHeaders: {{ entries: [{{ name: 'Content-Type', value: 'text/html; charset=utf-8' }}, {{ name: 'Cache-Control', value: 'no-store' }}] }} }} }} }} }});
const negar = node({{ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: {{ name: 'Link inválido', parameters: {{ respondWith: 'text', responseBody: '<!doctype html><meta charset="utf-8"><p style="font-family:system-ui;padding:24px">Link inválido ou expirado.</p>', options: {{ responseCode: 403, responseHeaders: {{ entries: [{{ name: 'Content-Type', value: 'text/html; charset=utf-8' }}] }} }} }} }} }});

export default workflow('painel-senhor-smart', 'Painel Senhor Smart (link ao vivo)')
  .add(webhook)
  .to(filtros)
  .to(valido.onTrue(consulta.to(montar).to(responder)).onFalse(negar));
""")
