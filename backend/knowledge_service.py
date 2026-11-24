"""通用知识库：分类文档 + 简易关键词检索（供对话引用）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import KnowledgeDoc

KB_CATEGORIES = ["使用说明", "业务资料", "常见问题"]

_LEGACY_CAT = {
    "红色文化": "业务资料",
    "景点介绍": "业务资料",
    "历史人文": "业务资料",
    "文旅": "业务资料",
}

_SEED_DOCS = [
    {
        "category": "使用说明",
        "title": "Apex AI 能做什么",
        "content": (
            "Apex AI 是通用智能助手。你可以：在工具箱使用写作、翻译、画图、修图、PPT 等能力；"
            "在地图里查询地点坐标并打点；用行程规划生成一日游建议；在知识库上传资料供对话引用。"
            "左侧可新建对话，个人主页可查看额度与开通 VIP。"
        ),
    },
    {
        "category": "使用说明",
        "title": "地图与定位怎么用",
        "content": (
            "打开「地图」页，登录后提问具体地点（建议带城市），例如「保定西大街在哪」。"
            "系统会检索坐标并在右侧地图标记。也支持问「帮我规划保定一日游」生成分站路线并按序打点。"
        ),
    },
    {
        "category": "常见问题",
        "title": "VIP 有什么用",
        "content": (
            "VIP 提供更高对话/生图额度，并解锁 AI 视频与 PPT 下载。"
            "可在个人主页选择套餐，通过支付宝支付；支付成功后自动开通。"
            "管理员也可在管理后台直接开通。"
        ),
    },
    {
        "category": "常见问题",
        "title": "验证码收不到怎么办",
        "content": (
            "当前登录/找回密码优先使用邮箱验证码（SMTP）。请确认邮箱填写正确，并检查垃圾箱。"
            "若仍为演示模式，页面可能直接回显验证码。短信通道需企业资质，个人环境通常不可用。"
        ),
    },
    {
        "category": "业务资料",
        "title": "知识库如何被对话使用",
        "content": (
            "你在知识库保存的文档，会在用户提问时按关键词自动检索。"
            "命中后内容会注入回答上下文，并在回复末尾标注「已参考知识库」。"
            "适合放产品说明、业务口径、FAQ 等，避免模型凭空编造。"
        ),
    },
]


def migrate_legacy_categories(db: Session) -> None:
    for old, new in _LEGACY_CAT.items():
        db.query(KnowledgeDoc).filter(KnowledgeDoc.category == old).update(
            {KnowledgeDoc.category: new},
            synchronize_session=False,
        )
    db.commit()


def ensure_seed_docs(db: Session) -> None:
    migrate_legacy_categories(db)
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
