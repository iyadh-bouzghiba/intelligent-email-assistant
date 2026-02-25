import { useState, useEffect, useRef } from 'react';
import { apiService } from '@services';
import { websocketService } from '@services/websocket';
import { Sparkles, RefreshCw, Mail, Shield, AlertCircle, Clock, CheckCircle2, User, ChevronRight, Brain, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Briefing, AccountInfo } from '@types';

const BRAND_NAME = "EXECUTIVE BRAIN";
const SUBTITLE = "Strategic Intelligence Feed";
const ITEMS_PER_PAGE = 5;
const MAX_CONNECTED_ACCOUNTS = 3;

// Helper function: Generate color based on email
const getAccountColor = (email: string): string => {
  const colors = [
    'from-blue-500 to-indigo-600',
    'from-purple-500 to-pink-600',
    'from-emerald-500 to-teal-600',
    'from-amber-500 to-orange-600',
    'from-rose-500 to-red-600',
    'from-cyan-500 to-blue-600',
  ];
  const hash = email.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
};

// Helper function: Get initials from email
const getEmailInitials = (email: string): string => {
  if (!email || email === 'default') return '?';
  const username = email.split('@')[0];
  if (username.length === 1) return username.toUpperCase();
  // Take first letter + first letter after dot/underscore
  const parts = username.split(/[._-]/);
  if (parts.length > 1) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return username.substring(0, 2).toUpperCase();
};

