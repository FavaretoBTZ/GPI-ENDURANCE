# 📊 Análise Estatística Endurance (Streamlit)

App Streamlit para analisar sessões de Endurance a partir de um Excel com múltiplas abas.  
Recursos principais:

- Ignora automaticamente **a última aba** do Excel.
- Detecção robusta de colunas de **Lap**, **Lap Tm** e cálculo automático de **Stint**.
- Gráficos comparativos (linha, dispersão e **boxplot**).
- **Boxplot** com anotações de **mediana**, **Q1** e **Q3**.
- **Seletor independente** por sessão/stint com **cores consistentes por sessão**.
- Tabela de **Métricas Avançadas por Stint** (P1) e download CSV.

## 🛠️ Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate      # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
