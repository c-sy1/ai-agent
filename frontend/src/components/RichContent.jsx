import { Link } from "react-router-dom";
import { resolveAssetUrl } from "../api";

const IMG_RE = /!\[[^\]]*\]\(([^)]+)\)/g;
const VIDEO_RE = /\[\[video:([^\]]+)\]\]/g;
const MAP_RE = /\[\[map:([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([^\]]+)\]\]/g;
const LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;

function renderTextWithLinks(text, keyPrefix) {
  const nodes = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(LINK_RE)) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    const label = m[1];
    const href = resolveAssetUrl(m[2]);
    const isPpt = /\.pptx($|\?)/i.test(m[2]) || /下载\s*PPT/i.test(label);
    nodes.push(
      <a
        key={`${keyPrefix}-a${i++}`}
        href={href}
        download={isPpt ? undefined : undefined}
        target={isPpt ? undefined : "_blank"}
        rel="noreferrer"
        style={{ color: "#0b6e4f", fontWeight: 600 }}
      >
        {label}
      </a>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function RichContent({ content }) {
  if (!content) return null;

  const parts = [];
  let last = 0;
  const markers = [];

  for (const m of content.matchAll(IMG_RE)) {
    markers.push({ i: m.index, len: m[0].length, type: "img", url: m[1] });
  }
  for (const m of content.matchAll(VIDEO_RE)) {
    markers.push({ i: m.index, len: m[0].length, type: "video", url: m[1] });
  }
  for (const m of content.matchAll(MAP_RE)) {
    markers.push({
      i: m.index,
      len: m[0].length,
      type: "map",
      lng: m[1],
      lat: m[2],
      name: m[3].trim(),
    });
  }
  markers.sort((a, b) => a.i - b.i);

  markers.forEach((mk, idx) => {
    if (mk.i > last) {
      parts.push({ kind: "text", key: `t${idx}`, text: content.slice(last, mk.i) });
    }
    if (mk.type === "map") {
      parts.push({
        kind: "map",
        key: `m${idx}`,
        lng: mk.lng,
        lat: mk.lat,
        name: mk.name,
      });
    } else {
      parts.push({ kind: mk.type, key: `m${idx}`, url: mk.url });
    }
    last = mk.i + mk.len;
  });
  if (last < content.length) {
    parts.push({ kind: "text", key: "tail", text: content.slice(last) });
  }

  if (parts.length === 0) {
    return (
      <div className="bubble-text" style={{ whiteSpace: "pre-wrap" }}>
        {renderTextWithLinks(content, "only")}
      </div>
    );
  }

  return (
    <div className="bubble-rich">
      {parts.map((p) => {
        if (p.kind === "text") {
          return (
            <div key={p.key} className="bubble-text" style={{ whiteSpace: "pre-wrap" }}>
              {renderTextWithLinks(p.text, p.key)}
            </div>
          );
        }
        if (p.kind === "img") {
          return (
            <img
              key={p.key}
              className="bubble-media"
              src={resolveAssetUrl(p.url)}
              alt="生成图片"
              loading="lazy"
            />
          );
        }
        if (p.kind === "map") {
          return (
            <Link key={p.key} className="map-marker-link" to="/map">
              🗺️ 在地图中查看「{p.name}」({p.lng}, {p.lat})
            </Link>
          );
        }
        return (
          <video
            key={p.key}
            className="bubble-media"
            src={resolveAssetUrl(p.url)}
            controls
            playsInline
          />
        );
      })}
    </div>
  );
}
