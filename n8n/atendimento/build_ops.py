"""Gera as operações do update_workflow do n8n a partir dos arquivos versionados (prompts + scripts)."""
import json, re, sys
from pathlib import Path

AQUI = Path(__file__).parent
RAIZ = AQUI.parent.parent

def sem_chaves_duplas(js: str) -> str:
    """Dentro de uma expressão {{ }} do n8n, "}}" fecha a expressão antes da hora. Separa as chaves."""
    while "}}" in js or "{{" in js:
        js = js.replace("}}", "} }").replace("{{", "{ {")
    return js


def checar_expressoes(ops):
    """Toda expressão ={{ ... }} não pode ter {{ ou }} no meio (o n8n corta ali e dá 'invalid syntax')."""
    def varrer(v, onde):
        if isinstance(v, dict):
            for k, x in v.items(): varrer(x, onde + "/" + k)
        elif isinstance(v, list):
            for i, x in enumerate(v): varrer(x, onde + f"[{i}]")
        elif isinstance(v, str) and v.startswith("={{") and v.rstrip().endswith("}}"):
            miolo = v[3:v.rstrip().rfind("}}")]
            assert "}}" not in miolo and "{{" not in miolo, f"chaves duplas dentro da expressão em {onde}"
    for o in ops:
        varrer(o, o.get("nodeName") or o.get("node", {}).get("name", "?"))


def bloco(md: str, abertura: str) -> str:
    texto = (RAIZ / "prompts" / md).read_text()
    ini = texto.index(abertura) + len(abertura)
    return texto[ini:texto.index("\n```", ini)].strip("\n")

sys_extrator = bloco("extrator.md", "## System prompt\n\n```\n")
sys_extrator = sys_extrator[:sys_extrator.index("<catalogo>")].rstrip()
sys_sofia = bloco("narrador.md", "## System prompt\n\n```markdown\n")
schema = json.loads((RAIZ / "prompts" / "extrator.schema.json").read_text())
schema.pop("_nota", None)

expr_ext = (AQUI / "expr_extrator.js").read_text().strip()
expr_ext = expr_ext.replace("__SCHEMA__", sem_chaves_duplas(json.dumps(schema, ensure_ascii=False))).replace(
    "__SYSTEM__", json.dumps(sys_extrator, ensure_ascii=False))
expr = lambda f: "={{ " + (AQUI / f).read_text().strip() + " }}"
code = lambda f: (AQUI / f).read_text()

MAQUINA_URL = "https://senhor-smart-estado.mpstudio.ia.br/processar"
PG = {"postgres": {"id": "O9soLH536pVD9my1", "name": "Postgres account"}}

def cond(left, op):
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 3},
            "conditions": [{"id": "c-" + op, "leftValue": left, "rightValue": "",
                            "operator": {"type": "boolean", "operation": op, "singleValue": True}}],
            "combinator": "and"}, "looseTypeValidation": True, "options": {}}

lote1 = [
    # --- leitura -----------------------------------------------------------------
    {"type": "renameNode", "oldName": "Carregar Estado", "newName": "Carregar Estado + Catálogo"},
    {"type": "updateNodeParameters", "nodeName": "Carregar Estado + Catálogo", "replace": True, "parameters": {
        "operation": "executeQuery",
        "query": "SELECT senhor_smart_at.v1_carregar_estado($1::bigint) AS estado, senhor_smart_at.v1_catalogo_extrator() AS catalogo;",
        "options": {"queryReplacement": "={{ $('Webhook').first().json.body.ticketId }}"}}},
    {"type": "renameNode", "oldName": "Extrair Intencao com Contexto", "newName": "Extrair Intenção"},
    {"type": "setNodeParameter", "nodeName": "Extrair Intenção", "path": "/jsonBody", "value": "={{ " + expr_ext + " }}"},
    {"type": "setNodeSettings", "nodeName": "Extrair Intenção",
     "settings": {"retryOnFail": True, "maxTries": 2, "waitBetweenTries": 1000, "onError": "continueRegularOutput"}},
    {"type": "renameNode", "oldName": "Montar contexto", "newName": "Carregar Contexto"},
    {"type": "updateNodeParameters", "nodeName": "Carregar Contexto", "replace": True, "parameters": {
        "operation": "executeQuery", "query": "SELECT senhor_smart_at.v1_carregar_contexto(now()) AS contexto;", "options": {}}},
    # --- máquina -----------------------------------------------------------------
    {"type": "addNode", "node": {"name": "Máquina de Estado", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.4,
        "position": [5200, 860], "parameters": {
            "method": "POST", "url": MAQUINA_URL, "sendBody": True, "specifyBody": "json",
            "jsonBody": expr("expr_maquina.js"), "options": {"timeout": 10000}}}},
    {"type": "setNodeSettings", "nodeName": "Máquina de Estado",
     "settings": {"retryOnFail": True, "maxTries": 2, "waitBetweenTries": 1000, "onError": "continueErrorOutput"}},
    {"type": "removeConnection", "source": "Carregar Contexto", "target": "Dedup OK?"},
    {"type": "addConnection", "source": "Carregar Contexto", "target": "Máquina de Estado"},
    {"type": "addConnection", "source": "Máquina de Estado", "target": "Dedup OK?"},
    {"type": "addConnection", "source": "Máquina de Estado", "sourceIndex": 1, "target": "Liberar próxima mensagem do cliente"},
    {"type": "updateNodeParameters", "nodeName": "Dedup OK?", "replace": True,
     "parameters": cond("={{ $('Máquina de Estado').first().json.conducao.duplicata }}", "false")},
]

