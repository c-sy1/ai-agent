import { useEffect, useRef, useState } from "react";
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
  const [maskBase64, setMaskBase64] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [brush, setBrush] = useState(28);
  const photoRequired = needsPhoto(tool);
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const drawing = useRef(false);

  useEffect(() => {
    setInput("");
    setOutput("");
    setFileUrl("");
    setFilename("");
    setMediaUrl("");
    setPreview("");
    setImageBase64("");
    setMaskBase64("");
    setError("");
  }, [tool?.id]);

  const syncCanvasSize = () => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    const w = img.clientWidth || img.naturalWidth;
    const h = img.clientHeight || img.naturalHeight;
    if (!w || !h) return;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);
    }
  };

  useEffect(() => {
    if (!preview) return;
    const t = setTimeout(syncCanvasSize, 50);
    window.addEventListener("resize", syncCanvasSize);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", syncCanvasSize);
    };
  }, [preview]);

  if (!tool) return null;

  const paintAt = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((e.clientY - rect.top) / rect.height) * canvas.height;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(x, y, brush, 0, Math.PI * 2);
    ctx.fill();
  };

  const onPointerDown = (e) => {
    drawing.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    paintAt(e);
  };
  const onPointerMove = (e) => {
    if (!drawing.current) return;
    paintAt(e);
  };
  const onPointerUp = () => {
    drawing.current = false;
    const canvas = canvasRef.current;
    if (canvas) setMaskBase64(canvas.toDataURL("image/png"));
  };

  const clearMask = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    setMaskBase64("");
  };

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
      setMaskBase64("");
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
    const needMask = /去掉|删除|消除|去除|路人|擦除|移除/.test(input || "");
    let mask = maskBase64;
    if (photoRequired && needMask) {
      const canvas = canvasRef.current;
      if (canvas) mask = canvas.toDataURL("image/png");
      if (!mask) {
        setError("去掉路人请先在图上涂抹要改的区域（白色笔刷）");
        return;
      }
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
        mask_base64: photoRequired ? mask || undefined : undefined,
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
                <>
                  <p className="profile-desc" style={{ margin: "8px 0" }}>
                    去掉路人：在下方图上用笔刷涂抹要删除的区域，再点生成（只写文字往往几乎不改图）
                  </p>
                  <div className="mask-stage">
                    <img
                      ref={imgRef}
                      src={preview}
                      alt="预览"
                      className="tool-upload-preview"
                      onLoad={syncCanvasSize}
                      draggable={false}
                    />
                    <canvas
                      ref={canvasRef}
                      className="mask-canvas"
                      onPointerDown={onPointerDown}
                      onPointerMove={onPointerMove}
                      onPointerUp={onPointerUp}
                      onPointerLeave={onPointerUp}
                    />
                  </div>
                  <div className="mask-toolbar">
                    <label>
                      笔刷
                      <input
                        type="range"
                        min={12}
                        max={64}
                        value={brush}
                        onChange={(e) => setBrush(Number(e.target.value))}
                      />
                    </label>
                    <button type="button" className="chip" onClick={clearMask}>
                      清除涂抹
                    </button>
                  </div>
                </>
              ) : (
                <p className="profile-desc" style={{ margin: "8px 0 0" }}>
                  必须上传原图；去路人请涂抹要改的区域
                </p>
              )}
            </div>
          </>
        )}

        <label className="tool-modal-label">{photoRequired ? "修复需求" : "输入"}</label>
        <textarea
          className="tool-modal-input"
          rows={4}
          placeholder={
            photoRequired
              ? "例如：去掉涂抹区域中的路人和车辆，用街道背景自然填补"
              : tool.input_placeholder || "请输入你的需求…"
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />

        <div className="tool-modal-actions">
          <button type="button" className="btn-primary" onClick={run} disabled={loading}>
            {loading ? (photoRequired ? "局部修图中，约需 10～30 秒…" : "AI 生成中…") : "立即生成"}
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
