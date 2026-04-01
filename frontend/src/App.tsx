import { useState, useEffect, useRef } from 'react';
import { apiService } from '@services';
import { websocketService } from '@services/websocket';
import { Sparkles, RefreshCw, Mail, Shield, AlertCircle, Clock, ChevronRight, Brain, LogOut, X } from 'lucide-react';
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
  const briefingsRef = useRef<Briefing[]>([]); // Keep current briefings accessible in closures
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filterCategory, setFilterCategory] = useState<'All' | 'Security' | 'Financial' | 'Work' | 'Personal' | 'Marketing' | 'General'>('All');
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
  const lastSyncTimeRef = useRef<number>(0); // Track last sync timestamp for cooldown
  const syncingRef = useRef<boolean>(false); // Ref-based lock for synchronous check (prevents race conditions)
  const initDoneRef = useRef<boolean>(false); // Prevent double initializeApp in React 18 StrictMode
  const inFlightSummarizingRef = useRef<Set<string>>(new Set()); // Track in-flight summarization IDs (dedupe guard)
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [summarizingIds, setSummarizingIds] = useState<Set<string>>(new Set());
  const [selectedEmailDetail, setSelectedEmailDetail] = useState<Briefing | null>(null);
  const [offlineAccounts, setOfflineAccounts] = useState<Set<string>>(new Set());
  const [showMaxAccountsMsg, setShowMaxAccountsMsg] = useState(false);
  const [scrollToActions, setScrollToActions] = useState(false);
  const actionItemsRef = useRef<HTMLDivElement | null>(null);
  const [showReplyCompose, setShowReplyCompose] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [sendToast, setSendToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const showSendToast = (type: 'success' | 'error', message: string) => {
    setSendToast({ type, message });
    const duration = type === 'success' ? 3500 : 4500;
    setTimeout(() => setSendToast(null), duration);
  };

  // --- Detail panel state helpers ---
  // Resets all transient compose/reply state inside the panel
  const resetPanelTransientState = () => {
    setShowReplyCompose(false);
    setReplyBody('');
    setSendSuccess(false);
    setPanelError(null);
    setScrollToActions(false);
  };

  // Closes the panel and resets all transient state
  const closeDetailPanel = () => {
    setSelectedEmailDetail(null);
    resetPanelTransientState();
  };

  // Opens the panel for an item — always resets transient state first
  const openDetailPanel = (item: Briefing, jumpToActions = false) => {
    resetPanelTransientState();
    if (jumpToActions) setScrollToActions(true);
    setSelectedEmailDetail(item);
  };
  // --- End detail panel state helpers ---

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

  // Smart email categorization based on content analysis with refined priority
  const categorizeEmail = (subject: string, sender: string, body: string, aiSummary?: string): 'Security' | 'Financial' | 'Work' | 'Personal' | 'Marketing' | 'General' => {
    const text = `${subject} ${sender} ${body} ${aiSummary || ''}`.toLowerCase();

    // HIGH PRIORITY: Work-related keywords (itinerary, travel, business)
    // Checked BEFORE security to prevent false positives
    const workKeywords = [
      'meeting', 'deadline', 'project', 'review', 'presentation', 'report', 'urgent', 'asap',
      'feedback', 'approval', 'task', 'jira', 'confluence', 'slack',
      'itinerary', 'travel', 'flight', 'booking', 'reservation', 'conference', 'trip details',
      'boarding pass', 'check-in', 'hotel', 'rental car'
    ];
    if (workKeywords.some(keyword => text.includes(keyword))) {
      // Exception: If explicitly mentions account security/compromise, still classify as Security
      const criticalSecurityPhrases = [
        'account locked', 'unauthorized access', 'suspicious activity', 'password reset required',
        'account compromised', 'unusual activity', 'verify your identity'
      ];
      if (criticalSecurityPhrases.some(phrase => text.includes(phrase))) {
        return 'Security';
      }
      return 'Work';
    }

    // CRITICAL PRIORITY: Genuine security threats (refined to avoid false positives)
    const criticalSecurityKeywords = [
      'account locked', 'unauthorized', 'breach', 'suspicious activity', 'verify your identity',
      'password reset required', 'account compromised', 'unusual activity', 'confirm your identity',
      'security code', 'two-factor authentication required'
    ];
    if (criticalSecurityKeywords.some(keyword => text.includes(keyword))) return 'Security';

    // Financial keywords
    const financialKeywords = ['invoice', 'payment', 'bank', 'transaction', 'receipt', 'refund', 'billing', 'charge', 'purchase', 'order', 'card', 'paypal', 'stripe', 'revenue', 'expense'];
    if (financialKeywords.some(keyword => text.includes(keyword))) return 'Financial';

    // Marketing keywords
    const marketingKeywords = ['unsubscribe', 'newsletter', 'promotion', 'discount', 'sale', 'offer', 'deal', 'subscribe', 'marketing'];
    if (marketingKeywords.some(keyword => text.includes(keyword))) return 'Marketing';

    // Personal keywords
    const personalKeywords = ['family', 'friend', 'birthday', 'vacation', 'personal'];
    if (personalKeywords.some(keyword => text.includes(keyword))) return 'Personal';

    return 'General';
  };

  // Scroll detection for scroll-to-top button
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 400);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Keyboard shortcut for scroll to top (Ctrl+Home or Cmd+Home)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Home') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Escape key closes details panel
  useEffect(() => {
    if (!selectedEmailDetail) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeDetailPanel();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [selectedEmailDetail]);

  // Auto-scroll to action items when panel opens via "View N more" button
  useEffect(() => {
    if (scrollToActions && selectedEmailDetail && actionItemsRef.current) {
      // Wait for panel slide animation to finish (250ms transition)
      const timer = setTimeout(() => {
        actionItemsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setScrollToActions(false);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [scrollToActions, selectedEmailDetail]);

  const fetchEmails = async (overrideAccountId?: string | null) => {
    // Note: We avoid setting full loading:true during background polling for smoothness
    const accountIdToUse = overrideAccountId !== undefined ? overrideAccountId : activeEmail;
    try {
      const [emailData, accountsData] = await Promise.all([
        apiService.listEmailsWithSummaries(accountIdToUse ?? undefined),
        apiService.listAccounts()
      ]);

      // Sort emails by date descending (newest first)
      const sorted = (emailData || []).sort((a: any, b: any) => {
        const dateA = Date.parse(a.date ?? a.created_at ?? '0');
        const dateB = Date.parse(b.date ?? b.created_at ?? '0');
        return dateB - dateA;
      });

      const loadedAccounts: AccountInfo[] = accountsData.accounts || [];

      // Emails already include AI summary fields from unified endpoint
      // No N+1 query pattern - summaries are fetched in batch on backend

      // Map DB schema to UI Briefing model
      const mapped: Briefing[] = sorted.map((e: any) => {
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

        // ENHANCED: Smart categorization based on email content
        const category = categorizeEmail(
          e.subject || '',
          e.sender || '',
          e.body || '',
          e.ai_summary_text
        );

        const briefing: Briefing = {
          account: e.account_id || 'Unknown',
          subject: e.subject || 'No Subject',
          sender: e.sender || 'Unknown',
          date: formattedDate,
          priority: priority,
          category: category,
          should_alert: e.ai_summary_json?.urgency === 'high',
          summary: displaySummary,
          action: primaryAction,
          body: e.body || '',

          ai_summary_json: e.ai_summary_json,
          ai_summary_text: e.ai_summary_text,
          ai_summary_model: e.ai_summary_model,
          gmail_message_id: e.gmail_message_id,
          thread_id: e.thread_id, // Gmail thread ID for send functionality
        };

        // CRITICAL: Trigger Sentinel Alert for high-urgency emails
        if (briefing.should_alert) {
          setTimeout(() => triggerSentinelAlert(briefing), 500);
        }

        return briefing;
      });

      setBriefings(mapped);

      // Reconcile completed summaries: release IDs that now have ai_summary_text
      // This prevents stuck in-flight/pending state across fetch cycles
      const inFlightIds = Array.from(inFlightSummarizingRef.current);
      const nowCompleted = inFlightIds.filter(id => {
        const email = mapped.find(e => e.gmail_message_id === id);
        return email?.ai_summary_text; // Has summary = completed
      });
      if (nowCompleted.length > 0) {
        nowCompleted.forEach(id => inFlightSummarizingRef.current.delete(id));
        setSummarizingIds(prev => {
          const updated = new Set(prev);
          nowCompleted.forEach(id => updated.delete(id));
          return updated;
        });
        console.log(`[RECONCILE] Released ${nowCompleted.length} completed IDs from in-flight tracking`);
      }

      setAccounts(loadedAccounts);
      const firstConnected = loadedAccounts.find(a => a.connected);
      if (firstConnected && !accountIdToUse) {
        setActiveEmail(firstConnected.account_id);
      }
      setError(null);
      setConsecutiveFailures(0);

      // Auto-summarize unsummarized emails after load
      const effectiveId = accountIdToUse || firstConnected?.account_id;
      if (effectiveId) {
        autoSummarizeEmails(mapped, effectiveId);
      }
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

  const autoSummarizeEmails = async (emails: Briefing[], accountId: string) => {
    // Filter out emails that are already summarized OR already in-flight
    const unsummarized = emails.filter(e =>
      !e.ai_summary_text &&
      e.gmail_message_id &&
      !inFlightSummarizingRef.current.has(e.gmail_message_id)
    );
    if (unsummarized.length === 0) return;

    console.log('[AUTO-SUMMARIZE] Starting for', unsummarized.length, 'emails');

    // Mark all as in-flight (ref for dedupe guard)
    unsummarized.forEach(e => inFlightSummarizingRef.current.add(e.gmail_message_id!));

    // Mark all as pending (state for UI indicators) - merge with existing to handle overlapping calls
    setSummarizingIds(prev => {
      const updated = new Set(prev);
      unsummarized.forEach(e => updated.add(e.gmail_message_id!));
      return updated;
    });

    const BATCH_SIZE = 5;
    for (let i = 0; i < unsummarized.length; i += BATCH_SIZE) {
      const batch = unsummarized.slice(i, i + BATCH_SIZE);
      try {
        await Promise.all(
          batch.map(email =>
            apiService.summarizeEmail(email.gmail_message_id!, accountId)
          )
        );
        console.log(`[AUTO-SUMMARIZE] Batch ${Math.floor(i / BATCH_SIZE) + 1} queued (${batch.length} emails)`);
      } catch (err) {
        console.warn('[AUTO-SUMMARIZE] Batch failed:', err);
      }

      // Wait 500ms between batches
      if (i + BATCH_SIZE < unsummarized.length) {
        await new Promise(r => setTimeout(r, 500));
      }
    }

    // After all batches queued, poll for results
    console.log('[AUTO-SUMMARIZE] All jobs queued. Refreshing in 8s...');
    setTimeout(async () => {
      await fetchEmails(accountId);

      // Wait briefly for state propagation from fetchEmails
      await new Promise(r => setTimeout(r, 100));

      // Check which of the queued IDs now have summaries (evidence-based cleanup)
      const queuedIds = unsummarized.map(e => e.gmail_message_id!);
      const completed = queuedIds.filter(id => {
        const email = briefingsRef.current.find(e => e.gmail_message_id === id);
        return email?.ai_summary_text; // Has summary = completed
      });

      // Release only confirmed-complete IDs from in-flight tracking
      completed.forEach(id => inFlightSummarizingRef.current.delete(id));

      // Remove only confirmed-complete IDs from pending UI state (merge-safe)
      setSummarizingIds(prev => {
        const updated = new Set(prev);
        completed.forEach(id => updated.delete(id));
        return updated;
      });

      console.log(`[AUTO-SUMMARIZE] Cleanup: ${completed.length}/${queuedIds.length} confirmed complete`);
    }, 8000);
  };

  const autoSync = async () => {
    // All guards must pass BEFORE claiming cooldown or lock
    const now = Date.now();
    const COOLDOWN_MS = 60000; // 60 seconds
    if (now - lastSyncTimeRef.current < COOLDOWN_MS) return;
    if (syncingRef.current) return;
    if (document.visibilityState !== 'visible') return;
    if (!activeEmailRef.current) return;

    // All guards passed — claim cooldown + lock atomically
    lastSyncTimeRef.current = now;
    syncingRef.current = true;
    setSyncing(true);

    try {
      // Preflight health check
      await apiService.checkHealth();

      // Execute sync
      const result = await apiService.syncNow(activeEmailRef.current);

      if (result.status === 'done' && result.count && result.count > 0) {
        console.log(`[AUTO-SYNC] Processed ${result.processed_count ?? result.count} emails`);
        // Refetch emails for active account to update UI
        await fetchEmails(activeEmailRef.current);
        // Reset failures on success
        setConsecutiveFailures(0);
      } else if (result.status === 'auth_required') {
        console.warn('[AUTO-SYNC] Auth required, marking offline');
        if (activeEmailRef.current) {
          setOfflineAccounts(prev => new Set(prev).add(activeEmailRef.current!));
        }
      }
    } catch (error) {
      console.warn('[AUTO-SYNC] Failed', error);
    } finally {
      syncingRef.current = false;
      setSyncing(false);
    }
  };

  useEffect(() => {
    // Initial load: Load accounts and auto-select first connected account (Phase 2)
    const initializeApp = async () => {
      try {
        const accountsData = await apiService.listAccounts();
        const loadedAccounts: AccountInfo[] = accountsData.accounts || [];
        setAccounts(loadedAccounts);

        // Account selection logic:
        // 0 connected -> onboarding screen (activeEmail stays null)
        // 1 connected -> auto-select it
        // >1 connected + localStorage match -> auto-select saved
        // >1 connected + no localStorage match -> show "Select Account" screen
        const connectedList = loadedAccounts.filter(a => a.connected);
        const lastSelected = localStorage.getItem('last_selected_account');

        let accountToSelect: AccountInfo | null = null;

        if (connectedList.length === 0) {
          // Scenario A: No accounts -> onboarding
          console.log('[INIT] No connected accounts -> showing onboarding');
        } else if (connectedList.length === 1) {
          // Scenario B: Single account -> auto-select
          accountToSelect = connectedList[0];
          console.log(`[INIT] Single account -> auto-selecting: ${accountToSelect.account_id}`);
        } else {
          // Scenario C: Multiple accounts
          const savedMatch = lastSelected ? connectedList.find(a => a.account_id === lastSelected) : null;
          if (savedMatch) {
            accountToSelect = savedMatch;
            console.log(`[INIT] Returning user -> auto-selecting saved: ${savedMatch.account_id}`);
          } else {
            console.log(`[INIT] Multiple accounts, no saved preference -> showing selection screen`);
          }
        }

        if (accountToSelect) {
          setActiveEmail(accountToSelect.account_id);
          localStorage.setItem('last_selected_account', accountToSelect.account_id);

          // Trigger initial sync and fetch
          try {
            const syncResult = await apiService.syncNow(accountToSelect.account_id);
            if (syncResult.status === 'auth_required') {
              setOfflineAccounts(prev => new Set(prev).add(accountToSelect!.account_id));
            }
            await fetchEmails(accountToSelect.account_id);
            // Start cooldown clock from init so autoSync waits 60s
            lastSyncTimeRef.current = Date.now();
          } catch (err) {
            console.warn('[INIT] Initial sync failed:', err);
          }
        }

        setLoading(false);
      } catch (error) {
        console.warn('[STRATEGY] Failed to load accounts on init', error);
        setLoading(false);
      }
    };

    if (!initDoneRef.current) {
      initDoneRef.current = true;
      initializeApp();
    }

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

    // Note: ai_summary_ready event removed - worker runs in separate process from Socket.IO
    // Frontend uses unified /api/emails-with-summaries endpoint that fetches summaries in batch

    websocketService.on("emails_updated", handleEmailsUpdated);
    websocketService.on("summary_ready", handleSummaryReady);

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
      clearInterval(autoSyncInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  // Connect/disconnect WebSocket based on account state
  useEffect(() => {
    if (activeEmail) {
      try {
        websocketService.connect();
      } catch (e) {
        console.error("[WebSocket] Connect failed:", e);
      }
    } else {
      websocketService.disconnect();
    }
    // Clear in-flight summarization tracking on account change
    inFlightSummarizingRef.current.clear();
    // Close detail panel on account change to prevent stale panel state
    closeDetailPanel();
  }, [activeEmail]);

  useEffect(() => {
    if (!showAccountMenu) { setShowMaxAccountsMsg(false); return; }
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

  // Keep activeEmailRef in sync with activeEmail state + persist to localStorage
  useEffect(() => {
    activeEmailRef.current = activeEmail;
    if (activeEmail) {
      localStorage.setItem('last_selected_account', activeEmail);
    }
  }, [activeEmail]);

  // Keep briefingsRef in sync with briefings state (for closure access)
  useEffect(() => {
    briefingsRef.current = briefings;
  }, [briefings]);

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
      setError('OAuth completed but account information was lost. Please try connecting again.');
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
          localStorage.setItem('last_selected_account', newAccountId);
          setOfflineAccounts(prev => { const next = new Set(prev); next.delete(newAccountId); return next; });
          fetchEmails(newAccountId);
          return;
        }

        // Account not found yet - retry if attempts remaining
        if (retryCount < MAX_RETRIES) {
          console.log(`[OAUTH-CALLBACK] ⏳ Account not found yet - retrying in ${delay}ms...`);
          setTimeout(attemptActivation, delay);
        } else {
          // Max retries exceeded - show error
          console.error(`[OAUTH-CALLBACK] ❌ FAILED - Account ${newAccountId} not found after ${MAX_RETRIES} attempts`);
          setError(`Failed to activate ${newAccountId}. Please select it manually from the account dropdown.`);
          // Leave user on account selection screen - don't auto-activate wrong account
        }
      } catch (error) {
        console.error(`[OAUTH-CALLBACK] Attempt ${retryCount} failed:`, error);
        if (retryCount < MAX_RETRIES) {
          setTimeout(attemptActivation, delay);
        } else {
          setError('Failed to load accounts after OAuth. Please refresh the page.');
        }
      }
    };

    // Start activation attempts
    attemptActivation();
  }, []);

  const getCategoryStyles = (category: string) => {
    switch (category) {
      case 'Security': return 'text-red-400 bg-red-500/10 border-red-500/30';
      case 'Financial': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'Work': return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      case 'Personal': return 'text-purple-400 bg-purple-500/10 border-purple-500/20';
      case 'Marketing': return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
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
        localStorage.removeItem('last_selected_account');
        setBriefings([]); // Clear emails since no account is active
        console.log(`[DISCONNECT] Cleared active account (was ${account_id})`);
      }
    } catch (err) {
      console.error('[DISCONNECT] Failed to disconnect account:', account_id, err);
      setError(`Failed to disconnect ${account_id}. Please try again.`);
    }
  };

  const connectedAccounts = accounts.filter(a => a.connected);
  const hasLegacyAccounts = connectedAccounts.some(a => a.account_id === 'default' || a.account_id === 'PRIMARY');

  const handleSendReply = async () => {
    if (!selectedEmailDetail?.thread_id) {
      setPanelError('Cannot send: thread ID missing. Please refresh and try again.');
      return;
    }

    if (!replyBody.trim()) {
      setPanelError('Reply body cannot be empty.');
      return;
    }

    setSending(true);
    setPanelError(null);

    try {
      const result = await apiService.sendThreadReply(selectedEmailDetail.thread_id, replyBody.trim());

      if (result.success) {
        console.log('[SEND] Email sent successfully:', result.message_id);
        setSendSuccess(true);
        setReplyBody('');
        setShowReplyCompose(false);
        setPanelError(null);
        showSendToast('success', 'Reply sent successfully.');

        // Refetch emails to update UI
        await fetchEmails(activeEmail);

        // Auto-hide success message after 3s
        setTimeout(() => setSendSuccess(false), 3000);
      } else {
        const errMsg = result.error || 'Failed to send email. Please try again.';
        setPanelError(errMsg);
        showSendToast('error', errMsg);
      }
    } catch (err: any) {
      console.error('[SEND] Unexpected error:', err);
      const netMsg = 'Network error: Could not send email.';
      setPanelError(netMsg);
      showSendToast('error', netMsg);
    } finally {
      setSending(false);
    }
  };

  const handleDisconnectAll = async () => {
    try {
      await apiService.disconnectAllAccounts();
      setAccounts([]);
      setActiveEmail(null);
      localStorage.removeItem('last_selected_account');
      await fetchEmails();
    } catch (err) {
      console.error('[DISCONNECT-ALL] Failed:', err);
    }
  };

  // Filter out self-generated security alerts (from app's own Gmail API access)
  const isSelfGeneratedAlert = (briefing: Briefing): boolean => {
    // Check if this is a security alert category
    if (briefing.category !== 'Security') return false;

    // Expanded domain matching patterns
    const appIdentifiers = [
      'intelligent-email-assistant',
      'intelligent-email',
      'onrender.com',
      'onrender',
      'executive brain',
      'executivebrain',
      'strategic intelligence'
    ];

    // Check all text fields for app-related content
    const textToCheck = [
      briefing.summary?.toLowerCase() || '',
      briefing.subject?.toLowerCase() || '',
      briefing.sender?.toLowerCase() || '',
      briefing.action?.toLowerCase() || ''
    ].join(' ');

    // Check for Google security alert patterns related to our app
    const isGoogleSecurityAlert = (
      (briefing.sender?.toLowerCase().includes('google') ||
       briefing.sender?.toLowerCase().includes('no-reply@accounts.google.com')) &&
      briefing.subject?.toLowerCase().includes('security alert')
    );

    // If it's a Google security alert, check if it mentions our app domains
    if (isGoogleSecurityAlert) {
      return appIdentifiers.some(id => textToCheck.includes(id));
    }

    // Otherwise, check if any of our identifiers appear in the content
    return appIdentifiers.some(id => textToCheck.includes(id));
  };

  const filteredBriefings = (filterCategory === 'All'
    ? briefings
    : briefings.filter(b => b.category === filterCategory))
    .filter(b => !isSelfGeneratedAlert(b)); // Remove self-generated alerts

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
                          <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-[#0f172a] ${activeEmail && offlineAccounts.has(activeEmail) ? 'bg-[#EF4444]' : 'bg-[#22C55E]'}`} />
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
                                  {/* 3-state indicator: ACTIVE(green) / ONLINE(blue) / OFFLINE(red) */}
                                  <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-[#0f172a] ${
                                    offlineAccounts.has(info.account_id) ? 'bg-[#EF4444]' : isActive ? 'bg-[#22C55E]' : 'bg-[#3B82F6]'
                                  }`} title={offlineAccounts.has(info.account_id) ? 'Offline' : isActive ? 'Active' : 'Online'} />
                                </div>
                                <button
                                  onClick={async () => {
                                    console.log(`[DROPDOWN] Switching to account: ${info.account_id}`);
                                    setActiveEmail(info.account_id);
                                    localStorage.setItem('last_selected_account', info.account_id);
                                    setShowAccountMenu(false);
                                    setLoading(true);
                                    try {
                                      console.log(`[SYNC] Syncing account: ${info.account_id}`);
                                      const syncResult = await apiService.syncNow(info.account_id);
                                      console.log(`[SYNC] Sync result:`, syncResult);
                                      if (syncResult.status === 'auth_required') {
                                        setOfflineAccounts(prev => new Set(prev).add(info.account_id));
                                      } else {
                                        setOfflineAccounts(prev => { const next = new Set(prev); next.delete(info.account_id); return next; });
                                      }
                                      console.log(`[FETCH] Fetching emails for: ${info.account_id}`);
                                      await fetchEmails(info.account_id);
                                      lastSyncTimeRef.current = Date.now(); // Reset cooldown so autoSync waits 60s
                                      console.log(`[DROPDOWN] Switched to ${info.account_id} successfully`);
                                    } catch (err) {
                                      console.error(`[DROPDOWN] Failed to switch to ${info.account_id}:`, err);
                                      setError(`Failed to load emails for ${info.account_id}.`);
                                    } finally {
                                      setLoading(false);
                                    }
                                  }}
                                  className={`text-[11px] font-bold truncate flex-1 text-left ${isActive ? 'text-indigo-400' : 'text-slate-300'}`}
                                >
                                  <div className="truncate">{info.account_id}</div>
                                  {offlineAccounts.has(info.account_id) ? (
                                    <div className="text-[9px] font-black text-[#EF4444] uppercase tracking-wider mt-0.5">● Offline</div>
                                  ) : isActive ? (
                                    <div className="text-[9px] font-black text-[#22C55E] uppercase tracking-wider mt-0.5">● Active</div>
                                  ) : (
                                    <div className="text-[9px] font-bold text-[#3B82F6] uppercase tracking-wider mt-0.5">● Online</div>
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
                          {showMaxAccountsMsg && (
                            <p className="text-[10px] text-[#EF4444] mb-2">Maximum {MAX_CONNECTED_ACCOUNTS} accounts. Disconnect one first.</p>
                          )}
                          {connectedAccounts.length >= MAX_CONNECTED_ACCOUNTS ? (
                            <button
                              onClick={() => setShowMaxAccountsMsg(true)}
                              className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                              + Add account
                            </button>
                          ) : (
                            <a
                              href={apiService.getGoogleAuthUrl()}
                              className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                              + Add account
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
              onClick={async () => {
                setLoading(true);
                try {
                  console.log('[REFRESH] Syncing from Gmail API for account:', activeEmail);
                  const syncResult = await apiService.syncNow(activeEmail ?? undefined);
                  console.log('[REFRESH] Sync result:', syncResult);

                  if (syncResult.status === 'done' || syncResult.status === 'success') {
                    console.log(`[REFRESH] Synced ${syncResult.count || 0} emails, processed ${syncResult.processed_count || 0}`);
                  } else {
                    console.warn('[REFRESH] Sync failed:', syncResult);
                  }

                  // Always fetch emails after sync attempt
                  await fetchEmails(activeEmail);
                  lastSyncTimeRef.current = Date.now(); // Reset cooldown so autoSync waits 60s
                } catch (err) {
                  console.error('[REFRESH] Sync error:', err);
                  // Still try to fetch emails from database
                  await fetchEmails(activeEmail);
                  lastSyncTimeRef.current = Date.now(); // Reset cooldown even on error (sync was attempted)
                }
              }}
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

          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/[0.02] border border-white/5 backdrop-blur-sm flex-wrap">
            {['All', 'Security', 'Financial', 'Work', 'Personal', 'Marketing', 'General'].map((cat) => (
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

        <div className="flex flex-col gap-4 mb-12 max-w-[720px] mx-auto">
          <AnimatePresence mode="popLayout">
            {loading ? (
              [...Array(currentItems.length || ITEMS_PER_PAGE)].map((_, i) => (
                <motion.div
                  key={`skeleton-${i}`}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.3, delay: i * 0.05 }}
                  className="rounded-2xl bg-white/[0.02] border border-white/5 relative overflow-hidden p-6 flex flex-col gap-3"
                >
                  <div className="flex gap-2">
                    <div className="w-16 h-5 rounded-full bg-white/5 animate-pulse" />
                    <div className="w-16 h-5 rounded-full bg-white/5 animate-pulse" />
                  </div>
                  <div className="w-3/4 h-6 rounded-lg bg-white/5 animate-pulse" />
                  <div className="w-full h-16 rounded-xl bg-white/5 animate-pulse" />
                  <div className="w-1/2 h-4 rounded-lg bg-white/5 animate-pulse" />
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.015] to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
                </motion.div>
              ))
            ) : currentItems.length > 0 ? (
              currentItems.map((item, index) => {
                const cardId = `${item.gmail_message_id || item.subject}-${index}`;
                const urgency = item.ai_summary_json?.urgency || 'medium';
                const urgencyLabel = urgency === 'high' ? 'URGENT' : urgency === 'low' ? 'ROUTINE' : 'MEDIUM';

                const getPriorityBadgeStyle = () => {
                  switch(urgency) {
                    case 'high': return 'bg-[#FF3B5C] text-white border-[#FF3B5C] font-bold';
                    case 'low': return 'bg-[#3D4A5C] text-[#94A3B8] border-[#3D4A5C]';
                    default: return 'bg-[#FFB800] text-[#1a1a1a] border-[#FFB800] font-bold';
                  }
                };

                return (
                <motion.div
                  key={cardId}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.03 }}
                  className="group relative flex flex-col p-6 rounded-2xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] hover:border-white/10 transition-all duration-300 shadow-xl hover:shadow-indigo-500/5"
                >
                  {/* Header row: badges + AI indicator */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getPriorityBadgeStyle()}`}>
                        {urgencyLabel}
                      </span>
                      <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(item.category)}`}>
                        {item.category}
                      </span>
                    </div>
                    {item.ai_summary_text && (
                      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-indigo-500/15 border border-indigo-400/30">
                        <Sparkles size={10} className={`text-indigo-300 ${summarizingIds.has(item.gmail_message_id || '') ? 'animate-pulse' : ''}`} />
                        <span className="text-[8px] font-black text-indigo-300 uppercase tracking-wider">AI</span>
                      </div>
                    )}
                    {!item.ai_summary_text && item.gmail_message_id && summarizingIds.has(item.gmail_message_id) && (
                      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-indigo-500/10 border border-indigo-400/20">
                        <Sparkles size={10} className="text-indigo-400 animate-pulse" />
                        <span className="text-[8px] font-black text-indigo-400 uppercase tracking-wider">Queued</span>
                      </div>
                    )}
                  </div>

                  {/* Subject and sender */}
                  <div className="mb-3">
                    <h3 className="text-lg font-black text-white mb-1 tracking-tight leading-tight group-hover:text-indigo-400 transition-colors duration-300">
                      {item.subject}
                    </h3>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span className="font-semibold truncate mr-2">{item.sender.split('<')[0].trim()}</span>
                      <div className="flex items-center gap-1 shrink-0">
                        <Clock size={11} className="text-indigo-400/60" />
                        <span className="text-[10px] font-medium">{item.date}</span>
                      </div>
                    </div>
                    {item.ai_summary_json?.urgency && (
                      <p className={`text-[10px] font-bold uppercase tracking-wider mt-1.5 ${
                        urgency === 'high' ? 'text-rose-400' : urgency === 'low' ? 'text-slate-500' : 'text-amber-400'
                      }`}>
                        {urgency === 'high' ? '↩ Action or reply required' : urgency === 'low' ? '· For reference' : '· Review recommended'}
                      </p>
                    )}
                  </div>

                  {/* Summary - 3-line clamp with fade, 14px body */}
                  <div className="mb-3 relative">
                    <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                      <p className="text-[8px] font-black uppercase tracking-widest text-indigo-400/60 mb-1.5">
                        {item.ai_summary_text ? 'AI Overview' : 'Message Preview'}
                      </p>
                      <p className="text-sm leading-[1.6] text-slate-200 line-clamp-3">
                        {item.summary}
                      </p>
                      <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-[#0f172a]/80 to-transparent rounded-b-xl pointer-events-none" />
                    </div>

                    {/* Action Items - Full text bullets */}
                    {item.ai_summary_json?.action_items && item.ai_summary_json.action_items.length > 0 && (
                      <div className="mt-2">
                        <ul className="space-y-1 list-disc pl-4">
                          {item.ai_summary_json.action_items.slice(0, 3).map((action: string, idx: number) => (
                            <li key={idx} className="text-xs leading-relaxed text-slate-300">{action}</li>
                          ))}
                        </ul>
                        {item.ai_summary_json.action_items.length > 3 && (
                          <button
                            onClick={() => { openDetailPanel(item, true); }}
                            className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 mt-1.5 transition-colors"
                          >
                            View {item.ai_summary_json.action_items.length - 3} more action{item.ai_summary_json.action_items.length - 3 > 1 ? 's' : ''} &rarr;
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Footer */}
                  <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {/* Queued indicator for pending summaries */}
                      {!item.ai_summary_text && item.gmail_message_id && summarizingIds.has(item.gmail_message_id) && (
                        <span className="text-[9px] font-bold text-indigo-400 uppercase flex items-center gap-1">
                          <Sparkles size={11} className="animate-pulse" />
                          Queued...
                        </span>
                      )}
                      {/* Re-summarize for cards that already have summaries */}
                      {item.ai_summary_text && item.gmail_message_id && (
                        <button
                          onClick={async () => {
                            setSummarizingIds(prev => new Set(prev).add(item.gmail_message_id!));
                            await apiService.summarizeEmail(item.gmail_message_id!, activeEmail || 'default');
                            setTimeout(() => {
                              fetchEmails(activeEmail);
                              setSummarizingIds(prev => { const next = new Set(prev); next.delete(item.gmail_message_id!); return next; });
                            }, 8000);
                          }}
                          className="text-[9px] font-bold text-slate-500 hover:text-indigo-400 uppercase flex items-center gap-1 transition-colors"
                        >
                          <Sparkles size={11} />
                          Re-summarize
                        </button>
                      )}
                      <button
                        onClick={() => openDetailPanel(item)}
                        className="text-[9px] font-bold text-slate-500 hover:text-slate-300 uppercase flex items-center gap-1 transition-colors"
                      >
                        Details <ChevronRight size={11} />
                      </button>
                    </div>
                  </div>
                </motion.div>
                );
              })
            ) : null}

            {/* BATCH LIMIT INDICATOR: Inform users about auto-summary limits */}
            {currentItems.length > 30 && (
              <div className="w-full mt-8 mb-4 p-6 rounded-2xl bg-gradient-to-r from-indigo-500/10 to-violet-500/10 border border-indigo-500/20">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-full bg-indigo-600/20 flex items-center justify-center border border-indigo-500/30">
                    <Sparkles size={20} className="text-indigo-400" />
                  </div>
                  <div className="flex-1">
                    <h4 className="text-sm font-black text-indigo-300 mb-1 uppercase tracking-wide">
                      Auto-Summary Batch Limit Reached
                    </h4>
                    <p className="text-xs text-slate-400 leading-relaxed mb-3">
                      You have <span className="text-white font-bold">{currentItems.length} emails</span> in this account.
                      Only the <span className="text-indigo-400 font-bold">first 30 emails</span> receive automatic AI summaries to optimize costs.
                    </p>
                    <p className="text-xs text-slate-500">
                      <strong className="text-indigo-400">💡 Tip:</strong> Use the <strong className="text-white">"Summarize Email"</strong> button
                      to manually generate AI summaries for emails #{31} onwards.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {connectedAccounts.length === 0 && !error ? (
              /* ONBOARDING GUIDE: Professional zero-account state with step-by-step instructions */
              <div className="w-full py-16 flex flex-col items-center gap-8 text-center max-w-4xl mx-auto">
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
              <div className="w-full py-32 flex flex-col items-center gap-6 text-center">
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
                          localStorage.setItem('last_selected_account', acc.account_id);
                          setLoading(true);
                          try {
                            console.log(`[SYNC] Syncing account: ${acc.account_id}`);
                            const syncResult = await apiService.syncNow(acc.account_id);
                            console.log(`[SYNC] Sync result:`, syncResult);
                            if (syncResult.status === 'auth_required') {
                              setOfflineAccounts(prev => new Set(prev).add(acc.account_id));
                            } else {
                              setOfflineAccounts(prev => { const next = new Set(prev); next.delete(acc.account_id); return next; });
                            }
                            console.log(`[FETCH] Fetching emails for: ${acc.account_id}`);
                            await fetchEmails(acc.account_id);
                            lastSyncTimeRef.current = Date.now(); // Reset cooldown so autoSync waits 60s
                            console.log(`[ACCOUNT-SELECT] Completed for ${acc.account_id}`);
                          } catch (err) {
                            console.error(`[ACCOUNT-SELECT] Failed for ${acc.account_id}:`, err);
                            setError(`Failed to load emails for ${acc.account_id}.`);
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
              <div className="w-full py-32 flex flex-col items-center gap-6 text-center">
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

      {/* Email Details Panel - Slides from right */}
      <AnimatePresence>
        {selectedEmailDetail && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[150] bg-black/60 backdrop-blur-sm"
              onClick={() => closeDetailPanel()}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="fixed top-0 right-0 z-[200] h-screen w-full md:w-[60vw] bg-[#0f172a] border-l border-white/10 shadow-2xl flex flex-col"
            >
              {/* Panel Header - Sticky */}
              <div className="sticky top-0 z-10 bg-[#0f172a]/95 backdrop-blur-sm border-b border-white/5 px-6 py-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h2 className="text-xl font-black text-white mb-2 leading-tight">{selectedEmailDetail.subject}</h2>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
                      <span className="font-semibold text-slate-300">{selectedEmailDetail.sender}</span>
                      <span className="text-slate-600">|</span>
                      <span>{selectedEmailDetail.date}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-3">
                      <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${
                        selectedEmailDetail.priority === 'High' ? 'bg-[#FF3B5C] text-white border-[#FF3B5C]' :
                        selectedEmailDetail.priority === 'Medium' ? 'bg-[#FFB800] text-[#1a1a1a] border-[#FFB800]' :
                        'bg-[#3D4A5C] text-[#94A3B8] border-[#3D4A5C]'
                      }`}>
                        {selectedEmailDetail.priority}
                      </span>
                      <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(selectedEmailDetail.category)}`}>
                        {selectedEmailDetail.category}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => closeDetailPanel()}
                    className="p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0"
                  >
                    <X size={20} />
                  </button>
                </div>
              </div>

              {/* Panel Body - Scrollable */}
              <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-6 space-y-6">
                {/* Section 1: AI Analysis */}
                {selectedEmailDetail.ai_summary_text && (
                  <div className="space-y-4 border-t border-white/5 pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Sparkles size={16} className="text-indigo-400" />
                        <h3 className="text-sm font-black text-indigo-400 uppercase tracking-wider">AI Analysis</h3>
                        {selectedEmailDetail.ai_summary_model && (
                          <span className="text-[9px] text-slate-600 font-bold">{selectedEmailDetail.ai_summary_model}</span>
                        )}
                      </div>
                      {selectedEmailDetail.ai_summary_json?.urgency && (
                        <span className={`px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider border ${
                          selectedEmailDetail.ai_summary_json.urgency === 'high' ? 'bg-rose-500/10 text-rose-400 border-rose-500/30' :
                          selectedEmailDetail.ai_summary_json.urgency === 'low' ? 'bg-slate-500/10 text-slate-400 border-slate-500/20' :
                          'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        }`}>
                          {selectedEmailDetail.ai_summary_json.urgency === 'high' ? 'Act Now' :
                           selectedEmailDetail.ai_summary_json.urgency === 'low' ? 'For Reference' :
                           'Review Recommended'}
                        </span>
                      )}
                    </div>

                    {/* Overview */}
                    <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
                      <p className="text-sm leading-relaxed text-slate-200">{selectedEmailDetail.ai_summary_text}</p>
                    </div>

                    {/* Action Items */}
                    {selectedEmailDetail.ai_summary_json?.action_items && selectedEmailDetail.ai_summary_json.action_items.length > 0 && (
                      <div ref={actionItemsRef} className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
                        <p className="text-xs font-black text-indigo-400 uppercase tracking-wider mb-3">Action Items</p>
                        <ol className="space-y-2 list-decimal list-inside">
                          {selectedEmailDetail.ai_summary_json.action_items.map((action: string, idx: number) => (
                            <li key={idx} className="text-sm leading-relaxed text-slate-300">{action}</li>
                          ))}
                        </ol>
                      </div>
                    )}

                  </div>
                )}

                {/* Section 2: Full Message */}
                <div className="space-y-3 border-t border-white/5 pt-6">
                  <h3 className="text-sm font-black text-slate-400 uppercase tracking-wider">Full Message</h3>
                  <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 max-h-[50vh] overflow-y-auto custom-scrollbar">
                    <pre className="text-[13px] leading-[1.7] text-slate-300 whitespace-pre-wrap font-sans break-words">
                      {selectedEmailDetail.body || selectedEmailDetail.summary || 'No message body available.'}
                    </pre>
                  </div>
                </div>
              </div>

              {/* Panel Error (visible inside panel) */}
              {panelError && (
                <div className="space-y-3 border-t border-white/5 pt-6">
                  <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm">
                    <AlertCircle size={16} className="flex-shrink-0" />
                    <span className="font-bold">{panelError}</span>
                  </div>
                </div>
              )}

              {/* Section 4: Reply Compose (conditional) */}
              {showReplyCompose && (
                <div className="space-y-3 border-t border-white/5 pt-6">
                  <h3 className="text-sm font-black text-indigo-400 uppercase tracking-wider">Compose Reply</h3>
                  <textarea
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    placeholder="Type your reply here..."
                    rows={8}
                    className="w-full p-4 rounded-xl bg-white/[0.03] border border-white/10 text-slate-200 placeholder-slate-600 text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
                  />
                  {sendSuccess && (
                    <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm">
                      <span className="font-bold">✓ Reply sent successfully!</span>
                    </div>
                  )}
                </div>
              )}

              {/* Section 5: Actions - Sticky bottom */}
              <div className="sticky bottom-0 bg-[#0f172a]/95 backdrop-blur-sm border-t border-white/5 px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => closeDetailPanel()}
                    className="px-5 py-2.5 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-sm font-bold transition-all"
                  >
                    Close
                  </button>
                  {!selectedEmailDetail.ai_summary_text && selectedEmailDetail.gmail_message_id && (
                    <button
                      onClick={async () => {
                        const id = selectedEmailDetail.gmail_message_id!;
                        setSummarizingIds(prev => new Set(prev).add(id));
                        await apiService.summarizeEmail(id, activeEmail || 'default');
                        console.log('[PANEL] Summarization queued for', id);
                        setTimeout(() => {
                          fetchEmails(activeEmail);
                          setSummarizingIds(prev => { const next = new Set(prev); next.delete(id); return next; });
                        }, 8000);
                      }}
                      className="px-5 py-2.5 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-sm font-bold transition-all flex items-center gap-2"
                    >
                      <Sparkles size={14} />
                      Summarize
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {showReplyCompose ? (
                    <>
                      <button
                        onClick={() => {
                          setShowReplyCompose(false);
                          setReplyBody('');
                          setPanelError(null);
                        }}
                        className="px-5 py-2.5 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-sm font-bold transition-all"
                        disabled={sending}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSendReply}
                        disabled={sending || !replyBody.trim() || !selectedEmailDetail.thread_id}
                        className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold transition-all shadow-lg shadow-indigo-600/20 flex items-center gap-2"
                      >
                        {sending ? (
                          <>
                            <RefreshCw size={14} className="animate-spin" />
                            Sending...
                          </>
                        ) : (
                          <>
                            <Mail size={14} />
                            Send Reply
                          </>
                        )}
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => {
                        setPanelError(null);

                        if (!selectedEmailDetail.thread_id) {
                          setPanelError('Cannot reply: thread ID missing. Please refresh your emails and try again.');
                          return;
                        }

                        setShowReplyCompose(true);
                        setSendSuccess(false);
                      }}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-sm font-bold transition-all shadow-lg shadow-indigo-600/20 flex items-center gap-2"
                    >
                      <Mail size={14} />
                      Draft Reply
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Scroll to Top Button - Bottom Right */}
      <AnimatePresence>
        {showScrollTop && (
          <motion.button
            initial={{ opacity: 0, y: 20, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.8 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            className="fixed bottom-8 right-8 z-50 group"
            title="Scroll to top (Ctrl+Home)"
          >
            <div className="relative">
              {/* Glow effect */}
              <div className="absolute inset-0 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-2xl blur-xl opacity-50 group-hover:opacity-75 transition-opacity" />

              {/* Button */}
              <div className="relative flex items-center gap-2 px-4 py-3 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 border border-indigo-400/30 shadow-2xl group-hover:shadow-indigo-500/50 transition-all duration-300 group-hover:scale-105">
                <svg
                  className="w-5 h-5 text-white group-hover:animate-bounce"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
                <span className="text-white font-bold text-sm tracking-wide">TOP</span>
              </div>

              {/* Pulse ring */}
              <div className="absolute inset-0 rounded-2xl border-2 border-indigo-400/30 animate-ping opacity-20" />
            </div>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Send feedback toast */}
      <AnimatePresence>
        {sendToast && (
          <motion.div
            key="send-toast"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-[300] flex items-center gap-3 px-5 py-3 rounded-2xl border shadow-2xl text-sm font-bold pointer-events-none ${
              sendToast.type === 'success'
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 shadow-emerald-500/10'
                : 'bg-rose-500/15 border-rose-500/40 text-rose-300 shadow-rose-500/10'
            }`}
          >
            {sendToast.type === 'success' ? (
              <Shield size={16} className="flex-shrink-0 text-emerald-400" />
            ) : (
              <AlertCircle size={16} className="flex-shrink-0 text-rose-400" />
            )}
            <span>{sendToast.message}</span>
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
