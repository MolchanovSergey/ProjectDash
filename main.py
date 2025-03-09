import dash
from dash import dcc, html, Input, Output, callback, State
import plotly.express as px
import pandas as pd
from datetime import datetime
from dash import dash_table
import plotly.graph_objects as go
from gigachat import GigaChat
from dotenv import load_dotenv
import os


load_dotenv()

client_file_path = "client_5.csv"
mapping_file_path = "maping_csv.csv"
giga_token = os.getenv('TOKEN_GIGA')
# Чтение файлов
df = pd.read_csv(client_file_path, delimiter=';',
                         parse_dates=["fund_date", "trade_close_dt", "loan_indicator_dt"], encoding="utf-8")
mapping_df = pd.read_csv(mapping_file_path, delimiter=';')
df['reporting_dt'] = pd.to_datetime(df['reporting_dt'])

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
    '0%',      # -inf <= x <= 0
    '10%',     # 0 < x < 10
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
server = app.server # Gunicorn запускает Flask-сервер
app.layout = html.Div(style={'backgroundColor': corporate_colors['background'],
                             'fontFamily': 'Verdana, sans-serif', # Шрифтовая схема
                             'padding': '10px'  # Уменьшаем общий отступ
                             }, children=[
    # Компонент для перенаправления
    dcc.Location(id='redirect-url', refresh=True),

    html.H1("Ваш помощник по кредитам", style={'textAlign': 'center', 'color': corporate_colors['text']}),


        html.Div([
            html.H3("Выберите дату отчета", style={'textAlign': 'center', 'color': corporate_colors['text']}),
            dcc.DatePickerSingle(
                id='report-date-filter',
                min_date_allowed=df['reporting_dt'].min(),
                max_date_allowed=df['reporting_dt'].max(),
                initial_visible_month=df['reporting_dt'].max(),
                date=df['reporting_dt'].max()
            )
        ], style={'width': '35%', 'padding': '10px'}),



    # KPI метрики
    # html.Div(id='kpi-cards', style={'display': 'grip', 'justifyContent': 'space-around', 'padding': '20px'}),
    html.Div(id='kpi-cards', style={
        'display': 'grid',
        'grid-template-columns': 'repeat(auto-fit, minmax(180px, 1fr))',
        'gap': '10p x',
        'padding': '5px'
    }),
    # # 3. Добавим медиа-запросы для адаптации
    # html.Style('''
    #     @media (max-width: 600px) {
    #         .dash-table-container {
    #             overflow-x: auto;
    #             font-size: 12px;
    #         }
    #         .dash-graph {
    #             height: 300px!important;
    #         }
    #         .DatePickerSingle {
    #             width: 100%!important;
    #         }
    #         .dash-dropdown {
    #             font-size: 14px;
    #         }
    #     }
    # '''),
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

    # Скрытый элемент для хранения данных о выборе
    dcc.Store(id='crossfilter-selection', data=df.to_json(date_format='iso', orient='split')),

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
                    # 'backgroundColor': '#4B0082',
                    # 'color': 'white',
                    # 'fontWeight': 'bold',
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
            # style_cell={'textAlign': 'left', 'minWidth': '100px'},
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
                        # 'backgroundColor': '#4B0082',
                        # 'color': 'white',
                        # 'fontWeight': 'bold',
                        'fontSize': '14px'
                    },
                    style_data={
                        'backgroundColor': corporate_colors['card'],
                        'color': corporate_colors['text']
                    }
                ),

                # В блоке layout после таблицы добавьте:
                # html.Div([
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
                                'fontFamily': 'Verdana',
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
                    'fontFamily': 'Verdana',
                    'marginBottom': '10px'
                   }
        ),
        html.Button('ДОБАВИТЬ',
                    id='upgrade-button',
                    n_clicks=0,
                    style={
                    'fontSize': '18px',  # Уеличен шрифт кнопки
                    'padding': '6px 12px',  # Увеличен размер кнопки
                    'borderRadius': '5px',
                    'backgroundColor': '#4B0082',
                    'color': 'white',
                    'fontFamily': 'Verdana',
                    'cursor': 'pointer'
                }
                    )
    ], style={'padding': '20px',

              }),

    # График с доходом
    dcc.Graph(id='income-plot',
              config={'responsive': True},
              style={'height': '40vh'}
              ),

    # Блок с рекомендациями от GigaChat
    html.Div([
        html.H3("Рекомендации по кредитному портфелю", style={'margin': '20px 0'}),
        dcc.Input(
                id='user-question',
                type='text',
                placeholder='Введите ваш вопрос...',
                style={
                    'width': '100%',
                    'height': '50px',
                    'fontSize': '18px',
                    'fontFamily': 'Verdana',
                    'marginBottom': '10px'
                    }
            ),
        html.Button('ОТПРАВИТЬ',
                    id='submit-question',
                    n_clicks=0,
                    style={
                    'fontSize': '18px',  # Уеличен шрифт кнопки
                    'padding': '6px 12px',  # Увеличен размер кнопки
                    'borderRadius': '5px',
                    'backgroundColor': '#4B0082',
                    'color': 'white',
                    'fontFamily': 'Verdana',
                    'cursor': 'pointer'
                }
        ),
        dcc.Markdown(id='llm-output', style={
            'background': corporate_colors['card'],
            'padding': '15px',
            'borderRadius': '5px',
            'marginTop': '10px',
            # 'whiteSpace': 'pre-wrap'  # Для форматирования текста
            'border': '1px solid #EEE'
        })
    ], style={'padding': '20px'}),
])


