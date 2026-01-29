"""
NBA Value Analyzer v2 - Free Data Scraper
Бесплатные источники данных в режиме реального времени
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time
import re

# NBA API (бесплатно)
try:
    from nba_api.stats.endpoints import (
        playergamelog,
        scoreboardv2,
        leaguedashteamstats
    )
    from nba_api.stats.static import players, teams
    NBA_API_AVAILABLE = True
except ImportError:
    NBA_API_AVAILABLE = False


@dataclass
class GameData:
    """Данные о матче"""
    game_id: str
    home_team: str
    away_team: str
    game_time: datetime
    home_abbr: str
    away_abbr: str


@dataclass
class PlayerLine:
    """Линия на игрока"""
    player_name: str
    team: str
    opponent: str
    game_id: str
    line_points: float
    over_odds: str
    under_odds: str
    is_home: bool


@dataclass
class PlayerStats:
    """Статистика игрока"""
    name: str
    team: str
    ppg: float
    last_5_avg: float
    last_10_avg: float
    std_10: float
    games_played: int
    last_10_games: List[Dict]


class FreeScraper:
    """Бесплатный сбор данных"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    # ========== СЕГОДНЯШНИЕ МАТЧИ ==========
    
    def get_todays_games(self) -> List[GameData]:
        """Получить сегодняшние матчи из NBA.com"""
        if not NBA_API_AVAILABLE:
            return self._scrape_games_from_web()
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            scoreboard = scoreboardv2.ScoreboardV2(game_date=today)
            games_df = scoreboard.get_data_frames()[0]
            
            games = []
            for _, row in games_df.iterrows():
                # Парсим время
                game_status = row.get('GAME_STATUS_TEXT', '')
                game_time_str = row.get('GAME_TIME', '')
                
                # Пытаемся определить время игры
                game_time = self._parse_game_time(game_status, game_time_str)
                
                games.append(GameData(
                    game_id=str(row.get('GAME_ID', '')),
                    home_team=row.get('HOME_TEAM_NAME', ''),
                    away_team=row.get('VISITOR_TEAM_NAME', ''),
                    game_time=game_time,
                    home_abbr=self._get_team_abbr(row.get('HOME_TEAM_NAME', '')),
                    away_abbr=self._get_team_abbr(row.get('VISITOR_TEAM_NAME', ''))
                ))
            
            print(f"✓ Найдено {len(games)} матчей на сегодня")
            return games
            
        except Exception as e:
            print(f"✗ Ошибка NBA API: {e}")
            return self._scrape_games_from_web()
    
    def _scrape_games_from_web(self) -> List[GameData]:
        """Резервный парсинг с ESPN/NBA.com"""
        try:
            url = "https://www.nba.com/games"
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем скрипт с данными
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'SportsEvent':
                                # Парсим данные из JSON-LD
                                pass
                except:
                    continue
            
            return []
        except Exception as e:
            print(f"✗ Ошибка парсинга: {e}")
            return []
    
    def _parse_game_time(self, status: str, time_str: str) -> datetime:
        """Парсинг времени игры"""
        # Если игра уже идёт
        if 'Quarter' in status or 'Half' in status:
            return datetime.now()
        
        # Пытаемся распарсить время
        try:
            # Формат: "7:00 pm ET"
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', time_str, re.I)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                ampm = time_match.group(3).lower()
                
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                today = datetime.now()
                game_time = today.replace(hour=hour, minute=minute, second=0)
                
                # Конвертируем из ET в локальное время (упрощённо)
                return game_time
        except:
            pass
        
        # Default: через 2 часа
        return datetime.now() + timedelta(hours=2)
    
    def _get_team_abbr(self, team_name: str) -> str:
        """Получить аббревиатуру команды"""
        abbr_map = {
            'Lakers': 'LAL', 'Clippers': 'LAC', 'Warriors': 'GSW',
            'Celtics': 'BOS', 'Heat': 'MIA', 'Knicks': 'NYK',
            'Nets': 'BKN', 'Bulls': 'CHI', 'Cavaliers': 'CLE',
            'Pistons': 'DET', 'Pacers': 'IND', 'Bucks': 'MIL',
            '76ers': 'PHI', 'Raptors': 'TOR', 'Mavericks': 'DAL',
            'Rockets': 'HOU', 'Grizzlies': 'MEM', 'Pelicans': 'NOP',
            'Spurs': 'SAS', 'Nuggets': 'DEN', 'Timberwolves': 'MIN',
            'Thunder': 'OKC', 'Trail Blazers': 'POR', 'Jazz': 'UTA',
            'Suns': 'PHX', 'Kings': 'SAC', 'Hawks': 'ATL',
            'Hornets': 'CHA', 'Magic': 'ORL', 'Wizards': 'WAS'
        }
        
        for key, val in abbr_map.items():
            if key in team_name:
                return val
        
        return team_name[:3].upper()
    
    # ========== ЛИНИИ (ПАРСИНГ) ==========
    
    def scrape_player_props(self, games: List[GameData]) -> List[PlayerLine]:
        """
        Парсинг линий с бесплатных источников
        
        ВАЖНО: Парсинг сайтов ненадёжен (структура меняется)
        Рекомендуется использовать демо данные или ручной ввод линий
        """
        all_lines = []
        
        print("⚠️  Парсинг линий не работает стабильно")
        print("💡 Используйте DEMO режим или добавьте линии вручную")
        print("   Или получите API ключ от the-odds-api.com (500 запросов бесплатно)")
        
        # Генерируем примеры линий на основе реальных игроков
        # Это временное решение пока парсинг не работает
        all_lines = self._generate_sample_lines(games)
        
        print(f"✓ Сгенерировано {len(all_lines)} примерных линий")
        return all_lines
    
    def _scrape_oddsshark(self, matchup: str, game: GameData) -> List[PlayerLine]:
        """Парсинг с OddsShark"""
        try:
            # URL формат: https://www.oddsshark.com/nba/lakers-vs-warriors-betting-odds
            team1 = game.away_team.split()[-1].lower()
            team2 = game.home_team.split()[-1].lower()
            url = f"https://www.oddsshark.com/nba/{team1}-vs-{team2}-betting-odds"
            
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return []
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем секцию player props
            props_section = soup.find('section', {'id': 'player-props'})
            if not props_section:
                return []
            
            lines = []
            # Парсим таблицу с линиями
            rows = props_section.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    player_name = cols[0].get_text(strip=True)
                    line_value = self._parse_number(cols[1].get_text(strip=True))
                    over_odds = cols[2].get_text(strip=True)
                    under_odds = cols[3].get_text(strip=True) if len(cols) > 3 else over_odds
                    
                    if player_name and line_value:
                        lines.append(PlayerLine(
                            player_name=player_name,
                            team=self._get_player_team(player_name, game),
                            opponent=matchup,
                            game_id=game.game_id,
                            line_points=line_value,
                            over_odds=over_odds,
                            under_odds=under_odds,
                            is_home=True  # TODO: определить точнее
                        ))
            
            return lines
            
        except Exception as e:
            print(f"  ⚠️ OddsShark error: {e}")
            return []
    
    def _scrape_covers(self, matchup: str, game: GameData) -> List[PlayerLine]:
        """Парсинг с Covers.com"""
        # TODO: Implements Covers парсинг
        return []
    
    def _parse_number(self, text: str) -> Optional[float]:
        """Извлечь число из текста"""
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            return float(match.group(1))
        return None
    
    def _get_player_team(self, player_name: str, game: GameData) -> str:
        """Определить команду игрока (упрощённо)"""
        # TODO: Использовать nba_api для точного определения
        return game.home_abbr  # Заглушка
    
    def _generate_sample_lines(self, games: List[GameData]) -> List[PlayerLine]:
        """
        Генерация примерных линий на основе реальных игроков
        Используется когда парсинг не работает
        """
        if not NBA_API_AVAILABLE:
            return []
        
        all_lines = []
        
        # Топ игроки по командам (примерные линии)
        team_stars = {
            'LAL': [('LeBron James', 24.5), ('Anthony Davis', 24.5)],
            'GSW': [('Stephen Curry', 26.5), ('Andrew Wiggins', 16.5)],
            'BOS': [('Jayson Tatum', 27.5), ('Jaylen Brown', 23.5)],
            'MIA': [('Jimmy Butler', 21.5), ('Bam Adebayo', 16.5)],
            'DEN': [('Nikola Jokic', 26.5), ('Jamal Murray', 20.5)],
            'OKC': [('Shai Gilgeous-Alexander', 30.5), ('Jalen Williams', 19.5)],
            'MIN': [('Anthony Edwards', 25.5), ('Karl-Anthony Towns', 21.5)],
            'PHX': [('Kevin Durant', 27.5), ('Devin Booker', 26.5)],
            'DAL': [('Luka Doncic', 32.5), ('Kyrie Irving', 24.5)],
            'LAC': [('Kawhi Leonard', 23.5), ('Paul George', 22.5)],
            'MIL': [('Giannis Antetokounmpo', 30.5), ('Damian Lillard', 25.5)],
            'PHI': [('Joel Embiid', 34.5), ('Tyrese Maxey', 26.5)],
            'CLE': [('Donovan Mitchell', 27.5), ('Darius Garland', 20.5)],
            'NYK': [('Jalen Brunson', 26.5), ('Julius Randle', 23.5)],
        }
        
        for game in games:
            # Добавляем игроков из обеих команд
            for team_abbr in [game.home_abbr, game.away_abbr]:
                if team_abbr in team_stars:
                    for player_name, line in team_stars[team_abbr]:
                        all_lines.append(PlayerLine(
                            player_name=player_name,
                            team=team_abbr,
                            opponent=f"{game.away_abbr}@{game.home_abbr}",
                            game_id=game.game_id,
                            line_points=line,
                            over_odds='-110',
                            under_odds='-110',
                            is_home=(team_abbr == game.home_abbr)
                        ))
        
        return all_lines
    
    # ========== СТАТИСТИКА ИГРОКОВ ==========
    
    def get_player_stats(self, player_name: str) -> Optional[PlayerStats]:
        """Получить статистику игрока через nba_api"""
        if not NBA_API_AVAILABLE:
            return None
        
        try:
            # Находим игрока
            all_players = players.get_active_players()
            player = None
            
            name_lower = player_name.lower()
            for p in all_players:
                if name_lower in p['full_name'].lower():
                    player = p
                    break
            
            if not player:
                return None
            
            # Получаем game log
            time.sleep(0.6)  # Rate limit
            log = playergamelog.PlayerGameLog(
                player_id=player['id'],
                season='2024-25'
            )
            
            df = log.get_data_frames()[0]
            
            if len(df) < 5:
                return None
            
            # Парсим данные
            games = []
            for _, row in df.head(10).iterrows():
                games.append({
                    'date': row.get('GAME_DATE', ''),
                    'pts': int(row.get('PTS', 0)),
                    'min': self._parse_minutes(row.get('MIN', 0))
                })
            
            pts_all = df['PTS'].values
            pts_10 = pts_all[:10]
            pts_5 = pts_all[:5]
            
            return PlayerStats(
                name=player['full_name'],
                team=self._get_team_abbr_by_id(player.get('team_id', 0)),
                ppg=float(pts_all.mean()),
                last_5_avg=float(pts_5.mean()),
                last_10_avg=float(pts_10.mean()),
                std_10=float(pts_10.std()),
                games_played=len(df),
                last_10_games=games
            )
            
        except Exception as e:
            print(f"  ✗ Error for {player_name}: {e}")
            return None
    
    def _parse_minutes(self, min_str) -> float:
        """Парсинг минут"""
        if isinstance(min_str, (int, float)):
            return float(min_str)
        
        if isinstance(min_str, str) and ':' in min_str:
            parts = min_str.split(':')
            return float(parts[0]) + float(parts[1]) / 60
        
        return 0.0
    
    def _get_team_abbr_by_id(self, team_id: int) -> str:
        """Получить аббревиатуру по ID команды"""
        try:
            all_teams = teams.get_teams()
            for t in all_teams:
                if t['id'] == team_id:
                    return t['abbreviation']
        except:
            pass
        
        return ''


