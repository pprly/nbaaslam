"""
NBA Value Betting Analyzer - Web Dashboard
Веб-интерфейс с визуализацией статистики
"""

from flask import Flask, render_template, request, jsonify
from datetime import datetime
import json
import os

# Загружаем .env файл
try:
    from dotenv import load_dotenv
    # Ищем .env в текущей директории
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✓ Загружен .env файл: {env_path}")
    else:
        load_dotenv()  # Попробует найти .env автоматически
except ImportError:
    print("⚠️ python-dotenv не установлен: pip install python-dotenv")

# Импорты из основного проекта
from config import config
from data_fetcher import DataFetcher, PlayerLine, PlayerStats, generate_demo_data
from stability_analyzer import analyze_player_pool, StabilityAnalyzer
from probability_model import ValueDetector, BetType

try:
    from free_data_fetcher import FreeDataFetcher, ManualLine
    FREE_MODE_AVAILABLE = True
except ImportError:
    FREE_MODE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'nba_value_analyzer_2024'

# Глобальный кэш данных
data_cache = {
    'lines': [],
    'stats': {},
    'analysis': None,
    'value_bets': []
}


def american_to_prob(odds: float) -> float:
    """Конвертация американских коэффициентов в вероятность"""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/demo', methods=['GET'])
def load_demo():
    """Загрузить демо данные"""
    lines, stats = generate_demo_data()
    
    # Сохраняем в кэш
    data_cache['lines'] = lines
    data_cache['stats'] = stats
    
    # Анализируем
    analysis = analyze_player_pool(lines, stats)
    data_cache['analysis'] = analysis
    
    # Ищем value bets
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"])
    data_cache['value_bets'] = value_bets
    
    return jsonify({
        'success': True,
        'message': f'Загружено {len(lines)} линий (демо)',
        'players': [format_player_data(item) for item in analysis["analyzed"]],
        'value_bets': [format_value_bet(vb) for vb in value_bets],
        'summary': analysis['summary']
    })


@app.route('/api/live', methods=['GET'])
def load_live():
    """Загрузить реальные данные с Odds API"""
    
    # Проверяем API ключ
    api_key = os.environ.get('ODDS_API_KEY', '')
    
    # Проверяем что ключ установлен и не дефолтный
    if not api_key or api_key == 'твой_ключ_сюда':
        return jsonify({
            'success': False,
            'error': 'API ключ не настроен! Открой файл .env и вставь свой ключ от the-odds-api.com'
        })
    
    # Обновляем конфиг
    config.api.odds_api_key = api_key
    
    fetcher = DataFetcher()
    
    # Получаем линии на игроков
    try:
        lines = fetcher.fetch_player_props()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Ошибка загрузки линий: {str(e)}'
        })
    
    if not lines:
        return jsonify({
            'success': False,
            'error': 'Линии не найдены. Player props обычно доступны за 24ч до игры.'
        })
    
    # Собираем статистику игроков через nba_api (надёжнее)
    stats = {}
    errors = []
    
    if FREE_MODE_AVAILABLE:
        free_fetcher = FreeDataFetcher()
        for i, line in enumerate(lines):
            try:
                print(f"  [{i+1}/{len(lines)}] {line.player_name}...", end=" ")
                player_stats = free_fetcher.fetch_player_stats(line.player_name)
                if player_stats:
                    stats[line.player_name] = player_stats
                    print("✓")
                else:
                    print("✗")
            except Exception as e:
                print(f"✗ {e}")
                errors.append(f"{line.player_name}: {str(e)}")
    else:
        # Fallback на старый метод
        for line in lines:
            try:
                player_stats = fetcher.fetch_player_stats(line.player_name, line.player_id)
                if player_stats:
                    stats[line.player_name] = player_stats
            except Exception as e:
                errors.append(f"{line.player_name}: {str(e)}")
    
    if not stats:
        return jsonify({
            'success': False,
            'error': f'Не удалось загрузить статистику игроков. Ошибки: {"; ".join(errors[:3])}'
        })
    
    # Сохраняем в кэш
    data_cache['lines'] = lines
    data_cache['stats'] = stats
    
    # Анализируем
    analysis = analyze_player_pool(lines, stats)
    data_cache['analysis'] = analysis
    
    # Защитные рейтинги команд
    team_defenses = fetcher.fetch_team_defense_ratings()
    
    # Ищем value bets
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"], team_defenses)
    data_cache['value_bets'] = value_bets
    
    return jsonify({
        'success': True,
        'message': f'Загружено {len(lines)} линий, статистика для {len(stats)} игроков',
        'players': [format_player_data(item) for item in analysis["analyzed"]],
        'value_bets': [format_value_bet(vb) for vb in value_bets],
        'summary': analysis['summary']
    })


