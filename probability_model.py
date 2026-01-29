"""
NBA Value Betting Analyzer - Probability Model & Value Detector
Вероятностная модель и определение value bets
"""

import numpy as np
from scipy import stats as scipy_stats
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from config import config
from data_fetcher import PlayerStats, PlayerLine, TeamDefense
from stability_analyzer import StabilityMetrics


class BetType(Enum):
    OVER = "OVER"
    UNDER = "UNDER"
    NO_VALUE = "NO_VALUE"


@dataclass
class ContextFactors:
    """Контекстные факторы для корректировки"""
    is_home: bool = True
    is_back_to_back: bool = False
    opponent_def_rating: float = 112.0    # Средний DRtg
    opponent_pace: float = 100.0
    blowout_risk: float = 0.0             # 0-1, оценка риска разгрома
    
    # Рассчитанные модификаторы
    total_adjustment: float = 0.0


@dataclass
class ProbabilityResult:
    """Результат вероятностной модели"""
    player_name: str
    line: float
    
    # Вероятности
    p_over: float
    p_under: float
    
    # Implied probabilities от букмекера
    implied_over: float
    implied_under: float
    
    # Edge (преимущество)
    edge_over: float
    edge_under: float
    
    # Рекомендация
    recommended_bet: BetType
    edge_percent: float
    
    # Уверенность модели (0-1)
    confidence: float
    
    # Причины
    reasons: List[str] = field(default_factory=list)


@dataclass
class ValueBet:
    """Структура value bet"""
    player_name: str
    team: str
    opponent: str
    game_time: str
    
    line: float
    bet_type: BetType
    
    # Вероятности
    model_prob: float
    implied_prob: float
    edge_percent: float
    
    # Метаданные
    stability_score: float
    risk_level: str
    confidence: float
    
    # Объяснение
    reasons: List[str]
    
    # Ранг
    rank: int = 0


