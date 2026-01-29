"""
NBA Value Analyzer v2 - Cache System
Кеширование данных для быстрой загрузки
"""

import json
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional
import hashlib


class CacheManager:
    """Менеджер кеша с файловым хранилищем"""
    
    def __init__(self, cache_dir: str = 'cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Время жизни разных типов данных
        self.ttl = {
            'games': timedelta(hours=6),      # Расписание обновляется редко
            'lines': timedelta(hours=1),      # Линии меняются часто
            'stats': timedelta(hours=12),     # Статистика - раз в 12ч
            'analysis': timedelta(minutes=30) # Анализ кешируем на 30 мин
        }
    
    def _get_cache_path(self, key: str, cache_type: str) -> Path:
        """Путь к файлу кеша"""
        # Хешируем ключ для безопасности
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{cache_type}_{key_hash}.pkl"
    
    def get(self, key: str, cache_type: str = 'default') -> Optional[Any]:
        """Получить из кеша"""
        cache_path = self._get_cache_path(key, cache_type)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            
            # Проверяем срок годности
            cached_at = data.get('cached_at')
            if not cached_at:
                return None
            
            ttl = self.ttl.get(cache_type, timedelta(hours=1))
            if datetime.now() - cached_at > ttl:
                # Кеш устарел
                cache_path.unlink()
                return None
            
            return data.get('value')
            
        except Exception as e:
            print(f"⚠️ Cache read error: {e}")
            return None
    
    def set(self, key: str, value: Any, cache_type: str = 'default'):
        """Сохранить в кеш"""
        cache_path = self._get_cache_path(key, cache_type)
        
        try:
            data = {
                'value': value,
                'cached_at': datetime.now(),
                'cache_type': cache_type
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            
        except Exception as e:
            print(f"⚠️ Cache write error: {e}")
    
    def clear(self, cache_type: Optional[str] = None):
        """Очистить кеш"""
        if cache_type:
            # Очистить только определённый тип
            pattern = f"{cache_type}_*.pkl"
            for cache_file in self.cache_dir.glob(pattern):
                cache_file.unlink()
        else:
            # Очистить весь кеш
            for cache_file in self.cache_dir.glob('*.pkl'):
                cache_file.unlink()
        
        print(f"✓ Кеш очищен: {cache_type or 'all'}")
    
    def get_cache_info(self) -> dict:
        """Информация о кеше"""
        info = {
            'total_files': 0,
            'total_size': 0,
            'by_type': {}
        }
        
        for cache_file in self.cache_dir.glob('*.pkl'):
            info['total_files'] += 1
            info['total_size'] += cache_file.stat().st_size
            
            # Определяем тип
            cache_type = cache_file.stem.split('_')[0]
            if cache_type not in info['by_type']:
                info['by_type'][cache_type] = {'count': 0, 'size': 0}
            
            info['by_type'][cache_type]['count'] += 1
            info['by_type'][cache_type]['size'] += cache_file.stat().st_size
        
        # Конвертируем размер в MB
        info['total_size_mb'] = round(info['total_size'] / 1024 / 1024, 2)
        
        for cache_type in info['by_type']:
            size_mb = info['by_type'][cache_type]['size'] / 1024 / 1024
            info['by_type'][cache_type]['size_mb'] = round(size_mb, 2)
        
        return info


class SessionCache:
    """
    In-memory кеш для текущей сессии
    Быстрее файлового кеша, но живёт только в рамках процесса
    """
    
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получить из памяти"""
        return self._cache.get(key)
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Сохранить в память"""
        self._cache[key] = value
        self._timestamps[key] = datetime.now()
    
    def clear(self):
        """Очистить память"""
        self._cache.clear()
        self._timestamps.clear()
    
    def cleanup(self, ttl_seconds: int = 3600):
        """Удалить устаревшие записи"""
        now = datetime.now()
        expired_keys = []
        
        for key, timestamp in self._timestamps.items():
            if (now - timestamp).total_seconds() > ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            del self._timestamps[key]


# Глобальные экземпляры
file_cache = CacheManager()
session_cache = SessionCache()


if __name__ == '__main__':
    # Тест
    cache = CacheManager('test_cache')
    
    # Сохраняем
    cache.set('test_key', {'data': 'test value'}, 'games')
    
    # Загружаем
    value = cache.get('test_key', 'games')
    print(f"Cached value: {value}")
    
    # Информация
    info = cache.get_cache_info()
    print(f"\nCache info: {json.dumps(info, indent=2)}")
    
    # Очистка
    cache.clear()
