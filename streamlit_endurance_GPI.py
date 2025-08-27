import math
from typing import Optional
import re

import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D  # <- para legenda dos marcadores

st.set_page_config(page_title="📊 Análise Estatística Endurance", layout="wide")

# ---------- Utils ----------
def time_to_seconds(t):
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
    def smart_to_float(x):
        s = str(x).strip()
        if s == "" or s.lower() in {"nan", "none"}:
            return pd.NA
        s = re.sub(r'\.(?=\d{3}\b)', '', s)  # remove milhar "1.234"
        s = s.replace(',', '.')              # vírgula decimal -> ponto
        try:
            return float(s)
        except:
            return pd.NA
    return series.apply(smart_to_float)

def find_lap_column(df: pd.DataFrame) -> str:
    candidates = [c for c in df.columns if c.strip().lower() in {"lap", "leadlap", "lap #", "#lap"}]
    if candidates:
        if "Lap" not in df.columns:
            df.rename(columns={candidates[0]: "Lap"}, inplace=True)
        return "Lap"
    if "Lap" not in df.columns:
        df["Lap"] = range(1, len(df) + 1)
    return "Lap"

def find_lap_time_column(df: pd.DataFrame) -> Optional[str]:
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
    return pd.read_excel(file, sheet_name=None)

def preprocess_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "SSTRAP Tm" in out.columns and "SSTRAP" not in out.columns:
        out["SSTRAP"] = coerce_numeric(out["SSTRAP Tm"])
    find_lap_column(out)
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
    if "Stint" in df.columns:
        return df
    stn, stints = 1, []
    for t in df[lap_time_col].fillna(threshold + 1):
        stints.append(stn)
        if t > threshold:
            stn += 1
    out = df.copy()
    out["Stint"] = stints
    return out

def get_filtered(df: pd.DataFrame, stint_choice, min_lap_seconds, max_lap_seconds, is_time_metric: bool) -> pd.DataFrame:
    d = df.copy()
    if stint_choice != "All":
        d = d[d["Stint"] == stint_choice]
    if is_time_metric and "Lap Tm" in d.columns:
        d = d[pd.to_numeric(d["Lap Tm"], errors="coerce").notna()]
        d = d[d["Lap Tm"] >= float(min_lap_seconds)]
        d = d[d["Lap Tm"] <= float(max_lap_seconds)]
    return d

# ----- float_input: aceita vírgula/ponto -----
def parse_float_any(s: str) -> Optional[float]:
    if s is None:
        return None
    txt = str(s).strip().replace(" ", "")
    if txt == "":
        return None
    if "," in txt and "." in txt:
        last_comma, last_dot = txt.rfind(","), txt.rfind(".")
        if last_comma > last_dot:
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", "")
    else:
        if "," in txt:
            txt = txt.replace(",", ".")
    try:
        return float(txt)
    except:
        return None

def float_input(label: str, default: float, min_value: float = 0.0, max_value: float = 1e9, key: str = None) -> float:
    raw = st.text_input(label, value=str(default).replace(".", ","), key=key)
    val = parse_float_any(raw)
    if val is None:
        st.caption("↳ Valor vazio/ inválido: usando padrão.")
        val = default
    val = max(min_value, min(max_value, val))
    return float(val)

# --------- Anotação do boxplot (Q1/Mediana/Q3 + Máx/Mín) ---------
def annotate_box(ax, bp, ys_list, idx, color, fs, dy):
    data_i = np.array(ys_list[idx], dtype=float)
    q1 = float(np.percentile(data_i, 25))
    q3 = float(np.percentile(data_i, 75))
    med = float(np.median(data_i))
    y_min = float(np.min(data_i))
    y_max = float(np.max(data_i))

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

    ax.text(x_mid, y_max + 2*dy, f"{y_max:.3f}", fontsize=fs, va="bottom", ha="center",
            color="black", bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.5, linewidth=0),
            clip_on=True, zorder=5)
    ax.text(x_mid, y_min - 2*dy, f"{y_min:.3f}", fontsize=fs, va="top", ha="center",
            color="black", bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.5, linewidth=0),
            clip_on=True, zorder=5)