# Объединенный колбэк для всех выходов
@callback(
    [Output('crossfilter-selection', 'data'),
     Output('kpi-cards', 'children'),
     Output('llm-output', 'children')],
    [Input('report-date-filter', 'date'),
     # Input('currency-filter', 'value'), # Заменяем year-filter на date
     # Input('client-filter', 'value'),
     # Input('amount-by-year', 'clickData'),
     # Input('count-by-year', 'clickData'),
     Input('submit-question', 'n_clicks')],
    [State('user-question', 'value'),
     State('crossfilter-selection', 'data')]
)
# def update_data(selected_year, selected_currency, selected_client, click_amount, click_count):
#     ctx = dash.callback_context
#     filtered_df = df.copy()
def unified_callback(selected_date, n_clicks, question, filtered_data):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Базовый фильтр: только активные кредиты
    filtered_df = df[df["arrear_sign"] == 1].copy()


    # Обработка фильтров
    if triggered_id in ['report-date-filter', None]:
        # Фильтрация по дате отчета
        if selected_date:
            filtered_df = filtered_df[filtered_df['reporting_dt'] == pd.to_datetime(selected_date)]

        # Расчет KPI
        total_principal = filtered_df['arrear_principal_outstanding'].sum(skipna=True)
        total_interest = filtered_df['arrear_int_outstanding'].sum(skipna=True)
        total_other = filtered_df['arrear_other_amt_outstanding'].sum(skipna=True)
        avg_monthly = filtered_df['month_aver_paymt_aver_paymt_amt'].sum(skipna=True)

        kpi_cards = [
            # create_kpi_card("Основной долг", f"{total_principal:,.0f}", "#1f77b4"),
            # create_kpi_card("Проценты", f"{total_interest:,.0f}", "#2ca02c"),
            # create_kpi_card("Иные требования", f"{total_other:,.0f}", "#d62728"),
            # create_kpi_card("Ср.месячн. платеж", f"{avg_monthly:,.0f}", "#9467bd")
            create_kpi_card("Основной долг", total_principal, "#1f77b4"),
            create_kpi_card("Проценты", total_interest, "#2ca02c"),
            create_kpi_card("Иные требования", total_other, "#d62728"),
            create_kpi_card("Ср.месячн. платеж", avg_monthly, "#9467bd")
        ]

        # Формирование данных для LLM
        try:
            kpi_data = {
                "total_principal": total_principal,
                "total_interest": total_interest,
                "total_other": total_other,
                "avg_monthly": avg_monthly
            }
            response = send_prompt_to_llm(kpi_data, giga_token)
            recommendation = response.choices[0].message.content
        except Exception as e:
            recommendation = f"Ошибка: {str(e)}"

        return filtered_df.to_json(date_format='iso', orient='split'), kpi_cards, recommendation
    # Обработка пользовательского вопроса
    elif triggered_id == 'submit-question' and question:
        try:
            # mapping_df = pd.read_csv(mapping_file_path, delimiter=';')
            # Загрузка данных с правильными параметрами
            mapping_df = pd.read_csv(
                "maping_csv.csv",
                delimiter=";",
                skiprows=2,  # Пропускаем первые две строки (заголовок и разделитель)
                names=["Поле", "Описание"],  # Только две колонки
                usecols=[2, 3],  # Берем данные из 2-й и 3-й колонок файла
                encoding='utf-8-sig'  # Для корректной работы с BOM
            )
            client_df = pd.read_json(filtered_data, orient='split')

            # Удаляем лишние символы в названиях колонок
            mapping_df["Поле"] = (
                mapping_df["Поле"]
                .str.strip()  # Удаляем пробелы
                .str.replace("['\",]", "", regex=True)  # Удаляем кавычки и запятые
            )
            # Создание словаря для переименования
            rename_dict = dict(zip(mapping_df["Поле"], mapping_df["Описание"]))

            # Переименование колонок
            client_df_rus = client_df.rename(columns=rename_dict)
            # print(list(client_df_rus.columns))

            # Формирование контекста маппинга
            mapping_context = "\n".join([f"{row['Поле']}: {row['Описание']}" for _, row in mapping_df.iterrows()])
            # print(mapping_context)

            # Статистика с русскими названиями колонок
            data_stats = client_df_rus.describe().to_string()
            # print(data_stats)





            # Формирование промпта
            prompt = f"""
            Вопрос пользователя: {question}

            Справочник параметров:
            {mapping_context}

            Задача:
            1. Определить соответствующий параметр из колонок: 
            {list(client_df_rus.columns)}
            2. Ответить на вопрос используя данные из {client_df_rus}
            3. Дать ответ используя терминологию из справочника.
            
            Пример правильного ответа:
            "Сумма платежа в августе 2023 составляет X рублей, 
            рассчитанная на основе [русское название колонки]"
            
            Статистика данных (русские названия):
            {data_stats}  
 
            """

            # Отправка запроса
            with GigaChat(credentials=giga_token, verify_ssl_certs=False) as giga:
                response = giga.chat(prompt)
                answer = response.choices[0].message.content
            return dash.no_update, dash.no_update, answer

        except Exception as e:
            return dash.no_update, dash.no_update, f"Ошибка: {str(e)}"

    return dash.no_update, dash.no_update, "Ожидаю ваш вопрос..."
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
        filtered_df = pd.read_json(filtered_data, orient='split') if filtered_data else pd.DataFrame()
        # Добавляем преобразование типа для 'fund_date'
        if not filtered_df.empty and 'fund_date' in filtered_df.columns:
            filtered_df['fund_date'] = pd.to_datetime(filtered_df['fund_date'])
    except:
        filtered_df = pd.DataFrame()

    # Заглушки для пустых данных
    empty_fig = px.scatter(title="Нет данных").update_layout(
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        font_color=corporate_colors['text']
    )
    if filtered_df.empty:
        return empty_fig, empty_fig, [], empty_fig

    # Круговые диаграммы
    loan_kind_fig = px.pie(
        filtered_df,
        names='trade_loan_kind_code',
        values='account_amt_credit_limit',
        title='Распределение по видам займов',
        hole=0.6  # Добавьте этот параметр для создания кольца
    ).update_layout(
        font_family='Verdana',
        font_color=corporate_colors['text'],
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        title_font_size=18,
        title_font_color='#5D3FBA'
    )

    loan_purpose_fig = px.pie(
        filtered_df,
        names='trade_acct_type1',
        values='account_amt_credit_limit',
        title='Распределение по целям кредитов',
        hole=0.6  # Добавьте этот параметр
    ).update_layout(
        font_family='Verdana',
        font_color=corporate_colors['text'],
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        title_font_size=18,
        title_font_color='#5D3FBA'
    )
    # Новая круговая диаграмма
    rate_pie_fig = px.pie(
        filtered_df,
        names='rate_category',
        values='arrear_principal_outstanding',
        title='Распределение задолженности по ставкам',
        hole=0.6
    ).update_layout(
        font_family='Verdana',
        font_color=corporate_colors['text'],
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        title_font_size=18,
        title_font_color='#5D3FBA'
    )

    # Таблица с задолженностью
    arrear_df = filtered_df[filtered_df['arrear_sign'] == 1]
    table_data = arrear_df[[
        'account_uid', 'arrear_amt_outstanding',
        'arrear_calc_date', 'due_arrear_start_dt', 'past_due_amt_past_due', 'overall_val_credit_total_amt'
    ]].to_dict('records')

    # График с доходом
    income_fig = go.Figure()
    if n_clicks > 0 and income is not None and not filtered_df.empty and 'fund_date' in filtered_df.columns:
        monthly_debt = filtered_df.resample('M', on='fund_date')['account_amt_credit_limit'].mean()
        income_fig.add_trace(go.Scatter(
            x=monthly_debt.index,
            y=monthly_debt.values,
            name='Средняя задолженность'
        ))
        income_fig.add_hline(
            y=income,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Доход: {income}"
        )
        income_fig.update_layout(
            title="Задолженность vs Доход",
            plot_bgcolor=corporate_colors['card'],
            paper_bgcolor=corporate_colors['background'],
            font_color=corporate_colors['text']
        )
    else:
        income_fig = empty_fig.update_layout(title="Задолженность vs Доход")

    return loan_kind_fig, loan_purpose_fig, rate_pie_fig, table_data, income_fig

