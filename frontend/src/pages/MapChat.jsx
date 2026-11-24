import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, getSession } from "../api";
import RichContent from "../components/RichContent";

const QUICK = ["保定理工学院位置", "白洋淀在哪？", "狼牙山坐标"];

function loadAmapScript(key, securityCode) {
  return new Promise((resolve, reject) => {
    // 必须在加载 JS API 之前设置，否则底图瓦片会灰屏（只有标记）
    const code = (securityCode || "").trim();
    if (code) {
      window._AMapSecurityConfig = { securityJsCode: code };
    }
    if (window.AMap) {
      resolve(window.AMap);
      return;
    }
    const existing = document.querySelector("script[data-amap]");
    if (existing) {
      existing.addEventListener("load", () => resolve(window.AMap));
      existing.addEventListener("error", () => reject(new Error("高德脚本加载失败")));
      return;
    }
    const s = document.createElement("script");
    s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    s.async = true;
    s.dataset.amap = "1";
    s.onload = () => resolve(window.AMap);
    s.onerror = () => reject(new Error("高德脚本加载失败，请检查 AMAP_JS_KEY"));
    document.head.appendChild(s);
  });
}

export default function MapChat() {
  const user = getSession();
  const userId = user?.user_id;
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [mapHint, setMapHint] = useState("地图加载中…");
  const [cid, setCid] = useState(null);
  const [places, setPlaces] = useState([]);
  const mapRef = useRef(null);
  const mapInst = useRef(null);
  const markersRef = useRef([]);
  const listRef = useRef(null);

  const flyTo = useCallback(async (point) => {
    if (!point || point.lng == null || point.lat == null) return;
    const AMap = window.AMap;
    if (!AMap || !mapInst.current) return;
    const pos = [Number(point.lng), Number(point.lat)];
    const marker = new AMap.Marker({
      position: pos,
      title: point.name || "",
      label: point.name
        ? { content: `<div class="amap-label">${point.name}</div>`, direction: "top" }
        : undefined,
    });
    mapInst.current.add(marker);
    markersRef.current.push(marker);
    mapInst.current.setZoomAndCenter(13, pos);
    setMapHint(`${point.name || "目标"} · ${point.lng}, ${point.lat}`);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.mapConfig();
        if (cancelled) return;
        setPlaces(cfg.data?.places || []);
        const key = (cfg.data?.amap_js_key || "").trim();
        if (!key) {
          setMapHint("未配置 AMAP_JS_KEY：请在 backend/.env 填写高德 Web端(JS API) Key 后重启");
          return;
        }
        if (!(cfg.data?.security_js_code || "").trim()) {
          setMapHint("缺少 AMAP_SECURITY_JS_CODE：底图会灰屏。请在服务器 backend/.env 填写安全密钥后重启");
        }
        await loadAmapScript(key, cfg.data?.security_js_code);
        if (cancelled || !mapRef.current) return;
        const el = mapRef.current;
        if (!el.clientWidth || !el.clientHeight) {
          el.style.minHeight = "420px";
        }
        // 默认矢量样式在部分 Key 上会 INVALID_USER_KEY 导致灰底；
        // 改用高德公开栅格路网瓦片，保证录屏能看到真实地图。
        const raster = new window.AMap.TileLayer({
          getTileUrl(x, y, z) {
            const host = (x % 4) + 1;
            return `https://webrd0${host}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x=${x}&y=${y}&z=${z}`;
          },
          zIndex: 1,
          zooms: [3, 18],
        });
        const map = new window.AMap.Map(el, {
          zoom: 10,
          center: [115.4648, 38.8739],
          viewMode: "2D",
          layers: [raster],
        });
        mapInst.current = map;
        map.on("complete", () => {
          map.resize();
          setMapHint("已就绪 · 试试问「白洋淀在哪」");
        });
        map.on("error", (err) => {
          setMapHint(
            `底图加载失败：${err?.info || err?.type || "鉴权/白名单"}。请检查安全密钥与域名白名单`
          );
        });
        setTimeout(() => map.resize(), 200);
        window.addEventListener("resize", () => mapInst.current?.resize());
        const list = cfg.data?.places || [];
        list.forEach((p) => {
          const m = new window.AMap.Marker({
            position: [p.lng, p.lat],
            title: p.name,
          });
          map.add(m);
          markersRef.current.push(m);
        });
      } catch (e) {
        if (!cancelled) setMapHint(e.message || "地图初始化失败");
      }
    })();
    return () => {
      cancelled = true;
      markersRef.current = [];
      if (mapInst.current) {
        mapInst.current.destroy();
        mapInst.current = null;
      }
    };
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const send = async (raw) => {
    const q = (raw ?? text).trim();
    if (!q || sending || !userId) return;
    setSending(true);
    setError("");
    setText("");
    setMessages((prev) => [...prev, { role: "human", content: q }]);
    try {
      const res = await api.chat({
        user_id: userId,
        conversation_id: cid || undefined,
        question: q,
      });
      const answer = res.data?.answer || "";
      const mapPoint = res.data?.map;
      setCid(res.data?.conversation_id ?? cid);
      setMessages((prev) => [...prev, { role: "ai", content: answer }]);
      if (mapPoint) await flyTo(mapPoint);
    } catch (e) {
      setError(e.message || "发送失败");
      setMessages((prev) => prev.slice(0, -1));
      setText(q);
    } finally {
      setSending(false);
    }
  };

  const locatePlace = async (name) => {
    try {
      const res = await api.mapGeocode(name);
      await flyTo(res.data);
      setMessages((prev) => [
        ...prev,
        { role: "human", content: `定位：${name}` },
        {
          role: "ai",
          content:
            `已定位 **${res.data.name}**\n\n` +
            `- 地址：${res.data.address}\n` +
            `- 经度：${res.data.lng}\n` +
            `- 纬度：${res.data.lat}\n\n` +
            `[[map:${res.data.lng},${res.data.lat},${res.data.name}]]`,
        },
      ]);
    } catch (e) {
      setError(e.message || "定位失败");
    }
  };

  return (
    <div className="map-page">
      <div className="map-chat-pane">
        <div className="map-chat-head">
          <div>
            <h1>地图工具</h1>
            <p>内置：保定理工学院 · 保定 · 白洋淀 · 狼牙山</p>
          </div>
          <Link to="/toolbox" className="map-back">
            ← 工具箱
          </Link>
        </div>

        <div className="map-place-chips">
          {places.map((p) => (
            <button key={p.key || p.name} type="button" className="chip" onClick={() => locatePlace(p.name)}>
              📍 {p.name}
            </button>
          ))}
        </div>

        <div className="map-messages" ref={listRef}>
          {messages.length === 0 && (
            <p className="map-empty">登录后提问地理位置，例如「白洋淀在哪？」右侧地图会跳转并标记。</p>
          )}
          {messages.map((m, i) =>
            m.role === "human" ? (
              <div key={i} className="msg-user">
                <div className="bubble">{m.content}</div>
              </div>
            ) : (
              <div key={i} className="msg-ai">
                <div className="bubble">
                  <RichContent content={m.content} />
                </div>
              </div>
            )
          )}
          {sending && <p className="map-sending">定位中…</p>}
        </div>

        <div className="map-composer">
          <div className="quick-chips">
            {QUICK.map((q) => (
              <button key={q} type="button" className="chip" disabled={sending} onClick={() => send(q)}>
                {q}
              </button>
            ))}
          </div>
          {error && <p className="chat-footer-error">{error}</p>}
          <div className="composer-row">
            <textarea
              rows={2}
              placeholder="问地点，如：狼牙山在哪"
              value={text}
              disabled={sending}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button type="button" className="btn-primary" disabled={sending || !text.trim()} onClick={() => send()}>
              发送
            </button>
          </div>
        </div>
      </div>

      <div className="map-view-pane">
        <div className="map-status">{mapHint}</div>
        <div ref={mapRef} className="map-canvas" />
      </div>
    </div>
  );
}
