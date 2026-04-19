import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Briefcase, PieChart, Search, Settings, ArrowUpRight, Menu, RefreshCw, ChevronRight, Plus, X } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from './api';

const fmt = (n, dec = 0) => (n ?? 0).toLocaleString('en-US', { maximumFractionDigits: dec });
const fmtPct = (n) => `${n >= 0 ? '+' : ''}${(n ?? 0).toFixed(1)}%`;

const Tag = ({ children, color = 'default' }) => {
  const styles = {
    default: { background: 'rgba(255,255,255,0.06)', color: '#888890' },
    green:   { background: 'rgba(74,222,128,0.1)',   color: '#4ade80' },
    red:     { background: 'rgba(248,113,113,0.1)',  color: '#f87171' },
    lime:    { background: 'rgba(212,255,0,0.1)',    color: '#d4ff00' },
  };
  return (
    <span style={{ ...styles[color], padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, letterSpacing: '0.03em', display: 'inline-flex', alignItems: 'center' }}>
      {children}
    </span>
  );
};

const fade = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0 }, transition: { duration: 0.2 } };

const CardHeader = ({ title, sub }) => (
  <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <p style={{ fontSize: 14, fontWeight: 600, color: '#e8e8ea' }}>{title}</p>
    {sub && <p style={{ fontSize: 12, color: '#888890', marginTop: 3 }}>{sub}</p>}
  </div>
);

