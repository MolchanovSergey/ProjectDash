import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import pandas as pd
from datetime import datetime

# Загрузка данных
df = pd.read_csv(
    "credits.csv", sep=";",
    parse_dates=["fund_date", "trade_close_dt", "loan_indicator_dt"]
)

# Предобработка данных
df["year"] = df["fund_date"].dt.year
closed_loans = df[df["loan_indicator"] == 1]

# Корпоративная цветовая схема
corporate_colors = {
    'background': '#F9F9F9',
    'text': '#1E1E1E',
    'colorscale': ['#1f77b4', '#2ca02c', '#d62728'],
    'card': '#FFFFFF'
}

# Создание приложения Dash
app = dash.Dash(__name__)
server = app.server # Gunicorn запускает Flask-сервер
app.layout = html.Div(style={'backgroundColor': corporate_colors['background']}, children=[
    html.H1("Анализ кредитного портфеля", style={'textAlign': 'center', 'color': corporate_colors['text']}),

    # Фильтры
    html.Div([
        html.Div([
            dcc.Dropdown(
                id='year-filter',
                options=[{'label': 'Все годы', 'value': 'all'}] +
                        [{'label': str(year), 'value': year} for year in sorted(df['year'].unique())],
                value='all',
                placeholder="Выберите год"
            )
        ], style={'width': '30%', 'padding': '10px'}),

        html.Div([
            dcc.Dropdown(
                id='currency-filter',
                options=[{'label': 'Все валюты', 'value': 'all'}] +
                        [{'label': curr, 'value': curr} for curr in df['account_amt_currency_code'].unique()],
                value='all',
                placeholder="Выберите валюту"
            )
        ], style={'width': '30%', 'padding': '10px'})
    ], style={'display': 'flex'}),

    # KPI метрики
    html.Div(id='kpi-cards', style={'display': 'flex', 'justifyContent': 'space-around', 'padding': '20px'}),

    # Графики
    html.Div([
        html.Div([
            dcc.Graph(id='amount-by-year'),
            dcc.Graph(id='count-by-year')
        ], style={'width': '49%', 'display': 'inline-block'}),

        html.Div([
            dcc.Graph(id='cost-scatter'),
            dcc.Graph(id='dynamic-line')
        ], style={'width': '49%', 'display': 'inline-block', 'float': 'right'})
    ]),

    # Скрытый элемент для хранения данных о выборе
    dcc.Store(id='crossfilter-selection')
])


# Колбэки для обновления данных
@callback(
    [Output('crossfilter-selection', 'data'),
     Output('kpi-cards', 'children')],
    [Input('year-filter', 'value'),
     Input('currency-filter', 'value'),
     Input('amount-by-year', 'clickData'),
     Input('count-by-year', 'clickData')]
)
def update_data(selected_year, selected_currency, click_amount, click_count):
    ctx = dash.callback_context
    filtered_df = df.copy()

    # Фильтрация данных
    if selected_year != 'all':
        filtered_df = filtered_df[filtered_df['year'] == selected_year]
    if selected_currency != 'all':
        filtered_df = filtered_df[filtered_df['account_amt_currency_code'] == selected_currency]

    # Обработка кликов на графиках
    if ctx.triggered:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id in ['amount-by-year', 'count-by-year']:
            click_data = click_amount if trigger_id == 'amount-by-year' else click_count
            if click_data:
                point = click_data['points'][0]
                filtered_df = filtered_df[
                    (filtered_df['year'] == point['x']) &
                    (filtered_df['account_amt_currency_code'] == point['customdata'][0])
                    ]

    # Расчет KPI
    total_loans = filtered_df.shape[0]
    total_closed = filtered_df[filtered_df['loan_indicator'] == 1].shape[0]
    total_amount = filtered_df['account_amt_credit_limit'].sum()
    total_closed_amount = filtered_df[filtered_df['loan_indicator'] == 1]['account_amt_credit_limit'].sum()

    kpi_cards = [
        create_kpi_card("Всего кредитов", total_loans, "#1f77b4"),
        create_kpi_card("Погашено кредитов", total_closed, "#2ca02c"),
        create_kpi_card("Общая сумма", f"{total_amount:,.0f}", "#d62728"),
        create_kpi_card("Погашенная сумма", f"{total_closed_amount:,.0f}", "#9467bd")
    ]

    return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards


# Функция создания карточек KPI
def create_kpi_card(title, value, color):
    return html.Div(
        style={
            'background': corporate_colors['card'],
            'borderRadius': '5px',
            'padding': '15px',
            'margin': '10px',
            'boxShadow': '0 4px 6px 0 rgba(0,0,0,0.1)',
            'width': '22%'
        },
        children=[
            html.H3(title, style={'margin': '0', 'color': corporate_colors['text']}),
            html.H2(
                value,
                style={'color': color, 'margin': '10px 0', 'fontSize': '24px'}
            )
        ]
    )


# Колбэк для обновления графиков
@callback(
    [Output('amount-by-year', 'figure'),
     Output('count-by-year', 'figure'),
     Output('cost-scatter', 'figure'),
     Output('dynamic-line', 'figure')],
    [Input('crossfilter-selection', 'data')]
)
def update_graphs(filtered_data):
    filtered_df = pd.read_json(filtered_data, orient='split')

    # Группировка данных
    loans_by_year = filtered_df.groupby(["year", "account_amt_currency_code"]).agg(
        total_amount=("account_amt_credit_limit", "sum"),
        loan_count=("account_amt_credit_limit", "count")
    ).reset_index()

    closed_stats = filtered_df[filtered_df['loan_indicator'] == 1].groupby("year").agg(
        closed_count=("account_amt_credit_limit", "count"),
        closed_amount=("account_amt_credit_limit", "sum"),
        avg_pct_cost=("overall_val_credit_total_amt", "mean"),
        total_monetary_cost=("overall_val_credit_total_monetary_amt", "sum")
    ).reset_index()

    # Создание графиков
    fig1 = px.bar(
        loans_by_year,
        x="year",
        y="total_amount",
        color="account_amt_currency_code",
        color_discrete_sequence=corporate_colors['colorscale'],
        title="Общая сумма кредитов",
        custom_data=["account_amt_currency_code"]
    )

    fig2 = px.bar(
        loans_by_year,
        x="year",
        y="loan_count",
        color="account_amt_currency_code",
        color_discrete_sequence=corporate_colors['colorscale'],
        title="Количество кредитов",
        custom_data=["account_amt_currency_code"]
    )

    fig3 = px.scatter(
        closed_stats,
        x="closed_amount",
        y="avg_pct_cost",
        size="total_monetary_cost",
        color="closed_count",
        color_continuous_scale=corporate_colors['colorscale'],
        title="Стоимость погашенных кредитов"
    )

    fig4 = px.line(
        closed_stats,
        x="year",
        y=["closed_amount", "total_monetary_cost"],
        color_discrete_sequence=corporate_colors['colorscale'],
        title="Динамика погашений"
    )

    # Обновление стилей
    for fig in [fig1, fig2, fig3, fig4]:
        fig.update_layout(
            plot_bgcolor=corporate_colors['card'],
            paper_bgcolor=corporate_colors['background'],
            font_color=corporate_colors['text']
        )

    return fig1, fig2, fig3, fig4


if __name__ == '__main__':
    app.run_server(debug=True)