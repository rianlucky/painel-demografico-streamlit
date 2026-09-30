"""Cálculo dos indicadores do painel Dados Demográficos — sem Streamlit, para testar e validar.

Entrada: core.v_demografico_base (Neon), uma linha por atribuição, pessoa pseudonimizada.
Regras da especificação do dashboard do Databricks
(ZZ - Prompts Migração.../Dashboard_Demograficos_Streamlit_Spec.md):
  1. Headcount numa data: admitido até a data e sem desligamento (ou desligado depois);
     pessoas distintas — a mesma regra do painel Turnover
  2. Gerações por ano de nascimento; faixas etárias e de tempo de casa da especificação
  3. Tempo de casa médio "X anos Y meses" = floor(média/365) anos e floor(resto/30) meses
Diferenças deliberadas (ver README.md): data de referência = foto mais recente da base; diretoria
e área do mapeamento oficial; família de cargo da própria atribuição (sem o join com dim_cargo que
duplicava pessoas); cidade de core.local_cidade; tudo pode ser visto numa data do período (idade e
tempo de casa recalculados para a data).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

FAIXAS_TEMPO_CASA = [
    (91, "0 a 3 meses"), (183, "3 a 6 meses"), (365, "6 meses a 1 ano"), (730, "1 ano a 2 anos"),
    (1095, "2 anos a 3 anos"), (1826, "3 anos a 5 anos"), (3652, "5 anos a 10 anos"),
]
ORDEM_TEMPO_CASA = ["+ 10 anos", "5 anos a 10 anos", "3 anos a 5 anos", "2 anos a 3 anos",
                    "1 ano a 2 anos", "6 meses a 1 ano", "3 a 6 meses", "0 a 3 meses"]
ORDEM_FAIXA_ETARIA = ["60+", "55 a 59", "50 a 54", "45 a 49", "40 a 44", "35 a 39", "30 a 34",
                      "25 a 29", "18 a 24", "Menor de 18"]
ORDEM_GERACAO = ["Geração Alpha", "Tradicionalistas", "Baby Boomers", "Geração X", "Millennials", "Geração Z"]
ORDEM_RACA = ["Branca", "Parda", "Preta", "Amarela", "Não Informada"]
NAO_INFORMADO = "Não informado"
# nível de gerenciamento com as variações juntas (mesmo agrupamento do Headcount Total e da Aderência)
NIVEL_GERENCIAMENTO = {"Gerente de Vendas": "Gerente", "Gerente Executivo de Obras": "Gerente Executivo",
                       "Gerente Executivo Estadual de Obras": "Gerente Executivo", "Coordenador de Obras": "Coordenador/Especialista",
                       "Diretor de Obras": "Diretor"}
ORDEM_NIVEL = ["Operacional", "Pilotos", "Staff", "Supervisor/Advogado/Engenheiro", "Coordenador/Especialista",
               "Gerente", "Gerente Executivo", "Diretor", "Conselheiro"]
ORDEM_FRENTE = ["Obras", "Corporativo", "Comercial"]
NEGRAS = {"Preta", "Parda"}


def faixa_tempo_casa(dias) -> str | None:
    if dias is None or pd.isna(dias):
        return None
    for limite, nome in FAIXAS_TEMPO_CASA:
        if dias < limite:
            return nome
    return "+ 10 anos"


def faixa_etaria(idade) -> str | None:
    if idade is None or pd.isna(idade):
        return None
    if idade < 18:
        return "Menor de 18"
    for teto, nome in ((24, "18 a 24"), (29, "25 a 29"), (34, "30 a 34"), (39, "35 a 39"),
                       (44, "40 a 44"), (49, "45 a 49"), (54, "50 a 54"), (59, "55 a 59")):
        if idade <= teto:
            return nome
    return "60+"


def preparar(base: pd.DataFrame) -> pd.DataFrame:
    df = base.copy()
    for c in ("data_referencia", "data_admissao", "data_desligamento"):
        df[c] = pd.to_datetime(df[c]).dt.date
    for c in ("idade_ref", "latitude", "longitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("diretoria", "area", "nome_centro_custo", "familia_cargo", "sexo", "cidade"):
        df[c] = df[c].fillna(NAO_INFORMADO)
    df["raca_cor"] = df["raca_cor"].fillna("Não Informada")
    df["nivel"] = df["nivel_gerenciamento"].replace(NIVEL_GERENCIAMENTO).fillna(NAO_INFORMADO)
    for c in ("frente", "uf", "vinculo"):
        df[c] = df[c].fillna(NAO_INFORMADO)
    return df


def data_referencia(df: pd.DataFrame) -> date:
    return max(df["data_referencia"].dropna())


def _fim_mes(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def meses_entre(ini: date, fim: date) -> list[date]:
    lista, d = [], ini.replace(day=1)
    while d <= fim:
        lista.append(d)
        d = (d + timedelta(days=32)).replace(day=1)
    return lista


def inicio_padrao(ref: date) -> date:
    """Período padrão: do dia 1 do mesmo mês do ano anterior até a referência."""
    return date(ref.year - 1, ref.month, 1)


def ativos_em(df: pd.DataFrame, d: date, faixas_tempo_casa: list[str] | None = None) -> pd.DataFrame:
    """Uma linha por pessoa ativa na data `d`, com idade e tempo de casa naquela data.
    `faixas_tempo_casa` filtra pela faixa de tempo de casa na própria data."""
    ativo = (df["data_admissao"] <= d) & (df["data_desligamento"].isna() | (df["data_desligamento"] > d))
    a = df[ativo].sort_values(["pessoa", "data_admissao"], ascending=[True, False]).drop_duplicates("pessoa").copy()
    ref = a["data_referencia"]
    a["idade"] = a["idade_ref"] - [(r - d).days / 365.25 for r in ref]
    a["tempo_casa_dias"] = [(d - x).days for x in a["data_admissao"]]
    a["faixa_tempo_casa"] = a["tempo_casa_dias"].map(faixa_tempo_casa)
    a["faixa_etaria"] = a["idade"].map(faixa_etaria)
    if faixas_tempo_casa:
        a = a[a["faixa_tempo_casa"].isin(faixas_tempo_casa)]
    return a


def tempo_casa_texto(dias: pd.Series) -> str:
    dias = dias.dropna()
    if dias.empty:
        return "—"
    media = float(dias.mean())
    anos, meses = int(media // 365), int((media % 365) // 30)
    return f"{anos} {'ano' if anos == 1 else 'anos'} {meses} {'mês' if meses == 1 else 'meses'}"


def idade_media_texto(idades: pd.Series) -> str:
    idades = idades.dropna()
    return "—" if idades.empty else f"{round(float(idades.mean()))} anos"


def pct_feminino(a: pd.DataFrame) -> float | None:
    return float((a["sexo"] == "Feminino").mean()) if len(a) else None


def moda(serie: pd.Series) -> str:
    s = serie.dropna()
    s = s[s != NAO_INFORMADO]
    return "—" if s.empty else str(s.value_counts().idxmax())


def kpis(df: pd.DataFrame, d: date, faixas_tempo_casa: list[str] | None = None) -> dict:
    """Cards do topo: na data `d` e no fim do mês anterior a ela (para o delta)."""
    atual = ativos_em(df, d, faixas_tempo_casa)
    anterior = ativos_em(df, d.replace(day=1) - timedelta(days=1), faixas_tempo_casa)
    masc, fem = int((atual["sexo"] == "Masculino").sum()), int((atual["sexo"] == "Feminino").sum())
    return {
        "headcount": len(atual), "headcount_anterior": len(anterior),
        "pct_feminino": pct_feminino(atual), "pct_feminino_anterior": pct_feminino(anterior),
        "tempo_casa": tempo_casa_texto(atual["tempo_casa_dias"]), "idade_media": idade_media_texto(atual["idade"]),
        "genero_predominante": "—" if not len(atual) else ("Masculino" if masc >= fem else "Feminino"),
        "raca_predominante": moda(atual["raca_cor"]), "geracao_predominante": moda(atual["geracao"]),
    }


def _distribuicao(serie: pd.Series, ordem: list[str]) -> list[tuple[str, int, float]]:
    """[(valor, pessoas, % do grupo)] na ordem dada (valores fora da ordem vão para o fim)."""
    vc = serie.value_counts()
    total = int(vc.sum())
    chaves = [o for o in ordem if o in vc.index] + [v for v in vc.index if v not in ordem]
    return [(k, int(vc[k]), vc[k] / total) for k in chaves] if total else []


def retrato_por_sexo(a: pd.DataFrame) -> dict[str, dict]:
    """Como é cada sexo no quadro: pessoas, % do quadro, idade média, tempo de casa médio e a
    composição por raça/cor e por geração (em % do próprio grupo)."""
    total = len(a)
    out = {}
    for sexo in ("Masculino", "Feminino"):
        g = a[a["sexo"] == sexo]
        out[sexo] = {
            "pessoas": len(g), "pct_quadro": len(g) / total if total else None,
            "idade_media": idade_media_texto(g["idade"]), "tempo_casa": tempo_casa_texto(g["tempo_casa_dias"]),
            "raca": _distribuicao(g["raca_cor"], ORDEM_RACA),
            "geracao": _distribuicao(g["geracao"], list(reversed(ORDEM_GERACAO))),
        }
    return out


def _pct_mulheres_negras(g: pd.DataFrame) -> tuple[float | None, float | None]:
    n = len(g)
    return ((g["sexo"] == "Feminino").mean() if n else None, g["raca_cor"].isin(NEGRAS).mean() if n else None)


def retrato_por_frente(a: pd.DataFrame) -> dict[str, dict]:
    """Como é cada frente (Obras, Corporativo, Comercial): pessoas, % do quadro, idade e tempo de casa
    médios e a composição por sexo, raça/cor e geração."""
    total, out = len(a), {}
    for frente in [f for f in ORDEM_FRENTE if f in set(a["frente"])]:
        g = a[a["frente"] == frente]
        out[frente] = {"pessoas": len(g), "pct_quadro": len(g) / total if total else None,
                       "idade_media": idade_media_texto(g["idade"]), "tempo_casa": tempo_casa_texto(g["tempo_casa_dias"]),
                       "sexo": _distribuicao(g["sexo"], ["Masculino", "Feminino", NAO_INFORMADO]),
                       "raca": _distribuicao(g["raca_cor"], ORDEM_RACA),
                       "geracao": _distribuicao(g["geracao"], list(reversed(ORDEM_GERACAO)))}
    return out


def diversidade_por_nivel(a: pd.DataFrame) -> pd.DataFrame:
    """% de mulheres e de pretas e pardas em cada nível de gerenciamento (do operacional ao conselho)."""
    linhas = []
    for nivel, g in a.groupby("nivel"):
        pm, pn = _pct_mulheres_negras(g)
        linhas.append({"nivel": nivel, "pessoas": len(g), "pct_mulheres": pm, "pct_negras": pn})
    t = pd.DataFrame(linhas, columns=["nivel", "pessoas", "pct_mulheres", "pct_negras"])
    ordem = [n for n in ORDEM_NIVEL if n in set(t["nivel"])] + sorted(set(t["nivel"]) - set(ORDEM_NIVEL))
    return t.set_index("nivel").reindex(ordem).reset_index()


def evolucao_diversidade(df: pd.DataFrame, ini: date, fim: date, faixas_tempo_casa: list[str] | None = None) -> pd.DataFrame:
    """% de mulheres e de pretas e pardas no fim de cada mês do período."""
    linhas = []
    for mes in meses_entre(ini, fim):
        a = ativos_em(df, min(_fim_mes(mes), fim), faixas_tempo_casa)
        pm, pn = _pct_mulheres_negras(a)
        linhas.append({"periodo": mes, "pessoas": len(a), "pct_mulheres": pm, "pct_negras": pn,
                       "mulheres": int((a["sexo"] == "Feminino").sum()), "homens": int((a["sexo"] == "Masculino").sum()),
                       "negras": int(a["raca_cor"].isin(NEGRAS).sum())})
    return pd.DataFrame(linhas, columns=["periodo", "pessoas", "pct_mulheres", "pct_negras", "mulheres", "homens", "negras"])


def entrantes(df: pd.DataFrame, ini: date, fim: date) -> pd.DataFrame:
    """Uma linha por pessoa admitida no período (a admissão mais recente dentro dele), com a idade na
    admissão e se ainda está ativa na data final."""
    e = df[(df["data_admissao"] >= ini) & (df["data_admissao"] <= fim)]
    e = e.sort_values(["pessoa", "data_admissao"], ascending=[True, False]).drop_duplicates("pessoa").copy()
    e["idade_admissao"] = e["idade_ref"] - [(r - x).days / 365.25 for r, x in zip(e["data_referencia"], e["data_admissao"])]
    e["ativo_fim"] = e["data_desligamento"].isna() | (e["data_desligamento"] > fim)
    return e


def comparar_entrantes(e: pd.DataFrame, a: pd.DataFrame) -> dict:
    """Perfil de quem entrou no período x o quadro na data final."""
    pm_e, pn_e = _pct_mulheres_negras(e)
    pm_a, pn_a = _pct_mulheres_negras(a)
    comp = {}
    for campo, ordem in (("sexo", ["Masculino", "Feminino", NAO_INFORMADO]), ("raca_cor", ORDEM_RACA),
                         ("geracao", list(reversed(ORDEM_GERACAO)))):
        comp[campo] = {"Admitidos no período": _distribuicao(e[campo], ordem), "Quadro na data final": _distribuicao(a[campo], ordem)}
    return {"admitidos": len(e), "ainda_ativos": int(e["ativo_fim"].sum()) if len(e) else 0,
            "pct_mulheres": pm_e, "pct_mulheres_quadro": pm_a, "pct_negras": pn_e, "pct_negras_quadro": pn_a,
            "idade_admissao": idade_media_texto(e["idade_admissao"]), "idade_quadro": idade_media_texto(a["idade"]),
            "composicao": comp}


def contagem(a: pd.DataFrame, coluna: str, ordem: list[str] | None = None) -> pd.DataFrame:
    t = a.groupby(coluna)["pessoa"].nunique().rename("headcount").reset_index()
    total = t["headcount"].sum()
    t["pct"] = t["headcount"] / total if total else 0
    if ordem:
        t = t.set_index(coluna).reindex([o for o in ordem if o in set(t[coluna])]).reset_index()
    return t


def evolucao_sexo(df: pd.DataFrame, ini: date, fim: date, faixas_tempo_casa: list[str] | None = None) -> pd.DataFrame:
    """Headcount por sexo no fim de cada mês do período (o último mês vai até `fim`)."""
    linhas = []
    for mes in meses_entre(ini, fim):
        d = min(_fim_mes(mes), fim)
        a = ativos_em(df, d, faixas_tempo_casa)
        for sexo, n in a["sexo"].value_counts().items():
            linhas.append({"periodo": mes, "sexo": sexo, "headcount": int(n)})
    ev = pd.DataFrame(linhas, columns=["periodo", "sexo", "headcount"])
    if ev.empty:
        return ev.assign(total=[], pct=[], delta=[])
    tot = ev.groupby("periodo")["headcount"].sum().rename("total")
    ev = ev.merge(tot, on="periodo")
    ev["pct"] = ev["headcount"] / ev["total"]
    delta = tot.diff().rename("delta")
    return ev.merge(delta, on="periodo", how="left")


def distribuicao_diretoria_area(a: pd.DataFrame) -> pd.DataFrame:
    """Pivot diretoria × área: headcount, % feminino, tempo de casa e idade média, com total."""
    if a.empty:
        return pd.DataFrame(columns=["diretoria", "area", "headcount", "pct_feminino", "tempo_casa", "idade_media"])
    g = a.groupby(["diretoria", "area"])
    t = g["pessoa"].nunique().rename("headcount").to_frame()
    t["pct_feminino"] = g["sexo"].apply(lambda s: (s == "Feminino").mean())
    t["tempo_casa"] = g["tempo_casa_dias"].agg(lambda s: tempo_casa_texto(s))
    t["idade_media"] = g["idade"].agg(lambda s: idade_media_texto(s))
    t = t.reset_index().sort_values(["diretoria", "area"])
    total = pd.DataFrame([{"diretoria": "Total", "area": "", "headcount": a["pessoa"].nunique(),
                           "pct_feminino": pct_feminino(a), "tempo_casa": tempo_casa_texto(a["tempo_casa_dias"]),
                           "idade_media": idade_media_texto(a["idade"])}])
    return pd.concat([t, total], ignore_index=True)


def mapa_cidades(a: pd.DataFrame) -> pd.DataFrame:
    m = a.dropna(subset=["latitude", "longitude"])
    return (m.groupby(["cidade", "latitude", "longitude"])["pessoa"].nunique().rename("headcount")
            .reset_index().sort_values("headcount", ascending=False))
