import json
import calendar
import dash
from dash import dcc, html, Input, Output, callback, State, ALL
import plotly.express as px
import pandas as pd
from datetime import datetime, date
from dash import dash_table
import plotly.graph_objects as go
from gigachat import GigaChat
from dotenv import load_dotenv
import os
import io

load_dotenv()

client_file_path = 'data_for_llm/cl_10/random_client.csv'
default_prob_file_path = 'data_for_llm/cl_10/real_cb_test_result.csv'
mapping_file_path = "maping_csv.csv"
giga_token = os.getenv('TOKEN_GIGA')
# Чтение файлов
df = pd.read_csv(client_file_path,
                 parse_dates=["fund_date", "trade_close_dt", "loan_indicator_dt"], encoding="utf-8")
mapping_df = pd.read_csv(mapping_file_path, delimiter=';')

df['reporting_dt'] = pd.to_datetime(df['reporting_dt'])

default_prob_df = pd.read_csv(default_prob_file_path)
default_prob = default_prob_df['Predicted Probability'].values[0] * 100

df.fillna({
    'arrear_principal_outstanding': 0,
    'arrear_int_outstanding': 0,
    'arrear_other_amt_outstanding': 0,
    'month_aver_paymt_aver_paymt_amt': 0,
    'overall_val_credit_total_amt': 0  # Новое поле
}, inplace=True)

# Обновите bins и labels:
rate_bins = [-float('inf'), 0, 10, 20, 36, 50, 100, 200, 290, float('inf')]
rate_labels = [
    '0%',  # -inf <= x <= 0
    '10%',  # 0 < x < 10
    '10-20%',
    '20-36%',
    '36-50%',
    '50-100%',
    '100-200%',
    '200-290%',
    '>290%'
]
# 2. Явная обработка нулевых значений ДО категоризации
df['rate_category'] = '0%'  # Инициализируем все как 0%
df.loc[df['overall_val_credit_total_amt'] > 0, 'rate_category'] = pd.cut(
    df[df['overall_val_credit_total_amt'] > 0]['overall_val_credit_total_amt'],
    bins=rate_bins[1:],  # Исключаем первый бин
    labels=rate_labels[1:],
    right=False
)

# Дополнительная логика для arrear_principal_outstanding:
df.loc[df['arrear_principal_outstanding'] == 0, 'rate_category'] = '0%'

# Убедитесь, что account_uid - строковый тип
df['account_uid'] = df['account_uid'].astype(str)

# Извлечение маппинга из строки 10 (ключи - числа, значения - текстовые описания)
loan_kind_mapping_raw = mapping_df.iloc[10, 4]
loan_kind_mapping = {}

# Разбиваем строку по строкам и заполняем словарь
for line in str(loan_kind_mapping_raw).split("\n"):
    parts = line.split("\t")
    if len(parts) == 2:
        key, value = parts
        try:
            loan_kind_mapping[int(key)] = value
        except ValueError:
            continue  # Пропустить строки, которые не соответствуют формату

# Преобразование колонки 'trade_loan_kind_code' в числовой формат
df['trade_loan_kind_code'] = pd.to_numeric(df['trade_loan_kind_code'], errors='coerce')

# Замена кодов на текстовые значения
df['trade_loan_kind_code'] = df['trade_loan_kind_code'].map(loan_kind_mapping)

# === Обработка trade_acct_type1 ===

acct_type_mapping_raw = mapping_df.iloc[11, 4]  # Маппинг из строки 11
acct_type_mapping = {}

# Разбираем строки (код + описание), где код может содержать точки
for line in str(acct_type_mapping_raw).split("\n"):
    parts = line.split(" ", 1)  # Разделяем по первому пробелу (код - описание)
    if len(parts) == 2:
        key, value = parts
        try:
            acct_type_mapping[float(key)] = value  # Храним как float для кодов типа 2.1, 4.5
        except ValueError:
            continue

# Преобразование trade_acct_type1 в числовой формат
# client_df['trade_acct_type1'] = client_df['trade_acct_type1'].astype(str).str.strip()
df['trade_acct_type1'] = pd.to_numeric(df['trade_acct_type1'], errors='coerce')

# Маппинг (сопоставляем float)
df['trade_acct_type1'] = df['trade_acct_type1'].map(acct_type_mapping)

# # Предобработка данных
# df["year"] = df["fund_date"].dt.year
# closed_loans = df[df["loan_indicator"] == 1]

df["reporting_dt"] = pd.to_datetime(df["reporting_dt"])
active_loans = df[df["arrear_sign"] == 1]

# Корпоративная цветовая схема
corporate_colors = {
    'background': '#F5F3FF',
    'text': '#4B0082',
    'colorscale': ['#7E5BEF', '#A389F4', '#C9B9FC', '#E5DEFF'],
    'card': '#FFFFFF'
}

