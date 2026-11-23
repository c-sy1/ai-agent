import { useEffect, useState } from "react";
import { api, getSession, resolveAssetUrl } from "../api";
import RichContent from "./RichContent";

export default function ToolPanel({ tool, onClose }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [filename, setFilename] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setInput("");
    setOutput("");
    setFileUrl("");
    setFilename("");
    setError("");
  }, [tool?.id]);

  if (!tool) return null;

  const run = async () => {
    const user = getSession();
    if (!user) {
      setError("请先登录");
      return;
    }
    setLoading(true);
    setError("");
    setFileUrl("");
    setFilename("");
    try {
      const res = await api.invokeTool(tool.id, {
        user_id: user.user_id,
        input,
      });
      const out = res.data.output || "";
      setOutput(out);
      let url = res.data.file_url || "";
      let name = res.data.filename || "";
      if (!url) {
        const m = out.match(/\((\/generated\/pptx\/[^)]+\.pptx)\)/i);
        if (m) url = m[1];
      }
      if (!name && url) {
        name = decodeURIComponent(url.split("/").pop() || "ApexAI.pptx");
      }
      if (url) {
        setFileUrl(resolveAssetUrl(url));
        setFilename(name || "ApexAI.pptx");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    if (output) navigator.clipboard?.writeText(output);
  };

  return (
    <div className="tool-modal-overlay" onClick={onClose} role="presentation">
      <div className="tool-modal card" onClick={(e) => e.stopPropagation()}>
        <div className="tool-modal-head">
          <span style={{ fontSize: 28 }}>{tool.icon}</span>
          <div>
            <h2 style={{ margin: 0 }}>{tool.name}</h2>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "#636e72" }}>
              {tool.description}
            </p>
          </div>
          <button type="button" className="tool-modal-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <label className="tool-modal-label">输入</label>
        <textarea
          className="tool-modal-input"
          rows={5}
          placeholder={tool.input_placeholder || "请输入你的需求…"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />

        <div className="tool-modal-actions">
          <button type="button" className="btn-primary" onClick={run} disabled={loading}>
            {loading ? "AI 生成中…" : "立即生成"}
          </button>
          {output && (
            <button type="button" className="chip" onClick={copy}>
              复制结果
            </button>
          )}
        </div>

        {error && <p className="form-error">{error}</p>}

        {fileUrl && (
          <div className="ppt-download-banner">
            <div>
              <strong>PPT 文件已生成</strong>
              <div style={{ fontSize: 13, color: "#636e72", marginTop: 4 }}>
                {filename || "ApexAI.pptx"} · 可直接用 PowerPoint / WPS 打开
              </div>
            </div>
            <a className="btn-primary" href={fileUrl} download={filename || "ApexAI.pptx"}>
              下载 PPT
            </a>
          </div>
        )}

        {output && (
          <>
            <label className="tool-modal-label">生成结果</label>
            <div className="tool-modal-output">
              <RichContent content={output} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
