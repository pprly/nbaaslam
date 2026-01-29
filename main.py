#!/usr/bin/env python3
"""
NBA Value Betting Analyzer - Main Entry Point
Система анализа value bets для NBA player props

Использование:
    python main.py                  # Демо режим
    python main.py --live           # Реальные данные (требует API ключ)
    python main.py --player "Name"  # Анализ конкретного игрока
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Optional

# Загружаем .env файл
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass

from config import config
from data_fetcher import DataFetcher, generate_demo_data
from stability_analyzer import analyze_player_pool, PlayerFilter, StabilityAnalyzer
from probability_model import ValueDetector, ProbabilityModel

# Опционально: бесплатный режим
try:
    from free_data_fetcher import FreeDataFetcher, ManualLine, run_free_analysis
    FREE_MODE_AVAILABLE = True
except ImportError:
    FREE_MODE_AVAILABLE = False


def print_banner():
    """Выводит баннер приложения"""
    banner = """
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   🏀  NBA VALUE BETTING ANALYZER                                     ║
║                                                                      ║
║   Вероятностная модель для поиска неэффективностей рынка             ║
║   Фокус: стабильность, минуты, usage rate                            ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def run_demo_mode():
    """
    Запуск в демо режиме с сгенерированными данными.
    Полезно для тестирования и демонстрации работы системы.
    """
    print("\n📊 Режим: ДЕМО (сгенерированные данные)")
    print("-" * 50)
    
    # Генерируем демо данные
    print("→ Генерация демо данных...")
    lines, stats = generate_demo_data()
    
    print(f"  ✓ Линий: {len(lines)}")
    print(f"  ✓ Игроков со статистикой: {len(stats)}")
    
    # Анализ пула игроков
    print("\n→ Фильтрация и анализ стабильности...")
    analysis = analyze_player_pool(lines, stats)
    
    print(f"  ✓ Принято к анализу: {analysis['summary']['accepted']}")
    print(f"  ✓ Отклонено: {analysis['summary']['rejected']}")
    print(f"  ✓ Средний stability score: {analysis['summary']['avg_stability']:.1f}")
    
    # Поиск value bets
    print("\n→ Поиск value bets...")
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"])
    
    # Вывод результатов
    print("\n" + detector.format_output(value_bets))
    
    # Детальная статистика
    print_detailed_stats(analysis)


def run_live_mode():
    """
    Запуск с реальными данными из API.
    Требует настроенный ODDS_API_KEY в .env файле.
    """
    print("\n📡 Режим: LIVE (реальные данные)")
    print("-" * 50)
    
    # Проверяем API ключ из окружения
    api_key = os.environ.get('ODDS_API_KEY', '')
    
    if not api_key or api_key == 'твой_ключ_сюда':
        print("\n❌ API ключ не настроен!")
        print("")
        print("Что делать:")
        print("1. Получи бесплатный ключ на https://the-odds-api.com/")
        print("2. Открой файл .env в папке проекта")
        print("3. Замени 'твой_ключ_сюда' на свой ключ")
        print("4. Запусти снова")
        return
    
    # Обновляем конфиг
    config.api.odds_api_key = api_key
    
    fetcher = DataFetcher()
    
    # Получаем предстоящие матчи
    print("\n→ Загрузка предстоящих матчей...")
    games = fetcher.fetch_upcoming_games()
    
    if not games:
        print("  ⚠️ Нет предстоящих матчей в ближайшие 2 дня")
        print("  Попробуй в game day!")
        return
    
    print(f"  ✓ Найдено {len(games)} матчей:")
    for game in games[:5]:  # Показываем первые 5
        print(f"    • {game['away_team']} @ {game['home_team']}")
    
    # Получаем линии на игроков
    print("\n→ Загрузка линий O/U на игроков...")
    lines = fetcher.fetch_player_props()
    
    if not lines:
        print("  ⚠️ Линии не найдены")
        print("  Player props обычно доступны за 24ч до игры")
        return
    
    print(f"  ✓ Загружено {len(lines)} линий")
    
    # Собираем статистику игроков
    print("\n→ Загрузка статистики игроков...")
    stats = {}
    
    for line in lines:
        player_stats = fetcher.fetch_player_stats(line.player_name, line.player_id)
        if player_stats:
            stats[line.player_name] = player_stats
            print(f"  ✓ {line.player_name}")
    
    if not stats:
        print("  ⚠️ Не удалось загрузить статистику")
        return
    
    # Защитные рейтинги команд
    print("\n→ Загрузка защитных рейтингов...")
    team_defenses = fetcher.fetch_team_defense_ratings()
    
    # Анализ
    print("\n→ Анализ пула игроков...")
    analysis = analyze_player_pool(lines, stats)
    
    # Поиск value bets
    print("\n→ Поиск value bets...")
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"], team_defenses)
    
    # Вывод
    print("\n" + detector.format_output(value_bets))


