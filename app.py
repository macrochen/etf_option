from flask import Flask, render_template, request, jsonify
import plotly
import plotly.graph_objs as go
import json
from back_test_engine import BacktestConfig, BacktestEngine
import pandas as pd

app = Flask(__name__)

# 常量定义
ETF_OPTIONS = [
    {'value': '510050', 'label': '上证50ETF (510050)'},
    {'value': '510300', 'label': '沪深300ETF (510300)'},
    {'value': '510500', 'label': '中证500ETF (510500)'},
    {'value': '159901', 'label': '深证100ETF (159901)'},
    {'value': '159915', 'label': '创业板ETF (159915)'},
    {'value': '159919', 'label': '深市沪深300ETF (159919)'},
    {'value': '159922', 'label': '深市中证500ETF (159922)'},
    {'value': '588000', 'label': '科创板50ETF (588000)'},
    {'value': '588080', 'label': '科创板100ETF (588080)'}
]

DELTA_OPTIONS = [
    {'value': 0.1, 'label': '0.1'},
    {'value': 0.2, 'label': '0.2'},
    {'value': 0.3, 'label': '0.3'},
    {'value': 0.4, 'label': '0.4'},
    {'value': 0.5, 'label': '0.5'},
    {'value': 0.6, 'label': '0.6'},
    {'value': 0.7, 'label': '0.7'}
]

HOLDING_TYPES = [
    {'value': 'stock', 'label': '正股持仓'},
    {'value': 'synthetic', 'label': '合成持仓'}
]

@app.route('/')
def index():
    return render_template('index.html', 
                         etf_options=ETF_OPTIONS,
                         delta_options=DELTA_OPTIONS,
                         holding_types=HOLDING_TYPES)

@app.route('/run_backtest', methods=['POST'])
def run_backtest():
    # 获取表单数据
    etf_code = request.form.get('etf_code')
    delta = float(request.form.get('delta'))
    holding_type = request.form.get('holding_type', 'stock')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # 转换日期字符串为datetime对象
    if start_date:
        start_date = pd.to_datetime(start_date)
    if end_date:
        end_date = pd.to_datetime(end_date)
    
    # 运行回测
    config = BacktestConfig(etf_code, delta=delta, start_date=start_date, end_date=end_date, holding_type=holding_type)
    engine = BacktestEngine(config)
    results = engine.run_backtest()
    
    if not results:
        return jsonify({'error': '回测执行失败'})
    
    # 生成图表
    fig = create_plot(results)
    plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    # 生成交易记录表格数据
    trade_records = format_trade_records(results)
    
    # 生成交易汇总数据
    trade_summary = format_trade_summary(results)
    
    # 生成每日盈亏数据
    daily_pnl = format_daily_pnl(results)
    
    # 生成策略对比数据
    strategy_comparison = format_strategy_comparison(results)
    
    return jsonify({
        'plot': plot_json,
        'trade_records': trade_records,
        'trade_summary': trade_summary,
        'daily_pnl': daily_pnl,
        'strategy_comparison': strategy_comparison
    })

