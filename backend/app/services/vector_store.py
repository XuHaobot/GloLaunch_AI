import os
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

class KnowledgeStore:
    _instance = None

    def __init__(self):
        settings = get_settings()
        os.makedirs(settings.chroma_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name="crossborder_knowledge",
            metadata={"description": "跨境电商规则、选品洞察与SEO词库"}
        )
        self._seed_default_knowledge()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = KnowledgeStore()
        return cls._instance

    def _seed_default_knowledge(self):
        """预置常用的跨境电商平台规范、热销特征与爆款对标知识（幂等：按固定 ID upsert）"""
        documents = [
            "【Amazon Listing 规范】标题控制在 150-200 字符内，首字母大写，严禁包含免运费、热销等促销词。五点描述需前置核心卖点大写标签，如 [PREMIUM LINEN FABRIC]。",
            "【Amazon SEO 规则】Search Terms (Generic Keywords) 限制在 250 字节以内，无需重复标题已出现的词汇，空格分隔，不使用标点符号。",
            "【欧美夏季女装趋势 2026】法式复古碎花、棉麻透气长裙、方领抽褶设计持续走热，主要消费痛点在裙长防走光、面料防缩水与真实尺码对照。",
            "【Shopee 东南亚女装偏好】偏好高饱和明亮色系（姜黄、海浪蓝、碎花），标题前缀需带核心品类热搜词，五点说明强调透气吸汗与包邮赠品政策。",
            "【TikTok Shop 爆款要素】前 3 秒视觉冲击（走动摆动动态效果），短视频脚本突出前后穿着对比与生活场景化（度假、通勤、下午茶）。",
            "【Amazon US 女装爆款标题公式】核心大词前置 + 面料功能词 + 版型细节 + 场景词，如 'BTFBM Women Ruched Bodycon Maxi Dresses Sexy Sleeveless... Wedding Guest Dress'，标题建议 150-200 字符，合理埋入 5-8 个关键词。",
            "【Amazon US 3C 电子爆款标题公式】品类大词 + 核心参数前置（容量/功率/协议） + 兼容性列表 + 场景词，如 'Anker 313 Power Bank 10000mAh USB-C Portable Charger for iPhone 15'，参数前置有助于提升点击率。",
            "【Amazon US 家居百货爆款标题公式】核心功能词前置 + 材质规格 + 适用空间/人群 + 情感收益词，如 'Bamboo Drawer Organizer Expandable Kitchen Utensil Holder'，A+ 页面场景图有助于提升转化率。",
            "【Amazon 美妆个护爆款策略】标题必含成分卖点（Vegan/Cruelty-Free 认证词），首图需展示质地/上脸效果，五点第一条必须是安全性声明（Dermatologist Tested）。",
            "【TikTok Shop 爆款标题钩子】以效果对比与情绪钩子开头（'Finally! / Game Changer'），埋入挑战话题标签，视频前 3 秒需出现使用前后对比。",
            "【Shopee 爆款标题策略】前 15 字符必须命中类目热搜词，叠加马来/泰国本地热词（如 Murah、Free Shipping），标题尾部加颜色/尺码变体词提升长尾流量。",
            "【跨文化文案改写原则】直译会丢失搜索意图：需先提取中文详情页核心卖点，再按目标市场买家搜索习惯重组语言，如中文'显瘦神器'应改写为 'flattering slim fit' 而非字面翻译。",
            "【季节性选品对标】美区夏季（6-8 月）度假风/婚礼宾客装搜索峰值在 5 月底，提前 30 天布局 Listing 可抢占流量红利期。"
        ]
        metadatas = [
            {"category": "platform_rule", "platform": "Amazon", "type": "listing"},
            {"category": "platform_rule", "platform": "Amazon", "type": "seo"},
            {"category": "market_trend", "platform": "US/EU", "type": "fashion"},
            {"category": "market_trend", "platform": "Southeast Asia", "type": "fashion"},
            {"category": "content_strategy", "platform": "TikTok", "type": "video"},
            {"category": "trend_benchmark", "platform": "Amazon", "type": "apparel"},
            {"category": "trend_benchmark", "platform": "Amazon", "type": "electronics"},
            {"category": "trend_benchmark", "platform": "Amazon", "type": "home"},
            {"category": "trend_benchmark", "platform": "Amazon", "type": "beauty"},
            {"category": "trend_benchmark", "platform": "TikTok", "type": "content"},
            {"category": "trend_benchmark", "platform": "Shopee", "type": "seo"},
            {"category": "trend_benchmark", "platform": "Global", "type": "localization"},
            {"category": "trend_benchmark", "platform": "US", "type": "seasonality"}
        ]
        ids = [f"seed_kb_{i}" for i in range(len(documents))]

        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """检索相关的跨境电商知识与规则"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        items = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            for doc, meta, score in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
                items.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": score
                })
        return items

def search_knowledge_base(query: str, top_k: int = 3) -> str:
    """搜索知识库并返回合并文本"""
    kb = KnowledgeStore.get_instance()
    results = kb.search(query, top_k=top_k)
    if not results:
        return ""
    return "\n\n".join([f"- {r['content']}" for r in results])