def run_free_mode(lines_file: str = None):
    """
    Запуск с бесплатными данными.
    Статистика: nba_api (бесплатно)
    Линии: ручной ввод или JSON файл
    """
    if not FREE_MODE_AVAILABLE:
        print("\n❌ Бесплатный режим недоступен")
        print("   Установи nba_api: pip install nba_api")
        return
    
    print("\n🆓 Режим: FREE (бесплатные данные)")
    print("-" * 50)
    print("Статистика: nba_api (официальные данные NBA)")
    print("Линии: ручной ввод или JSON файл")
    
    if lines_file:
        print(f"\n→ Загрузка линий из: {lines_file}")
        run_free_analysis(lines_file=lines_file)
    else:
        print("\n💡 Линии можно:")
        print("   1. Ввести вручную (сейчас)")
        print("   2. Загрузить из JSON: python main.py --free --file lines.json")
        print("")
        run_free_analysis()


def analyze_single_player(player_name: str):
    """
    Анализ конкретного игрока.
    """
    print(f"\n🔍 Анализ игрока: {player_name}")
    print("-" * 50)
    
    if not config.api.odds_api_key:
        print("⚠️ ODDS_API_KEY не установлен")
        print("Используем демо данные для демонстрации...\n")
        
        lines, stats = generate_demo_data()
        
        # Ищем игрока в демо данных
        if player_name in stats:
            player_stats = stats[player_name]
            player_line = next((l for l in lines if l.player_name == player_name), None)
        else:
            print(f"❌ Игрок '{player_name}' не найден в демо данных")
            print(f"   Доступные игроки: {', '.join(stats.keys())}")
            return
    else:
        fetcher = DataFetcher()
        
        # Получаем статистику
        player_stats = fetcher.fetch_player_stats(player_name)
        
        if not player_stats:
            print(f"❌ Не удалось найти статистику для '{player_name}'")
            return
        
        # TODO: получить линию для этого игрока
        player_line = None
    
    if player_stats:
        print(f"\n📈 Статистика сезона:")
        print(f"   PPG: {player_stats.season_ppg:.1f}")
        print(f"   MPG: {player_stats.season_mpg:.1f}")
        print(f"   Games: {player_stats.games_played}")
        
        print(f"\n📊 Последние 10 игр:")
        for i, game in enumerate(player_stats.last_10_games[:5], 1):
            print(f"   {i}. {game['game_date']}: {game['pts']} PTS, {game['min']:.0f} MIN")
        
        print(f"\n📉 Метрики:")
        print(f"   Avg L5: {player_stats.avg_pts_last_5:.1f}")
        print(f"   Avg L10: {player_stats.avg_pts_last_10:.1f}")
        print(f"   STD L10: {player_stats.std_pts_last_10:.1f}")
        
        if player_line:
            analyzer = StabilityAnalyzer()
            stability = analyzer.analyze(player_stats, player_line)
            
            print(f"\n🎯 Анализ относительно линии {player_line.line_points}:")
            print(f"   Stability Score: {stability.stability_score:.1f}")
            print(f"   Hit Rate L10: {stability.hit_rate_last_10*100:.0f}%")
            print(f"   Risk Level: {stability.risk_level}")


