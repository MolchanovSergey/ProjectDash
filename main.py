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


# Предобработка данных
df["year"] = df["fund_date"].dt.year
closed_loans = df[df["loan_indicator"] == 1]

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
                             'fontFamily': 'Verdana, sans-serif'  # Шрифтовая схема
                             }, children=[
    html.H1("Ваш помощник по кредитам", style={'textAlign': 'center', 'color': corporate_colors['text']}),

    # Фильтры
    html.Div([
        html.Div([
            dcc.Dropdown(
                id='client-filter',
                options=[{'label': 'Все клиенты', 'value': 'all'}] +
                        [{'label': str(cid), 'value': cid} for cid in df['client_id'].unique()],
                value='all',
                placeholder="Выберите клиента"
            )
        ], style={'width': '25%', 'padding': '10px','display':'none'}),

        html.Div([
            html.H3("Выберите год за который хотите узнать информацию", style={'textAlign': 'center', 'color': corporate_colors['text']}),
            dcc.Dropdown(
                id='year-filter',
                options=[{'label': 'Все годы', 'value': 'all'}] +
                        [{'label': str(year), 'value': year} for year in sorted(df['year'].unique())],
                value='all',
                placeholder="Выберите год"
            )
        ], style={'width': '35%', 'padding': '10px'}),

        html.Div([
            dcc.Dropdown(
                id='currency-filter',
                options=[{'label': 'Все валюты', 'value': 'all'}] +
                        [{'label': curr, 'value': curr} for curr in df['account_amt_currency_code'].unique()],
                value='all',
                placeholder="Выберите валюту"
            )
        ], style={'width': '25%', 'padding': '10px','display':'none'})

    ], style={'display': 'flex'}),

    # KPI метрики
    # html.Div(id='kpi-cards', style={'display': 'grip', 'justifyContent': 'space-around', 'padding': '20px'}),
    html.Div(id='kpi-cards', style={
        'display': 'grid',
        'grid-template-columns': 'repeat(auto-fit, minmax(45%, 1fr))',
        'gap': '30px',
        'padding': '10px'
    }),
    # Новые круговые диаграммы
    html.Div([
        html.Div([
            dcc.Graph(id='loan-kind-pie'),
        ], style={'width': '100%', 'padding': '10px'}),

        html.Div([
            dcc.Graph(id='loan-purpose-pie'),
        ], style={'width': '100%', 'padding': '10px'})
    ]),
    # Основные Графики
    html.Div([
        dcc.Graph(id='amount-by-year', style={'width': '100%', 'padding': '10px','display':'none'}),
        dcc.Graph(id='count-by-year', style={'width': '100%', 'padding': '10px','display':'none'}),
        dcc.Graph(id='cumulative-debt', style={'width': '100%', 'padding': '10px'}),
        dcc.Graph(id='cost-scatter', style={'width': '100%', 'padding': '10px','display':'none'}),
        dcc.Graph(id='dynamic-line', style={'width': '100%', 'padding': '10px','display':'none'}),


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
            style_header={
                    'backgroundColor': '#4B0082',
                    'color': 'white',
                    'fontWeight': 'bold'
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
            style_cell={'textAlign': 'left', 'minWidth': '100px'},
            page_size=10

        )
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
    dcc.Graph(id='income-plot'),

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
    [Input('year-filter', 'value'),
     Input('currency-filter', 'value'),
     Input('client-filter', 'value'),
     Input('amount-by-year', 'clickData'),
     Input('count-by-year', 'clickData'),
     Input('submit-question', 'n_clicks')],
    [State('user-question', 'value'),
     State('crossfilter-selection', 'data')]
)
# def update_data(selected_year, selected_currency, selected_client, click_amount, click_count):
#     ctx = dash.callback_context
#     filtered_df = df.copy()
def unified_callback(selected_year, selected_currency, selected_client,
                    click_amount, click_count, n_clicks,
                    question, filtered_data):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Обработка фильтров и KPI
    if triggered_id in ['year-filter', 'currency-filter', 'client-filter',
                       'amount-by-year', 'count-by-year', None]:
        filtered_df = df.copy()
    # Фильтрация данных
        if selected_year != 'all':
            filtered_df = filtered_df[filtered_df['year'] == selected_year]
        if selected_currency != 'all':
            filtered_df = filtered_df[filtered_df['account_amt_currency_code'] == selected_currency]
        if selected_client != 'all':  # Фильтр по клиенту
            filtered_df = filtered_df[filtered_df['client_id'] == selected_client]
        # Обработка кликов на графиках
        if ctx.triggered:
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if trigger_id in ['amount-by-year', 'count-by-year']:
                click_data = click_amount if trigger_id == 'amount-by-year' else click_count
                if click_data:
                    point = click_data['points'][0]
                    filtered_df = filtered_df[
                        (filtered_df['year'] == point['x']) &
                        (filtered_df['account_amt_currency_code'] == point['customdata'][0]) &
                        ((filtered_df['client_id'] == selected_client) if selected_client != 'all' else True)
                        ]

        # Расчет KPI
        # Расчет KPI с проверкой на пустые данные
        if filtered_df.empty:
            total_loans = total_closed = total_amount = total_closed_amount = 0
        else:
            total_loans = filtered_df.shape[0]
            total_closed = filtered_df['loan_indicator'].sum()
            total_amount = filtered_df['account_amt_credit_limit'].sum(skipna=True)
            total_closed_amount = filtered_df.loc[filtered_df['loan_indicator'] == 1, 'account_amt_credit_limit'].sum(
                skipna=True)

        kpi_cards = [
            create_kpi_card("Всего кредитов", total_loans, "#1f77b4"),
            create_kpi_card("Погашено кредитов", total_closed, "#2ca02c"),
            create_kpi_card("Общая сумма", f"{total_amount:,.0f}", "#d62728"),
            create_kpi_card("Погашенная сумма", f"{total_closed_amount:,.0f}", "#9467bd")
        ]
        # Рекомендации по
        try:
            kpi_data = {
                "total_loans": total_loans,
                "total_closed": total_closed,
                "total_amount": total_amount,
                "total_closed_amount": total_closed_amount
            }
        # # Получаем рекомендации
        # try:
            response = send_prompt_to_llm(kpi_data, giga_token)
            recommendation = response.choices[0].message.content
        except Exception as e:
            recommendation = f"Ошибка получения рекомендаций: {str(e)}"

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



            # # Применяем переименование
            # df_rus = client_df.rename(columns=rename_dict)

            # # Анализ маппинга
            # mapping_context = ""
            # for idx, row in mapping_giga.iterrows():
            #     mapping_context += f"Строка {idx}: {row[4]}\n"

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

    return loan_kind_fig, loan_purpose_fig, table_data, income_fig

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
    return html.Div(
        style={
            'background': corporate_colors['card'],
            'border': f'2px solid {color}',
            'borderRadius': '15px',
            'padding': '20px',
            'margin': '10px',
            'boxShadow': '0 4px 6px 0 rgba(93, 63, 186, 0.1)',
            'width': '22%'
        },
        children=[
            html.H3(title, style={
                'margin': '0',
                'color': corporate_colors['text'],
                'fontWeight': '600'
            }),
            html.H2(
                value,
                style={
                    'color': color,
                    'margin': '10px 0',
                    'fontSize': '28px',
                    'fontWeight': '700'
                }
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

    if filtered_df.empty:
        return [
            px.scatter(title="Нет данных"),
            px.scatter(title="Нет данных"),
            px.scatter(title="Нет данных"),
            px.scatter(title="Нет данных")
        ]

    # Группировка данных
    loans_by_year = filtered_df.groupby(["year", "account_amt_currency_code", "client_id"]).agg(
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
            font_family='Verdana',
            font_color=corporate_colors['text'],
            plot_bgcolor=corporate_colors['card'],
            paper_bgcolor=corporate_colors['background'],
            title_font_size=18,
            title_font_color='#5D3FBA'
        )

    return fig1, fig2, fig3, fig4


@callback(
    Output('cumulative-debt', 'figure'),
    [Input('crossfilter-selection', 'data')]
)
def update_cumulative_debt(filtered_data):
    filtered_df = pd.read_json(filtered_data, orient='split')

    if filtered_df.empty:
        return px.line(title="Нет данных")

    # Создаем DataFrame событий
    events = []
    for _, row in filtered_df.iterrows():
        if pd.notnull(row['fund_date']):
            events.append({
                'date': row['fund_date'],
                'amount': row['account_amt_credit_limit'] + row['overall_val_credit_total_monetary_amt'],
                'type': 'issue'
            })
        if pd.notnull(row['loan_indicator_dt']) and row['loan_indicator'] == 1:
            events.append({
                'date': row['loan_indicator_dt'],
                'amount': -(row['account_amt_credit_limit'] + row['overall_val_credit_total_monetary_amt']),
                'type': 'repayment'
            })

    df_events = pd.DataFrame(events)

    if df_events.empty:
        return px.line(title="Нет данных")

    # Сортируем по дате и считаем нарастающий итог
    df_events = df_events.sort_values('date')
    df_events['cumulative'] = df_events['amount'].cumsum()

    # Создаем график
    fig = px.line(
        df_events,
        x='date',
        y='cumulative',
        title='Динамика общей задолженности',
        color_discrete_sequence=[corporate_colors['colorscale'][0]]
    )

    fig.update_layout(
        font_family='Verdana',
        font_color=corporate_colors['text'],
        plot_bgcolor=corporate_colors['card'],
        paper_bgcolor=corporate_colors['background'],
        title_font_size=18,
        title_font_color='#5D3FBA',
        xaxis_title="Дата",
        yaxis_title="Сумма задолженности",
        yaxis_tickformat=",.0f"
    )

    return fig

def send_prompt_to_llm(kpi_data: dict, giga_token):

    credentials = giga_token  # Замените на реальные учетные данные

    prompt = f"""
    Анализ параметров кредитной истории:
    - Всего кредитов: {kpi_data['total_loans']}
    - Погашено кредитов: {kpi_data['total_closed']}
    - Общая сумма: {kpi_data['total_amount']:,.0f}
    - Погашенная сумма: {kpi_data['total_closed_amount']:,.0f}

    Задача: 1. Дать развернутый анализ по каждому параметру. Дать конкретные рекомендации по каждому параметру для заемщика по улучшению. 
            2. Ответ оформить как маркированный список.
            3. Указать среднюю процентную ставку потребительского кредитованя в банках : (на текущую дату {datetime.now()} составляет 21,0%+ 7%/15%)
            Расчет не выводить!"
         
    """
    prompt += f"\n\nДополнительный контекст маппинга:\n{mapping_df.iloc[:, 4].to_string()}"

    with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
        return giga.chat(prompt)


if __name__ == '__main__':
    app.run_server(debug=True)