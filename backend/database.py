import os
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./apex_ai.db")
_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=_connect_args)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

ROLE_HUMAN = "human"
ROLE_AI = "ai"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(50), nullable=False)
    nickname = Column(String(50), nullable=False, default="")
    avatar = Column(String(255), nullable=False, default="")
    is_vip = Column(Integer, nullable=False, default=0)
    vip_expire_at = Column(DateTime, nullable=True)
    balance = Column(Float, nullable=False, default=0.0)
    is_admin = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False, default="新对话")
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    is_pinned = Column(Integer, nullable=False, default=0, index=True)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


class RechargeOrder(Base):
    __tablename__ = "recharge_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_id = Column(String(50), nullable=False, default="")
    package_name = Column(String(100), nullable=False, default="")
    amount = Column(Float, nullable=False, default=0.0)
    days = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    channel = Column(String(30), nullable=False, default="alipay")
    remark = Column(String(200), nullable=False, default="")
    out_trade_no = Column(String(64), nullable=False, default="", index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class HotTopic(Base):
    __tablename__ = "hot_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rank = Column(Integer, nullable=False, unique=True)
    title = Column(String(200), nullable=False)
    heat = Column(String(20), nullable=False, default="")


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False)
    category = Column(String(30), nullable=False, index=True)
    tag = Column(String(50), nullable=False, default="")
    icon = Column(String(20), nullable=False, default="🔧")
    sort_order = Column(Integer, nullable=False, default=0)
    system_prompt = Column(Text, nullable=False, default="")
    input_placeholder = Column(String(200), nullable=False, default="请输入你的需求…")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(30), nullable=False, index=True, default="全部分类")
    author = Column(String(50), nullable=False, default="宇宙第一小仙女")
    likes = Column(String(20), nullable=False, default="6000+")
    heat = Column(String(20), nullable=False, default="1.2w+")
    icon = Column(String(20), nullable=False, default="🤖")
    system_prompt = Column(Text, nullable=False, default="")
    featured = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)


def _migrate_tool_columns():
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = insp.get_table_names()
    with engine.begin() as conn:
        if "tools" in tables:
            names = {c["name"] for c in insp.get_columns("tools")}
            if "system_prompt" not in names:
                conn.execute(
                    text(
                        "ALTER TABLE tools ADD COLUMN system_prompt TEXT NOT NULL DEFAULT ''"
                    )
                )
            if "input_placeholder" not in names:
                conn.execute(
                    text(
                        "ALTER TABLE tools ADD COLUMN input_placeholder VARCHAR(200) NOT NULL DEFAULT '请输入你的需求…'"
                    )
                )
        if "conversations" in tables:
            cnames = {c["name"] for c in insp.get_columns("conversations")}
            if "is_pinned" not in cnames:
                conn.execute(
                    text(
                        "ALTER TABLE conversations ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0"
                    )
                )
        if "users" in tables:
            unames = {c["name"] for c in insp.get_columns("users")}
            alters = []
            if "is_vip" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN is_vip INTEGER NOT NULL DEFAULT 0")
            if "vip_expire_at" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN vip_expire_at DATETIME")
            if "balance" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN balance FLOAT NOT NULL DEFAULT 0")
            if "is_admin" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            for sql in alters:
                conn.execute(text(sql))
        if "recharge_orders" in tables:
            onames = {c["name"] for c in insp.get_columns("recharge_orders")}
            if "out_trade_no" not in onames:
                conn.execute(
                    text(
                        "ALTER TABLE recharge_orders ADD COLUMN out_trade_no VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )


def init_db():
    Base.metadata.create_all(engine)
    _migrate_tool_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