# Создание приложения Dash
app = dash.Dash(__name__)
server = app.server  # Gunicorn запускает Flask-сервер
app.layout = html.Div(style={'backgroundColor': corporate_colors['background'],
                             'fontFamily': 'Avenir, sans-serif',
                             'padding': '10px'}, children=[
    # Хранилище для состояния согласия
    dcc.Store(id='consent-given', data=False),

    # Модальное окно согласия
    html.Div(
        id='consent-modal',
        style={
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'zIndex': '1000',
            'display': 'flex',
            'justifyContent': 'center',
            'alignItems': 'center'
        },
        children=[
            html.Div(
                style={
                    'backgroundColor': corporate_colors['card'],
                    'padding': '30px',
                    'borderRadius': '15px',
                    'maxWidth': '600px',
                    'textAlign': 'center',
                    'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'
                },
                children=[
                    html.H2(
                        "Согласие на обработку данных",
                        style={'color': corporate_colors['text'], 'marginBottom': '20px'}
                    ),
                    dcc.Markdown(
                        """
                        **Нажимая кнопку "Далее" вы соглашаетесь:**
                        - С политикой конфиденциальности
                        - С условиями обработки персональных данных
                        - С использованием аналитических cookie

                        [Ознакомиться с полным текстом правил](https://example.com/privacy-policy)
                        """,
                        style={'marginBottom': '30px', 'fontSize': '18px'}
                    ),
                    html.Button(
                        'Далее →',
                        id='consent-button',
                        style={
                            'padding': '12px 24px',
                            'fontSize': '18px',
                            'backgroundColor': '#4B0082',
                            'color': 'white',
                            'borderRadius': '8px',
                            'border': 'none',
                            'cursor': 'pointer',
                            'fontFamily': 'Avenir'
                        }
                    )
                ]
            )
        ]
    ),

    # Обертка для всего основного контента
    html.Div(
        id='main-content',
        style={'display': 'none'},  # Изначально скрыто
        children=[
            # Компонент для перенаправления
            dcc.Location(id='redirect-url', refresh=True),

            html.H1("Ваш помощник по кредитам", style={'textAlign': 'center', 'color': corporate_colors['text']}),

            html.Div([
                html.H3("Выберите дату отчета из бюро кредитных историй",
                        style={'textAlign': 'center', 'color': corporate_colors['text']}),
                dcc.DatePickerSingle(
                    id='report-date-filter',
                    min_date_allowed=df['reporting_dt'].min(),
                    max_date_allowed=df['reporting_dt'].max(),
                    initial_visible_month=df['reporting_dt'].max(),
                    date=df['reporting_dt'].max()
                )
            ], style={'width': '35%', 'padding': '10px'}),

            # KPI метрики
            html.Div(id='kpi-cards', style={
                'display': 'grid',
                'grid-template-columns': 'repeat(auto-fit, minmax(180px, 1fr))',
                'gap': '10p x',
                'padding': '5px'
            }),

            # Новые круговые диаграммы
            html.Div([
                html.Div([
                    dcc.Graph(id='loan-kind-pie', config={'responsive': True}, style={'height': '40vh'}),
                ], style={'width': '100%', 'padding': '10px'}),

                html.Div([
                    dcc.Graph(id='loan-purpose-pie', config={'responsive': True}, style={'height': '40vh'}),
                ], style={'width': '100%', 'padding': '10px'}),

                html.Div([
                    dcc.Graph(id='rate-pie-chart', config={'responsive': True}, style={'height': '40vh'}),
                ], style={'width': '100%', 'padding': '10px'}),

            ]),
            # Добавить после блока с круговыми диаграммами
            html.Div([
                html.H3("Кредитные карты", style={'margin': '20px 0', 'color': corporate_colors['text']}),
                html.Div(id='credit-cards-buttons'),
                html.Div(id='credit-card-details'),
                dcc.Markdown(id='llm-output1', style={
                    'background': corporate_colors['card'],
                    'padding': '15px',
                    'borderRadius': '5px',
                    'marginTop': '10px',
                    'border': '1px solid #EEE'
                }),
            ], style={'padding': '20px'}),

            # Скрытый элемент для хранения данных о выборе
            dcc.Store(id='crossfilter-selection', data=df.to_json(date_format='iso', orient='split')),

            # В блоке layout добавьте новый компонент перед графиком платежей:
            html.Div([
                html.H3("Календарь платежей",
                        style={'margin': '20px 0', 'color': corporate_colors['text'], 'fontSize': '24px'}),
                html.Div([
                    html.Button('◄', id='prev-month', n_clicks=0,
                                style={'marginRight': '10px',
                                       'border': 'none',
                                       'background': 'none',
                                       'cursor': 'pointer',
                                       'fontSize': '36px',
                                       'fontFamily': 'VAvenir'}),
                    html.Span(id='current-month-year',
                              style={'fontWeight': 'bold',
                                     'marginRight': '10px',
                                     'fontSize': '32px',
                                     'fontFamily': 'Avenir'}),
                    html.Button('►', id='next-month', n_clicks=0,
                                style={'border': 'none',
                                       'background': 'none',
                                       'cursor': 'pointer',
                                       'fontSize': '36px',
                                       'fontFamily': 'Avenir'}),
                ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '15px'}),
                html.Div(id='payment-calendar',
                         style={'backgroundColor': corporate_colors['card'],
                                'padding': '15px',
                                'borderRadius': '8px',
                                'height': '800px'
                                })
            ], style={'padding': '20px'}),

            # В макет добавьте:
            html.Div([
                dcc.Graph(id='payment-schedule', style={'width': '100%', 'padding': '10px'})
            ], style={'padding': '20px'}),

            # Таблица с задолженностью
            html.Div([
                html.H3("Список непогашенных кредитов", style={'margin': '20px 0'}),
                dash_table.DataTable(
                    style_data={
                        'backgroundColor': corporate_colors['card'],
                        'color': corporate_colors['text']
                    },
                    style_cell={
                        'minWidth': '80px',
                        'maxWidth': '120px',
                        'fontSize': '12px',
                        'padding': '5px'
                    },
                    style_header={
                        'fontSize': '14px'
                    },
                    id='arrear-table',
                    columns=[
                        {'name': 'ID кредита', 'id': 'account_uid'},
                        {'name': 'Сумма задолженности', 'id': 'arrear_amt_outstanding'},
                        {'name': 'Дата расчета', 'id': 'arrear_calc_date'},
                        {'name': 'Дата срочной задолженности', 'id': 'due_arrear_start_dt'},
                        {'name': 'Сумма просрочки', 'id': 'past_due_amt_past_due'},
                        {'name': 'Процентная ставка', 'id': 'overall_val_credit_total_amt'}
                    ],
                    style_table={'overflowX': 'auto'},
                    page_size=10

                )
            ], style={'padding': '20px'}),

            html.Div([
                html.H3("Выберите кредит для погашения", style={'margin': '20px 0', 'color': corporate_colors['text']}),
                dcc.Dropdown(
                    id='loan-selector',
                    options=[
                        {
                            'label': f"Кредит ID: {row['account_uid']} (Задолженность: {row['arrear_principal_outstanding']} руб.)",
                            'value': str(row['account_uid'])
                        }
                        for _, row in df.iterrows()
                    ],
                    placeholder="Выберите кредит...",
                    style={'fontSize': '14px', 'marginBottom': '10px'}
                ),
                html.Div(id='selected-loan-details', style={'display': 'none'}, children=[
                    dash_table.DataTable(
                        id='loan-details-table',
                        data=[],
                        columns=[
                            {'name': 'ID кредита', 'id': 'account_uid'},
                            {'name': 'Сумма задолженности', 'id': 'arrear_amt_outstanding'},
                            {'name': 'Дата расчета', 'id': 'arrear_calc_date'},
                            {'name': 'Дата срочной задолженности', 'id': 'due_arrear_start_dt'},
                            {'name': 'Сумма просрочки', 'id': 'past_due_amt_past_due'},
                            {'name': 'Процентная ставка', 'id': 'overall_val_credit_total_amt'}
                        ],
                        style_table={'overflowX': 'auto'},
                        style_cell={
                            'minWidth': '80px',
                            'maxWidth': '120px',
                            'fontSize': '12px',
                            'padding': '5px'
                        },
                        style_header={
                            'fontSize': '14px'
                        },
                        style_data={
                            'backgroundColor': corporate_colors['card'],
                            'color': corporate_colors['text']
                        }
                    ),

                    html.H3("Что бы погасить выбранный кредит нажмите на кнопку", style={'margin': '20px 0'}),
                    html.Button('ПОГАСИТЬ',
                                id='repay-button',
                                n_clicks=0,
                                style={
                                    'fontSize': '18px',
                                    'padding': '6px 12px',
                                    'borderRadius': '5px',
                                    'backgroundColor': '#4B0082',
                                    'color': 'white',
                                    'fontFamily': 'Avenir',
                                    'cursor': 'pointer',
                                    'marginTop': '20px'
                                }),
                    dcc.ConfirmDialog(
                        id='repay-confirm',
                        message='Вы будете переведены в соответствующий раздел мобильного банка для внесения реквизитов. Продолжить оплату?',
                    )
                ])
            ], style={'padding': '20px'}),
            # Блок с доходом
            html.Div([
                dcc.Input(
                    id='income-input',
                    type='number',
                    placeholder='Введите среднем.есячный доход',
                    style={'marginRight': '10px',
                           'marginLeft': '10px',
                           'width': '15%',
                           'height': '30px',
                           'fontSize': '18px',
                           'fontFamily': 'Avenir',
                           'marginBottom': '10px'
                           }
                ),
                html.Button('ДОБАВИТЬ',
                            id='upgrade-button',
                            n_clicks=0,
                            style={
                                'fontSize': '18px',
                                'padding': '6px 12px',
                                'borderRadius': '5px',
                                'backgroundColor': '#4B0082',
                                'color': 'white',
                                'fontFamily': 'Avenir',
                                'cursor': 'pointer'
                            }
                            )
            ], style={'padding': '20px'}),

            # График с доходом
            dcc.Graph(id='income-plot',
                      config={'responsive': True},
                      style={'height': '40vh'}
                      ),

            # Блок с рекомендациями от GigaChat
            html.Div([
                html.H3("Ваши персональные рекомендации по кредитам", style={'margin': '20px 0'}),

                # Выпадающий список с часто задаваемыми вопросами
                dcc.Dropdown(
                    id='frequent-questions',
                    options=[
                        {'label': 'Как снизить ежемесячные платежи?', 'value': 'Как снизить ежемесячные платежи?'},
                        {'label': 'Какой кредит выгоднее погасить первым?', 'value': 'Какой кредит выгоднее погасить первым?'},
                        {'label': 'Как рефинансировать кредиты?', 'value': 'Как рефинансировать кредиты?'},
                        {'label': 'Как избежать просрочек?', 'value': 'Как избежать просрочек?'},
                        {'label': 'Как оптимизировать кредитную нагрузку?', 'value': 'Как оптимизировать кредитную нагрузку?'},
                    ],
                    placeholder="Выберите часто задаваемый вопрос...",
                    style={
                        'marginBottom': '10px',
                        'fontFamily': 'Avenir',
                        'fontSize': '16px'
                    }
                ),

                dcc.Input(
                    id='user-question',
                    type='text',
                    placeholder='Введите ваш вопрос...',
                    style={
                        'width': '100%',
                        'height': '50px',
                        'fontSize': '18px',
                        'fontFamily': 'Avenir',
                        'marginBottom': '10px'
                    }
                ),
                html.Button('ОТПРАВИТЬ',
                            id='submit-question',
                            n_clicks=0,
                            style={
                                'fontSize': '18px',
                                'padding': '6px 12px',
                                'borderRadius': '5px',
                                'backgroundColor': '#4B0082',
                                'color': 'white',
                                'fontFamily': 'Avenir',
                                'cursor': 'pointer'
                            }
                            ),
                dcc.Markdown(id='llm-output', style={
                    'background': corporate_colors['card'],
                    'padding': '15px',
                    'borderRadius': '5px',
                    'marginTop': '10px',
                    'border': '1px solid #EEE'
                })
            ], style={'padding': '20px'}),

            # После блока с рекомендациями от GigaChat добавьте:
            dcc.Store(id='show-disclaimer', data=False),  # Хранилище для состояния показа предупреждения

            # Модальное окно с предупреждением
            html.Div(
                id='disclaimer-modal',
                style={
                    'position': 'fixed',
                    'top': '0',
                    'left': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.5)',
                    'zIndex': '1001',  # Выше, чем у окна согласия
                    'display': 'none',  # По умолчанию скрыто
                    'justifyContent': 'center',
                    'alignItems': 'center'
                },
                children=[
                    html.Div(
                        style={
                            'backgroundColor': corporate_colors['card'],
                            'padding': '30px',
                            'borderRadius': '15px',
                            'maxWidth': '600px',
                            'width': '90%',
                            'textAlign': 'center',
                            'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'
                        },
                        children=[
                            html.H2(
                                "Важная информация",
                                style={'color': corporate_colors['text'], 'marginBottom': '20px'}
                            ),
                            dcc.Markdown(
                                """
                                **Обратите внимание:**
                                - Предоставляемые рекомендации не являются инвестиционной стратегией
                                - Компания не несет ответственности за решения, принятые на основе этих рекомендаций
                                - Все финансовые решения вы принимаете на свой собственный риск
                                """,
                                style={'marginBottom': '30px', 'fontSize': '18px', 'textAlign': 'left'}
                            ),
                            html.Button(
                                'Я понимаю',
                                id='disclaimer-ok-button',
                                style={
                                    'padding': '12px 24px',
                                    'fontSize': '18px',
                                    'backgroundColor': '#4B0082',
                                    'color': 'white',
                                    'borderRadius': '8px',
                                    'border': 'none',
                                    'cursor': 'pointer',
                                    'fontFamily': 'Avenir',
                                    'margin': '0 auto',
                                    'display': 'block'}
                            )
                        ]
                    )
                ]
            )

        ]
    )
])


