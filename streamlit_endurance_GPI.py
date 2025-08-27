import math
from typing import Optional
import re

import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ==================== Config geral ====================
st.set_page_config(page_title="📊 Análise Estatística Endurance", layout="wide")

# ==================== Utils ====================
def time_to_seconds(t):
    """Converte 'M:SS.mmm' ou string numérica para segundos; retorna NaN se não parsear."""
    try:
        ts = str(t).replace(',', '.').strip()
        if ts == "" or ts.lower() in {"nan", "none"}:
            return pd.NA
        if ':' in ts:
            m, s = ts.split(':', 1)
            return int(m) * 60 + float(s)
        return float(ts)
    except:
        return pd.NA

def coerce_numeric(series: pd.Series) -> pd.Series:
    """Converte para float lidando com separador de milhar e vírgula decimal."""
    def smart_to_float(x):
        s = str(x).strip()
        if s == "" or s.lower() in {"nan", "none"}:
            return pd.NA
        # remove separador de milhar (ponto) quando seguido de 3 dígitos
        s = re.sub(r'\.(?=\d{3}\b)', '', s)
        # vírgula decimal -> ponto
        s = s.replace(',', '.')
        try:
            return float(s)
        except:
            return pd.NA
    return series.apply(smart_to_float)

def find_lap_column(df: pd.DataFrame) -> str:
    """Tenta localizar a coluna de número de volta. Retorna/garante 'Lap'."""
    candidates = [c for c in df.columns if c.strip().lower() in {"lap", "leadlap", "lap #", "#lap"}]
    if candidates:
        if "Lap" not in df.columns:
            df.rename(columns={candidates[0]: "Lap"}, inplace=True)
        return "Lap"
    if "Lap" not in df.columns:
        df["Lap"] = range(1, len(df) + 1)
    return "Lap"

def find_lap_time_column(df: pd.DataFrame) -> Optional[str]:
    """Descobre a coluna de tempo de volta; retorna o nome original ou None."""
    exacts = [
        "Lap Tm","LapTm","Lap Time","LapTime","Lap_Time","Best Lap Tm","Best Lap",
        "Lap Time (s)","LapTime(s)","LAP_TM","LAP_TIME"
    ]
    for c in exacts:
        if c in df.columns:
            return c

    for c in df.columns:
        cl = c.lower().replace(" ", "").replace("_","")
        if "lap" in cl and ("tm" in cl or "time" in cl):
            return c

    best, score = None, 0.0
    for c in df.columns:
        conv = df[c].apply(time_to_seconds)
        ratio = conv.notna().mean()
        name_hit = (c.lower().endswith("tm") or "time" in c.lower() or "lap" in c.lower())
        if ratio >= 0.7 and name_hit and ratio > score:
            best, score = c, ratio
    return best

@st.cache_data
def load_excel(file) -> dict:
    # openpyxl é necessário para .xlsx
    return pd.read_excel(file, sheet_name=None)

def preprocess_df(df: pd.DataFrame) -> pd.DataFrame:
    """Converte *Tm* em seg; tenta numérico no resto quando fizer sentido."""
    out = df.copy()

    # Normaliza SSTRAP se vier como 'SSTRAP Tm' (texto)
    if "SSTRAP Tm" in out.columns and "SSTRAP" not in out.columns:
        out["SSTRAP"] = coerce_numeric(out["SSTRAP Tm"])

    find_lap_column(out)  # cria/normaliza 'Lap'
    for c in out.columns:
        if c == "SSTRAP Tm":
            continue
        if c.lower().endswith("tm"):
            out[c] = out[c].apply(time_to_seconds)
        else:
            maybe = coerce_numeric(out[c])
            if maybe.notna().mean() >= 0.5:
                out[c] = maybe
    return out

