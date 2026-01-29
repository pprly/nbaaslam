"""
NBA Value Analyzer v2 - Flask Backend
Улучшенный веб-сервер с кешированием и live данными
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import os

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# Импорты проекта
from data_scraper import (
    FreeScraper, 
    get_demo_games, 
    get_demo_lines,
    GameData,
    PlayerLine,
    PlayerStats
)
from cache_system import file_cache, session_cache
from stability_analyzer import StabilityAnalyzer
from probability_model import ValueDetector

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Глобальные экземпляры
scraper = FreeScraper()
analyzer = StabilityAnalyzer()
detector = ValueDetector()


# ========== ROUTES ==========

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index_v2.html')


@app.route('/api/demo', methods=['GET'])
def api_demo():
    """Загрузить демо данные"""
    
    # Проверяем кеш
    cached = session_cache.get('demo_data')
    if cached:
        print("✓ Используем кешированные демо данные")
        return jsonify(cached)
    
    try:
        # Генерируем демо данные
        games = get_demo_games()
        lines = get_demo_lines()
        
        # Собираем статистику (демо)
        players_data = []
        for line in lines:
            # Генерируем демо статистику
            import numpy as np
            
            avg_pts = line.line_points + np.random.uniform(-2, 2)
            std_pts = np.random.uniform(3, 7)
            
            player_data = {
                'name': line.player_name,
                'team': line.team,
                'opponent': line.opponent,
                'line': line.line_points,
                'avg_last_10': round(avg_pts, 1),
                'std': round(std_pts, 1),
                'hit_rate': int(np.random.uniform(40, 70)),
                'stability_score': int(np.random.uniform(50, 85)),
                'edge': round(np.random.uniform(3, 12), 1) if np.random.random() > 0.5 else None
            }
            players_data.append(player_data)
        
        # Value bets (топ 5)
        value_bets = sorted(
            [p for p in players_data if p['edge']], 
            key=lambda x: x['edge'], 
            reverse=True
        )[:5]
        
        value_bets_formatted = [{
            'rank': i + 1,
            'player': vb['name'],
            'team': vb['team'],
            'line': vb['line'],
            'bet_type': 'OVER' if np.random.random() > 0.5 else 'UNDER',
            'edge': vb['edge'],
            'model_prob': round(52 + vb['edge'], 1),
            'implied_prob': 52.0,
            'confidence': int(60 + vb['edge'])
        } for i, vb in enumerate(value_bets)]
        
        # Форматируем игры
        games_formatted = [{
            'id': game.game_id,
            'home_team': game.home_team,
            'away_team': game.away_team,
            'home_abbr': game.home_abbr,
            'away_abbr': game.away_abbr,
            'time': game.game_time.isoformat(),
            'live': False,
            'players': [p['name'] for p in players_data if p['team'] in [game.home_abbr, game.away_abbr]][:4]
        } for game in games]
        
        response = {
            'success': True,
            'mode': 'demo',
            'message': f'Загружено {len(games)} матчей (демо режим)',
            'games': games_formatted,
            'players': players_data,
            'value_bets': value_bets_formatted
        }
        
        # Кешируем
        session_cache.set('demo_data', response, ttl_seconds=3600)
        
        return jsonify(response)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/live', methods=['GET'])
def api_live():
    """Загрузить реальные данные"""
    
    # Проверяем кеш (TTL 30 минут)
    cached = file_cache.get('live_data', 'analysis')
    if cached:
        print("✓ Используем кешированные live данные")
        cached['message'] += ' (из кеша)'
        return jsonify(cached)
    
    try:
        # Загружаем сегодняшние матчи
        print("→ Загрузка матчей...")
        games = scraper.get_todays_games()
        
        if not games:
            return jsonify({
                'success': False,
                'error': 'Нет матчей на сегодня. Попробуйте в game day.'
            })
        
        # Проверяем есть ли The Odds API ключ
        odds_api_key = os.environ.get('ODDS_API_KEY', '')
        
        if odds_api_key:
            # Используем The Odds API
            print("  ✓ Используем The Odds API")
            try:
                from odds_api_fetcher import OddsAPIFetcher
                odds_fetcher = OddsAPIFetcher(odds_api_key)
                lines = odds_fetcher.fetch_player_props()
            except Exception as e:
                print(f"  ✗ Ошибка The Odds API: {e}")
                lines = scraper.scrape_player_props(games)
        else:
            # Генерируем примерные линии
            print("  ⚙️  Генерация примерных линий...")
            lines = scraper.scrape_player_props(games)
        
        if not lines:
            return jsonify({
                'success': False,
                'error': 'Линии не найдены. Player props обычно доступны за 24ч до игры.'
            })
        
        # Собираем статистику игроков
        print("→ Загрузка статистики игроков...")
        players_data = []
        stats_cache = {}
        
        for i, line in enumerate(lines):
            print(f"  [{i+1}/{len(lines)}] {line.player_name}...")
            
            # Проверяем кеш статистики
            cached_stats = file_cache.get(f"stats_{line.player_name}", 'stats')
            if cached_stats:
                stats = cached_stats
            else:
                stats = scraper.get_player_stats(line.player_name)
                if stats:
                    file_cache.set(f"stats_{line.player_name}", stats, 'stats')
            
            if stats:
                stats_cache[line.player_name] = stats
                
                # Рассчитываем метрики
                player_data = {
                    'name': stats.name,
                    'team': stats.team,
                    'opponent': line.opponent,
                    'line': line.line_points,
                    'avg_last_10': round(stats.last_10_avg, 1),
                    'std': round(stats.std_10, 1),
                    'hit_rate': int((stats.last_10_avg > line.line_points) * 100),  # Упрощённо
                    'stability_score': int(max(0, 100 - stats.std_10 * 10)),  # Упрощённо
                    'edge': None  # Рассчитается позже
                }
                players_data.append(player_data)
        
        if not players_data:
            return jsonify({
                'success': False,
                'error': 'Не удалось загрузить статистику игроков'
            })
        
        # TODO: Полноценный анализ и value detection
        # Для MVP используем упрощённый расчёт
        
        # Форматируем игры
        games_formatted = [{
            'id': game.game_id,
            'home_team': game.home_team,
            'away_team': game.away_team,
            'home_abbr': game.home_abbr,
            'away_abbr': game.away_abbr,
            'time': game.game_time.isoformat(),
            'live': False,
            'players': [p['name'] for p in players_data if p['team'] in [game.home_abbr, game.away_abbr]][:4]
        } for game in games]
        
        response = {
            'success': True,
            'mode': 'live',
            'message': f'Загружено {len(games)} матчей, {len(players_data)} игроков',
            'games': games_formatted,
            'players': players_data,
            'value_bets': []  # TODO: Implement
        }
        
        # Кешируем на 30 минут
        file_cache.set('live_data', response, 'analysis')
        
        return jsonify(response)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Ошибка загрузки: {str(e)}'
        }), 500


@app.route('/api/player/<player_name>', methods=['GET'])
def api_player_detail(player_name):
    """Детальная информация по игроку"""
    
    # Проверяем кеш
    cached = file_cache.get(f"player_detail_{player_name}", 'stats')
    if cached:
        return jsonify(cached)
    
    try:
        stats = scraper.get_player_stats(player_name)
        
        if not stats:
            return jsonify({
                'success': False,
                'error': f'Игрок {player_name} не найден'
            }), 404
        
        response = {
            'success': True,
            'player': {
                'name': stats.name,
                'team': stats.team,
                'ppg': round(stats.ppg, 1),
                'last_5_avg': round(stats.last_5_avg, 1),
                'last_10_avg': round(stats.last_10_avg, 1),
                'std': round(stats.std_10, 1),
                'games_played': stats.games_played
            },
            'games': stats.last_10_games
        }
        
        # Кешируем
        file_cache.set(f"player_detail_{player_name}", response, 'stats')
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cache/info', methods=['GET'])
def api_cache_info():
    """Информация о кеше"""
    info = file_cache.get_cache_info()
    return jsonify({
        'success': True,
        'cache': info
    })


@app.route('/api/cache/clear', methods=['POST'])
def api_cache_clear():
    """Очистить кеш"""
    cache_type = request.json.get('type') if request.json else None
    
    file_cache.clear(cache_type)
    session_cache.clear()
    
    return jsonify({
        'success': True,
        'message': f'Кеш очищен: {cache_type or "all"}'
    })


# ========== ERROR HANDLERS ==========

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'success': False,
        'error': 'Not found'
    }), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏀 NBA Value Analyzer v2")
    print("="*60)
    print("\n🌐 Откройте: http://localhost:5000")
    print("\n💡 Функции:")
    print("  • Бесплатные live данные (nba_api)")
    print("  • Кеширование (файлы + память)")
    print("  • Фильтрация и сортировка")
    print("  • Уникальный спортивный дизайн")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
