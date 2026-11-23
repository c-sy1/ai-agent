import { useEffect, useState } from "react";
import { api, getSession, resolveAssetUrl } from "../api";
import RichContent from "./RichContent";

function needsPhoto(tool) {
  const s = `${tool?.name || ""}${tool?.description || ""}`;
  return /照片|拍照|修图|修复|药品/.test(s);
}

export default function ToolPanel({ tool, onClose }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [filename, setFilename] = useState("");
  const [mediaUrl, setMediaUrl] = useState("");
  const [preview, setPreview] = useState("");
  const [imageBase64, setImageBase64] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const photoRequired = needsPhoto(tool);

  useEffect(() => {
    setInput("");
    setOutput("");
    setFileUrl("");
    setFilename("");
    setMediaUrl("");
    setPreview("");
    setImageBase64("");
    setError("");
  }, [tool?.id]);

  if (!tool) return null;

  const onPickFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("请上传图片文件（jpg/png/webp）");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setError("图片请小于 8MB");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      setImageBase64(dataUrl);
      setPreview(dataUrl);
      setError("");
    };
    reader.onerror = () => setError("读取图片失败");
    reader.readAsDataURL(file);
  };

  const run = async () => {
    const user = getSession();
    if (!user) {
      setError("请先登录");
      return;
    }
    if (photoRequired && !imageBase64) {
      setError("请先上传照片");
      return;
    }
    setLoading(true);
    setError("");
    setFileUrl("");
    setFilename("");
    setMediaUrl("");
    try {
      const res = await api.invokeTool(tool.id, {
        user_id: user.user_id,
        input,
        image_base64: photoRequired ? imageBase64 : undefined,
      });
      const out = res.data.output || "";
      setOutput(out);
      if (res.data.media_url) {
        setMediaUrl(resolveAssetUrl(res.data.media_url));
      }
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

        {photoRequired && (
          <>
            <label className="tool-modal-label">上传照片</label>
            <div className="tool-upload">
              <input type="file" accept="image/*" onChange={onPickFile} />
              {preview ? (
                <img src={preview} alt="预览" className="tool-upload-preview" />
              ) : (
                <p className="profile-desc" style={{ margin: "8px 0 0" }}>
                  必须上传原图；将基于这张图做真修图（非另画一张）
                </p>
              )}
            </div>
          </>
        )}

        <label className="tool-modal-label">{photoRequired ? "修复需求" : "输入"}</label>
        <textarea
          className="tool-modal-input"
          rows={5}
          placeholder={
            photoRequired
              ? "例如：去掉前方路人、提亮人脸、去除杂物，保持原图主体不变"
              : tool.input_placeholder || "请输入你的需求…"
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />

        <div className="tool-modal-actions">
          <button type="button" className="btn-primary" onClick={run} disabled={loading}>
            {loading ? (photoRequired ? "原图修图中，约需 10～30 秒…" : "AI 生成中…") : "立即生成"}
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

        {photoRequired && preview && mediaUrl && (
          <div className="tool-compare" style={{ marginTop: 12 }}>
            <div>
              <label className="tool-modal-label">原图</label>
              <img src={preview} alt="原图" className="tool-upload-preview" />
            </div>
            <div>
              <label className="tool-modal-label">修图结果</label>
              <img src={mediaUrl} alt="修图结果" className="tool-upload-preview" />
            </div>
          </div>
        )}
        {!photoRequired && mediaUrl && (
          <div style={{ marginTop: 12 }}>
            <label className="tool-modal-label">效果图</label>
            <img src={mediaUrl} alt="生成结果" className="tool-upload-preview" />
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