@app.route('/api/analyze', methods=['POST'])
def analyze_lines():
    """Анализировать введённые линии"""
    data = request.json
    lines_input = data.get('lines', [])
    
    if not lines_input:
        return jsonify({'success': False, 'error': 'Нет линий для анализа'})
    
    # Создаём PlayerLine объекты
    player_lines = []
    for item in lines_input:
        over_odds = float(item.get('over_odds', -110))
        under_odds = float(item.get('under_odds', -110))
        
        line = PlayerLine(
            player_name=item['player'],
            player_id=None,
            team=item.get('team', ''),
            opponent=item.get('opponent', ''),
            game_id='manual',
            game_time=datetime.now(),
            is_home=item.get('is_home', True),
            line_points=float(item['line']),
            over_odds=over_odds,
            under_odds=under_odds,
            over_implied_prob=american_to_prob(over_odds),
            under_implied_prob=american_to_prob(under_odds)
        )
        player_lines.append(line)
    
    # Получаем статистику
    stats = {}
    
    if FREE_MODE_AVAILABLE:
        fetcher = FreeDataFetcher()
        for line in player_lines:
            try:
                player_stats = fetcher.fetch_player_stats(line.player_name)
                if player_stats:
                    stats[line.player_name] = player_stats
            except Exception as e:
                print(f"Ошибка загрузки {line.player_name}: {e}")
    
    if not stats:
        # Fallback на демо данные
        _, demo_stats = generate_demo_data()
        for line in player_lines:
            if line.player_name in demo_stats:
                stats[line.player_name] = demo_stats[line.player_name]
    
    if not stats:
        return jsonify({'success': False, 'error': 'Не удалось загрузить статистику'})
    
    # Сохраняем и анализируем
    data_cache['lines'] = player_lines
    data_cache['stats'] = stats
    
    analysis = analyze_player_pool(player_lines, stats)
    data_cache['analysis'] = analysis
    
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"])
    data_cache['value_bets'] = value_bets
    
    return jsonify({
        'success': True,
        'message': f'Проанализировано {len(analysis["analyzed"])} игроков',
        'players': [format_player_data(item) for item in analysis["analyzed"]],
        'value_bets': [format_value_bet(vb) for vb in value_bets],
        'summary': analysis['summary']
    })


@app.route('/api/player/<name>', methods=['GET'])
def get_player_detail(name):
    """Детальная информация по игроку"""
    if name not in data_cache['stats']:
        return jsonify({'success': False, 'error': 'Игрок не найден'})
    
    stats = data_cache['stats'][name]
    
    # Данные для графиков
    game_dates = [g['game_date'] for g in stats.last_10_games][::-1]
    points = [g['pts'] for g in stats.last_10_games][::-1]
    minutes = [g['min'] for g in stats.last_10_games][::-1]
    
    # Находим линию для этого игрока
    line_value = None
    for line in data_cache['lines']:
        if line.player_name == name:
            line_value = line.line_points
            break
    
    return jsonify({
        'success': True,
        'player': {
            'name': name,
            'team': stats.team,
            'season_ppg': round(stats.season_ppg, 1),
            'season_mpg': round(stats.season_mpg, 1),
            'games_played': stats.games_played,
            'avg_pts_last_5': round(stats.avg_pts_last_5, 1),
            'avg_pts_last_10': round(stats.avg_pts_last_10, 1),
            'std_pts_last_10': round(stats.std_pts_last_10, 1),
        },
        'charts': {
            'dates': game_dates,
            'points': points,
            'minutes': minutes,
            'line': line_value
        }
    })


def format_player_data(item):
    """Форматирование данных игрока для JSON"""
    line = item['line']
    stats = item['stats']
    stability = item['stability']
    trend = item['trend']
    
    # Полные данные по играм (для тултипов)
    games_detail = []
    for g in stats.last_10_games[::-1]:  # Реверс: от старых к новым
        games_detail.append({
            'date': g.get('game_date', ''),
            'matchup': g.get('matchup', ''),
            'pts': g.get('pts', 0),
            'min': round(g.get('min', 0)),
            'reb': g.get('reb', 0),
            'ast': g.get('ast', 0),
            'wl': g.get('wl', '')
        })
    
    return {
        'name': stats.player_name,
        'team': stats.team,
        'line': line.line_points,
        'season_ppg': round(stats.season_ppg, 1),
        'avg_last_5': round(stats.avg_pts_last_5, 1),
        'avg_last_10': round(stats.avg_pts_last_10, 1),
        'std': round(stability.std_pts, 1),
        'cv': round(stability.cv_pts, 2),
        'hit_rate_5': round(stability.hit_rate_last_5 * 100),
        'hit_rate_10': round(stability.hit_rate_last_10 * 100),
        'stability_score': round(stability.stability_score),
        'risk_level': stability.risk_level,
        'trend_direction': trend['pts_direction'],
        'trend_pct': round(trend['pts_trend_pct'], 1),
        'games': [g['pts'] for g in stats.last_10_games][::-1],
        'games_detail': games_detail
    }


def format_value_bet(vb):
    """Форматирование value bet для JSON"""
    return {
        'rank': vb.rank,
        'player': vb.player_name,
        'team': vb.team,
        'opponent': vb.opponent,
        'line': vb.line,
        'bet_type': vb.bet_type.value,
        'model_prob': round(vb.model_prob * 100, 1),
        'implied_prob': round(vb.implied_prob * 100, 1),
        'edge': round(vb.edge_percent, 1),
        'stability_score': round(vb.stability_score),
        'risk_level': vb.risk_level,
        'confidence': round(vb.confidence * 100),
        'reasons': vb.reasons
    }


if __name__ == '__main__':
    print("\n🏀 NBA Value Analyzer - Web Dashboard")
    print("=" * 50)
    print("Открой в браузере: http://localhost:5000")
    print("=" * 50 + "\n")
    
    app.run(debug=True, port=5000)
