"""文旅知识库：分类文档 + 简易关键词检索。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import KnowledgeDoc

KB_CATEGORIES = ["红色文化", "景点介绍", "历史人文"]

_SEED_DOCS = [
    {
        "category": "红色文化",
        "title": "狼牙山五勇士",
        "content": (
            "狼牙山位于河北省保定市易县，因八路军五勇士跳崖事迹闻名。"
            "参观时可了解抗战历史，登山需注意安全与景区开放时间。"
            "适合红色研学与党史教育。"
        ),
    },
    {
        "category": "红色文化",
        "title": "保定军校纪念馆",
        "content": (
            "保定军校是中国近代著名军事学堂，纪念馆展示军校沿革与历史人物。"
            "适合了解近代军事教育与爱国主义教育。"
        ),
    },
    {
        "category": "景点介绍",
        "title": "直隶总督署与古莲花池",
        "content": (
            "直隶总督署博物馆位于保定市区，是清代直隶总督办公地遗址。"
            "古莲花池与其相邻，为北方古典园林，适合半日文化游览。"
        ),
    },
    {
        "category": "景点介绍",
        "title": "白洋淀景区",
        "content": (
            "白洋淀地处保定安新一带，以水域风光、荷花芦苇著称。"
            "可乘船游淀，注意季节与天气；门票船班以景区当日公告为准。"
        ),
    },
    {
        "category": "历史人文",
        "title": "保定西大街历史文化街区",
        "content": (
            "西大街是保定古城重要历史文化街区，保留传统街巷肌理与老字号氛围，"
            "适合步行游览、品尝本地小吃，并感受近代城市风貌。"
        ),
    },
]


def ensure_seed_docs(db: Session) -> None:
    if db.query(KnowledgeDoc).count() > 0:
        return
    for item in _SEED_DOCS:
        db.add(
            KnowledgeDoc(
                category=item["category"],
                title=item["title"],
                content=item["content"],
                user_id=0,
            )
        )
    db.commit()


def list_docs(db: Session, category: str | None = None) -> list[KnowledgeDoc]:
    q = db.query(KnowledgeDoc)
    if category and category != "all":
        q = q.filter(KnowledgeDoc.category == category)
    return q.order_by(KnowledgeDoc.id.desc()).all()