# ---------- App ----------
def main():
    st.title("📊 Análise Estatística Endurance")

    uploaded = st.file_uploader("Faça upload do arquivo Excel", type=["xlsx", "xls"])
    if not uploaded:
        st.info("Envie seu arquivo de estatísticas Endurance.")
        return

    sheets = load_excel(uploaded)

    remove_last_sheet = st.checkbox("Remover última aba da planilha", value=True)
    if remove_last_sheet and len(sheets) >= 1:
        last_key = list(sheets.keys())[-1]
        del sheets[last_key]

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

    # ---- Seleção de sessões ----
    default_p1 = [s for s in sheets if s.strip().endswith("P1")]
    sessions = st.multiselect(
        "Selecione sessões para análise",
        options=list(sheets.keys()),
        default=default_p1[:3] if default_p1 else list(sheets.keys())[:3]
    )
    if not sessions:
        st.warning("Selecione ao menos uma aba.")
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

    # ---- Filtros min/max (principal) ----
    min_lap = float_input("Excluir voltas com 'Lap Tm' abaixo de (s) (valor mínimo)", default=0.0, key="min_lap_main")
    max_lap = float_input("Excluir voltas com 'Lap Tm' acima de (s)", default=60.0, key="max_lap_main")
    if max_lap < min_lap:
        st.warning("O máximo não pode ser menor que o mínimo. Ajustei o máximo para ficar igual ao mínimo.")
        max_lap = float(min_lap)

    # ---- Sliders por sessão (robusto para avail 0/1) ----
    session_sample = {}
    filtered_exports = {}

    for s in sessions:
        df_f = get_filtered(sheets[s], session_stint[s], min_lap, max_lap, is_time_metric)
        avail = int(len(df_f))
        key = f"sample_{s}"

        if avail <= 0:
            session_sample[s] = 0
            st.text(f"Amostragem (voltas mais rápidas) em '{s}': 0 (sem dados após filtros)")
        elif avail == 1:
            session_sample[s] = 1
            st.text(f"Amostragem (voltas mais rápidas) em '{s}': 1 (apenas 1 volta após filtros)")
        else:
            min_v, max_v = 1, avail
            default_v = min(30, max_v)
            cur = st.session_state.get(key, default_v)
            try:
                cur = int(cur)
            except Exception:
                cur = default_v
            cur = max(min_v, min(max_v, cur))
            session_sample[s] = st.slider(
                f"Amostragem (voltas mais rápidas) em '{s}'",
                min_value=min_v, max_value=max_v, value=cur, step=1, key=key
            )

    # ---- Construção das séries (principal) ----
    series_x, series_y, labels = [], [], []
    for s in sessions:
        df_f = get_filtered(sheets[s], session_stint[s], min_lap, max_lap, is_time_metric)
        if metric not in df_f.columns:
            st.warning(f"'{metric}' não encontrado em {s}. Pulando.")
            continue

        n_take = int(session_sample[s])
        if n_take <= 0 or len(df_f) == 0:
            df_sel = df_f.head(0)
        else:
            n_take = min(n_take, len(df_f))
            df_sel = df_f.nsmallest(n_take, metric)

        filtered_exports[s] = df_sel.copy()

        lap_col = find_lap_column(df_sel) if not df_sel.empty else "Lap"
        if x_axis_mode == "Lap" and not df_sel.empty:
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
        fs = max(6, min(12, (10 * (h_in / 4.0)) * (8 / max(6, n_boxes))))
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

    # ---- Estatísticas (principal) ----
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

    # ---- Download por sessão ----
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

    # ---- Métricas por Stint ----
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
            cond = (
                (df_s_local["Stint"] == stn)
                & df_s_local["Lap Tm"].between(float(min_lap), float(max_lap), inclusive="both")
            )
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

            GPI = (I*4 + VI*2 + gauss*2 + II*2) / 10 if all(pd.notna(x) for x in [I, II, VI, gauss]) else pd.NA

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
        st.download_button("⬇️ Baixar métricas (CSV)",
                           dfm.to_csv(index=False).encode("utf-8"),
                           "metricas_avancadas_P1.csv", "text/csv")

    # ---- Boxplot independente ----
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
    metric2 = st.selectbox("Selecione métrica (Boxplot)", options=metric_opts2,
                           format_func=lambda x: labels_map2[x], key="metric_box2")

    # filtros min/máx do boxplot
    min_lap2 = float_input("Excluir voltas com 'Lap Tm' abaixo de (s) (valor mínimo)", default=min_lap, key="minlap_box2")
    max_lap2 = float_input("Excluir voltas com 'Lap Tm' acima de (s)", default=max_lap, key="maxlap_box2")
    if max_lap2 < min_lap2:
        st.warning("No Boxplot, o máximo não pode ser menor que o mínimo. Ajustei o máximo para ficar igual ao mínimo.")
        max_lap2 = float(min_lap2)

    sel_stints_per_session = {}
    with st.container():
        st.markdown("**Selecione Stint(s) (Boxplot) por sessão:**")
        for idx, s in enumerate(sel_sessions2):
            df_s = sheets[s]
            stints_s = sorted(pd.Series(df_s["Stint"]).dropna().unique()) if "Stint" in df_s.columns else []
            sel = st.multiselect(f"{s} — Stint(s)", options=stints_s, default=stints_s, key=f"stints_box2_{idx}")
            sel_stints_per_session[s] = sel if sel else stints_s

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
            avail = len(df_s if (stn is None or "Stint" not in df_s.columns) else df_s[df_s["Stint"] == stn])
            max_avail2 = max(max_avail2, int(avail))

    if max_avail2 <= 0:
        sample2 = 0
        st.text("Amostragem (voltas mais rápidas) (Boxplot): 0 (sem dados após filtros)")
    elif max_avail2 == 1:
        sample2 = 1
        st.text("Amostragem (voltas mais rápidas) (Boxplot): 1 (apenas 1 volta após filtros)")
    else:
        key_box = "sample_box2"
        min_v2, max_v2 = 1, max_avail2
        default_v2 = min(30, max_v2)
        cur2 = st.session_state.get(key_box, default_v2)
        try:
            cur2 = int(cur2)
        except Exception:
            cur2 = default_v2
        cur2 = max(min_v2, min(max_v2, cur2))
        sample2 = st.slider(
            "Amostragem (voltas mais rápidas) (Boxplot)",
            min_value=min_v2, max_value=max_v2, value=cur2, step=1, key=key_box
        )

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

        def take_smallest(df_g, n):
            if n <= 0 or len(df_g) == 0:
                return df_g.head(0)
            return df_g.nsmallest(min(int(n), len(df_g)), metric2)

        if "Stint" not in df_s.columns or not stints_to_use:
            df_sel = take_smallest(df_s, sample2)
            y = pd.to_numeric(df_sel[metric2], errors="coerce").dropna().tolist()
            if y:
                ys_list2.append(y); lbls2.append(f"{s}"); box_sessions2.append(s)
        else:
            for stn in stints_to_use:
                df_g = df_s[df_s["Stint"] == stn]
                if df_g.empty:
                    continue
                df_sel = take_smallest(df_g, sample2)
                y = pd.to_numeric(df_sel[metric2], errors="coerce").dropna().tolist()
                if not y:
                    continue
                ys_list2.append(y); lbls2.append(f"{s} — Stint {int(stn)}"); box_sessions2.append(s)

    st.divider()
    st.markdown("#### 📊 Boxplot (Independente por sessão/stint)")
    if not ys_list2:
        st.info("Sem dados para o boxplot com os filtros atuais.")
        return

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
    fs2 = max(6, min(12, (10 * (h_in2 / 4.0)) * (8 / max(6, n_boxes2))))
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

    # ===== Gráfico: Mínimo · Média · Máximo (mesma cor da sessão) + valores =====
    st.subheader("📈 Mínimo · Média · Máximo (mesma ordem do Boxplot) — cores por sessão")
    mins, means, maxs = [], [], []
    for y in ys_list2:
        s = pd.Series(pd.to_numeric(y, errors="coerce")).dropna()
        if s.empty:
            mins.append(np.nan); means.append(np.nan); maxs.append(np.nan)
        else:
            mins.append(float(s.min()))
            means.append(float(s.mean()))
            maxs.append(float(s.max()))

    x = np.arange(1, len(lbls2) + 1, dtype=float)
    fig3, ax3 = plt.subplots(figsize=(10, 4))

    vals_all = [v for v in (mins + means + maxs) if not np.isnan(v)]
    y_range = (max(vals_all) - min(vals_all)) if vals_all else 1.0
    dy = max(0.002 * y_range, 0.0005)

    for i, sess in enumerate(box_sessions2):
        col = session_to_color.get(sess, "C0")

        if not np.isnan(maxs[i]):
            ax3.scatter([x[i]], [maxs[i]], marker="^", s=55, color=col, zorder=3)
            ax3.text(x[i], maxs[i] + dy, f"{maxs[i]:.3f}", ha="center", va="bottom",
                     fontsize=8, color="black",
                     bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.6, linewidth=0),
                     clip_on=True, zorder=4)

        if not np.isnan(means[i]):
            ax3.scatter([x[i]], [means[i]], marker="o", s=55, color=col, zorder=3)
            ax3.text(x[i], means[i] + dy, f"{means[i]:.3f}", ha="center", va="bottom",
                     fontsize=8, color="black",
                     bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.6, linewidth=0),
                     clip_on=True, zorder=4)

        if not np.isnan(mins[i]):
            ax3.scatter([x[i]], [mins[i]], marker="v", s=55, color=col, zorder=3)
            ax3.text(x[i], mins[i] + dy, f"{mins[i]:.3f}", ha="center", va="bottom",
                     fontsize=8, color="black",
                     bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.6, linewidth=0),
                     clip_on=True, zorder=4)

    ax3.set_xlim(0.5, len(x) + 0.5)
    ax3.set_xticks([])
    ax3.set_xlabel("Grupos (mesma ordem do Boxplot)")
    ax3.set_ylabel(labels_map2[metric2])
    ax3.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.6)

    leg1 = ax3.legend(handles=handles2, loc="upper right", fontsize="x-small", title="Sessões")
    ax3.add_artist(leg1)
    shape_handles = [
        Line2D([0], [0], marker="^", linestyle="None", label="Máximo"),
        Line2D([0], [0], marker="o", linestyle="None", label="Média"),
        Line2D([0], [0], marker="v", linestyle="None", label="Mínimo"),
    ]
    ax3.legend(handles=shape_handles, loc="lower right", fontsize="x-small", title="Estatística")

    fig3.tight_layout()
    st.pyplot(fig3, use_container_width=True)
    plt.close(fig3)

if __name__ == "__main__":
    main()
