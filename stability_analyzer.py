"""
Simplified Stability Analyzer for NBA Value Analyzer v2
"""

import numpy as np
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class StabilityMetrics:
    """Метрики стабильности"""
    player_name: str
    mean_pts: float
    std_pts: float
    cv_pts: float
    stability_score: float
    is_stable: bool
    risk_level: str


class StabilityAnalyzer:
    """Анализ стабильности игрока"""
    
    def analyze(self, stats, line_points: float) -> StabilityMetrics:
        """Рассчитать метрики стабильности"""
        
        pts_data = [g['pts'] for g in stats.last_10_games]
        mean_pts = np.mean(pts_data)
        std_pts = np.std(pts_data)
        cv_pts = std_pts / mean_pts if mean_pts > 0 else 1.0
        
        # Stability score (0-100)
        stability_score = max(0, min(100, (8 - std_pts) / 5 * 100))
        
        is_stable = stability_score >= 60
        
        if stability_score >= 70:
            risk_level = "low"
        elif stability_score >= 50:
            risk_level = "medium"
        else:
            risk_level = "high"
        
        return StabilityMetrics(
            player_name=stats.name,
            mean_pts=mean_pts,
            std_pts=std_pts,
            cv_pts=cv_pts,
            stability_score=stability_score,
            is_stable=is_stable,
            risk_level=risk_level
        )
