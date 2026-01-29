"""
NBA Value Betting Analyzer - Configuration
Конфигурация системы анализа value bets
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class APIConfig:
    """Конфигурация API ключей"""
    # The Odds API (https://the-odds-api.com/)
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    
    # NBA Stats API не требует ключа
    nba_stats_base_url: str = "https://stats.nba.com/stats"
    
    # Basketball Reference
    bbref_base_url: str = "https://www.basketball-reference.com"


@dataclass  
class FilterConfig:
    """Параметры фильтрации игроков"""
    min_minutes: float = 24.0           # Минимум минут за игру
    min_games_played: int = 5           # Минимум сыгранных матчей
    excluded_statuses: tuple = ("Out", "Doubtful", "Questionable")
    
    # Размеры выборок для анализа
    sample_sizes: tuple = (5, 10)       # Последние N игр


@dataclass
class StabilityConfig:
    """Параметры анализа стабильности"""
    # Веса для stability score
    weight_std_dev: float = 0.35        # Вес стандартного отклонения
    weight_minutes_consistency: float = 0.30  # Вес стабильности минут
    weight_usage_consistency: float = 0.20    # Вес стабильности usage rate
    weight_hit_rate: float = 0.15       # Вес % пробития линии
    
    # Пороги
    low_std_threshold: float = 4.0      # Низкое стд. отклонение (очки)
    high_cv_threshold: float = 0.25     # Высокий коэф. вариации (плохо)


@dataclass
class ContextConfig:
    """Контекстные модификаторы"""
    # Позитивные факторы
    home_advantage: float = 0.03        # +3% дома
    weak_defense_bonus: float = 0.05    # +5% vs слабая защита
    high_pace_bonus: float = 0.02       # +2% высокий темп
    
    # Негативные факторы
    back_to_back_penalty: float = -0.04  # -4% back-to-back
    blowout_risk_penalty: float = -0.03  # -3% риск разгрома
    road_penalty: float = -0.02          # -2% на выезде
    
    # Пороги защиты (Defensive Rating)
    weak_defense_threshold: float = 115.0   # DRtg > 115 = слабая защита
    strong_defense_threshold: float = 108.0 # DRtg < 108 = сильная защита


@dataclass
class ValueConfig:
    """Параметры определения value bet"""
    # Минимальное преимущество для value bet
    min_edge_percent: float = 5.0       # 5%
    strong_edge_percent: float = 8.0    # 8% = сильный value
    
    # Confidence thresholds
    min_confidence: float = 0.55        # Мин. уверенность модели
    max_confidence: float = 0.85        # Макс. (избегаем overconfidence)
    
    # Количество выводимых результатов
    top_n_results: int = 5


@dataclass
class ModelConfig:
    """Параметры модели"""
    # Rule-based веса (Phase 1)
    weight_recent_form: float = 0.30    # Последние игры
    weight_season_avg: float = 0.25     # Средние за сезон
    weight_matchup: float = 0.20        # Матчап
    weight_stability: float = 0.15      # Стабильность
    weight_context: float = 0.10        # Контекст (home/away, b2b)
    
    # ML параметры (Phase 2)
    use_ml_model: bool = False          # Включить ML
    ml_model_path: Optional[str] = None


class Config:
    """Главный конфигурационный класс"""
    
    def __init__(self):
        self.api = APIConfig()
        self.filter = FilterConfig()
        self.stability = StabilityConfig()
        self.context = ContextConfig()
        self.value = ValueConfig()
        self.model = ModelConfig()
        
        # HTTP заголовки для NBA Stats API
        self.nba_headers = {
            "Host": "stats.nba.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nba.com/",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
            "Connection": "keep-alive",
        }
    
    def validate(self) -> bool:
        """Проверка конфигурации"""
        errors = []
        
        if not self.api.odds_api_key:
            errors.append("ODDS_API_KEY не установлен (установи через env variable)")
        
        if self.filter.min_minutes < 0:
            errors.append("min_minutes должен быть >= 0")
            
        if self.value.min_edge_percent < 0:
            errors.append("min_edge_percent должен быть >= 0")
        
        if errors:
            print("⚠️ Ошибки конфигурации:")
            for e in errors:
                print(f"  - {e}")
            return False
        
        return True


# Глобальный экземпляр конфигурации
config = Config()
