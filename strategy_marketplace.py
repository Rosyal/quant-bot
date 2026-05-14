"""
策略市场 — 用户分享/发布/订阅策略
差异化功能：社区驱动策略生态
"""
import json
import os
import time
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

from utils.logger import get_logger

logger = get_logger("strategy_market")

MARKETPLACE_DIR = "data/marketplace"


@dataclass
class StrategyListing:
    """策略上架信息"""
    id: str = ""
    name: str = ""
    author: str = ""
    description: str = ""
    strategy_type: str = ""  # ma_cross, rsi, macd, etc.
    params: dict = field(default_factory=dict)
    backtest_summary: dict = field(default_factory=dict)  # profit_pct, sharpe, max_dd
    tags: list = field(default_factory=list)
    rating: float = 0.0
    rating_count: int = 0
    downloads: int = 0
    price: float = 0.0  # 0 = 免费
    created_at: str = ""
    updated_at: str = ""


@dataclass
class StrategyReview:
    """策略评价"""
    listing_id: str = ""
    user: str = ""
    rating: float = 0.0  # 1-5
    comment: str = ""
    created_at: str = ""


class StrategyMarketplace:
    """策略市场服务"""

    def __init__(self, data_dir: str = MARKETPLACE_DIR):
        self.data_dir = data_dir
        self.listings_file = os.path.join(data_dir, "listings.json")
        self.reviews_file = os.path.join(data_dir, "reviews.json")
        self.subscriptions_file = os.path.join(data_dir, "subscriptions.json")
        os.makedirs(data_dir, exist_ok=True)
        self._listings: Dict[str, StrategyListing] = self._load(self.listings_file, StrategyListing)
        self._reviews: List[StrategyReview] = self._load_list(self.reviews_file, StrategyReview)
        self._subscriptions: Dict[str, List[str]] = self._load_simple(self.subscriptions_file)

    def _load(self, path: str, cls) -> Dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: cls(**v) for k, v in data.items()}

    def _load_list(self, path: str, cls) -> List:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [cls(**v) for v in data]

    def _load_simple(self, path: str) -> Dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_listings(self):
        with open(self.listings_file, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in self._listings.items()}, f, indent=2, ensure_ascii=False)

    def _save_reviews(self):
        with open(self.reviews_file, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self._reviews], f, indent=2, ensure_ascii=False)

    def _save_subscriptions(self):
        with open(self.subscriptions_file, "w", encoding="utf-8") as f:
            json.dump(self._subscriptions, f, indent=2, ensure_ascii=False)

    def publish(self, name: str, author: str, strategy_type: str,
                description: str = "", params: dict = None,
                backtest_summary: dict = None, tags: list = None,
                price: float = 0.0) -> StrategyListing:
        """发布策略到市场"""
        sid = hashlib.md5(f"{author}:{name}:{time.time()}".encode()).hexdigest()[:12]
        listing = StrategyListing(
            id=sid, name=name, author=author, description=description,
            strategy_type=strategy_type, params=params or {},
            backtest_summary=backtest_summary or {},
            tags=tags or [], price=price,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._listings[sid] = listing
        self._save_listings()
        logger.info(f"策略已发布: {name} by {author} (id={sid})")
        return listing

    def search(self, query: str = "", strategy_type: str = "",
               sort_by: str = "rating", limit: int = 20) -> List[dict]:
        """搜索策略"""
        results = list(self._listings.values())
        if query:
            q = query.lower()
            results = [r for r in results if q in r.name.lower() or q in r.description.lower()]
        if strategy_type:
            results = [r for r in results if r.strategy_type == strategy_type]
        sort_key = {"rating": lambda x: x.rating, "downloads": lambda x: x.downloads,
                    "newest": lambda x: x.created_at, "profit": lambda x: x.backtest_summary.get("profit_pct", 0)
                    }.get(sort_by, lambda x: x.rating)
        results.sort(key=sort_key, reverse=True)
        return [asdict(r) for r in results[:limit]]

    def get_listing(self, listing_id: str) -> Optional[dict]:
        l = self._listings.get(listing_id)
        return asdict(l) if l else None

    def download(self, listing_id: str, user: str) -> Optional[dict]:
        """下载策略（增加下载计数）"""
        l = self._listings.get(listing_id)
        if not l:
            return None
        l.downloads += 1
        self._subscriptions.setdefault(user, []).append(listing_id)
        self._save_listings()
        self._save_subscriptions()
        return {"strategy_type": l.strategy_type, "params": l.params, "name": l.name}

    def review(self, listing_id: str, user: str, rating: float, comment: str = ""):
        """评价策略"""
        if listing_id not in self._listings:
            return None
        rev = StrategyReview(
            listing_id=listing_id, user=user, rating=rating,
            comment=comment, created_at=datetime.now().isoformat(),
        )
        self._reviews.append(rev)
        # 更新平均评分
        listing_reviews = [r for r in self._reviews if r.listing_id == listing_id]
        avg = sum(r.rating for r in listing_reviews) / len(listing_reviews)
        self._listings[listing_id].rating = round(avg, 1)
        self._listings[listing_id].rating_count = len(listing_reviews)
        self._save_listings()
        self._save_reviews()
        return rev

    def get_trending(self, limit: int = 10) -> List[dict]:
        """热门策略（综合评分 + 下载量）"""
        results = list(self._listings.values())
        results.sort(key=lambda x: x.rating * 0.6 + min(x.downloads, 100) / 100 * 0.4, reverse=True)
        return [asdict(r) for r in results[:limit]]

    def get_user_subscriptions(self, user: str) -> List[dict]:
        """获取用户订阅的策略"""
        ids = self._subscriptions.get(user, [])
        return [asdict(self._listings[i]) for i in ids if i in self._listings]
