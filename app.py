import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from bcb import sgs
import warnings
from flask import Flask, render_template, request, jsonify
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import time
import functools
import pytz

warnings.filterwarnings("ignore", category=FutureWarning)

# Inicializa o app Flask
server = Flask(__name__)

# Inicializa o app Dash
app = dash.Dash(
    __name__,
    server=server,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)

# Configuração inicial
start_date = '1994-07-01'
end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

# Dicionário de indicadores
indicadores = {
    'Ibovespa': {'codigo': '^BVSP', 'fonte': 'YF', 'unidade': 'Pontos'},
    'PIB Total': {'codigo': 4380, 'fonte': 'BCB', 'unidade': 'R$ milhões'},
    'Taxa Selic': {'codigo': 4189, 'fonte': 'BCB', 'unidade': '% ao ano'},
    'IPCA Mensal': {'codigo': 433, 'fonte': 'BCB', 'unidade': '%'},
    'Câmbio USD/BRL': {'codigo': 3696, 'fonte': 'BCB', 'unidade': 'R$'},
    'Taxa de Desemprego': {'codigo': 24369, 'fonte': 'BCB', 'unidade': '%'}
}

# Sistema de cache
cache = {}
CACHE_TIMEOUT = 3600  # 1 hora

# Função para buscar dados no Yahoo Finance
def fetch_yfinance_data(ticker, start_date, end_date):
    try:
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
            threads=True,
            timeout=30
        )
        
        if data.empty:
            print(f"Aviso: Nenhum dado encontrado para {ticker}")
            return pd.DataFrame()
            
        if 'Close' not in data.columns:
            print(f"Aviso: Dados incompletos para {ticker}")
            return pd.DataFrame()
            
        return data[['Close']].rename(columns={'Close': ticker})
        
    except Exception as e:
        print(f"Erro ao buscar {ticker}: {str(e)}")
        return pd.DataFrame()

# Decorator para cache
def with_cache(func):
    @functools.wraps(func)
    def wrapper(indicador_nome):
        if indicador_nome in cache and time.time() - cache[indicador_nome]['timestamp'] < CACHE_TIMEOUT:
            return cache[indicador_nome]['data']
        
        try:
            result = func(indicador_nome)
            cache[indicador_nome] = {
                'data': result,
                'timestamp': time.time()
            }
            return result
        except Exception as e:
            print(f"Erro ao carregar {indicador_nome}: {str(e)}")
            return pd.DataFrame()
    return wrapper

# Função para baixar dados
@with_cache
def baixar_dados(indicador_nome):
    indicador_info = indicadores[indicador_nome]
    
    if indicador_info['fonte'] == 'YF':
        df = fetch_yfinance_data(indicador_info['codigo'], start_date, end_date)
        return df.dropna()
    else:
        df = sgs.get({indicador_nome: indicador_info['codigo']}, start=start_date, end=end_date)
        return df.dropna()

# Layout do app Dash
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H1("Dashboard de indicadores econômicos", 
                   className="text-center my-4")
        ], width=12)
    ]),
    
    dbc.Row([
        dbc.Col([
            html.Label("Selecione o Indicador:", className="fw-bold"),
            dcc.Dropdown(
                id='dropdown-indicador',
                options=[{'label': k, 'value': k} for k in indicadores.keys()],
                value='Ibovespa',
                clearable=False,
                className="mb-4"
            ),
            
            dbc.Card([
                dbc.CardBody([
                    html.H5("Informações do indicador", className="card-title"),
                    html.Div(id='info-indicador', className="card-text")
                ])
            ], className="mb-4"),
            
            dcc.Loading(
                id="loading-grafico",
                type="circle",
                children=[
                    dcc.Graph(id='grafico-indicador', style={'height': '500px'})
                ]
            ),
            
            html.Div(id='data-atualizacao', className="text-muted mt-3 text-center")
        ], width=12)
    ]),
    
    html.Hr(),
    
    dbc.Row([
        dbc.Col([
            html.P("© 2024 Dashboard econômico - dados do Yahoo Finance e Banco Central do Brasil", 
                  className="text-center text-muted")
        ], width=12)
    ])
], fluid=True)

# Callbacks
@app.callback(
    [Output('grafico-indicador', 'figure'),
     Output('info-indicador', 'children'),
     Output('data-atualizacao', 'children')],
    [Input('dropdown-indicador', 'value')]
)
def atualizar_grafico(indicador_nome):
    if not indicador_nome:
        return go.Figure(), "", ""
    
    dados = baixar_dados(indicador_nome)
    
    if dados.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Erro ao carregar dados",
            xaxis_title="Data",
            yaxis_title="Valor",
            height=500
        )
        info = html.P("Não foi possível carregar os dados para este indicador.", 
                     className="text-danger")
        return fig, info, ""
    
    # Obtém as datas reais dos dados
    data_inicio = dados.index.min().strftime('%d/%m/%Y')
    data_fim = dados.index.max().strftime('%d/%m/%Y')
    
    # Cria o gráfico
    fig = go.Figure()
    
    if 'Acum' in indicador_nome:
        fig.add_trace(go.Bar(
            x=dados.index,
            y=dados[dados.columns[0]],
            name=indicador_nome
        ))
    else:
        fig.add_trace(go.Scatter(
            x=dados.index,
            y=dados[dados.columns[0]],
            name=indicador_nome,
            mode='lines',
            line=dict(width=2)
        ))
    
    # Configurações do gráfico
    fig.update_layout(
        hovermode='x unified',
        title=f'{indicador_nome} ({data_inicio} a {data_fim})',
        xaxis_title='Data',
        yaxis_title=indicadores[indicador_nome]['unidade'],
        height=500,
        showlegend=False,
        template='plotly_white'
    )
    
    # Informações do indicador
    info_content = [
        html.P(f"Fonte: {'Yahoo Finance' if indicadores[indicador_nome]['fonte'] == 'YF' else 'Banco Central do Brasil'}"),
        html.P(f"Unidade: {indicadores[indicador_nome]['unidade']}"),
        html.P(f"Período: {data_inicio} até {data_fim}"),
        html.P(f"Último valor: {dados.iloc[-1, 0]:.2f}")
    ]
    
    # Data de atualização
    # Define o fuso horário de São Paulo
    tz_sao_paulo = pytz.timezone('America/Sao_Paulo')
    data_atual_sp = datetime.now(tz_sao_paulo)
    atualizacao = f"Última atualização: {data_atual_sp.strftime('%d/%m/%Y %H:%M:%S')} (horário de Brasília)"
        
    return fig, info_content, atualizacao

# Rota principal do Flask
@server.route('/')
def index():
    return app.index()

# Adicione no final do arquivo:
if __name__ == '__main__':
    app.run_server(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=False
    )
