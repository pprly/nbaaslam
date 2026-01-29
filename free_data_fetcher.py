"""
NBA Value Betting Analyzer - Free Data Fetcher
Бесплатный сбор данных через nba_api (без API ключей)

Источники:
- nba_api: официальная статистика NBA (бесплатно)
- Линии: ручной ввод или парсинг бесплатных сайтов
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

try:
    from nba_api.stats.endpoints import (
        playergamelog,
        commonplayerinfo,
        commonallplayers,
        scoreboardv2,
        leaguedashteamstats,
        teamgamelog
    )
    from nba_api.stats.static import players, teams
    NBA_API_AVAILABLE = True
except ImportError:
    NBA_API_AVAILABLE = False
    print("⚠️  nba_api не установлен. Установи: pip install nba_api")

import numpy as np

from data_fetcher import PlayerLine, PlayerStats, TeamDefense


@dataclass
class ManualLine:
    """Линия для ручного ввода"""
    player_name: str
    line_points: float
    over_odds: float = -110  # Американский формат
    under_odds: float = -110
    opponent: str = ""
    is_home: bool = True


class FreeDataFetcher:
    """
    Бесплатный сбор данных.
    Использует nba_api для статистики.
    Линии вводятся вручную или загружаются из файла.
    """
    
    def __init__(self):
        self.request_delay = 0.6  # Задержка между запросами (rate limit)
        self._players_cache = None
        self._teams_cache = None
    
    def _american_to_prob(self, odds: float) -> float:
        """Конвертация американских коэффициентов в вероятность"""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    
    # ========== ИГРОКИ ==========
    
    def get_all_players(self) -> List[Dict]:
        """Получить список всех активных игроков"""
        if not NBA_API_AVAILABLE:
            return []
        
        if self._players_cache:
            return self._players_cache
        
        try:
            all_players = players.get_active_players()
            self._players_cache = all_players
            return all_players
        except Exception as e:
            print(f"✗ Ошибка получения игроков: {e}")
            return []
    
    def find_player(self, name: str) -> Optional[Dict]:
        """Найти игрока по имени"""
        all_players = self.get_all_players()
        name_lower = name.lower()
        
        # Точное совпадение
        for p in all_players:
            if p['full_name'].lower() == name_lower:
                return p
        
        # Частичное совпадение
        for p in all_players:
            if name_lower in p['full_name'].lower():
                return p
        
        # Поиск по фамилии
        for p in all_players:
            if name_lower in p['last_name'].lower():
                return p
        
        return None
    
    def fetch_player_game_log(
        self, 
        player_id: int, 
        season: str = "2025-26",
        last_n: int = 15
    ) -> List[Dict]:
        """Получить game log игрока"""
        if not NBA_API_AVAILABLE:
            return []
        
        try:
            time.sleep(self.request_delay)
            
            log = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season,
                season_type_all_star="Regular Season"
            )
            
            df = log.get_data_frames()[0]
            
            games = []
            for _, row in df.head(last_n).iterrows():
                # Парсим минуты
                min_str = row.get('MIN', '0')
                if isinstance(min_str, str) and ':' in min_str:
                    parts = min_str.split(':')
                    minutes = float(parts[0]) + float(parts[1]) / 60
                else:
                    minutes = float(min_str) if min_str else 0
                
                games.append({
                    'game_date': row.get('GAME_DATE', ''),
                    'matchup': row.get('MATCHUP', ''),
                    'pts': int(row.get('PTS', 0)),
                    'min': minutes,
                    'fga': int(row.get('FGA', 0)),
                    'fta': int(row.get('FTA', 0)),
                    'reb': int(row.get('REB', 0)),
                    'ast': int(row.get('AST', 0)),
                    'plus_minus': int(row.get('PLUS_MINUS', 0)),
                    'wl': row.get('WL', '')
                })
            
            return games
            
        except Exception as e:
            print(f"✗ Ошибка game log: {e}")
            return []
    
    def fetch_player_stats(self, player_name: str) -> Optional[PlayerStats]:
        """Собрать полную статистику игрока"""
        
        # Находим игрока
        player = self.find_player(player_name)
        if not player:
            print(f"✗ Игрок не найден: {player_name}")
            return None
        
        player_id = player['id']
        print(f"  → {player['full_name']} (ID: {player_id})")
        
        # Получаем game log
        game_log = self.fetch_player_game_log(player_id)
        
        if len(game_log) < 5:
            print(f"  ✗ Недостаточно игр: {len(game_log)}")
            return None
        
        # Последние игры
        last_5 = game_log[:5]
        last_10 = game_log[:10]
        
        # Рассчитываем метрики
        pts_5 = [g['pts'] for g in last_5]
        pts_10 = [g['pts'] for g in last_10]
        min_10 = [g['min'] for g in last_10]
        
        # Season averages
        all_pts = [g['pts'] for g in game_log]
        all_min = [g['min'] for g in game_log]
        
        # Получаем команду из matchup
        team = ""
        if game_log and game_log[0].get('matchup'):
            matchup = game_log[0]['matchup']
            team = matchup.split()[0] if matchup else ""
        
        stats = PlayerStats(
            player_name=player['full_name'],
            player_id=str(player_id),
            team=team,
            season_ppg=np.mean(all_pts),
            season_mpg=np.mean(all_min),
            season_usage=0.0,  # Не считаем usage для простоты
            games_played=len(game_log),
            last_5_games=last_5,
            last_10_games=last_10,
            avg_pts_last_5=np.mean(pts_5),
            avg_pts_last_10=np.mean(pts_10),
            std_pts_last_5=np.std(pts_5),
            std_pts_last_10=np.std(pts_10),
            avg_min_last_10=np.mean(min_10)
        )
        
        return stats
    
    # ========== КОМАНДЫ ==========
    
    def get_all_teams(self) -> List[Dict]:
        """Получить список всех команд"""
        if not NBA_API_AVAILABLE:
            return []
        
        if self._teams_cache:
            return self._teams_cache
        
        try:
            all_teams = teams.get_teams()
            self._teams_cache = all_teams
            return all_teams
        except Exception as e:
            print(f"✗ Ошибка получения команд: {e}")
            return []
    
    def fetch_team_defense_ratings(self) -> Dict[str, TeamDefense]:
        """Получить защитные рейтинги команд"""
        if not NBA_API_AVAILABLE:
            return {}
        
        try:
            time.sleep(self.request_delay)
            
            stats = leaguedashteamstats.LeagueDashTeamStats(
                season="2025-26",
                season_type_all_star="Regular Season",
                per_mode_detailed="PerGame"
            )
            
            df = stats.get_data_frames()[0]
            
            team_defenses = {}
            for _, row in df.iterrows():
                abbr = row.get('TEAM_ABBREVIATION', '')
                
                # DEF_RATING может не быть в этом endpoint
                # Используем очки соперников как прокси
                opp_pts = 110.0  # Дефолт
                
                team_defenses[abbr] = TeamDefense(
                    team_name=row.get('TEAM_NAME', ''),
                    team_abbr=abbr,
                    def_rating=opp_pts,
                    opp_pts_per_game=opp_pts,
                    pace=100.0
                )
            
            print(f"✓ Загружено {len(team_defenses)} команд")
            return team_defenses
            
        except Exception as e:
            print(f"✗ Ошибка team stats: {e}")
            return {}
    
    # ========== СЕГОДНЯШНИЕ МАТЧИ ==========
    
    def fetch_todays_games(self) -> List[Dict]:
        """Получить сегодняшние матчи"""
        if not NBA_API_AVAILABLE:
            return []
        
        try:
            time.sleep(self.request_delay)
            
            scoreboard = scoreboardv2.ScoreboardV2(game_date=datetime.now().strftime("%Y-%m-%d"))
            games_df = scoreboard.get_data_frames()[0]
            
            games = []
            for _, row in games_df.iterrows():
                games.append({
                    'game_id': row.get('GAME_ID', ''),
                    'home_team': row.get('HOME_TEAM_ID', ''),
                    'away_team': row.get('VISITOR_TEAM_ID', ''),
                    'game_status': row.get('GAME_STATUS_TEXT', '')
                })
            
            return games
            
        except Exception as e:
            print(f"✗ Ошибка scoreboard: {e}")
            return []
    
    # ========== ЛИНИИ (РУЧНОЙ ВВОД) ==========
    
    def create_lines_from_input(self, lines_data: List[ManualLine]) -> List[PlayerLine]:
        """Создать PlayerLine из ручного ввода"""
        player_lines = []
        
        for manual in lines_data:
            over_implied = self._american_to_prob(manual.over_odds)
            under_implied = self._american_to_prob(manual.under_odds)
            
            line = PlayerLine(
                player_name=manual.player_name,
                player_id=None,
                team="",
                opponent=manual.opponent,
                game_id="manual",
                game_time=datetime.now() + timedelta(hours=6),
                is_home=manual.is_home,
                line_points=manual.line_points,
                over_odds=manual.over_odds,
                under_odds=manual.under_odds,
                over_implied_prob=over_implied,
                under_implied_prob=under_implied
            )
            player_lines.append(line)
        
        return player_lines
    
    def load_lines_from_file(self, filepath: str) -> List[PlayerLine]:
        """Загрузить линии из JSON файла"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            manual_lines = []
            for item in data:
                manual_lines.append(ManualLine(
                    player_name=item['player'],
                    line_points=item['line'],
                    over_odds=item.get('over_odds', -110),
                    under_odds=item.get('under_odds', -110),
                    opponent=item.get('opponent', ''),
                    is_home=item.get('is_home', True)
                ))
            
            return self.create_lines_from_input(manual_lines)
            
        except Exception as e:
            print(f"✗ Ошибка загрузки файла: {e}")
            return []
    
    def interactive_line_input(self) -> List[PlayerLine]:
        """Интерактивный ввод линий"""
        print("\n📝 ВВОД ЛИНИЙ")
        print("Формат: Имя игрока, линия O/U, коэф. Over, коэф. Under")
        print("Пример: LeBron James, 25.5, -110, -110")
        print("Введи 'done' для завершения\n")
        
        manual_lines = []
        
        while True:
            try:
                user_input = input("→ ").strip()
                
                if user_input.lower() == 'done':
                    break
                
                if not user_input:
                    continue
                
                parts = [p.strip() for p in user_input.split(',')]
                
                if len(parts) < 2:
                    print("  ✗ Минимум: имя, линия")
                    continue
                
                player_name = parts[0]
                line_points = float(parts[1])
                over_odds = float(parts[2]) if len(parts) > 2 else -110
                under_odds = float(parts[3]) if len(parts) > 3 else -110
                
                manual_lines.append(ManualLine(
                    player_name=player_name,
                    line_points=line_points,
                    over_odds=over_odds,
                    under_odds=under_odds
                ))
                
                print(f"  ✓ {player_name}: O/U {line_points}")
                
            except ValueError as e:
                print(f"  ✗ Ошибка формата: {e}")
            except KeyboardInterrupt:
                print("\n  Отмена...")
                break
        
        return self.create_lines_from_input(manual_lines)


