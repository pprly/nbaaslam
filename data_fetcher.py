"""
NBA Value Betting Analyzer - Data Fetcher
Сбор данных: коэффициенты, статистика игроков, расписание
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time
import json

from config import config


@dataclass
class PlayerLine:
    """Линия на игрока"""
    player_name: str
    player_id: Optional[str]
    team: str
    opponent: str
    game_id: str
    game_time: datetime
    is_home: bool
    
    # Линия O/U
    line_points: float
    over_odds: float      # Американский формат (-110, +105, etc)
    under_odds: float
    
    # Implied probabilities
    over_implied_prob: float = 0.0
    under_implied_prob: float = 0.0


@dataclass
class PlayerStats:
    """Статистика игрока"""
    player_name: str
    player_id: str
    team: str
    
    # Средние за сезон
    season_ppg: float
    season_mpg: float
    season_usage: float
    games_played: int
    
    # Последние игры
    last_5_games: List[Dict]
    last_10_games: List[Dict]
    
    # Рассчитанные метрики
    avg_pts_last_5: float = 0.0
    avg_pts_last_10: float = 0.0
    std_pts_last_5: float = 0.0
    std_pts_last_10: float = 0.0
    avg_min_last_10: float = 0.0
    
    # Статус
    injury_status: Optional[str] = None
    is_available: bool = True


@dataclass
class TeamDefense:
    """Защитный рейтинг команды"""
    team_name: str
    team_abbr: str
    def_rating: float           # Defensive Rating
    opp_pts_per_game: float     # Очки соперников за игру
    pace: float                 # Темп игры
    
    # По позициям (очки, которые позволяют набирать)
    vs_pg: float = 0.0
    vs_sg: float = 0.0
    vs_sf: float = 0.0
    vs_pf: float = 0.0
    vs_c: float = 0.0


class DataFetcher:
    """Основной класс сбора данных"""
    
    def __init__(self):
        self.config = config
        self.session = requests.Session()
        
    def _american_to_prob(self, odds: float) -> float:
        """Конвертация американских коэффициентов в вероятность"""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    
    def _decimal_to_prob(self, odds: float) -> float:
        """Конвертация десятичных коэффициентов в вероятность"""
        return 1 / odds if odds > 0 else 0
    
    # ========== ODDS API ==========
    
    def fetch_upcoming_games(self) -> List[Dict]:
        """Получить предстоящие матчи NBA"""
        url = "https://api.the-odds-api.com/v4/sports/basketball_nba/events"
        
        params = {
            "apiKey": self.config.api.odds_api_key,
            "dateFormat": "iso"
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            games = resp.json()
            
            # Текущее время UTC (timezone-aware)
            from datetime import timezone
            now = datetime.now(timezone.utc)
            
            upcoming = []
            for game in games:
                # Парсим время игры
                commence_str = game.get("commence_time", "")
                if not commence_str:
                    continue
                
                # Преобразуем в datetime (timezone-aware)
                try:
                    # Формат: 2026-01-30T00:00:00Z
                    game_time = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
                except:
                    continue
                
                # Фильтруем: только игры в ближайшие 2 дня
                if game_time > now and game_time < now + timedelta(days=2):
                    upcoming.append({
                        "id": game["id"],
                        "home_team": game["home_team"],
                        "away_team": game["away_team"],
                        "commence_time": game_time
                    })
            
            print(f"✓ Найдено {len(upcoming)} предстоящих матчей")
            return upcoming
            
        except Exception as e:
            print(f"✗ Ошибка получения матчей: {e}")
            return []
    
    def fetch_player_props(self, game_id: str = None) -> List[PlayerLine]:
        """Получить линии O/U по очкам игроков"""
        
        all_lines = []
        
        # Если передан конкретный game_id - запрашиваем только его
        if game_id:
            game_ids = [game_id]
            games_info = {}
        else:
            # Сначала получаем список игр
            games = self.fetch_upcoming_games()
            if not games:
                print("✗ Нет предстоящих матчей")
                return []
            
            game_ids = [g["id"] for g in games]
            games_info = {g["id"]: g for g in games}
        
        print(f"→ Загрузка player props для {len(game_ids)} матчей...")
        
        # Для каждой игры запрашиваем player props
        for gid in game_ids:
            url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{gid}/odds"
            
            params = {
                "apiKey": self.config.api.odds_api_key,
                "regions": "us",
                "markets": "player_points",
                "oddsFormat": "american",
                "dateFormat": "iso"
            }
            
            try:
                resp = self.session.get(url, params=params, timeout=15)
                
                if resp.status_code == 404:
                    print(f"  ⚠️ Props не найдены для матча {gid}")
                    continue
                    
                if resp.status_code == 422:
                    print(f"  ⚠️ Player props недоступны для матча {gid}")
                    continue
                
                resp.raise_for_status()
                event = resp.json()
                
                # Информация о матче
                home_team = event.get("home_team", "")
                away_team = event.get("away_team", "")
                commence_time = event.get("commence_time", "")
                
                if commence_time:
                    game_time = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                else:
                    game_time = datetime.utcnow()
                
                bookmakers = event.get("bookmakers", [])
                
                if not bookmakers:
                    print(f"  ⚠️ Нет букмекеров для {away_team} @ {home_team}")
                    continue
                
                # Берём первого букмекера (обычно DraftKings или FanDuel)
                bookmaker = bookmakers[0]
                markets = bookmaker.get("markets", [])
                
                for market in markets:
                    if market.get("key") != "player_points":
                        continue
                    
                    outcomes = market.get("outcomes", [])
                    
                    # Группируем по игрокам
                    player_outcomes = {}
                    for outcome in outcomes:
                        player_name = outcome.get("description", "")
                        if not player_name:
                            continue
                            
                        if player_name not in player_outcomes:
                            player_outcomes[player_name] = {}
                        
                        if outcome.get("name") == "Over":
                            player_outcomes[player_name]["over"] = {
                                "line": outcome.get("point", 0),
                                "odds": outcome.get("price", -110)
                            }
                        elif outcome.get("name") == "Under":
                            player_outcomes[player_name]["under"] = {
                                "line": outcome.get("point", 0),
                                "odds": outcome.get("price", -110)
                            }
                    
                    # Создаём PlayerLine для каждого игрока
                    for player_name, pdata in player_outcomes.items():
                        if "over" in pdata and "under" in pdata:
                            over_odds = pdata["over"]["odds"]
                            under_odds = pdata["under"]["odds"]
                            
                            line = PlayerLine(
                                player_name=player_name,
                                player_id=None,
                                team="",  # Определится позже из статистики
                                opponent=f"{away_team} @ {home_team}",
                                game_id=gid,
                                game_time=game_time,
                                is_home=True,  # Упрощение
                                line_points=pdata["over"]["line"],
                                over_odds=over_odds,
                                under_odds=under_odds,
                                over_implied_prob=self._american_to_prob(over_odds),
                                under_implied_prob=self._american_to_prob(under_odds)
                            )
                            all_lines.append(line)
                
                print(f"  ✓ {away_team} @ {home_team}: {len(player_outcomes)} игроков")
                
                # Небольшая пауза между запросами
                time.sleep(0.3)
                
            except Exception as e:
                print(f"  ✗ Ошибка для матча {gid}: {e}")
                continue
        
        print(f"✓ Всего получено {len(all_lines)} линий на игроков")
        return all_lines
    
    # ========== NBA STATS API ==========
    
    def _nba_api_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Запрос к NBA Stats API"""
        url = f"{self.config.api.nba_stats_base_url}/{endpoint}"
        
        try:
            resp = self.session.get(
                url, 
                params=params, 
                headers=self.config.nba_headers,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"✗ NBA API error ({endpoint}): {e}")
            return None
    
    def fetch_player_game_log(self, player_id: str, season: str = "2025-26") -> List[Dict]:
        """Получить game log игрока"""
        params = {
            "PlayerID": player_id,
            "Season": season,
            "SeasonType": "Regular Season"
        }
        
        data = self._nba_api_request("playergamelog", params)
        
        if not data:
            return []
        
        try:
            headers = data["resultSets"][0]["headers"]
            rows = data["resultSets"][0]["rowSet"]
            
            games = []
            for row in rows:
                game = dict(zip(headers, row))
                games.append({
                    "game_date": game.get("GAME_DATE"),
                    "matchup": game.get("MATCHUP"),
                    "pts": game.get("PTS", 0),
                    "min": self._parse_minutes(game.get("MIN", "0")),
                    "fga": game.get("FGA", 0),
                    "fta": game.get("FTA", 0),
                    "reb": game.get("REB", 0),
                    "ast": game.get("AST", 0),
                    "plus_minus": game.get("PLUS_MINUS", 0),
                    "wl": game.get("WL")
                })
            
            return games
            
        except (KeyError, IndexError) as e:
            print(f"✗ Ошибка парсинга game log: {e}")
            return []
    
    def _parse_minutes(self, min_str: str) -> float:
        """Парсинг минут из формата MM:SS или просто числа"""
        if not min_str:
            return 0.0
        
        if isinstance(min_str, (int, float)):
            return float(min_str)
        
        if ":" in str(min_str):
            parts = str(min_str).split(":")
            return float(parts[0]) + float(parts[1]) / 60
        
        try:
            return float(min_str)
        except:
            return 0.0
    
    def fetch_player_stats(self, player_name: str, player_id: str = None) -> Optional[PlayerStats]:
        """Собрать полную статистику игрока"""
        
        # Если нет ID, пытаемся найти
        if not player_id:
            player_id = self._find_player_id(player_name)
            if not player_id:
                print(f"✗ Игрок не найден: {player_name}")
                return None
        
        # Получаем game log
        game_log = self.fetch_player_game_log(player_id)
        
        if len(game_log) < 5:
            print(f"✗ Недостаточно игр для {player_name}: {len(game_log)}")
            return None
        
        # Последние игры
        last_5 = game_log[:5]
        last_10 = game_log[:10]
        
        # Рассчитываем метрики
        pts_5 = [g["pts"] for g in last_5]
        pts_10 = [g["pts"] for g in last_10]
        min_10 = [g["min"] for g in last_10]
        
        # Season averages (по всем играм)
        all_pts = [g["pts"] for g in game_log]
        all_min = [g["min"] for g in game_log]
        
        # Usage rate estimation (упрощённо: FGA + 0.44*FTA per minute)
        usage_data = []
        for g in game_log:
            if g["min"] > 0:
                usage = (g["fga"] + 0.44 * g["fta"]) / g["min"]
                usage_data.append(usage)
        
        avg_usage = np.mean(usage_data) if usage_data else 0.0
        
        stats = PlayerStats(
            player_name=player_name,
            player_id=player_id,
            team="",  # Заполнится позже
            season_ppg=np.mean(all_pts),
            season_mpg=np.mean(all_min),
            season_usage=avg_usage,
            games_played=len(game_log),
            last_5_games=last_5,
            last_10_games=last_10,
            avg_pts_last_5=np.mean(pts_5),
            avg_pts_last_10=np.mean(pts_10),
            std_pts_last_5=np.std(pts_5),
            std_pts_last_10=np.std(pts_10),
            avg_min_last_10=np.mean(min_10)
        )
        
        time.sleep(0.6)  # Rate limiting
        return stats
    
    def _find_player_id(self, player_name: str) -> Optional[str]:
        """Поиск ID игрока по имени"""
        params = {
            "LeagueID": "00",
            "Season": "2025-26",
            "IsOnlyCurrentSeason": 1
        }
        
        data = self._nba_api_request("commonallplayers", params)
        
        if not data:
            return None
        
        try:
            headers = data["resultSets"][0]["headers"]
            rows = data["resultSets"][0]["rowSet"]
            
            name_lower = player_name.lower()
            
            for row in rows:
                player = dict(zip(headers, row))
                display_name = player.get("DISPLAY_FIRST_LAST", "").lower()
                
                if name_lower in display_name or display_name in name_lower:
                    return str(player.get("PERSON_ID"))
            
            # Fuzzy match
            for row in rows:
                player = dict(zip(headers, row))
                display_name = player.get("DISPLAY_FIRST_LAST", "").lower()
                
                name_parts = name_lower.split()
                if all(part in display_name for part in name_parts):
                    return str(player.get("PERSON_ID"))
            
            return None
            
        except (KeyError, IndexError):
            return None
    
    # ========== TEAM DEFENSE ==========
    
    def fetch_team_defense_ratings(self) -> Dict[str, TeamDefense]:
        """Получить защитные рейтинги всех команд"""
        params = {
            "LeagueID": "00",
            "Season": "2025-26",
            "SeasonType": "Regular Season",
            "PerMode": "PerGame"
        }
        
        data = self._nba_api_request("leaguedashteamstats", params)
        
        if not data:
            return {}
        
        try:
            headers = data["resultSets"][0]["headers"]
            rows = data["resultSets"][0]["rowSet"]
            
            teams = {}
            for row in rows:
                team = dict(zip(headers, row))
                
                team_name = team.get("TEAM_NAME", "")
                team_abbr = team.get("TEAM_ABBREVIATION", "")
                
                # Defensive Rating нужен отдельный endpoint
                # Используем OPP_PTS как прокси
                opp_pts = team.get("OPP_PTS", 110)
                
                teams[team_abbr] = TeamDefense(
                    team_name=team_name,
                    team_abbr=team_abbr,
                    def_rating=opp_pts * 1.0,  # Упрощённый DRtg
                    opp_pts_per_game=opp_pts,
                    pace=team.get("PACE", 100)
                )
            
            print(f"✓ Загружены данные по {len(teams)} командам")
            return teams
            
        except (KeyError, IndexError) as e:
            print(f"✗ Ошибка загрузки team defense: {e}")
            return {}
    
    def fetch_injury_report(self) -> Dict[str, str]:
        """Получить статусы травм (упрощённо)"""
        # NBA не имеет публичного API для injury report
        # В продакшене использовать scraping или сторонние API
        return {}