# Изменения в колбэке unified_callback
@callback(
    [Output('crossfilter-selection', 'data'),
     Output('kpi-cards', 'children'),
     Output('llm-output', 'children'),
     Output('show-disclaimer', 'data', allow_duplicate=True)],
    [Input('report-date-filter', 'date'),
     Input('submit-question', 'n_clicks')],
    [State('user-question', 'value'),
     State('crossfilter-selection', 'data'),
     State('income-input', 'value')],
    prevent_initial_call=True
)
def unified_callback(selected_date, n_clicks, question, filtered_data, user_income):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Базовый фильтр
    filtered_df = df[df["arrear_sign"] == 1].copy()

    if triggered_id in ['report-date-filter', None]:
        # Фильтрация по дате
        if selected_date:
            selected_date_dt = pd.to_datetime(selected_date)
            filtered_df = filtered_df[filtered_df['reporting_dt'].dt.date == selected_date_dt.date()]

        # Расчет KPI
        total_principal = filtered_df['arrear_principal_outstanding'].sum()
        total_interest = filtered_df['arrear_int_outstanding'].sum()
        avg_monthly = filtered_df['month_aver_paymt_aver_paymt_amt'].sum()

        # Новые метрики
        avg_rate = filtered_df['overall_val_credit_total_amt'].mean()
        min_rate = filtered_df['overall_val_credit_total_amt'].min()
        max_rate = filtered_df['overall_val_credit_total_amt'].max()
        total_past_due_principal = filtered_df['past_due_amt_past_due'].sum()
        total_past_due_interest = filtered_df['past_due_int_amt_past_due'].sum()

        kpi_cards = [
            create_kpi_card("Основной долг", total_principal, "#1f77b4"),
            create_kpi_card("Проценты", total_interest, "#2ca02c"),
            create_kpi_card("Ср.месячн. платеж", avg_monthly, "#9467bd"),

            # Новые KPI
            create_kpi_card("Ср. ставка", f"{avg_rate:.1f}%", "#FFA500"),
            create_kpi_card("Мин. ставка", f"{min_rate:.1f}%", "#32CD32"),
            create_kpi_card("Макс. ставка", f"{max_rate:.1f}%", "#FF4500"),
            create_kpi_card("Просрочка (осн.)", total_past_due_principal, "#8B0000"),
            create_kpi_card("Просрочка (%)", total_past_due_interest, "#4B0082")
        ]

        # УБИРАЕМ автоматический запрос к LLM здесь

        return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards, "Задайте вопрос в поле выше"

    # Обработка пользовательского вопроса
    elif triggered_id == 'submit-question' and question:
        try:
            # Фильтрация данных
            filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')

            # Формируем KPI data
            kpi_data = {
                'total_principal': filtered_df['arrear_principal_outstanding'].sum(),
                # Сумма основного долга по задолженности
                'total_interest': filtered_df['arrear_int_outstanding'].sum(),  # Сумма процентов по задолженности
                'avg_monthly': filtered_df['month_aver_paymt_aver_paymt_amt'].sum(),  # Среднемесячный платеж
                'avg_rate': filtered_df['overall_val_credit_total_amt'].mean(),
                # Полная стоимость кредита (займа) в процентах годовых
                'min_rate': filtered_df['overall_val_credit_total_amt'].min(),
                'max_rate': filtered_df['overall_val_credit_total_amt'].max(),
                'total_past_due_principal': filtered_df['past_due_amt_past_due'].sum(),
                # Сумма просроченной задолженности
                'total_past_due_interest': filtered_df['past_due_int_amt_past_due'].sum(),
                # Сумма процентов по просроченной задолженности
                'credit_cards_info': "...",  # Ваша логика формирования
                'num_active_loans': len(filtered_df),
                'num_overdue_loans': len(filtered_df[filtered_df['past_due_amt_past_due'] > 0]),
                'overdue_categories': {
                    'less_6_days': filtered_df['delay5'].sum(),
                    '6_30_days': filtered_df['delay30'].sum(),
                    '31_60_days': filtered_df['delay60'].sum(),
                    '61_90_days': filtered_df['delay90'].sum(),
                    '90_plus_days': filtered_df['delay_more'].sum(),
                },
                'max_overdue': filtered_df['cred_max_overdue'].max(),
                # 'loan_types': filtered_df.groupby('trade_loan_kind_code')['arrear_principal_outstanding'].agg(['count', 'sum']).to_dict(),
                # 'loan_purposes': filtered_df.groupby('trade_acct_type1')['arrear_principal_outstanding'].agg(['count', 'sum']).to_dict(),
                'monthly_payment_load': (
                        filtered_df['paymnt_condition_principal_terms_amt'].sum() +
                        filtered_df['paymnt_condition_interest_terms_amt'].sum()
                )
                # 'last_overdue_date': (
                #     pd.to_datetime(filtered_df['past_due_calc_date'].max().strftime('%Y-%m-%d'))
                #     if not filtered_df['past_due_calc_date'].isna().all()
                #     else 'Нет данных'
                # ),
                # 'new_loans_last_year': len(
                #     filtered_df[
                #         filtered_df['fund_date'] >= filtered_df['reporting_dt'] - pd.Timedelta(days=365)
                #     ]
                # )

            }

            # В блоке формирования kpi_data добавьте:
            kpi_data['active_loans'] = [
                {
                    'id': str(row.get('account_uid', 'N/A')),
                    'debt': float(row.get('arrear_amt_outstanding', 0)),
                    'calc_date': row.get('arrear_calc_date', 'Не указана'),
                    'due_date': row.get('due_arrear_start_dt', 'Не указана'),
                    'past_due': float(row.get('past_due_amt_past_due', 0)),
                    'rate': float(row.get('overall_val_credit_total_amt', 0))
                }
                for _, row in filtered_df.iterrows()
            ]

            kpi_data['loan_types'] = (
                filtered_df.groupby('trade_loan_kind_code')
                .agg(
                    count=('arrear_principal_outstanding', 'count'),
                    sum=('arrear_principal_outstanding', 'sum'),
                    max_rate=('overall_val_credit_total_amt', 'max')
                )
                .reset_index()
                .rename(columns={'trade_loan_kind_code': 'loan_type'})
                .to_dict(orient='records')
            ) if all(
                col in filtered_df.columns for col in ['trade_loan_kind_code', 'overall_val_credit_total_amt']) else []

            # Вызываем send_prompt_to_llm с вопросом
            response = send_prompt_to_llm(
                kpi_data=kpi_data,
                giga_token=giga_token,
                user_question=question,
                user_income=user_income
            )

            return dash.no_update, dash.no_update, response.choices[0].message.content, True

        except Exception as e:
            return dash.no_update, dash.no_update, f"Ошибка: {str(e)}", False

    return dash.no_update, dash.no_update, "Ожидаю ваш вопрос...", False