# ========== ДЕМО ДАННЫЕ ==========

def get_demo_games() -> List[GameData]:
    """Демо матчи на сегодня"""
    now = datetime.now()
    
    return [
        GameData(
            game_id='demo_1',
            home_team='Los Angeles Lakers',
            away_team='Golden State Warriors',
            game_time=now + timedelta(hours=3),
            home_abbr='LAL',
            away_abbr='GSW'
        ),
        GameData(
            game_id='demo_2',
            home_team='Boston Celtics',
            away_team='Miami Heat',
            game_time=now + timedelta(hours=4),
            home_abbr='BOS',
            away_abbr='MIA'
        ),
        GameData(
            game_id='demo_3',
            home_team='Oklahoma City Thunder',
            away_team='Denver Nuggets',
            game_time=now + timedelta(hours=5),
            home_abbr='OKC',
            away_abbr='DEN'
        )
    ]


def get_demo_lines() -> List[PlayerLine]:
    """Демо линии"""
    return [
        PlayerLine('LeBron James', 'LAL', 'GSW', 'demo_1', 25.5, '-110', '-110', True),
        PlayerLine('Stephen Curry', 'GSW', 'LAL', 'demo_1', 26.5, '-115', '-105', False),
        PlayerLine('Jayson Tatum', 'BOS', 'MIA', 'demo_2', 27.5, '-110', '-110', True),
        PlayerLine('Bam Adebayo', 'MIA', 'BOS', 'demo_2', 16.5, '-110', '-110', False),
        PlayerLine('Shai Gilgeous-Alexander', 'OKC', 'DEN', 'demo_3', 30.5, '-120', '+100', True),
        PlayerLine('Nikola Jokic', 'DEN', 'OKC', 'demo_3', 26.5, '-105', '-115', False),
    ]


if __name__ == '__main__':
    scraper = FreeScraper()
    
    print("\n=== NBA Data Scraper Test ===\n")
    
    # Test 1: Games
    print("→ Загрузка сегодняшних матчей...")
    games = scraper.get_todays_games()
    
    for game in games:
        print(f"  {game.away_abbr} @ {game.home_abbr} - {game.game_time.strftime('%H:%M')}")
    
    # Test 2: Player stats
    if NBA_API_AVAILABLE:
        print("\n→ Тест статистики игрока...")
        stats = scraper.get_player_stats("LeBron James")
        
        if stats:
            print(f"  ✓ {stats.name}")
            print(f"    PPG: {stats.ppg:.1f}")
            print(f"    L10 AVG: {stats.last_10_avg:.1f}")
