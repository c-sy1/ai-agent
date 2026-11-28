import os
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    password = Column(String(255), nullable=False)  # bcrypt 哈希
    nickname = Column(String(50), nullable=False, default="")
    avatar = Column(String(255), nullable=False, default="")
    is_vip = Column(Integer, nullable=False, default=0)
    vip_expire_at = Column(DateTime, nullable=True)
    balance = Column(Float, nullable=False, default=0.0)
    is_admin = Column(Integer, nullable=False, default=0)
    is_disabled = Column(Integer, nullable=False, default=0)
    phone = Column(String(20), nullable=True, unique=True)
    last_login_ip = Column(String(64), nullable=False, default="")
    admin_mfa_until = Column(DateTime, nullable=True)
    quota_chat_extra = Column(Integer, nullable=False, default=0)
    quota_image_extra = Column(Integer, nullable=False, default=0)
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


class UserCoupon(Base):
    """用户持有的优惠券（领取后有有效期，每人每码限用一次）。"""

    __tablename__ = "user_coupons"
    __table_args__ = (
        UniqueConstraint("user_id", "coupon_code", name="uq_user_coupon_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coupon_code = Column(String(40), nullable=False, index=True)
    source = Column(String(40), nullable=False, default="")  # welcome|claim|grant|support
    # 客服赠券等可覆盖模板面额（空则读 COUPON_DEFS）
    label = Column(String(80), nullable=False, default="")
    off_amount = Column(Float, nullable=True)
    min_amount = Column(Float, nullable=True)
    note = Column(String(200), nullable=False, default="")
    claimed_at = Column(DateTime, nullable=False, server_default=func.now())
    expire_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class SupportTicket(Base):
    """用户联系客服工单。"""

    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(40), nullable=False, default="other")  # pay|vip|bug|account|other
    title = Column(String(120), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending")  # pending|processing|resolved|closed
    admin_reply = Column(Text, nullable=False, default="")
    granted_coupon_code = Column(String(40), nullable=False, default="")
    admin_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class AdminOpLog(Base):
    """管理员操作日志（开通/取消 VIP 等）。"""

    __tablename__ = "admin_op_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user_id = Column(Integer, nullable=False, default=0, index=True)
    admin_username = Column(String(50), nullable=False, default="")
    action = Column(String(50), nullable=False, default="", index=True)
    target_user_id = Column(Integer, nullable=True, index=True)
    target_username = Column(String(50), nullable=False, default="")
    detail = Column(String(500), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class UsageDaily(Base):
    """用户每日用量（对话 / 生图），用于免费额度与 VIP 差异。"""

    __tablename__ = "usage_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD UTC
    chat_count = Column(Integer, nullable=False, default=0)
    image_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_usage_daily_user_day"),
        Index("ix_usage_daily_user_day", "user_id", "day"),
    )


class SmsLog(Base):
    """短信记录。kind=code 为验证码，kind=notice 为通知（不含验证码）。"""

    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(120), nullable=False, default="", index=True)  # 也可存 mail:邮箱
    user_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(20), nullable=False, default="code")  # code | notice
    scene = Column(String(40), nullable=False, default="")
    content = Column(String(500), nullable=False, default="")
    code = Column(String(10), nullable=False, default="")
    used = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
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


class ChatFeedback(Base):
    """对话点赞/踩反馈。"""

    __tablename__ = "chat_feedbacks"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_msg_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(Integer, nullable=False, index=True, default=0)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column(String(10), nullable=False)  # up | down
    comment = Column(String(500), nullable=False, default="")
    handle_status = Column(String(20), nullable=False, default="pending")  # pending|processing|resolved
    issue_tag = Column(String(40), nullable=False, default="")  # hallucination|kb_missing|bug|other|""
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class KnowledgeDoc(Base):
    """知识库文档（按分类）。"""

    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(40), nullable=False, index=True)  # 使用说明/业务资料/常见问题
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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
            if "is_disabled" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0")
            if "phone" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN phone VARCHAR(20)")
            if "last_login_ip" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(64) NOT NULL DEFAULT ''")
            if "admin_mfa_until" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN admin_mfa_until DATETIME")
            if "quota_chat_extra" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN quota_chat_extra INTEGER NOT NULL DEFAULT 0")
            if "quota_image_extra" not in unames:
                alters.append("ALTER TABLE users ADD COLUMN quota_image_extra INTEGER NOT NULL DEFAULT 0")
            for sql in alters:
                conn.execute(text(sql))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone ON users(phone)"))
        if "recharge_orders" in tables:
            onames = {c["name"] for c in insp.get_columns("recharge_orders")}
            if "out_trade_no" not in onames:
                conn.execute(
                    text(
                        "ALTER TABLE recharge_orders ADD COLUMN out_trade_no VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )
        if "chat_feedbacks" in tables:
            fnames = {c["name"] for c in insp.get_columns("chat_feedbacks")}
            if "handle_status" not in fnames:
                conn.execute(
                    text(
                        "ALTER TABLE chat_feedbacks ADD COLUMN handle_status VARCHAR(20) NOT NULL DEFAULT 'pending'"
                    )
                )
            if "issue_tag" not in fnames:
                conn.execute(
                    text(
                        "ALTER TABLE chat_feedbacks ADD COLUMN issue_tag VARCHAR(40) NOT NULL DEFAULT ''"
                    )
                )
        if "user_coupons" in tables:
            cnames = {c["name"] for c in insp.get_columns("user_coupons")}
            if "label" not in cnames:
                conn.execute(text("ALTER TABLE user_coupons ADD COLUMN label VARCHAR(80) NOT NULL DEFAULT ''"))
            if "off_amount" not in cnames:
                conn.execute(text("ALTER TABLE user_coupons ADD COLUMN off_amount FLOAT"))
            if "min_amount" not in cnames:
                conn.execute(text("ALTER TABLE user_coupons ADD COLUMN min_amount FLOAT"))
            if "note" not in cnames:
                conn.execute(text("ALTER TABLE user_coupons ADD COLUMN note VARCHAR(200) NOT NULL DEFAULT ''"))


def init_db():
    Base.metadata.create_all(engine)
    _migrate_tool_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
