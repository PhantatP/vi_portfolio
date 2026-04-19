import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Briefcase,
  PieChart,
  Search,
  Settings,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  Menu,
  X
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts';
import api from './api';

// Internal Components (I will split these later if needed)
const Dashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const res = await api.get('/dashboard');
        setData(res.data);
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboard();
  }, []);

  if (loading) return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-48 bg-white/5 rounded-lg animate-pulse" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[1, 2, 3].map(i => <div key={i} className="h-32 glass rounded-2xl animate-pulse" />)}
      </div>
    </div>
  );

  if (!data) return <div className="text-red-400 p-8 glass rounded-2xl">Error loading financial data. Please check backend.</div>;

  const topAsset = data.top_gainer ? data.top_gainer.ticker : 'N/A';
  const chartData = data.allocation
    ? Object.entries(data.allocation).map(([name, value]) => ({ name, value }))
    : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-16 pb-20"
    >
      <div className="flex flex-col gap-4 mb-4">
        <h2 className="text-4xl font-extrabold tracking-tight">Executive Summary</h2>
        <p className="text-gray-400 font-medium">Real-time performance analytics for your portfolio.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
        {/* Net Worth */}
        <motion.div whileHover={{ y: -5 }} className="glass p-12 rounded-[2.5rem] relative group border-white/5 neo-shadow min-h-[200px] flex flex-col justify-between transition-all">
          <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <TrendingUp size={110} className="text-primary" />
          </div>
          <div className="relative z-10">
            <p className="text-gray-500 text-xs font-black uppercase tracking-[0.2em] mb-5">Net Worth</p>
            <p className="text-6xl font-black text-white tracking-tighter leading-none mb-6">
              ฿ {data.total_val.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </p>
          </div>
          <div className="relative z-10 flex items-center gap-3 text-[10px] text-gray-500 font-black tracking-widest bg-white/5 w-fit px-5 py-2 rounded-full mt-auto">
            <div className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]" />
            LIVE ANALYTICS
          </div>
        </motion.div>

        {/* Unrealized Profit */}
        <motion.div whileHover={{ y: -5 }} className="glass p-12 rounded-[2.5rem] relative group border-white/5 min-h-[200px] flex flex-col justify-between transition-all">
          <div className="relative z-10">
            <p className="text-gray-500 text-xs font-black uppercase tracking-[0.2em] mb-5">Unrealized P/L</p>
            <p className={`text-6xl font-black tracking-tighter leading-none mb-6 ${data.total_profit >= 0 ? 'text-primary' : 'text-red-400'}`}>
              ฿ {data.total_profit.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </p>
          </div>
          <div className="relative z-10 flex items-center gap-4 mt-auto">
            <span className={`text-sm font-black px-6 py-2.5 rounded-full uppercase tracking-[0.1em] ${data.profit_pct >= 0 ? 'bg-primary/20 text-primary border border-primary/20' : 'bg-red-400/20 text-red-400 border border-red-400/20'}`}>
              {data.profit_pct >= 0 ? '+' : ''}{data.profit_pct.toFixed(1)}% Yield
            </span>
          </div>
        </motion.div>

        {/* Top Asset */}
        <motion.div whileHover={{ y: -5 }} className="glass p-12 rounded-[2.5rem] relative group border-white/5 min-h-[200px] flex flex-col justify-between transition-all">
          <div className="relative z-10">
            <p className="text-gray-500 text-xs font-black uppercase tracking-[0.2em] mb-5">Principal asset</p>
            <p className="text-6xl font-black text-white uppercase tracking-tighter leading-none mb-6">{topAsset}</p>
          </div>
          <div className="relative z-10 text-[11px] text-gray-500 font-black uppercase tracking-widest flex items-center gap-3 mt-auto">
            <ArrowUpRight size={20} className="text-primary" />
            Portfolio Core
          </div>
        </motion.div>
      </div>

      <div className="glass p-14 rounded-[3rem] border-white/5 min-h-[500px]">
        <div className="flex justify-between items-center mb-12">
          <h3 className="text-xl font-bold text-gray-200">Asset Distribution</h3>
          <div className="flex gap-2">
            <div className="bg-primary/10 border border-primary/20 px-4 py-2 rounded-xl text-primary text-xs font-bold uppercase tracking-widest">
              Value Breakdown
            </div>
          </div>
        </div>
        <div className="h-[450px] w-full mt-12 min-w-0">
          <ResponsiveContainer width="100%" height="100%" debounce={50}>
            <BarChart
              data={chartData}
              margin={{ top: 40, right: 30, left: 0, bottom: 40 }}
              barSize={40}
            >
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#d4ff00" stopOpacity={1} />
                  <stop offset="100%" stopColor="#d4ff00" stopOpacity={0.4} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="name"
                stroke="#555"
                fontSize={14}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#888', fontWeight: 800 }}
              />
              <YAxis
                stroke="#555"
                fontSize={14}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#888', fontWeight: 800 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(10, 10, 11, 0.95)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '32px',
                  backdropFilter: 'blur(30px)',
                  padding: '24px'
                }}
                itemStyle={{ color: '#d4ff00', fontWeight: 'bold' }}
                cursor={{ fill: 'rgba(255,255,255,0.03)' }}
              />
              <Bar
                dataKey="value"
                fill="url(#barGradient)"
                radius={[12, 12, 0, 0]}
                barSize={40}
                animationDuration={1500}
                animationEasing="ease-out"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  );
};

