import { useState } from "react";
import { api, getSession } from "../api";

export default function MessageFeedback({ messageId, initialRating }) {
  const [rating, setRating] = useState(initialRating || "");
  const [busy, setBusy] = useState(false);

  if (!messageId) return null;

  const vote = async (value) => {
    const user = getSession();
    if (!user?.user_id || busy) return;
    setBusy(true);
    try {
      await api.submitFeedback({
        user_id: user.user_id,
        message_id: messageId,
        rating: value,
      });
      setRating(value);
    } catch (e) {
      alert(e.message || "反馈失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="msg-feedback">
      <button
        type="button"
        className={rating === "up" ? "active" : ""}
        disabled={busy}
        title="满意"
        onClick={() => vote("up")}
      >
        👍
      </button>
      <button
        type="button"
        className={rating === "down" ? "active" : ""}
        disabled={busy}
        title="不满意"
        onClick={() => vote("down")}
      >
        👎
      </button>
    </div>
  );
}
