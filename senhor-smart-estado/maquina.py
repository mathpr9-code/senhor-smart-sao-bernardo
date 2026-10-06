"""
Maquina de estado da Senhor Smart (assistencia tecnica) — servico senhor-smart-estado.

Framework v1.2 (MP AI Platform): LLM interpreta, schema restringe, codigo decide.
  Extrator (GPT-5.4-mini, fora daqui) -> leitura
  Carregar Contexto (SQL, cego ao estado) -> contexto_dados
  Maquina (aqui) -> resolve entidades, decide o movimento do turno, calcula metricas
  Narrador (GPT-4.1-mini, fora daqui) -> so narra a conducao

Regra da conducao (ADR-0013): a maquina entrega DADO e ORIENTACAO, nunca frase pronta.
O narrador e literal: frase pronta aqui vira frase copiada la.

Contrato de entrada:
  {
    "ticket_id": int,
    "estado": {...} | None,           # None no 1o turno (o shape inicial e daqui)
    "leitura": {...},                 # saida do extrator (schema leitura_assistencia)
    "foto": {...} | None,             # saida do no de visao (so quando tipo == aparelho)
    "contexto_dados": {...},          # recorte do Carregar Contexto
    "agora": "ISO8601",               # horario da mensagem
    "nome_whatsapp": str | None,      # nome do contato no WhatsApp (pode vir emoji, numero...)
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

VERSAO = "1.1.0"
TZ = ZoneInfo("America/Sao_Paulo")

ETAPAS = ["novo", "triagem", "diagnostico", "orcamento", "agendado"]
INTENCOES_CRITICAS = {"reclamacao", "status_servico"}
MAX_PERGUNTAS_MODELO = 2          # depois disso, segue sem preco (avaliacao na loja)
SENTIMENTOS_ACOLHER = {"ansioso", "frustrado", "irritado"}
DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
NOMES_GENERICOS = {"cliente", "contato", "whatsapp", "usuario", "user", "teste", "loja", "celular", "eu", "oi", "ola"}
# pergunta do cliente -> chave de fato em loja (None = vem de outro lugar)
PERGUNTAS_FACTUAIS = {
    "endereco": "endereco", "horario": None, "garantia": "garantia_servico", "pagamento": "formas_pagamento",
    "diagnostico": "avaliacao_sem_custo", "leva_e_traz": "leva_e_traz", "prazo": None,
}
OBJECAO_LEGADA = {"objecao_preco": "preco_alto"}


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


def _tem_termo(texto_norm: str, termo: str) -> bool:
    """Termo inteiro (palavra ou expressao), nunca pedaco de outra palavra: 'mar' nao casa 'marcar'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(_norm(termo)) + r"(?![a-z0-9])", texto_norm) is not None