# @callback(
#     [Output('crossfilter-selection', 'data'),
#      Output('kpi-cards', 'children'),
#      Output('llm-output', 'children')],
#     [Input('report-date-filter', 'date'),
#      Input('submit-question', 'n_clicks')],
#     [State('user-question', 'value'),
#      State('crossfilter-selection', 'data'),
#      State('income-input', 'value')]
# )
# def unified_callback(selected_date, n_clicks, question, filtered_data, user_income):
#     ctx = dash.callback_context
#     triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
#
#     # Чтение и фильтрация данных
#     filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split') if filtered_data else df.copy()
#     filtered_df = filtered_df[filtered_df["Признак задолженности"] == 1].copy()
#
#     if selected_date:
#         selected_date_dt = pd.to_datetime(selected_date)
#         filtered_df = filtered_df[filtered_df['Дата отчета'].dt.date == selected_date_dt.date()]
#
#     # Агрегации
#     kpi_data = {
#         'total_principal': filtered_df['Сумма основного долга по задолженности'].sum(),
#         'total_interest': filtered_df['Сумма процентов по задолженности'].sum(),
#         'avg_monthly': filtered_df['Среднемесячный платеж'].sum(),
#         'avg_rate': filtered_df['Полная стоимость кредита (займа) в процентах годовых'].mean(),
#         'min_rate': filtered_df['Полная стоимость кредита (займа) в процентах годовых'].min(),
#         'max_rate': filtered_df['Полная стоимость кредита (займа) в процентах годовых'].max(),
#         'total_past_due_principal': filtered_df['Сумма просроченной задолженности'].sum(),
#         'total_past_due_interest': filtered_df['Сумма процентов по просроченной задолженности'].sum(),
#         'num_active_loans': len(filtered_df),
#         'num_overdue_loans': len(filtered_df[filtered_df['Сумма просроченной задолженности'] > 0]),
#         'overdue_categories': {
#             'less_6_days': filtered_df['Кол–во закрытых просрочек – менее 6 дней'].sum(),
#             '6_30_days': filtered_df['Кол–во закрытых просрочек – от 6 до 30 дней'].sum(),
#             '31_60_days': filtered_df['Кол–во закрытых просрочек – от 31 до 60 дней'].sum(),
#             '61_90_days': filtered_df['Кол–во закрытых просрочек – от 61 до 90 дней'].sum(),
#             '90_plus_days': filtered_df['Кол–во закрытых просрочек – более 90 дней'].sum(),
#         },
#         'max_overdue': filtered_df['Максимальная просрочка'].max(),
#         'loan_types': filtered_df.groupby('Вид займа')['Сумма основного долга по задолженности'].agg(['count', 'sum']).to_dict(),
#         'loan_purposes': filtered_df.groupby('Тип счета')['Сумма основного долга по задолженности'].agg(['count', 'sum']).to_dict(),
#         'monthly_payment_load': (
#             filtered_df['Сумма платежа по основному долгу'].sum() +
#             filtered_df['Сумма платежа по процентам'].sum()
#         ),
#         'last_overdue_date': (
#             filtered_df['Дата расчета просроченной задолженности'].max().strftime('%Y-%m-%d')
#             if not filtered_df['Дата расчета просроченной задолженности'].isna().all()
#             else 'Нет данных'
#         ),
#         'new_loans_last_year': len(
#             filtered_df[
#                 filtered_df['Дата финансирования'] >= pd.to_datetime(selected_date) - pd.Timedelta(days=365)
#             ]
#         )
#     }
#
#     # KPI для карточек
#     kpi_cards = [
#         create_kpi_card("Основной долг", kpi_data['total_principal'], "#1f77b4"),
#         create_kpi_card("Проценты", kpi_data['total_interest'], "#2ca02c"),
#         create_kpi_card("Ср.месячн. платеж", kpi_data['avg_monthly'], "#9467bd"),
#         create_kpi_card("Ср. ставка", f"{kpi_data['avg_rate']:.1f}%", "#FFA500"),
#         create_kpi_card("Мин. ставка", f"{kpi_data['min_rate']:.1f}%", "#32CD32"),
#         create_kpi_card("Макс. ставка", f"{kpi_data['max_rate']:.1f}%", "#FF4500"),
#         create_kpi_card("Просрочка (осн.)", kpi_data['total_past_due_principal'], "#8B0000"),
#         create_kpi_card("Просрочка (%)", kpi_data['total_past_due_interest'], "#4B0082"),
#         create_kpi_card("Активные кредиты", kpi_data['num_active_loans'], "#4B0082"),
#         create_kpi_card("Кредиты с просрочкой", kpi_data['num_overdue_loans'], "#FF0000")
#     ]
#
#     # Обработка пользовательского вопроса
#     if triggered_id == 'submit-question' and question:
#         try:
#             response = send_prompt_to_llm(
#                 kpi_data=kpi_data,
#                 giga_token=giga_token,
#                 user_question=question,
#                 user_income=user_income,
#                 default_prob=default_prob
#             )
#             return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards, response.choices[0].message.content
#         except Exception as e:
#             return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards, f"Ошибка: {str(e)}"
#
#     return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards, "Задайте вопрос в поле выше"

