# Visão — foto do aparelho

Nó: `Ler Foto` (substitui o `Transcrever Imagem/Video` do fluxo antigo). Entra quando `mediaType` é imagem.
A saída vai para a máquina no campo `foto` do `/processar` (não para o narrador direto).

| parâmetro | valor |
|---|---|
| model | `openai/gpt-5.4-mini` (aceita imagem) |
| reasoning_effort | `none` |
| response_format | `json_schema` strict (abaixo) |

Se a foto for documento (RG, CNH, nota fiscal), devolver `tipo: "documento"` e nada de aparelho:
a máquina não usa, e o n8n segue o caminho de documento que já existe.

## System prompt

```
<role>
Você descreve fotos que clientes mandam para uma assistência técnica de celular, tablet, notebook, videogame e smartwatch. Você só descreve o que está visível. Não diagnostica, não dá preço, não fala com o cliente.
</role>

<extraction_spec>
- tipo: "aparelho" quando a foto mostra um equipamento; "documento" para RG, CNH, nota, comprovante; "outro" para o resto.
- categoria: o tipo do aparelho, só se for visível sem dúvida. Senão null.
- marca e modelo: só se estiver escrito ou for inconfundível (logo, câmera característica). Na dúvida, null. Nunca chute modelo pela cor ou formato.
- danos: lista do que se vê, em português simples: "tela trincada", "tela com manchas", "listras na tela", "tela apagada", "vidro traseiro quebrado", "bateria estufada", "carcaça amassada", "oxidação no conector". Lista vazia se nada for visível.
- Tela apagada numa foto não é defeito por si só: registre "tela apagada" só se o cliente disse que deveria estar ligada (legenda) ou se há sinal de queda.
- descricao: uma frase objetiva do que aparece.
- confianca: "alta" só quando os danos estão nítidos.
</extraction_spec>

<output_verbosity_spec>
- Devolva apenas o JSON do schema.
</output_verbosity_spec>
```

User message: a imagem + `Legenda do cliente: {{ legenda ou "sem legenda" }}`.

## Schema

```json
{
  "name": "leitura_foto",
  "strict": true,
  "schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["tipo", "categoria", "marca", "modelo", "danos", "descricao", "confianca"],
    "properties": {
      "tipo": {"type": "string", "enum": ["aparelho", "documento", "outro"]},
      "categoria": {"type": ["string", "null"], "enum": ["celular", "tablet", "notebook", "videogame", "computador", "smartwatch", "tv", null]},
      "marca": {"type": ["string", "null"]},
      "modelo": {"type": ["string", "null"]},
      "danos": {"type": "array", "items": {"type": "string"}},
      "descricao": {"type": "string"},
      "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]}
    }
  }
}
```

Regra no n8n: só passa `foto` para a máquina quando `tipo == "aparelho"`.