def create_plot(results):
    """创建Plotly图表"""
    portfolio_df = results['portfolio_df']
    etf_buy_hold_df = results['etf_buy_hold_df']
    put_trades = results['put_trades']
    call_trades = results['call_trades']
    
    # 创建策略收益曲线
    trace1 = go.Scatter(
        x=portfolio_df.index,
        y=portfolio_df['cumulative_return'],
        name='期权策略收益率',
        line=dict(color='blue', width=2)
    )
    
    # 创建ETF持有收益曲线
    trace2 = go.Scatter(
        x=etf_buy_hold_df.index,
        y=etf_buy_hold_df['etf_buy_hold_return'],
        name=f'持有{results["symbol"]}ETF收益率',
        line=dict(color='gray', width=2)
    )
    
    # 添加PUT交易点
    put_dates = [date for date, _ in put_trades]
    put_returns = [etf_buy_hold_df.loc[date, 'etf_buy_hold_return'] for date, _ in put_trades]
    trace3 = go.Scatter(
        x=put_dates,
        y=put_returns,
        mode='markers',
        name='卖出PUT',
        marker=dict(color='red', size=10, symbol='circle')
    )
    
    # 添加CALL交易点
    call_dates = [date for date, _ in call_trades]
    call_returns = [etf_buy_hold_df.loc[date, 'etf_buy_hold_return'] for date, _ in call_trades]
    trace4 = go.Scatter(
        x=call_dates,
        y=call_returns,
        mode='markers',
        name='卖出CALL',
        marker=dict(color='green', size=10, symbol='circle')
    )
    
    # 添加最大回撤区间
    max_drawdown_start = results.get('max_drawdown_start_date')
    max_drawdown_end = results.get('max_drawdown_end_date')
    if max_drawdown_start and max_drawdown_end:
        # 获取从开始到结束的所有数据
        drawdown_data = portfolio_df.loc[max_drawdown_start:max_drawdown_end]
        
        # 获取最大回撤期间的峰值
        peak = portfolio_df.loc[:max_drawdown_end]['cumulative_return'].expanding().max()
        drawdown_peak = peak.loc[max_drawdown_start:max_drawdown_end]
        
        # 创建回撤区域
        trace5 = go.Scatter(
            x=drawdown_data.index,
            y=drawdown_peak,
            mode='lines',
            line=dict(color='rgba(255,0,0,0)', width=0),
            showlegend=False,
            hoverinfo='skip'
        )
        
        trace6 = go.Scatter(
            x=drawdown_data.index,
            y=drawdown_data['cumulative_return'],
            fill='tonextx',
            mode='lines',
            fillcolor='rgba(255,0,0,0.2)',
            line=dict(color='rgba(255,0,0,0)', width=0),
            showlegend=True,
            name=f'最大回撤 ({abs(results.get("max_drawdown", 0)):.2f}%)'
        )
        
        # 注意：trace5必须在trace6之前，这样填充才会在两条线之间
        data = [trace1, trace2, trace3, trace4, trace5, trace6]
    else:
        data = [trace1, trace2, trace3, trace4]
    
    # 创建图表布局
    layout = go.Layout(
        title=dict(
            text=f'期权策略 vs 持有{results["symbol"]}ETF收益率对比',
            x=0.5,
            y=0.95
        ),
        width=1200,
        height=800,
        xaxis=dict(
            title='日期',
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            type='date',
            dtick='M3',  # 每3个月显示一个刻度
            tickformat='%y/%m',  # 只显示年份的后两位
            tickangle=45,  # 45度角显示日期
            tickfont=dict(size=10)  # 调整字体大小
        ),
        yaxis=dict(
            title='累计收益率 (%)',
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            zeroline=True,
            zerolinecolor='rgba(0,0,0,0.2)'
        ),
        hovermode='x unified',
        plot_bgcolor='white',
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.15,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(255,255,255,0.8)'
        ),
        margin=dict(l=50, r=50, t=150, b=80)  # 增加底部边距，为倾斜的日期留出空间
    )
    
    return {'data': data, 'layout': layout}

def format_trade_records(results):
    """格式化交易记录"""
    trade_data = []
    
    # 获取所有交易记录
    for date, trade_info in results.get('trades', {}).items():
        trade_data.append([
            date.strftime('%Y-%m-%d'),
            trade_info.get('交易类型', ''),
            f"{trade_info.get('到期日ETF价格', 0):.2f}",
            f"{trade_info.get('行权价', 0):.2f}",
            f"{trade_info.get('期权价格', 0):.4f}",
            f"{trade_info.get('合约数量', 0)}张",
            f"{trade_info.get('权利金', 0):.2f}",
            f"{trade_info.get('交易成本', 0):.2f}",
            f"{trade_info.get('Delta', 0):.2f}"
        ])
    
    return {
        'headers': ['日期', '交易类型', 'ETF价格', '行权价', '期权价格', '合约数量', '权利金', '交易成本', 'Delta'],
        'data': sorted(trade_data)  # 按日期排序
    }

def format_daily_pnl(results):
    """格式化每日盈亏数据"""
    daily_data = []
    
    # 获取每日盈亏数据
    portfolio_df = results['portfolio_df']
    for date, row in portfolio_df.iterrows():
        daily_return = row.get('daily_return', 0)
        # 为收益率添加颜色标识
        if daily_return > 0:
            return_str = f'<span style="color: #4CAF50">{daily_return:.2f}%</span>'
        elif daily_return < 0:
            return_str = f'<span style="color: #F44336">{daily_return:.2f}%</span>'
        else:
            return_str = f'{daily_return:.2f}%'
            
        daily_data.append([
            date.strftime('%Y-%m-%d'),
            f"{row.get('cash', 0):.2f}",
            f"{row.get('etf_value', 0):.2f}",
            f"{row.get('option_value', 0):.2f}",
            f"{row.get('portfolio_value', 0):.2f}",
            return_str
        ])
    
    return {
        'headers': ['日期', '现金', 'ETF市值', '期权市值', '总市值', '当日收益率'],
        'data': daily_data
    }