@callback(
    [Output('loan-kind-pie', 'figure'),
     Output('loan-purpose-pie', 'figure'),
     Output('rate-pie-chart', 'figure'),  # Добавлен новый выход
     Output('arrear-table', 'data'),
     Output('income-plot', 'figure')],
    [Input('crossfilter-selection', 'data'),
     Input('upgrade-button', 'n_clicks')],
    [State('income-input', 'value')]
)
def update_additional_elements(filtered_data, n_clicks, income):
    try:
        if not filtered_data:
            # Возвращаем заглушки для всех выходов
            empty_fig = px.scatter(title="Нет данных").update_layout(
                plot_bgcolor=corporate_colors['card'],
                paper_bgcolor=corporate_colors['background'],
                font_color=corporate_colors['text']
            )
            return empty_fig, empty_fig, empty_fig, [], empty_fig
        # Чтение данных
        filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')
        # print(f"[DEBUG] Данные получены. Колонки: {filtered_df.columns.tolist()}")

        # Преобразование даты (если нужно)
        if 'fund_date' in filtered_df.columns:
            filtered_df['fund_date'] = pd.to_datetime(filtered_df['fund_date'], errors='coerce')

    except Exception as e:
        # print(f"[ERROR] Ошибка в update_additional_elements: {str(e)}")
        empty_fig = px.scatter(title="Ошибка данных").update_layout(
            plot_bgcolor=corporate_colors['card'],
            paper_bgcolor=corporate_colors['background'],
            font_color=corporate_colors['text']
        )
        return empty_fig, empty_fig, empty_fig, [], empty_fig

    # Заглушки для пустых данных
    empty_fig = px.scatter(title="Нет данных").update_layout(
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        font_color=corporate_colors['text']
    )
    if filtered_df.empty:
        return empty_fig, empty_fig, empty_fig, [], empty_fig

    # Круговые диаграммы
    loan_kind_fig = px.pie(
        filtered_df,
        names='trade_loan_kind_code',
        values='account_amt_credit_limit',
        title='Распределение по видам займов',
        hole=0.7  # Добавьте этот параметр для создания кольца
    ).update_traces(
        textinfo='value',
        texttemplate='%{value:,.0f} ₽',
        textposition='outside'
    ).update_layout(
        # font_family='Avenir',
        # font_color=corporate_colors['text'],
        # plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        # title_font_size=18,
        # title_font_color='#5D3FBA'
        font_family='Avenir',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=9),  # Уменьшаем размер шрифта
            # itemgap = 0.5,  # Расстояние между элементами
            title=None
        ),
        margin=dict(t=120, b=80, l=50, r=50),  # Настраиваем отступы
        title_font_size=18,
        title_x=0.5,
        title_y=0.95,  # Центрируем заголовок
        height=370,
        autosize=False
    )

    loan_purpose_fig = px.pie(
        filtered_df,
        names='trade_acct_type1',
        values='account_amt_credit_limit',
        title='Распределение по целям кредитов',
        hole=0.7  # Добавьте этот параметр
    ).update_traces(
        textinfo='value',
        texttemplate='%{value:,.0f} ₽',
        textposition='outside'
    ).update_layout(
        font_family='Avenir',
        # font_color=corporate_colors['text'],
        # plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=9),  # Уменьшаем размер шрифта
            # itemgap = 0.5,  # Расстояние между элементами
            title=None
        ),
        margin=dict(t=100, b=10, l=50, r=50),  # Настраиваем отступы
        title_font_size=18,
        title_x=0.5,
        title_y=0.95,  # Центрируем заголовок
        height=290,
        autosize=False
    )
    # Новая круговая диаграмма
    rate_pie_fig = px.pie(
        filtered_df,
        names='rate_category',
        values='arrear_principal_outstanding',
        title='Распределение задолженности по ставкам',
        hole=0.7
    ).update_traces(
        textinfo='value',
        texttemplate='%{value:,.0f} ₽',
        textposition='outside'
    ).update_layout(
        font_family='Avenir',
        # font_color=corporate_colors['text'],
        # plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=9),  # Уменьшаем размер шрифта
            # itemgap = 0.5,  # Расстояние между элементами
            title=None
        ),
        margin=dict(t=70, b=80, l=50, r=50),
        title_font_size=18,
        title_x=0.5,
        title_y=0.95,  # Центрируем заголовок
        height=330,
        autosize=False
    )

    # Таблица с задолженностью
    arrear_df = filtered_df[filtered_df['arrear_sign'] == 1]
    table_data = arrear_df[[
        'account_uid', 'arrear_amt_outstanding',
        'arrear_calc_date', 'due_arrear_start_dt', 'past_due_amt_past_due', 'overall_val_credit_total_amt'
    ]].to_dict('records')

    # График с доходом
    income_fig = go.Figure()

    if n_clicks > 0 and income is not None and not filtered_df.empty:
        # Преобразуем колонку с датами
        filtered_df['paymnt_condition_principal_terms_amt_dt'] = pd.to_datetime(
            filtered_df['paymnt_condition_principal_terms_amt_dt'],
            errors='coerce'
        )

        # Удаляем строки с некорректными датами
        filtered_df = filtered_df.dropna(subset=['paymnt_condition_principal_terms_amt_dt'])
        # Собираем платежи по месяцам
        payments = filtered_df.groupby(
            pd.Grouper(key='paymnt_condition_principal_terms_amt_dt', freq='M')
        ).agg(
            total_payment=('paymnt_condition_principal_terms_amt', 'sum'),
            total_interest=('paymnt_condition_interest_terms_amt', 'sum')
        ).reset_index()

        # Суммируем основной долг и проценты
        payments['total'] = payments['total_payment'] + payments['total_interest']

        if not payments.empty:
            income_fig.add_trace(go.Bar(
                x=payments['paymnt_condition_principal_terms_amt_dt'],
                y=payments['total'],
                name='Суммарный платеж',
                marker_color='#7E5BEF'
            ))

            income_fig.add_hline(
                y=income,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Доход: {income:.2f} ₽"
            )

            income_fig.update_layout(
                title="Сравнение дохода с платежами",
                xaxis_title="Месяц",
                yaxis_title="Сумма, ₽",
                plot_bgcolor=corporate_colors['card'],
                paper_bgcolor=corporate_colors['background'],
                font_color=corporate_colors['text'],
                barmode='group'
            )
        else:
            income_fig = empty_fig.update_layout(title="Нет данных о платежах")
    else:
        income_fig = empty_fig.update_layout(title="Введите доход для анализа")

    return loan_kind_fig, loan_purpose_fig, rate_pie_fig, table_data, income_fig


# В колбэки добавьте:
@callback(
    Output('payment-schedule', 'figure'),
    Input('crossfilter-selection', 'data')
)
def update_payment_chart(filtered_data):
    filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')

    fig = go.Figure()

    # Добавляем платежи по основному долгу
    fig.add_trace(go.Scatter(
        x=filtered_df['paymnt_condition_principal_terms_amt_dt'],
        y=filtered_df['paymnt_condition_principal_terms_amt'],
        mode='markers',
        name='Основной долг',
        marker_color='#7E5BEF'
    ))
    # Добавляем платежи по процентам
    fig.add_trace(go.Scatter(
        x=filtered_df['paymnt_condition_interest_terms_amt_dt'],
        y=filtered_df['paymnt_condition_interest_terms_amt'],
        mode='markers',
        name='Проценты',
        marker_color='#A389F4'
    ))

    fig.update_layout(
        title="График платежей",
        xaxis_title="Дата платежа",
        yaxis_title="Сумма",
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background']
    )

    return fig


# Функция создания карточек KPI
def create_kpi_card(title, value, color):
    try:
        # Обработка процентных значений
        if isinstance(value, str) and '%' in value:
            formatted_value = value
        else:
            num_value = float(value) if isinstance(value, str) else value
            formatted_value = f"{num_value:,.0f} ₽".replace(',', ' ') if num_value != 0 else "0 ₽"
            # Конвертируем в float, если передана строка
        # num_value = float(value) if isinstance(value, str) else value
        # formatted_value = f"{value:,.2f}".replace(',', ' ').replace('.', ',') + ' ₽'
    except (ValueError, TypeError):
        formatted_value = "0,00 ₽"
    return html.Div(
        style={
            'background': corporate_colors['card'],
            'border': f'2px solid {color}',
            'borderRadius': '15px',
            'padding': '10px',
            'margin': '5px',
            'boxShadow': '0 2px 4px rgba(93, 63, 186, 0.1)',
            'width': '48%',  # Для двух колонок на мобильных
            'minWidth': '180px',
            'boxSizing': 'border-box'
        },
        children=[
            html.H3(title, style={
                'margin': '0',
                'color': corporate_colors['text'],
                'fontWeight': '600',
                'fontSize': '14px'
            }),
            html.H2(
                formatted_value,
                style={
                    'color': color,
                    'margin': '8px 0',
                    'fontSize': '18px',
                    'fontWeight': '700',
                    'whiteSpace': 'nowrap'
                }
            )
        ]
    )


