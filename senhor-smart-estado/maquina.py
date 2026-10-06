"""
Maquina de estado da Senhor Smart (assistencia tecnica) — servico senhor-smart-estado.

Framework v1.2 (MP AI Platform): LLM interpreta, schema restringe, codigo decide.
  Extrator (fora daqui) -> leitura
  Carregar Contexto (SQL, cego ao estado) -> contexto_dados
  Maquina (aqui) -> resolve entidades, decide o movimento do turno, calcula metricas
  Narrador (fora daqui) -> so narra a conducao

Banco = dado. Maquina = decisao. LLM = fala.

Contrato de entrada:
  {
    "ticket_id": int,
    "estado": {...} | None,           # None no 1o turno (o shape inicial e daqui)
    "leitura": {...},                 # saida do extrator (schema leitura_assistencia)
    "foto": {...} | None,             # saida do no de visao, quando o cliente mandou imagem
    "contexto_dados": {...},          # recorte do Carregar Contexto
    "agora": "ISO8601",               # horario da mensagem
    "mensagem_texto": str | None,     # body.lastMessage (duplicata)
    "mensagem_data": str | None,      # body.lastMessageDate (duplicata)
    "anuncio": str | None,            # titulo/ctwa do anuncio, quando veio de clique
    "primeira_mensagem": str | None   # texto cru do 1o turno (origem por mensagem pronta)
  }
Saida:
  {"estado_novo": {...}, "conducao": {...}, "metricas": {...}}
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

VERSAO = "1.0.0"
TZ = ZoneInfo("America/Sao_Paulo")

ETAPAS = ["novo", "triagem", "diagnostico", "orcamento", "agendado"]
INTENCOES_CRITICAS = {"reclamacao", "status_servico"}
MAX_PERGUNTAS_MODELO = 2          # depois disso, segue sem preco (avaliacao na loja)
SENTIMENTOS_ACOLHER = {"ansioso", "frustrado", "irritado"}
PERGUNTAS_FACTUAIS = {
    # pergunta do cliente -> chave em loja (fato autorizado) ou None quando vem de outro lugar
    "endereco": "endereco",
    "horario": "horario_texto",
    "garantia": "garantia_servico",
    "pagamento": "formas_pagamento",
    "diagnostico": "diagnostico",
    "leva_e_traz": "leva_e_traz",
    "prazo": None,                # prazo do servico em foco
}


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def _regex_pg(padrao: str) -> re.Pattern:
    """Padroes do banco usam a sintaxe do Postgres (\\m e \\M = limite de palavra)."""
    return re.compile(padrao.replace("\\m", "\\b").replace("\\M", "\\b"), re.IGNORECASE)


def _ilike(texto: str, padrao: str) -> bool:
    rx = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in _norm(padrao))
    return re.fullmatch(rx, _norm(texto), re.DOTALL) is not None


def _brl(v) -> str:
    return "R$ " + f"{int(round(float(v))):,}".replace(",", ".")


def _primeiro_nome(nome: str | None) -> str | None:
    if not nome:
        return None
    m = re.search(r"[A-Za-zÀ-ÿ]{2,}", nome)
    return m.group(0).capitalize() if m else None


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
def _estado_inicial() -> dict:
    return {
        "versao": VERSAO,
        "turnos": 0,
        "cliente": {"nome": None},
        "origem": None,                 # {"canal", "campanha"}
        "primeira_msg_em": None,
        "fora_horario_inicio": None,
        "trabalhos": [],                # ver _novo_trabalho
        "foco_atual": None,
        "abertura_feita": False,
        "fatos_informados": [],         # fatos da loja ja ditos (nao repetir)
        "convite_visita_feito": False,
        "objecao_tratada": False,
        "nao_atende_avisado": [],
        "visita": None,                 # {"quando"}
        "etapa": "novo",
        "etapa_max": "novo",
        "transferido": False,
        "encerrado": False,
        "_ultima_mensagem_texto": None,
        "_ultima_mensagem_data": None,
    }


def _novo_trabalho(estado: dict, categoria: str | None) -> dict:
    n = len(estado["trabalhos"]) + 1
    t = {
        "id": f"{categoria or 'indefinido'}:{n}",
        "categoria": categoria,
        "marca": None,
        "modelo": None,
        "linha": None,
        "modelo_status": "insuficiente",     # resolvido | insuficiente
        "defeito": None,
        "danos_foto": [],
        "servico_sugerido": None,
        "servico_id": None,
        "servico_status": "insuficiente",    # resolvido | ambiguo | insuficiente
        "servico_fonte": None,
        "servico_opcoes": [],
        "faixa": None,                       # {"min","max","validado"}
        "cotado": False,                     # orcamento/avaliacao ja comunicado
        "perguntas": {},                     # dado -> quantas vezes perguntado
        "status": "pendente",                # pendente | cotado | fora | encerrado
    }
    estado["trabalhos"].append(t)
    return t


def _pendentes(estado: dict) -> list[dict]:
    return [t for t in estado["trabalhos"] if t["status"] == "pendente"]


# ---------------------------------------------------------------------------
# Dado (le SO do contexto_dados que chegou; nunca o banco)
# ---------------------------------------------------------------------------
def _categoria(ctx: dict, cid: str | None) -> dict | None:
    return next((c for c in ctx.get("categorias", []) if c["id"] == cid), None)


def _servico(ctx: dict, sid: str | None) -> dict | None:
    return next((s for s in ctx.get("servicos", []) if s["id"] == sid), None)


def _precos(ctx: dict, sid: str) -> list[dict]:
    return [p for p in ctx.get("precos", []) if p["servico_id"] == sid]


def _preco_independe_de_modelo(ctx: dict, sid: str) -> bool:
    return any(p["linha"] is None for p in _precos(ctx, sid))


def _cotar(ctx: dict, sid: str, linha: str | None) -> dict | None:
    ps = _precos(ctx, sid)
    exato = next((p for p in ps if linha is not None and p["linha"] == linha), None)
    p = exato or next((p for p in ps if p["linha"] is None), None)
    if not p:
        return None
    return {"min": p["min"], "max": p["max"], "validado": bool(p.get("validado"))}


# ---------------------------------------------------------------------------
# Resolvedor: modelo e servico (evidencia deterministica antes do LLM)
# ---------------------------------------------------------------------------
def resolver_modelo(ctx: dict, texto: str | None, categoria: str | None) -> dict | None:
    t = _norm(texto)
    if not t:
        return None
    modelos = sorted(ctx.get("modelos", []), key=lambda m: m.get("prioridade", 100))
    for m in modelos:
        if categoria and m["categoria"] != categoria:
            continue
        g = _regex_pg(m["padrao"]).search(t)
        if g:
            grupo = (g.group(1) if g.groups() and g.group(1) else "").upper()
            return {"categoria": m["categoria"], "marca": m["marca"],
                    "modelo": m["exibicao"].replace("\\1", grupo).strip(), "linha": m["linha"]}
    return None


def resolver_servico(ctx: dict, trabalho: dict) -> None:
    """RESOLVED / AMBIGUOUS / INSUFFICIENT. Sintoma no texto do cliente e evidencia
    deterministica; a sugestao do extrator so desempata ou preenche quando nao ha sintoma."""
    cat, defeito = trabalho["categoria"], trabalho["defeito"]
    sugerido = trabalho.get("servico_sugerido")
    candidatos = [s for s in ctx.get("servicos", []) if s["categoria"] == cat]
    if not cat or not defeito:
        trabalho.update(servico_id=None, servico_status="insuficiente", servico_fonte=None, servico_opcoes=[])
        return
    texto = _norm(defeito + " " + " ".join(trabalho.get("danos_foto") or []))
    placar = []
    for s in candidatos:
        n = sum(1 for x in s["sintomas"] if _norm(x) and _norm(x) in texto)
        if n:
            placar.append((n, s["id"]))
    if placar:
        topo = max(n for n, _ in placar)
        empatados = [sid for n, sid in placar if n == topo]
        if len(empatados) == 1:
            trabalho.update(servico_id=empatados[0], servico_status="resolvido", servico_fonte="sintoma", servico_opcoes=[])
        elif sugerido in empatados:
            trabalho.update(servico_id=sugerido, servico_status="resolvido", servico_fonte="sintoma+extrator", servico_opcoes=[])
        else:
            trabalho.update(servico_id=None, servico_status="ambiguo", servico_fonte="sintoma", servico_opcoes=empatados[:3])
        return
    if sugerido and any(s["id"] == sugerido for s in candidatos):
        trabalho.update(servico_id=sugerido, servico_status="resolvido", servico_fonte="extrator", servico_opcoes=[])
        return
    trabalho.update(servico_id=None, servico_status="insuficiente", servico_fonte=None, servico_opcoes=[])


# ---------------------------------------------------------------------------
# Horario e origem
# ---------------------------------------------------------------------------
def _agora(entrada: dict) -> datetime:
    bruto = entrada.get("agora")
    try:
        dt = datetime.fromisoformat(bruto) if bruto else datetime.now(TZ)
    except (TypeError, ValueError):
        dt = datetime.now(TZ)
    return (dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt).astimezone(TZ)


def _hhmm(s: str | None) -> time | None:
    return time.fromisoformat(s) if s else None


def situacao_horario(ctx: dict, agora: datetime) -> dict:
    horarios = {h["dia_semana"]: h for h in ctx.get("horario", [])}
    feriados = {f["data"] for f in ctx.get("feriados", [])}

    def expediente(d: date):
        h = horarios.get((d.weekday() + 1) % 7)  # banco: 0 = domingo
        if not h or h.get("fechado") or not h.get("abre") or d.isoformat() in feriados:
            return None
        return _hhmm(h["abre"]), _hhmm(h["fecha"])

    hoje = agora.date()
    exp = expediente(hoje)
    aberto = bool(exp and exp[0] <= agora.time() < exp[1])
    proxima = None
    if not aberto:
        dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        for i in range(0, 8):
            d = hoje + timedelta(days=i)
            e = expediente(d)
            if not e or (i == 0 and agora.time() >= e[0]):
                continue
            rotulo = "hoje" if i == 0 else "amanhã" if i == 1 else dias[d.weekday()]
            proxima = f"{rotulo} às {e[0].strftime('%Hh%M').replace('h00', 'h')}"
            break
    return {"aberto": aberto, "proxima_abertura": proxima}


def detectar_origem(ctx: dict, primeira_mensagem: str | None, anuncio: str | None) -> dict:
    for r in sorted(ctx.get("origem_regra", []), key=lambda r: r["prioridade"]):
        if r["campo"] == "anuncio" and anuncio:
            return {"canal": r["canal"], "campanha": anuncio or r["campanha"]}
        if r["campo"] == "mensagem" and primeira_mensagem and _ilike(primeira_mensagem, r["padrao"]):
            return {"canal": r["canal"], "campanha": r["campanha"]}
    return {"canal": "organico", "campanha": None}


# ---------------------------------------------------------------------------
# Ingerir (SO ACRESCENTA / completa; nunca apaga trabalho)
# ---------------------------------------------------------------------------
def _equipamentos_do_turno(leitura: dict, foto: dict | None) -> list[dict]:
    eqs = [dict(e) for e in (leitura.get("equipamentos") or [])]
    if foto:
        eqs.append({
            "categoria": foto.get("categoria"), "marca": foto.get("marca"), "modelo": foto.get("modelo"),
            "defeito": None, "servico_sugerido": None, "danos_foto": foto.get("danos") or [],
            "fonte": "foto",
        })
    return eqs


def _alvo(estado: dict, categoria: str | None) -> dict | None:
    pend = [t for t in estado["trabalhos"] if t["status"] in ("pendente", "cotado")]
    if categoria:
        mesmo = next((t for t in pend if t["categoria"] == categoria), None)
        if mesmo:
            return mesmo
        sem_cat = next((t for t in pend if t["categoria"] is None), None)
        return sem_cat
    foco = next((t for t in pend if t["id"] == estado.get("foco_atual")), None)
    if foco:
        return foco
    return pend[0] if len(pend) == 1 else None


def ingerir(estado: dict, leitura: dict, foto: dict | None, ctx: dict) -> list[dict]:
    """Devolve os trabalhos que mudaram neste turno."""
    mudaram = []
    for eq in _equipamentos_do_turno(leitura, foto):
        cat = eq.get("categoria") if _categoria(ctx, eq.get("categoria")) else None
        res = resolver_modelo(ctx, " ".join(x for x in (eq.get("marca"), eq.get("modelo")) if x), cat)
        if cat is None and res:
            cat = res["categoria"]
        if not any([cat, res, eq.get("defeito"), eq.get("danos_foto")]):
            continue
        t = _alvo(estado, cat) or _novo_trabalho(estado, cat)
        antes = (t["servico_id"], t["linha"])
        if cat and not t["categoria"]:
            t["categoria"] = cat
            t["id"] = f"{cat}:{t['id'].split(':')[-1]}"
        if res and res["categoria"] == t["categoria"]:
            t.update(marca=res["marca"], modelo=res["modelo"], linha=res["linha"], modelo_status="resolvido")
        elif eq.get("marca") or eq.get("modelo"):
            t["marca"] = t["marca"] or eq.get("marca")
            t["modelo"] = t["modelo"] or eq.get("modelo")
        if eq.get("defeito"):
            t["defeito"] = eq["defeito"]
        if eq.get("danos_foto"):
            t["danos_foto"] = list(dict.fromkeys((t.get("danos_foto") or []) + eq["danos_foto"]))
            t["defeito"] = t["defeito"] or ", ".join(eq["danos_foto"])
        if eq.get("servico_sugerido"):
            t["servico_sugerido"] = eq["servico_sugerido"]
        mudaram.append((t, antes))

    for t, antes in mudaram:
        _completar(t, ctx)
        if t["cotado"] and (t["servico_id"], t["linha"]) != antes:
            t["cotado"], t["status"] = False, "pendente"   # mudou o servico ou o modelo: cota de novo
    return [t for t, _ in mudaram]


def _completar(t: dict, ctx: dict) -> None:
    cat = _categoria(ctx, t["categoria"])
    if cat and not cat["atende"]:
        t["status"] = "fora"
        return
    if t["linha"] is None and t["categoria"] in ("notebook", "videogame", "computador"):
        t["linha"] = "padrao"
    resolver_servico(ctx, t)
    s = _servico(ctx, t["servico_id"])
    t["faixa"] = _cotar(ctx, s["id"], t["linha"]) if s and not s["exige_diagnostico"] else None


# ---------------------------------------------------------------------------
# Lacunas: o que falta para orientar este equipamento
# ---------------------------------------------------------------------------
def _precisa_modelo(t: dict, ctx: dict) -> bool:
    s = _servico(ctx, t["servico_id"])
    if not s or s["exige_diagnostico"] or t["linha"] is not None:
        return False
    if _preco_independe_de_modelo(ctx, s["id"]):
        return False
    return t["perguntas"].get("modelo", 0) < MAX_PERGUNTAS_MODELO


def _lacuna(t: dict, ctx: dict) -> str:
    if t["categoria"] is None:
        return "equipamento"
    if not t["defeito"]:
        return "defeito"
    if t["servico_status"] == "ambiguo":
        return "servico"
    if _precisa_modelo(t, ctx):
        return "modelo"
    return "pronto"


def _selecionar(estado: dict) -> dict | None:
    pend = _pendentes(estado)
    foco = next((t for t in pend if t["id"] == estado.get("foco_atual")), None)
    return foco or (pend[0] if pend else None)


def _coletar(t: dict | None, dado: str, ctx: dict) -> dict:
    vezes = (t or {}).get("perguntas", {}).get(dado, 0) if t else 0
    if t is not None:
        t["perguntas"][dado] = vezes + 1
    c = {"dado": dado, "re_perguntando": vezes > 0, "pode_mandar_foto": dado in ("modelo", "defeito")}
    if dado == "servico" and t:
        c["opcoes"] = [_servico(ctx, sid)["nome"] for sid in t["servico_opcoes"]]
    if dado == "equipamento":
        c["opcoes"] = [c_["nome"] for c_ in ctx.get("categorias", []) if c_["atende"]]
    return c


def _orientacao(t: dict, ctx: dict) -> dict:
    """Orcamento (faixa) quando autorizado; senao, avaliacao na loja."""
    s = _servico(ctx, t["servico_id"])
    cat = _categoria(ctx, t["categoria"]) or {}
    base = {"equipamento": cat.get("nome"), "modelo": t["modelo"], "defeito": t["defeito"],
            "servico": s["nome"] if s else None, "prazo": s["prazo"] if s else None,
            "observacao": s["observacao"] if s else None}
    if t["faixa"]:
        return {"tipo": "orcamento", **base,
                "faixa": f"entre {_brl(t['faixa']['min'])} e {_brl(t['faixa']['max'])}",
                "valor_final_na_avaliacao": True}
    motivo = ("servico_exige_avaliacao" if s and s["exige_diagnostico"]
              else "modelo_nao_identificado" if s else "defeito_precisa_de_avaliacao")
    return {"tipo": "avaliacao", **base, "faixa": None, "motivo": motivo}


# ---------------------------------------------------------------------------
# Fatos autorizados para responder perguntas diretas (responde primeiro, conduz depois)
# ---------------------------------------------------------------------------
def _responder(estado: dict, perguntas: list[str], ctx: dict, foco: dict | None) -> list[dict]:
    loja = ctx.get("loja", {})
    out = []
    for p in perguntas or []:
        if p not in PERGUNTAS_FACTUAIS:
            continue
        chave = PERGUNTAS_FACTUAIS[p]
        if p == "prazo":
            s = _servico(ctx, (foco or {}).get("servico_id"))
            valor = s["prazo"] if s else None
        else:
            valor = loja.get(chave)
        out.append({"pergunta": p, "fato": valor, "sem_informacao": valor is None})
        if valor is not None and p not in estado["fatos_informados"]:
            estado["fatos_informados"].append(p)
    return out


def _dados_visita(estado: dict, ctx: dict, horario: dict) -> dict:
    loja = ctx.get("loja", {})
    d = {"loja_aberta_agora": horario["aberto"], "proxima_abertura": horario["proxima_abertura"]}
    if "endereco" not in estado["fatos_informados"]:
        d["endereco"] = loja.get("endereco")
        estado["fatos_informados"].append("endereco")
    if "horario" not in estado["fatos_informados"]:
        d["horario"] = loja.get("horario_texto")
        estado["fatos_informados"].append("horario")
    return d


# ---------------------------------------------------------------------------
# Etapa do funil (codigo, nunca o LLM)
# ---------------------------------------------------------------------------
def _calcular_etapa(estado: dict) -> str:
    if estado.get("visita"):
        return "agendado"
    ativos = [t for t in estado["trabalhos"] if t["status"] != "fora"]
    if any(t["cotado"] for t in ativos):
        return "orcamento"
    if any(t["categoria"] and t["defeito"] for t in ativos):
        return "diagnostico"
    if any(t["categoria"] for t in ativos):
        return "triagem"
    return "novo"


def _rank(e: str) -> int:
    return ETAPAS.index(e) if e in ETAPAS else -1


# ---------------------------------------------------------------------------
# Decidir (orquestra o turno)
# ---------------------------------------------------------------------------
def _e_duplicata(entrada: dict) -> bool:
    estado = entrada.get("estado")
    texto, data = entrada.get("mensagem_texto"), entrada.get("mensagem_data")
    if not estado or not texto or not data:
        return False
    return estado.get("_ultima_mensagem_texto") == texto and estado.get("_ultima_mensagem_data") == data


def _transferir(estado: dict, ctx: dict, fila: str, motivo: str) -> dict:
    estado["transferido"] = True
    estado["encerrado"] = True
    return {"deve_transferir": True, "fila": fila,
            "transferir_para": (ctx.get("filas") or {}).get(fila), "motivo_transferencia": motivo}


def decidir(entrada: dict) -> dict:
    ctx = entrada.get("contexto_dados") or {}
    leitura = entrada.get("leitura") or {}

    if _e_duplicata(entrada):
        estado = deepcopy(entrada["estado"])
        return _finalizar(estado, {"movimento": None, "objetivo": "ignorar_duplicata"}, ctx, entrada,
                          eventos=[], duplicata=True)

    estado = deepcopy(entrada.get("estado")) or _estado_inicial()
    agora = _agora(entrada)
    horario = situacao_horario(ctx, agora)
    estado["turnos"] += 1
    if estado["turnos"] == 1:
        estado["primeira_msg_em"] = agora.isoformat()
        estado["fora_horario_inicio"] = not horario["aberto"]
        estado["origem"] = detectar_origem(ctx, entrada.get("primeira_mensagem") or entrada.get("mensagem_texto"),
                                           entrada.get("anuncio"))

    nome = _primeiro_nome(leitura.get("nome_informado"))
    if nome and not estado["cliente"]["nome"]:
        estado["cliente"]["nome"] = nome

    intencao = leitura.get("intencao") or "outro"
    sentimento = leitura.get("sentimento") or "neutro"
    saudar = not estado["abertura_feita"]
    etapa_antes = estado["etapa"]
    c: dict = {"saudar": saudar, "acolher": sentimento in SENTIMENTOS_ACOLHER}

    # 1. Fora do contrato da IA: reclamacao, andamento de servico, pessoa humana, compra
    if intencao in INTENCOES_CRITICAS:
        c.update(movimento="transfer", objetivo="acolher_e_encaminhar", acolher=True,
                 assunto=intencao, **_transferir(estado, ctx, "humano", intencao))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)
    if intencao == "pediu_humano":
        c.update(movimento="transfer", objetivo="encaminhar_atendente", **_transferir(estado, ctx, "humano", "pediu_humano"))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)
    if intencao == "comprar_aparelho":
        c.update(movimento="transfer", objetivo="encaminhar_vendas",
                 responder=[{"pergunta": "venda_aparelhos", "fato": ctx.get("loja", {}).get("venda_aparelhos"),
                             "sem_informacao": False}],
                 **_transferir(estado, ctx, "vendas", "comprar_aparelho"))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    # 2. Ingerir equipamentos (texto + foto) e resolver entidades
    ingerir(estado, leitura, entrada.get("foto"), ctx)

    # 3. Equipamento que a loja nao atende: avisa uma vez
    fora = [t for t in estado["trabalhos"] if t["status"] == "fora" and t["id"] not in estado["nao_atende_avisado"]]
    if fora:
        estado["nao_atende_avisado"] += [t["id"] for t in fora]
        c["nao_atende"] = {"equipamentos": [(_categoria(ctx, t["categoria"]) or {}).get("nome") for t in fora],
                           "atendemos": [x["nome"] for x in ctx.get("categorias", []) if x["atende"]]}

    foco = _selecionar(estado)
    if foco:
        estado["foco_atual"] = foco["id"]
    perguntas = leitura.get("perguntas") or []
    c["responder"] = _responder(estado, perguntas, ctx, foco) or None

    # 4. Cliente combinou ir a loja
    if intencao == "confirmar_visita" or (leitura.get("visita_texto") and any(t["cotado"] for t in estado["trabalhos"])):
        estado["visita"] = {"quando": leitura.get("visita_texto")}
        for t in estado["trabalhos"]:
            if t["status"] in ("pendente", "cotado"):
                t["status"] = "encerrado"
        c.update(movimento="confirm", objetivo="confirmar_visita", usar_nome=estado["cliente"]["nome"],
                 visita={"quando": leitura.get("visita_texto"), **_dados_visita(estado, ctx, horario)},
                 **_transferir(estado, ctx, "tecnico", "visita_combinada"))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    # 5. Despedida: encerra de verdade, sem empurrar visita
    if intencao == "despedida" or leitura.get("encerrar_conversa"):
        estado["encerrado"] = True
        c.update(movimento="close", objetivo="despedir", usar_nome=estado["cliente"]["nome"],
                 porta_aberta=any(t["cotado"] for t in estado["trabalhos"]))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    # 6. Objecao de preco depois do orcamento
    cotados = [t for t in estado["trabalhos"] if t["cotado"] and t["faixa"]]
    if intencao == "objecao_preco" and cotados:
        primeira = not estado["objecao_tratada"]
        estado["objecao_tratada"] = True
        c.update(movimento="explain", objetivo="tratar_objecao_preco", acolher=True,
                 objecao={"primeira_vez": primeira, "orcamento": _orientacao(cotados[0], ctx),
                          "garantia": ctx.get("loja", {}).get("garantia_servico"),
                          "insistir": False})
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    # 7. Conduzir o equipamento em foco: uma lacuna por turno
    if foco is None:
        if any(t["cotado"] for t in estado["trabalhos"]):
            c.update(movimento="answer" if c["responder"] else "recommend_next",
                     objetivo="aguardar_decisao", convidar_visita=False)
        else:
            c.update(movimento="welcome" if saudar else "clarify", objetivo="descobrir_equipamento",
                     coletar=_coletar(None, "equipamento", ctx))
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    lacuna = _lacuna(foco, ctx)
    if lacuna != "pronto":
        c.update(movimento="welcome" if saudar and estado["turnos"] == 1 and not foco["defeito"] else "clarify",
                 objetivo=f"perguntar_{lacuna}", coletar=_coletar(foco, lacuna, ctx),
                 equipamento_em_foco=_resumo_trabalho(foco, ctx))
        if c["coletar"]["dado"] == "modelo" and leitura.get("perguntas") and "preco" in leitura["perguntas"]:
            c["por_que_preciso"] = "o valor muda conforme o modelo"
        return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)

    orientacao = _orientacao(foco, ctx)
    foco["cotado"], foco["status"] = True, "cotado"
    proximo = _selecionar(estado)
    c.update(movimento="recommend_next", objetivo=orientacao["tipo"], orientacao=orientacao,
             convidar_visita=not estado["convite_visita_feito"] and proximo is None)
    if c["convidar_visita"]:
        estado["convite_visita_feito"] = True
        c["visita"] = _dados_visita(estado, ctx, horario)
    if proximo is not None:
        estado["foco_atual"] = proximo["id"]
        c["proximo_equipamento"] = _resumo_trabalho(proximo, ctx)
    return _finalizar(estado, c, ctx, entrada, eventos=[], etapa_antes=etapa_antes)


def _resumo_trabalho(t: dict, ctx: dict) -> dict:
    s = _servico(ctx, t["servico_id"])
    return {"equipamento": (_categoria(ctx, t["categoria"]) or {}).get("nome"), "modelo": t["modelo"],
            "defeito": t["defeito"], "servico": s["nome"] if s else None,
            "faixa": f"entre {_brl(t['faixa']['min'])} e {_brl(t['faixa']['max'])}" if t["faixa"] else None}


# ---------------------------------------------------------------------------
# Saida unica: conducao completa + estado + metricas
# ---------------------------------------------------------------------------
def _finalizar(estado: dict, c: dict, ctx: dict, entrada: dict, eventos: list, duplicata: bool = False,
               etapa_antes: str | None = None) -> dict:
    if not duplicata:
        estado["_ultima_mensagem_texto"] = entrada.get("mensagem_texto")
        estado["_ultima_mensagem_data"] = entrada.get("mensagem_data")
        if c.get("saudar"):
            estado["abertura_feita"] = True
        etapa = _calcular_etapa(estado)
        estado["etapa"] = etapa
        if _rank(etapa) > _rank(estado["etapa_max"]):
            estado["etapa_max"] = etapa
        if etapa_antes is not None and _rank(etapa) > _rank(etapa_antes):
            eventos = [e for e in ETAPAS[_rank(etapa_antes) + 1:_rank(etapa) + 1]]

    for k, v in {"movimento": None, "objetivo": None, "saudar": False, "acolher": False, "usar_nome": None,
                 "responder": None, "coletar": None, "orientacao": None, "visita": None, "nao_atende": None,
                 "deve_transferir": False, "fila": None, "transferir_para": None,
                 "motivo_transferencia": None}.items():
        c.setdefault(k, v)
    c["apresentar_ia"] = ctx.get("loja", {}).get("nome_ia") if c["saudar"] else None
    c["nao_afirmar"] = list(ctx.get("loja_a_confirmar") or [])
    c["duplicata"] = duplicata
    c["etapa"] = estado["etapa"]
    if c["deve_transferir"]:
        c["resumo_encaminhamento"] = {
            "cliente": estado["cliente"]["nome"], "origem": estado.get("origem"),
            "equipamentos": [_resumo_trabalho(t, ctx) for t in estado["trabalhos"] if t["status"] != "fora"],
            "visita": estado.get("visita"), "motivo": c["motivo_transferencia"],
        }
    return {"estado_novo": estado, "conducao": c, "metricas": _metricas(estado, c, ctx, entrada, eventos, duplicata)}


def _metricas(estado: dict, c: dict, ctx: dict, entrada: dict, eventos: list, duplicata: bool) -> dict:
    """Tudo o que o registrar_turno (SQL) grava. O SQL nao decide nada: so escreve isto."""
    leitura = entrada.get("leitura") or {}
    ativos = [t for t in estado["trabalhos"] if t["status"] != "fora"]
    principal = next((t for t in ativos if t["id"] == estado.get("foco_atual")), None) or (ativos[0] if ativos else None)
    origem = estado.get("origem") or {}
    return {
        "ticket_id": entrada.get("ticket_id"),
        "duplicata": duplicata,
        "primeiro_turno": estado["turnos"] == 1,
        "primeira_msg_em": estado.get("primeira_msg_em"),
        "canal": origem.get("canal"), "campanha": origem.get("campanha"),
        "fora_horario": estado.get("fora_horario_inicio"),
        "etapa": estado["etapa"], "etapa_max": estado["etapa_max"], "eventos_funil": eventos,
        "categoria": principal["categoria"] if principal else None,
        "marca": principal["marca"] if principal else None,
        "modelo": principal["modelo"] if principal else None,
        "linha": principal["linha"] if principal else None,
        "defeito": principal["defeito"] if principal else None,
        "servico_id": principal["servico_id"] if principal else None,
        "faixa_min": principal["faixa"]["min"] if principal and principal["faixa"] else None,
        "faixa_max": principal["faixa"]["max"] if principal and principal["faixa"] else None,
        "preco_validado": principal["faixa"]["validado"] if principal and principal["faixa"] else None,
        "equipamentos": len(ativos),
        "nome_cliente": estado["cliente"]["nome"],
        "visita_texto": (estado.get("visita") or {}).get("quando"),
        "transferido": bool(c.get("deve_transferir")),
        "fila": c.get("fila"), "motivo_transferencia": c.get("motivo_transferencia"),
        "intencao": leitura.get("intencao"), "sentimento": leitura.get("sentimento"),
        "pediu_preco": "preco" in (leitura.get("perguntas") or []),
        "objecao_preco": leitura.get("intencao") == "objecao_preco",
        "pediu_humano": leitura.get("intencao") == "pediu_humano",
        "reclamacao": leitura.get("intencao") in INTENCOES_CRITICAS,
        "foto": bool(entrada.get("foto")),
        "movimento": c.get("movimento"), "objetivo": c.get("objetivo"),
        "versao_maquina": VERSAO,
    }


# ---------------------------------------------------------------------------
# Follow-up (n8n agendado chama; a maquina decide se e o que mandar)
# ---------------------------------------------------------------------------
def decidir_followup(entrada: dict) -> dict:
    """
    Entrada: {estado, contexto_dados, agora, ultima_msg_cliente_em, followups_enviados}
    Janela do WhatsApp: mensagem livre so ate 24h da ultima mensagem do cliente.
      - 20h a 23h sem resposta, lead ativo -> lembrete (texto livre, narrador escreve)
      - 72h ou mais -> reengajar (exige template aprovado na Meta)
    No maximo 2 follow-ups por atendimento. Nunca fora do horario comercial.
    """
    estado = entrada.get("estado") or {}
    ctx = entrada.get("contexto_dados") or {}
    agora = _agora(entrada)
    if estado.get("encerrado") or estado.get("transferido") or estado.get("etapa") not in ("triagem", "diagnostico", "orcamento"):
        return {"enviar": False, "motivo": "lead_fora_de_followup"}
    if (entrada.get("followups_enviados") or 0) >= 2:
        return {"enviar": False, "motivo": "limite_atingido"}
    if not situacao_horario(ctx, agora)["aberto"]:
        return {"enviar": False, "motivo": "fora_do_horario"}
    try:
        ultima = datetime.fromisoformat(entrada["ultima_msg_cliente_em"]).astimezone(TZ)
    except (KeyError, TypeError, ValueError):
        return {"enviar": False, "motivo": "sem_data_da_ultima_mensagem"}
    horas = (agora - ultima).total_seconds() / 3600
    if 20 <= horas < 24 and (entrada.get("followups_enviados") or 0) == 0:
        tipo = "lembrete"
    elif horas >= 72:
        tipo = "reengajar_template"
    else:
        return {"enviar": False, "motivo": "fora_da_janela"}
    foco = next((t for t in estado.get("trabalhos", []) if t["status"] in ("pendente", "cotado")), None)
    return {"enviar": True, "tipo": tipo,
            "conducao": {"movimento": "recover", "objetivo": "retomar_atendimento",
                         "usar_nome": (estado.get("cliente") or {}).get("nome"),
                         "equipamento_em_foco": _resumo_trabalho(foco, ctx) if foco else None,
                         "etapa": estado.get("etapa"), "insistir": False}}


def processar(entrada: dict) -> dict:
    return decidir(entrada)