# ========== ДЕМО ДАННЫЕ ==========

def generate_demo_data() -> Tuple[List[PlayerLine], Dict[str, PlayerStats]]:
    """Генерация демо-данных для тестирования"""
    
    # Демо линии
    demo_lines = [
        PlayerLine(
            player_name="Luka Doncic",
            player_id="1629029",
            team="DAL",
            opponent="PHX",
            game_id="demo_001",
            game_time=datetime.utcnow() + timedelta(hours=6),
            is_home=True,
            line_points=32.5,
            over_odds=-115,
            under_odds=-105,
            over_implied_prob=0.535,
            under_implied_prob=0.512
        ),
        PlayerLine(
            player_name="Jayson Tatum",
            player_id="1628369",
            team="BOS",
            opponent="MIA",
            game_id="demo_002",
            game_time=datetime.utcnow() + timedelta(hours=8),
            is_home=True,
            line_points=27.5,
            over_odds=-110,
            under_odds=-110,
            over_implied_prob=0.524,
            under_implied_prob=0.524
        ),
        PlayerLine(
            player_name="Anthony Edwards",
            player_id="1630162",
            team="MIN",
            opponent="DEN",
            game_id="demo_003",
            game_time=datetime.utcnow() + timedelta(hours=10),
            is_home=False,
            line_points=25.5,
            over_odds=-105,
            under_odds=-115,
            over_implied_prob=0.512,
            under_implied_prob=0.535
        ),
        PlayerLine(
            player_name="Shai Gilgeous-Alexander",
            player_id="1628983",
            team="OKC",
            opponent="LAL",
            game_id="demo_004",
            game_time=datetime.utcnow() + timedelta(hours=12),
            is_home=True,
            line_points=30.5,
            over_odds=-120,
            under_odds=100,
            over_implied_prob=0.545,
            under_implied_prob=0.500
        ),
        PlayerLine(
            player_name="Tyrese Haliburton",
            player_id="1630169",
            team="IND",
            opponent="CLE",
            game_id="demo_005",
            game_time=datetime.utcnow() + timedelta(hours=7),
            is_home=False,
            line_points=18.5,
            over_odds=-110,
            under_odds=-110,
            over_implied_prob=0.524,
            under_implied_prob=0.524
        ),
    ]
    
    # Демо статистика
    def create_game_log(base_pts: float, std: float, n: int = 10) -> List[Dict]:
        games = []
        for i in range(n):
            pts = max(0, np.random.normal(base_pts, std))
            games.append({
                "game_date": (datetime.now() - timedelta(days=i*2)).strftime("%Y-%m-%d"),
                "matchup": f"vs TEAM",
                "pts": round(pts),
                "min": round(np.random.normal(34, 3)),
                "fga": round(np.random.normal(18, 4)),
                "fta": round(np.random.normal(6, 2)),
                "reb": round(np.random.normal(7, 2)),
                "ast": round(np.random.normal(5, 2)),
                "plus_minus": round(np.random.normal(3, 8)),
                "wl": np.random.choice(["W", "L"])
            })
        return games
    
    demo_stats = {}
    
    # Luka - высокие очки, высокая дисперсия
    log_luka = create_game_log(33, 7)
    demo_stats["Luka Doncic"] = PlayerStats(
        player_name="Luka Doncic",
        player_id="1629029",
        team="DAL",
        season_ppg=33.2,
        season_mpg=36.5,
        season_usage=0.38,
        games_played=45,
        last_5_games=log_luka[:5],
        last_10_games=log_luka,
        avg_pts_last_5=np.mean([g["pts"] for g in log_luka[:5]]),
        avg_pts_last_10=np.mean([g["pts"] for g in log_luka]),
        std_pts_last_5=np.std([g["pts"] for g in log_luka[:5]]),
        std_pts_last_10=np.std([g["pts"] for g in log_luka]),
        avg_min_last_10=np.mean([g["min"] for g in log_luka])
    )
    
    # Tatum - стабильный
    log_tatum = create_game_log(27, 4)
    demo_stats["Jayson Tatum"] = PlayerStats(
        player_name="Jayson Tatum",
        player_id="1628369",
        team="BOS",
        season_ppg=27.1,
        season_mpg=35.2,
        season_usage=0.32,
        games_played=48,
        last_5_games=log_tatum[:5],
        last_10_games=log_tatum,
        avg_pts_last_5=np.mean([g["pts"] for g in log_tatum[:5]]),
        avg_pts_last_10=np.mean([g["pts"] for g in log_tatum]),
        std_pts_last_5=np.std([g["pts"] for g in log_tatum[:5]]),
        std_pts_last_10=np.std([g["pts"] for g in log_tatum]),
        avg_min_last_10=np.mean([g["min"] for g in log_tatum])
    )
    
    # Edwards - взрывной
    log_ant = create_game_log(26, 6)
    demo_stats["Anthony Edwards"] = PlayerStats(
        player_name="Anthony Edwards",
        player_id="1630162",
        team="MIN",
        season_ppg=26.3,
        season_mpg=35.8,
        season_usage=0.33,
        games_played=47,
        last_5_games=log_ant[:5],
        last_10_games=log_ant,
        avg_pts_last_5=np.mean([g["pts"] for g in log_ant[:5]]),
        avg_pts_last_10=np.mean([g["pts"] for g in log_ant]),
        std_pts_last_5=np.std([g["pts"] for g in log_ant[:5]]),
        std_pts_last_10=np.std([g["pts"] for g in log_ant]),
        avg_min_last_10=np.mean([g["min"] for g in log_ant])
    )
    
    # SGA - очень стабильный
    log_sga = create_game_log(31, 3.5)
    demo_stats["Shai Gilgeous-Alexander"] = PlayerStats(
        player_name="Shai Gilgeous-Alexander",
        player_id="1628983",
        team="OKC",
        season_ppg=31.2,
        season_mpg=34.1,
        season_usage=0.35,
        games_played=50,
        last_5_games=log_sga[:5],
        last_10_games=log_sga,
        avg_pts_last_5=np.mean([g["pts"] for g in log_sga[:5]]),
        avg_pts_last_10=np.mean([g["pts"] for g in log_sga]),
        std_pts_last_5=np.std([g["pts"] for g in log_sga[:5]]),
        std_pts_last_10=np.std([g["pts"] for g in log_sga]),
        avg_min_last_10=np.mean([g["min"] for g in log_sga])
    )
    
    # Haliburton - более низкие очки, стабильный
    log_hali = create_game_log(18, 4)
    demo_stats["Tyrese Haliburton"] = PlayerStats(
        player_name="Tyrese Haliburton",
        player_id="1630169",
        team="IND",
        season_ppg=18.4,
        season_mpg=33.2,
        season_usage=0.26,
        games_played=42,
        last_5_games=log_hali[:5],
        last_10_games=log_hali,
        avg_pts_last_5=np.mean([g["pts"] for g in log_hali[:5]]),
        avg_pts_last_10=np.mean([g["pts"] for g in log_hali]),
        std_pts_last_5=np.std([g["pts"] for g in log_hali[:5]]),
        std_pts_last_10=np.std([g["pts"] for g in log_hali]),
        avg_min_last_10=np.mean([g["min"] for g in log_hali])
    )
    
    return demo_lines, demo_stats


if __name__ == "__main__":
    # Тест демо данных
    lines, stats = generate_demo_data()
    print(f"\nДемо линии: {len(lines)}")
    for line in lines:
        print(f"  {line.player_name}: O/U {line.line_points}")
    
    print(f"\nДемо статистика: {len(stats)} игроков")
    for name, stat in stats.items():
        print(f"  {name}: {stat.season_ppg:.1f} PPG, {stat.std_pts_last_10:.1f} STD")