def derive_stints(df: pd.DataFrame, lap_time_col: str, threshold: float = 300.0) -> pd.DataFrame:
    """Cria 'Stint' com base em Lap Tm > limiar (fecha stint)."""
    if "Stint" in df.columns:
        return df
    stn = 1
    stints = []
    for t in df[lap_time_col].fillna(threshold + 1):
        stints.append(stn)
        if t > threshold:
            stn += 1
    out = df.copy()
    out["Stint"] = stints
    return out

def get_filtered(df: pd.DataFrame, stint_choice, min_lap_seconds, max_lap_seconds, is_time_metric: bool) -> pd.DataFrame:
    """Aplica filtros por Stint e faixa (min/max) de Lap Tm quando métrica é de tempo."""
    d = df.copy()
    if stint_choice != "All":
        d = d[d["Stint"] == stint_choice]
    if is_time_metric and "Lap Tm" in d.columns:
        d = d[pd.to_numeric(d["Lap Tm"], errors="coerce").notna()]
        d = d[d["Lap Tm"] >= float(min_lap_seconds)]
        d = d[d["Lap Tm"] <= float(max_lap_seconds)]
    return d

# -------- Entrada de float que aceita vírgula ou ponto --------
def parse_float_any(s: str) -> Optional[float]:
    """Aceita '10,5', '10.5', '1.234,56', '1,234.56' etc. Retorna float ou None se vazio."""
    if s is None:
        return None
    txt = str(s).strip().replace(" ", "")
    if txt == "":
        return None
    # Se tem os dois separadores, considera o último como decimal
    if "," in txt and "." in txt:
        last_comma = txt.rfind(",")
        last_dot = txt.rfind(".")
        if last_comma > last_dot:
            # milhar = ponto, decimal = vírgula
            txt = txt.replace(".", "")
            txt = txt.replace(",", ".")
        else:
            # milhar = vírgula, decimal = ponto
            txt = txt.replace(",", "")
    else:
        # Só vírgula -> decimal
        if "," in txt:
            txt = txt.replace(",", ".")
        # Só ponto -> já está certo
    try:
        return float(txt)
    except:
        return None

def float_input(label: str, default: float, min_value: float = 0.0, max_value: float = 1e9, key: str = None) -> float:
    """Text input que aceita vírgula/ponto e limita min/max."""
    raw = st.text_input(label, value=str(default).replace(".", ","), key=key)
    val = parse_float_any(raw)
    if val is None:
        st.caption("↳ Valor vazio/ inválido: usando padrão.")
        val = default
    val = max(min_value, min(max_value, val))
    return float(val)

def annotate_box(ax, bp, ys_list, idx, color, fs, dy):
    """Anota mediana, Q3 e Q1 de um boxplot."""
    data_i = np.array(ys_list[idx], dtype=float)
    q1 = float(np.percentile(data_i, 25))
    q3 = float(np.percentile(data_i, 75))
    med = float(np.median(data_i))

    median_line = bp["medians"][idx]
    median_line.set_color("black")
    median_line.set_linewidth(2.0)
    x_mid = float(np.mean(median_line.get_xdata()))
    y_med = float(np.mean(median_line.get_ydata()))

    ax.text(x_mid, y_med, f"{med:.3f}", fontsize=fs, va="center", ha="center",
            color="black", bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.5, linewidth=0),
            clip_on=True, zorder=5)
    ax.text(x_mid, q3 + dy, f"{q3:.3f}", fontsize=fs, va="bottom", ha="center",
            color="black", bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.5, linewidth=0),
            clip_on=True, zorder=5)
    ax.text(x_mid, q1 - dy, f"{q1:.3f}", fontsize=fs, va="top", ha="center",
            color="black", bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.5, linewidth=0),
            clip_on=True, zorder=5)