# Модифицируем функцию send_prompt_to_llm
def send_prompt_to_llm(kpi_data: dict, giga_token, user_question=None, user_income=None):
    credentials = giga_token

    # Формирование строки с данными о просрочках
    overdue_info = (
        f"- Просрочки до 6 дней: {kpi_data['overdue_categories']['less_6_days']} случаев\n"
        f"- Просрочки 6–30 дней: {kpi_data['overdue_categories']['6_30_days']} случаев\n"
        f"- Просрочки 31–60 дней: {kpi_data['overdue_categories']['31_60_days']} случаев\n"
        f"- Просрочки 61–90 дней: {kpi_data['overdue_categories']['61_90_days']} случаев\n"
        f"- Просрочки более 90 дней: {kpi_data['overdue_categories']['90_plus_days']} случаев\n"
        f"- Максимальная просрочка: {kpi_data['max_overdue']:,.0f} ₽\n"
    )
    loans_info = "\n".join(
        f"{idx + 1}. Кредит ID: {loan['id']}\n"
        f"   - Сумма задолженности: {loan['debt']:,.0f} ₽\n"
        f"   - Дата расчета: {loan['calc_date']}\n"
        f"   - Дата просрочки: {loan['due_date']}\n"
        f"   - Просроченная сумма: {loan['past_due']:,.0f} ₽\n"
        f"   - Ставка: {loan['rate']}%"
        for idx, loan in enumerate(kpi_data.get('active_loans', []))
    )
    loan_types_info = "\n".join(
        f"- {lt['loan_type']}: {lt['count']} кредитов, сумма {lt['sum']:,.0f} ₽, макс. ставка {lt['max_rate']}%"
        for lt in kpi_data.get('loan_types', [])
    )
    # Формирование строки с типами кредитов
    # loan_types_info = "\n".join(
    #     f"- {loan_type}: {data['count']} кредитов, сумма {data['sum']:,.0f} ₽"
    #     for loan_type, data in kpi_data['loan_types'].items()
    # )
    # loan_purposes_info = "\n".join(
    #     f"- {purpose}: {data['count']} кредитов, сумма {data['sum']:,.0f} ₽"
    #     for purpose, data in kpi_data['loan_purposes'].items()
    # )
    prompt = f"""
    ### Ваша кредитная ситуация:
    - Количество активных кредитов: {kpi_data['num_active_loans']}
    - Детализация активных кредитов: {loans_info if loans_info else "Нет данных о кредитах"}
    - Кредиты с просрочками: {kpi_data['num_overdue_loans']} из {kpi_data['num_active_loans']}
    - Средняя ставка: {kpi_data['avg_rate']:.1f}%
    - Минимальная ставка: {kpi_data['min_rate']:.1f}%
    - Максимальная ставка: {kpi_data['max_rate']:.1f}%
    - Просрочка по основному долгу: {kpi_data['total_past_due_principal']:,.0f} ₽
    - Просрочка по процентам: {kpi_data['total_past_due_interest']:,.0f} ₽
    - История просрочек:\n{overdue_info}
    - Вероятность невозрата долга {default_prob:.1f}%
    - Ежемесячная платежная нагрузка (основной долг + проценты): {kpi_data['monthly_payment_load']:,.0f} ₽
    - Виды кредитов:\n{loan_types_info}


    ### Контекст анализа:
    - Основной долг: {kpi_data['total_principal']:,.0f} ₽
    - Начисленные проценты: {kpi_data['total_interest']:,.0f} ₽
    - Средний платёж: {kpi_data['avg_monthly']:,.0f} ₽
    - Доход пользователя: {user_income if user_income else 'не указан'}

    ### Пользовательский вопрос:
    {user_question if user_question else 'Общие рекомендации'}

    ### Задача:
    - Ответить на вопрос пользователя конкретно, если пользователь спрашивает конкретные данные, суммы, срок и т.д.
    - Дать рекомендации (не более 3) по управлению долгами, если пользователь не спрашивает конкретные данные по своей ситуации.

    - Учитывать:
      - Виды кредитов (например, микрозаймы, ипотека, потребительские кредиты) для приоритизации действий.
      - Просрочки для минимизации ущерба кредитной истории.
      - Ставки кредитов в сравнении с ключевой ставкой ЦБ (21%) для рекомендаций по рефинансированию.
      - Доход и платежную нагрузку (выше 40% от дохода — высокая нагрузка).
      - Вероятность невозврата ({default_prob:.1f}%) для оценки рисков.
    - Формат ответа: маркированный список.

    ### Требования к ответу:
    1.  **Запреты**:
       - ❌ Категорически запрещены шаблонные рекомендации без данных пользователя, такие как:
         - "Платите вовремя"
         - "Сократите расходы"
         - "Увеличьте доход"
         - "Следите за бюджетом"
         - "Не берите новые кредиты"
         - "Ведение бюджета и контроль расходов"
         - "Используйте дополнительный доход для погашения мелких кредитов"
         - "Оптимизируйте бюджет"
         - "Пересмотрите структуру кредитов"
         - "Управляйте просрочками"
         - "Избегайте новых просрочек"
       - ❌ Не использовать советы, без данных клиента.
       - ❌ Не использовать советы, которые можно дать любому заемщику.
       - ❌ Не включать рекомендации без связи с конкретными числами или фактами из данных.
       - ❌ Не копировать советы между пользователями.
       - ❌ Не использовать общие фразы без объяснений: если предлагается “рефинансировать кредит” — укажите, какой, под какую ставку, где и почему.
    2. **Персонализация**:
       - Использовать конкретные данные пользователя.
       - Если доход указан, рассчитать долю платежей от дохода пользователя.
       - Упомянуть конкретные кредиты с высокими ставками или просрочками для рекомендаций.
    3. **Простота и понятность**:
       - Использовать простой язык, избегая терминов вроде "консолидация", "дефолт", "рефинансирование" без объяснений.
       - Вместо формул приводить примеры с цифрами пользователя.
       - Объяснять сложные действия через аналогии.
    3. **Неочевидные рекомендации**:
   - Категорически запрещено предлагать шаблонные советы, такие как "платите вовремя", "сократите расходы", "увеличьте доход", "погасите долг раньше срока" или "ведите бюджет". Эти советы слишком общие и не помогают пользователю найти уникальные решения.
   - Предлагать креативные и нестандартные решения, адаптированные к данным пользователя.
   - Каждая рекомендация должна быть уникальной и не повторять советы для других заемщиков.
   - Указать, почему рекомендация подходит именно этому пользователю, ссылаясь на его данные.
    4. **Конкретность**:
       - Указывать, сколько пользователь сэкономит или как улучшится ситуация.
       - Приводить примеры, как рекомендации работают на данных пользователя.
    5. **Формат ответа**:
       - Маркированный список рекомендациями - не более 3.
       - Каждая рекомендация включает: действие, почему оно важно, и как оно поможет (с цифрами).

    """
    if user_income:
        prompt += f"\nРасчеты с учетом дохода {user_income} ₽:"
        prompt += f"\n- Макс. рекомендуемый платеж: {user_income * 0.4:.0f} ₽"
    try:
        with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
            return giga.chat(prompt)
    except Exception as e:
        print(f"Ошибка GigaChat: {str(e)}")
        return "Не удалось получить рекомендации. Пожалуйста, попробуйте позже."


