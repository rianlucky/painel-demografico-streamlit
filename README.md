# Dados Demográficos — perfil do quadro de colaboradores

Painel Streamlit migrado do dashboard AI/BI "Dashboard Demográficos" do Databricks
(especificação em `00 - Central de Gente & Dados/ZZ - Prompts Migração Databricks - Streamlit+Neon/Dashboard_Demograficos_Streamlit_Spec.md`).
Lê **só do Neon**, por uma view própria (sem nome, sem data de nascimento, pessoa pseudonimizada),
com um usuário de banco só de leitura. Com login (o mesmo dos outros painéis) e matriz de acessos
(painel `demograficos`, grupo Desenvolvimento Organizacional). Padrão visual da skill
`padrao-painel-streamlit`.

## Rodar

```powershell
streamlit run app.py
```

`.streamlit/secrets.toml` (fora do Git) tem `[neon]` com a conexão e `[app] email_suporte` —
ver `.streamlit/secrets.toml.example`.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `app.py` | Tela: cards, perfil predominante, gráficos (Vega-Lite), distribuição por área/diretoria e mapa (pydeck) |
| `metricas.py` | Todos os cálculos, sem Streamlit. O relatório de validação (`_neon/validacao`) usa o mesmo módulo |
| `auth.py` | Login e checagem da matriz de acessos |
| `painel_padrao.py` | Barra lateral padrão da Central e `pp.grafico` |
| `assets/icone-demograficos.png` | Ícone do painel (barra lateral e aba do navegador) |

## Regras (as da especificação)

1. **Headcount numa data**: admitido até a data e sem desligamento (ou desligado depois); pessoas distintas.
2. **Gerações** por ano de nascimento; **faixas etárias** e de **tempo de casa** da especificação.
3. **Tempo de casa médio** "X anos Y meses"; **idade média** arredondada.

## O que mudou em relação ao Databricks (de propósito)

| Ponto | Databricks | Aqui | Por quê |
|---|---|---|---|
| Base | silver 00004 (fotos diárias) | `core.fato_funcionario` (gold, mesmos dados) por `core.v_demografico_base` | mesma informação, sem as 126 fotos |
| Diretoria / área | `rh.gold.dim_departamento_areas_diretorias` + ~280 CCs à mão no SQL | mapeamento oficial (`core.v_funcionario_diretoria`) | a dim está desatualizada |
| Família de cargo | join com `rh.silver.dim_cargo` | a da própria atribuição | o join duplicava 67 pessoas (headcount 1.587 em vez de 1.520) |
| Cidade no mapa | `dim_local` + 40 coordenadas à mão no SQL | `core.local_cidade` (mesmo mapeamento do Headcount) | cobre todos os ativos; a dim_local deixava 56 fora |
| Raça/Cor predominante | `MAX_BY(raca_cor, 1)` (valor arbitrário) | a raça/cor mais frequente | a medida original não calculava moda |
| Data | `CURRENT_DATE()` | filtro de **período**: cards, perfis e mapa mostram o quadro na data final (idade e tempo de casa recalculados); a evolução usa o período inteiro | ver o perfil em qualquer data |
| Faixa de tempo de casa | 8 faixas em uns widgets, 5 em outros | as mesmas 8 faixas em tudo | um filtro só, sem divergência |
| Filtros | acima dos gráficos | barra lateral (padrão da Central), valendo para todos os widgets | |

Conferência (28/09/2026, referência 27/09): headcount total e da Diretoria Comercial, headcount por
diretoria e ausência de duplicidade batem com a régua do relatório de validação (mesmos 1.520 do
painel Turnover).

## Padrão visual atualizado (30/09/2026)

Login padrão da Central (card único, adaptável a celular), título em Nunito com selos de "Atualizado em" e dos filtros aplicados (vão junto num print/PDF), cards com o recorte em seta da marca, quatro seções (quadro na data final, evolução, idade/geração/tempo de casa, onde estão) e impressão em A4 deitada. Mapa com bolhas semitransparentes, como no Headcount Total. Cálculos sem mudança.

## Páginas e visuais novos (30/09/2026)

Quatro páginas na barra lateral (st.navigation): **Visão geral** (cards, retrato de cada gênero com persona, idade/geração/tempo de casa, diretorias/áreas/mapa), **Diversidade** (% de mulheres e de pretas e pardas por nível de gerenciamento, cards de liderança e retrato de cada frente Obras/Corporativo/Comercial), **Evolução** (cards de variação no período — headcount, homens, mulheres, pretas e pardas, em número e % — headcount por sexo e % de mulheres e de pretas e pardas mês a mês) e **Quem está entrando** (perfil dos admitidos no período x quadro). Filtros novos: Frente, Nível (variações agrupadas), UF e Vínculo — migração `_neon/migrations/020_demograficos_diversidade.sql` acrescenta nível, frente, UF e vínculo em `core.v_demografico_base`. Liderança = coordenação para cima.
