import { useState, useEffect } from 'react';
import { apiService } from '@services';
import { websocketService } from '@services/websocket';
import { Sparkles, RefreshCw, Mail, Shield, AlertCircle, Clock, CheckCircle2, User, ChevronRight, Brain } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Briefing } from '@types';

const BRAND_NAME = "EXECUTIVE BRAIN";
const SUBTITLE = "Strategic Intelligence Feed";
const ITEMS_PER_PAGE = 5;

export const App = () => {
  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [account, setAccount] = useState<string>('Syncing...');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filterCategory, setFilterCategory] = useState<'All' | 'Security' | 'Financial' | 'General'>('All');
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [showSentinelToast, setShowSentinelToast] = useState(false);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [activeEmail, setActiveEmail] = useState<string | null>(null);

  const requestNotificationPermission = async () => {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") {
      const permission = await Notification.requestPermission();
      if (permission === "granted") {
        setNotificationsEnabled(true);
        triggerToast();
      }
    } else {
      setNotificationsEnabled(true);
      triggerToast();
    }
  };

  const triggerToast = () => {
    setShowSentinelToast(true);
    setTimeout(() => setShowSentinelToast(false), 3000);
  };

  const triggerSentinelAlert = (briefing: Briefing) => {
    if (notificationsEnabled && briefing.should_alert) {
      new Notification(`⚠️ ${BRAND_NAME} Sentinel Alert`, {
        body: `[${briefing.account}] ${briefing.subject} - ${briefing.summary.substring(0, 80)}...`,
        icon: "/vite.svg"
      });
    }
  };

  const fetchEmails = async () => {
    // Note: We avoid setting full loading:true during background polling for smoothness
    try {
      const [emailData, accountsData] = await Promise.all([
        apiService.listEmails(),
        apiService.listAccounts()
      ]);

      // Map DB schema to UI Briefing model
      const mapped: Briefing[] = (emailData || []).map((e: any) => ({
        account: accountsData.accounts?.[0] || 'Primary',
        subject: e.subject || 'No Subject',
        sender: e.sender || 'Unknown',
        date: new Date(e.date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
        priority: 'Medium',
        category: 'General',
        should_alert: false,
        summary: e.body || 'Email content delivered. Awaiting strategic processing.',
        action: 'Review Pending'
      }));

      setBriefings(mapped);
      setAccounts(accountsData.accounts || []);
      if (accountsData.accounts?.[0] && !activeEmail) {
        setAccount(accountsData.accounts[0]);
      }
      setError(null);
    } catch (err: any) {
      console.warn("📡 [STRATEGY] Link degraded, maintaining last known state.");
      if (briefings.length === 0) {
        setError("Connection Failure: API is unreachable.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmails(); // Initial load

    // Realtime updates via WebSocket
    const handleEmailsUpdated = (data: { count: number; timestamp: string }) => {
      console.log("[STRATEGY] Realtime update received:", data);
      fetchEmails(); // Refresh email list
    };

    websocketService.on("emails_updated", handleEmailsUpdated);

    // Fallback polling (30s) for redundancy
    const interval = setInterval(fetchEmails, 30000);

    return () => {
      websocketService.off("emails_updated", handleEmailsUpdated);
      clearInterval(interval);
    };
  }, []);

  const getPriorityStyles = (priority: string) => {
    switch (priority) {
      case 'High': return 'text-rose-500 bg-rose-600/20 border-rose-600/30 font-black shadow-[0_0_15px_rgba(225,29,72,0.2)]';
      case 'Medium': return 'text-amber-400 bg-amber-500/10 border-amber-500/20 shadow-[0_0_15px_rgba(245,158,11,0.1)]';
      case 'Low': return 'text-slate-400 bg-slate-500/10 border-slate-500/20 shadow-none';
      default: return 'text-slate-500 bg-slate-500/10 border-slate-500/20';
    }
  };

  const getCategoryStyles = (category: string) => {
    switch (category) {
      case 'Security': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'Financial': return 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20';
      default: return 'text-slate-400 bg-white/5 border-white/10';
    }
  };

  const filteredBriefings = filterCategory === 'All'
    ? briefings
    : briefings.filter(b => b.category === filterCategory);

  const currentItems = filteredBriefings.slice((currentPage - 1) * ITEMS_PER_PAGE, currentPage * ITEMS_PER_PAGE);
  const totalPages = Math.ceil(filteredBriefings.length / ITEMS_PER_PAGE);

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-300 font-sans selection:bg-indigo-500/30 overflow-x-hidden">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-indigo-500/[0.03] blur-[120px] rounded-full animate-pulse" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-blue-500/[0.03] blur-[120px] rounded-full animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <header className="sticky top-0 z-50 border-b border-white/5 bg-[#0f172a]/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Brain className="text-white" size={20} />
            </div>
            <div>
              <h1 className="text-white font-bold tracking-tight text-lg">{BRAND_NAME}</h1>
              <div className="flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${error ? 'bg-rose-500' : 'bg-emerald-500'}`} />
                <p className={`text-[10px] uppercase tracking-[0.2em] font-bold ${error ? 'text-rose-500' : 'text-slate-500'}`}>
                  {error ? 'Sentinel Offline' : 'Sentinel Active'}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/5">
              <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Sentinel Alerts</span>
              <button
                onClick={() => notificationsEnabled ? setNotificationsEnabled(false) : requestNotificationPermission()}
                className={`w-10 h-5 rounded-full relative transition-colors duration-300 ${notificationsEnabled ? 'bg-indigo-600' : 'bg-slate-700'}`}
              >
                <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all duration-300 ${notificationsEnabled ? 'left-6' : 'left-1'}`} />
              </button>
            </div>

            {accounts.length > 1 && (
              <div className="hidden lg:flex items-center gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/5">
                {accounts.map((email) => (
                  <button
                    key={email}
                    onClick={() => {
                      setActiveEmail(email);
                      fetchEmails();
                    }}
                    className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all ${activeEmail === email || account.includes(email)
                      ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30'
                      : 'text-slate-500 hover:text-slate-300'
                      }`}
                  >
                    {email.split('@')[0]}
                  </button>
                ))}
              </div>
            )}

            <div className="hidden lg:flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10">
              <User size={14} className="text-indigo-400" />
              <span className="text-sm font-medium text-slate-400 truncate max-w-[150px]">{account}</span>
            </div>

            <button
              onClick={() => { setLoading(true); fetchEmails(); }}
              disabled={loading}
              className="group flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-bold transition-all shadow-xl shadow-indigo-600/20 active:scale-95"
            >
              <RefreshCw size={18} className={`${loading ? 'animate-spin' : 'group-hover:rotate-180'} transition-transform duration-700`} />
              {loading ? 'Analyzing...' : 'Refresh Intel'}
            </button>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {showSentinelToast && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-10 left-1/2 z-[100] px-6 py-3 rounded-2xl bg-indigo-600 text-white font-black text-xs uppercase tracking-[0.2em] shadow-2xl shadow-indigo-500/40 border border-white/10 flex items-center gap-3"
          >
            <Shield size={16} />
            Sentinel Defense Online
          </motion.div>
        )}
      </AnimatePresence>

      <main className="relative max-w-7xl mx-auto px-6 py-16">
        <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="text-center lg:text-left">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-black uppercase tracking-[0.2em] mb-6"
            >
              <Sparkles size={14} />
              <span>Hardened Shell 1.0</span>
            </motion.div>
            <h2 className="text-5xl lg:text-6xl font-black text-white tracking-tighter mb-4">
              {SUBTITLE}<span className="text-indigo-500">.</span>
            </h2>
            <p className="text-slate-400 text-lg max-w-xl font-medium leading-relaxed">
              Executive-grade email distillation with integrated security monitoring.
            </p>
          </div>

          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/[0.02] border border-white/5 backdrop-blur-sm">
            {['All', 'Security', 'Financial', 'General'].map((cat) => (
              <button
                key={cat}
                onClick={() => { setFilterCategory(cat as any); setCurrentPage(1); }}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${filterCategory === cat ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20' : 'text-slate-500 hover:text-slate-300'}`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="mb-12 p-6 rounded-3xl bg-rose-500/10 border border-rose-500/20 flex items-center gap-4 text-rose-400 shadow-2xl shadow-rose-900/10"
            >
              <AlertCircle size={22} className="flex-shrink-0" />
              <div className="flex-grow">
                <h4 className="font-bold text-base">Transmission Alert</h4>
                <p className="text-sm opacity-90">{error}</p>
              </div>
              <button onClick={() => fetchEmails()} className="px-4 py-2 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 transition-colors text-xs font-black uppercase tracking-widest">
                Re-Connect
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          <AnimatePresence mode="popLayout">
            {loading ? (
              [...Array(currentItems.length || ITEMS_PER_PAGE)].map((_, i) => (
                <motion.div
                  key={`skeleton-${i}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.4, delay: i * 0.1 }}
                  className="h-[480px] rounded-[2.5rem] bg-white/[0.02] border border-white/5 relative overflow-hidden p-10 flex flex-col"
                >
                  <div className="flex items-start justify-between mb-8">
                    <div className="flex flex-col gap-3">
                      <div className="w-24 h-5 rounded-full bg-white/5 animate-pulse" />
                      <div className="w-48 h-8 rounded-lg bg-white/5 animate-pulse" />
                    </div>
                  </div>
                  <div className="w-full h-12 rounded-xl bg-white/5 animate-pulse mb-6" />
                  <div className="w-2/3 h-6 rounded-lg bg-white/5 animate-pulse mb-10" />
                  <div className="flex-grow rounded-3xl bg-white/5 animate-pulse" />
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.015] to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
                </motion.div>
              ))
            ) : currentItems.length > 0 ? (
              currentItems.map((item, index) => (
                <motion.div
                  key={item.subject + index}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.4, delay: index * 0.05 }}
                  className="group relative flex flex-col h-[480px] p-10 rounded-[2.5rem] bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] hover:border-white/10 transition-all duration-500 shadow-2xl hover:shadow-indigo-500/5"
                >
                  <div className="flex items-start justify-between mb-8">
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-[0.15em] border transition-all duration-500 ${getPriorityStyles(item.priority)}`}>
                          {item.priority}
                        </div>
                        <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-[0.15em] border transition-all duration-500 ${getCategoryStyles(item.category)}`}>
                          {item.category}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-slate-500 text-xs font-bold bg-white/[0.03] px-3 py-1.5 rounded-lg border border-white/5">
                        <Clock size={14} className="text-indigo-400" />
                        {item.date}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-slate-500 text-[10px] font-black uppercase tracking-tighter">
                      <User size={14} className="text-indigo-400" /> {item.account}
                    </div>
                  </div>

                  <div className="mb-2">
                    <h3 className="text-2xl font-black text-white mb-2 tracking-tight line-clamp-2 leading-[1.2] group-hover:text-indigo-400 transition-colors duration-500">
                      {item.subject}
                    </h3>
                    <p className="text-slate-400 text-sm font-bold mb-6 flex items-center gap-2">
                      <span className="text-indigo-500 opacity-50 uppercase tracking-widest text-[10px]">Source</span> {item.sender.split('<')[0].trim()}
                    </p>
                  </div>

                  <div className="space-y-4 flex-grow overflow-y-auto custom-scrollbar pr-2">
                    <div className="p-5 rounded-3xl bg-white/[0.03] border border-white/5 group-hover:bg-white/[0.05] transition-colors duration-500">
                      <p className="text-sm leading-relaxed text-slate-200 font-medium overflow-wrap-anywhere word-break-break-word">
                        {item.summary}
                      </p>
                    </div>

                    <div className={`flex items-center gap-4 p-4 rounded-3xl border transition-all duration-500 ${item.action === 'None' ? 'bg-slate-500/5 border-slate-500/10' : 'bg-indigo-500/5 border-indigo-500/20 shadow-[0_0_20px_rgba(79,70,229,0.05)]'}`}>
                      <div className={`w-8 h-8 rounded-2xl flex items-center justify-center transition-colors duration-500 ${item.action === 'None' ? 'bg-slate-500/10 text-slate-500' : 'bg-indigo-500/10 text-indigo-400'}`}>
                        <CheckCircle2 size={16} />
                      </div>
                      <div className="min-w-0">
                        <p className={`text-[10px] font-black uppercase tracking-widest mb-0.5 ${item.action === 'None' ? 'text-slate-500' : 'text-indigo-400'}`}>Recommended Action</p>
                        <p className="text-xs font-bold text-slate-100 overflow-wrap-anywhere word-break-break-word">{item.action}</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-8 pt-6 border-t border-white/5 flex items-center justify-between">
                    <button
                      onClick={() => alert(`Strategic context expansion for "${item.subject}" is coming soon.`)}
                      className="text-[10px] font-black text-slate-500 hover:text-white uppercase tracking-[0.2em] flex items-center gap-2 transition-all group/btn"
                    >
                      Deep Dive <ChevronRight size={14} className="group-hover/btn:translate-x-1 transition-transform" />
                    </button>
                    <div className="flex items-center -space-x-2">
                      <div className="w-8 h-8 rounded-full bg-slate-800 border-2 border-[#0f172a] shadow-inner" />
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-600 border-2 border-[#0f172a] flex items-center justify-center text-[10px] font-black text-white shadow-lg">AI</div>
                    </div>
                  </div>
                </motion.div>
              ))
            ) : !error && (
              <div className="col-span-full py-32 flex flex-col items-center gap-6 text-center">
                <div className="w-24 h-24 rounded-full bg-white/[0.03] flex items-center justify-center text-slate-600 border border-white/5 relative shadow-inner">
                  <Mail size={40} className="text-indigo-500/20" />
                  <div className="absolute inset-0 rounded-full border border-indigo-500/10 animate-ping" />
                </div>
                <div>
                  <h3 className="text-2xl font-black text-white mb-2">{filterCategory} Channel Clear</h3>
                  <p className="text-slate-500 max-w-xs font-medium">No fresh briefings caught in the {filterCategory} filter.</p>
                </div>
              </div>
            )}
          </AnimatePresence>
        </div>

        {totalPages > 1 && !loading && (
          <div className="flex items-center justify-center gap-8 mt-4">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest"
            >
              Previous
            </button>
            <div className="flex flex-col items-center min-w-[120px]">
              <span className="text-[10px] font-black text-indigo-500 uppercase tracking-[0.2em] mb-1">Navigation</span>
              <span className="text-white font-black text-sm">{currentPage} of {totalPages}</span>
            </div>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest"
            >
              Next
            </button>
          </div>
        )}
      </main>

      <footer className="max-w-7xl mx-auto px-6 pt-32 pb-16">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8 border-t border-white/5 pt-12">
          <div className="flex items-center gap-2 text-slate-600">
            <Shield size={18} className="text-indigo-500/50" />
            <span className="text-[10px] font-black uppercase tracking-[0.3em]">Hardware Aligned Intelligence</span>
          </div>
          <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest opacity-50">© 2026 Executive Brain Ecosystem</p>
        </div>
      </footer>

      <style>{`
        @keyframes shimmer { 100% { transform: translateX(100%); } }
        .overflow-wrap-anywhere { overflow-wrap: anywhere; }
        .word-break-break-word { word-break: break-word; }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.02); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(79, 70, 229, 0.2); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(79, 70, 229, 0.4); }
      `}</style>
    </div>
  );
};

export default App;