export const App = () => {
  const [briefings, setBriefings] = useState<Briefing[]>([]);
  const [account, setAccount] = useState<string>('Syncing...');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filterCategory, setFilterCategory] = useState<'All' | 'Security' | 'Financial' | 'General'>('All');
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [showSentinelToast, setShowSentinelToast] = useState(false);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [activeEmail, setActiveEmail] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState<string | null>(null);
  const [showAccountMenu, setShowAccountMenu] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  const accountButtonRef = useRef<HTMLButtonElement | null>(null);
  const activeEmailRef = useRef<string | null>(null); // Track current activeEmail for closures
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);

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

  const fetchEmails = async (overrideAccountId?: string | null) => {
    // Note: We avoid setting full loading:true during background polling for smoothness
    const accountIdToUse = overrideAccountId !== undefined ? overrideAccountId : activeEmail;
    try {
      const [emailData, accountsData] = await Promise.all([
        apiService.listEmails(accountIdToUse ?? undefined),
        apiService.listAccounts()
      ]);

      // Sort emails by date descending (newest first)
      const sorted = (emailData || []).sort((a: any, b: any) => {
        const dateA = Date.parse(a.date ?? a.created_at ?? '0');
        const dateB = Date.parse(b.date ?? b.created_at ?? '0');
        return dateB - dateA;
      });

      const loadedAccounts: AccountInfo[] = accountsData.accounts || [];

      // Fetch AI summaries for emails (in parallel)
      const apiBase = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") || "";
      const effectiveAccountId = accountIdToUse || "default";

      const emailsWithSummaries = await Promise.all(
        sorted.map(async (email: any) => {
          if (!email.gmail_message_id) return email;

          try {
            const summaryResponse = await fetch(
              `${apiBase}/api/emails/${encodeURIComponent(email.gmail_message_id)}/summary?account_id=${effectiveAccountId}`
            );
            const summary = await summaryResponse.json();

            if (summary.status === "ready") {
              return {
                ...email,
                ai_summary_json: summary.summary_json,
                ai_summary_text: summary.summary_text,
                ai_summary_model: summary.model
              };
            }
          } catch (err) {
            console.warn(`Failed to fetch summary for ${email.gmail_message_id}`);
          }

          return email;
        })
      );

      // Map DB schema to UI Briefing model
      const mapped: Briefing[] = emailsWithSummaries.map((e: any) => {
        const isoDate = e.date ?? e.created_at;
        let formattedDate = 'Unknown time';
        try {
          if (isoDate) {
            formattedDate = new Date(isoDate).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
          }
        } catch {
          // Fallback already set
        }

        // CRITICAL: Determine priority from AI urgency if available
        let priority: 'Low' | 'Medium' | 'High' = 'Medium';
        if (e.ai_summary_json?.urgency === 'high') priority = 'High';
        else if (e.ai_summary_json?.urgency === 'low') priority = 'Low';

        // Use AI overview if available, fallback to raw body
        const displaySummary = e.ai_summary_text || e.body || 'Awaiting strategic processing.';

        // Use first action item as primary action if available
        const primaryAction = e.ai_summary_json?.action_items?.[0] || 'Review Pending';

        return {
          account: e.account_id || 'Unknown',  // CRITICAL: Use REAL account_id from email record
          subject: e.subject || 'No Subject',
          sender: e.sender || 'Unknown',
          date: formattedDate,
          priority: priority,
          category: 'General',
          should_alert: e.ai_summary_json?.urgency === 'high',
          summary: displaySummary,
          action: primaryAction,

          // NEW: Pass through AI summary fields for detailed display
          ai_summary_json: e.ai_summary_json,
          ai_summary_text: e.ai_summary_text,
          ai_summary_model: e.ai_summary_model,
          gmail_message_id: e.gmail_message_id,
        };
      });

      setBriefings(mapped);
      setAccounts(loadedAccounts);
      const firstConnected = loadedAccounts.find(a => a.connected);
      // CRITICAL: Check accountIdToUse (not activeEmail) to avoid race condition
      // When user explicitly selects an account, we must respect that choice
      if (firstConnected && !accountIdToUse) {
        setAccount(firstConnected.account_id);
        setActiveEmail(firstConnected.account_id);
      }
      setError(null);
      setConsecutiveFailures(0); // Reset on success
    } catch (err: any) {
      console.warn("📡 [STRATEGY] Link degraded, maintaining last known state.");
      setConsecutiveFailures((prev: number) => {
        const newFailureCount = prev + 1;

        if (briefings.length === 0) {
          // Show "Waking backend..." for first 5 failures, then show red error
          if (newFailureCount < 5) {
            setError("Waking backend… (reconnecting silently)");
          } else {
            setError("Connection Failure: API is unreachable after multiple attempts.");
          }
        }

        return newFailureCount;
      });
    } finally {
      setLoading(false);
    }
  };

  const autoSync = async () => {
    // Single-flight lock
    if (syncing) return;

    // Only run when tab is visible
    if (document.visibilityState !== 'visible') return;

    // CRITICAL: Skip auto-sync if no account is active (prevents "default" auth errors)
    if (!activeEmail) {
      console.log('[AUTO-SYNC] Skipped - no account selected');
      return;
    }

    setSyncing(true);

    try {
      // Preflight health check
      await apiService.checkHealth();

      // Execute sync
      const result = await apiService.syncNow(activeEmail);

      if (result.status === 'done' && result.count && result.count > 0) {
        console.log(`[AUTO-SYNC] Processed ${result.processed_count ?? result.count} emails`);
        // Refetch emails for active account to update UI
        await fetchEmails(activeEmail);
        // Reset failures on success
        setConsecutiveFailures(0);
      } else if (result.status === 'auth_required') {
        console.warn('[AUTO-SYNC] Auth required, skipping');
      }
    } catch (error) {
      console.warn('[AUTO-SYNC] Failed', error);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    // Initial load: Load accounts but DO NOT auto-select (user must choose)
    const initializeApp = async () => {
      try {
        const accountsData = await apiService.listAccounts();
        const loadedAccounts: AccountInfo[] = accountsData.accounts || [];
        setAccounts(loadedAccounts);

        // CRITICAL: Do NOT auto-select first account - user must explicitly choose
        // This provides professional UX where user is in control
        setLoading(false);
      } catch (error) {
        console.warn('[STRATEGY] Failed to load accounts on init', error);
        setLoading(false);
      }
    };

    initializeApp();

    // Note: autoSync removed from init - will sync when user selects account

    // Realtime updates via WebSocket
    const handleEmailsUpdated = (data: { count_new: number }) => {
      console.log("[STRATEGY] Realtime update received:", data);
      fetchEmails(activeEmailRef.current); // Refetch for current active account
    };

    const handleSummaryReady = (data: { count_summarized: number }) => {
      console.log("[STRATEGY] Summaries ready:", data);
      // Could refetch thread data if needed
    };

    // NEW: Handle real-time AI summary completion events
    const handleAiSummaryReady = (data: { account_id: string; gmail_message_id: string; timestamp: string }) => {
      console.log("[AI-SUMMARY] New summary ready:", data);

      // Only refresh if the summary is for the currently active account
      if (activeEmailRef.current === data.account_id || !activeEmailRef.current) {
        console.log("[AI-SUMMARY] Refreshing emails to show new summary");
        fetchEmails(activeEmailRef.current);
      }
    };

    websocketService.on("emails_updated", handleEmailsUpdated);
    websocketService.on("summary_ready", handleSummaryReady);
    websocketService.on("ai_summary_ready", handleAiSummaryReady);

    // Auto-sync scheduler (120s interval, respects visibility + backoff)
    const SYNC_INTERVAL = 120000; // 120s
    const autoSyncInterval = setInterval(() => {
      autoSync();
    }, SYNC_INTERVAL);

    // Visibility change handler - immediate sync when tab becomes visible
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Trigger immediate sync
        autoSync();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Note: Fallback polling removed - using WebSocket updates + activeEmail change detection instead

    return () => {
      websocketService.off("emails_updated", handleEmailsUpdated);
      websocketService.off("summary_ready", handleSummaryReady);
      websocketService.off("ai_summary_ready", handleAiSummaryReady);
      clearInterval(autoSyncInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (!showAccountMenu) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const menuEl = accountMenuRef.current;
      const btnEl = accountButtonRef.current;
      if (menuEl && menuEl.contains(target)) return;
      if (btnEl && btnEl.contains(target)) return;
      setShowAccountMenu(false);
    };
    document.addEventListener("mousedown", onMouseDown, true);
    return () => document.removeEventListener("mousedown", onMouseDown, true);
  }, [showAccountMenu]);

  // Refetch emails when active account changes
  useEffect(() => {
    activeEmailRef.current = activeEmail; // Keep ref in sync for closures
    if (activeEmail) {
      console.log(`[STRATEGY] Active account changed to: ${activeEmail}`);
      fetchEmails(activeEmail);
    }
  }, [activeEmail]);

  // Detect OAuth callback success and auto-activate the newly connected account
  // CRITICAL: Retry logic with exponential backoff to handle replication delays
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const authSuccess = urlParams.get('auth') === 'success';
    const newAccountId = urlParams.get('account_id'); // Backend passes URL-decoded email

    if (!authSuccess) return;

    console.log(`[OAUTH-CALLBACK] Detected - target account: ${newAccountId || 'MISSING'}`);

    // Clean up URL immediately to prevent re-triggering
    window.history.replaceState({}, document.title, window.location.pathname);

    if (!newAccountId) {
      console.error('[OAUTH-CALLBACK] CRITICAL: account_id parameter missing from callback URL');
      alert('OAuth completed but account information was lost. Please try connecting again.');
      return;
    }

    // Retry logic: Poll for account to appear (handles Supabase replication delay)
    const MAX_RETRIES = 5;
    const INITIAL_DELAY = 1000; // Start with 1s
    let retryCount = 0;

    const attemptActivation = async () => {
      retryCount++;
      const delay = INITIAL_DELAY * Math.pow(1.5, retryCount - 1); // Exponential backoff

      console.log(`[OAUTH-CALLBACK] Attempt ${retryCount}/${MAX_RETRIES} - checking for account: ${newAccountId}`);

      try {
        // Reload accounts from backend
        const accountsData = await apiService.listAccounts();
        const loadedAccounts: AccountInfo[] = accountsData.accounts || [];

        console.log(`[OAUTH-CALLBACK] Found ${loadedAccounts.length} accounts:`, loadedAccounts.map(a => a.account_id));

        setAccounts(loadedAccounts);

        // CRITICAL: Only activate if EXACT match found (no fallback)
        const targetAccount = loadedAccounts.find(a => a.account_id === newAccountId);

        if (targetAccount) {
          console.log(`[OAUTH-CALLBACK] ✅ SUCCESS - Activating: ${newAccountId}`);
          setActiveEmail(newAccountId);
          setAccount(newAccountId);
          return; // Success - stop retrying
        }

        // Account not found yet - retry if attempts remaining
        if (retryCount < MAX_RETRIES) {
          console.log(`[OAUTH-CALLBACK] ⏳ Account not found yet - retrying in ${delay}ms...`);
          setTimeout(attemptActivation, delay);
        } else {
          // Max retries exceeded - show error
          console.error(`[OAUTH-CALLBACK] ❌ FAILED - Account ${newAccountId} not found after ${MAX_RETRIES} attempts`);
          alert(`Failed to activate account ${newAccountId}.\n\nThe account was connected but couldn't be activated automatically.\n\nPlease select it manually from the account dropdown.`);
          // Leave user on account selection screen - don't auto-activate wrong account
        }
      } catch (error) {
        console.error(`[OAUTH-CALLBACK] Attempt ${retryCount} failed:`, error);
        if (retryCount < MAX_RETRIES) {
          setTimeout(attemptActivation, delay);
        } else {
          alert('Failed to load accounts after OAuth. Please refresh the page.');
        }
      }
    };

    // Start activation attempts
    attemptActivation();
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

  const handleDisconnect = async (account_id: string) => {
    setConfirmDisconnect(null);
    console.log(`[DISCONNECT] Disconnecting account: ${account_id}`);
    try {
      await apiService.disconnectAccount(account_id);
      console.log(`[DISCONNECT] Successfully disconnected: ${account_id}`);

      // CRITICAL: Reload accounts list from backend to reflect disconnect
      const accountsData = await apiService.listAccounts();
      const loadedAccounts: AccountInfo[] = accountsData.accounts || [];
      setAccounts(loadedAccounts);
      console.log(`[DISCONNECT] Reloaded ${loadedAccounts.length} accounts`);

      // If disconnected account was active, clear active email
      if (activeEmail === account_id) {
        setActiveEmail(null);
        setBriefings([]); // Clear emails since no account is active
        console.log(`[DISCONNECT] Cleared active account (was ${account_id})`);
      }
    } catch (err) {
      console.error('[DISCONNECT] Failed to disconnect account:', account_id, err);
      alert(`Failed to disconnect ${account_id}. Please try again.`);
    }
  };

  const connectedAccounts = accounts.filter(a => a.connected);
  const hasLegacyAccounts = connectedAccounts.some(a => a.account_id === 'default' || a.account_id === 'PRIMARY');

  const handleDisconnectAll = async () => {
    try {
      await apiService.disconnectAllAccounts();
      setAccounts([]);
      setActiveEmail(null);
      await fetchEmails();
    } catch (err) {
      console.error('[DISCONNECT-ALL] Failed:', err);
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
        <div className="max-w-7xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-3">
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

          <div className="flex items-center gap-3 flex-wrap justify-end min-w-0">
            <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/5">
              <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Sentinel Alerts</span>
              <button
                onClick={() => notificationsEnabled ? setNotificationsEnabled(false) : requestNotificationPermission()}
                className={`w-10 h-5 rounded-full relative transition-colors duration-300 ${notificationsEnabled ? 'bg-indigo-600' : 'bg-slate-700'}`}
              >
                <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all duration-300 ${notificationsEnabled ? 'left-6' : 'left-1'}`} />
              </button>
            </div>

            <div className="relative">
              {connectedAccounts.length === 0 ? (
                <a
                  href={apiService.getGoogleAuthUrl()}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 border border-indigo-500/50 text-white text-sm font-bold transition-all shadow-lg shadow-indigo-600/20 active:scale-95"
                >
                  <Mail size={16} />
                  <span>Connect Account</span>
                </a>
              ) : (
                <>
                  <button
                    ref={accountButtonRef}
                    onClick={(e) => { e.stopPropagation(); setShowAccountMenu(v => !v); }}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-slate-200 hover:bg-white/[0.05] transition-all min-w-0"
                  >
                    {activeEmail ? (
                      <>
                        <span className={`relative inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(activeEmail)} text-[10px] font-black text-white flex-shrink-0 shadow-lg`}>
                          {getEmailInitials(activeEmail)}
                          <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-[#0f172a]" />
                        </span>
                        <span className="hidden sm:inline text-[11px] font-bold text-slate-300 truncate max-w-[140px]">
                          {activeEmail.split('@')[0]}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-800 text-[10px] font-black text-slate-400 flex-shrink-0 shadow-lg">
                          ?
                        </span>
                        <span className="hidden sm:inline text-[11px] font-bold text-slate-500 truncate">
                          Select Account
                        </span>
                      </>
                    )}
                    <ChevronRight size={11} className={`transition-transform duration-200 ${showAccountMenu ? 'rotate-90' : ''}`} />
                  </button>
                  <AnimatePresence>
                    {showAccountMenu && (
                      <>
                      <div
                        className="fixed inset-0 z-[90] bg-black/40 sm:hidden"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setShowAccountMenu(false);
                        }}
                      />
                      <motion.div
                        ref={accountMenuRef}
                        onMouseDown={(e) => e.stopPropagation()}
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className="fixed left-4 right-4 top-24 w-auto rounded-2xl bg-[#0f172a] border border-white/10 shadow-2xl z-[100] overflow-hidden sm:absolute sm:left-auto sm:right-0 sm:top-full sm:mt-2 sm:w-56"
                      >
                        {/* CRITICAL: Show active account FIRST, then others */}
                        {connectedAccounts
                          .sort((a, b) => {
                            if (a.account_id === activeEmail) return -1;
                            if (b.account_id === activeEmail) return 1;
                            return 0;
                          })
                          .map((info) => {
                            const isActive = activeEmail === info.account_id;
                            return (
                              <div key={info.account_id} className={`flex items-center gap-3 px-4 py-3 hover:bg-white/[0.04] transition-colors ${isActive ? 'bg-indigo-500/10' : ''}`}>
                                <div className="relative">
                                  <div className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(info.account_id)} text-[10px] font-black text-white flex-shrink-0 shadow-md`}>
                                    {getEmailInitials(info.account_id)}
                                  </div>
                                  {/* ONLINE/OFFLINE indicator badge */}
                                  <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-[#0f172a] ${isActive ? 'bg-emerald-400' : 'bg-slate-600'}`}
                                        title={isActive ? 'Online (Active)' : 'Offline (Inactive)'} />
                                </div>
                                <button
                                  onClick={async () => {
                                    console.log(`[DROPDOWN] Switching to account: ${info.account_id}`);
                                    setActiveEmail(info.account_id);
                                    setShowAccountMenu(false);
                                    setLoading(true);
                                    try {
                                      // Trigger sync for selected account
                                      console.log(`[SYNC] Syncing account: ${info.account_id}`);
                                      const syncResult = await apiService.syncNow(info.account_id);
                                      console.log(`[SYNC] Sync result:`, syncResult);
                                      console.log(`[FETCH] Fetching emails for: ${info.account_id}`);
                                      await fetchEmails(info.account_id);
                                      console.log(`[DROPDOWN] Switched to ${info.account_id} successfully`);
                                    } catch (err) {
                                      console.error(`[DROPDOWN] Failed to switch to ${info.account_id}:`, err);
                                      alert(`Failed to load emails for ${info.account_id}. Check console for details.`);
                                    } finally {
                                      setLoading(false);
                                    }
                                  }}
                                  className={`text-[11px] font-bold truncate flex-1 text-left ${isActive ? 'text-indigo-400' : 'text-slate-300'}`}
                                >
                                  <div className="truncate">{info.account_id}</div>
                                  {isActive && (
                                    <div className="text-[9px] font-black text-emerald-400 uppercase tracking-wider mt-0.5">● Online</div>
                                  )}
                                  {!isActive && (
                                    <div className="text-[9px] font-bold text-slate-600 uppercase tracking-wider mt-0.5">○ Offline</div>
                                  )}
                                </button>
                                <button
                                  onClick={() => { setShowAccountMenu(false); setConfirmDisconnect(info.account_id); }}
                                  title={`Disconnect ${info.account_id}`}
                                  className="p-1.5 rounded-md text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-colors flex-shrink-0"
                                >
                                  <LogOut size={12} />
                                </button>
                              </div>
                            );
                          })}
                        <div className="border-t border-white/5 px-4 py-3">
                          {connectedAccounts.length >= MAX_CONNECTED_ACCOUNTS ? (
                            <p className="text-[10px] text-slate-500">Max accounts reached. Disconnect one to add another.</p>
                          ) : (
                            <a
                              href={apiService.getGoogleAuthUrl()}
                              className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                              + Connect another account
                            </a>
                          )}
                        </div>
                      </motion.div>
                      </>
                    )}
                  </AnimatePresence>
                </>
              )}
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

      <AnimatePresence>
        {hasLegacyAccounts && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="max-w-7xl mx-auto px-6 py-4 mt-4"
          >
            <div className="p-6 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-4">
              <AlertCircle size={24} className="text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h4 className="text-white font-bold text-base mb-2">⚠️ Legacy Accounts Detected</h4>
                <p className="text-amber-200 text-sm mb-4">
                  Your accounts use the old "default" system. To enable multi-account features with real email addresses and colored avatars, please disconnect and reconnect your accounts.
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={handleDisconnectAll}
                    className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-sm font-bold transition-all shadow-lg"
                  >
                    Disconnect All & Start Fresh
                  </button>
                  <a
                    href={apiService.getGoogleAuthUrl()}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-bold transition-all"
                  >
                    Reconnect First Account
                  </a>
                </div>
              </div>
            </div>
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
              className={`mb-12 p-6 rounded-3xl flex items-center gap-4 shadow-2xl ${
                consecutiveFailures >= 5
                  ? 'bg-rose-500/10 border border-rose-500/20 text-rose-400 shadow-rose-900/10'
                  : 'bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shadow-indigo-900/10'
              }`}
            >
              <AlertCircle size={22} className="flex-shrink-0" />
              <div className="flex-grow">
                <h4 className="font-bold text-base">
                  {consecutiveFailures >= 5 ? 'Transmission Alert' : 'Connecting...'}
                </h4>
                <p className="text-sm opacity-90">{error}</p>
              </div>
              {syncing && (
                <RefreshCw size={18} className="animate-spin opacity-50" />
              )}
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
                      {/* AI Summary Badge (only if AI summary exists) */}
                      {item.ai_summary_text && (
                        <div className="flex items-center gap-2 mb-3">
                          <Sparkles size={12} className="text-indigo-400" />
                          <span className="text-[9px] font-black text-indigo-400 uppercase tracking-wider">
                            AI Summary
                          </span>
                          <span className="text-[8px] text-slate-600">
                            {item.ai_summary_model || 'mistral'}
                          </span>
                        </div>
                      )}

                      {/* Summary Text (AI or fallback to raw body) */}
                      <p className="text-sm leading-relaxed text-slate-200 font-medium overflow-wrap-anywhere word-break-break-word">
                        {item.summary}
                      </p>

                      {/* Action Items (only if AI summary has action items) */}
                      {item.ai_summary_json?.action_items && item.ai_summary_json.action_items.length > 0 && (
                        <div className="mt-4 space-y-2">
                          <p className="text-[10px] font-black text-indigo-400 uppercase tracking-wider">
                            Action Items
                          </p>
                          <ul className="space-y-1.5">
                            {item.ai_summary_json.action_items.slice(0, 3).map((action: string, idx: number) => (
                              <li key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                                <span className="text-indigo-500 mt-0.5">•</span>
                                <span>{action}</span>
                              </li>
                            ))}
                          </ul>
                          {item.ai_summary_json.action_items.length > 3 && (
                            <p className="text-[9px] text-slate-600 italic mt-1">
                              +{item.ai_summary_json.action_items.length - 3} more action item{item.ai_summary_json.action_items.length - 3 > 1 ? 's' : ''}
                            </p>
                          )}
                        </div>
                      )}
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
                    <div className="flex items-center gap-3">
                      {/* NEW: Manual Summarization Button (only if no AI summary exists) */}
                      {!item.ai_summary_text && item.gmail_message_id && (
                        <button
                          onClick={async () => {
                            console.log('[SUMMARIZE] Requesting:', item.gmail_message_id);

                            // Optimistic UI update
                            const updatedBriefings = briefings.map(b =>
                              b.gmail_message_id === item.gmail_message_id
                                ? { ...b, summary: '⏳ Generating AI summary...' }
                                : b
                            );
                            setBriefings(updatedBriefings);

                            // Call API to enqueue summarization job
                            const result = await apiService.summarizeEmail(
                              item.gmail_message_id!,
                              activeEmail || 'default'
                            );

                            // Handle result
                            if (result.status === 'queued') {
                              console.log('[SUMMARIZE] Job queued:', result.job_id);
                              // Refresh after 5 seconds to show completed summary
                              setTimeout(() => fetchEmails(activeEmail), 5000);
                            } else if (result.status === 'no_mistral_key') {
                              alert('AI summarization requires MISTRAL_API_KEY configuration.');
                              setBriefings(briefings); // Revert optimistic update
                            } else {
                              console.warn('[SUMMARIZE] Failed:', result);
                              setBriefings(briefings); // Revert optimistic update
                            }
                          }}
                          className="text-[10px] font-black text-indigo-500 hover:text-indigo-400 uppercase tracking-[0.2em] flex items-center gap-2 transition-all group/btn"
                        >
                          <Sparkles size={14} className="group-hover/btn:rotate-12 transition-transform" />
                          Summarize Email
                        </button>
                      )}
                      <button
                        onClick={() => alert(`Strategic context expansion for "${item.subject}" is coming soon.`)}
                        className="text-[10px] font-black text-slate-500 hover:text-white uppercase tracking-[0.2em] flex items-center gap-2 transition-all group/btn"
                      >
                        Deep Dive <ChevronRight size={14} className="group-hover/btn:translate-x-1 transition-transform" />
                      </button>
                    </div>
                    <div className="flex items-center -space-x-2">
                      <div className="w-8 h-8 rounded-full bg-slate-800 border-2 border-[#0f172a] shadow-inner" />
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-600 border-2 border-[#0f172a] flex items-center justify-center text-[10px] font-black text-white shadow-lg">AI</div>
                    </div>
                  </div>
                </motion.div>
              ))
            ) : connectedAccounts.length === 0 && !error ? (
              /* ONBOARDING GUIDE: Professional zero-account state with step-by-step instructions */
              <div className="col-span-full py-16 flex flex-col items-center gap-8 text-center max-w-4xl mx-auto">
                <div className="w-28 h-28 rounded-full bg-gradient-to-br from-indigo-500/20 to-violet-500/20 flex items-center justify-center border border-indigo-500/30 relative shadow-2xl">
                  <Mail size={48} className="text-indigo-400" />
                  <div className="absolute inset-0 rounded-full border border-indigo-500/20 animate-pulse" />
                </div>

                <div className="space-y-3">
                  <h3 className="text-4xl font-black text-white">Welcome to {BRAND_NAME}</h3>
                  <p className="text-slate-400 text-lg font-medium max-w-2xl">
                    Executive-grade email intelligence at your fingertips. Connect your Gmail account to begin.
                  </p>
                </div>

                <div className="w-full max-w-2xl bg-white/[0.02] border border-white/5 rounded-3xl p-8 mt-4">
                  <h4 className="text-lg font-black text-white mb-6 text-left flex items-center gap-2">
                    <Shield size={20} className="text-indigo-400" />
                    Quick Start Guide
                  </h4>
                  <div className="space-y-5 text-left">
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white font-black text-sm">1</div>
                      <div className="flex-1">
                        <p className="text-slate-200 font-bold mb-1">Connect Your Gmail Account</p>
                        <p className="text-slate-500 text-sm">Click the button below to securely authorize access to your Gmail inbox. Your credentials are encrypted and stored safely.</p>
                      </div>
                    </div>
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white font-black text-sm">2</div>
                      <div className="flex-1">
                        <p className="text-slate-200 font-bold mb-1">Select Your Account</p>
                        <p className="text-slate-500 text-sm">After connecting, click the account switcher in the top-right corner to activate and view your emails. You can connect up to {MAX_CONNECTED_ACCOUNTS} accounts.</p>
                      </div>
                    </div>
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white font-black text-sm">3</div>
                      <div className="flex-1">
                        <p className="text-slate-200 font-bold mb-1">Your Intelligence Feed Loads</p>
                        <p className="text-slate-500 text-sm">Emails from your INBOX will sync automatically. Switch between accounts anytime using the dropdown menu.</p>
                      </div>
                    </div>
                  </div>
                </div>

                <a
                  href={apiService.getGoogleAuthUrl()}
                  className="inline-flex items-center gap-3 px-8 py-4 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-base font-black transition-all shadow-2xl shadow-indigo-600/30 active:scale-95 border border-indigo-400/20"
                >
                  <Mail size={20} />
                  <span>Connect Your First Account</span>
                  <ChevronRight size={18} />
                </a>

                <p className="text-slate-600 text-xs font-medium max-w-md">
                  🔒 Your data is encrypted end-to-end. We only read your INBOX with permissions you grant. You can disconnect anytime.
                </p>
              </div>
            ) : !activeEmail && connectedAccounts.length > 0 ? (
              /* CRITICAL: Show "Select Account" when accounts exist but none is active */
              <div className="col-span-full py-32 flex flex-col items-center gap-6 text-center">
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-indigo-500/20 to-violet-500/20 flex items-center justify-center border border-indigo-500/30 relative shadow-xl">
                  <Mail size={40} className="text-indigo-400" />
                  <div className="absolute inset-0 rounded-full border border-indigo-500/20 animate-pulse" />
                </div>
                <div>
                  <h3 className="text-2xl font-black text-white mb-2">Select Account to Begin</h3>
                  <p className="text-slate-400 max-w-md font-medium mb-6">
                    You have {connectedAccounts.length} connected {connectedAccounts.length === 1 ? 'account' : 'accounts'}. Click the account switcher above to select which account to view.
                  </p>
                  <div className="flex flex-wrap gap-3 justify-center">
                    {connectedAccounts.map((acc) => (
                      <button
                        key={acc.account_id}
                        onClick={async () => {
                          console.log(`[ACCOUNT-SELECT] Selecting account: ${acc.account_id}`);
                          setActiveEmail(acc.account_id);
                          setLoading(true);
                          try {
                            console.log(`[SYNC] Syncing account: ${acc.account_id}`);
                            const syncResult = await apiService.syncNow(acc.account_id);
                            console.log(`[SYNC] Sync result:`, syncResult);
                            console.log(`[FETCH] Fetching emails for: ${acc.account_id}`);
                            await fetchEmails(acc.account_id);
                            console.log(`[ACCOUNT-SELECT] Completed for ${acc.account_id}`);
                          } catch (err) {
                            console.error(`[ACCOUNT-SELECT] Failed for ${acc.account_id}:`, err);
                            alert(`Failed to load emails for ${acc.account_id}. Check console for details.`);
                          } finally {
                            setLoading(false);
                          }
                        }}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 hover:bg-indigo-600/10 hover:border-indigo-500/30 transition-all group"
                      >
                        <span className={`flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(acc.account_id)} text-[10px] font-black text-white shadow-md`}>
                          {getEmailInitials(acc.account_id)}
                        </span>
                        <span className="text-xs font-bold text-slate-300 group-hover:text-indigo-300 transition-colors">
                          {acc.account_id.split('@')[0]}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
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

      <AnimatePresence>
        {confirmDisconnect && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setConfirmDisconnect(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-[#0f172a] border border-white/10 rounded-3xl p-8 max-w-sm w-full mx-4 shadow-2xl"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-2xl bg-rose-500/10 flex items-center justify-center">
                  <LogOut size={18} className="text-rose-400" />
                </div>
                <h3 className="text-white font-black text-lg">Disconnect Account</h3>
              </div>
              <p className="text-slate-400 text-sm mb-2">
                Remove <span className="text-white font-bold">{confirmDisconnect}</span> from your intelligence feed?
              </p>
              <p className="text-slate-600 text-xs mb-8">Emails from this account will no longer be synced. You can reconnect at any time.</p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmDisconnect(null)}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-white/10 text-slate-400 hover:text-white text-sm font-bold transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleDisconnect(confirmDisconnect)}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-sm font-bold transition-all shadow-lg shadow-rose-900/30"
                >
                  Disconnect
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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
