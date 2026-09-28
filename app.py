"""Painel Dados Demográficos — perfil do quadro de colaboradores (Pacaembu Construtora).

Migrado do dashboard AI/BI do Databricks (especificação em
"ZZ - Prompts Migração Databricks - Streamlit+Neon/Dashboard_Demograficos_Streamlit_Spec.md").
Fonte: uma view própria no Neon, com um usuário de banco só de leitura. Cálculos em metricas.py.
Padrão visual e de barra lateral: skill padrao-painel-streamlit (painel_padrao.py).

    streamlit run app.py
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import psycopg2
import pydeck as pdk
import streamlit as st

import auth
import metricas as m
import painel_padrao as pp

ASSETS = Path(__file__).resolve().parent / "assets"
AZUL, AMARELO, VERMELHO, VERDE = "#064D66", "#FAB900", "#F02727", "#22C55E"
CINZA, CINZA_ESCURO, BORDA = "#6B7280", "#1F2937", "#CBD8DE"
CORES_SEXO = {"Masculino": AZUL, "Feminino": AMARELO, m.NAO_INFORMADO: CINZA}
CORES_RACA = {"Branca": "#A8C5D0", "Parda": "#4A8FA8", "Preta": AZUL, "Amarela": AMARELO, "Não Informada": VERMELHO}
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
SEM_DADOS = "Sem pessoas no filtro selecionado."

st.set_page_config(page_title="Dados Demográficos · Pacaembu Construtora", page_icon=str(ASSETS / "icone-demograficos.png"), layout="wide")

st.html(f"""<style>
.kpi {{ background:#fff; border:1px solid {BORDA}; border-radius:10px; overflow:hidden; height:100%; }}
.kpi-topo {{ background:{AZUL}; color:#fff; font-weight:700; font-size:.78rem; letter-spacing:.04em; padding:.45rem .85rem; }}
.kpi-valor {{ color:{CINZA_ESCURO}; font-size:1.9rem; font-weight:700; text-align:center; padding:.7rem 0 .1rem; }}
.kpi-delta {{ text-align:center; font-size:.8rem; font-weight:600; min-height:1.2rem; padding-bottom:.55rem; }}
.kpi-base {{ height:7px; background:{AMARELO}; }}
.contador {{ background:#fff; border:1px solid #E2EBF0; border-radius:8px; padding:.55rem .85rem; margin-bottom:.45rem;
             display:flex; justify-content:space-between; align-items:center; }}
.contador span {{ color:{CINZA}; font-size:.82rem; font-weight:600; }}
.contador b {{ color:{AZUL}; font-size:1.02rem; }}
.secao {{ color:{AZUL}; font-weight:700; font-size:1.05rem; border-bottom:3px solid {AMARELO};
          display:inline-block; padding-bottom:.15rem; margin:.4rem 0 .2rem; }}
.titulo-graf {{ color:{CINZA_ESCURO}; font-weight:600; font-size:.92rem; margin-bottom:-.4rem; }}
</style>""")

# login antes de qualquer dado (mesma tabela acesso.app_users dos outros painéis) + matriz de acessos
auth.exigir_login()
auth.exigir_acesso_ao_painel("demograficos")


# ----------------------------------------------------------------------------- dados

@st.cache_data(ttl=600, show_spinner="Carregando dados…")
def carregar() -> tuple[pd.DataFrame, datetime | None]:
    with psycopg2.connect(st.secrets["neon"]["database_url"], connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM core.v_demografico_base")
        base = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        cur.execute("SELECT max(concluido_em) FROM ops.v_ultima_carga WHERE schema_nome = 'core' AND tabela = 'fato_funcionario'")
        carga = cur.fetchone()[0]
    return m.preparar(base), carga


def _mes_txt(d: date) -> str:
    return f"{MESES_PT[d.month - 1]}/{d:%y}"


def _int(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _pct(v, casas=1) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def kpi(rotulo: str, valor: str, delta: str = "", cor_delta: str = CINZA) -> None:
    st.html(f"""<div class="kpi"><div class="kpi-topo">{rotulo}</div><div class="kpi-valor">{valor}</div>
    <div class="kpi-delta" style="color:{cor_delta}">{delta}</div><div class="kpi-base"></div></div>""")


def contador(rotulo: str, valor: str) -> None:
    st.html(f'<div class="contador"><span>{escape(rotulo)}</span><b>{escape(valor)}</b></div>')


def _sem_dados_grafico(titulo: str) -> None:
    st.html(f'<div class="titulo-graf">{titulo}</div>')
    st.info(SEM_DADOS, icon=":material/info:")


# ----------------------------------------------------------------------------- gráficos

def donut_sexo(tab: pd.DataFrame) -> dict:
    dominio = [s for s in ("Masculino", "Feminino", m.NAO_INFORMADO) if s in set(tab["sexo"])]
    ordem = {v: i for i, v in enumerate(dominio)}
    # fatia com menos de 3% (ex.: 1 pessoa sem sexo informado) fica sem rótulo, só no tooltip
    d = tab.assign(ordem=tab["sexo"].map(ordem), rotulo=[f"{p:.0%}" if p >= .03 else "" for p in tab["pct"]]).to_dict("records")
    enc = {"theta": {"field": "headcount", "type": "quantitative", "stack": True}, "order": {"field": "ordem", "type": "quantitative"}}
    return {"data": {"values": d}, "view": {"stroke": None}, "layer": [
        {"mark": {"type": "arc", "innerRadius": 48, "outerRadius": 82, "padAngle": 0.025, "cornerRadius": 4, "stroke": "#fff", "strokeWidth": 2},
         "encoding": {**enc, "color": {"field": "sexo", "scale": {"domain": dominio, "range": [CORES_SEXO[s] for s in dominio]},
                                       "legend": {"orient": "bottom", "direction": "vertical", "symbolType": "circle", "labelFontSize": 10}},
                      "tooltip": [{"field": "sexo", "title": "Sexo"}, {"field": "headcount", "title": "Headcount"},
                                  {"field": "pct", "title": "Participação", "format": ".1%"}]}},
        {"mark": {"type": "text", "radius": 65, "fontSize": 12, "fontWeight": 700, "color": "#FFFFFF"},
         "encoding": {**enc, "text": {"field": "rotulo"}}},
    ]}


def barras_raca(tab: pd.DataFrame) -> dict:
    d = tab.assign(rotulo=[f"{int(n)}|({p * 100:.1f}%)".replace(".", ",") for n, p in zip(tab["headcount"], tab["pct"])])
    x = {"field": "raca_cor", "type": "nominal", "sort": list(tab["raca_cor"]),
         "axis": {"labelAngle": 0, "ticks": False, "title": None, "labelOverlap": False, "labelFontSize": 10, "labelLimit": 80,
                  "labelExpr": "datum.label == 'Não Informada' ? 'Não inf.' : datum.label"}}
    return {"data": {"values": d.to_dict("records")}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
         "encoding": {"x": x, "y": {"field": "headcount", "type": "quantitative", "axis": {"grid": True, "title": None}},
                      "color": {"field": "raca_cor", "scale": {"domain": list(CORES_RACA), "range": list(CORES_RACA.values())}, "legend": None},
                      "tooltip": [{"field": "raca_cor", "title": "Raça/Cor"}, {"field": "headcount", "title": "Headcount"},
                                  {"field": "pct", "title": "%", "format": ".1%"}]}},
        {"mark": {"type": "text", "dy": -16, "fontSize": 9, "fontWeight": 600, "color": CINZA_ESCURO, "lineBreak": "|"},
         "encoding": {"x": x, "y": {"field": "headcount", "type": "quantitative"}, "text": {"field": "rotulo"}}},
    ], "padding": {"top": 26}}


def evolucao(ev: pd.DataFrame) -> dict:
    """Barras empilhadas por sexo, rótulo dentro de cada parte, total e variação acima."""
    ordem = ["Masculino", "Feminino", m.NAO_INFORMADO]
    ev = ev.assign(ordem=ev["sexo"].map({s: i for i, s in enumerate(ordem)})).sort_values(["periodo", "ordem"])
    ev["y1"] = ev.groupby("periodo")["headcount"].cumsum(); ev["y0"] = ev["y1"] - ev["headcount"]; ev["meio"] = (ev["y0"] + ev["y1"]) / 2
    ev["mes"] = [_mes_txt(p) for p in ev["periodo"]]
    ev["rotulo"] = [f"{int(n)}|({p:.0%})" if n >= 60 else "" for n, p in zip(ev["headcount"], ev["pct"])]
    ev["cor_rotulo"] = ["#FFFFFF" if s == "Masculino" else AZUL for s in ev["sexo"]]
    tot = ev.drop_duplicates("periodo")[["periodo", "mes", "total", "delta"]].copy()
    tot["delta_txt"] = ["" if pd.isna(dl) else ("▲ " if dl > 0 else "▼ " if dl < 0 else "● ") + _int(abs(dl)) for dl in tot["delta"]]
    tot["cor_delta"] = [CINZA if pd.isna(dl) or dl == 0 else (VERDE if dl > 0 else VERMELHO) for dl in tot["delta"]]
    x = {"field": "mes", "type": "ordinal", "sort": list(tot["mes"]), "axis": {"labelAngle": 0, "title": None}}
    dominio = [s for s in ordem if s in set(ev["sexo"])]
    teto = float(tot["total"].max()) * 1.18 if len(tot) else 1
    y = lambda campo: {"field": campo, "type": "quantitative", "scale": {"domain": [0, teto]}}  # noqa: E731
    return {"layer": [
        {"data": {"values": ev.to_dict("records")}, "mark": {"type": "bar", "cornerRadius": 2},
         "encoding": {"x": x, "y": {**y("y0"), "axis": {"grid": True, "title": None}}, "y2": {"field": "y1"},
                      "color": {"field": "sexo", "title": "Sexo", "scale": {"domain": dominio, "range": [CORES_SEXO[s] for s in dominio]},
                                "legend": {"orient": "right"}},
                      "tooltip": [{"field": "mes", "title": "Mês"}, {"field": "sexo", "title": "Sexo"},
                                  {"field": "headcount", "title": "Headcount"}, {"field": "pct", "title": "%", "format": ".1%"}]}},
        {"data": {"values": ev.to_dict("records")}, "mark": {"type": "text", "fontSize": 10, "fontWeight": 600, "lineBreak": "|"},
         "encoding": {"x": x, "y": y("meio"), "text": {"field": "rotulo"}, "color": {"field": "cor_rotulo", "type": "nominal", "scale": None}}},
        {"data": {"values": tot.to_dict("records")}, "mark": {"type": "text", "dy": -8, "fontSize": 12, "fontWeight": 700, "color": CINZA_ESCURO},
         "encoding": {"x": x, "y": y("total"), "text": {"field": "total"}}},
        {"data": {"values": tot.to_dict("records")}, "mark": {"type": "text", "dy": -24, "fontSize": 10, "fontWeight": 600},
         "encoding": {"x": x, "y": y("total"), "text": {"field": "delta_txt"}, "color": {"field": "cor_delta", "type": "nominal", "scale": None}}},
    ]}


def barras_horizontais(tab: pd.DataFrame, campo: str, ordem: list[str]) -> dict:
    maximo = tab["headcount"].max() if len(tab) else 1
    d = tab.assign(dentro=tab["headcount"] / maximo >= 0.2)
    y = {"field": campo, "type": "nominal", "sort": ordem, "axis": {"title": None, "labelLimit": 150}}
    xq = {"field": "headcount", "type": "quantitative", "axis": {"title": None, "grid": True}}
    return {"data": {"values": d.to_dict("records")}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusEnd": 4, "color": AZUL},
         "encoding": {"y": y, "x": xq, "tooltip": [{"field": campo}, {"field": "headcount", "title": "Headcount"}]}},
        {"transform": [{"filter": "datum.dentro"}], "mark": {"type": "text", "align": "right", "dx": -6, "fontSize": 11, "fontWeight": 600, "color": "#FFFFFF"},
         "encoding": {"y": y, "x": xq, "text": {"field": "headcount", "format": ",d"}}},
        {"transform": [{"filter": "!datum.dentro"}], "mark": {"type": "text", "align": "left", "dx": 5, "fontSize": 11, "fontWeight": 600, "color": AZUL},
         "encoding": {"y": y, "x": xq, "text": {"field": "headcount", "format": ",d"}}},
    ], "padding": {"right": 20}}


def persona(genero: str) -> None:
    """Busto do perfil predominante (azul = masculino, rosa = feminino): cabeça e ombros,
    cortados pela borda do card."""
    feminino = genero == "Feminino"
    fundo = "#EF3976" if feminino else "#0B5A78"
    cabelo = '<path d="M26 74 Q26 36 50 36 Q74 36 74 74 L74 104 Q62 96 50 96 Q38 96 26 104 Z" fill="#fff" opacity=".55"/>' if feminino else ""
    ombros = ('<path d="M14 200 V158 Q14 122 50 122 Q86 122 86 158 V200 Z" fill="#fff"/>'
              '<path d="M42 122 L50 136 L58 122 Z" fill="' + fundo + '" opacity=".35"/>') if feminino else              '<path d="M10 200 V156 Q10 118 50 118 Q90 118 90 156 V200 Z" fill="#fff"/>'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 200">'
           f'<defs><clipPath id="c"><rect x="4" y="4" width="92" height="192" rx="24"/></clipPath></defs>'
           f'<rect x="4" y="4" width="92" height="192" rx="24" fill="{fundo}"/>'
           f'<g clip-path="url(#c)">{cabelo}<circle cx="50" cy="74" r="22" fill="#fff"/>{ombros}</g></svg>')
    # como imagem: o st.html remove <svg> colocado direto no HTML
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    st.html(f'<div class="titulo-graf">Persona</div><div style="display:flex;justify-content:center;margin-top:.9rem">'
            f'<img src="{uri}" alt="Perfil {escape(genero)}" style="width:100%;max-width:150px;height:auto"/></div>')


def _cor_entre(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def tabela_distribuicao(tab: pd.DataFrame):
    """Pivot com escala de cor em headcount e % feminino (sem matplotlib)."""
    corpo = tab["diretoria"] != "Total"
    hc_max = tab.loc[corpo, "headcount"].max() or 1
    pf = tab.loc[corpo, "pct_feminino"]
    pf_min, pf_max = (pf.min(), pf.max()) if len(pf) else (0, 1)

    def estilo(linha):
        if linha["diretoria"] == "Total":
            return ["font-weight:700; background-color:#F3F6F8"] * len(linha)
        t_hc = linha["headcount"] / hc_max
        t_pf = 0 if pf_max == pf_min else (linha["pct_feminino"] - pf_min) / (pf_max - pf_min)
        cor_hc = _cor_entre("#EAF4F7", AZUL, t_hc)
        out = []
        for c in linha.index:
            if c == "headcount":
                out.append(f"background-color:{cor_hc}; color:{'#FFFFFF' if t_hc > .55 else CINZA_ESCURO}")
            elif c == "pct_feminino":
                out.append(f"background-color:{_cor_entre('#EFF3FF', '#F5C6F3', t_pf)}")
            else:
                out.append("")
        return out

    return (tab.style.apply(estilo, axis=1)
            .format({"headcount": lambda v: _int(v), "pct_feminino": lambda v: _pct(v)}))


def mapa(tab: pd.DataFrame) -> None:
    st.html('<div class="titulo-graf">Distribuição em locais de trabalho</div>')
    if tab.empty:
        st.info(SEM_DADOS, icon=":material/info:")
        return
    d = tab.assign(raio=(tab["headcount"] ** 0.5) * 9000, hc_txt=[_int(v) for v in tab["headcount"]])
    camada = pdk.Layer("ScatterplotLayer", data=d, get_position="[longitude, latitude]", get_radius="raio",
                       get_fill_color=[6, 77, 102, 217], get_line_color=[255, 255, 255], line_width_min_pixels=1,
                       stroked=True, pickable=True)
    vista = pdk.ViewState(latitude=float(d["latitude"].mean()), longitude=float(d["longitude"].mean()), zoom=4.2)
    deck = pdk.Deck(layers=[camada], initial_view_state=vista, map_provider="carto", map_style="light",
                    tooltip={"html": "<b>{cidade}</b><br/>Headcount: {hc_txt}", "style": {"fontFamily": "Inter"}})
    chave = hashlib.md5(d[["cidade", "headcount"]].to_json().encode()).hexdigest()
    st.pydeck_chart(deck, height=430, key=f"mapa-{chave}")


# ----------------------------------------------------------------------------- página

try:
    df, carga = carregar()
except Exception as exc:  # noqa: BLE001
    st.error("Não consegui ler a base do Neon. Confira o bloco [neon] em .streamlit/secrets.toml.", icon=":material/error:")
    st.caption(type(exc).__name__)
    st.stop()

ref = m.data_referencia(df)
pp.logo(ASSETS / "icone-demograficos.png", "Dados Demográficos")
with st.container(horizontal=True, vertical_alignment="bottom"):
    st.title("Dados Demográficos", anchor=False)
    cabecalho = st.empty()

opcoes = lambda c: sorted(df[c].dropna().unique())  # noqa: E731
with pp.barra_lateral(fonte="Neon + Databricks", atualizado_em=carga):
    st.markdown("**Período**")
    _padrao = (m.inicio_padrao(ref), ref)
    _escolha = st.date_input("Período", value=_padrao, min_value=date(2020, 1, 1), max_value=ref,
                             format="DD/MM/YYYY", label_visibility="collapsed")
    per_ini, per_fim = _escolha if isinstance(_escolha, (tuple, list)) and len(_escolha) == 2 else _padrao
    st.caption("A evolução usa o período inteiro; cards, perfis e mapa mostram o quadro na data final.")
    st.markdown("**Filtros**")
    sel = {
        "diretoria": st.multiselect("Diretoria", opcoes("diretoria"), placeholder="Todas"),
        "area": st.multiselect("Área", opcoes("area"), placeholder="Todas"),
        "nome_centro_custo": st.multiselect("Centro de custo", opcoes("nome_centro_custo"), placeholder="Todos"),
        "familia_cargo": st.multiselect("Família de cargo", opcoes("familia_cargo"), placeholder="Todas"),
        "sexo": st.multiselect("Sexo", opcoes("sexo"), placeholder="Todos"),
    }
    sel_tempo = st.multiselect("Tempo de casa", list(reversed(m.ORDEM_TEMPO_CASA)), placeholder="Todos",
                               help="Tempo de casa na data de cada foto (data final nos cards; fim de cada mês na evolução).")

ref_p = min(per_fim, ref)
cabecalho.caption(f"Quadro em {ref_p:%d/%m/%Y} · evolução de {per_ini:%d/%m/%Y} até {ref_p:%d/%m/%Y} · dados de {ref:%d/%m/%Y}")

base = df
for col, vals in sel.items():
    if vals:
        base = base[base[col].isin(vals)]
ativos = m.ativos_em(base, ref_p, sel_tempo)
k = m.kpis(base, ref_p, sel_tempo)

c1, c2, c3, c4 = st.columns([3, 2, 4, 3])
with c1:
    dl = k["headcount"] - k["headcount_anterior"]
    kpi("HEADCOUNT", _int(k["headcount"]), "Estável" if dl == 0 else f"{'▲' if dl > 0 else '▼'} {_int(abs(dl))} vs mês ant.",
        VERDE if dl > 0 else VERMELHO if dl < 0 else CINZA)
with c2:
    pa, pb = k["pct_feminino"], k["pct_feminino_anterior"]
    pp_ = (pa - pb) * 100 if pa is not None and pb is not None else 0
    kpi("% FEMININO", _pct(pa), "Estável" if abs(pp_) < 0.05 else f"{'▲' if pp_ > 0 else '▼'} {abs(pp_):.1f} pp".replace(".", ","),
        VERDE if pp_ >= 0.05 else VERMELHO if pp_ <= -0.05 else CINZA)
with c3:
    kpi("TEMPO DE CASA MÉDIO", k["tempo_casa"], "Média de permanência", CINZA)
with c4:
    kpi("IDADE MÉDIA", k["idade_media"], "Média do quadro ativo", CINZA)

if ativos.empty:
    st.info(SEM_DADOS, icon=":material/info:")
    st.stop()

g1, g2, g3, g4 = st.columns([3, 2, 4, 3])
with g1:
    pp.grafico("Distribuição por sexo", donut_sexo(m.contagem(ativos, "sexo")), 300, SEM_DADOS)
with g2:
    persona(k["genero_predominante"])
with g3:
    st.html('<div class="titulo-graf">Perfil predominante</div>'); st.html('<div style="height:.7rem"></div>')
    contador("Gênero predominante", k["genero_predominante"])
    contador("Raça/Cor predominante", k["raca_predominante"])
    contador("Idade média", k["idade_media"])
    contador("Tempo de casa", k["tempo_casa"])
    contador("Geração predominante", k["geracao_predominante"])
with g4:
    pp.grafico("Headcount por raça/cor", barras_raca(m.contagem(ativos, "raca_cor", m.ORDEM_RACA)), 300, SEM_DADOS)

ev = m.evolucao_sexo(base, per_ini, ref_p, sel_tempo)
if ev.empty:
    _sem_dados_grafico("Evolução do headcount por sexo")
else:
    pp.grafico("Evolução do headcount por sexo", evolucao(ev), 360, SEM_DADOS)

b1, b2, b3 = st.columns(3)
with b1:
    pp.grafico("Faixa etária", barras_horizontais(m.contagem(ativos, "faixa_etaria", m.ORDEM_FAIXA_ETARIA), "faixa_etaria", m.ORDEM_FAIXA_ETARIA), 290, SEM_DADOS)
with b2:
    pp.grafico("Geração", barras_horizontais(m.contagem(ativos, "geracao", m.ORDEM_GERACAO), "geracao", m.ORDEM_GERACAO), 290, SEM_DADOS)
with b3:
    pp.grafico("Tempo de casa", barras_horizontais(m.contagem(ativos, "faixa_tempo_casa", m.ORDEM_TEMPO_CASA), "faixa_tempo_casa", m.ORDEM_TEMPO_CASA), 290, SEM_DADOS)

t1, t2 = st.columns([8, 4])
with t1:
    st.html('<div class="secao">Distribuição por área e diretoria</div>')
    dist = m.distribuicao_diretoria_area(ativos)
    st.dataframe(tabela_distribuicao(dist), hide_index=True, width="stretch", height=430,
                 column_config={"diretoria": st.column_config.TextColumn("Diretoria", width=170),
                                "area": st.column_config.TextColumn("Área", width=190),
                                "headcount": st.column_config.TextColumn("Headcount"),
                                "pct_feminino": st.column_config.TextColumn("% Feminino"),
                                "tempo_casa": "Tempo de casa", "idade_media": "Idade média"})
with t2:
    mapa(m.mapa_cidades(ativos))
    sem_coord = ativos["latitude"].isna().sum()
    if sem_coord:
        st.caption(f"{_int(sem_coord)} pessoa(s) sem cidade cadastrada ficam fora do mapa.")
