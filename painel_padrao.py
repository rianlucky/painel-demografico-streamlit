"""Padrão visual dos painéis Streamlit da Central de Gente & Dados (Pacaembu Construtora).

Modelo mantido na skill `padrao-painel-streamlit` (People Analytics/.claude/skills). Cada
painel tem a sua cópia deste arquivo (o deploy no Streamlit Cloud é por repositório).

Barra lateral, sempre nesta ordem:
    1. Logo: ícone do painel + nome (st.logo, fixo no topo)
    2. "Olá, {nome}" + botão Sair   (quando há login; em desenvolvimento, aviso discreto)
    3. Abas / páginas, se houver   (st.navigation ou st.radio, feito pelo painel)
    4. Filtros                      (feitos pelo painel dentro do `with barra_lateral(...)`)
    5. Fonte e Atualizado em        (mesmo visual do card do Hub de Indicadores)

Uso:
    import painel_padrao as pp
    pp.logo("assets/icone.png", "Turnover")
    with pp.barra_lateral(fonte="Neon + Databricks", atualizado_em=datetime(...)):
        st.multiselect(...)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

AZUL = "#064D66"
AZUL_ESCURO = "#003244"
AMARELO = "#FAB900"
FUSO = ZoneInfo("America/Sao_Paulo")

_CSS = f"""<style>
[data-testid="stSidebar"] .pp-ola {{ color:{AZUL_ESCURO}; font-size:.95rem; margin:.1rem 0 .35rem; }}
[data-testid="stSidebar"] .pp-dev {{ color:#7A8C96; font-size:.78rem; margin:.1rem 0 .35rem; }}
[data-testid="stSidebar"] .pp-meta {{ background:#F3F6F8; border-radius:10px; padding:.55rem .75rem;
    font-size:.8rem; border-left:4px solid {AMARELO}; margin-top:.4rem; }}
[data-testid="stSidebar"] .pp-meta div {{ display:flex; gap:.5rem; padding:.12rem 0; color:{AZUL_ESCURO}; }}
[data-testid="stSidebar"] .pp-meta span {{ flex:0 0 5.9rem; color:#7A8C96; font-weight:600; font-size:.74rem; white-space:nowrap; }}
</style>"""


@st.cache_resource
def _wordmark(icone: str, titulo: str):
    """Ícone + nome do painel numa imagem só (st.logo aceita só imagem). Mesmo padrão do
    Headcount Total e da Aderência Salarial."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(icone).convert("RGBA")
        alt = 64
        img = img.resize((int(img.width * alt / img.height), alt))
        fonte = None
        for f in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            if Path(f).exists():
                fonte = ImageFont.truetype(f, 34)
                break
        fonte = fonte or ImageFont.load_default()
        caixa = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), titulo, font=fonte)
        larg, alt_txt = caixa[2] - caixa[0], caixa[3] - caixa[1]
        tela = Image.new("RGBA", (img.width + 14 + larg + 4, alt), (0, 0, 0, 0))
        tela.paste(img, (0, 0), img)
        ImageDraw.Draw(tela).text((img.width + 14, (alt - alt_txt) // 2 - caixa[1]), titulo, font=fonte, fill=AZUL)
        return tela
    except Exception:  # noqa: BLE001 — sem PIL/fonte, cai só no ícone
        return None


def logo(icone: str | Path, titulo: str) -> None:
    icone = str(icone)
    marca = _wordmark(icone, titulo)
    st.logo(marca if marca is not None else icone, icon_image=icone, size="large")


def _conta() -> None:
    usuario = st.session_state.get("auth_user")
    if usuario:
        st.html(f'<div class="pp-ola">Olá, <b>{escape(usuario.get("name") or usuario.get("email", ""))}</b></div>')
        if st.button("Sair", key="pp_sair", width="stretch", icon=":material/logout:"):
            st.session_state["auth_user"] = None
            st.session_state["auth_email"] = None
            st.rerun()
    else:
        st.html('<div class="pp-dev">Modo desenvolvimento · sem login</div>')
    st.divider()


def _formatar(valor) -> str:
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(FUSO)
        return f"{valor:%d/%m/%Y %H:%M}"
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return str(valor)


def rodape(fonte: str, atualizado_em=None, extra: dict[str, str] | None = None) -> None:
    linhas = {"Fonte": fonte}
    if atualizado_em is not None:
        linhas["Atualizado em"] = _formatar(atualizado_em)
    linhas |= extra or {}
    corpo = "".join(f"<div><span>{escape(k)}</span>{escape(str(v))}</div>" for k, v in linhas.items())
    st.html(f'<div class="pp-meta">{corpo}</div>')


@contextlib.contextmanager
def barra_lateral(fonte: str, atualizado_em=None, extra: dict[str, str] | None = None):
    """Monta a barra lateral no padrão: conta no topo, o conteúdo do `with` (abas e filtros)
    no meio, Fonte/Atualizado em no fim."""
    with st.sidebar:
        st.html(_CSS)
        _conta()
        yield
        st.divider()
        rodape(fonte, atualizado_em, extra)


# ----------------------------------------------------------------------------- gráficos (Vega-Lite)
# Use pp.grafico(titulo, spec, altura) em todo gráfico. Ele: mostra o aviso "i" quando não há dados
# no filtro; leva os dados para dentro das camadas em JSON seguro; e passa uma key que muda com os
# dados — sem isso, gráficos com camadas não redesenhavam quando o filtro mudava (Turnover, 28/09).
FONTE_GRAFICO, CINZA, CINZA_ESCURO, BORDA, GRID = "Inter", "#6B7280", "#1F2937", "#CBD8DE", "#E5EDF1"


def _config() -> dict:
    return {"view": {"stroke": None}, "font": FONTE_GRAFICO,
            "axis": {"labelFont": FONTE_GRAFICO, "labelFontSize": 11, "labelColor": CINZA, "domainColor": BORDA,
                     "gridColor": GRID, "tickColor": BORDA, "title": None},
            "legend": {"labelFont": FONTE_GRAFICO, "labelFontSize": 11, "labelColor": CINZA_ESCURO, "title": None, "orient": "top"}}


SEM_DADOS = "Sem desligamentos no filtro selecionado."


def _linhas(spec) -> list[dict]:
    """Todas as linhas de dados do spec (no topo e dentro das camadas)."""
    out = []
    if isinstance(spec, dict):
        out += (spec.get("data") or {}).get("values") or []
        for camada in spec.get("layer", []):
            out += _linhas(camada)
    return out


def _sem_dados(spec: dict) -> bool:
    """Nada para desenhar: sem linhas, ou todas as contagens zeradas (donut/funil de uma área sem
    desligados quebraria o gráfico)."""
    linhas = _linhas(spec)
    if not linhas:
        return True
    campos = [c for c in ("desligamentos", "admitidos", "desligamentos_voluntario", "desligamentos_involuntario")
              if c in linhas[0]]
    return bool(campos) and all(not (r.get(c) or 0) for r in linhas for c in campos)


def _json_seguro(linhas: list[dict]) -> list[dict]:
    return json.loads(pd.DataFrame(linhas).to_json(orient="records", date_format="iso")) if linhas else []


def _dados_nas_camadas(spec: dict) -> dict:
    """Leva os dados do topo para cada camada do primeiro nível (em JSON seguro). Com os dados no
    topo e várias camadas, o Streamlit separa os dados do desenho e o navegador às vezes não
    redesenha quando o filtro muda (evolução e donut de motivos, 28/09).
    Um grupo de camadas recebe os dados no próprio nível do grupo — junto com o transform dele
    (ex.: fold das séries); dar dados às camadas internas faria elas ignorarem esse transform."""
    spec = dict(spec)
    topo = spec.pop("data", None)
    if "layer" not in spec:
        if topo is not None:
            spec["data"] = {"values": _json_seguro(topo.get("values", []))}
        return spec
    camadas = []
    for camada in spec["layer"]:
        camada = dict(camada)
        dados = camada.get("data") or topo
        if dados is not None:
            camada["data"] = {"values": _json_seguro(dados.get("values", []))}
        camadas.append(camada)
    spec["layer"] = camadas
    return spec


def grafico(titulo: str, spec: dict, altura: int = 300, aviso: str = SEM_DADOS) -> None:
    st.html(f'<div class="titulo-graf">{titulo}</div>')
    if _sem_dados(spec):
        st.info(aviso, icon=":material/info:")
        return
    spec = _dados_nas_camadas(spec)
    spec = {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "height": altura, "config": _config(), **spec}
    # key muda junto com os dados: o Streamlit manda os dados separados do desenho e, em gráficos
    # com várias camadas, só trocar os dados às vezes não redesenha — com a key nova, redesenha sempre
    chave = hashlib.md5(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()
    st.vega_lite_chart(spec, width="stretch", key=f"graf-{chave}")