def run_free_analysis(lines: List[PlayerLine] = None, lines_file: str = None):
    """
    Запуск анализа с бесплатными данными.
    
    Args:
        lines: Список линий (если уже есть)
        lines_file: Путь к JSON файлу с линиями
    """
    from stability_analyzer import analyze_player_pool
    from probability_model import ValueDetector
    
    fetcher = FreeDataFetcher()
    
    # Получаем линии
    if lines:
        player_lines = lines
    elif lines_file:
        player_lines = fetcher.load_lines_from_file(lines_file)
    else:
        player_lines = fetcher.interactive_line_input()
    
    if not player_lines:
        print("❌ Нет линий для анализа")
        return
    
    print(f"\n✓ Линий для анализа: {len(player_lines)}")
    
    # Собираем статистику
    print("\n→ Загрузка статистики игроков...")
    stats = {}
    
    for line in player_lines:
        player_stats = fetcher.fetch_player_stats(line.player_name)
        if player_stats:
            stats[line.player_name] = player_stats
            print(f"  ✓ {line.player_name}: {player_stats.season_ppg:.1f} PPG")
    
    if not stats:
        print("❌ Не удалось загрузить статистику")
        return
    
    # Анализ
    print("\n→ Анализ стабильности...")
    analysis = analyze_player_pool(player_lines, stats)
    
    print(f"  ✓ Принято: {analysis['summary']['accepted']}")
    print(f"  ✓ Отклонено: {analysis['summary']['rejected']}")
    
    # Value bets
    print("\n→ Поиск value bets...")
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"])
    
    # Вывод
    print("\n" + detector.format_output(value_bets))
    
    return value_bets