def nome_valido(nome: str | None) -> str | None:
    """Primeiro nome utilizavel, ou None quando o nome do WhatsApp e emoji, numero, sigla ou generico."""
    if not nome:
        return None
    m = re.match(r"\s*([A-Za-zÀ-ÿ]{2,})", nome)
    if not m:
        return None
    primeiro = m.group(1)
    if _norm(primeiro) in NOMES_GENERICOS or primeiro.isupper() and len(primeiro) <= 3:
        return None
    return primeiro.capitalize()


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
def _estado_inicial() -> dict:
    return {
        "versao": VERSAO,
        "turnos": 0,
        "cliente": {"nome": None, "nome_fonte": None, "nome_perguntado": False},
        "origem": None,                 # {"canal", "campanha"}
        "primeira_msg_em": None,
        "fora_horario_inicio": None,
        "impacto": None,                # o que o problema esta custando ao cliente (palavras dele)
        "trabalhos": [],                # ver _novo_trabalho
        "foco_atual": None,
        "abertura_feita": False,
        "fatos_informados": [],         # fatos da loja ja ditos (nao repetir)
        "convite_visita_feito": False,
        "objecoes": {},                 # codigo -> vezes tratada
        "nao_atende_avisado": [],
        "visita": None,                 # {"quando", "combinada_em"}
        "lembrete_visita_enviado": False,
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
        "marca": None, "modelo": None, "linha": None,
        "modelo_status": "insuficiente",     # resolvido | insuficiente
        "defeito": None,
        "danos_foto": [],
        "servico_sugerido": None,
        "servico_id": None,
        "servico_status": "insuficiente",    # resolvido | ambiguo | avaliacao | insuficiente
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


def _horario_loja(ctx: dict) -> list[dict]:
    """Horario como dado: [{dias: [...], abre, fecha}] agrupando dias iguais."""
    grupos: list[dict] = []
    por_dia = {h["dia_semana"]: h for h in ctx.get("horario", [])}
    for i, nome in enumerate(DIAS):
        h = por_dia.get((i + 1) % 7)
        if not h or h.get("fechado"):
            continue
        if grupos and grupos[-1]["abre"] == h["abre"] and grupos[-1]["fecha"] == h["fecha"]:
            grupos[-1]["dias"].append(nome)
        else:
            grupos.append({"dias": [nome], "abre": h["abre"], "fecha": h["fecha"]})
    return grupos


# ---------------------------------------------------------------------------
# Resolvedor: modelo e servico (evidencia deterministica antes do LLM)
# ---------------------------------------------------------------------------
def resolver_modelo(ctx: dict, texto: str | None, categoria: str | None) -> dict | None:
    t = _norm(texto)
    if not t:
        return None
    for m in sorted(ctx.get("modelos", []), key=lambda m: m.get("prioridade", 100)):
        if categoria and m["categoria"] != categoria:
            continue
        g = _regex_pg(m["padrao"]).search(t)
        if g:
            grupo = (g.group(1) if g.groups() and g.group(1) else "").upper()
            return {"categoria": m["categoria"], "marca": m["marca"],
                    "modelo": m["exibicao"].replace("\\1", grupo).strip(), "linha": m["linha"]}
    return None


def resolver_servico(ctx: dict, trabalho: dict) -> None:
    """resolvido / ambiguo / avaliacao / insuficiente. Sintoma no texto do cliente e evidencia
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
        n = sum(1 for x in s["sintomas"] if _norm(x) and _tem_termo(texto, x))
        if n:
            placar.append((n, s["id"]))
    if placar:
        topo = max(n for n, _ in placar)
        empatados = [sid for n, sid in placar if n == topo]
        if len(empatados) == 1:
            trabalho.update(servico_id=empatados[0], servico_status="resolvido", servico_fonte="sintoma", servico_opcoes=[])
        elif sugerido in empatados:
            trabalho.update(servico_id=sugerido, servico_status="resolvido", servico_fonte="sintoma+extrator", servico_opcoes=[])
        elif all((_servico(ctx, sid) or {}).get("exige_diagnostico") for sid in empatados):
            # empate entre servicos que exigem avaliacao de todo jeito: perguntar ao cliente nao ajuda
            trabalho.update(servico_id=None, servico_status="avaliacao", servico_fonte="sintoma", servico_opcoes=empatados)
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


def periodo_do_dia(agora: datetime) -> str:
    h = agora.hour
    return "bom_dia" if 5 <= h < 12 else "boa_tarde" if 12 <= h < 18 else "boa_noite"


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
        for i in range(0, 8):
            d = hoje + timedelta(days=i)
            e = expediente(d)
            if not e or (i == 0 and agora.time() >= e[0]):
                continue
            proxima = {"dia": "hoje" if i == 0 else "amanha" if i == 1 else DIAS[d.weekday()],
                       "hora": e[0].strftime("%H:%M")}
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
    if foto and foto.get("tipo", "aparelho") == "aparelho":
        eqs.append({"categoria": foto.get("categoria"), "marca": foto.get("marca"), "modelo": foto.get("modelo"),
                    "defeito": None, "servico_sugerido": None, "danos_foto": foto.get("danos") or []})
    return eqs


def _alvo(estado: dict, categoria: str | None) -> dict | None:
    pend = [t for t in estado["trabalhos"] if t["status"] in ("pendente", "cotado")]
    if categoria:
        mesmo = next((t for t in pend if t["categoria"] == categoria), None)
        return mesmo or next((t for t in pend if t["categoria"] is None), None)
    foco = next((t for t in pend if t["id"] == estado.get("foco_atual")), None)
    if foco:
        return foco
    return pend[0] if len(pend) == 1 else None


def ingerir(estado: dict, leitura: dict, foto: dict | None, ctx: dict) -> list[dict]:
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
            t["cotado"], t["status"] = False, "pendente"   # mudou o servico ou o modelo: orienta de novo
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


def _coletar(t: dict | None, dado: str, ctx: dict, motivo: str | None = None) -> dict:
    vezes = t["perguntas"].get(dado, 0) if t else 0
    if t is not None:
        t["perguntas"][dado] = vezes + 1
    c = {"dado": dado, "re_perguntando": vezes > 0, "pode_mandar_foto": dado in ("modelo", "defeito"),
         "motivo": motivo}
    if dado == "servico" and t:
        c["opcoes"] = [_servico(ctx, sid)["nome"] for sid in t["servico_opcoes"]]
    if dado == "equipamento":
        c["opcoes"] = [c_["nome"] for c_ in ctx.get("categorias", []) if c_["atende"]]
    return c


def _detalhes(ctx: dict, sids: list[str]) -> dict:
    """Une os detalhes estruturados dos servicos (pode_ser, cuidados, inclui, beneficio...)."""
    out: dict = {}
    for sid in sids:
        for k, v in ((_servico(ctx, sid) or {}).get("detalhes") or {}).items():
            if isinstance(v, list):
                out[k] = list(dict.fromkeys(out.get(k, []) + v))
            else:
                out.setdefault(k, v)
    return out


def _orientacao(t: dict, ctx: dict, estado: dict) -> dict:
    """Dado para o narrador orientar o equipamento: faixa (numeros) ou avaliacao, detalhes e desejo."""
    s = _servico(ctx, t["servico_id"])
    sids = [s["id"]] if s else list(t.get("servico_opcoes") or [])
    o = {"equipamento": (_categoria(ctx, t["categoria"]) or {}).get("nome"), "modelo": t["modelo"],
         "defeito_relatado": t["defeito"], "danos_na_foto": t.get("danos_foto") or None,
         "servico": s["nome"] if s else None, "prazo": s["prazo"] if s else None,
         "detalhes": _detalhes(ctx, sids) or None,
         "desejo": {"impacto_relatado": estado.get("impacto"),
                    "beneficio": _detalhes(ctx, sids).get("beneficio")}}
    if t["faixa"]:
        return {"tipo": "orcamento", **o, "faixa": {"min": t["faixa"]["min"], "max": t["faixa"]["max"]},
                "valor_final_na_avaliacao": True}
    if not s and t.get("servico_opcoes"):
        o["possibilidades"] = [_servico(ctx, sid)["nome"] for sid in t["servico_opcoes"] if _servico(ctx, sid)]
    motivo = ("servico_exige_avaliacao" if s and s["exige_diagnostico"]
              else "modelo_nao_identificado" if s else "defeito_precisa_de_avaliacao")
    return {"tipo": "avaliacao", **o, "faixa": None, "motivo": motivo}


# ---------------------------------------------------------------------------
# Fatos autorizados (responde primeiro, conduz depois)
# ---------------------------------------------------------------------------
def _fato(ctx: dict, chave: str):
    """Fato autorizado ou None. Fatos nao confirmados nunca saem daqui."""
    if chave == "horario_texto":
        return _horario_loja(ctx)
    return (ctx.get("loja") or {}).get(chave)


def _responder(estado: dict, perguntas: list[str], ctx: dict, foco: dict | None) -> list[dict]:
    out = []
    for p in perguntas or []:
        if p not in PERGUNTAS_FACTUAIS:
            continue
        if p == "prazo":
            s = _servico(ctx, (foco or {}).get("servico_id"))
            valor = s["prazo"] if s else None
        elif p == "horario":
            valor = _horario_loja(ctx)
        else:
            valor = _fato(ctx, PERGUNTAS_FACTUAIS[p])
        out.append({"pergunta": p, "dado": valor, "sem_informacao": valor is None})
        if valor is not None and p not in estado["fatos_informados"]:
            estado["fatos_informados"].append(p)
    return out


def _dados_visita(estado: dict, ctx: dict, horario: dict) -> dict:
    d = {"loja_aberta_agora": horario["aberto"], "proxima_abertura": horario["proxima_abertura"]}
    if "endereco" not in estado["fatos_informados"]:
        d["endereco"] = _fato(ctx, "endereco")
        d["referencia"] = _fato(ctx, "referencia_local")
        estado["fatos_informados"].append("endereco")
    if "horario" not in estado["fatos_informados"]:
        d["horario"] = _horario_loja(ctx)
        estado["fatos_informados"].append("horario")
    return d


# ---------------------------------------------------------------------------
# Objecoes (dado da biblioteca + fatos autorizados; nunca resposta pronta)
# ---------------------------------------------------------------------------
def _argumento(chave: str, ctx: dict, estado: dict, foco: dict | None, horario: dict):
    if chave == "valor_final_na_avaliacao":
        return True
    if chave == "prazo_servico":
        s = _servico(ctx, (foco or {}).get("servico_id"))
        return s["prazo"] if s else None
    if chave == "loja_aberta_agora":
        return horario["aberto"]
    return _fato(ctx, chave)


def tratar_objecao(estado: dict, codigo: str, ctx: dict, horario: dict) -> dict | None:
    obj = next((o for o in ctx.get("objecoes", []) if o["codigo"] == codigo), None)
    if not obj:
        return None
    vezes = estado["objecoes"].get(codigo, 0)
    estado["objecoes"][codigo] = vezes + 1
    cotados = [t for t in estado["trabalhos"] if t["cotado"]]
    foco = cotados[0] if cotados else _selecionar(estado)
    if vezes > 0:
        # segunda vez: nao argumenta de novo, nao convida de novo; respeita e deixa a porta aberta
        return {"codigo": codigo, "nome": obj["nome"], "primeira_vez": False, "insistir": False,
                "proximo_passo": "deixar_porta_aberta", "nunca": obj["nunca"]}
    args = []
    for chave in obj["argumentos"]:
        v = _argumento(chave, ctx, estado, foco, horario)
        if v is not None:
            args.append({"chave": chave, "dado": v})
    return {"codigo": codigo, "nome": obj["nome"], "primeira_vez": True, "insistir": False,
            "por_tras": obj["por_tras"], "explorar": obj.get("explorar"),
            "argumentos": args, "desejo": {"caminhos": obj["desejo"], "impacto_relatado": estado.get("impacto")},
            "orcamento": _orientacao(foco, ctx, estado) if foco and foco["cotado"] else None,
            "proximo_passo": obj["proximo_passo"], "nunca": obj["nunca"]}


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
                          duplicata=True)

    estado = deepcopy(entrada.get("estado")) or _estado_inicial()
    agora = _agora(entrada)
    horario = situacao_horario(ctx, agora)
    estado["turnos"] += 1
    if estado["turnos"] == 1:
        estado["primeira_msg_em"] = agora.isoformat()
        estado["fora_horario_inicio"] = not horario["aberto"]
        estado["origem"] = detectar_origem(ctx, entrada.get("primeira_mensagem") or entrada.get("mensagem_texto"),
                                           entrada.get("anuncio"))

    # Nome: o que o cliente disse vence o WhatsApp; WhatsApp so vale se for nome de verdade
    cliente = estado["cliente"]
    nome_dito = nome_valido(leitura.get("nome_informado"))
    nome_recem_informado = bool(nome_dito and cliente.get("nome_fonte") != "cliente")
    if nome_dito:
        cliente.update(nome=nome_dito, nome_fonte="cliente")
    elif not cliente["nome"] and nome_valido(entrada.get("nome_whatsapp")):
        cliente.update(nome=nome_valido(entrada.get("nome_whatsapp")), nome_fonte="whatsapp")
    if leitura.get("impacto"):
        estado["impacto"] = leitura["impacto"]

    intencao = leitura.get("intencao") or "outro"
    objecao_cod = leitura.get("objecao") or OBJECAO_LEGADA.get(intencao)
    if objecao_cod:
        intencao = "objecao"
    sentimento = leitura.get("sentimento") or "neutro"
    saudar = not estado["abertura_feita"]
    etapa_antes = estado["etapa"]
    c: dict = {"saudar": saudar, "periodo": periodo_do_dia(agora) if saudar else None,
               "acolher": sentimento in SENTIMENTOS_ACOLHER,
               "usar_nome": cliente["nome"] if (saudar or nome_recem_informado) else None,
               "nome_recem_informado": nome_recem_informado}

    def fim(**kw):
        c.update(kw)
        return _finalizar(estado, c, ctx, entrada, etapa_antes=etapa_antes)

    # 1. Fora do contrato da IA: reclamacao, andamento de servico, pessoa humana, compra
    if intencao in INTENCOES_CRITICAS:
        return fim(movimento="transfer", objetivo="acolher_e_encaminhar", acolher=True, assunto=intencao,
                   **_transferir(estado, ctx, "humano", intencao))
    if intencao == "pediu_humano":
        return fim(movimento="transfer", objetivo="encaminhar_atendente",
                   **_transferir(estado, ctx, "humano", "pediu_humano"))
    if intencao == "comprar_aparelho":
        return fim(movimento="transfer", objetivo="encaminhar_vendas",
                   responder=[{"pergunta": "venda_aparelhos", "dado": _fato(ctx, "venda_aparelhos"),
                               "sem_informacao": False}],
                   **_transferir(estado, ctx, "vendas", "comprar_aparelho"))

    # 2. Ingerir equipamentos (texto + foto) e resolver entidades. Nada que o cliente disse se perde.
    ingerir(estado, leitura, entrada.get("foto"), ctx)
    foco = _selecionar(estado)
    if foco:
        estado["foco_atual"] = foco["id"]
    c["responder"] = _responder(estado, leitura.get("perguntas") or [], ctx, foco) or None

    # 3. Nome desconhecido: pergunta antes de conduzir (responde a pergunta direta no mesmo turno)
    if not cliente["nome"] and not cliente["nome_perguntado"]:
        cliente["nome_perguntado"] = True
        return fim(movimento="welcome" if saudar else "clarify", objetivo="perguntar_nome",
                   coletar={"dado": "nome", "re_perguntando": False, "pode_mandar_foto": False, "motivo": None},
                   equipamento_ja_citado=_resumo_trabalho(foco, ctx) if foco else None)

    # 4. Equipamento que a loja nao atende: avisa uma vez
    fora = [t for t in estado["trabalhos"] if t["status"] == "fora" and t["id"] not in estado["nao_atende_avisado"]]
    if fora:
        estado["nao_atende_avisado"] += [t["id"] for t in fora]
        c["nao_atende"] = {"equipamentos": [(_categoria(ctx, t["categoria"]) or {}).get("nome") for t in fora],
                           "atendemos": [x["nome"] for x in ctx.get("categorias", []) if x["atende"]]}

    # 5. Cliente combinou ir a loja
    if intencao == "confirmar_visita" or (leitura.get("visita_texto") and any(t["cotado"] for t in estado["trabalhos"])):
        estado["visita"] = {"quando": leitura.get("visita_texto"), "combinada_em": agora.isoformat()}
        for t in estado["trabalhos"]:
            if t["status"] in ("pendente", "cotado"):
                t["status"] = "encerrado"
        return fim(movimento="confirm", objetivo="confirmar_visita", usar_nome=cliente["nome"],
                   visita={"quando": leitura.get("visita_texto"), **_dados_visita(estado, ctx, horario)},
                   **_transferir(estado, ctx, "tecnico", "visita_combinada"))

    # 6. Despedida: encerra de verdade, sem empurrar visita
    if intencao == "despedida" or leitura.get("encerrar_conversa"):
        estado["encerrado"] = True
        return fim(movimento="close", objetivo="despedir", usar_nome=cliente["nome"],
                   porta_aberta=any(t["cotado"] for t in estado["trabalhos"]))

    # 7. Objecao: dado + orientacao da biblioteca; segunda vez nao insiste
    if intencao == "objecao":
        obj = tratar_objecao(estado, objecao_cod, ctx, horario)
        if obj:
            convidar = obj["proximo_passo"] == "convidar_avaliacao" and not estado["convite_visita_feito"]
            if convidar:
                estado["convite_visita_feito"] = True
            return fim(movimento="explain", objetivo="tratar_objecao", acolher=True, objecao=obj,
                       convidar_visita=convidar, visita=_dados_visita(estado, ctx, horario) if convidar else None,
                       oferecer_compra={"venda_aparelhos": _fato(ctx, "venda_aparelhos"),
                                        "sem_consulta_spc": _fato(ctx, "venda_sem_consulta_spc")}
                       if obj["proximo_passo"] == "oferecer_compra" else None)

    # 8. Conduzir o equipamento em foco: uma lacuna por turno
    if foco is None:
        if any(t["cotado"] for t in estado["trabalhos"]):
            return fim(movimento="answer" if c["responder"] else "recommend_next", objetivo="aguardar_decisao",
                       convidar_visita=False)
        return fim(movimento="welcome" if saudar else "clarify", objetivo="descobrir_equipamento",
                   coletar=_coletar(None, "equipamento", ctx))

    lacuna = _lacuna(foco, ctx)
    if lacuna != "pronto":
        motivo = "preco_depende_do_modelo" if lacuna == "modelo" else None
        return fim(movimento="welcome" if saudar and not foco["defeito"] else "clarify",
                   objetivo=f"perguntar_{lacuna}", coletar=_coletar(foco, lacuna, ctx, motivo),
                   equipamento_em_foco=_resumo_trabalho(foco, ctx))

    orientacao = _orientacao(foco, ctx, estado)
    foco["cotado"], foco["status"] = True, "cotado"
    proximo = _selecionar(estado)
    convidar = not estado["convite_visita_feito"] and proximo is None
    if convidar:
        estado["convite_visita_feito"] = True
    if proximo is not None:
        estado["foco_atual"] = proximo["id"]
    return fim(movimento="recommend_next", objetivo=orientacao["tipo"], orientacao=orientacao,
               convidar_visita=convidar, visita=_dados_visita(estado, ctx, horario) if convidar else None,
               proximo_equipamento=_resumo_trabalho(proximo, ctx) if proximo else None)


def _resumo_trabalho(t: dict, ctx: dict) -> dict:
    s = _servico(ctx, t["servico_id"])
    return {"equipamento": (_categoria(ctx, t["categoria"]) or {}).get("nome"), "modelo": t["modelo"],
            "defeito": t["defeito"], "servico": s["nome"] if s else None,
            "faixa": {"min": t["faixa"]["min"], "max": t["faixa"]["max"]} if t["faixa"] else None}


# ---------------------------------------------------------------------------
# Saida unica: conducao completa + estado + metricas
# ---------------------------------------------------------------------------
def _finalizar(estado: dict, c: dict, ctx: dict, entrada: dict, duplicata: bool = False,
               etapa_antes: str | None = None) -> dict:
    eventos: list[str] = []
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
            eventos = ETAPAS[_rank(etapa_antes) + 1:_rank(etapa) + 1]

    for k, v in {"movimento": None, "objetivo": None, "saudar": False, "periodo": None, "acolher": False,
                 "usar_nome": None, "responder": None, "coletar": None, "orientacao": None, "objecao": None,
                 "convidar_visita": False, "visita": None, "nao_atende": None, "deve_transferir": False,
                 "fila": None, "transferir_para": None, "motivo_transferencia": None}.items():
        c.setdefault(k, v)
    c["apresentar_ia"] = (ctx.get("loja") or {}).get("nome_ia") if c["saudar"] else None
    c["nao_afirmar"] = list(ctx.get("loja_a_confirmar") or [])
    c["duplicata"] = duplicata
    c["etapa"] = estado["etapa"]
    if c["deve_transferir"]:
        c["resumo_encaminhamento"] = {
            "cliente": estado["cliente"]["nome"], "origem": estado.get("origem"), "impacto": estado.get("impacto"),
            "equipamentos": [_resumo_trabalho(t, ctx) for t in estado["trabalhos"] if t["status"] != "fora"],
            "visita": estado.get("visita"), "motivo": c["motivo_transferencia"],
        }
    return {"estado_novo": estado, "conducao": c,
            "metricas": _metricas(estado, c, entrada, eventos, duplicata)}


def _metricas(estado: dict, c: dict, entrada: dict, eventos: list, duplicata: bool) -> dict:
    """Tudo o que o v1_registrar_turno (SQL) grava. O SQL nao decide nada: so escreve isto."""
    leitura = entrada.get("leitura") or {}
    ativos = [t for t in estado["trabalhos"] if t["status"] != "fora"]
    principal = next((t for t in ativos if t["id"] == estado.get("foco_atual")), None) or (ativos[0] if ativos else None)
    origem = estado.get("origem") or {}
    objecao = (c.get("objecao") or {}).get("codigo")
    return {
        "ticket_id": entrada.get("ticket_id"), "duplicata": duplicata,
        "primeiro_turno": estado["turnos"] == 1, "primeira_msg_em": estado.get("primeira_msg_em"),
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
        "objecao": objecao,
        "pediu_preco": "preco" in (leitura.get("perguntas") or []),
        "objecao_preco": objecao in ("preco_alto", "comparou_concorrente"),
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
    - lembrete_visita: visita combinada ha 12h+ e ainda nao lembrada (confirmacao automatica, 1x).
    - lembrete: lead ativo 20h a 23h sem resposta (dentro da janela de 24h do WhatsApp).
    - reengajar_template: 72h+ sem resposta (exige template aprovado na Meta).
    Nunca fora do horario comercial. No maximo 2 follow-ups de reengajamento por atendimento.
    """
    estado = entrada.get("estado") or {}
    ctx = entrada.get("contexto_dados") or {}
    agora = _agora(entrada)
    if not situacao_horario(ctx, agora)["aberto"]:
        return {"enviar": False, "motivo": "fora_do_horario"}
    cliente = (estado.get("cliente") or {}).get("nome")
    visita = estado.get("visita")
    if visita and not estado.get("lembrete_visita_enviado"):
        try:
            combinada = datetime.fromisoformat(visita["combinada_em"]).astimezone(TZ)
        except (KeyError, TypeError, ValueError):
            return {"enviar": False, "motivo": "visita_sem_data"}
        if (agora - combinada).total_seconds() / 3600 < 12:
            return {"enviar": False, "motivo": "visita_recente"}
        estado_novo = deepcopy(estado)
        estado_novo["lembrete_visita_enviado"] = True
        return {"enviar": True, "tipo": "lembrete_visita", "estado_novo": estado_novo,
                "conducao": {"movimento": "confirm", "objetivo": "lembrar_visita", "usar_nome": cliente,
                             "visita": {"quando": visita.get("quando"),
                                        "loja_aberta_agora": True, "horario": _horario_loja(ctx)},
                             "insistir": False}}
    if estado.get("encerrado") or estado.get("transferido") or estado.get("etapa") not in ("triagem", "diagnostico", "orcamento"):
        return {"enviar": False, "motivo": "lead_fora_de_followup"}
    if (entrada.get("followups_enviados") or 0) >= 2:
        return {"enviar": False, "motivo": "limite_atingido"}
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
            "conducao": {"movimento": "recover", "objetivo": "retomar_atendimento", "usar_nome": cliente,
                         "equipamento_em_foco": _resumo_trabalho(foco, ctx) if foco else None,
                         "impacto_relatado": estado.get("impacto"),
                         "etapa": estado.get("etapa"), "insistir": False}}


def processar(entrada: dict) -> dict:
    return decidir(entrada)