const Holdings = ({ holdingsData }) => {
  const [holdings, setHoldings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHoldings = async () => {
      try {
        const res = await api.get('/holdings');
        setHoldings(res.data);
      } catch (err) {
        console.error("Holdings fetch error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchHoldings();
  }, []);

  if (loading) return (
    <div className="space-y-6">
      <div className="h-8 w-48 bg-white/5 rounded-lg animate-pulse" />
      <div className="h-[400px] glass rounded-3xl animate-pulse" />
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-16 pb-20"
    >
      <div className="flex flex-col gap-4">
        <h2 className="text-4xl font-extrabold tracking-tight">Active Holdings</h2>
        <p className="text-gray-400 font-medium">Manage your currently deployed assets across all sectors.</p>
      </div>

      <div className="glass rounded-[3rem] border-white/5 p-4 transition-all">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-white/5 text-gray-500 text-[10px] font-black uppercase tracking-[0.2em]">
              <th className="px-8 py-6">Asset Ticker</th>
              <th className="px-8 py-6">Quantity</th>
              <th className="px-8 py-6">Entry Price</th>
              <th className="px-8 py-6">Market Value</th>
              <th className="px-8 py-6">Performance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {holdings.map((h) => (
              <tr key={h.ticker} className="hover:bg-white/5 transition-colors group">
                <td className="px-8 py-8">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center text-primary font-bold text-sm">
                      {h.ticker[0]}
                    </div>
                    <span className="font-black text-xl text-white group-hover:text-primary transition-colors">{h.ticker}</span>
                  </div>
                </td>
                <td className="px-8 py-8 font-mono text-gray-300">{h.total_quantity?.toLocaleString()}</td>
                <td className="px-8 py-8 font-medium text-gray-300">฿ {h.avg_price_thb?.toLocaleString()}</td>
                <td className="px-8 py-8 font-black text-lg text-white">฿ {h.value_thb?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="px-8 py-8">
                  <div className="flex flex-col gap-1 items-start">
                    <span className={`text-lg font-black ${h.unrealized_pl_thb >= 0 ? 'text-primary' : 'text-red-400'}`}>
                      {h.unrealized_pl_thb >= 0 ? '+' : ''}฿ {Math.abs(h.unrealized_pl_thb)?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${h.unrealized_pl_pct >= 0 ? 'bg-primary/20 text-primary' : 'bg-red-400/20 text-red-400'}`}>
                      {(h.unrealized_pl_pct * 100).toFixed(1)}% Return
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
};

const Analysis = () => {
  const [dist, setDist] = useState([]);
  const [rebal, setRebal] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dRes, rRes] = await Promise.all([
          api.get('/analysis/distribution'),
          api.get('/analysis/rebalance')
        ]);
        setDist(dRes.data);
        setRebal(rRes.data);
      } catch (err) {
        console.error("Analysis fetch error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div className="h-96 glass rounded-3xl animate-pulse" />
      <div className="h-96 glass rounded-3xl animate-pulse" />
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-16 pb-20"
    >
      <div className="flex flex-col gap-4">
        <h2 className="text-4xl font-extrabold tracking-tight">Portfolio Optimization</h2>
        <p className="text-gray-400 font-medium">Algorithmic rebalancing and sector distribution matrix.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-14">
        {/* Rebalance List */}
        <div className="space-y-8">
          <h3 className="text-xs font-black text-gray-500 uppercase tracking-[0.3em] ml-4">Optimization Strategy</h3>
          <div className="space-y-6">
            {rebal.map(r => {
              const diff = r.difference_pct;
              return (
                <motion.div
                  key={r.ticker}
                  whileHover={{ x: 5 }}
                  className="flex justify-between items-center p-5 rounded-3xl bg-white/5 border border-white/5 hover:border-primary/20 transition-all group"
                >
                  <div>
                    <p className="text-xl font-black text-white group-hover:text-primary transition-colors uppercase tracking-tighter">{r.ticker}</p>
                    <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest mt-1">
                      {r.current_weight?.toFixed(1)}% <span className="text-gray-700 mx-1">→</span> {r.target_weight?.toFixed(1)}%
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={`text-lg font-black ${diff >= 0 ? 'text-primary' : 'text-red-400'}`}>
                      {diff >= 0 ? 'BUY' : 'SELL'} ฿ {Math.abs(r.diff_value_thb).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                    <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">{Math.abs(r.shares_to_buy).toFixed(2)} SHARES</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Distribution Summary */}
        <div className="glass p-10 rounded-[2.5rem] border-white/5 flex flex-col min-h-[500px]">
          <h3 className="text-xl font-bold mb-10">Sector Allocation</h3>
          <div className="flex-1 w-full space-y-8">
            {Array.from(new Set(dist.map(d => d.sector))).map(s => {
              const val = dist.filter(d => d.sector === s).reduce((acc, curr) => acc + curr.value_thb, 0);
              const total = dist.reduce((acc, curr) => acc + curr.value_thb, 0);
              const pct = total > 0 ? (val / total * 100).toFixed(1) : 0;
              return (
                <div key={s} className="space-y-3">
                  <div className="flex justify-between text-sm items-baseline">
                    <span className="text-gray-300 font-bold uppercase tracking-widest text-xs">{s}</span>
                    <span className="font-black text-xl text-primary tabular-nums">{pct}%</span>
                  </div>
                  <div className="h-3 bg-white/5 rounded-full overflow-hidden p-0.5 border border-white/5">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 1, ease: "circOut" }}
                      className="h-full bg-gradient-to-r from-primary/40 to-primary rounded-full shadow-[0_0_15px_rgba(212,255,0,0.4)]"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </motion.div>
  );
};

const Discovery = () => {
  const [search, setSearch] = useState('');
  const [picks, setPicks] = useState([]);
  const [sectors, setSectors] = useState({});
  const [research, setResearch] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchMeta = async () => {
      const [pRes, sRes] = await Promise.all([
        api.get('/discovery/smart-picks'),
        api.get('/discovery/sectors')
      ]);
      setPicks(pRes.data);
      setSectors(sRes.data);
    };
    fetchMeta();
  }, []);

  const performSearch = async (ticker) => {
    const t = ticker || search;
    if (!t) return;
    setLoading(true);
    setSearch(t);
    try {
      const res = await api.get(`/research/stock/${t}`);
      setResearch(res.data);
    } catch (err) {
      console.error("Research error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-16 pb-20"
    >
      <div className="flex flex-col gap-4">
        <h2 className="text-4xl font-extrabold tracking-tight">Market Intelligence</h2>
        <p className="text-gray-400 font-medium">Discover top-tier assets and analyze sector trends.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-14">
        {/* Search & Suggestions */}
        <div className="lg:col-span-2 space-y-10">
          <div className="glass p-12 rounded-[3.5rem] border-white/5 relative group transition-all">
            <div className="absolute -right-20 -top-20 w-80 h-80 bg-primary/5 rounded-full blur-3xl group-hover:bg-primary/10 transition-colors" />
            <h3 className="text-xs font-black text-gray-400 uppercase tracking-[0.3em] mb-10">Asset Discovery</h3>
            <div className="flex flex-col sm:flex-row gap-6">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.toUpperCase())}
                placeholder="ENTER TICKER (E.G. NVDA)"
                className="flex-1 bg-white/[0.03] border border-white/10 rounded-[2rem] px-10 py-6 outline-none focus:border-primary/50 focus:bg-white/10 transition-all font-black text-2xl tracking-tighter w-full"
                onKeyDown={(e) => e.key === 'Enter' && performSearch()}
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => performSearch()}
                className="bg-primary text-black px-14 py-6 rounded-[2rem] font-black text-base uppercase tracking-widest shadow-[0_20px_40px_rgba(212,255,0,0.3)] min-w-[200px]"
              >
                Analyze
              </motion.button>
            </div>
          </div>

          <div className="glass p-12 rounded-[3rem] border-white/5 transition-all">
            <h3 className="text-xs font-black text-gray-500 uppercase tracking-[0.3em] mb-10">Smart Suggestions</h3>
            <div className="flex flex-wrap gap-5">
              {picks.map(p => (
                <button
                  key={p}
                  onClick={() => performSearch(p)}
                  className="px-10 py-5 bg-white/[0.03] border border-white/10 rounded-[1.5rem] hover:border-primary/50 hover:bg-primary/5 transition-all font-black text-lg tracking-tighter uppercase"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Sector Explorer */}
        <div className="glass p-12 rounded-[3rem] border-white/5 overflow-y-auto max-h-[850px] shadow-inner transition-all">
          <h3 className="text-xs font-black text-gray-500 uppercase tracking-[0.3em] mb-10">Intelligence Catalog</h3>
          <div className="space-y-14 pr-4">
            {Object.entries(sectors).map(([sector, symbols]) => (
              <div key={sector} className="group">
                <p className="text-[12px] text-primary/60 mb-6 font-black uppercase tracking-[0.3em] transition-colors">{sector}</p>
                <div className="flex flex-wrap gap-4">
                  {symbols.map(s => (
                    <button
                      key={s}
                      onClick={() => performSearch(s)}
                      className="text-[12px] px-5 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:border-primary/50 hover:text-primary transition-all font-black uppercase tracking-tight"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-40 space-y-4">
          <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <p className="text-xs font-black text-gray-500 uppercase tracking-[0.3em]">Quantum Synthesis in Progress</p>
        </div>
      )}

      {research && !loading && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass p-16 pb-32 rounded-[4rem] border-white/5 space-y-20 shadow-2xl relative"
        >
          <div className="absolute top-10 right-16 opacity-5 select-none text-right">
            <div className="text-[12rem] font-black text-white leading-none">{research.info.symbol}</div>
          </div>

          <div className="flex justify-between items-start relative z-10 pt-4">
            <div className="space-y-6">
              <span className="text-[11px] font-black text-primary bg-primary/10 px-6 py-2 rounded-full tracking-[0.2em] uppercase border border-primary/20">
                📊 Fundamental Analysis
              </span>
              <div className="space-y-1">
                <h3 className="text-7xl font-black text-white tracking-tighter leading-tight drop-shadow-2xl">{research.info.longName}</h3>
                <p className="text-xl text-gray-500 font-bold uppercase tracking-widest">{research.info.sector} <span className="text-gray-800 mx-3">•</span> {research.info.industry}</p>
              </div>
            </div>
            <div className="text-right space-y-2 mt-4 pr-2">
              <p className="text-[10px] font-black text-gray-500 uppercase tracking-[0.3em]">Market Valuation</p>
              <p className="text-7xl font-black tracking-tighter text-white">฿ {research.info.currentPrice?.toLocaleString()}</p>
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 relative z-10">
            {[
              { label: 'Expectation (P/E)', val: research.info.forwardPE?.toFixed(2), icon: <LayoutDashboard size={18} /> },
              { label: 'Market Capital', val: research.info.marketCap ? `${(research.info.marketCap / 1e9).toFixed(1)}B` : 'N/A', icon: <Briefcase size={18} /> },
              { label: 'Dividend Potential', val: research.info.dividendYield ? `${(research.info.dividendYield * 100).toFixed(2)}%` : '0.00%', icon: <PieChart size={18} /> },
              { label: 'Volatility (Beta)', val: research.info.beta?.toFixed(2), icon: <TrendingUp size={18} /> }
            ].map(m => (
              <div key={m.label} className="bg-white/[0.03] p-10 rounded-[2.5rem] border border-white/5 group hover:border-primary/30 transition-all shadow-lg">
                <div className="text-gray-600 mb-6 group-hover:text-primary transition-colors">{m.icon}</div>
                <p className="text-[10px] text-gray-500 font-black uppercase tracking-[0.2em] mb-2">{m.label}</p>
                <p className="text-3xl font-black text-white tracking-tight">{m.val || 'N/A'}</p>
              </div>
            ))}
          </div>

          {/* Funnel */}
          {research.funnel && research.funnel["Total Revenue"] && (
            <div className="space-y-12 relative z-10 bg-white/[0.02] p-12 rounded-[3rem] border border-white/5">
              <h4 className="text-2xl font-black text-white tracking-tight flex items-center gap-4">
                <div className="w-8 h-1 bg-primary rounded-full" />
                Efficiency Metrics <span className="text-gray-600 font-bold text-sm ml-2 tracking-widest">PROJECTION {research.funnel.Date}</span>
              </h4>
              <div className="space-y-10">
                {[
                  { label: 'GROSS REVENUE', key: 'Total Revenue', color: 'bg-white/20' },
                  { label: 'GROSS MARGIN', key: 'Gross Profit', color: 'bg-primary/40' },
                  { label: 'OPERATING EDGE', key: 'Operating Income', color: 'bg-primary/70' },
                  { label: 'NET CONVERSION', key: 'Net Income', color: 'bg-primary' }
                ].map((step, idx) => {
                  const val = research.funnel[step.key];
                  const total = research.funnel["Total Revenue"];
                  const pct = (val / total * 100).toFixed(1);
                  if (!val) return null;
                  return (
                    <div key={step.key} className="space-y-4">
                      <div className="flex justify-between items-end px-2">
                        <span className="text-[11px] font-black uppercase tracking-[0.25em] text-gray-500">{step.label}</span>
                        <span className="font-black text-lg text-white">฿ {(val / 1e9).toFixed(2)}B <span className="text-primary ml-2 opacity-80">({pct}%)</span></span>
                      </div>
                      <div className="relative h-6 w-full bg-white/5 rounded-full overflow-hidden border border-white/5 shadow-inner">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 1.5, delay: idx * 0.1, ease: "circOut" }}
                          className={`h-full ${step.color} rounded-full shadow-[0_0_20px_rgba(212,255,0,0.2)]`}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="space-y-8 relative z-10 px-4">
            <h4 className="text-2xl font-black text-white tracking-tight flex items-center gap-4">
              <div className="w-8 h-1 bg-primary rounded-full" />
              Business Intelligence
            </h4>
            <p className="text-gray-400 leading-relaxed text-lg font-medium max-w-5xl">{research.info.summary}</p>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
};

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isSidebarOpen, setSidebarOpen] = useState(true);

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'holdings', label: 'Holdings', icon: Briefcase },
    { id: 'analysis', label: 'Analysis', icon: PieChart },
    { id: 'discovery', label: 'Discovery', icon: Search },
    { id: 'more', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen flex bg-background text-white selection:bg-primary/30 font-sans">
      {/* Sidebar */}
      <aside className={`w-72 glass-nav p-8 flex flex-col gap-12 transition-all duration-500 ease-in-out z-50 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full absolute md:relative'}`}>
        <div className="flex items-center gap-4 px-2">
          <div className="w-14 h-14 bg-primary rounded-3xl flex items-center justify-center text-black font-black text-2xl shadow-[0_0_30px_rgba(212,255,0,0.4)]">
            VI
          </div>
          <div className="flex flex-col">
            <span className="text-2xl font-black leading-none tracking-tighter">VI SYSTEM</span>
            <span className="text-[10px] text-primary font-black tracking-[0.3em] mt-1.5 ml-0.5 uppercase">Intelligence</span>
          </div>
        </div>

        <nav className="flex-1 space-y-3">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-5 px-6 py-5 rounded-3xl transition-all duration-300 relative group overflow-hidden ${isActive
                  ? 'text-black font-black'
                  : 'text-gray-500 hover:text-white hover:bg-white/5'
                  }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute inset-0 bg-primary shadow-[0_10px_30px_rgba(212,255,0,0.4)]"
                    transition={{ type: "spring", bounce: 0.1, duration: 0.6 }}
                  />
                )}
                <Icon size={24} className={`relative z-10 transition-transform duration-300 group-hover:scale-110 ${isActive ? 'text-black' : 'text-gray-500 group-hover:text-primary'}`} />
                <span className="relative z-10 text-sm font-bold tracking-wide uppercase">{tab.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-8 glass rounded-[2.5rem] border-white/5 relative overflow-hidden group">
          <div className="absolute -right-4 -bottom-4 w-32 h-32 bg-primary/5 rounded-full blur-3xl group-hover:bg-primary/10 transition-colors" />
          <p className="text-[10px] text-gray-600 uppercase font-black tracking-widest mb-4">Core Status</p>
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse shadow-[0_0_15px_rgba(34,197,94,0.6)]" />
            <span className="text-xs font-black text-gray-400 tracking-wider">SYNCED</span>
          </div>
        </div>
      </aside>

      {/* Main Content Container */}
      <main className="flex-1 h-screen overflow-y-auto overflow-x-hidden relative flex flex-col items-center">
        {/* Header centered with content */}
        <header className="sticky top-0 z-40 backdrop-blur-3xl border-b border-white/5 px-12 py-8 flex justify-between items-center w-full max-w-[1300px]">
          <div className="flex items-center gap-8">
            <button
              onClick={() => setSidebarOpen(!isSidebarOpen)}
              className="p-4 hover:bg-white/5 rounded-3xl transition-colors border border-white/10 group"
            >
              <Menu size={24} className="text-gray-400 group-hover:text-primary transition-colors" />
            </button>
            <div className="h-8 w-[1.5px] bg-white/10" />
            <h1 className="text-xs font-black text-gray-500 uppercase tracking-[0.4em] select-none">
              VI <span className="text-white">TERMINAL</span> <span className="text-primary opacity-50 ml-1">v2.1</span>
            </h1>
          </div>

          <div className="flex items-center gap-6">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="glass px-10 py-4 rounded-[1.5rem] text-[10px] font-black uppercase tracking-[0.2em] border-primary/20 text-primary hover:bg-primary hover:text-black hover:border-primary transition-all flex items-center gap-3 group"
            >
              <div className="w-2 h-2 bg-primary group-hover:bg-black rounded-full" />
              Synchronize
            </motion.button>
          </div>
        </header>

        <div className="p-12 w-full max-w-[1300px] min-h-[calc(100vh-112px)]">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.4, ease: "circOut" }}
            >
              {activeTab === 'dashboard' && <Dashboard />}
              {activeTab === 'holdings' && <Holdings />}
              {activeTab === 'analysis' && <Analysis />}
              {activeTab === 'discovery' && <Discovery />}
              {activeTab === 'more' && (
                <div className="space-y-10">
                  <h2 className="text-4xl font-extrabold tracking-tight">Settings</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="glass p-10 rounded-[2.5rem] border-white/5 space-y-6">
                      <h3 className="text-xl font-bold">Data Management</h3>
                      <p className="text-gray-400 text-sm leading-relaxed">Refresh your local portfolio engine and clear calculated caches.</p>
                      <div className="space-y-3">
                        <button className="w-full bg-white/5 border border-white/5 p-5 rounded-3xl text-left hover:bg-white/10 hover:border-white/10 transition-all font-bold text-sm">
                          🔄 Sync All Transactions
                        </button>
                        <button className="w-full bg-red-400/5 border border-red-400/10 p-5 rounded-3xl text-left hover:bg-red-400/10 transition-all font-bold text-sm text-red-400">
                          🧹 Purge Financial Cache
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
};

export default App;