def print_detailed_stats(analysis: dict):
    """Выводит детальную статистику анализа"""
    print("\n" + "=" * 70)
    print("📋 ДЕТАЛЬНАЯ СТАТИСТИКА")
    print("=" * 70)
    
    for item in analysis["analyzed"]:
        line = item["line"]
        stats = item["stats"]
        stability = item["stability"]
        trend = item["trend"]
        
        print(f"\n▸ {line.player_name} ({stats.team or 'N/A'})")
        print(f"  Линия: O/U {line.line_points}")
        print(f"  Season: {stats.season_ppg:.1f} PPG | {stats.season_mpg:.1f} MPG")
        print(f"  L5 Avg: {stats.avg_pts_last_5:.1f} | L10 Avg: {stats.avg_pts_last_10:.1f}")
        print(f"  STD: {stability.std_pts:.1f} | CV: {stability.cv_pts:.2f}")
        print(f"  Stability: {stability.stability_score:.0f} | Risk: {stability.risk_level}")
        print(f"  Hit Rate: L5={stability.hit_rate_last_5*100:.0f}% | L10={stability.hit_rate_last_10*100:.0f}%")
        print(f"  Trend: PTS {trend['pts_direction']} ({trend['pts_trend_pct']:+.1f}%)")
        print(f"         MIN {trend['min_direction']} ({trend['min_trend_pct']:+.1f}%)")
    
    if analysis["rejected"]:
        print("\n" + "-" * 70)
        print("❌ ОТКЛОНЁННЫЕ ИГРОКИ:")
        for rej in analysis["rejected"]:
            print(f"  • {rej['player']}: {rej['reason']} — {rej['details']}")


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="NBA Value Betting Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py                          # Демо режим
  python main.py --free                   # Бесплатный режим (ручной ввод линий)
  python main.py --free --file lines.json # Бесплатно + линии из файла
  python main.py --live                   # С API (требует ODDS_API_KEY)
  python main.py --player "LeBron James"  # Анализ игрока
  python main.py --config                 # Показать конфигурацию
        """
    )
    
    parser.add_argument(
        "--live", 
        action="store_true",
        help="Использовать реальные данные из API (требует ODDS_API_KEY)"
    )
    
    parser.add_argument(
        "--free",
        action="store_true",
        help="Бесплатный режим: nba_api + ручной ввод линий"
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="JSON файл с линиями (для --free режима)"
    )
    
    parser.add_argument(
        "--player",
        type=str,
        help="Анализ конкретного игрока"
    )
    
    parser.add_argument(
        "--config",
        action="store_true",
        help="Показать текущую конфигурацию"
    )
    
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Количество топ value bets (default: 5)"
    )
    
    args = parser.parse_args()
    
    # Баннер
    print_banner()
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Обновляем конфиг если нужно
    if args.top:
        config.value.top_n_results = args.top
    
    # Показать конфигурацию
    if args.config:
        print("\n⚙️  Конфигурация:")
        print(f"   Min Minutes: {config.filter.min_minutes}")
        print(f"   Min Games: {config.filter.min_games_played}")
        print(f"   Min Edge: {config.value.min_edge_percent}%")
        print(f"   Strong Edge: {config.value.strong_edge_percent}%")
        print(f"   Top N: {config.value.top_n_results}")
        print(f"   API Key: {'✓ Set' if config.api.odds_api_key else '✗ Not set'}")
        return
    
    # Анализ игрока
    if args.player:
        analyze_single_player(args.player)
        return
    
    # Live или Demo или Free режим
    if args.free:
        run_free_mode(args.file)
    elif args.live:
        run_live_mode()
    else:
        run_demo_mode()
    
    print("\n✅ Анализ завершён")


if __name__ == "__main__":
    main()
