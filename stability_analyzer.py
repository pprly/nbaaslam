"""
NBA Value Betting Analyzer - Player Filter & Stability Analyzer
Фильтрация игроков и анализ стабильности показателей
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from config import config
from data_fetcher import PlayerStats, PlayerLine


@dataclass
class StabilityMetrics:
    """Метрики стабильности игрока"""
    player_name: str
    
    # Базовые метрики
    mean_pts: float
    std_pts: float
    cv_pts: float              # Коэффициент вариации (std/mean)
    
    # Стабильность минут
    mean_minutes: float
    std_minutes: float
    cv_minutes: float
    
    # Hit rates (% пробития линии)
    hit_rate_last_5: float     # % over в последних 5
    hit_rate_last_10: float    # % over в последних 10
    
    # Итоговый score
    stability_score: float     # 0-100, выше = стабильнее
    
    # Флаги
    is_stable: bool
    risk_level: str            # "low", "medium", "high"


class PlayerFilter:
    """Фильтрация игроков по критериям допуска"""
    
    def __init__(self):
        self.config = config.filter
    
    def filter_players(
        self, 
        lines: List[PlayerLine], 
        stats: Dict[str, PlayerStats],
        injury_report: Dict[str, str] = None
    ) -> Tuple[List[PlayerLine], List[Dict]]:
        """
        Фильтрует игроков по критериям допуска.
        Возвращает (допущенные линии, причины исключения)
        """
        accepted = []
        rejected = []
        
        for line in lines:
            player_name = line.player_name
            
            # Проверяем наличие статистики
            if player_name not in stats:
                rejected.append({
                    "player": player_name,
                    "reason": "Нет статистики",
                    "details": "Игрок не найден в базе данных"
                })
                continue
            
            player_stats = stats[player_name]
            
            # Проверка минут
            if player_stats.avg_min_last_10 < self.config.min_minutes:
                rejected.append({
                    "player": player_name,
                    "reason": "Мало минут",
                    "details": f"Avg MIN: {player_stats.avg_min_last_10:.1f} < {self.config.min_minutes}"
                })
                continue
            
            # Проверка количества игр
            if player_stats.games_played < self.config.min_games_played:
                rejected.append({
                    "player": player_name,
                    "reason": "Мало игр",
                    "details": f"Игр: {player_stats.games_played} < {self.config.min_games_played}"
                })
                continue
            
            # Проверка статуса травмы
            if injury_report and player_name in injury_report:
                status = injury_report[player_name]
                if status in self.config.excluded_statuses:
                    rejected.append({
                        "player": player_name,
                        "reason": "Травма/статус",
                        "details": f"Статус: {status}"
                    })
                    continue
            
            # Проверка доступности
            if not player_stats.is_available:
                rejected.append({
                    "player": player_name,
                    "reason": "Недоступен",
                    "details": player_stats.injury_status or "Неизвестная причина"
                })
                continue
            
            # Игрок прошёл фильтр
            accepted.append(line)
        
        return accepted, rejected


class StabilityAnalyzer:
    """Анализ стабильности показателей игрока"""
    
    def __init__(self):
        self.config = config.stability
    
    def analyze(self, stats: PlayerStats, line: PlayerLine) -> StabilityMetrics:
        """
        Рассчитывает метрики стабильности для игрока относительно линии.
        """
        # Базовые статистики очков
        pts_data = [g["pts"] for g in stats.last_10_games]
        mean_pts = np.mean(pts_data)
        std_pts = np.std(pts_data)
        cv_pts = std_pts / mean_pts if mean_pts > 0 else 1.0
        
        # Статистики минут
        min_data = [g["min"] for g in stats.last_10_games]
        mean_min = np.mean(min_data)
        std_min = np.std(min_data)
        cv_min = std_min / mean_min if mean_min > 0 else 1.0
        
        # Hit rates относительно текущей линии
        line_value = line.line_points
        
        pts_5 = [g["pts"] for g in stats.last_5_games]
        pts_10 = [g["pts"] for g in stats.last_10_games]
        
        hit_rate_5 = sum(1 for p in pts_5 if p > line_value) / len(pts_5)
        hit_rate_10 = sum(1 for p in pts_10 if p > line_value) / len(pts_10)
        
        # Рассчитываем stability score
        stability_score = self._calculate_stability_score(
            std_pts=std_pts,
            cv_pts=cv_pts,
            cv_min=cv_min,
            hit_rate=hit_rate_10
        )
        
        # Определяем уровень риска
        risk_level = self._determine_risk_level(cv_pts, std_pts, stability_score)
        
        return StabilityMetrics(
            player_name=stats.player_name,
            mean_pts=mean_pts,
            std_pts=std_pts,
            cv_pts=cv_pts,
            mean_minutes=mean_min,
            std_minutes=std_min,
            cv_minutes=cv_min,
            hit_rate_last_5=hit_rate_5,
            hit_rate_last_10=hit_rate_10,
            stability_score=stability_score,
            is_stable=stability_score >= 60,
            risk_level=risk_level
        )
    
    def _calculate_stability_score(
        self,
        std_pts: float,
        cv_pts: float,
        cv_min: float,
        hit_rate: float
    ) -> float:
        """
        Рассчитывает итоговый stability score (0-100).
        Выше = стабильнее.
        """
        score = 0.0
        
        # 1. Компонент стандартного отклонения (35%)
        # Низкий STD = хорошо
        # Нормализуем: STD 3 = 100, STD 8 = 0
        std_component = max(0, min(100, (8 - std_pts) / 5 * 100))
        score += std_component * self.config.weight_std_dev
        
        # 2. Компонент стабильности минут (30%)
        # Низкий CV минут = хорошо
        # CV 0.05 = 100, CV 0.20 = 0
        min_component = max(0, min(100, (0.20 - cv_min) / 0.15 * 100))
        score += min_component * self.config.weight_minutes_consistency
        
        # 3. Компонент CV очков (20%)
        # Низкий CV = хорошо
        # CV 0.10 = 100, CV 0.30 = 0
        cv_component = max(0, min(100, (0.30 - cv_pts) / 0.20 * 100))
        score += cv_component * self.config.weight_usage_consistency
        
        # 4. Компонент hit rate (15%)
        # Hit rate показывает насколько часто пробивается линия
        # 50% = нейтрально (50 баллов), 80%+ = отлично
        hit_component = hit_rate * 100
        score += hit_component * self.config.weight_hit_rate
        
        return round(score, 1)
    
    def _determine_risk_level(
        self, 
        cv_pts: float, 
        std_pts: float,
        stability_score: float
    ) -> str:
        """Определяет уровень риска ставки"""
        
        if stability_score >= 70 and cv_pts < 0.20:
            return "low"
        elif stability_score >= 50 and cv_pts < 0.25:
            return "medium"
        else:
            return "high"
    
    def get_trend(self, stats: PlayerStats) -> Dict:
        """
        Анализирует тренд показателей игрока.
        Сравнивает последние 5 игр с последними 10.
        """
        pts_5 = [g["pts"] for g in stats.last_5_games]
        pts_10 = [g["pts"] for g in stats.last_10_games]
        
        avg_5 = np.mean(pts_5)
        avg_10 = np.mean(pts_10)
        
        min_5 = [g["min"] for g in stats.last_5_games]
        min_10 = [g["min"] for g in stats.last_10_games]
        
        avg_min_5 = np.mean(min_5)
        avg_min_10 = np.mean(min_10)
        
        # Тренд очков
        pts_trend_pct = (avg_5 - avg_10) / avg_10 * 100 if avg_10 > 0 else 0
        
        # Тренд минут
        min_trend_pct = (avg_min_5 - avg_min_10) / avg_min_10 * 100 if avg_min_10 > 0 else 0
        
        # Определяем направление
        if pts_trend_pct > 5:
            pts_direction = "up"
        elif pts_trend_pct < -5:
            pts_direction = "down"
        else:
            pts_direction = "stable"
        
        if min_trend_pct > 3:
            min_direction = "up"
        elif min_trend_pct < -3:
            min_direction = "down"
        else:
            min_direction = "stable"
        
        return {
            "pts_avg_5": avg_5,
            "pts_avg_10": avg_10,
            "pts_trend_pct": pts_trend_pct,
            "pts_direction": pts_direction,
            "min_avg_5": avg_min_5,
            "min_avg_10": avg_min_10,
            "min_trend_pct": min_trend_pct,
            "min_direction": min_direction
        }


def analyze_player_pool(
    lines: List[PlayerLine],
    stats: Dict[str, PlayerStats],
    injury_report: Dict[str, str] = None
) -> Dict:
    """
    Полный анализ пула игроков.
    Возвращает структурированный результат.
    """
    # Фильтрация
    player_filter = PlayerFilter()
    accepted_lines, rejected = player_filter.filter_players(lines, stats, injury_report)
    
    # Анализ стабильности
    stability_analyzer = StabilityAnalyzer()
    
    analysis_results = []
    
    for line in accepted_lines:
        player_stats = stats[line.player_name]
        
        # Метрики стабильности
        stability = stability_analyzer.analyze(player_stats, line)
        
        # Тренд
        trend = stability_analyzer.get_trend(player_stats)
        
        analysis_results.append({
            "line": line,
            "stats": player_stats,
            "stability": stability,
            "trend": trend
        })
    
    # Сортируем по stability score
    analysis_results.sort(key=lambda x: x["stability"].stability_score, reverse=True)
    
    return {
        "analyzed": analysis_results,
        "rejected": rejected,
        "summary": {
            "total_lines": len(lines),
            "accepted": len(accepted_lines),
            "rejected": len(rejected),
            "avg_stability": np.mean([r["stability"].stability_score for r in analysis_results]) if analysis_results else 0
        }
    }


if __name__ == "__main__":
    # Тест
    from data_fetcher import generate_demo_data
    
    lines, stats = generate_demo_data()
    
    result = analyze_player_pool(lines, stats)
    
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ АНАЛИЗА")
    print("="*60)
    
    print(f"\nСводка:")
    print(f"  Всего линий: {result['summary']['total_lines']}")
    print(f"  Принято: {result['summary']['accepted']}")
    print(f"  Отклонено: {result['summary']['rejected']}")
    print(f"  Средний stability score: {result['summary']['avg_stability']:.1f}")
    
    print("\n" + "-"*60)
    print("АНАЛИЗ ИГРОКОВ:")
    print("-"*60)
    
    for item in result["analyzed"]:
        line = item["line"]
        stability = item["stability"]
        trend = item["trend"]
        
        print(f"\n{line.player_name}")
        print(f"  Линия: O/U {line.line_points}")
        print(f"  Stability Score: {stability.stability_score:.1f} ({stability.risk_level})")
        print(f"  Mean PTS: {stability.mean_pts:.1f} ± {stability.std_pts:.1f}")
        print(f"  CV: {stability.cv_pts:.2f}")
        print(f"  Hit Rate L10: {stability.hit_rate_last_10*100:.0f}%")
        print(f"  Trend: {trend['pts_direction']} ({trend['pts_trend_pct']:+.1f}%)")
