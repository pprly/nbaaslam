"""
NBA Value Analyzer v2 - The Odds API Integration
Бесплатно: 500 запросов в месяц
Регистрация: https://the-odds-api.com/
"""

import requests
import os
from datetime import datetime
from typing import List
from data_scraper import PlayerLine, GameData


class OddsAPIFetcher:
    """
    Получение линий через The Odds API
    Бесплатно: 500 запросов/месяц
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('ODDS_API_KEY', '')
        self.base_url = 'https://api.the-odds-api.com/v4'
        
    def fetch_player_props(self) -> List[PlayerLine]:
        """Получить player props линии"""
        
        if not self.api_key:
            print("❌ ODDS_API_KEY не установлен!")
            print("📝 Получите бесплатный ключ:")
            print("   1. Зайдите на https://the-odds-api.com/")
            print("   2. Нажмите 'Get Your Free API Key'")
            print("   3. Введите email → получите ключ")
            print("   4. Установите: export ODDS_API_KEY='ваш_ключ'")
            return []
        
        try:
            # 1. Получаем предстоящие матчи
            events_url = f"{self.base_url}/sports/basketball_nba/events"
            params = {
                'apiKey': self.api_key,
                'dateFormat': 'iso'
            }
            
            resp = requests.get(events_url, params=params, timeout=15)
            resp.raise_for_status()
            events = resp.json()
            
            print(f"✓ Найдено {len(events)} матчей")
            
            # 2. Для каждого матча получаем player props
            all_lines = []
            
            for i, event in enumerate(events[:5], 1):  # Ограничим 5 матчами
                event_id = event['id']
                print(f"  [{i}/5] Загрузка props для {event['home_team']} vs {event['away_team']}...")
                
                props_url = f"{self.base_url}/sports/basketball_nba/events/{event_id}/odds"
                params = {
                    'apiKey': self.api_key,
                    'regions': 'us',
                    'markets': 'player_points',
                    'oddsFormat': 'american'
                }
                
                try:
                    resp = requests.get(props_url, params=params, timeout=15)
                    
                    if resp.status_code == 404:
                        print(f"    ⚠️ Props не найдены")
                        continue
                    
                    resp.raise_for_status()
                    odds_data = resp.json()
                    
                    # Парсим линии
                    lines = self._parse_odds_response(odds_data, event)
                    all_lines.extend(lines)
                    print(f"    ✓ Найдено {len(lines)} линий")
                    
                except Exception as e:
                    print(f"    ✗ Ошибка: {e}")
                    continue
            
            print(f"\n✓ Всего загружено {len(all_lines)} линий")
            print(f"💡 Осталось запросов: проверьте на https://the-odds-api.com/account/")
            
            return all_lines
            
        except Exception as e:
            print(f"✗ Ошибка The Odds API: {e}")
            return []
    
    def _parse_odds_response(self, data: dict, event: dict) -> List[PlayerLine]:
        """Парсинг ответа API"""
        lines = []
        
        home_team = event.get('home_team', '')
        away_team = event.get('away_team', '')
        
        bookmakers = data.get('bookmakers', [])
        if not bookmakers:
            return lines
        
        # Берём первого букмекера
        bookmaker = bookmakers[0]
        markets = bookmaker.get('markets', [])
        
        for market in markets:
            if market.get('key') != 'player_points':
                continue
            
            outcomes = market.get('outcomes', [])
            
            # Группируем по игрокам
            player_data = {}
            for outcome in outcomes:
                player_name = outcome.get('description', '')
                if not player_name:
                    continue
                
                if player_name not in player_data:
                    player_data[player_name] = {}
                
                if outcome.get('name') == 'Over':
                    player_data[player_name]['over'] = {
                        'line': outcome.get('point', 0),
                        'odds': outcome.get('price', -110)
                    }
                elif outcome.get('name') == 'Under':
                    player_data[player_name]['under'] = {
                        'line': outcome.get('point', 0),
                        'odds': outcome.get('price', -110)
                    }
            
            # Создаём PlayerLine
            for player_name, pdata in player_data.items():
                if 'over' in pdata and 'under' in pdata:
                    lines.append(PlayerLine(
                        player_name=player_name,
                        team='',  # Определится позже
                        opponent=f"{away_team} @ {home_team}",
                        game_id=event['id'],
                        line_points=pdata['over']['line'],
                        over_odds=str(pdata['over']['odds']),
                        under_odds=str(pdata['under']['odds']),
                        is_home=True  # Упрощение
                    ))
        
        return lines


def main():
    """Тест"""
    fetcher = OddsAPIFetcher()
    lines = fetcher.fetch_player_props()
    
    if lines:
        print("\n📊 Примеры линий:")
        for line in lines[:5]:
            print(f"  {line.player_name}: O/U {line.line_points}")


if __name__ == '__main__':
    main()