// ─── Dashboard ────────────────────────────────────────────────────────────────
const Dashboard = ({ refreshKey }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get('/dashboard').then(r => setData(r.data)).catch(console.error).finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
        {[1,2,3].map(i => <div key={i} className="card rounded-xl animate-pulse" style={{ height: 130 }} />)}
      </div>
      <div className="card rounded-xl animate-pulse" style={{ height: 280 }} />
    </div>
  );

  if (!data) return <div className="card rounded-lg" style={{ padding: 20, color: '#f87171', fontSize: 14 }}>Backend unreachable.</div>;

  const profit = data.total_profit ?? 0;
  const profitPct = data.profit_pct ?? 0;
  const topAsset = data.top_gainer?.ticker ?? '—';
  const chartData = data.allocation ? Object.entries(data.allocation).map(([name, value]) => ({ name, value })) : [];

  return (
    <motion.div {...fade} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
        <div className="card rounded-xl" style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#555558' }}>Net Worth</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#555558' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ade80', display: 'inline-block', animation: 'pulse 2s infinite' }} />
              Live
            </span>
          </div>
          <p style={{ fontSize: 32, fontWeight: 600, letterSpacing: '-0.02em', color: '#fff', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            ฿{fmt(data.total_val)}
          </p>
          <p style={{ fontSize: 12, color: '#555558', marginTop: 'auto' }}>Cost basis ฿{fmt(data.total_cost)}</p>
        </div>

        <div className="card rounded-xl" style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#555558' }}>Unrealized P/L</span>
            <Tag color={profitPct >= 0 ? 'green' : 'red'}>{fmtPct(profitPct)}</Tag>
          </div>
          <p style={{ fontSize: 32, fontWeight: 600, letterSpacing: '-0.02em', color: profit >= 0 ? '#4ade80' : '#f87171', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            {profit >= 0 ? '+' : ''}฿{fmt(Math.abs(profit))}
          </p>
          <p style={{ fontSize: 12, color: '#555558', marginTop: 'auto' }}>Total return on capital</p>
        </div>

        <div className="card rounded-xl" style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#555558' }}>Top Gainer</span>
            <ArrowUpRight size={14} color="#d4ff00" />
          </div>
          <p style={{ fontSize: 32, fontWeight: 600, letterSpacing: '-0.02em', color: '#fff', lineHeight: 1 }}>{topAsset}</p>
          <p style={{ fontSize: 12, color: '#555558', marginTop: 'auto' }}>
            {data.top_gainer ? `+฿${fmt(data.top_gainer.unrealized_pl_thb ?? 0)} gain` : 'No positions yet'}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="card rounded-xl" style={{ padding: '24px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#e8e8ea' }}>Asset Distribution</p>
            <p style={{ fontSize: 12, color: '#888890', marginTop: 3 }}>Portfolio value by position</p>
          </div>
          <Tag>THB</Tag>
        </div>
        {chartData.length === 0 ? (
          <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#555558', fontSize: 13 }}>
            No allocation data yet
          </div>
        ) : (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 16 }} barSize={24}>
                <defs>
                  <linearGradient id="barG" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#d4ff00" stopOpacity={0.9} />
                    <stop offset="100%" stopColor="#d4ff00" stopOpacity={0.2} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#555558', fontSize: 11, fontWeight: 600 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#555558', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1c1c20', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12, padding: '8px 12px' }} itemStyle={{ color: '#d4ff00', fontWeight: 600 }} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                <Bar dataKey="value" fill="url(#barG)" radius={[4,4,0,0]} animationDuration={900} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ─── Holdings ─────────────────────────────────────────────────────────────────
const Holdings = ({ refreshKey }) => {
  const [holdings, setHoldings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get('/holdings').then(r => setHoldings(r.data)).catch(console.error).finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading) return <div className="card rounded-lg animate-pulse" style={{ height: 240 }} />;

  return (
    <motion.div {...fade}>
      <div className="card rounded-xl" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, minWidth: 580 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              {['Ticker','Qty','Avg Cost','Market Value','P/L'].map((h, i) => (
                <th key={h} style={{ padding: '14px 20px', textAlign: i === 0 ? 'left' : 'right', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#555558', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '48px 20px', textAlign: 'center', fontSize: 13, color: '#555558' }}>
                  No holdings yet. Add your first position to get started.
                </td>
              </tr>
            )}
            {holdings.map(h => {
              const pl = h.unrealized_pl_thb ?? 0;
              const plPct = (h.unrealized_pl_pct ?? 0) * 100;
              return (
                <tr key={h.ticker} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }} className="hover:bg-white/[0.02] transition-colors">
                  <td style={{ padding: '14px 20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 30, height: 30, borderRadius: 8, background: 'rgba(212,255,0,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#d4ff00', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                        {h.ticker?.[0]}
                      </div>
                      <span style={{ fontWeight: 600, color: '#e8e8ea' }}>{h.ticker}</span>
                    </div>
                  </td>
                  <td style={{ padding: '14px 20px', textAlign: 'right', color: '#888890', fontVariantNumeric: 'tabular-nums' }}>{h.total_quantity?.toLocaleString()}</td>
                  <td style={{ padding: '14px 20px', textAlign: 'right', color: '#888890' }}>฿{h.avg_price_thb?.toLocaleString()}</td>
                  <td style={{ padding: '14px 20px', textAlign: 'right', fontWeight: 600, color: '#e8e8ea' }}>฿{fmt(h.value_thb)}</td>
                  <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                    <div style={{ fontWeight: 600, color: pl >= 0 ? '#4ade80' : '#f87171', fontVariantNumeric: 'tabular-nums' }}>
                      {pl >= 0 ? '+' : ''}฿{fmt(Math.abs(pl))}
                    </div>
                    <div style={{ fontSize: 11, marginTop: 2, color: plPct >= 0 ? 'rgba(74,222,128,0.6)' : 'rgba(248,113,113,0.6)' }}>
                      {fmtPct(plPct)}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
};

// ─── Analysis ─────────────────────────────────────────────────────────────────
const Analysis = () => {
  const [dist, setDist] = useState([]);
  const [rebal, setRebal] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.get('/analysis/distribution'), api.get('/analysis/rebalance')])
      .then(([d, r]) => { setDist(d.data); setRebal(r.data); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      <div className="card rounded-xl animate-pulse" style={{ height: 280 }} />
      <div className="card rounded-xl animate-pulse" style={{ height: 280 }} />
    </div>
  );

  const total = dist.reduce((a, c) => a + c.value_thb, 0);
  const sectors = Array.from(new Set(dist.map(d => d.sector)))
    .map(s => ({ sector: s, pct: total > 0 ? dist.filter(d => d.sector === s).reduce((a,c) => a + c.value_thb, 0) / total * 100 : 0 }))
    .sort((a, b) => b.pct - a.pct);

  return (
    <motion.div {...fade} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Rebalance */}
      <div className="card rounded-xl" style={{ overflow: 'hidden' }}>
        <CardHeader title="Rebalancing" sub="Actions to reach target weights" />
        <div>
          {rebal.length === 0 && <p style={{ padding: '24px 20px', fontSize: 13, color: '#555558' }}>No rebalancing needed</p>}
          {rebal.map(r => {
            const isBuy = r.difference_pct >= 0;
            return (
              <div key={r.ticker} style={{ padding: '14px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.04)' }} className="hover:bg-white/[0.02] transition-colors">
                <div>
                  <p style={{ fontWeight: 600, color: '#e8e8ea', fontSize: 14 }}>{r.ticker}</p>
                  <p style={{ fontSize: 12, color: '#555558', marginTop: 3 }}>{r.current_weight?.toFixed(1)}% → {r.target_weight?.toFixed(1)}%</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <Tag color={isBuy ? 'green' : 'red'}>{isBuy ? 'BUY' : 'SELL'}</Tag>
                  <p style={{ fontWeight: 600, color: '#e8e8ea', fontSize: 14, marginTop: 4 }}>฿{fmt(Math.abs(r.diff_value_thb))}</p>
                  <p style={{ fontSize: 11, color: '#555558', marginTop: 2 }}>{Math.abs(r.shares_to_buy).toFixed(2)} shares</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sector Allocation */}
      <div className="card rounded-xl" style={{ overflow: 'hidden' }}>
        <CardHeader title="Sector Allocation" sub="Distribution across sectors" />
        <div style={{ padding: '20px' }}>
          {sectors.length === 0 && <p style={{ fontSize: 13, color: '#555558', padding: '12px 0' }}>No sector data yet</p>}
          {sectors.map(({ sector, pct: p }) => (
            <div key={sector} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                <span style={{ color: '#888890', fontWeight: 500 }}>{sector}</span>
                <span style={{ color: '#e8e8ea', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{p.toFixed(1)}%</span>
              </div>
              <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                <motion.div initial={{ width: 0 }} animate={{ width: `${p}%` }} transition={{ duration: 0.7 }}
                  style={{ height: '100%', background: '#d4ff00', borderRadius: 4 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

// ─── Discovery ────────────────────────────────────────────────────────────────
const Discovery = () => {
  const [search, setSearch] = useState('');
  const [picks, setPicks] = useState([]);
  const [sectors, setSectors] = useState({});
  const [research, setResearch] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.get('/discovery/smart-picks'), api.get('/discovery/sectors')])
      .then(([p, s]) => { setPicks(p.data); setSectors(s.data); })
      .catch(console.error);
  }, []);

  const doSearch = async (ticker) => {
    const t = (ticker || search).trim().toUpperCase();
    if (!t) return;
    setSearch(t);
    setLoading(true);
    try { const res = await api.get(`/research/stock/${t}`); setResearch(res.data); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  return (
    <motion.div {...fade} style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20 }}>
      {/* Left */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Search bar */}
        <div className="card rounded-xl" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              type="text" value={search}
              onChange={e => setSearch(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
              placeholder="Search ticker — e.g. AAPL, NVDA, TSLA"
              style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '10px 16px', fontSize: 14, color: '#e8e8ea', outline: 'none' }}
            />
            <button onClick={() => doSearch()}
              style={{ background: '#d4ff00', color: '#000', padding: '10px 20px', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer', border: 'none', flexShrink: 0 }}>
              Analyze
            </button>
          </div>
          {picks.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: '#555558', marginRight: 4 }}>Suggestions:</span>
              {picks.map(p => (
                <button key={p} onClick={() => doSearch(p)}
                  style={{ fontSize: 12, padding: '4px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, color: '#888890', cursor: 'pointer' }}>
                  {p}
                </button>
              ))}
            </div>
          )}
        </div>

        {loading && (
          <div className="card rounded-xl" style={{ padding: '32px 24px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, fontSize: 13, color: '#888890' }}>
            <RefreshCw size={14} className="animate-spin" /> Fetching market data...
          </div>
        )}

        {research && !loading && (
          <motion.div {...fade} className="card rounded-xl" style={{ overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <Tag color="lime">{research.info.symbol}</Tag>
                  {research.info.sector && <Tag>{research.info.sector}</Tag>}
                </div>
                <h3 style={{ fontSize: 18, fontWeight: 600, color: '#e8e8ea', lineHeight: 1.3 }}>{research.info.longName}</h3>
                <p style={{ fontSize: 12, color: '#888890', marginTop: 4 }}>{research.info.industry}</p>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <p style={{ fontSize: 22, fontWeight: 600, color: '#e8e8ea', fontVariantNumeric: 'tabular-nums' }}>฿{research.info.currentPrice?.toLocaleString()}</p>
                <p style={{ fontSize: 11, color: '#888890', marginTop: 3 }}>Current Price</p>
              </div>
            </div>

            {/* Metrics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              {[
                { label: 'P/E Forward', val: research.info.forwardPE?.toFixed(2) ?? '—' },
                { label: 'Market Cap',  val: research.info.marketCap ? `$${(research.info.marketCap/1e9).toFixed(1)}B` : '—' },
                { label: 'Dividend',    val: research.info.dividendYield ? `${(research.info.dividendYield*100).toFixed(2)}%` : '—' },
                { label: 'Beta',        val: research.info.beta?.toFixed(2) ?? '—' },
              ].map((m, i) => (
                <div key={m.label} style={{ padding: '16px 20px', borderRight: i < 3 ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
                  <p style={{ fontSize: 11, color: '#555558', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{m.label}</p>
                  <p style={{ fontSize: 18, fontWeight: 600, color: '#e8e8ea', marginTop: 6 }}>{m.val}</p>
                </div>
              ))}
            </div>

            {/* Funnel */}
            {research.funnel?.["Total Revenue"] && (
              <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <p style={{ fontSize: 11, color: '#555558', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 14 }}>Income Funnel</p>
                {[
                  { label: 'Revenue',         key: 'Total Revenue' },
                  { label: 'Gross Profit',     key: 'Gross Profit' },
                  { label: 'Operating Income', key: 'Operating Income' },
                  { label: 'Net Income',       key: 'Net Income' },
                ].map((step, i) => {
                  const val = research.funnel[step.key];
                  const total = research.funnel["Total Revenue"];
                  const p = val ? (val / total * 100) : 0;
                  if (!val) return null;
                  return (
                    <div key={step.key} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 5 }}>
                        <span style={{ color: '#888890' }}>{step.label}</span>
                        <span style={{ color: '#e8e8ea', fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>
                          ${(val/1e9).toFixed(2)}B <span style={{ color: '#555558', marginLeft: 8 }}>{p.toFixed(1)}%</span>
                        </span>
                      </div>
                      <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                        <motion.div initial={{ width: 0 }} animate={{ width: `${p}%` }} transition={{ duration: 0.8, delay: i * 0.08 }}
                          style={{ height: '100%', background: '#d4ff00', borderRadius: 4 }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {research.info.summary && (
              <div style={{ padding: '20px 24px' }}>
                <p style={{ fontSize: 11, color: '#555558', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>About</p>
                <p style={{ fontSize: 13, color: '#888890', lineHeight: 1.65, display: '-webkit-box', WebkitLineClamp: 5, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{research.info.summary}</p>
              </div>
            )}
          </motion.div>
        )}
      </div>

      {/* Right: Sector Catalog */}
      <div className="card rounded-xl" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          <p style={{ fontSize: 14, fontWeight: 600, color: '#e8e8ea' }}>Sector Catalog</p>
        </div>
        <div style={{ overflowY: 'auto', flex: 1, padding: 16 }}>
          {Object.entries(sectors).map(([sector, symbols]) => (
            <div key={sector} style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#555558', marginBottom: 8 }}>{sector}</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {symbols.map(s => (
                  <button key={s} onClick={() => doSearch(s)}
                    style={{ fontSize: 11, padding: '4px 8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 5, color: '#888890', cursor: 'pointer' }}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

// ─── Add Transaction Modal ────────────────────────────────────────────────────
const BROKERS = ['SCB', 'Dime', 'IBKR', 'Bitkub', 'Binance', 'Other'];

const inputStyle = {
  width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8, padding: '9px 14px', fontSize: 14, color: '#e8e8ea', outline: 'none',
};
const labelStyle = {
  fontSize: 11, fontWeight: 700, color: '#555558', textTransform: 'uppercase',
  letterSpacing: '0.08em', marginBottom: 6, display: 'block',
};

// ── Manual entry form ──
const ManualForm = ({ onClose, onSuccess }) => {
  const today = new Date().toISOString().split('T')[0];
  const [form, setForm] = useState({
    ticker: '', side: 'buy', quantity: '', price_per_share: '',
    price_ccy: 'THB', broker: 'Other', trade_date: today,
    fee: '', thb_amount: '', fx_thb_per_usd: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async () => {
    if (!form.ticker.trim()) { setError('Ticker is required'); return; }
    if (!form.quantity || Number(form.quantity) <= 0) { setError('Quantity must be > 0'); return; }
    setError(''); setSubmitting(true);
    try {
      await api.post('/transactions', {
        ticker: form.ticker.trim().toUpperCase(), side: form.side,
        quantity: Number(form.quantity),
        price_per_share: form.price_per_share ? Number(form.price_per_share) : null,
        price_ccy: form.price_ccy, broker: form.broker,
        trade_date: form.trade_date || today, fee: Number(form.fee) || 0,
        thb_amount: form.thb_amount ? Number(form.thb_amount) : null,
        fx_thb_per_usd: form.fx_thb_per_usd ? Number(form.fx_thb_per_usd) : null,
      });
      onSuccess(); onClose();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to add transaction');
    } finally { setSubmitting(false); }
  };

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Ticker + Side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 14 }}>
        <div>
          <label style={labelStyle}>Ticker</label>
          <input style={inputStyle} placeholder="e.g. CPALL.BK, AAPL" value={form.ticker}
            onChange={e => set('ticker', e.target.value.toUpperCase())} />
        </div>
        <div>
          <label style={labelStyle}>Side</label>
          <div style={{ display: 'flex', gap: 6 }}>
            {['buy', 'sell'].map(s => (
              <button key={s} onClick={() => set('side', s)}
                style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid', fontSize: 13, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
                  ...(form.side === s
                    ? s === 'buy' ? { background: 'rgba(74,222,128,0.15)', borderColor: 'rgba(74,222,128,0.4)', color: '#4ade80' }
                                  : { background: 'rgba(248,113,113,0.15)', borderColor: 'rgba(248,113,113,0.4)', color: '#f87171' }
                    : { background: 'transparent', borderColor: 'rgba(255,255,255,0.08)', color: '#555558' })
                }}>{s.charAt(0).toUpperCase() + s.slice(1)}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Date + Broker */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div>
          <label style={labelStyle}>Date</label>
          <input type="date" style={inputStyle} value={form.trade_date} onChange={e => set('trade_date', e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Broker</label>
          <select style={{ ...inputStyle, cursor: 'pointer' }} value={form.broker} onChange={e => set('broker', e.target.value)}>
            {BROKERS.map(b => <option key={b} value={b} style={{ background: '#18181c' }}>{b}</option>)}
          </select>
        </div>
      </div>

      {/* Qty + Price + Currency */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 14 }}>
        <div>
          <label style={labelStyle}>Quantity</label>
          <input type="number" min="0" step="any" style={inputStyle} placeholder="0" value={form.quantity} onChange={e => set('quantity', e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Price / Share</label>
          <input type="number" min="0" step="any" style={inputStyle} placeholder="0.00" value={form.price_per_share} onChange={e => set('price_per_share', e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Ccy</label>
          <select style={{ ...inputStyle, width: 80, cursor: 'pointer' }} value={form.price_ccy} onChange={e => set('price_ccy', e.target.value)}>
            {['THB', 'USD'].map(c => <option key={c} value={c} style={{ background: '#18181c' }}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* THB Total + FX + Fee */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div>
          <label style={labelStyle}>THB Total (optional)</label>
          <input type="number" min="0" step="any" style={inputStyle} placeholder="Overrides price×qty" value={form.thb_amount} onChange={e => set('thb_amount', e.target.value)} />
        </div>
        {form.price_ccy === 'USD' ? (
          <div>
            <label style={labelStyle}>FX Rate (THB/USD)</label>
            <input type="number" min="0" step="any" style={inputStyle} placeholder="e.g. 33.5" value={form.fx_thb_per_usd} onChange={e => set('fx_thb_per_usd', e.target.value)} />
          </div>
        ) : (
          <div>
            <label style={labelStyle}>Fee</label>
            <input type="number" min="0" step="any" style={inputStyle} placeholder="0.00" value={form.fee} onChange={e => set('fee', e.target.value)} />
          </div>
        )}
      </div>
      {form.price_ccy === 'USD' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <label style={labelStyle}>Fee</label>
            <input type="number" min="0" step="any" style={inputStyle} placeholder="0.00" value={form.fee} onChange={e => set('fee', e.target.value)} />
          </div>
        </div>
      )}

      {error && <p style={{ fontSize: 13, color: '#f87171', padding: '10px 14px', background: 'rgba(248,113,113,0.08)', borderRadius: 8, border: '1px solid rgba(248,113,113,0.15)' }}>{error}</p>}

      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 4 }}>
        <button onClick={onClose} style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'transparent', color: '#888890', fontSize: 13, cursor: 'pointer' }}
          className="hover:text-white hover:border-white/20 transition-colors">Cancel</button>
        <button onClick={handleSubmit} disabled={submitting}
          style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: submitting ? 'rgba(212,255,0,0.5)' : '#d4ff00', color: '#000', fontSize: 13, fontWeight: 700, cursor: submitting ? 'not-allowed' : 'pointer' }}>
          {submitting ? 'Saving…' : `Confirm ${form.side === 'buy' ? 'Buy' : 'Sell'}`}
        </button>
      </div>
    </div>
  );
};

// ── OCR / Photo scan form ──
const ScanPhotoForm = ({ onClose, onSuccess }) => {
  const [rows, setRows] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);

  useEffect(() => {
    return () => { if (imageUrl) URL.revokeObjectURL(imageUrl); };
  }, [imageUrl]);

  const processFile = async (file) => {
    if (!file) return;
    // Create preview URL before async OCR
    const url = URL.createObjectURL(file);
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setImageUrl(url);
    setError(''); setScanning(true); setRows(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post('/ocr/parse', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const parsed = (res.data.transactions || []).filter(t => t.side === 'buy' || t.side === 'sell');
      if (parsed.length === 0) { setError('No buy/sell transactions found in image.'); }
      else { setRows(parsed.map(t => ({ ...t, broker: 'Dime', fee: 0, selected: true }))); }
    } catch (e) {
      setError(e.response?.data?.detail || 'OCR failed. Try a clearer screenshot.');
    } finally { setScanning(false); }
  };

  const resetScan = () => {
    setRows(null); setError('');
    if (imageUrl) { URL.revokeObjectURL(imageUrl); setImageUrl(null); }
  };

  const handleDrop = (e) => { e.preventDefault(); setDragOver(false); processFile(e.dataTransfer.files[0]); };
  const handleFileInput = (e) => processFile(e.target.files[0]);
  const setRowField = (i, k, v) => setRows(prev => prev.map((r, idx) => idx === i ? { ...r, [k]: v } : r));

  const handleImport = async () => {
    const selected = rows.filter(r => r.selected);
    if (selected.length === 0) { setError('Select at least one transaction.'); return; }
    setError(''); setImporting(true);
    try {
      await api.post('/ocr/import', {
        transactions: selected.map(r => ({
          ticker: r.ticker, side: r.side, quantity: Number(r.quantity),
          price_per_share: r.price ? Number(r.price) : null,
          price_ccy: r.price_currency || 'USD', broker: r.broker || 'Dime',
          trade_date: r.trade_date, fee: Number(r.fee) || 0,
          thb_amount: r.total_amount ? Number(r.total_amount) : null,
        })),
      });
      onSuccess(); onClose();
    } catch (e) {
      setError(e.response?.data?.detail || 'Import failed');
    } finally { setImporting(false); }
  };

  const cellInput = { background: 'transparent', border: 'none', outline: 'none', color: '#e8e8ea', fontSize: 13, width: '100%', fontFamily: 'inherit' };

  // Side-by-side layout when image + results are ready
  const showSplit = imageUrl && (rows || scanning);

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Drop zone — only shown when no image yet */}
      {!imageUrl && (
        <div
          onDrop={handleDrop} onDragOver={e => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)}
          onClick={() => document.getElementById('ocr-file-input').click()}
          style={{ border: `2px dashed ${dragOver ? '#d4ff00' : 'rgba(255,255,255,0.12)'}`, borderRadius: 12, padding: '40px 24px', textAlign: 'center', cursor: 'pointer', transition: 'border-color 0.15s', background: dragOver ? 'rgba(212,255,0,0.03)' : 'transparent' }}>
          <input id="ocr-file-input" type="file" accept="image/png,image/jpeg" style={{ display: 'none' }} onChange={handleFileInput} />
          <div style={{ fontSize: 28, marginBottom: 10 }}>📸</div>
          <p style={{ fontSize: 14, fontWeight: 600, color: '#e8e8ea', marginBottom: 4 }}>Drop a Dime screenshot here</p>
          <p style={{ fontSize: 12, color: '#555558' }}>PNG or JPG — or click to browse</p>
        </div>
      )}

      {/* Split view: image preview + results */}
      {showSplit && (
        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16, alignItems: 'start' }}>
          {/* Photo panel */}
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)', flexShrink: 0 }}>
            <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#555558' }}>Source</span>
              <button onClick={resetScan} style={{ fontSize: 11, color: '#555558', background: 'transparent', border: 'none', cursor: 'pointer' }}
                className="hover:text-white transition-colors">Rescan</button>
            </div>
            <img src={imageUrl} alt="Uploaded screenshot"
              style={{ width: '100%', display: 'block', maxHeight: 480, objectFit: 'contain', background: '#0c0c0e' }} />
          </div>

          {/* Results panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
            {scanning ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '48px 0' }}>
                <RefreshCw size={20} color="#d4ff00" className="animate-spin" />
                <p style={{ fontSize: 13, color: '#888890' }}>Reading image with OCR…</p>
              </div>
            ) : rows && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <p style={{ fontSize: 13, fontWeight: 600, color: '#e8e8ea' }}>{rows.length} transaction{rows.length !== 1 ? 's' : ''} detected</p>
                  <button onClick={() => { /* allow re-upload while keeping split */ document.getElementById('ocr-file-input-split').click(); }}
                    style={{ fontSize: 12, color: '#888890', background: 'transparent', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                    Scan another
                  </button>
                  <input id="ocr-file-input-split" type="file" accept="image/png,image/jpeg" style={{ display: 'none' }} onChange={handleFileInput} />
                </div>

                <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid rgba(255,255,255,0.07)' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                        {['', 'Ticker', 'Side', 'Qty', 'Price', 'THB Total', 'Date'].map(h => (
                          <th key={h} style={{ padding: '9px 10px', textAlign: 'left', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#555558', whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', opacity: r.selected ? 1 : 0.4 }}>
                          <td style={{ padding: '7px 10px' }}>
                            <input type="checkbox" checked={r.selected} onChange={e => setRowField(i, 'selected', e.target.checked)} style={{ cursor: 'pointer', accentColor: '#d4ff00' }} />
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            <input style={{ ...cellInput, fontWeight: 600, width: 80 }} value={r.ticker} onChange={e => setRowField(i, 'ticker', e.target.value.toUpperCase())} />
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            <select value={r.side} onChange={e => setRowField(i, 'side', e.target.value)}
                              style={{ ...cellInput, width: 52, cursor: 'pointer', color: r.side === 'buy' ? '#4ade80' : '#f87171', background: '#18181c', border: 'none' }}>
                              <option value="buy" style={{ color: '#4ade80', background: '#18181c' }}>buy</option>
                              <option value="sell" style={{ color: '#f87171', background: '#18181c' }}>sell</option>
                            </select>
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            <input type="number" style={{ ...cellInput, width: 60 }} value={r.quantity} onChange={e => setRowField(i, 'quantity', e.target.value)} />
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            <input type="number" style={{ ...cellInput, width: 72 }} value={r.price} onChange={e => setRowField(i, 'price', e.target.value)} />
                          </td>
                          <td style={{ padding: '7px 10px' }}>
                            <input type="number" style={{ ...cellInput, width: 80 }} value={r.total_amount} onChange={e => setRowField(i, 'total_amount', e.target.value)} />
                          </td>
                          <td style={{ padding: '7px 10px', color: '#888890', whiteSpace: 'nowrap', fontSize: 12 }}>{r.trade_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {error && <p style={{ fontSize: 13, color: '#f87171', padding: '10px 14px', background: 'rgba(248,113,113,0.08)', borderRadius: 8, border: '1px solid rgba(248,113,113,0.15)' }}>{error}</p>}

      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 4 }}>
        <button onClick={onClose} style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'transparent', color: '#888890', fontSize: 13, cursor: 'pointer' }}>Cancel</button>
        {rows && (
          <button onClick={handleImport} disabled={importing}
            style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: importing ? 'rgba(212,255,0,0.5)' : '#d4ff00', color: '#000', fontSize: 13, fontWeight: 700, cursor: importing ? 'not-allowed' : 'pointer' }}>
            {importing ? 'Importing…' : `Import ${rows.filter(r=>r.selected).length} Trade${rows.filter(r=>r.selected).length !== 1 ? 's' : ''}`}
          </button>
        )}
      </div>
    </div>
  );
};

// ── Modal shell with tabs ──
const AddTransactionModal = ({ onClose, onSuccess }) => {
  const [tab, setTab] = useState('manual');
  const tabBtn = (id, label) => (
    <button key={id} onClick={() => setTab(id)}
      style={{ padding: '6px 16px', borderRadius: 6, border: 'none', fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s',
        background: tab === id ? 'rgba(255,255,255,0.08)' : 'transparent',
        color: tab === id ? '#e8e8ea' : '#555558' }}>
      {label}
    </button>
  );

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 24 }}>
      <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }} transition={{ duration: 0.15 }}
        style={{ background: '#18181c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, width: '100%', maxWidth: tab === 'scan' ? 860 : 480, maxHeight: '90vh', overflowY: 'auto' }}>

        {/* Header */}
        <div style={{ padding: '18px 24px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {tabBtn('manual', 'Manual Entry')}
            {tabBtn('scan', 'Scan Photo')}
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#888890', padding: 4, display: 'flex', borderRadius: 6 }}
            className="hover:text-white hover:bg-white/5 transition-colors"><X size={16} /></button>
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.1 }}>
            {tab === 'manual'
              ? <ManualForm onClose={onClose} onSuccess={onSuccess} />
              : <ScanPhotoForm onClose={onClose} onSuccess={onSuccess} />}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

// ─── App Shell ────────────────────────────────────────────────────────────────
const tabs = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'holdings',  label: 'Holdings',  icon: Briefcase },
  { id: 'analysis',  label: 'Analysis',  icon: PieChart },
  { id: 'discovery', label: 'Discovery', icon: Search },
  { id: 'settings',  label: 'Settings',  icon: Settings },
];

export default function App() {
  const [active, setActive] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleTransactionSuccess = useCallback(() => setRefreshKey(k => k + 1), []);

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0c0c0e', color: '#e8e8ea' }}>
      <AnimatePresence>
        {addOpen && <AddTransactionModal onClose={() => setAddOpen(false)} onSuccess={handleTransactionSuccess} />}
      </AnimatePresence>
      {/* Sidebar */}
      <aside style={{ width: sidebarOpen ? 200 : 52, flexShrink: 0, background: '#0f0f11', borderRight: '1px solid rgba(255,255,255,0.07)', display: 'flex', flexDirection: 'column', transition: 'width 0.25s ease', overflow: 'hidden' }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px', height: 56, borderBottom: '1px solid rgba(255,255,255,0.07)', flexShrink: 0 }}>
          <div style={{ width: 28, height: 28, background: '#d4ff00', borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#000', fontSize: 11, fontWeight: 900, flexShrink: 0 }}>VI</div>
          {sidebarOpen && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#e8e8ea', lineHeight: 1 }}>VI System</div>
              <div style={{ fontSize: 10, color: '#555558', marginTop: 3 }}>Intelligence</div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '10px 8px' }}>
          {tabs.map(({ id, label, icon: Icon }) => {
            const isActive = active === id;
            return (
              <button key={id} onClick={() => setActive(id)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, marginBottom: 2, cursor: 'pointer', border: 'none', background: isActive ? 'rgba(212,255,0,0.09)' : 'transparent', color: isActive ? '#d4ff00' : '#888890', fontSize: 13, fontWeight: isActive ? 600 : 400, transition: 'all 0.15s', textAlign: 'left', position: 'relative' }}
                className={isActive ? '' : 'hover:bg-white/5 hover:text-white'}>
                <Icon size={15} style={{ flexShrink: 0 }} />
                {sidebarOpen && <span>{label}</span>}
              </button>
            );
          })}
        </nav>

        {/* Status */}
        <div style={{ padding: '14px 16px', borderTop: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ade80', flexShrink: 0, display: 'inline-block' }} />
          {sidebarOpen && <span style={{ fontSize: 12, color: '#555558' }}>Connected</span>}
        </div>
      </aside>

      {/* Main */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        {/* Header */}
        <header style={{ height: 56, borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 40px', flexShrink: 0, background: '#0c0c0e' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button onClick={() => setSidebarOpen(v => !v)}
              style={{ padding: 6, borderRadius: 8, background: 'transparent', border: 'none', cursor: 'pointer', color: '#888890', display: 'flex' }}
              className="hover:bg-white/5 hover:text-white transition-colors">
              <Menu size={16} />
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
              <span style={{ color: '#555558' }}>VI Terminal</span>
              <ChevronRight size={12} color="#333336" />
              <span style={{ fontWeight: 500, color: '#e8e8ea' }}>{tabs.find(t => t.id === active)?.label}</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => setAddOpen(true)}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: '#000', padding: '6px 14px', borderRadius: 8, border: 'none', background: '#d4ff00', cursor: 'pointer' }}>
              <Plus size={13} /> Add Trade
            </button>
            <button style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#888890', padding: '6px 14px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.07)', background: 'rgba(255,255,255,0.02)', cursor: 'pointer' }}
              className="hover:text-white hover:border-white/15 hover:bg-white/5 transition-colors">
              <RefreshCw size={12} /> Sync
            </button>
          </div>
        </header>

        {/* Content */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '36px 40px' }}>
          <div style={{ marginBottom: 24 }}>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: '#e8e8ea' }}>{tabs.find(t => t.id === active)?.label}</h1>
          </div>

          <AnimatePresence mode="wait">
            <motion.div key={active} {...fade}>
              {active === 'dashboard' && <Dashboard refreshKey={refreshKey} />}
              {active === 'holdings'  && <Holdings refreshKey={refreshKey} />}
              {active === 'analysis'  && <Analysis />}
              {active === 'discovery' && <Discovery />}
              {active === 'settings'  && (
                <div style={{ maxWidth: 420 }}>
                  <div className="card rounded-xl" style={{ padding: '24px 28px' }}>
                    <p style={{ fontSize: 14, fontWeight: 600, color: '#e8e8ea', marginBottom: 8 }}>Data Management</p>
                    <p style={{ fontSize: 13, color: '#888890', lineHeight: 1.6, marginBottom: 16 }}>Refresh local portfolio data or clear cached calculations.</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <button style={{ textAlign: 'left', padding: '12px 16px', fontSize: 13, borderRadius: 8, border: '1px solid rgba(255,255,255,0.07)', background: 'rgba(255,255,255,0.02)', color: '#e8e8ea', cursor: 'pointer' }}
                        className="hover:bg-white/5 transition-colors">
                        Sync All Transactions
                      </button>
                      <button style={{ textAlign: 'left', padding: '12px 16px', fontSize: 13, borderRadius: 8, border: '1px solid rgba(248,113,113,0.15)', background: 'rgba(248,113,113,0.05)', color: '#f87171', cursor: 'pointer' }}
                        className="hover:bg-red-500/10 transition-colors">
                        Purge Financial Cache
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
