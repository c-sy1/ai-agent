import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getSession } from "../api";

export default function ChatFooter({ conversationId, onSent }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [activeCid, setActiveCid] = useState(conversationId ?? null);
  const navigate = useNavigate();
  const user = getSession();
  const inputRef = useRef(null);

  useEffect(() => {
    if (conversationId) setActiveCid(conversationId);
  }, [conversationId]);

  const doSend = async (message) => {
    const q = (message ?? text).trim();
    if (!q || sending) return;
    if (!user) {
      navigate("/login");
      return;
    }

    setSending(true);
    setError("");
    const typed = message === undefined;
    setText("");

    try {
      const res = await api.chat({
        user_id: user.user_id,
        conversation_id: activeCid ?? conversationId ?? undefined,
        question: q,
      });
      const cid = res.data.conversation_id;
      setActiveCid(cid);
      if (!conversationId) navigate(`/chat/${cid}`, { replace: true });
      onSent?.(cid);
    } catch (e) {
      const msg = (e && e.message) || "";
      setError(
        msg
          ? `发送失败：${msg}`
          : "发送失败：服务暂时不可用，请稍后重试；若一直失败请联系管理员检查服务器是否在运行。"
      );
      if (typed) setText(q);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  };

  return (
    <div className="chat-footer">
      <div className="quick-chips">
        <button
          type="button"
          className="chip"
          disabled={sending}
          onClick={() => doSend("帮我写一篇活动宣传短文")}
        >
          ✍️ 快速写作
        </button>
        <button
          type="button"
          className="chip"
          disabled={sending}
          onClick={() => doSend("请把下面内容翻译成英文：")}
        >
          🌐 语言翻译
        </button>
        <button
          type="button"
          className="chip"
          disabled={sending}
          onClick={() => doSend("请生成一张高清插画：夕阳海边")}
        >
          🎨 生成图片
        </button>
        <button type="button" className="chip" disabled={sending} onClick={() => doSend("请生成一段5秒短视频：")}>
          🎬 生成视频
        </button>
      </div>

      {sending && (
        <p className="chat-footer-hint">
          AI 正在处理… 生成图片/视频可能需要 1～2 分钟，请勿关闭页面
        </p>
      )}
      {error && <p className="chat-footer-error">{error}</p>}

      <div className="chat-input-bar">
        <textarea
          ref={inputRef}
          rows={1}
          className="chat-input-field"
          placeholder="输入文字进行对话吧"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          disabled={sending}
        />
        <button
          type="button"
          className="chat-send-btn"
          onClick={() => doSend()}
          disabled={sending || !text.trim()}
          title="发送"
          aria-label="发送"
        >
          {sending ? "…" : "↑"}
        </button>
      </div>
    </div>
  );
}