# def send_prompt_to_llm(kpi_data: dict, giga_token, user_question=None, user_income=None, default_prob=None):
#     credentials = giga_token
#
# Формирование строки с данными о просрочках
# overdue_info = (
#     f"- Просрочки до 6 дней: {kpi_data['overdue_categories']['less_6_days']} случаев\n"
#     f"- Просрочки 6–30 дней: {kpi_data['overdue_categories']['6_30_days']} случаев\n"
#     f"- Просрочки 31–60 дней: {kpi_data['overdue_categories']['31_60_days']} случаев\n"
#     f"- Просрочки 61–90 дней: {kpi_data['overdue_categories']['61_90_days']} случаев\n"
#     f"- Просрочки более 90 дней: {kpi_data['overdue_categories']['90_plus_days']} случаев\n"
#     f"- Максимальная просрочка: {kpi_data['max_overdue']:,.0f} ₽\n"
#     f"- Последняя просрочка: {kpi_data['last_overdue_date']}"
# )
#
#     # Формирование строки с типами кредитов
#     loan_types_info = "\n".join(
#         f"- {loan_type}: {data['count']} кредитов, сумма {data['sum']:,.0f} ₽"
#         for loan_type, data in kpi_data['loan_types'].items()
#     )
#     loan_purposes_info = "\n".join(
#         f"- {purpose}: {data['count']} кредитов, сумма {data['sum']:,.0f} ₽"
#         for purpose, data in kpi_data['loan_purposes'].items()
#     )
#
#     prompt = f"""
#     ### Кредитный профиль клиента:
#     - Количество активных кредитов: {kpi_data['num_active_loans']}
#     - Кредиты с просрочками: {kpi_data['num_overdue_loans']} из {kpi_data['num_active_loans']}
#     - Общий основной долг: {kpi_data['total_principal']:,.0f} ₽
#     - Общие проценты: {kpi_data['total_interest']:,.0f} ₽
#     - Средний ежемесячный платеж: {kpi_data['avg_monthly']:,.0f} ₽
#     - Ежемесячная платежная нагрузка (основной долг + проценты): {kpi_data['monthly_payment_load']:,.0f} ₽
#     - Средняя процентная ставка: {kpi_data['avg_rate']:.1f}%
#     - Минимальная ставка: {kpi_data['min_rate']:.1f}%
#     - Максимальная ставка: {kpi_data['max_rate']:.1f}%
#     - Просроченный основной долг: {kpi_data['total_past_due_principal']:,.0f} ₽
#     - Просроченные проценты: {kpi_data['total_past_due_interest']:,.0f} ₽
#     - Вероятность дефолта: {default_prob:.1f}%
#     - Новые кредиты за последний год: {kpi_data['new_loans_last_year']}
#     - История просрочек:\n{overdue_info}
#     - Виды кредитов:\n{loan_types_info}
#     - Цели кредитов:\n{loan_purposes_info}
#     - Доход клиента: {user_income if user_income else 'не указан'} ₽
#
#     ### Пользовательский вопрос:
#     {user_question if user_question else 'Дайте рекомендации по управлению долгами'}
#
#     ### Задача:
#     - Ответить на вопрос пользователя или дать рекомендации по управлению долгами.
#     - Учитывать данные кредитной истории, включая виды кредитов, просрочки и ставки.
#     - Объяснять рекомендации простым языком, избегая сложных финансовых терминов.
#     - Предлагать неочевидные шаги, например:
#       - Рефинансирование кредитов с высокими ставками (выше 16% — ключевой ставки ЦБ).
#       - Консолидацию мелких кредитов для снижения платежной нагрузки.
#       - Приоритизацию погашения кредитов с просрочками более 90 дней.
#       - Оптимизацию бюджета с учетом дохода.
#     - Сравнивать ставки клиента с ключевой ставкой ЦБ (16%) для рекомендаций по рефинансированию.
#     - Формат ответа: маркированный список.
#
#     ### Требования к ответу:
#     - Персонализировать рекомендации, используя данные о просрочках, видах кредитов и доходе.
#     - Объяснять, как рекомендации помогут клиенту (например, снизят платежи или улучшат кредитную историю).
#     - Избегать шаблонных советов вроде "платите вовремя".
#     - Если доход указан, рассчитать, какую часть дохода составляют платежи, и предложить действия, если нагрузка выше 40%.
#
#     ### Пример расчета:
#     {f"Максимальный рекомендуемый платеж: {user_income * 0.4:.0f} ₽ (40% от дохода)" if user_income else ""}
#     """
#
#     try:
#         with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
#             return giga.chat(prompt)
#     except Exception as e:
#         print(f"Ошибка GigaChat: {str(e)}")
#         return "Не удалось получить рекомендации. Пожалуйста, попробуйте позже."

# Колбэк для создания кнопок
@callback(
    Output('credit-cards-buttons', 'children'),
    Input('crossfilter-selection', 'data')
)
def update_credit_cards_buttons(filtered_data):
    try:
        # Чтение и преобразование данных
        filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')

        # Преобразование типов с обработкой ошибок

        filtered_df['arrear_sign'] = pd.to_numeric(
            filtered_df['arrear_sign'], errors='coerce'
        )

        # Фильтрация данных
        credit_cards = filtered_df[
            (filtered_df['trade_loan_kind_code'].astype(str) == 'Кредитная линия с лимитом задолженности') &
            (filtered_df['arrear_sign'] == 1)
            ]

        # Создание кнопок
        buttons = []
        for _, row in credit_cards.iterrows():
            try:
                # Форматирование суммы
                principal = float(row['arrear_principal_outstanding'])
                formatted_principal = f"{principal:,.0f} ₽".replace(",", " ")

                # Обработка минимального платежа
                min_payment = (
                    f"{float(row['paymnt_condition_min_paymt']):,.0f} ₽"
                    if not pd.isna(row['paymnt_condition_min_paymt'])
                    else "оплачен"
                )

                # Создание кнопки
                button = html.Button(
                    children=[
                        html.Div(formatted_principal,
                                 style={'fontSize': '18px',
                                        'fontWeight': 'bold',
                                        'marginBottom': '5px'}),
                        html.Div(f"Минимальный платеж: {min_payment}",
                                 style={'fontSize': '12px'})
                    ],
                    id={'type': 'credit-card-button',
                        'index': str(row['account_uid'])},
                    style={
                        'margin': '10px',
                        'padding': '15px',
                        'width': '220px',
                        'borderRadius': '10px',
                        'backgroundColor': '#7E5BEF',
                        'color': 'white',
                        'cursor': 'pointer',
                        'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'
                    }
                )
                buttons.append(button)

            except Exception as e:
                print(f"Ошибка при создании кнопки: {str(e)}")
                continue

        # Возвращаем результат с проверкой на пустоту
        return (
            html.Div(
                buttons,
                style={
                    'display': 'flex',
                    'flexWrap': 'wrap',
                    'gap': '15px',
                    'padding': '10px',
                    'backgroundColor': corporate_colors['card'],
                    'borderRadius': '8px'
                }
            ) if buttons else
            html.Div("Нет активных кредитных карт",
                     style={'color': corporate_colors['text'],
                            'padding': '20px'})
        )

    except Exception as e:
        print(f"Критическая ошибка в колбэке: {str(e)}")
        return html.Div("Ошибка при загрузке данных",
                        style={'color': 'red', 'padding': '20px'})


