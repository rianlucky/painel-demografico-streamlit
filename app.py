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
AJUDA_LIDERANCA = ("Liderança = níveis de coordenação para cima: Coordenador/Especialista, Gerente, Gerente Executivo, "
                   "Diretor e Conselho. Vermelho quando a participação na liderança fica 5 pontos ou mais abaixo da do quadro.")

st.set_page_config(page_title="Dados Demográficos · Pacaembu Construtora", page_icon=str(ASSETS / "icone-demograficos.png"), layout="wide")

st.html(f"""<style>
.contador {{ background:#fff; border:1px solid #E2EBF0; border-radius:8px; padding:.55rem .85rem; margin-bottom:.45rem;
             display:flex; justify-content:space-between; align-items:center; }}
.contador span {{ color:{CINZA}; font-size:.82rem; font-weight:600; }}
.contador b {{ color:{AZUL}; font-size:1.02rem; }}
.rt-card {{ background:#fff; border:1px solid {BORDA}; border-top:5px solid; border-radius:12px; padding:1rem 1.1rem .8rem; height:100%; }}
.rt-topo {{ display:flex; gap:1rem; align-items:center; }}
.rt-img {{ width:82px; flex:0 0 82px; height:auto; }}
.rt-dados {{ flex:1; min-width:0; }}
.rt-nome {{ font-weight:800; font-size:1.05rem; text-transform:uppercase; letter-spacing:.04em; }}
.rt-num {{ font-size:1.9rem; font-weight:800; color:{CINZA_ESCURO}; line-height:1.15; }}
.rt-num span {{ font-size:.85rem; font-weight:600; color:{CINZA}; }}
.rt-linhas {{ margin-top:.45rem; display:grid; grid-template-columns:1fr 1fr; gap:.4rem; }}
.rt-linhas div {{ background:#F5F8FA; border-radius:8px; padding:.35rem .6rem; display:flex; flex-direction:column; }}
.rt-linhas span {{ color:{CINZA}; font-size:.72rem; font-weight:700; }}
.rt-linhas b {{ color:{AZUL}; font-size:1rem; }}
.rt-bloco {{ margin-top:.8rem; }}
.rt-sub {{ color:{CINZA_ESCURO}; font-size:.8rem; font-weight:800; margin-bottom:.3rem; }}
.rt-barra {{ display:flex; height:14px; border-radius:7px; overflow:hidden; background:#EEF2F4; }}
.rt-barra span {{ display:block; height:100%; }}
.rt-legs {{ display:flex; flex-wrap:wrap; gap:.15rem .8rem; margin-top:.35rem; }}
.rt-leg {{ font-size:.76rem; color:{CINZA}; display:inline-flex; align-items:center; gap:.3rem; }}
.rt-leg i {{ width:9px; height:9px; border-radius:2px; display:inline-block; }}
.rt-leg b {{ color:{CINZA_ESCURO}; }}
@media (max-width: 900px) {{ .rt-linhas {{ grid-template-columns:1fr; }} }}
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


def _persona_uri(genero: str) -> str:
    """Busto em SVG (azul = masculino, rosa = feminino), como data URI: o st.html remove <svg>
    colocado direto no HTML."""
    feminino = genero == "Feminino"
    fundo = "#EF3976" if feminino else "#0B5A78"
    cabelo = '<path d="M26 74 Q26 36 50 36 Q74 36 74 74 L74 104 Q62 96 50 96 Q38 96 26 104 Z" fill="#fff" opacity=".55"/>' if feminino else ""
    ombros = ('<path d="M14 200 V158 Q14 122 50 122 Q86 122 86 158 V200 Z" fill="#fff"/>'
              '<path d="M42 122 L50 136 L58 122 Z" fill="' + fundo + '" opacity=".35"/>') if feminino else              '<path d="M10 200 V156 Q10 118 50 118 Q90 118 90 156 V200 Z" fill="#fff"/>'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 200">'
           f'<defs><clipPath id="c"><rect x="4" y="4" width="92" height="192" rx="24"/></clipPath></defs>'
           f'<rect x="4" y="4" width="92" height="192" rx="24" fill="{fundo}"/>'
           f'<g clip-path="url(#c)">{cabelo}<circle cx="50" cy="74" r="22" fill="#fff"/>{ombros}</g></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def persona(genero: str) -> None:
    """Busto do perfil predominante, cortado pela borda do card."""
    uri = _persona_uri(genero)
    st.html(f'<div class="titulo-graf">Persona</div><div style="display:flex;justify-content:center;margin-top:.9rem">'
            f'<img src="{uri}" alt="Perfil {escape(genero)}" style="width:100%;max-width:150px;height:auto"/></div>')


CORES_GERACAO = {"Geração Z": "#A8C5D0", "Millennials": "#4A8FA8", "Geração X": AZUL, "Baby Boomers": AMARELO,
                 "Tradicionalistas": "#EB6834", "Geração Alpha": CINZA}


def _barra_composicao(titulo: str, partes: list[tuple[str, int, float]], cores: dict[str, str]) -> str:
    """Barra 100% empilhada + legenda com o % de cada parte (HTML leve, cabe no card)."""
    if not partes:
        return ""
    fatias = "".join(f'<span title="{escape(n)}: {_pct(p)} ({_int(q)})" style="width:{p * 100:.2f}%;background:{cores.get(n, CINZA)}"></span>'
                     for n, q, p in partes)
    legenda = "".join(f'<span class="rt-leg"><i style="background:{cores.get(n, CINZA)}"></i>{escape(n)} <b>{_pct(p)}</b></span>'
                      for n, q, p in partes)
    return f'<div class="rt-bloco"><div class="rt-sub">{escape(titulo)}</div><div class="rt-barra">{fatias}</div><div class="rt-legs">{legenda}</div></div>'


def retrato(sexo: str, r: dict) -> None:
    """Card "como é cada gênero na companhia": persona fixa, quantidade, % do quadro, idade média,
    tempo de casa médio e a composição por raça/cor e geração."""
    cor = "#EF3976" if sexo == "Feminino" else AZUL
    nome = "Mulheres" if sexo == "Feminino" else "Homens"
    if not r["pessoas"]:
        st.html(f'<div class="rt-card" style="border-top-color:{cor}"><div class="rt-nome" style="color:{cor}">{nome}</div>'
                f'<div class="nota">Sem {nome.lower()} no filtro selecionado.</div></div>')
        return
    st.html(f"""<div class="rt-card" style="border-top-color:{cor}">
      <div class="rt-topo">
        <img src="{_persona_uri(sexo)}" alt="" class="rt-img"/>
        <div class="rt-dados">
          <div class="rt-nome" style="color:{cor}">{nome}</div>
          <div class="rt-num">{_int(r["pessoas"])} <span>pessoas · {_pct(r["pct_quadro"])} do quadro</span></div>
          <div class="rt-linhas"><div><span>Idade média</span><b>{escape(r["idade_media"])}</b></div>
            <div><span>Tempo de casa médio</span><b>{escape(r["tempo_casa"])}</b></div></div>
        </div>
      </div>
      {_barra_composicao("Raça/cor", r["raca"], CORES_RACA)}
      {_barra_composicao("Geração", r["geracao"], CORES_GERACAO)}
    </div>""")


def diversidade_nivel(t: pd.DataFrame, pm: float | None, pn: float | None) -> dict:
    """Barras agrupadas por nível: % de mulheres e % de pretas e pardas, com o quadro todo tracejado."""
    linhas = []
    for _, r in t.iterrows():
        rot = f"{r['nivel']} ({_int(r['pessoas'])})"
        for serie, v in (("Mulheres", r["pct_mulheres"]), ("Pretas e pardas", r["pct_negras"])):
            linhas.append({"nivel": rot, "serie": serie, "pct": float(v) if pd.notna(v) else 0, "txt": _pct(v, 0)})
    ordem = [f"{n} ({_int(p)})" for n, p in zip(t["nivel"], t["pessoas"])][::-1]
    y = {"field": "nivel", "type": "nominal", "sort": ordem, "axis": {"title": None, "labelLimit": 260}}
    cor = {"field": "serie", "scale": {"domain": ["Mulheres", "Pretas e pardas"], "range": ["#EF3976", "#4A8FA8"]},
           "legend": {"orient": "top", "title": None}}
    x = {"field": "pct", "type": "quantitative", "scale": {"domain": [0, 1]}, "axis": {"format": ".0%", "grid": True, "title": None}}
    ref = [{"serie": "Mulheres", "v": pm or 0}, {"serie": "Pretas e pardas", "v": pn or 0}]
    return {"layer": [
        {"data": {"values": linhas}, "mark": {"type": "bar", "cornerRadiusEnd": 3, "height": {"band": .8}},
         "encoding": {"y": y, "yOffset": {"field": "serie"}, "x": x, "color": cor,
                      "tooltip": [{"field": "nivel", "title": "Nível"}, {"field": "serie", "title": " "}, {"field": "txt", "title": "%"}]}},
        {"data": {"values": linhas}, "mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 10, "fontWeight": 700, "color": CINZA_ESCURO},
         "encoding": {"y": y, "yOffset": {"field": "serie"}, "x": x, "text": {"field": "txt"}}},
        {"data": {"values": ref}, "mark": {"type": "rule", "strokeDash": [5, 4], "strokeWidth": 1.5},
         "encoding": {"x": {"field": "v", "type": "quantitative", "scale": {"domain": [0, 1]}}, "color": cor}},
    ]}


def linhas_diversidade(ev: pd.DataFrame) -> dict:
    linhas = []
    for _, r in ev.iterrows():
        for serie, v in (("Mulheres", r["pct_mulheres"]), ("Pretas e pardas", r["pct_negras"])):
            if pd.notna(v):
                linhas.append({"mes": _mes_txt(r["periodo"]), "serie": serie, "pct": float(v), "txt": _pct(v)})
    x = {"field": "mes", "type": "ordinal", "sort": [_mes_txt(p) for p in ev["periodo"]], "axis": {"labelAngle": 0, "title": None}}
    y = {"field": "pct", "type": "quantitative", "scale": {"zero": False, "padding": 12}, "axis": {"format": ".0%", "grid": True, "title": None}}
    cor = {"field": "serie", "scale": {"domain": ["Mulheres", "Pretas e pardas"], "range": ["#EF3976", "#4A8FA8"]},
           "legend": {"orient": "top", "title": None}}
    return {"layer": [
        {"data": {"values": linhas}, "mark": {"type": "line", "strokeWidth": 2.5, "point": {"size": 36, "filled": True}},
         "encoding": {"x": x, "y": y, "color": cor, "tooltip": [{"field": "mes", "title": "Mês"}, {"field": "serie", "title": " "},
                                                               {"field": "txt", "title": "%"}]}},
        {"data": {"values": linhas}, "mark": {"type": "text", "dy": -11, "fontSize": 10, "fontWeight": 700},
         "encoding": {"x": x, "y": y, "text": {"field": "txt"}, "color": cor}},
    ]}


def retrato_frente(frente: str, r: dict) -> None:
    st.html(f"""<div class="rt-card" style="border-top-color:{AZUL}">
      <div class="rt-nome" style="color:{AZUL}">{escape(frente)}</div>
      <div class="rt-num">{_int(r["pessoas"])} <span>pessoas · {_pct(r["pct_quadro"])} do quadro</span></div>
      <div class="rt-linhas"><div><span>Idade média</span><b>{escape(r["idade_media"])}</b></div>
        <div><span>Tempo de casa médio</span><b>{escape(r["tempo_casa"])}</b></div></div>
      {_barra_composicao("Sexo", r["sexo"], {**CORES_SEXO, "Feminino": "#EF3976"})}
      {_barra_composicao("Raça/cor", r["raca"], CORES_RACA)}
      {_barra_composicao("Geração", r["geracao"], CORES_GERACAO)}
    </div>""")


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
                       get_fill_color=[6, 77, 102, 115], get_line_color=[6, 77, 102, 230], line_width_min_pixels=1.2,
                       stroked=True, pickable=True)
    vista = pdk.ViewState(latitude=float(d["latitude"].mean()), longitude=float(d["longitude"].mean()), zoom=4.2)
    deck = pdk.Deck(layers=[camada], initial_view_state=vista, map_provider="carto", map_style="light",
                    tooltip={"html": "<b>{cidade}</b><br/>Headcount: {hc_txt}", "style": {"fontFamily": "Nunito"}})
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
navegacao = st.navigation([
    st.Page(lambda: pagina_geral(), title="Visão geral", icon=":material/dashboard:", url_path="visao-geral", default=True),
    st.Page(lambda: pagina_diversidade(), title="Diversidade", icon=":material/diversity_3:", url_path="diversidade"),
    st.Page(lambda: pagina_evolucao(), title="Evolução", icon=":material/show_chart:", url_path="evolucao"),
    st.Page(lambda: pagina_entrantes(), title="Quem está entrando", icon=":material/person_add:", url_path="quem-esta-entrando"),
])
opcoes = lambda c: sorted(df[c].dropna().unique())  # noqa: E731
with pp.barra_lateral(fonte="Neon + Databricks", atualizado_em=carga):
    st.markdown("**Período**")
    _padrao = (m.inicio_padrao(ref), ref)
    _escolha = st.date_input("Período", value=_padrao, min_value=date(2020, 1, 1), max_value=ref,
                             format="DD/MM/YYYY", label_visibility="collapsed")
    per_ini, per_fim = _escolha if isinstance(_escolha, (tuple, list)) and len(_escolha) == 2 else _padrao
    st.caption("Evolução e admitidos usam o período inteiro; o resto mostra o quadro na data final.")
    st.markdown("**Filtros**")
    sel = {
        "frente": st.multiselect("Frente", [f for f in m.ORDEM_FRENTE if f in set(df["frente"])], placeholder="Todas"),
        "diretoria": st.multiselect("Diretoria", opcoes("diretoria"), placeholder="Todas"),
        "area": st.multiselect("Área", opcoes("area"), placeholder="Todas"),
        "nome_centro_custo": st.multiselect("Centro de custo", opcoes("nome_centro_custo"), placeholder="Todos"),
        "familia_cargo": st.multiselect("Família de cargo", opcoes("familia_cargo"), placeholder="Todas"),
        "nivel": st.multiselect("Nível", [n for n in m.ORDEM_NIVEL if n in set(df["nivel"])] +
                                sorted(set(df["nivel"]) - set(m.ORDEM_NIVEL)), placeholder="Todos"),
        "uf": st.multiselect("UF", opcoes("uf"), placeholder="Todas"),
        "vinculo": st.multiselect("Vínculo", opcoes("vinculo"), placeholder="Todos",
                                  help="Classificação do colaborador (CLT por experiência, estagiário, prazo determinado, diretor, PJ…)."),
        "sexo": st.multiselect("Sexo", opcoes("sexo"), placeholder="Todos"),
    }
    sel_tempo = st.multiselect("Tempo de casa", list(reversed(m.ORDEM_TEMPO_CASA)), placeholder="Todos",
                               help="Tempo de casa na data de cada foto (data final nos cards; fim de cada mês na evolução).")

ref_p = min(per_fim, ref)
rotulos = {"frente": "Frente", "diretoria": "Diretoria", "area": "Área", "nome_centro_custo": "Centro de custo",
           "familia_cargo": "Família de cargo", "nivel": "Nível", "uf": "UF", "vinculo": "Vínculo", "sexo": "Sexo"}
pp.cabecalho("Dados Demográficos" if navegacao.title == "Visão geral" else navegacao.title, atualizado_em=carga,
             filtros={"Período": f"{per_ini:%d/%m/%Y} a {ref_p:%d/%m/%Y}", **{rotulos[c]: v for c, v in sel.items()},
                      "Tempo de casa": sel_tempo},
             legenda=f"Quadro em {ref_p:%d/%m/%Y} · evolução de {per_ini:%d/%m/%Y} até {ref_p:%d/%m/%Y} · dados de {ref:%d/%m/%Y}")

base = df
for col, vals in sel.items():
    if vals:
        base = base[base[col].isin(vals)]
ativos = m.ativos_em(base, ref_p, sel_tempo)
k = m.kpis(base, ref_p, sel_tempo)


# ================================================================ visão geral
def pagina_geral() -> None:
    pp.secao("Quadro na data final")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dl = k["headcount"] - k["headcount_anterior"]
        pp.kpi("Headcount", _int(k["headcount"]), "Estável" if dl == 0 else f"{'▲' if dl > 0 else '▼'} {_int(abs(dl))} vs mês ant.",
               VERDE if dl > 0 else VERMELHO if dl < 0 else CINZA)
    with c2:
        pa, pb = k["pct_feminino"], k["pct_feminino_anterior"]
        dif = (pa - pb) * 100 if pa is not None and pb is not None else 0
        pp.kpi("% Feminino", _pct(pa), "Estável" if abs(dif) < 0.05 else f"{'▲' if dif > 0 else '▼'} {abs(dif):.1f}".replace(".", ",") + " pp vs mês ant.",
               VERDE if dif >= 0.05 else VERMELHO if dif <= -0.05 else CINZA)
    with c3:
        pp.kpi("Tempo de casa médio", k["tempo_casa"], "média de permanência", CINZA)
    with c4:
        pp.kpi("Idade média", k["idade_media"], "média do quadro ativo", CINZA)
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

    pp.secao("Como é cada gênero na companhia")
    rt = m.retrato_por_sexo(ativos)
    r1, r2 = st.columns(2)
    with r1:
        retrato("Masculino", rt["Masculino"])
    with r2:
        retrato("Feminino", rt["Feminino"])
    st.html('<div class="nota">Quadro na data final, com os filtros aplicados. Raça/cor e geração em % de cada grupo; '
            'passe o mouse na barra para ver o número de pessoas.</div>')

    pp.secao("Idade, geração e tempo de casa")
    b1, b2, b3 = st.columns(3)
    with b1:
        pp.grafico("Faixa etária", barras_horizontais(m.contagem(ativos, "faixa_etaria", m.ORDEM_FAIXA_ETARIA), "faixa_etaria", m.ORDEM_FAIXA_ETARIA), 290, SEM_DADOS)
    with b2:
        pp.grafico("Geração", barras_horizontais(m.contagem(ativos, "geracao", m.ORDEM_GERACAO), "geracao", m.ORDEM_GERACAO), 290, SEM_DADOS)
    with b3:
        pp.grafico("Tempo de casa", barras_horizontais(m.contagem(ativos, "faixa_tempo_casa", m.ORDEM_TEMPO_CASA), "faixa_tempo_casa", m.ORDEM_TEMPO_CASA), 290, SEM_DADOS)

    secao_locais()


# ================================================================ diversidade
def pagina_diversidade() -> None:
    if ativos.empty:
        st.info(SEM_DADOS, icon=":material/info:")
        st.stop()
    pm, pn = m._pct_mulheres_negras(ativos)
    lid = ativos[ativos["nivel"].isin(m.ORDEM_NIVEL[m.ORDEM_NIVEL.index("Coordenador/Especialista"):])]
    lm, ln = m._pct_mulheres_negras(lid)
    pp.secao("Diversidade na liderança")
    c = st.columns(4)
    with c[0]:
        pp.kpi("Mulheres no quadro", _pct(pm), f"{_int((ativos['sexo'] == 'Feminino').sum())} pessoas")
    with c[1]:
        pp.kpi("Mulheres na liderança", _pct(lm), f"{_int(len(lid))} pessoas na liderança",
               VERMELHO if lm is not None and pm is not None and lm < pm - .05 else CINZA, ajuda=AJUDA_LIDERANCA)
    with c[2]:
        pp.kpi("Pretas e pardas no quadro", _pct(pn), f"{_int(ativos['raca_cor'].isin(m.NEGRAS).sum())} pessoas")
    with c[3]:
        pp.kpi("Pretas e pardas na liderança", _pct(ln), "coordenação para cima",
               VERMELHO if ln is not None and pn is not None and ln < pn - .05 else CINZA, ajuda=AJUDA_LIDERANCA)
    niv = m.diversidade_por_nivel(ativos)
    pp.grafico("% de mulheres e de pretas e pardas em cada nível", diversidade_nivel(niv, pm, pn), max(300, 58 * len(niv)), SEM_DADOS)
    st.html('<div class="nota">Níveis do operacional (embaixo) ao conselho (em cima), com as variações juntas (Gerente inclui '
            'Gerente de Vendas; Gerente Executivo inclui os de Obras; Coordenador/Especialista inclui Coordenador de Obras; '
            'Diretor inclui Diretor de Obras). Linhas tracejadas = o quadro todo. Entre parênteses, pessoas no nível.</div>')

    pp.secao("Como é cada frente")
    rf = m.retrato_por_frente(ativos)
    if not rf:
        st.info(SEM_DADOS, icon=":material/info:")
    else:
        cols = st.columns(len(rf))
        for col, (frente, r) in zip(cols, rf.items()):
            with col:
                retrato_frente(frente, r)
        st.html('<div class="nota">Quadro na data final, com os filtros aplicados. Sexo, raça/cor e geração em % de cada frente.</div>')


# ================================================================ evolução
def _variacao(ini: float, fim: float) -> tuple[str, str]:
    """Nota "+12 (+1,5%) desde set/25" e a cor (verde cresceu, vermelho caiu)."""
    dif = fim - ini
    pct = f" ({'+' if dif >= 0 else '−'}{abs(dif) / ini * 100:.1f}%)".replace(".", ",") if ini else ""
    return f"{'+' if dif > 0 else '−' if dif < 0 else ''}{_int(abs(dif))}{pct} desde {_mes_txt(per_ini)}", VERDE if dif > 0 else VERMELHO if dif < 0 else CINZA


def _variacao_pp(ini: float | None, fim: float | None) -> str:
    if ini is None or fim is None or pd.isna(ini) or pd.isna(fim):
        return ""
    dif = (fim - ini) * 100
    return f"{_pct(fim)} do quadro ({'+' if dif >= 0 else '−'}{abs(dif):.1f} pp)".replace(".", ",")


def pagina_evolucao() -> None:
    evd = m.evolucao_diversidade(base, per_ini, ref_p, sel_tempo)
    pp.secao("Quanto o quadro mudou no período")
    if len(evd) >= 2:
        a, b = evd.iloc[0], evd.iloc[-1]
        c = st.columns(4)
        with c[0]:
            pp.kpi("Headcount", _int(b["pessoas"]), *_variacao(a["pessoas"], b["pessoas"]),
                   ajuda=f"Quadro ativo no fim de {_mes_txt(per_ini)} comparado com a data final ({ref_p:%d/%m/%Y}), com os filtros aplicados.")
        with c[1]:
            nota, cor = _variacao(a["homens"], b["homens"])
            pp.kpi("Homens", _int(b["homens"]), nota, cor)
        with c[2]:
            nota, cor = _variacao(a["mulheres"], b["mulheres"])
            pp.kpi("Mulheres", _int(b["mulheres"]), nota, cor)
        with c[3]:
            nota, cor = _variacao(a["negras"], b["negras"])
            pp.kpi("Pretas e pardas", _int(b["negras"]), nota, cor)
        st.html(f'<div class="nota">Participação no quadro — mulheres: {_variacao_pp(a["pct_mulheres"], b["pct_mulheres"])}; '
                f'pretas e pardas: {_variacao_pp(a["pct_negras"], b["pct_negras"])}. Variação entre o fim de {_mes_txt(per_ini)} '
                f'e {ref_p:%d/%m/%Y}.</div>')
    pp.secao("Headcount por sexo")
    ev = m.evolucao_sexo(base, per_ini, ref_p, sel_tempo)
    if ev.empty:
        _sem_dados_grafico("Evolução do headcount por sexo")
    else:
        pp.grafico("Evolução do headcount por sexo", evolucao(ev), 360, SEM_DADOS)
    pp.secao("Evolução da diversidade")
    pp.grafico("% de mulheres e de pretas e pardas no fim de cada mês", linhas_diversidade(evd), 320, SEM_DADOS)
    st.html('<div class="nota">Participação no quadro ativo no fim de cada mês (o último mês vai até a data final).</div>')


# ================================================================ quem está entrando
def pagina_entrantes() -> None:
    e = m.entrantes(base, per_ini, ref_p)
    pp.secao("Perfil de quem entrou no período")
    if e.empty:
        st.info("Ninguém admitido no período com os filtros aplicados.", icon=":material/info:")
        st.stop()
    cmp = m.comparar_entrantes(e, ativos)

    def nota_vs(p, q):
        if p is None or q is None:
            return "", CINZA
        dif = (p - q) * 100
        return f"no quadro: {_pct(q)} ({'+' if dif >= 0 else '−'}{abs(dif):.1f} pp)".replace(".", ","), VERDE if dif >= 1 else VERMELHO if dif <= -1 else CINZA

    c = st.columns(4)
    with c[0]:
        pp.kpi("Admitidos no período", _int(cmp["admitidos"]), f"{_int(cmp['ainda_ativos'])} ainda ativos")
    with c[1]:
        pp.kpi("Mulheres entre admitidos", _pct(cmp["pct_mulheres"]), *nota_vs(cmp["pct_mulheres"], cmp["pct_mulheres_quadro"]))
    with c[2]:
        pp.kpi("Pretas e pardas entre admitidos", _pct(cmp["pct_negras"]), *nota_vs(cmp["pct_negras"], cmp["pct_negras_quadro"]))
    with c[3]:
        pp.kpi("Idade média na admissão", cmp["idade_admissao"], f"idade média do quadro: {cmp['idade_quadro']}")
    cores = {"sexo": {**CORES_SEXO, "Feminino": "#EF3976"}, "raca_cor": CORES_RACA, "geracao": CORES_GERACAO}
    titulos = {"sexo": "Sexo", "raca_cor": "Raça/cor", "geracao": "Geração"}
    g = st.columns(3)
    for col, campo in zip(g, ("sexo", "raca_cor", "geracao")):
        with col:
            st.html(f'<div class="rt-card" style="border-top-color:{AZUL}"><div class="rt-nome" style="color:{AZUL}">{titulos[campo]}</div>'
                    + "".join(_barra_composicao(grupo, partes, cores[campo]) for grupo, partes in cmp["composicao"][campo].items())
                    + "</div>")
    st.html('<div class="nota">Admitidos no período = pessoas com admissão entre a data inicial e a final (com os filtros aplicados), '
            'mesmo as que já saíram. Comparação com o quadro ativo na data final. Verde = participação maior que a do quadro.</div>')


# ================================================================ onde estão (fim da visão geral)
def secao_locais() -> None:
    pp.secao("Onde estão: diretorias, áreas e locais de trabalho")
    t1, t2 = st.columns([8, 4])
    with t1:
        st.html('<div class="titulo-graf">Distribuição por área e diretoria</div>')
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


navegacao.run()