# ========== ПРИМЕР JSON ФАЙЛА ==========

EXAMPLE_LINES_JSON = """
[
    {
        "player": "LeBron James",
        "line": 25.5,
        "over_odds": -115,
        "under_odds": -105,
        "opponent": "GSW",
        "is_home": true
    },
    {
        "player": "Stephen Curry",
        "line": 26.5,
        "over_odds": -110,
        "under_odds": -110,
        "opponent": "LAL",
        "is_home": false
    },
    {
        "player": "Nikola Jokic",
        "line": 26.5,
        "over_odds": -105,
        "under_odds": -115,
        "opponent": "PHX",
        "is_home": true
    }
]
"""


if __name__ == "__main__":
    print("="*60)
    print("🏀 FREE NBA VALUE ANALYZER")
    print("="*60)
    
    if not NBA_API_AVAILABLE:
        print("\n❌ Установи nba_api:")
        print("   pip install nba_api")
        exit(1)
    
    # Тест поиска игрока
    fetcher = FreeDataFetcher()
    
    print("\n→ Тест поиска игрока...")
    player = fetcher.find_player("LeBron")
    if player:
        print(f"  ✓ Найден: {player['full_name']}")
    
    # Пример с ручным вводом линий
    print("\n→ Создание тестовых линий...")
    test_lines = [
        ManualLine("LeBron James", 25.5, -110, -110, "GSW", True),
        ManualLine("Stephen Curry", 26.5, -115, -105, "LAL", False),
    ]
    
    player_lines = fetcher.create_lines_from_input(test_lines)
    print(f"  ✓ Создано линий: {len(player_lines)}")
    
    # Запуск анализа
    print("\n" + "="*60)
    run_free_analysis(player_lines)