class ProbabilityModel:
    """
    Rule-based вероятностная модель.
    Рассчитывает P(Over) и P(Under) на основе:
    - Исторических данных игрока
    - Контекстных факторов
    - Стабильности показателей
    """
    
    def __init__(self):
        self.config = config.model
        self.context_config = config.context
    
    def calculate_probability(
        self,
        stats: PlayerStats,
        line: PlayerLine,
        stability: StabilityMetrics,
        context: Optional[ContextFactors] = None,
        team_defense: Optional[TeamDefense] = None
    ) -> ProbabilityResult:
        """
        Главный метод расчёта вероятностей.
        """
        line_value = line.line_points
        
        # 1. Базовая вероятность из исторических данных
        base_p_over = self._calculate_base_probability(stats, line_value)
        
        # 2. Контекстная корректировка
        if context is None:
            context = ContextFactors(is_home=line.is_home)
        
        context_adjustment = self._calculate_context_adjustment(context, team_defense)
        
        # 3. Корректировка на стабильность
        stability_adjustment = self._calculate_stability_adjustment(stability)
        
        # 4. Финальная вероятность
        p_over = np.clip(base_p_over + context_adjustment + stability_adjustment, 0.05, 0.95)
        p_under = 1 - p_over
        
        # 5. Сравнение с implied probability
        implied_over = line.over_implied_prob
        implied_under = line.under_implied_prob
        
        edge_over = p_over - implied_over
        edge_under = p_under - implied_under
        
        # 6. Определяем лучшую ставку
        recommended_bet, edge_percent = self._determine_best_bet(edge_over, edge_under)
        
        # 7. Уверенность модели
        confidence = self._calculate_confidence(stability, abs(edge_percent), stats)
        
        # 8. Причины
        reasons = self._generate_reasons(
            stats, line_value, stability, context, 
            base_p_over, context_adjustment, edge_percent, recommended_bet
        )
        
        return ProbabilityResult(
            player_name=stats.player_name,
            line=line_value,
            p_over=p_over,
            p_under=p_under,
            implied_over=implied_over,
            implied_under=implied_under,
            edge_over=edge_over,
            edge_under=edge_under,
            recommended_bet=recommended_bet,
            edge_percent=edge_percent,
            confidence=confidence,
            reasons=reasons
        )
    
    def _calculate_base_probability(self, stats: PlayerStats, line: float) -> float:
        """
        Рассчитывает базовую вероятность OVER из исторических данных.
        Использует нормальное распределение.
        """
        # Данные последних 10 игр
        pts_data = [g["pts"] for g in stats.last_10_games]
        mean_pts = np.mean(pts_data)
        std_pts = np.std(pts_data)
        
        # Защита от нулевого std
        if std_pts < 1:
            std_pts = 1.0
        
        # P(X > line) где X ~ N(mean, std)
        # Используем survival function (1 - CDF)
        z_score = (line - mean_pts) / std_pts
        p_over = 1 - scipy_stats.norm.cdf(z_score)
        
        # Взвешиваем с данными за 5 игр (более актуальные)
        pts_5 = [g["pts"] for g in stats.last_5_games]
        mean_5 = np.mean(pts_5)
        std_5 = np.std(pts_5) if np.std(pts_5) > 1 else std_pts
        
        z_score_5 = (line - mean_5) / std_5
        p_over_5 = 1 - scipy_stats.norm.cdf(z_score_5)
        
        # Комбинируем: 60% вес на L5, 40% на L10
        combined_p = 0.6 * p_over_5 + 0.4 * p_over
        
        return combined_p
    
    def _calculate_context_adjustment(
        self, 
        context: ContextFactors,
        team_defense: Optional[TeamDefense]
    ) -> float:
        """
        Рассчитывает корректировку вероятности на основе контекста.
        """
        adjustment = 0.0
        
        # Home/Away
        if context.is_home:
            adjustment += self.context_config.home_advantage
        else:
            adjustment += self.context_config.road_penalty
        
        # Back-to-back
        if context.is_back_to_back:
            adjustment += self.context_config.back_to_back_penalty
        
        # Защита соперника
        if team_defense:
            if team_defense.def_rating > self.context_config.weak_defense_threshold:
                adjustment += self.context_config.weak_defense_bonus
            elif team_defense.def_rating < self.context_config.strong_defense_threshold:
                adjustment -= 0.03  # Штраф за сильную защиту
            
            # Корректировка на темп
            pace_diff = (team_defense.pace - 100) / 100  # Нормализуем
            adjustment += pace_diff * self.context_config.high_pace_bonus
        
        # Риск blowout
        if context.blowout_risk > 0.5:
            adjustment += self.context_config.blowout_risk_penalty * context.blowout_risk
        
        context.total_adjustment = adjustment
        return adjustment
    
    def _calculate_stability_adjustment(self, stability: StabilityMetrics) -> float:
        """
        Корректировка на основе стабильности.
        Стабильные игроки → больше уверенности в среднем.
        """
        # Высокий hit rate → увеличиваем вероятность OVER
        if stability.hit_rate_last_10 > 0.7:
            return 0.03
        elif stability.hit_rate_last_10 < 0.3:
            return -0.03
        
        # Высокая дисперсия → уменьшаем уверенность
        if stability.cv_pts > 0.25:
            return -0.02
        
        return 0.0
    
    def _determine_best_bet(
        self, 
        edge_over: float, 
        edge_under: float
    ) -> Tuple[BetType, float]:
        """
        Определяет лучшую ставку на основе edge.
        """
        min_edge = config.value.min_edge_percent / 100
        
        if edge_over >= min_edge and edge_over > edge_under:
            return BetType.OVER, edge_over * 100
        elif edge_under >= min_edge and edge_under > edge_over:
            return BetType.UNDER, edge_under * 100
        else:
            return BetType.NO_VALUE, max(edge_over, edge_under) * 100
    
    def _calculate_confidence(
        self, 
        stability: StabilityMetrics,
        edge_percent: float,
        stats: PlayerStats
    ) -> float:
        """
        Рассчитывает уверенность модели (0-1).
        """
        confidence = 0.5  # Базовая
        
        # Стабильность повышает уверенность
        confidence += (stability.stability_score - 50) / 200  # Max +0.25
        
        # Большая выборка повышает уверенность
        games_factor = min(stats.games_played / 30, 1.0) * 0.1  # Max +0.1
        confidence += games_factor
        
        # Слишком большой edge снижает уверенность (подозрительно)
        if edge_percent > 15:
            confidence -= 0.1
        
        # Низкий CV повышает уверенность
        if stability.cv_pts < 0.15:
            confidence += 0.1
        elif stability.cv_pts > 0.25:
            confidence -= 0.1
        
        return np.clip(confidence, 0.3, 0.9)
    
    def _generate_reasons(
        self,
        stats: PlayerStats,
        line: float,
        stability: StabilityMetrics,
        context: ContextFactors,
        base_p: float,
        context_adj: float,
        edge: float,
        bet_type: BetType
    ) -> List[str]:
        """
        Генерирует объяснения для рекомендации.
        """
        reasons = []
        
        # Историческая статистика
        avg_pts = stability.mean_pts
        if bet_type == BetType.OVER:
            if avg_pts > line:
                reasons.append(f"Среднее ({avg_pts:.1f}) выше линии ({line})")
            
            over_count = int(stability.hit_rate_last_10 * 10)
            if over_count >= 7:
                reasons.append(f"{over_count} из 10 последних игр — OVER")
        
        elif bet_type == BetType.UNDER:
            if avg_pts < line:
                reasons.append(f"Среднее ({avg_pts:.1f}) ниже линии ({line})")
            
            under_count = int((1 - stability.hit_rate_last_10) * 10)
            if under_count >= 7:
                reasons.append(f"{under_count} из 10 последних игр — UNDER")
        
        # Стабильность
        if stability.is_stable:
            reasons.append(f"Высокая стабильность (score: {stability.stability_score:.0f})")
        
        # Минуты
        if stability.mean_minutes >= 34:
            reasons.append(f"Стабильные минуты ({stability.mean_minutes:.0f}+ MPG)")
        
        # Контекст
        if context.is_home and bet_type == BetType.OVER:
            reasons.append("Домашняя игра (+)")
        
        if context.is_back_to_back:
            reasons.append("Back-to-back (−)")
        
        # Low variance
        if stability.cv_pts < 0.18:
            reasons.append("Низкая дисперсия результатов")
        
        return reasons