# ==================== App ====================
def main():
    st.title("📊 Análise Estatística Endurance")

    uploaded = st.file_uploader("Faça upload do arquivo Excel", type=["xlsx", "xls"])
    if not uploaded:
        st.info("Envie seu arquivo de estatísticas Endurance.")
        return

    sheets = load_excel(uploaded)

    # Opção para remover a última aba
    remove_last_sheet = st.checkbox("Remover última aba da planilha", value=True)
    if remove_last_sheet and len(sheets) >= 1:
        last_key = list(sheets.keys())[-1]
        del sheets[last_key]

    # Pré-processamento
    sheets_missing_laptm = []
    for name in list(sheets):
        df = preprocess_df(sheets[name])
        ltcol = find_lap_time_column(df)
        if ltcol:
            if ltcol != "Lap Tm":
                df.rename(columns={ltcol: "Lap Tm"}, inplace=True)
            df["Lap Tm"] = df["Lap Tm"].apply(time_to_seconds)
            df = derive_stints(df, lap_time_col="Lap Tm", threshold=300.0)
        else:
            df["Lap Tm"] = pd.NA
            df["Stint"] = 1
            sheets_missing_laptm.append(name)
        sheets[name] = df

    if sheets_missing_laptm:
        with st.expander("Abas sem coluna de tempo de volta identificável"):
            st.write(", ".join(sheets_missing_laptm))

    # -------------------- BLOCO 1 --------------------
    default_p1 = [s for s in sheets if s.strip().endswith("P1")]
    sessions = st.multiselect(
        "Selecione sessões para análise",
        options=list(sheets.keys()),
        default=default_p1[:3] if default_p1 else list(sheets.keys())[:3]
    )
    if not sessions:
        st.warning("Selecione ao menos uma aba (ex.: ‘- P1’).")
        return

    session_stint = {}
    for s in sessions:
        opts = sorted(pd.Series(sheets[s]["Stint"]).dropna().unique())
        session_stint[s] = st.selectbox(
            f"Stint para '{s}'",
            options=["All"] + list(opts),
            format_func=lambda x: "All" if x == "All" else f"Stint {int(x)}",
            key=f"stint_{s}"
        )

    chart_type = st.selectbox("Tipo de gráfico", ["Boxplot", "Linha", "Dispersão"])
    x_axis_mode = st.selectbox("Eixo X", ["Amostragem", "Lap"])

    first_df = sheets[sessions[0]]
    time_cols = [c for c in first_df.columns if c.lower().endswith("tm") and c != "SSTRAP Tm"]
    metric_opts = list(time_cols)
    if "SSTRAP" in first_df.columns:
        metric_opts += ["SSTRAP"]
    if not metric_opts:
        st.error("Não encontrei colunas de tempo (*Tm) nem 'SSTRAP'.")
        return

    labels_map = {c: c for c in metric_opts}
    if "SSTRAP" in labels_map:
        labels_map["SSTRAP"] = "Velocidade Máxima (SSTRAP)"

    metric = st.selectbox("Selecione métrica", options=metric_opts, format_func=lambda x: labels_map[x])
    ylabel = labels_map[metric]
    is_time_metric = metric.lower().endswith("tm")

    # ---- NOVO: mínimo e máximo aceitando vírgula/ponto ----
    min_lap = float_input("Excluir voltas com 'Lap Tm' abaixo de (s) (valor mínimo)", default=0.0, key="min_lap_main")
    max_lap = float_input("Excluir voltas com 'Lap Tm' acima de (s)", default=60.0, key="max_lap_main")
    if max_lap < min_lap:
        st.warning("O máximo não pode ser menor que o mínimo. Ajustei o máximo para ficar igual ao mínimo.")
        max_lap = float(min_lap)

    # Sliders de amostragem por sessão
    session_sample = {}
    filtered_exports = {}  # para downloads por sessão

    for s in sessions:
        df_f = get_filtered(sheets[s], session_stint[s], min_lap, max_lap, is_time_metric)
        avail = len(df_f)
        session_sample[s] = st.slider(
            f"Amostragem (voltas mais rápidas) em '{s}'",
            min_value=1, max_value=max(1, avail),
            value=min(30, avail) if avail else 1,
            key=f"sample_{s}"
        )

    series_x, series_y, labels = [], [], []
    for s in sessions:
        df_f = get_filtered(sheets[s], session_stint[s], min_lap, max_lap, is_time_metric)
        if metric not in df_f.columns:
            st.warning(f"'{metric}' não encontrado em {s}. Pulando.")
            continue
        df_sel = df_f.nsmallest(session_sample[s], metric)
        filtered_exports[s] = df_sel.copy()  # guarda para download

        lap_col = find_lap_column(df_sel)
        if x_axis_mode == "Lap":
            df_sel = df_sel.sort_values(lap_col)
            x = df_sel[lap_col].tolist()
            y = pd.to_numeric(df_sel[metric], errors="coerce").tolist()
        else:
            df_sel = df_sel.sort_values(metric)
            x = list(range(1, len(df_sel) + 1))
            y = pd.to_numeric(df_sel[metric], errors="coerce").tolist()
        series_x.append(x); series_y.append(y)
        labels.append(f"{s} ({'All' if session_stint[s]=='All' else 'Stint '+str(session_stint[s])})")

    # ---- Plot BLOCO 1 ----
    fig, ax = plt.subplots(figsize=(10, 4))
    if chart_type == "Boxplot":
        valid_pairs = [(ys, lbl) for ys, lbl in zip(series_y, labels) if len(ys) > 0]
        if not valid_pairs:
            st.warning("Sem dados para plotar.")
            return
        ys_list, lbls = zip(*valid_pairs)

        cycle = plt.rcParams.get("axes.prop_cycle", None)
        base_colors = cycle.by_key().get("color", ["C0"]) if cycle else ["C0"]
        cols = [base_colors[i % len(base_colors)] for i in range(len(lbls))]
        bp = ax.boxplot(ys_list, patch_artist=True)

        n_boxes = len(lbls); h_in = fig.get_size_inches()[1]
        fs = max(6, min(12, (10 * (h_in / 4.0)) * (8 / max(6, n_boxes))))  # 6–12 pt

        all_vals = np.concatenate([np.array(v, dtype=float) for v in ys_list])
        y_range = float(np.nanmax(all_vals) - np.nanmin(all_vals)) if all_vals.size else 1.0
        dy = max(0.002 * y_range, 0.0005)

        for i, (box, col) in enumerate(zip(bp["boxes"], cols)):
            box.set_facecolor(col); box.set_edgecolor(col)
            bp["whiskers"][2*i].set_color(col); bp["whiskers"][2*i + 1].set_color(col)
            bp["caps"][2*i].set_color(col); bp["caps"][2*i + 1].set_color(col)

            annotate_box(ax, bp, ys_list, i, col, fs, dy)

        handles = [mpatches.Patch(facecolor=c, edgecolor=c, label=l) for c, l in zip(cols, lbls)]
        ax.legend(handles=handles, loc="upper right", fontsize="xx-small")
        ax.set_xticks([])

    elif chart_type == "Linha":
        for x, y, lbl in zip(series_x, series_y, labels):
            if len(x) and len(y): ax.plot(x, y, label=lbl)
        ax.legend(loc="upper right", fontsize="xx-small")
    else:
        for x, y, lbl in zip(series_x, series_y, labels):
            if len(x) and len(y): ax.scatter(x, y, s=10, label=lbl)
        ax.legend(loc="upper right", fontsize="xx-small")

    ax.set_xlabel("Lap" if x_axis_mode == "Lap" else "Amostra")
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    # ---- Estatísticas ----
    st.header("📊 Estatísticas Descritivas por Amostragem")
    stats_frames = []
    for lbl, y in zip(labels, series_y):
        y_clean = pd.Series(pd.to_numeric(y, errors="coerce")).dropna()
        if not y_clean.empty:
            stats_frames.append(y_clean.describe().to_frame(name=lbl))
    if stats_frames:
        st.dataframe(pd.concat(stats_frames, axis=1))
    else:
        st.info("Sem dados suficientes para estatísticas descritivas.")

    # ---- Download dos dados filtrados por sessão ----
    st.subheader("⬇️ Baixar dados filtrados (por sessão)")
    for s in sessions:
        if s in filtered_exports and not filtered_exports[s].empty:
            st.download_button(
                label=f"Baixar '{s}' (CSV)",
                data=filtered_exports[s].to_csv(index=False).encode("utf-8"),
                file_name=f"{s}_filtrado.csv",
                mime="text/csv",
                key=f"dl_{s}"
            )

    # -------------------- BLOCO 2 (Métricas Avançadas por Stint) --------------------
    st.header(f"📋 Métricas Avançadas por Stint (Somente P1, Lap Tm entre {float(min_lap):.1f}s e {max_lap:.1f}s)")
    p1 = [s for s in sheets if s.strip().endswith("P1")]
    for special in ["42 - V.FOREST - P1", "22 - LANCASTER-ABRUNH(L)-MORAES", "42 - V.FOREST(L)-L.FOREST-R.MAR"]:
        if special in sheets and special not in p1:
            p1.append(special)

    rows = []
    for sess in p1:
        df_s = sheets[sess]
        if "Lap Tm" not in df_s.columns:
            continue
        df_s_local = df_s[pd.to_numeric(df_s["Lap Tm"], errors="coerce").notna()]
        df_s_local = df_s_local[df_s_local["Lap Tm"] >= float(min_lap)]
        for stn in sorted(pd.Series(df_s_local["Stint"]).dropna().unique()):
            cond = (df_s_local["Stint"] == stn) & (df_s_local["Lap Tm"] <= float(max_lap)) & (df_s_local["Lap Tm"] >= float(min_lap))
            df_grp = df_s_local[cond]
            if df_grp.empty:
                continue

            I   = df_grp.nsmallest(10, "Lap Tm")["Lap Tm"].mean()
            II  = df_grp["Lap Tm"].min()
            vel = df_grp["SSTRAP"].max() if "SSTRAP" in df_grp.columns else pd.NA

            n   = len(df_grp)
            n30 = max(math.ceil(n * 0.3), 1)
            chronological = df_grp.reset_index(drop=True)
            IV  = chronological.iloc[:n30]["Lap Tm"].mean()
            V   = chronological.iloc[-n30:]["Lap Tm"].mean()
            VI  = pd.Series([IV, V]).mean()

            times_sorted = df_grp["Lap Tm"].sort_values().reset_index(drop=True)
            n2 = len(times_sorted); k = int(n2 * 0.2)
            gauss = times_sorted.iloc[k:n2-k].mean() if n2 > 2*k else pd.NA

            if all(pd.notna(x) for x in [I, II, VI, gauss]):
                GPI = (I*4 + VI*2 + gauss*2 + II*2) / 10
            else:
                GPI = pd.NA

            rows.append({
                "Sessão":              sess,
                "Stint":               int(stn) if pd.notna(stn) else stn,
                "MédiaTop10":          round(I, 3)    if pd.notna(I)    else pd.NA,
                "MinLap":              round(II, 3)   if pd.notna(II)   else pd.NA,
                "Velocidade Máxima":   round(vel, 3)  if pd.notna(vel)  else pd.NA,
                "MédiaIni30%":         round(IV, 3)   if pd.notna(IV)   else pd.NA,
                "MédiaFim30%":         round(V, 3)    if pd.notna(V)    else pd.NA,
                "MédiaIV_V":           round(VI, 3)   if pd.notna(VI)   else pd.NA,
                "Gauss (20% trimmed)": round(gauss, 3) if pd.notna(gauss) else pd.NA,
                "GPI":                 round(GPI, 3)  if pd.notna(GPI)  else pd.NA
            })

    dfm = pd.DataFrame(rows)
    if dfm.empty:
        st.warning("Nenhuma métrica avançada calculada.")
    else:
        st.dataframe(dfm, use_container_width=True)
        csv = dfm.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Baixar métricas (CSV)", csv, "metricas_avancadas_P1.csv", "text/csv")

    # -------------------- BLOCO 3 (Boxplot independente — por sessão/stint) --------------------
    st.subheader("📦 Boxplot — Seletor independente (por sessão)")

    all_session_names = list(sheets.keys())
    sel_sessions2 = st.multiselect(
        "Selecione sessões para análise (Boxplot)",
        options=all_session_names,
        default=default_p1[:2] if default_p1 else all_session_names[:2],
        key="sessions_box2"
    )
    if not sel_sessions2:
        st.info("Sem dados para o boxplot independente.")
        return

    first_df2 = sheets[sel_sessions2[0]]
    time_cols2 = [c for c in first_df2.columns if c.lower().endswith("tm") and c != "SSTRAP Tm"]
    metric_opts2 = list(time_cols2)
    if "SSTRAP" in first_df2.columns:
        metric_opts2 += ["SSTRAP"]
    if not metric_opts2:
        st.warning("A sessão selecionada não tem colunas de tempo (*Tm) nem 'SSTRAP'.")
        return

    labels_map2 = {c: c for c in metric_opts2}
    if "SSTRAP" in labels_map2:
        labels_map2["SSTRAP"] = "Velocidade Máxima (SSTRAP)"
    metric2 = st.selectbox("Selecione métrica (Boxplot)", options=metric_opts2, format_func=lambda x: labels_map2[x], key="metric_box2")

    # ---- mínimo e máximo aceitando vírgula/ponto (Boxplot) ----
    min_lap2 = float_input("Excluir voltas com 'Lap Tm' abaixo de (s) (Boxplot)", default=min_lap, key="minlap_box2")
    max_lap2 = float_input("Excluir voltas com 'Lap Tm' acima de (s) (Boxplot)", default=max_lap, key="maxlap_box2")
    if max_lap2 < min_lap2:
        st.warning("No Boxplot, o máximo não pode ser menor que o mínimo. Ajustei o máximo para ficar igual ao mínimo.")
        max_lap2 = float(min_lap2)

    # —— Multiselect de Stints POR sessão selecionada
    sel_stints_per_session = {}
    with st.container():
        st.markdown("**Selecione Stint(s) (Boxplot) por sessão:**")
        for idx, s in enumerate(sel_sessions2):
            df_s = sheets[s]
            if "Stint" in df_s.columns:
                stints_s = sorted(pd.Series(df_s["Stint"]).dropna().unique())
            else:
                stints_s = []
            default_stints = stints_s
            sel = st.multiselect(
                f"{s} — Stint(s)",
                options=stints_s,
                default=default_stints,
                key=f"stints_box2_{idx}"
            )
            sel_stints_per_session[s] = sel if sel else stints_s

    # Slider de amostragem dimensionado pelo maior grupo após filtros
    max_avail2 = 0
    for s in sel_sessions2:
        df_s = sheets[s].copy()
        if "Lap Tm" in df_s.columns:
            df_s = df_s[pd.to_numeric(df_s["Lap Tm"], errors="coerce").notna()]
            df_s = df_s[df_s["Lap Tm"] >= float(min_lap2)]
            df_s = df_s[df_s["Lap Tm"] <= float(max_lap2)]
        stints_to_use = sel_stints_per_session.get(s, [])
        if not stints_to_use and "Stint" in df_s.columns:
            stints_to_use = sorted(pd.Series(df_s["Stint"]).dropna().unique())
        for stn in stints_to_use if stints_to_use else [None]:
            if stn is None or "Stint" not in df_s.columns:
                avail = len(df_s)
            else:
                avail = len(df_s[df_s["Stint"] == stn])
            max_avail2 = max(max_avail2, avail)

    sample2 = st.slider(
        "Amostragem (voltas mais rápidas) (Boxplot)",
        min_value=1, max_value=max(1, max_avail2),
        value=min(30, max_avail2) if max_avail2 else 1,
        key="sample_box2"
    )

    # Monta séries (cada (sessão, stint) vira um box)
    ys_list2, lbls2, box_sessions2 = [], [], []
    for s in sel_sessions2:
        df_s = sheets[s].copy()
        if "Lap Tm" in df_s.columns:
            df_s = df_s[pd.to_numeric(df_s["Lap Tm"], errors="coerce").notna()]
            df_s = df_s[df_s["Lap Tm"] >= float(min_lap2)]
            df_s = df_s[df_s["Lap Tm"] <= float(max_lap2)]
        if metric2 not in df_s.columns:
            st.warning(f"Métrica '{metric2}' não encontrada em {s}. Pulando.")
            continue

        stints_to_use = sel_stints_per_session.get(s, [])
        if not stints_to_use and "Stint" in df_s.columns:
            stints_to_use = sorted(pd.Series(df_s["Stint"]).dropna().unique())

        if "Stint" not in df_s.columns or not stints_to_use:
            df_sel = df_s.nsmallest(sample2, metric2)
            y = pd.to_numeric(df_sel[metric2], errors="coerce").dropna().tolist()
            if y:
                ys_list2.append(y)
                lbls2.append(f"{s}")
                box_sessions2.append(s)
        else:
            for stn in stints_to_use:
                df_g = df_s[df_s["Stint"] == stn]
                if df_g.empty:
                    continue
                df_sel = df_g.nsmallest(sample2, metric2)
                y = pd.to_numeric(df_sel[metric2], errors="coerce").dropna().tolist()
                if not y:
                    continue
                ys_list2.append(y)
                lbls2.append(f"{s} — Stint {int(stn)}")
                box_sessions2.append(s)

    st.divider()
    st.markdown("#### 📊 Boxplot (Independente por sessão/stint)")

    if not ys_list2:
        st.info("Sem dados para o boxplot com os filtros atuais.")
        return

    # Plot do boxplot independente com cores CONSISTENTES por SESSÃO
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    bp2 = ax2.boxplot(ys_list2, patch_artist=True)

    cycle = plt.rcParams.get("axes.prop_cycle", None)
    base_colors = cycle.by_key().get("color", ["C0"]) if cycle else ["C0"]

    present_sessions_order = []
    for s in sel_sessions2:
        if s in box_sessions2 and s not in present_sessions_order:
            present_sessions_order.append(s)
    session_to_color = {s: base_colors[i % len(base_colors)] for i, s in enumerate(present_sessions_order)}

    n_boxes2 = len(lbls2); h_in2 = fig2.get_size_inches()[1]
    fs2 = max(6, min(12, (10 * (h_in2 / 4.0)) * (8 / max(6, n_boxes2))))  # 6–12 pt

    all_vals2 = np.concatenate([np.array(v, dtype=float) for v in ys_list2])
    y_range2 = float(np.nanmax(all_vals2) - np.nanmin(all_vals2)) if all_vals2.size else 1.0
    dy2 = max(0.002 * y_range2, 0.0005)

    for i, box in enumerate(bp2["boxes"]):
        sess = box_sessions2[i]
        col = session_to_color.get(sess, base_colors[0])

        box.set_facecolor(col); box.set_edgecolor(col)
        bp2["whiskers"][2*i].set_color(col); bp2["whiskers"][2*i + 1].set_color(col)
        bp2["caps"][2*i].set_color(col); bp2["caps"][2*i + 1].set_color(col)

        annotate_box(ax2, bp2, ys_list2, i, col, fs2, dy2)

    handles2 = [mpatches.Patch(facecolor=session_to_color[s], edgecolor=session_to_color[s], label=s)
                for s in present_sessions_order]
    ax2.legend(handles=handles2, loc="upper right", fontsize="xx-small")
    ax2.set_xticks([])
    ax2.set_xlabel("Grupos (Sessão — Stint)")
    ax2.set_ylabel(labels_map2[metric2])
    fig2.tight_layout()
    st.pyplot(fig2, use_container_width=True)
    plt.close(fig2)

if __name__ == "__main__":
    main()