lote2 = [
    # --- narrador ----------------------------------------------------------------
    {"type": "renameNode", "oldName": "AI Agent", "newName": "Sofia"},
    {"type": "updateNodeParameters", "nodeName": "Sofia", "replace": True, "parameters": {
        "promptType": "define", "text": expr("expr_sofia.js"), "options": {}}},
    {"type": "renameNode", "oldName": "OpenRouter Chat Model", "newName": "GPT 4.1 mini"},
    {"type": "updateNodeParameters", "nodeName": "GPT 4.1 mini", "replace": True, "parameters": {
        "model": "openai/gpt-4.1-mini",
        "options": {"temperature": 0.4, "maxTokens": 350, "frequencyPenalty": 0.2}}},
    {"type": "removeNode", "nodeName": "Simple Memory"},
    {"type": "addNode", "node": {"name": "Memória Sofia", "type": "@n8n/n8n-nodes-langchain.memoryPostgresChat",
        "typeVersion": 1.4, "position": [6160, 848], "credentials": PG, "parameters": {
            "sessionIdType": "customKey", "sessionKey": "={{ String($('Webhook').first().json.body.ticketId) }}",
            "tableName": "senhor_smart_at.sofia_memoria", "contextWindowLength": 12}}},
    {"type": "addConnection", "source": "Memória Sofia", "target": "Sofia", "connectionType": "ai_memory"},
    # --- logs: turno + métricas numa chamada só ------------------------------------
    {"type": "renameNode", "oldName": "Classificar interação", "newName": "Montar Log do Turno"},
    {"type": "updateNodeParameters", "nodeName": "Montar Log do Turno", "replace": True,
     "parameters": {"jsCode": code("montar_log_turno.js")}},
    {"type": "renameNode", "oldName": "Logar no Supabase", "newName": "Registrar Turno e Métricas"},
    {"type": "updateNodeParameters", "nodeName": "Registrar Turno e Métricas", "replace": True, "parameters": {
        "operation": "executeQuery", "query": "SELECT senhor_smart_at.v1_registrar_turno($1::jsonb);",
        "options": {"queryReplacement": "={{ JSON.stringify($('Montar Log do Turno').first().json.payload) }}"}}},
    {"type": "setNodeSettings", "nodeName": "Registrar Turno e Métricas",
     "settings": {"executeOnce": True, "retryOnFail": True, "onError": "continueRegularOutput"}},
    {"type": "removeNode", "nodeName": "Upsert atendimento_log"},
    {"type": "addConnection", "source": "Registrar Turno e Métricas", "target": "Pós-processador"},
    {"type": "updateNodeParameters", "nodeName": "Pós-processador", "replace": True,
     "parameters": {"jsCode": code("pos_processador.js")}},
    # --- estado antes de soltar o lock ----------------------------------------------
    {"type": "removeConnection", "source": "Loop Mensagens", "target": "Liberar Lock"},
    {"type": "removeConnection", "source": "Liberar Lock", "target": "Atualizar Estado"},
    {"type": "removeConnection", "source": "Atualizar Estado", "target": "If"},
    {"type": "addConnection", "source": "Loop Mensagens", "target": "Atualizar Estado"},
    {"type": "addConnection", "source": "Atualizar Estado", "target": "Liberar Lock"},
    {"type": "addConnection", "source": "Liberar Lock", "target": "If"},
    {"type": "updateNodeParameters", "nodeName": "Atualizar Estado", "replace": True, "parameters": {
        "operation": "executeQuery",
        "query": "SELECT senhor_smart_at.v1_atualizar_estado(($1::jsonb->>'ticket_id')::bigint, $1::jsonb->'estado', ($1::jsonb->>'agora')::timestamptz);",
        "options": {"queryReplacement": "={{ JSON.stringify({ ticket_id: String($('Webhook').first().json.body.ticketId), estado: $('Máquina de Estado').first().json.estado_novo, agora: $now.setZone('America/Sao_Paulo').toISO() }) }}"}}},
    {"type": "setNodeSettings", "nodeName": "Liberar Lock", "settings": {"executeOnce": True}},
    # --- transferência + nota interna ------------------------------------------------
    {"type": "updateNodeParameters", "nodeName": "If", "replace": True,
     "parameters": cond("={{ $('Pós-processador').first().json.precisa_transferir }}", "true")},
    {"type": "setNodeParameter", "nodeName": "Transferencia", "path": "/jsonBody",
     "value": "={\n  \"queueId\": {{ Number($('Pós-processador').first().json.queueId) }}\n}"},
    {"type": "setNodeSettings", "nodeName": "Transferencia",
     "settings": {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000, "onError": "continueRegularOutput"}},
    {"type": "addNode", "node": {"name": "Montar Nota Interna", "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [8848, 752], "parameters": {"jsCode": code("montar_nota_interna.js")}}},
    {"type": "addConnection", "source": "Transferencia", "target": "Montar Nota Interna"},
]

# --- lote 4: começo do fluxo (foto do aparelho no lugar do caminho de documento) ---
visao_md = (RAIZ / "prompts" / "visao.md").read_text()
sys_visao = bloco("visao.md", "## System prompt\n\n```\n")
schema_visao = json.loads(visao_md[visao_md.index("```json\n") + 8:visao_md.index("\n```", visao_md.index("```json\n"))])
expr_foto = (AQUI / "expr_ler_foto.js").read_text().strip().replace(
    "__SCHEMA__", sem_chaves_duplas(json.dumps(schema_visao, ensure_ascii=False))).replace("__SYSTEM__", json.dumps(sys_visao, ensure_ascii=False))

def atrib(nome, valor, tipo="string"):
    return {"id": "f-" + nome, "name": nome, "value": valor, "type": tipo}

FOTO = "$('Interpretar Foto').isExecuted ? ($('Interpretar Foto').first().json.descricao_texto || '') : ''"
filtra = {"assignments": {"assignments": [
    atrib("message", "={{ (() => {\n  const candidatos = [\n    $json.text,\n    " + FOTO.replace(" : ''", " : null") + ",\n    $('Webhook').item.json.body?.lastMessage,\n    $('Webhook').item.json.body?.contact?.lastMessage,\n    typeof $json.body === 'string' ? $json.body : null,\n    $('Webhook').item.json.body?.body\n  ];\n  for (const c of candidatos) {\n    if (c === null || c === undefined) continue;\n    const s = String(c).trim();\n    if (s === '' || s === 'null' || s === 'undefined' || s === '[object Object]') continue;\n    return s;\n  }\n  return '[MEDIA]';\n})() }}"),
    atrib("Nome", "={{ $('Webhook').item.json.body.contact.name }}"),
    atrib("Ticketid", "={{ $('Webhook').item.json.body.ticketId }}", "number"),
    atrib("Audiomessage", "={{ $json.text || '' }}"),
    atrib("telefone", "={{ $('Webhook').item.json.body.contact.number }}"),
    atrib("imagem", "={{ " + FOTO + " }}"),
    atrib("legenda", "={{ (() => { const l = $('Webhook').item.json.body?.lastMediaMessage || ''; return (typeof l === 'string' && !l.startsWith('http')) ? l : ''; })() }}"),
    atrib("vemDeAnuncio", "={{ (() => {\n  const wb = $('Webhook').item.json.body;\n  if (!wb) return false;\n  if (wb.entryPointConversionSource === 'ctwa_ad') return true;\n  if (wb.ctwaclid && wb.ctwaclid !== '') return true;\n  if (wb.title && wb.title !== '' && wb.title !== 'null') return true;\n  return false;\n})() }}", "boolean"),
]}, "options": {}}

lote4 = [
    *[{"type": "removeNode", "nodeName": n} for n in
      ["É documento?", "Baixar imagem original", "Set filename documento", "Subir para Supabase Storage", "Set documento_url"]],
    {"type": "renameNode", "oldName": "Transcrever Imagem/Video", "newName": "Ler Foto"},
    {"type": "updateNodeParameters", "nodeName": "Ler Foto", "replace": True, "parameters": {
        "method": "POST", "url": "https://openrouter.ai/api/v1/chat/completions",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "openRouterApi",
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ " + expr_foto + " }}", "options": {"timeout": 30000}}},
    {"type": "setNodeCredential", "nodeName": "Ler Foto", "credentialKey": "openRouterApi",
     "credentialId": "r8UA8KIXE9HGOwuj", "credentialName": "OR Teste"},
    {"type": "setNodeSettings", "nodeName": "Ler Foto",
     "settings": {"retryOnFail": True, "maxTries": 2, "waitBetweenTries": 1000, "onError": "continueRegularOutput"}},
    {"type": "renameNode", "oldName": "Parse classificação imagem", "newName": "Interpretar Foto"},
    {"type": "updateNodeParameters", "nodeName": "Interpretar Foto", "replace": True,
     "parameters": {"jsCode": code("interpretar_foto.js")}},
    {"type": "addConnection", "source": "Interpretar Foto", "target": "Filtra webhook"},
    {"type": "updateNodeParameters", "nodeName": "Filtra webhook", "replace": True, "parameters": filtra},
    {"type": "setNodeParameter", "nodeName": "Máquina de Estado", "path": "/jsonBody", "value": expr("expr_maquina.js")},
    {"type": "updateNodeParameters", "nodeName": "Montar Log do Turno", "replace": True,
     "parameters": {"jsCode": code("montar_log_turno.js")}},
]

# --- lote 5: post-its (zona) + notas de documentação, padrão Lívia/Nexfar ---
def altura(md, largura):
    por_linha = max((largura - 48) // 8, 20)
    linhas = sum(max(1, -(-len(l) // por_linha)) for l in md.splitlines())
    return max(320, linhas * 25 + 100)

ZONAS = [  # sticky de zona, nota Doc, arquivo, título, x, largura, cor
    ("Sticky Note", "Doc Recebe", "1_recebe.md", "Recebe Mensagens + Tratamento (texto, áudio, foto do aparelho)", 16, 2320, None, 1424),
    ("Sticky Note1", "Doc Buffer", "2_buffer.md", "Buffer de Mensagens", 2416, 2128, 2, 1136),
    ("Sticky Note2", "Doc Estado", "3_estado.md", "Controle de Estado — Extrator + Máquina de Estado", 4608, 1120, 5, 1136),
    ("Sticky Note3", "Doc IA", "4_ia.md", "IA — Sofia (só narra)", 5776, 752, 4, 1136),
    ("Sticky Note4", "Doc Metricas", "5_logs.md", "Logs do Turno + Métricas do Painel", 6592, 1120, 6, 1136),
    ("Sticky Note5", "Doc Envio", "6_envio.md", "Envio para DeskRio + Estado + Transferência + Nota Interna", 7776, 1520, 3, 1136),
]
lote5 = []
for zona, doc, arq, titulo, x, w, cor, y in ZONAS:
    md = (AQUI / "notas" / arq).read_text().strip()
    lote5.append({"type": "updateNodeParameters", "nodeName": zona, "parameters": {"content": titulo, "width": w}})
    lote5.append({"type": "updateNodeParameters", "nodeName": doc,
                  "parameters": {"content": md, "width": w, "height": altura(md, w), "color": 7}})
    lote5.append({"type": "setNodePosition", "nodeName": doc, "position": [x, y]})

lote5.append({"type": "setNodeParameter", "nodeName": "If1", "path": "/looseTypeValidation", "value": True})

lote3 = [{"type": "setNodeParameter", "nodeName": "Sofia", "path": "/options/systemMessage", "value": sys_sofia}]

for _lote in (lote1, lote2, lote3, lote4, lote5):
    checar_expressoes(_lote)

if __name__ == "__main__":
    lote = {"1": lote1, "2": lote2, "3": lote3, "4": lote4, "5": lote5}[sys.argv[1]]
    print(json.dumps(lote, ensure_ascii=False))