# Колбэк для отображения деталей
@callback(
    [Output('credit-card-details', 'children'),
     Output('llm-output1', 'children', allow_duplicate=True)],
    [Input({'type': 'credit-card-button', 'index': ALL}, 'n_clicks')],
    [State('crossfilter-selection', 'data')],
    prevent_initial_call=True
)
def show_credit_card_details(clicks, filtered_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    try:
        filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        account_uid = str(json.loads(button_id)['index'])

        # Преобразуем account_uid к строковому типу
        filtered_df['account_uid'] = filtered_df['account_uid'].astype(str)
        card_data_df = filtered_df[filtered_df['account_uid'] == account_uid]

        if card_data_df.empty:
            return html.Div("Данные по карте не найдены",
                            style={'color': 'red'}), dash.no_update

        card_data = card_data_df.iloc[0]

        # Создание таблицы
        table = dash_table.DataTable(
            columns=[
                {'name': 'ID кредита', 'id': 'account_uid'},
                {'name': 'Основной долг', 'id': 'arrear_principal_outstanding'},
                {'name': 'Проценты', 'id': 'arrear_int_outstanding'},
                {'name': 'Иные требования', 'id': 'arrear_other_amt_outstanding'},
                {'name': '% ставка', 'id': 'overall_val_credit_total_amt'},
                {'name': 'Начало льг. периода', 'id': 'paymnt_condition_grace_start_dt'},
                {'name': 'Конец льг. периода', 'id': 'paymnt_condition_grace_end_dt'}
            ],
            data=[{
                'account_uid': card_data['account_uid'],
                'arrear_principal_outstanding': f"{card_data['arrear_principal_outstanding']:,.0f} ₽",
                'arrear_int_outstanding': f"{card_data['arrear_int_outstanding']:,.0f} ₽",
                'arrear_other_amt_outstanding': f"{card_data['arrear_other_amt_outstanding']:,.0f} ₽",
                'overall_val_credit_total_amt': f"{card_data['overall_val_credit_total_amt']}%",
                'paymnt_condition_grace_start_dt': card_data['paymnt_condition_grace_start_dt'],
                'paymnt_condition_grace_end_dt': card_data['paymnt_condition_grace_end_dt']
            }],
            style_table={'overflowX': 'auto'},
            style_cell={
                'minWidth': '100px',
                'fontSize': '12px',
                'padding': '5px'
            }
        )

        # Формирование сообщения о льготном периоде
        grace_end_dt = card_data.get('paymnt_condition_grace_end_dt')

        if pd.isna(grace_end_dt) or grace_end_dt in [None, '']:
            message = "льготный период по этой карте не предусмотрен"
        else:
            grace_period_msg = f"чтобы не платить проценты до {grace_end_dt}"

            message = (
                    f"Внесите сумму {card_data['arrear_amt_outstanding']:,.0f} ₽ " +
                    grace_period_msg
            )

        return table, message

    except Exception as e:
        print(f"Ошибка: {str(e)}")
        return html.Div("Ошибка при загрузке данных карты",
                        style={'color': 'red'}), dash.no_update


@callback(
    [Output('repay-confirm', 'displayed'),
     Output('redirect-url', 'href')],
    Input('repay-button', 'n_clicks'),
    prevent_initial_call=True
)
def handle_repay(n_clicks):
    if n_clicks and n_clicks > 0:
        return True, None  # Показываем диалог
    return False, None


@callback(
    Output('redirect-url', 'href', allow_duplicate=True),
    Input('repay-confirm', 'submit_n_clicks'),
    prevent_initial_call=True
)
def redirect_to_bank(submit_clicks):
    if submit_clicks:
        return 'https://www.banki.ru'  # Перенаправление при подтверждении
    return None


# Добавьте колбэк для управления отображением
@callback(
    [Output('selected-loan-details', 'style'),
     Output('loan-details-table', 'data')],
    [Input('loan-selector', 'value')]
)
def update_loan_details(selected_loan):
    if not selected_loan:
        return {'display': 'none'}, []

    # Конвертируем selected_loan в строку для сравнения
    selected_loan = str(selected_loan)
    filtered = df[df['account_uid'] == selected_loan]

    # Проверка наличия данных
    if filtered.empty:
        return {'display': 'none'}, []
    return {'display': 'block'}, filtered.to_dict('records')


@app.callback(
    [Output('payment-calendar', 'children'),
     Output('current-month-year', 'children')],
    [Input('prev-month', 'n_clicks'),
     Input('next-month', 'n_clicks'),
     Input('crossfilter-selection', 'data')],
    [State('current-month-year', 'children'),
     State('report-date-filter', 'date')]
)
def update_calendar(prev_clicks, next_clicks, filtered_data, current_display, report_date):
    # print(f"Данные для календаря: {filtered_df.shape if not filtered_df.empty else 'пусто'}")
    ctx = dash.callback_context

    # Определяем начальный месяц и год
    if not ctx.triggered:
        if report_date:
            report_date = pd.to_datetime(report_date)
            month, year = report_date.month, report_date.year
        else:
            today = date.today()
            month, year = today.month, today.year
    else:
        if current_display:
            month_name, year_str = current_display.split()
            month = list(calendar.month_name).index(month_name)
            year = int(year_str)
        else:
            if report_date:
                report_date = pd.to_datetime(report_date)
                month, year = report_date.month, report_date.year
            else:
                today = date.today()
                month, year = today.month, today.year

        if ctx.triggered[0]['prop_id'] == 'prev-month.n_clicks':
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        elif ctx.triggered[0]['prop_id'] == 'next-month.n_clicks':
            month += 1
            if month > 12:
                month = 1
                year += 1

    # filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split') if filtered_data else pd.DataFrame()
    # Исправленный блок чтения данных
    try:
        if filtered_data:
            filtered_df = pd.read_json(io.StringIO(filtered_data), orient='split')
        else:
            filtered_df = pd.DataFrame()
    except Exception as e:
        print(f"Ошибка чтения данных: {str(e)}")
        filtered_df = pd.DataFrame()

    # Исправленный принт
    if not filtered_df.empty:
        print(f"Данные для календаря: {filtered_df.shape}")
    else:
        print("Данные для календаря: пусто")

    # Создаем словарь с суммами платежей по дням
    payment_dict = {}
    if not filtered_df.empty:
        if 'paymnt_condition_principal_terms_amt_dt' in filtered_df.columns:
            filtered_df['paymnt_condition_principal_terms_amt_dt'] = pd.to_datetime(
                filtered_df['paymnt_condition_principal_terms_amt_dt'], errors='coerce')
            principal_payments = filtered_df.dropna(subset=['paymnt_condition_principal_terms_amt_dt'])
            for _, row in principal_payments.iterrows():
                payment_date = row['paymnt_condition_principal_terms_amt_dt']
                if pd.notna(payment_date) and payment_date.year == year and payment_date.month == month:
                    day = payment_date.day
                    amount = row.get('paymnt_condition_principal_terms_amt', 0)
                    if not pd.isna(amount):
                        payment_dict[day] = payment_dict.get(day, 0) + amount

        if 'paymnt_condition_interest_terms_amt_dt' in filtered_df.columns:
            filtered_df['paymnt_condition_interest_terms_amt_dt'] = pd.to_datetime(
                filtered_df['paymnt_condition_interest_terms_amt_dt'], errors='coerce')
            interest_payments = filtered_df.dropna(subset=['paymnt_condition_interest_terms_amt_dt'])
            for _, row in interest_payments.iterrows():
                payment_date = row['paymnt_condition_interest_terms_amt_dt']
                if pd.notna(payment_date) and payment_date.year == year and payment_date.month == month:
                    day = payment_date.day
                    amount = row.get('paymnt_condition_interest_terms_amt', 0)
                    if not pd.isna(amount):
                        payment_dict[day] = payment_dict.get(day, 0) + amount

    # Создаем календарь вручную вместо использования HTMLCalendar
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    month_year_display = f"{month_name} {year}"

    # Создаем HTML для календаря
    html_cal = f"""
    <table style="
        font-family: Avenir, sans-serif;
        font-size: 20px;
        width: 100%;
        border-collapse: separate;
        border-spacing: 5px;
    ">
        <thead>
            <tr>
                <th colspan="7" style="
                    padding: 15px;
                    text-align: center;
                    background-color: #F5F3FF;
                    color: #4B0082;
                    font-size: 24px;
                    border-radius: 8px;
                ">{month_year_display}</th>
            </tr>
            <tr>
                {"".join(f'<th style="padding: 15px; text-align: center; background-color: #F5F3FF; color: #4B0082; font-size: 24px; border-radius: 8px;">{day}</th>'
                         for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"])}
            </tr>
        </thead>
        <tbody>
    """

    for week in cal:
        html_cal += "<tr>"
        for day in week:
            if day == 0:
                html_cal += '<td style="padding: 15px; text-align: center; height: 80px; vertical-align: top; border: 1px solid #E5DEFF; border-radius: 8px; background-color: #FFFFFF;"></td>'
            else:
                payment = payment_dict.get(day, 0)
                payment_html = f'<div style="color: #4B0082; font-size: 16px; margin-top: 10px; font-weight: bold;">{payment:,.0f} ₽</div>' if payment else ''
                html_cal += f'''
                <td style="
                    padding: 15px;
                    text-align: center;
                    height: 80px;
                    vertical-align: top;
                    border: 1px solid #E5DEFF;
                    border-radius: 8px;
                    background-color: #FFFFFF;
                    font-size: 20px;
                ">
                    {day}
                    {payment_html}
                </td>
                '''
        html_cal += "</tr>"
    html_cal += "</tbody></table>"

    return html.Iframe(
        srcDoc=html_cal,
        style={
            'width': '100%',
            'height': '800px',
            'border': 'none',
            'transform': 'scale(1)',
            'transform-origin': '0 0'
        }
    ), month_year_display

@app.callback(
    [Output('consent-modal', 'style'),
     Output('main-content', 'style'),
     Output('consent-given', 'data')],
    [Input('consent-button', 'n_clicks')]
)
def handle_consent(n_clicks):
    if n_clicks:
        # Скрыть модалку, показать основной контент
        return {'display': 'none'}, {'display': 'block'}, True
    # По умолчанию показать модалку
    return {'display': 'flex'}, {'display': 'none'}, False

@app.callback(
    Output('user-question', 'value'),
    [Input('frequent-questions', 'value')],
    prevent_initial_call=True
)
def update_user_question_from_dropdown(selected_question):
    """Обновляет поле ввода при выборе вопроса из выпадающего списка"""
    if selected_question:
        return selected_question
    return dash.no_update


@app.callback(
    [Output('disclaimer-modal', 'style'),
     Output('show-disclaimer', 'data', allow_duplicate=True)],
    [Input('disclaimer-ok-button', 'n_clicks'),
     Input('show-disclaimer', 'data')],
    prevent_initial_call=True
)
def handle_disclaimer(ok_clicks, show_flag):
    ctx = dash.callback_context

    # Если нужно показать предупреждение
    if show_flag:
        return {'display': 'flex'}, False

    # Если нажата кнопка "Я понимаю"
    if ctx.triggered[0]['prop_id'] == 'disclaimer-ok-button.n_clicks':
        return {'display': 'none'}, False

    return dash.no_update, dash.no_update

if __name__ == '__main__':
    app.run_server(debug=True)