def format_strategy_comparison(results):
    """格式化策略对比数据"""
    portfolio_metrics = results.get('portfolio_metrics', {})
    etf_metrics = results.get('etf_metrics', {})
    
    # 计算累计收益率
    portfolio_df = results['portfolio_df']
    etf_buy_hold_df = results['etf_buy_hold_df']
    cumulative_return_portfolio = portfolio_metrics.get('portfolio_total_return', 0) * 100  # 转换为百分比
    cumulative_return_etf = etf_buy_hold_df['etf_buy_hold_return'].iloc[-1]
    
    # 计算年化收益率
    annual_return_portfolio = portfolio_metrics.get('portfolio_annual_return', 0) * 100  # 转换为百分比
    annual_return_etf = etf_metrics.get('etf_annual_return', 0) * 100  # 转换为百分比
    
    # 计算夏普比率
    sharpe_ratio_portfolio = portfolio_metrics.get('portfolio_sharpe_ratio', 0)
    sharpe_ratio_etf = etf_metrics.get('etf_sharpe_ratio', 0)
    
    # 计算最大回撤
    portfolio_max_drawdown = results['portfolio_max_drawdown']
    portfolio_max_drawdown_start = results['portfolio_max_drawdown_start_date']
    portfolio_max_drawdown_end = results['portfolio_max_drawdown_end_date']
    
    # 计算ETF的最大回撤
    etf_max_drawdown = etf_metrics.get('etf_max_drawdown', 0) * 100  # 转换为百分比
    
    # 计算期权策略的单日最大亏损
    portfolio_values = portfolio_df['portfolio_value']
    portfolio_daily_returns = portfolio_values.pct_change() * 100  # 转换为百分比
    portfolio_max_daily_loss = abs(min(0, portfolio_daily_returns.min()))
    portfolio_max_daily_loss_date = portfolio_daily_returns[portfolio_daily_returns == -portfolio_max_daily_loss].index[0]
    
    # 计算ETF的单日最大亏损
    etf_data = results['etf_data']  # 获取原始ETF数据
    
    # 使用开盘价和收盘价计算日内跌幅
    etf_daily_returns = ((etf_data['收盘价'] - etf_data['开盘价']) / etf_data['开盘价'] * 100)
    etf_max_daily_loss = abs(min(0, etf_daily_returns.min()))
    etf_max_daily_loss_date = etf_daily_returns[etf_daily_returns == -etf_max_daily_loss].index[0]
    
    print(f"\nETF单日最大亏损计算:")
    print(f"最大亏损日期: {etf_max_daily_loss_date}")
    print(f"开盘价: {etf_data.loc[etf_max_daily_loss_date, '开盘价']:.4f}")
    print(f"收盘价: {etf_data.loc[etf_max_daily_loss_date, '收盘价']:.4f}")
    print(f"单日跌幅: {etf_max_daily_loss:.2f}%")
    
    # 比较函数：根据指标类型决定哪个值更好
    def compare_metrics(portfolio_value, etf_value, metric_type='higher_better'):
        if metric_type == 'higher_better':
            if portfolio_value > etf_value:
                return ['bold', 'normal']
            elif portfolio_value < etf_value:
                return ['normal', 'bold']
            else:
                return ['normal', 'normal']
        else:  # lower_better
            if portfolio_value < etf_value:
                return ['bold', 'normal']
            elif portfolio_value > etf_value:
                return ['normal', 'bold']
            else:
                return ['normal', 'normal']
    
    # 格式化数值并添加样式
    def format_value(value, style, suffix=''):
        if style == 'bold':
            return f'<span style="color: #FF4444; font-weight: bold">{value:.2f}{suffix}</span>'
        return f'{value:.2f}{suffix}'
    
    # 格式化日期并添加样式
    def format_date_with_value(value, date, style):
        if style == 'bold':
            return f'<span style="color: #FF4444; font-weight: bold">{value:.2f}% ({date.strftime("%Y-%m-%d")})</span>'
        return f'{value:.2f}% ({date.strftime("%Y-%m-%d")})'
    
    # 比较各项指标
    annual_return_style = compare_metrics(
        portfolio_metrics.get('portfolio_annual_return', 0) * 100,
        etf_metrics.get('etf_annual_return', 0) * 100,
        'higher_better'  # 年化收益率越高越好
    )
    max_drawdown_style = compare_metrics(
        portfolio_max_drawdown,
        etf_max_drawdown,
        'lower_better'  # 最大回撤越低越好
    )
    volatility_style = compare_metrics(
        portfolio_metrics.get('portfolio_annual_volatility', 0) * 100,
        etf_metrics.get('etf_annual_volatility', 0) * 100,
        'lower_better'  # 年化波动率越低越好
    )
    sharpe_style = compare_metrics(
        portfolio_metrics.get('portfolio_sharpe_ratio', 0),
        etf_metrics.get('etf_sharpe_ratio', 0),
        'higher_better'  # 夏普比率越高越好
    )
    cumulative_style = compare_metrics(
        portfolio_metrics.get('portfolio_total_return', 0) * 100,
        cumulative_return_etf,
        'higher_better'  # 累计收益率越高越好
    )
    max_daily_loss_style = compare_metrics(
        portfolio_max_daily_loss,
        etf_max_daily_loss,
        'lower_better'  # 单日最大亏损越低越好
    )
    
    data = [
        ['累计收益率',
         format_value(portfolio_metrics.get('portfolio_total_return', 0) * 100, cumulative_style[0], '%'),
         format_value(cumulative_return_etf, cumulative_style[1], '%')],
        ['年化收益率', 
         format_value(portfolio_metrics.get('portfolio_annual_return', 0) * 100, annual_return_style[0], '%'),
         format_value(etf_metrics.get('etf_annual_return', 0) * 100, annual_return_style[1], '%')],
        ['单日最大亏损',
         format_date_with_value(portfolio_max_daily_loss, portfolio_max_daily_loss_date, max_daily_loss_style[0]),
         format_date_with_value(etf_max_daily_loss, etf_max_daily_loss_date, max_daily_loss_style[1])],
        ['最大回撤',
         format_value(portfolio_max_drawdown, max_drawdown_style[0], '%'),
         format_value(etf_max_drawdown, max_drawdown_style[1], '%')],
        ['年化波动率',
         format_value(portfolio_metrics.get('portfolio_annual_volatility', 0) * 100, volatility_style[0], '%'),
         format_value(etf_metrics.get('etf_annual_volatility', 0) * 100, volatility_style[1], '%')],
        ['夏普比率',
         format_value(portfolio_metrics.get('portfolio_sharpe_ratio', 0), sharpe_style[0], ''),
         format_value(etf_metrics.get('etf_sharpe_ratio', 0), sharpe_style[1], '')],
    ]
    
    return {
        'headers': ['指标', '期权策略', '持有ETF'],
        'data': data,
        'allow_html': True  # 添加标志允许HTML渲染
    }