class ValueDetector:
    """
    Определение value bets.
    Находит ставки, где модель видит преимущество над букмекером.
    """
    
    def __init__(self):
        self.config = config.value
        self.model = ProbabilityModel()
    
    def detect_value_bets(
        self,
        analyzed_players: List[Dict],
        team_defenses: Optional[Dict[str, TeamDefense]] = None
    ) -> List[ValueBet]:
        """
        Анализирует всех игроков и находит value bets.
        """
        value_bets = []
        
        for item in analyzed_players:
            line: PlayerLine = item["line"]
            stats: PlayerStats = item["stats"]
            stability: StabilityMetrics = item["stability"]
            
            # Получаем защиту соперника
            opponent_defense = None
            if team_defenses and line.opponent:
                # Пытаемся найти по аббревиатуре
                for abbr, defense in team_defenses.items():
                    if abbr in line.opponent or line.opponent in defense.team_name:
                        opponent_defense = defense
                        break
            
            # Создаём контекст
            context = ContextFactors(
                is_home=line.is_home,
                is_back_to_back=False,  # TODO: определять из расписания
                opponent_def_rating=opponent_defense.def_rating if opponent_defense else 112.0,
                opponent_pace=opponent_defense.pace if opponent_defense else 100.0
            )
            
            # Рассчитываем вероятности
            prob_result = self.model.calculate_probability(
                stats=stats,
                line=line,
                stability=stability,
                context=context,
                team_defense=opponent_defense
            )
            
            # Проверяем на value
            if prob_result.recommended_bet != BetType.NO_VALUE:
                if prob_result.edge_percent >= self.config.min_edge_percent:
                    if prob_result.confidence >= self.config.min_confidence:
                        
                        value_bet = ValueBet(
                            player_name=stats.player_name,
                            team=stats.team or line.team,
                            opponent=line.opponent,
                            game_time=line.game_time.strftime("%Y-%m-%d %H:%M"),
                            line=line.line_points,
                            bet_type=prob_result.recommended_bet,
                            model_prob=prob_result.p_over if prob_result.recommended_bet == BetType.OVER else prob_result.p_under,
                            implied_prob=prob_result.implied_over if prob_result.recommended_bet == BetType.OVER else prob_result.implied_under,
                            edge_percent=prob_result.edge_percent,
                            stability_score=stability.stability_score,
                            risk_level=stability.risk_level,
                            confidence=prob_result.confidence,
                            reasons=prob_result.reasons
                        )
                        
                        value_bets.append(value_bet)
        
        # Сортируем по edge (убывание)
        value_bets.sort(key=lambda x: x.edge_percent, reverse=True)
        
        # Присваиваем ранги
        for i, vb in enumerate(value_bets):
            vb.rank = i + 1
        
        # Возвращаем топ-N
        return value_bets[:self.config.top_n_results]
    
    def format_output(self, value_bets: List[ValueBet]) -> str:
        """
        Форматирует вывод value bets.
        """
        if not value_bets:
            return "❌ Value bets не найдены в текущем пуле игроков."
        
        output = []
        output.append("=" * 70)
        output.append("🏀 NBA VALUE BETS ANALYSIS")
        output.append("=" * 70)
        output.append("")
        
        for vb in value_bets:
            output.append(f"#{vb.rank}. {vb.player_name}")
            output.append(f"   📊 Линия: O/U {vb.line} очков")
            output.append(f"   🎯 Рекомендация: {vb.bet_type.value}")
            output.append(f"   ")
            output.append(f"   Вероятность (модель): {vb.model_prob*100:.1f}%")
            output.append(f"   Вероятность (букмекер): {vb.implied_prob*100:.1f}%")
            output.append(f"   ⚡ Преимущество (Edge): +{vb.edge_percent:.1f}%")
            output.append(f"   ")
            output.append(f"   📈 Стабильность: {vb.stability_score:.0f}/100 ({vb.risk_level})")
            output.append(f"   🎲 Уверенность модели: {vb.confidence*100:.0f}%")
            output.append(f"   ")
            output.append(f"   Причины:")
            for reason in vb.reasons:
                output.append(f"   • {reason}")
            output.append(f"   ")
            output.append(f"   ⏰ {vb.team} vs {vb.opponent} | {vb.game_time}")
            output.append("-" * 70)
        
        output.append("")
        output.append("⚠️  Это аналитический инструмент, не финансовый совет.")
        output.append("    Всегда учитывай риски и играй ответственно.")
        
        return "\n".join(output)


if __name__ == "__main__":
    # Тест модуля
    from data_fetcher import generate_demo_data
    from stability_analyzer import analyze_player_pool
    
    print("Генерация демо данных...")
    lines, stats = generate_demo_data()
    
    print("Анализ пула игроков...")
    analysis = analyze_player_pool(lines, stats)
    
    print("Поиск value bets...")
    detector = ValueDetector()
    value_bets = detector.detect_value_bets(analysis["analyzed"])
    
    print("\n" + detector.format_output(value_bets))
