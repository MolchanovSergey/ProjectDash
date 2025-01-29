import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.express as px
import pandas as pd

# Чтение CSV файла с данными
df = pd.read_csv('credits.csv', sep=';')

# Преобразование дат в datetime
df['fund_date'] = pd.to_datetime(df['fund_date'])
df['trade_close_dt'] = pd.to_datetime(df['trade_close_dt'], errors='coerce')  # Ошибки преобразования в NaT

# Добавление столбца с годом выдачи займа
df['fund_year'] = df['fund_date'].dt.year

# Фильтрация погашенных кредитов
df['is_paid'] = df['loan_indicator'] == 1

# Сумма займов и количество по годам (агрегация)
loan_summary_by_year = df.groupby('fund_year').agg(
    loan_count=('account_amt_credit_limit', 'count'),
    total_amount=('account_amt_credit_limit', 'sum'),
    total_arrears=('arrear_int_outstanding', 'sum')
).reset_index()

# Сумма погашенных кредитов с расчетом стоимости кредита
paid_loan_summary = df[df['is_paid']].groupby('fund_year').agg(
    paid_count=('account_amt_credit_limit', 'count'),
    total_paid_amount=('account_amt_credit_limit', 'sum'),
    avg_annual_cost_percentage=('overall_val_credit_total_amt', 'mean'),
    total_monetary_cost=('overall_val_credit_total_monetary_amt', 'sum')
).reset_index()
# Create the app
app = dash.Dash(name="my_first_dash_app")

# График по сумме и количеству займов по годам
fig1 = px.bar(loan_summary_by_year,
              x='fund_year',
              y=['loan_count', 'total_amount'],
              title="Количество и сумма займов по годам",
              labels={"loan_count": "Количество займов", "total_amount": "Сумма займов"},
              barmode='group')

# График по погашенным кредитам с полной стоимостью
fig2 = px.bar(paid_loan_summary,
              x='fund_year',
              y=['paid_count', 'total_paid_amount'],
              title="Количество и сумма погашенных кредитов",
              labels={"paid_count": "Количество погашенных кредитов", "total_paid_amount": "Сумма погашенных кредитов"},
              barmode='group')

# График по полной стоимости кредита (проценты и денежное выражение)
fig3 = px.scatter(paid_loan_summary,
                  x='avg_annual_cost_percentage',
                  y='total_monetary_cost',
                  color='fund_year',
                  title="Полная стоимость кредита (проценты vs денежное выражение)",
                  labels={"avg_annual_cost_percentage": "Полная стоимость кредита (%)",
                          "total_monetary_cost": "Полная стоимость кредита (в денежном выражении)"})

# # Load dataset using Plotly
# tips = px.data.tips()
#
# fig = px.scatter(tips, x="total_bill", y="tip") # Create a scatterplot
#
# app.layout = html.Div(children=[
#    html.H1(children='Hello Dash'),  # Create a title with H1 tag
#
#    html.Div(children='''
#        Dash: A web application framework for your data.
#    '''),  # Display some text
#
#    dcc.Graph(
#        id='example-graph',
#        figure=fig
#    )  # Display the Plotly figure
# ])
# Компоновка элементов дэшборда
app.layout = html.Div(children=[
    html.H1(children='Дэшборд по кредитам'),

    html.Div(children='''
        Дэшборд для анализа кредитного портфеля заемщика.
    '''),

    # График количества и суммы займов по годам
    dcc.Graph(
        id='loan-summary-graph',
        figure=fig1
    ),

    # График количества и суммы погашенных кредитов
    dcc.Graph(
        id='paid-loan-summary-graph',
        figure=fig2
    ),

    # График полной стоимости кредита
    dcc.Graph(
        id='cost-comparison-graph',
        figure=fig3
    )
])
# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    app.run_server(debug=True)  # Run the Dash app



