import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import ChatFooter from "../components/ChatFooter";

export default function Home() {
  const [topics, setTopics] = useState([]);
  const [tools, setTools] = useState([]);
  const [agents, setAgents] = useState([]);

  useEffect(() => {
    api.hotTopics().then((r) => setTopics(r.data));
    api.tools().then((r) => {
      const names = ["会议记录助手", "旅游规划助手", "合同检查工具"];
      setTools(r.data.filter((t) => names.includes(t.name)));
    });
    api.agents({ featured: 1 }).then((r) => setAgents(r.data));
  }, []);

  const agentBg = ["linear-gradient(135deg,#55efc4,#00b894)", "linear-gradient(135deg,#fab1a0,#e17055)"];

  return (
    <>
      <div className="page-scroll">
        <div className="hero">
          <div className="hero-logo">🤖</div>
          <h1>Apex AI</h1>
          <p>从熬夜加班到一键生成，你和高效办公只差一个AI</p>
        </div>

        <div className="grid-3">
          <div className="card" style={{ padding: 20 }}>
            <h2 className="panel-title">热搜榜单</h2>
            <p className="panel-desc">实时捕捉全网最热话题，一秒 get 社交货币</p>
            <ul className="hot-list">
              {topics.map((t) => (
                <li key={t.rank}>
                  <span className="hot-rank">{t.rank}</span>
                  <span>{t.title}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="card" style={{ padding: 20 }}>
            <h2 className="panel-title">实用工具</h2>
            <p className="panel-desc">上百款神器精准匹配需求</p>
            {tools.map((t) => (
              <Link key={t.id} to="/toolbox" className="tool-mini">
                <span style={{ fontSize: 24 }}>{t.icon}</span>
                <div>
                  <strong>{t.name}</strong>
                  <div style={{ fontSize: 12, color: "#636e72" }}>{t.description}</div>
                </div>
              </Link>
            ))}
          </div>

          <div className="card" style={{ padding: 20 }}>
            <h2 className="panel-title">智能体</h2>
            <p className="panel-desc">24 小时在线的数字员工</p>
            {agents.map((a, i) => (
              <div
                key={a.id}
                className="agent-feature"
                style={{ background: agentBg[i % agentBg.length] }}
              >
                <div>
                  <div style={{ fontSize: 28 }}>{a.icon}</div>
                  <strong>{a.name}</strong>
                </div>
                <Link to={`/agents?try=${a.id}`} className="chip" style={{ alignSelf: "flex-start" }}>
                  立即体验
                </Link>
              </div>
            ))}
          </div>
        </div>
      </div>
      <ChatFooter />
    </>
  );
}
