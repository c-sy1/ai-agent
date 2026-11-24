import json
from pathlib import Path

from auth_service import hash_password, is_hashed_password
from database import (
    Agent,
    ChatMessage,
    Conversation,
    HotTopic,
    SessionLocal,
    Tool,
    User,
    init_db,
    ROLE_AI,
    ROLE_HUMAN,
)
from knowledge_service import ensure_seed_docs

DATA_FILE = Path(__file__).parent / "seed_data.json"


def _tool_from_json(item: dict) -> Tool:
    return Tool(
        name=item["name"],
        description=item["description"],
        category=item["category"],
        tag=item.get("tag", ""),
        icon=item.get("icon", "🔧"),
        sort_order=item.get("sort_order", 0),
        system_prompt=item.get("system_prompt", ""),
        input_placeholder=item.get("input_placeholder", "请输入你的需求…"),
    )


def seed():
    init_db()
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    with SessionLocal() as db:
        if db.query(User).count() == 0:
            demo = User(
                username="xiaoyema",
                email="xiaoyema@apex.ai",
                password=hash_password("123456"),
                nickname="小野马",
                avatar="",
                is_admin=1,
            )
            db.add(demo)
            db.commit()
            db.refresh(demo)
            print(f"演示账号: username=xiaoyema password=123456 user_id={demo.id}")
        else:
            demo = db.query(User).filter(User.username == "xiaoyema").first()
            if demo is not None:
                changed = False
                if int(getattr(demo, "is_admin", 0) or 0) != 1:
                    demo.is_admin = 1
                    changed = True
                # 旧明文密码升级为 bcrypt
                if not is_hashed_password(demo.password or ""):
                    demo.password = hash_password(demo.password or "123456")
                    changed = True
                if changed:
                    db.commit()
            # 批量升级其他明文用户
            for u in db.query(User).all():
                if u.password and not is_hashed_password(u.password):
                    u.password = hash_password(u.password)
            db.commit()

        if db.query(HotTopic).count() == 0:
            for item in raw["hot_topics"]:
                db.add(HotTopic(rank=item["rank"], title=item["title"], heat=item.get("heat", "")))

        if db.query(Tool).count() == 0:
            for item in raw["tools"]:
                db.add(_tool_from_json(item))
        else:
            for item in raw["tools"]:
                row = db.query(Tool).filter(Tool.name == item["name"]).first()
                if row is None:
                    db.add(_tool_from_json(item))
                else:
                    row.description = item["description"]
                    row.system_prompt = item.get("system_prompt", "")
                    row.input_placeholder = item.get(
                        "input_placeholder", "请输入你的需求…"
                    )

        if db.query(Agent).count() == 0:
            for item in raw["agents"]:
                db.add(
                    Agent(
                        name=item["name"],
                        description=item["description"],
                        category=item.get("category", "全部分类"),
                        author=item.get("author", "宇宙第一小仙女"),
                        likes=item.get("likes", "6000+"),
                        heat=item.get("heat", "1.2w+"),
                        icon=item.get("icon", "🤖"),
                        system_prompt=item.get("system_prompt", ""),
                        featured=item.get("featured", 0),
                        sort_order=item.get("sort_order", 0),
                    )
                )

        db.commit()
        ensure_seed_docs(db)

        if demo and db.query(Conversation).filter(Conversation.user_id == demo.id).count() == 0:
            pm_agent = db.query(Agent).filter(Agent.name == "智囊折叠器").first()
            conv = Conversation(
                user_id=demo.id,
                title="产品经理面试合集",
                agent_id=pm_agent.id if pm_agent else None,
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

            db.add(
                ChatMessage(
                    conversation_id=conv.id,
                    user_id=demo.id,
                    role=ROLE_HUMAN,
                    content="产品经理面试合集",
                )
            )
            from chat_service import PM_INTERVIEW_REPLY

            db.add(
                ChatMessage(
                    conversation_id=conv.id,
                    user_id=demo.id,
                    role=ROLE_AI,
                    content=PM_INTERVIEW_REPLY,
                )
            )

            extras = [
                ("今天的天气如何？", "今天以多云为主，气温 18～26℃，适合轻便出行。"),
                ("明天上班穿什么衣服", "建议商务休闲：衬衫 + 休闲西裤 + 轻便外套，舒适得体。"),
            ]
            for title, reply in extras:
                c = Conversation(user_id=demo.id, title=title)
                db.add(c)
                db.commit()
                db.refresh(c)
                db.add(
                    ChatMessage(
                        conversation_id=c.id,
                        user_id=demo.id,
                        role=ROLE_HUMAN,
                        content=title,
                    )
                )
                db.add(
                    ChatMessage(
                        conversation_id=c.id,
                        user_id=demo.id,
                        role=ROLE_AI,
                        content=reply,
                    )
                )

            older = Conversation(user_id=demo.id, title="半年前的学习笔记整理")
            db.add(older)
            db.commit()

        db.commit()
    print("seed 完成")


if __name__ == "__main__":
    seed()
