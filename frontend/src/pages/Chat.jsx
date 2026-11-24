import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, getSession } from "../api";
import ChatFooter from "../components/ChatFooter";
import MessageFeedback from "../components/MessageFeedback";
import RichContent from "../components/RichContent";

function HistoryRow({
  item,
  active,
  editing,
  onSelect,
  onStartRename,
  onSaveRename,
  onCancelRename,
  onPin,
  onDelete,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState(item.title);
  const inputRef = useRef(null);

  useEffect(() => {
    setDraft(item.title);
  }, [item.title]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  if (editing) {
    return (
      <div className="history-item editing" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="history-rename-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSaveRename(item.id, draft);
            if (e.key === "Escape") onCancelRename();
          }}
          onBlur={() => onSaveRename(item.id, draft)}
        />
      </div>
    );
  }

  return (
    <div
      className={`history-item${active ? " active" : ""}${item.is_pinned ? " pinned" : ""}`}
      onClick={() => onSelect(item.id)}
    >
      <span className="history-item-title">
        {item.is_pinned && <span className="history-pin-mark">📌</span>}
        {item.title}
      </span>
      <button
        type="button"
        className="history-item-more"
        aria-label="更多"
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
        }}
      >
        ⋮
      </button>
      {menuOpen && (
        <div className="history-menu" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onStartRename(item.id);
            }}
          >
            重命名
          </button>
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onPin(item);
            }}
          >
            {item.is_pinned ? "取消置顶" : "置顶"}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => {
              setMenuOpen(false);
              onDelete(item);
            }}
          >
            删除
          </button>
        </div>
      )}
    </div>
  );
}

export default function Chat() {
  const { conversationId } = useParams();
  const cid = conversationId ? Number(conversationId) : null;
  const user = getSession();
  const userId = user?.user_id;
  const navigate = useNavigate();
  const [groups, setGroups] = useState({
    pinned: [],
    recent_month: [],
    recent_half_year: [],
  });
  const [messages, setMessages] = useState([]);
  const [editingId, setEditingId] = useState(null);

  const loadHistory = useCallback(async () => {
    if (!userId) return;
    try {
      const conv = await api.conversations(userId);
      setGroups({
        pinned: conv.data.pinned || [],
        recent_month: conv.data.recent_month || [],
        recent_half_year: conv.data.recent_half_year || [],
      });
    } catch (e) {
      alert(e.message || "加载对话列表失败");
    }
  }, [userId]);

  const loadMessages = useCallback(async () => {
    if (!userId || !cid) {
      setMessages([]);
      return;
    }
    const res = await api.messages(cid, userId);
    setMessages(res.data);
  }, [userId, cid]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  const onSent = async () => {
    await loadHistory();
    await loadMessages();
  };

  const exportTxt = () => {
    if (!messages.length) {
      alert("当前没有可导出的消息");
      return;
    }
    const lines = messages.map((m) => {
      const who = m.role === "human" ? "我" : "AI";
      const body = String(m.content || "")
        .replace(/\[\[map:[^\]]+\]\]/g, "")
        .replace(/\[\[video:[^\]]+\]\]/g, "[视频]")
        .trim();
      return `【${who}】\n${body}\n`;
    });
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `apex-chat-${cid || "new"}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const selectConv = (id) => navigate(`/chat/${id}`);

  const handleSaveRename = async (id, title) => {
    setEditingId(null);
    const t = title.trim();
    if (!t) return;
    try {
      await api.updateConversation(id, { user_id: userId, title: t });
      await loadHistory();
    } catch (e) {
      alert(e.message || "重命名失败");
    }
  };

  const handlePin = async (item) => {
    try {
      await api.updateConversation(item.id, {
        user_id: userId,
        is_pinned: item.is_pinned ? 0 : 1,
      });
      await loadHistory();
    } catch (e) {
      alert(e.message || "置顶操作失败，请稍后重试");
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`确定删除「${item.title}」？`)) return;
    try {
      await api.deleteConversation(item.id, userId);
      if (cid === item.id) navigate("/chat");
      await loadHistory();
    } catch (e) {
      alert(e.message || "删除失败");
    }
  };

  const renderList = (list) =>
    list?.map((c) => (
      <HistoryRow
        key={c.id}
        item={c}
        active={cid === c.id}
        editing={editingId === c.id}
        onSelect={selectConv}
        onStartRename={setEditingId}
        onSaveRename={handleSaveRename}
        onCancelRename={() => setEditingId(null)}
        onPin={handlePin}
        onDelete={handleDelete}
      />
    ));

  const monthList = groups.recent_month || [];
  const halfList = (groups.recent_half_year || []).filter(
    (c) => !monthList.some((m) => m.id === c.id)
  );

  return (
    <div className="chat-layout">
      <aside className="history-panel">
        <button
          type="button"
          className="btn-primary"
          style={{ width: "100%", marginBottom: 12 }}
          onClick={() => navigate("/chat")}
        >
          + 新对话
        </button>

        {(groups.pinned?.length > 0 || monthList.length > 0) && (
          <>
            <div className="history-group-title">对话列表</div>
            {renderList(groups.pinned)}
            {renderList(monthList)}
          </>
        )}

        {halfList.length > 0 && (
          <>
            <div className="history-group-title">最近半年</div>
            {renderList(halfList)}
          </>
        )}
      </aside>
      <div className="chat-main">
        <div className="chat-toolbar">
          <button type="button" className="chip" disabled={!messages.length} onClick={exportTxt}>
            导出对话
          </button>
        </div>
        <div className="messages">
          {!cid && (
            <p style={{ textAlign: "center", color: "#636e72", marginTop: 80 }}>
              选择左侧对话或输入消息开始聊天
            </p>
          )}
          {messages.map((m, i) =>
            m.role === "human" ? (
              <div key={m.id || i} className="msg-user">
                <div className="bubble">{m.content}</div>
              </div>
            ) : (
              <div key={m.id || i} className="msg-ai">
                <div className="bubble">
                  <RichContent content={m.content} />
                  <MessageFeedback messageId={m.id} initialRating={m.my_rating} />
                </div>
              </div>
            )
          )}
        </div>
        <ChatFooter conversationId={cid} onSent={onSent} />
      </div>
    </div>
  );
}