def format_trade_summary(results):
    """格式化交易汇总数据"""
    stats = results.get('statistics', {})
    
    # 计算ETF交易盈亏
    etf_trading_pnl = stats.get('etf_sell_income', 0) - stats.get('etf_buy_cost', 0)
    current_etf_value = stats.get('max_etf_held', 0) * results['etf_data'].iloc[-1]['收盘价']
    unrealized_etf_pnl = current_etf_value #- (stats.get('etf_buy_cost', 0) - stats.get('etf_sell_income', 0))
    etf_exercise_pnl = etf_trading_pnl + unrealized_etf_pnl
    
    data = [
        ['卖出CALL总次数', f"{stats.get('call_sold', 0)}次"],
        ['CALL行权次数', f"{stats.get('call_exercised', 0)}次"],
        ['CALL作废次数', f"{stats.get('call_expired', 0)}次"],
        ['CALL权利金总计', f"{stats.get('total_call_premium', 0):.2f}"],
        ['卖出PUT总次数', f"{stats.get('put_sold', 0)}次"],
        ['PUT行权次数', f"{stats.get('put_exercised', 0)}次"],
        ['PUT作废次数', f"{stats.get('put_expired', 0)}次"],
        ['PUT权利金总计', f"{stats.get('total_put_premium', 0):.2f}"],
        ['收取权利金总计', f"{stats.get('total_put_premium', 0) + stats.get('total_call_premium', 0):.2f}"],
        # ['PUT行权成本', f"{stats.get('put_exercise_cost', 0):.2f}"],
        # ['CALL行权收入', f"{stats.get('call_exercise_income', 0):.2f}"],
        ['ETF交易已实现盈亏', f"{etf_trading_pnl:.2f}"],
        ['ETF持仓未实现盈亏', f"{unrealized_etf_pnl:.2f}"],
        ['ETF交易总盈亏', f"{etf_exercise_pnl:.2f}"],
        ['总交易成本', f"{stats.get('total_transaction_cost', 0):.2f}"]
    ]
    
    return {
        'headers': ['统计项', '数值'],
        'data': data
    }

if __name__ == '__main__':
    app.run(debug=True) 