# В колбэки добавьте:
@callback(
    Output('payment-schedule', 'figure'),
    Input('crossfilter-selection', 'data')
)
def update_payment_chart(filtered_data):
    filtered_df = pd.read_json(filtered_data, orient='split')

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
        # Конвертируем в float, если передана строка
        num_value = float(value) if isinstance(value, str) else value
        formatted_value = f"{value:,.2f}".replace(',', ' ').replace('.', ',') + ' ₽'
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




def send_prompt_to_llm(kpi_data: dict, giga_token):

    credentials = giga_token  # Замените на реальные учетные данные

    prompt = f"""
    Анализ параметров кредитной истории:
    - Основной долг: {kpi_data['total_principal']}
    - Начисленные проценты: {kpi_data['total_interest']}
    - Иные требования: {kpi_data['total_other']:,.0f}
    - Средний платёж: {kpi_data['avg_monthly']:,.0f}

    Задача: 1. Дать развернутый анализ по каждому параметру. Дать конкретные рекомендации по каждому параметру для заемщика по улучшению. 
            2. Ответ оформить как маркированный список.
            3. Указать среднюю процентную ставку потребительского кредитованя в банках : (на текущую дату {datetime.now()} составляет 28% - 36%)
            Расчет не выводить!"
         
    """
    prompt += f"\n\nДополнительный контекст маппинга:\n{mapping_df.iloc[:, 4].to_string()}"

    with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
        return giga.chat(prompt)
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

if __name__ == '__main__':
    app.run_server(debug=True)