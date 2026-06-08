import { useState, useEffect, useRef, useMemo } from 'react';
import './i18n';
import { apiService, AILanguage } from '@services';
import { websocketService, type EmailsUpdatedData, type SummaryReadyData } from '@services/websocket';
import { Sparkles, RefreshCw, Mail, MailOpen, Shield, AlertCircle, Clock, ChevronRight, Brain, LogOut, Send, Search, X, Paperclip } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { EmailViewModel, AccountInfo, SentEmail, SupportedLanguage, SupportedTone, EmailTemplate, DraftTone, InboxThreadRow, ReplyAttachmentDraft, AccountIntelligenceProfile } from '@types';
import { SentList } from './components/SentList';
import { EmailDetailModal } from './components/EmailDetailModal';
import { ReplyComposeModal } from './components/ReplyComposeModal';
import { AssistantPanel } from './components/AssistantPanel';
import { AccountSwitcherMobile } from './components/AccountSwitcherMobile';
import { AccountSwitcherDesktop } from './components/AccountSwitcherDesktop';
import { GlobeButton } from './components/GlobeButton';
import { NotificationCenter } from './components/NotificationCenter';
import { WakingUp } from './components/WakingUp';
import { getAccountColor, getEmailInitials } from './components/accountSwitcherHelpers';
import CategoryPillBar from './components/CategoryPillBar';
import AttachmentSearchToggle from './components/AttachmentSearchToggle';
import { isSearchQueryActive, shouldDisableAttachmentToggle, shouldResetAttachmentFilterOnInput, resolveSearchEmptyBodyKey } from './utils/searchFilterState';
import { deriveSpineSignals } from '@utils/deriveSpineSignals';
import { ThreadSpine } from './components/ThreadSpine';
import DeleteAccountModal from './components/DeleteAccountModal';

const devLog = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.log(...args);
  }
};

const AUTH_REQUIRED_EVENT = 'iea:auth-required';
const ITEMS_PER_PAGE = 5;
const MAX_CONNECTED_ACCOUNTS = 3;

/** Dangerous-extension denylist for client-side UX gate — aligned with backend policy. */
const BLOCKED_ATTACHMENT_EXTENSIONS = new Set([
  'ade', 'adp', 'apk', 'appx', 'appxbundle', 'bat', 'cab', 'chm', 'cmd', 'com',
  'cpl', 'diagcab', 'diagcfg', 'diagpkg', 'dll', 'dmg', 'ex', 'ex_', 'exe', 'hta',
  'img', 'ins', 'iso', 'isp', 'jar', 'jnlp', 'js', 'jse', 'lib', 'lnk', 'mde',
  'mjs', 'msc', 'msi', 'msix', 'msixbundle', 'msp', 'mst', 'nsh', 'pif', 'ps1',
  'scr', 'sct', 'shb', 'sys', 'vb', 'vbe', 'vbs', 'vhd', 'vxd', 'wsc', 'wsf', 'wsh', 'xll',
]);

const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

type FilterCategory = 'All' | 'Security' | 'Financial' | 'Work' | 'Personal' | 'Marketing' | 'General';

const CATEGORY_OPTIONS: FilterCategory[] = ['All', 'Security', 'Financial', 'Work', 'Personal', 'Marketing', 'General'];

const resolveCategoryLabelKey = (category: string) => {
  switch (category) {
    case 'All':
      return 'inbox.category_all';
    case 'Security':
      return 'inbox.categories.security';
    case 'Financial':
      return 'inbox.categories.financial';
    case 'Work':
      return 'inbox.categories.work';
    case 'Personal':
      return 'inbox.categories.personal';
    case 'Marketing':
      return 'inbox.categories.marketing';
    default:
      return 'inbox.categories.general';
  }
};

const resolveUrgencyLabelKey = (urgency: string) => {
  switch (urgency) {
    case 'high':
      return 'inbox.urgency.high';
    case 'low':
      return 'inbox.urgency.low';
    default:
      return 'inbox.urgency.medium';
  }
};

const FALLBACK_LANGUAGE_OPTIONS: SupportedLanguage[] = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'de', label: 'German', native: 'Deutsch' },
  { code: 'fr', label: 'French', native: 'Français' },
  { code: 'es', label: 'Spanish', native: 'Español' },
  { code: 'pt-BR', label: 'Portuguese (Brazil)', native: 'Português (Brasil)' },
  { code: 'tr', label: 'Turkish', native: 'Türkçe' },
  { code: 'ar', label: 'Arabic', native: 'العربية' },
  { code: 'zh', label: 'Chinese (Simplified)', native: '简体中文' },
  { code: 'ja', label: 'Japanese', native: '日本語' },
  { code: 'ko', label: 'Korean', native: '한국어' },
];

export const App = () => {
  const { t, i18n } = useTranslation();
  const [emailViewModels, setBriefings] = useState<EmailViewModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startupPhase, setStartupPhase] = useState<'probing' | 'waking' | 'ready'>('probing');
  const [showReadyToast, setShowReadyToast] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [filterCategory, setFilterCategory] = useState<FilterCategory>('All');
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [showSentinelToast, setShowSentinelToast] = useState(false);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [activeEmail, setActiveEmail] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [deleteAccountError, setDeleteAccountError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const activeEmailRef = useRef<string | null>(null); // Track current activeEmail for closures
  const lastSyncTimeRef = useRef<number>(0); // Track last sync timestamp for cooldown
  const syncingRef = useRef<boolean>(false); // Ref-based lock for synchronous check (prevents race conditions)
  const queuedSummarizeIdsRef = useRef<Set<string>>(new Set()); // Persistent in-flight tracking — prevents re-queuing
  const summaryRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null); // Coalesced one-shot refresh after summary jobs are queued
  const fetchingRef = useRef<boolean>(false); // Single-flight guard — only one fetchEmails in-flight at a time
  const fetchPendingRef = useRef<boolean>(false); // Coalesced rerun flag — set when a call arrives during in-flight fetch
  const lastFetchRequestedAccountRef = useRef<string | null | undefined>(null); // Latest account requested during in-flight fetch
  const lastFetchReasonRef = useRef<string | null>(null); // Latest reason tag for coalesced rerun logging
  const pendingSwitchAccountRef = useRef<string | null>(null); // Queued target account when switch arrives during active sync
  const initDoneRef = useRef<boolean>(false); // Prevent double initializeApp in React 18 StrictMode
  const wakeRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const readyToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [summarizingIds, setSummarizingIds] = useState<Set<string>>(new Set());
  const [selectedEmailDetail, setSelectedEmailDetail] = useState<EmailViewModel | null>(null);
  const [_notificationSeenIds, setNotificationSeenIds] = useState<Set<string>>(new Set());
  const [_notificationDismissedIds, setNotificationDismissedIds] = useState<Set<string>>(new Set());
  const [_notificationUnseenIds, setNotificationUnseenIds] = useState<Set<string>>(new Set());
  const [isNotificationCenterOpen, setIsNotificationCenterOpen] = useState(false);
  const [notificationUrgencyDeltaIds, setNotificationUrgencyDeltaIds] = useState<Set<string>>(new Set());
  const urgencySnapshotRef = useRef<Record<string, 'low' | 'medium' | 'high'>>({});
  const [isDesktopViewport, setIsDesktopViewport] = useState<boolean>(
    typeof window !== 'undefined' ? window.innerWidth >= 640 : true
  );
  const knownHighUrgencyIdsRef = useRef<Set<string>>(new Set());
  const [focusedItemIndex, setFocusedItemIndex] = useState<number | null>(null);
  const [keyboardMode, setKeyboardMode] = useState(false);
  const [shortcutsDisabledOnTouch, setShortcutsDisabledOnTouch] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return (
      window.matchMedia('(hover: none)').matches ||
      window.matchMedia('(pointer: coarse)').matches
    );
  });
  const [offlineAccounts, setOfflineAccounts] = useState<Set<string>>(new Set());
  const [scrollToActions, setScrollToActions] = useState(false);
  const actionItemsRef = useRef<HTMLDivElement | null>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [activeModal, setActiveModal] = useState<'none' | 'detail' | 'compose' | 'assistant'>('none');
  const [isDetailRead, setIsDetailRead] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const [replySubject, setReplySubject] = useState('');
  const [replyCC, setReplyCC] = useState('');
  const [sentToAddress, setSentToAddress] = useState('');
  const [sentCCAddress, setSentCCAddress] = useState('');
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [, setDiagnosticClickCount] = useState(0);
  const [panelView, setPanelView] = useState<'quick' | 'full'>('quick');
  const [detailIsSent, setDetailIsSent] = useState(false);
  const [activeTab, setActiveTab] = useState<'inbox' | 'sent'>('inbox');
  const [sentEmails, setSentEmails] = useState<SentEmail[]>([]);
  const [loadingSent, setLoadingSent] = useState(false);
  const [sentCurrentPage, setSentCurrentPage] = useState(1);
  const [readStatePending, setReadStatePending] = useState(false);
  const [aiLanguage, setAiLanguage] = useState<AILanguage>('en');
  const [aiLanguageLoading, setAiLanguageLoading] = useState(false);
  const [aiLanguageSaving, setAiLanguageSaving] = useState(false);
  const [aiLanguageError, setAiLanguageError] = useState<string | null>(null);
  const [aiLanguageSavedAccountId, setAiLanguageSavedAccountId] = useState<string | null>(null);
  const [supportedLanguages, setSupportedLanguages] = useState<SupportedLanguage[]>([]);
  const [selectedTone, setSelectedTone] = useState<DraftTone>('professional');
  const [availableTones, setAvailableTones] = useState<SupportedTone[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [templateDeletingId, setTemplateDeletingId] = useState<string | null>(null);
  const [replyAttachments, setReplyAttachments] = useState<ReplyAttachmentDraft[]>([]);
  const [replyAttachmentError, setReplyAttachmentError] = useState<string | null>(null);
  const [aiLanguageResolvedAccountId, setAiLanguageResolvedAccountId] = useState<string | null>(null);
  const [_accountIntelligenceProfile, setAccountIntelligenceProfile] = useState<AccountIntelligenceProfile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<EmailViewModel[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchHasAttachments, setSearchHasAttachments] = useState(false);
  const [expandedThreadIds, setExpandedThreadIds] = useState<Set<string>>(new Set());
  const [threadItemsById, setThreadItemsById] = useState<Record<string, EmailViewModel[]>>({});
  const [_threadLoadingIds, setThreadLoadingIds] = useState<Set<string>>(new Set());
  const [_threadLoadErrors, setThreadLoadErrors] = useState<Record<string, string | null>>({});
  const desktopSearchInputRef = useRef<HTMLInputElement | null>(null);
  const mobileSearchInputRef = useRef<HTMLInputElement | null>(null);
  const activeSearchInputRef = () =>
    window.innerWidth >= 640 ? desktopSearchInputRef.current : mobileSearchInputRef.current;
  const selectedEmailIdentity =
    selectedEmailDetail?.gmail_message_id ??
    selectedEmailDetail?.thread_id ??
    null;
  const aiLanguageRef = useRef<AILanguage>('en');
  const aiLanguageResolvedAccountRef = useRef<string | null>(null);
  const resolvedLanguageOptions =
    supportedLanguages.length > 0 ? supportedLanguages : FALLBACK_LANGUAGE_OPTIONS;

  const replyAttachmentsTotalBytes = replyAttachments.reduce((sum, a) => sum + a.size, 0);
  const attachmentsDisabled = !(accounts.find(a => a.account_id === activeEmail)?.send_scope === true);

  const brandName = t('nav.brand_name');
  const subtitle = t('nav.subtitle');
  const uiLanguage = i18n.resolvedLanguage ?? i18n.language ?? 'en';

  const getCategoryDisplayLabel = (category: string) => t(resolveCategoryLabelKey(category));
  const isCategoryPillBarRTL = uiLanguage === 'ar';
  const getUrgencyDisplayLabel = (urgency: string) => t(resolveUrgencyLabelKey(urgency));
  const getPageStatusLabel = (current: number, total: number) =>
    t('common.page_status', { current, total });

  const dateLocale = uiLanguage;

  const formatDisplayDate = (value?: string | null, fallback = t('inbox.unknown_time')) => {
    if (!value) return fallback;

    try {
      return new Date(value).toLocaleString(dateLocale, { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
      return fallback;
    }
  };

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

  const triggerSentinelAlert = (emailViewModel: EmailViewModel) => {
    if (notificationsEnabled && emailViewModel.should_alert) {
      new Notification(
        t('nav.sentinel_alert_notification_title', { brand: brandName }),
        {
          body: `[${emailViewModel.account}] ${emailViewModel.subject} - ${emailViewModel.summary.substring(0, 80)}...`,
          icon: "/vite.svg"
        }
      );
    }
  };

  const clearWakeRetryTimer = () => {
    if (wakeRetryTimerRef.current !== null) {
      clearTimeout(wakeRetryTimerRef.current);
      wakeRetryTimerRef.current = null;
    }
  };

  const clearReadyToastTimer = () => {
    if (readyToastTimerRef.current !== null) {
      clearTimeout(readyToastTimerRef.current);
      readyToastTimerRef.current = null;
    }
  };

  const showReadyToastBriefly = () => {
    clearReadyToastTimer();
    setShowReadyToast(true);
    readyToastTimerRef.current = setTimeout(() => {
      setShowReadyToast(false);
      readyToastTimerRef.current = null;
    }, 2000);
  };

  const probePublicHealth = async (timeoutMs: number): Promise<boolean> => {
    const controller = new AbortController();
    const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch('/health', {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });

      return response.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timeoutHandle);
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

  // Maps one InboxThreadRow to an EmailViewModel.  triggerAlerts=false suppresses
  // Sentinel notifications for search results (avoids alert spam on FTS queries).
  const mapRowToEmailViewModel = (e: InboxThreadRow, triggerAlerts: boolean): EmailViewModel => {
    const isoDate = e.date ?? e.created_at;
    const formattedDate = formatDisplayDate(isoDate);
    let priority: 'Low' | 'Medium' | 'High' = 'Medium';
    if (e.ai_summary_json?.urgency === 'high') priority = 'High';
    else if (e.ai_summary_json?.urgency === 'low') priority = 'Low';
    const displaySummary = e.ai_summary_text || e.body || t('inbox.awaiting_processing');
    const primaryAction = e.ai_summary_json?.action_items?.[0] || t('inbox.review_pending');
    const category = categorizeEmail(
      e.subject || '',
      e.sender || '',
      e.body || '',
      e.ai_summary_text ?? undefined
    );
    const emailViewModel: EmailViewModel = {
      account: e.account_id || t('common.unknown'),
      subject: e.subject || t('inbox.no_subject'),
      sender: e.sender || t('common.unknown'),
      date: formattedDate,
      date_iso: isoDate ?? null,
      priority,
      category,
      should_alert: e.ai_summary_json?.urgency === 'high',
      summary: displaySummary,
      action: primaryAction,
      body: e.body || '',
      ai_summary_json: e.ai_summary_json ?? undefined,
      ai_summary_text: e.ai_summary_text ?? undefined,
      ai_summary_model: e.ai_summary_model ?? undefined,
      ai_summary_language: e.ai_summary_language ?? null,
      ai_summary_is_fallback: e.ai_summary_is_fallback ?? false,
      ai_preferred_language: e.ai_preferred_language ?? null,
      ai_preferred_language_available: e.ai_preferred_language_available ?? false,
      gmail_message_id: e.gmail_message_id ?? undefined,
      thread_id: e.thread_id ?? undefined,
      thread_count: typeof e.thread_count === 'number' && e.thread_count >= 1 ? e.thread_count : 1,
      is_read: e.is_read !== undefined ? Boolean(e.is_read) : undefined,
      has_attachments: e.has_attachments ?? undefined,
      last_activity_iso: e.last_activity_iso ?? null,
      last_sender: e.last_sender ?? null,
    };
    if (triggerAlerts && emailViewModel.should_alert) {
      setTimeout(() => triggerSentinelAlert(emailViewModel), 500);
    }
    return emailViewModel;
  };

  const areIdSetsEqual = (a: Set<string>, b: Set<string>): boolean => {
    if (a.size !== b.size) return false;
    for (const value of a) {
      if (!b.has(value)) return false;
    }
    return true;
  };

  const getNotificationIdentity = (item: EmailViewModel): string | null => {
    const baseId = item.gmail_message_id ?? item.thread_id ?? null;
    if (!baseId) return null;
    return `${item.account}::${baseId}`;
  };

  const getNotificationUrgency = (item: EmailViewModel): 'low' | 'medium' | 'high' => {
    const rawUrgency = item.ai_summary_json?.urgency?.trim().toLowerCase();
    if (rawUrgency === 'high' || rawUrgency === 'medium' || rawUrgency === 'low') {
      return rawUrgency;
    }
    if (item.priority === 'High') return 'high';
    if (item.priority === 'Low') return 'low';
    return 'medium';
  };

  const getNotificationUrgencyWeight = (urgency: 'low' | 'medium' | 'high'): number => {
    if (urgency === 'high') return 3;
    if (urgency === 'medium') return 2;
    return 1;
  };

  const itemDateToEpoch = (item: EmailViewModel): number => {
    if (!item.date_iso) return Number.NEGATIVE_INFINITY;
    const parsed = Date.parse(item.date_iso);
    return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
  };

  const getNotificationItemsFromEmailViewModels = (items: EmailViewModel[]): EmailViewModel[] => {
    return items
      .filter((item) => item.should_alert)
      .sort((a, b) => {
        const urgencyDiff =
          getNotificationUrgencyWeight(getNotificationUrgency(b)) -
          getNotificationUrgencyWeight(getNotificationUrgency(a));

        if (urgencyDiff !== 0) return urgencyDiff;

        const timeA = itemDateToEpoch(a);
        const timeB = itemDateToEpoch(b);
        return timeB - timeA;
      });
  };

  // Updates cached thread message rows when read state changes for a thread.
  const _updateThreadItemReadState = (thread_id: string, is_read: boolean) => {
    setThreadItemsById(prev => {
      const rows = prev[thread_id];
      if (!rows) return prev;
      return { ...prev, [thread_id]: rows.map(r => ({ ...r, is_read })) };
    });
  };

  // Toggles thread expansion; fetches and caches messages on first expand.
  const _handleToggleThreadExpansion = async (item: EmailViewModel) => {
    const { thread_id, thread_count } = item;
    if (!thread_id) return;
    if ((thread_count ?? 1) <= 1) return;
    if (!activeEmail) return;

    if (expandedThreadIds.has(thread_id)) {
      setExpandedThreadIds(prev => { const s = new Set(prev); s.delete(thread_id); return s; });
      return;
    }

    if (threadItemsById[thread_id]) {
      setExpandedThreadIds(prev => new Set(prev).add(thread_id));
      return;
    }

    setExpandedThreadIds(prev => new Set(prev).add(thread_id));
    setThreadLoadingIds(prev => new Set(prev).add(thread_id));
    setThreadLoadErrors(prev => ({ ...prev, [thread_id]: null }));
    try {
      const rows = await apiService.getThreadMessages(thread_id, activeEmail, aiLanguageRef.current);
      const mapped = rows.map(row => mapRowToEmailViewModel(row, false));
      setThreadItemsById(prev => ({ ...prev, [thread_id]: mapped }));
    } catch {
      setThreadLoadErrors(prev => ({ ...prev, [thread_id]: 'error' }));
    } finally {
      setThreadLoadingIds(prev => { const s = new Set(prev); s.delete(thread_id); return s; });
    }
  };

  // Global session-expired handler: reset all UI state when backend returns 401
  useEffect(() => {
    const handleAuthRequired = () => {
      websocketService.disconnect();
      activeEmailRef.current = null;
      syncingRef.current = false;
      localStorage.removeItem('last_selected_account');
      setAccounts([]);
      setActiveEmail(null);
      setBriefings([]);
      setSentEmails([]);
      resetAccountScopedState();
      setLoading(false);
      setLoadingSent(false);
      setSyncing(false);
      setError(null);
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Scroll detection for scroll-to-top button
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 400);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Viewport breakpoint tracking — closes panel on mobile<->desktop transition
  useEffect(() => {
    let currentIsDesktop = window.innerWidth >= 640;
    const handleResize = () => {
      const nextIsDesktop = window.innerWidth >= 640;
      if (nextIsDesktop !== currentIsDesktop) {
        currentIsDesktop = nextIsDesktop;
        setIsDesktopViewport(nextIsDesktop);
        setIsNotificationCenterOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Touch-capability tracking — disables keyboard shortcuts on touch-primary devices
  useEffect(() => {
    const hoverQuery = window.matchMedia('(hover: none)');
    const pointerQuery = window.matchMedia('(pointer: coarse)');

    const recalculate = () => {
      const disabled = hoverQuery.matches || pointerQuery.matches;
      setShortcutsDisabledOnTouch(disabled);
      if (disabled) {
        setFocusedItemIndex(null);
        setKeyboardMode(false);
      }
    };

    recalculate();

    if (typeof hoverQuery.addEventListener === 'function') {
      hoverQuery.addEventListener('change', recalculate);
      pointerQuery.addEventListener('change', recalculate);

      return () => {
        hoverQuery.removeEventListener('change', recalculate);
        pointerQuery.removeEventListener('change', recalculate);
      };
    }

    hoverQuery.addListener(recalculate);
    pointerQuery.addListener(recalculate);

    return () => {
      hoverQuery.removeListener(recalculate);
      pointerQuery.removeListener(recalculate);
    };
  }, []);

  // Reset keyboard mode AND virtual selection on any pointer/wheel interaction
  // This prevents stale focusedItemIndex from surviving mouse/touch exits
  useEffect(() => {
    const handlePointerInteraction = () => {
      setKeyboardMode(false);
      setFocusedItemIndex(null);
    };
    window.addEventListener('pointerdown', handlePointerInteraction);
    window.addEventListener('mousedown', handlePointerInteraction);
    window.addEventListener('touchstart', handlePointerInteraction);
    window.addEventListener('wheel', handlePointerInteraction, { passive: true });
    return () => {
      window.removeEventListener('pointerdown', handlePointerInteraction);
      window.removeEventListener('mousedown', handlePointerInteraction);
      window.removeEventListener('touchstart', handlePointerInteraction);
      window.removeEventListener('wheel', handlePointerInteraction);
    };
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

  // Cmd+K / Ctrl+K: focus search input when no modal is blocking
  useEffect(() => {
    const handleSearchFocus = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k' && activeModal === 'none') {
        e.preventDefault();
        activeSearchInputRef()?.focus();
      }
    };
    window.addEventListener('keydown', handleSearchFocus);
    return () => window.removeEventListener('keydown', handleSearchFocus);
  }, [activeModal]);

  // Escape key: if compose is open → discard compose, stay on detail; else → close detail
  useEffect(() => {
    if (!selectedEmailDetail) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeModal === 'compose') {
          setActiveModal('detail');
          setReplyBody('');
          setReplySubject('');
          setReplyCC('');
          setPanelError(null);
          setReplyAttachments([]);
          setReplyAttachmentError(null);
        } else if (activeModal === 'assistant') {
          setActiveModal('detail');
        } else {
          setSelectedEmailDetail(null);
          setSendSuccess(false);
          setPanelError(null);
        }
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [selectedEmailDetail, activeModal]);

  // Search Escape: clear query or blur; yields to modal Escape handlers when any modal is open
  useEffect(() => {
    const handleSearchEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || activeModal !== 'none') return;
      const focused = document.activeElement;
      if (focused !== desktopSearchInputRef.current && focused !== mobileSearchInputRef.current) return;
      if (searchQuery.trim().length > 0) {
        resetSearch();
      } else {
        (focused as HTMLElement).blur();
      }
    };
    window.addEventListener('keydown', handleSearchEsc);
    return () => window.removeEventListener('keydown', handleSearchEsc);
  }, [activeModal, searchQuery]);

  // D2: Lock background scroll while detail panel is open; restore on close or unmount
  useEffect(() => {
    if (selectedEmailDetail) {
      document.body.classList.add('panel-open');
    } else {
      document.body.classList.remove('panel-open');
    }
    return () => {
      document.body.classList.remove('panel-open');
    };
  }, [selectedEmailDetail]);

  // Autofocus reply textarea when compose modal opens; place caret at top deterministically
  useEffect(() => {
    if (activeModal === 'compose' && replyTextareaRef.current) {
      const timer = setTimeout(() => {
        const el = replyTextareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(0, 0);
        el.scrollTop = 0;
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [activeModal]);

  // INVARIANT: Whenever the selected email identity changes or panel closes, force compose back to neutral.
  // This avoids leaking compose state across different emails while preserving compose state when the
  // currently selected email is merely refreshed from the latest emailViewModels data.
  useEffect(() => {
    if (!selectedEmailIdentity) {
      setActiveModal('none');
    }
    setReplyBody('');
    setReplyCC('');
    setSending(false);
    setPanelError(null);
    setReplyAttachments([]);
    setReplyAttachmentError(null);
  }, [selectedEmailIdentity]);

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

  // Run FTS search whenever query or active account changes; debounced 300ms
  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2 || !activeEmail) {
      setSearchResults([]);
      setSearchError(null);
      setSearchLoading(false);
      return;
    }
    let stale = false;
    const timer = setTimeout(async () => {
      if (stale) return;
      setSearchLoading(true);
      setSearchError(null);
      try {
        const rows = await apiService.searchEmails(trimmed, activeEmail, aiLanguageRef.current, 50, searchHasAttachments || undefined);
        if (!stale) setSearchResults(rows.map(e => mapRowToEmailViewModel(e, false)));
      } catch {
        if (!stale) setSearchError('error');
      } finally {
        if (!stale) setSearchLoading(false);
      }
    }, 300);
    return () => { stale = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, activeEmail, aiLanguage, searchHasAttachments]);

  // Rerun active search when emailViewModels change (read/unread mutations, summary refreshes, inbox refetches)
  // so the visible search card list stays coherent with inbox state without overwriting emailViewModels.
  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2 || !activeEmail) return;
    let stale = false;
    const timer = setTimeout(async () => {
      if (stale) return;
      if (!stale) setSearchError(null);
      try {
        const rows = await apiService.searchEmails(trimmed, activeEmail, aiLanguageRef.current, 50, searchHasAttachments || undefined);
        if (!stale) setSearchResults(rows.map(e => mapRowToEmailViewModel(e, false)));
      } catch {
        if (!stale) setSearchError('error');
      }
    }, 200);

    return () => { stale = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailViewModels]);

  // Reset category filtering when search becomes active.
  // Search results must remain flat and sovereign over inbox category filtering.
  useEffect(() => {
    const searchActivated = isSearchQueryActive(searchQuery) && !!activeEmail;
    if (!searchActivated) return;

    setCurrentPage(1);
    setFilterCategory((prev) => (prev === 'All' ? prev : 'All'));
  }, [searchQuery, activeEmail]);

  // Fetch sent emails when the Sent tab is active, or when the active account changes while Sent is open.
  useEffect(() => {
    if (activeTab !== 'sent' || !activeEmail) return;
    let cancelled = false;
    setLoadingSent(true);
    apiService.getSentEmails(activeEmail)
      .then(data => { if (!cancelled) setSentEmails(data); })
      .catch(() => { if (!cancelled) setSentEmails([]); })
      .finally(() => { if (!cancelled) setLoadingSent(false); });
    return () => { cancelled = true; };
  }, [activeTab, activeEmail]);

  // Reset sent page when switching tabs or accounts.
  useEffect(() => {
    setSentCurrentPage(1);
  }, [activeTab, activeEmail]);

  const SENT_PAGE_SIZE = 5;
  const sentTotalPages = Math.max(1, Math.ceil(sentEmails.length / SENT_PAGE_SIZE));
  const sentStartIndex = (sentCurrentPage - 1) * SENT_PAGE_SIZE;
  const currentSentItems = sentEmails.slice(sentStartIndex, sentStartIndex + SENT_PAGE_SIZE);

  // Clamp current page when emails shrink (e.g. re-fetch returns fewer results).
  useEffect(() => {
    if (sentCurrentPage > sentTotalPages) setSentCurrentPage(sentTotalPages);
  }, [sentCurrentPage, sentTotalPages]);

  // fetchEmails options:
  //   reason          — readable log tag for this trigger (e.g. 'runSync', 'ws:emails_updated')
  //   refetchAccounts — when true, also refetches /api/accounts and updates account state;
  //                     keep false for routine polls to halve the request count
  const fetchEmails = async (
    overrideAccountId?: string | null,
    opts: { reason?: string; refetchAccounts?: boolean } = {}
  ) => {
    const { reason = 'poll', refetchAccounts = false } = opts;
    const accountIdToUse = overrideAccountId !== undefined ? overrideAccountId : activeEmail;

    // ── Single-flight guard with coalesced rerun ────────────────────────────
    if (fetchingRef.current) {
      devLog(`[FETCH] In-flight — coalescing (reason: ${reason}, account: ${accountIdToUse ?? 'all'})`);
      fetchPendingRef.current = true;
      lastFetchRequestedAccountRef.current = accountIdToUse;
      lastFetchReasonRef.current = `coalesced:${reason}`;
      return;
    }
    fetchingRef.current = true;
    devLog(`[FETCH] Start (reason: ${reason}, account: ${accountIdToUse ?? 'all'})`);
    // ───────────────────────────────────────────────────────────────────────

    try {
      // Accounts are only refetched when the caller explicitly needs them
      // (e.g. OAuth callback, post-connect activation).
      // Routine email polls skip /api/accounts — halves request count in settled state.
      let emailData: InboxThreadRow[];
      let accountsForAutoSelect: AccountInfo[] | null = null;

      if (refetchAccounts) {
        const [emails, accountsData] = await Promise.all([
          accountIdToUse
            ? apiService.getInboxThreads(accountIdToUse, 50, aiLanguageRef.current)
            : Promise.resolve([]),
          apiService.listAccounts()
        ]);
        emailData = emails;
        const fetched: AccountInfo[] = accountsData.accounts || [];
        setAccounts(fetched);
        accountsForAutoSelect = fetched;
        // Auto-select first connected account when none is active (e.g. post-OAuth)
        const firstConnected = fetched.find((a: AccountInfo) => a.connected);
        if (firstConnected && !accountIdToUse) {
          setActiveEmail(firstConnected.account_id);
        }
      } else {
        emailData = accountIdToUse
          ? await apiService.getInboxThreads(accountIdToUse, 50, aiLanguageRef.current)
          : [];
      }

      // ── Stale-account guard ─────────────────────────────────────────────────
      // The fetch above was async. If the user switched accounts while it was
      // in-flight, activeEmailRef.current will have advanced to the new account.
      // Applying stale email data would overwrite the correct account's feed.
      // Only guard when we were fetching for a specific account (non-null).
      // The coalesced rerun in finally will carry the latest account automatically.
      if (accountIdToUse != null && activeEmailRef.current !== accountIdToUse) {
        devLog(
          `[FETCH] Stale — fetched: ${accountIdToUse}, active: ${activeEmailRef.current ?? 'none'} (reason: ${reason}). Discarding.`
        );
        return; // exits try → finally; coalesced rerun will handle new account if pending
      }
      // ────────────────────────────────────────────────────────────────────────

      // Trust backend order — /api/inbox returns threads sorted by latest activity DESC.
      // Client-side re-sort by individual message date would overwrite that ordering.
      const ordered = emailData || [];

      // Map DB schema to UI EmailViewModel (alerts enabled for normal inbox fetch)
      const mapped: EmailViewModel[] = ordered.map((e: InboxThreadRow) => mapRowToEmailViewModel(e, true));

      setBriefings(mapped);
      setError(null);
      setConsecutiveFailures(0);
      devLog(`[FETCH] Committed (reason: ${reason}, account: ${accountIdToUse ?? 'all'}, count: ${mapped.length})`);

      // Clear queuedSummarizeIdsRef for emails whose summaries have arrived
      mapped.forEach(e => {
        if (e.ai_summary_text && e.gmail_message_id) {
          queuedSummarizeIdsRef.current.delete(e.gmail_message_id);
        }
      });
      // Keep UI summarizing indicators in sync with persistent ref
      setSummarizingIds(new Set(queuedSummarizeIdsRef.current));

      // Auto-summarize only truly-new unsummarized emails
      // effectiveId falls back to the auto-selected account only when refetchAccounts was used
      const effectiveId = accountIdToUse
        || accountsForAutoSelect?.find((a: AccountInfo) => a.connected)?.account_id;
      if (effectiveId) {
        autoSummarizeEmails(mapped, effectiveId);
      }
    } catch {
      console.warn(`📡 [FETCH] Degraded (reason: ${reason})`);
      // Suppress error UI during active sync — transient failures are expected there
      if (!syncingRef.current) {
        setConsecutiveFailures((prev: number) => {
          const newFailureCount = prev + 1;
          if (emailViewModels.length === 0) {
            if (newFailureCount < 5) {
              setError(t('common.waking_backend'));
            } else {
              setError(t('common.connection_failure'));
            }
          }
          return newFailureCount;
        });
      }
    } finally {
      fetchingRef.current = false;
      // ── Coalesced rerun ─────────────────────────────────────────────────
      // If another fetchEmails call arrived while we were in-flight, run exactly
      // one follow-up now using the latest requested account + reason.
      if (fetchPendingRef.current) {
        fetchPendingRef.current = false;
        const pendingAccount = lastFetchRequestedAccountRef.current;
        const pendingReason = lastFetchReasonRef.current ?? 'coalesced';
        lastFetchRequestedAccountRef.current = null;
        lastFetchReasonRef.current = null;
        devLog(`[FETCH] Running coalesced follow-up (reason: ${pendingReason}, account: ${pendingAccount ?? 'all'})`);
        // setTimeout(0) lets React flush state from the current fetch before the next one starts
        setTimeout(() => fetchEmails(pendingAccount, { reason: pendingReason }), 0);
      }
      // ────────────────────────────────────────────────────────────────────
      setLoading(false);
    }
  };

  // Bounded polling summary refresh — replaces one-shot 12s timer.
  // Polls until all in-flight summarizingIds have resolved or the timeout budget is exhausted.
  // Multiple queue events within a polling window are coalesced (at most one timer active).
  const scheduleSummaryRefresh = (accountId: string) => {
    // Cancel any existing pending timer — only one polling chain at a time
    if (summaryRefreshTimerRef.current !== null) {
      clearTimeout(summaryRefreshTimerRef.current);
      summaryRefreshTimerRef.current = null;
    }

    // Poll intervals in ms: first poll at 6s, then every 6s, up to 8 polls (48s total budget)
    const POLL_INTERVALS_MS = [6000, 6000, 6000, 8000, 8000, 10000, 10000, 10000];
    let pollIndex = 0;

    const poll = async () => {
      summaryRefreshTimerRef.current = null;

      // Terminal: no more pending IDs — nothing left to refresh
      if (queuedSummarizeIdsRef.current.size === 0) {
        devLog('[SUMMARY-REFRESH] All summarizingIds resolved — stopping');
        return;
      }

      // Terminal: budget exhausted — clear tracking state and stop
      if (pollIndex >= POLL_INTERVALS_MS.length) {
        devLog('[SUMMARY-REFRESH] Polling budget exhausted — clearing summarizingIds');
        queuedSummarizeIdsRef.current.clear();
        setSummarizingIds(new Set());
        return;
      }

      // If full sync is already running, defer briefly to avoid concurrent fetch interference
      if (syncingRef.current) {
        devLog('[SUMMARY-REFRESH] Sync active — deferring 5s');
        summaryRefreshTimerRef.current = setTimeout(poll, 5000);
        return;
      }

      devLog(`[SUMMARY-REFRESH] Poll ${pollIndex + 1}/${POLL_INTERVALS_MS.length} for account:`, accountId);
      await fetchEmails(accountId, { reason: `summary-refresh:poll-${pollIndex + 1}` });

      // After fetch, queuedSummarizeIdsRef is updated by fetchEmails (cleared for resolved emails)
      pollIndex++;

      if (queuedSummarizeIdsRef.current.size === 0) {
        devLog('[SUMMARY-REFRESH] All summaries visible — done');
        return;
      }

      // Schedule next poll
      summaryRefreshTimerRef.current = setTimeout(poll, POLL_INTERVALS_MS[pollIndex] ?? 10000);
    };

    summaryRefreshTimerRef.current = setTimeout(poll, POLL_INTERVALS_MS[0]);
  };

  const autoSummarizeEmails = async (emails: EmailViewModel[], accountId: string) => {
    // Only queue emails that are unsummarized AND not already tracked in-flight
    const toQueue = emails.filter(
      e => !e.ai_summary_text && e.gmail_message_id && !queuedSummarizeIdsRef.current.has(e.gmail_message_id)
    );
    if (toQueue.length === 0) return;

    devLog('[AUTO-SUMMARIZE] Queuing', toQueue.length, 'new emails (already tracked:', queuedSummarizeIdsRef.current.size, ')');

    // Register all new IDs in persistent ref BEFORE firing requests — prevents re-queuing
    toQueue.forEach(e => queuedSummarizeIdsRef.current.add(e.gmail_message_id!));

    // Keep UI summarizing indicators in sync with persistent ref
    setSummarizingIds(new Set(queuedSummarizeIdsRef.current));

    const BATCH_SIZE = 5;
    for (let i = 0; i < toQueue.length; i += BATCH_SIZE) {
      const batch = toQueue.slice(i, i + BATCH_SIZE);
      try {
        await Promise.all(
          batch.map(email =>
            apiService.summarizeEmail(email.gmail_message_id!, accountId, aiLanguageRef.current)
          )
        );
        devLog(`[AUTO-SUMMARIZE] Batch ${Math.floor(i / BATCH_SIZE) + 1} queued (${batch.length} emails)`);
      } catch (err) {
        console.warn('[AUTO-SUMMARIZE] Batch failed:', err);
      }

      if (i + BATCH_SIZE < toQueue.length) {
        await new Promise(r => setTimeout(r, 500));
      }
    }

    // Schedule a single bounded follow-up fetch to reveal completed summaries.
    // scheduleSummaryRefresh coalesces multiple calls — safe against double-queuing.
    // queuedSummarizeIdsRef entries are cleared in fetchEmails when ai_summary_text arrives.
    devLog('[AUTO-SUMMARIZE] All jobs queued. Scheduling bounded summary refresh.');
    scheduleSummaryRefresh(accountId);
  };

  // Unified sync runner — single lock owner for all sync call sites.
  // Does NOT touch `loading` state; call sites that want skeleton spinners set it themselves.
  const runSync = async (accountId: string): Promise<void> => {
    if (syncingRef.current) {
      // Record the requested account as a pending switch target.
      // Do NOT call setLoading(false) — if the caller set loading=true expecting a handoff,
      // loading must stay true until the queued switch executes and fetchEmails completes.
      pendingSwitchAccountRef.current = accountId;
      devLog(`[SWITCH] Sync busy; queued pending switch for account: ${accountId}`);
      return;
    }
    syncingRef.current = true;
    lastSyncTimeRef.current = Date.now();
    setSyncing(true);

    try {
      const syncResult = await apiService.syncNow(accountId);
      devLog('[SYNC] Result:', syncResult);
      if (syncResult.status === 'auth_required') {
        setOfflineAccounts(prev => new Set(prev).add(accountId));
      } else {
        setOfflineAccounts(prev => { const next = new Set(prev); next.delete(accountId); return next; });
      }
      if (syncResult.status === 'timeout') {
        // Backend timed out but DB writes may still be in-flight.
        // Perform 3 bounded reconciliation fetches with ~3s gaps to catch late-arriving rows.
        console.warn('[SYNC] Backend timeout — starting reconciliation fetches');
        await fetchEmails(accountId, { reason: 'runSync:timeout-r1' });
        for (let pass = 2; pass <= 3; pass++) {
          await new Promise<void>(resolve => setTimeout(resolve, 3000));
          if (activeEmailRef.current !== accountId) break; // Account switched — abort
          await fetchEmails(accountId, { reason: `runSync:timeout-r${pass}` });
        }
      } else {
        await fetchEmails(accountId, { reason: 'runSync:success' });
      }
    } catch (err) {
      console.error('[SYNC] Failed:', err);
      await fetchEmails(accountId, { reason: 'runSync:error-fallback' }); // Still render stale DB data
    } finally {
      syncingRef.current = false;
      setSyncing(false);

      // ── Pending switch execution ────────────────────────────────────────────
      // If an account switch arrived while this sync was running, execute it now.
      const pendingAccount = pendingSwitchAccountRef.current;
      if (pendingAccount !== null) {
        pendingSwitchAccountRef.current = null;
        if (pendingAccount !== accountId) {
          // Different target account — launch its sync cycle immediately
          devLog(`[SWITCH] Applying queued pending switch for account: ${pendingAccount}`);
          runSync(pendingAccount); // Non-awaited: let it claim the lock and drive fetch/loading
        } else {
          // Same account already synced — no re-run needed, ensure loading is cleared
          setLoading(false);
          devLog(`[SWITCH] Queued switch resolved by completed sync for: ${pendingAccount}`);
        }
      }
      // ───────────────────────────────────────────────────────────────────────
    }
  };

  const autoSync = async () => {
    // All guards must pass BEFORE delegating to runSync
    const now = Date.now();
    const COOLDOWN_MS = 60000; // 60 seconds
    if (now - lastSyncTimeRef.current < COOLDOWN_MS) return;
    if (document.visibilityState !== 'visible') return;
    if (!activeEmailRef.current) return;

    await runSync(activeEmailRef.current);
  };

  useEffect(() => {
    let cancelled = false;

    // Initial load: Load accounts — neutral startup, never auto-select
    const initializeApp = async () => {
      try {
        const accountsData = await apiService.listAccounts();
        if (cancelled) return;

        const loadedAccounts: AccountInfo[] = accountsData.accounts || [];
        setAccounts(loadedAccounts);

        // Account selection logic (neutral startup):
        // Always show onboarding or selection screen — never auto-select.
        // Post-OAuth callback activation is handled by its own dedicated useEffect.
        const connectedList = loadedAccounts.filter(a => a.connected);

        if (connectedList.length === 0) {
          devLog('[INIT] No connected accounts -> showing onboarding');
        } else {
          devLog(`[INIT] ${connectedList.length} connected account(s) -> showing selection screen`);
        }

        setLoading(false);
      } catch (error) {
        if (cancelled) return;
        console.warn('[STRATEGY] Failed to load accounts on init', error);
        setLoading(false);
      }
    };

    const scheduleWakeRetry = () => {
      clearWakeRetryTimer();

      const retry = async () => {
        const probeOk = await probePublicHealth(3000);
        if (cancelled) return;

        if (probeOk) {
          await initializeApp();
          if (cancelled) return;
          setStartupPhase('ready');
          showReadyToastBriefly();
          return;
        }

        wakeRetryTimerRef.current = setTimeout(retry, 4000);
      };

      wakeRetryTimerRef.current = setTimeout(retry, 4000);
    };

    const bootstrapStartup = async () => {
      let wakingShown = false;
      const wakingGateTimer = setTimeout(() => {
        wakingShown = true;
        if (!cancelled) {
          setStartupPhase('waking');
        }
      }, 800);

      const probeOk = await probePublicHealth(3000);
      clearTimeout(wakingGateTimer);
      if (cancelled) return;

      if (probeOk) {
        await initializeApp();
        if (cancelled) return;
        setStartupPhase('ready');
        if (wakingShown) {
          showReadyToastBriefly();
        }
        return;
      }

      setStartupPhase('waking');
      scheduleWakeRetry();
    };

    if (!initDoneRef.current) {
      initDoneRef.current = true;
      setLoading(true);
      bootstrapStartup();
    }

    // Note: autoSync removed from init - will sync when user selects account

    // Realtime updates via WebSocket
    const handleEmailsUpdated = (data: EmailsUpdatedData) => {
      devLog("[STRATEGY] Realtime update received:", data);
      // Skip if runSync is already active — its fetchEmails completion will carry the update
      if (syncingRef.current) {
        devLog('[FETCH] ws:emails_updated — sync active, skipping redundant fetch');
        return;
      }
      fetchEmails(activeEmailRef.current, { reason: 'ws:emails_updated' });
    };

    const handleSummaryReady = (data: SummaryReadyData) => {
      devLog("[STRATEGY] Summaries ready:", data);
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
      cancelled = true;
      websocketService.off("emails_updated", handleEmailsUpdated);
      websocketService.off("summary_ready", handleSummaryReady);
      clearInterval(autoSyncInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      clearWakeRetryTimer();
      clearReadyToastTimer();
      if (summaryRefreshTimerRef.current !== null) {
        clearTimeout(summaryRefreshTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional mount-only startup orchestration: timers, websocket subscriptions, wake retry, and init lifecycle must not be rebound by callback identity changes
  }, []);


  // Keep activeEmailRef in sync with activeEmail state + persist to localStorage
  useEffect(() => {
    activeEmailRef.current = activeEmail;
    if (activeEmail) {
      localStorage.setItem('last_selected_account', activeEmail);
    }
  }, [activeEmail]);

  // Fetch account intelligence profile whenever the active account changes.
  useEffect(() => {
    let cancelled = false;

    if (!activeEmail) {
      setAccountIntelligenceProfile(null);
      return;
    }

    apiService.getAccountIntelligenceProfile(activeEmail).then((profile) => {
      if (cancelled || activeEmailRef.current !== activeEmail) return;
      setAccountIntelligenceProfile(profile);
    }).catch((error) => {
      if (cancelled || activeEmailRef.current !== activeEmail) return;
      console.warn('[intelligence] failed to load account intelligence profile:', error);
      setAccountIntelligenceProfile(null);
    });

    return () => {
      cancelled = true;
    };
  }, [activeEmail]);

  // Socket.IO is session-scoped, not account-scoped.
  // The channel connects when any authenticated
  // account exists and disconnects when none remain.
  // Account switching does not affect this channel.
  const hasAuthenticatedSession = useMemo(
    () => accounts.some(a => !a.auth_required),
    [accounts]
  );

  useEffect(() => {
    if (hasAuthenticatedSession) {
      websocketService.connect();
    } else {
      websocketService.disconnect();
    }
  }, [hasAuthenticatedSession]);

  // Keep aiLanguageRef in sync for closure-safe access inside fetchEmails
  useEffect(() => {
    aiLanguageRef.current = aiLanguage;
  }, [aiLanguage]);

  // Load supported languages + tones from backend on mount (once)
  useEffect(() => {
    let cancelled = false;

    const loadStaticOptions = async () => {
      const [langs, tones] = await Promise.all([
        apiService.getSupportedLanguages(),
        apiService.getSupportedTones(),
      ]);

      if (cancelled) return;

      if (langs.length > 0) setSupportedLanguages(langs);
      if (tones.length > 0) setAvailableTones(tones);
    };

    loadStaticOptions();

    return () => {
      cancelled = true;
    };
  }, []);

  // Sync selectedEmailDetail with latest emailViewModels data so language metadata stays fresh after a re-fetch
  useEffect(() => {
    if (!selectedEmailDetail?.gmail_message_id) return;
    const fresh = emailViewModels.find(b => b.gmail_message_id === selectedEmailDetail.gmail_message_id);
    if (fresh) setSelectedEmailDetail(fresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailViewModels]);

  useEffect(() => {
    const highUrgencyItems = getNotificationItemsFromEmailViewModels(emailViewModels);
    const currentIds = new Set(
      highUrgencyItems
        .map((item) => getNotificationIdentity(item))
        .filter((id): id is string => id !== null)
    );

    setNotificationSeenIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => currentIds.has(id)));
      return areIdSetsEqual(prev, next) ? prev : next;
    });

    setNotificationDismissedIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => currentIds.has(id)));
      return areIdSetsEqual(prev, next) ? prev : next;
    });

    setNotificationUnseenIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => currentIds.has(id)));

      currentIds.forEach((id) => {
        if (!knownHighUrgencyIdsRef.current.has(id)) {
          next.add(id);
        }
      });

      return areIdSetsEqual(prev, next) ? prev : next;
    });

    knownHighUrgencyIdsRef.current = currentIds;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailViewModels]);

  useEffect(() => {
    let cancelled = false;

    const loadAiLanguage = async () => {
      aiLanguageResolvedAccountRef.current = null;
      setAiLanguageResolvedAccountId(null);

      if (!activeEmail) {
        setAiLanguage('en');
        setAiLanguageError(null);
        setAiLanguageSavedAccountId(null);
        setAiLanguageLoading(false);
        setAiLanguageSaving(false);
        return;
      }

      setAiLanguageLoading(true);
      setAiLanguageError(null);
      setAiLanguageSavedAccountId(null);

      try {
        const response = await apiService.getPreferences(activeEmail);
        if (cancelled || activeEmailRef.current !== activeEmail) return;

        const resolvedLanguage = response.ai_language ?? 'en';
        setAiLanguage(resolvedLanguage);
        aiLanguageResolvedAccountRef.current = activeEmail;
        setAiLanguageResolvedAccountId(activeEmail);
      } catch (error) {
        if (cancelled || activeEmailRef.current !== activeEmail) return;

        setAiLanguage('en');
        setAiLanguageError(null);
        aiLanguageResolvedAccountRef.current = activeEmail;
        setAiLanguageResolvedAccountId(activeEmail);
      } finally {
        if (!cancelled && activeEmailRef.current === activeEmail) {
          setAiLanguageLoading(false);
        }
      }
    };

    loadAiLanguage();

    return () => {
      cancelled = true;
    };
  }, [activeEmail]);

  useEffect(() => {
    let cancelled = false;

    const loadTemplatesForActiveContext = async () => {
      if (!activeEmail) {
        setTemplates([]);
        setTemplatesLoading(false);
        setTemplatesError(null);
        setTemplateSaving(false);
        setTemplateDeletingId(null);
        setSelectedTone('professional');
        return;
      }

      const languageResolvedForActiveAccount =
        aiLanguageResolvedAccountId === activeEmail &&
        aiLanguageResolvedAccountRef.current === activeEmail;

      // Block template loading until the active account's language is resolved.
      // This avoids transient wrong-language fetches on account switch.
      if (!languageResolvedForActiveAccount) {
        setTemplates([]);
        setTemplatesLoading(false);
        setTemplatesError(null);
        return;
      }

      setTemplatesLoading(true);
      setTemplatesError(null);

      try {
        const rows = await apiService.listTemplates(activeEmail, aiLanguage);
        if (cancelled || activeEmailRef.current !== activeEmail) return;
        setTemplates(rows);
      } catch (error) {
        if (cancelled || activeEmailRef.current !== activeEmail) return;
        setTemplates([]);
        setTemplatesError(t('compose.templates_load_failed'));
      } finally {
        if (!cancelled && activeEmailRef.current === activeEmail) {
          setTemplatesLoading(false);
        }
      }
    };

    loadTemplatesForActiveContext();

    return () => {
      cancelled = true;
    };
  }, [activeEmail, aiLanguage, aiLanguageResolvedAccountId, t]);

  // Detect OAuth callback success and auto-activate the newly connected account
  // CRITICAL: Retry logic with exponential backoff to handle replication delays
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const authSuccess = urlParams.get('auth') === 'success';
    const newAccountId = urlParams.get('account_id'); // Backend passes URL-decoded email

    if (!authSuccess) return;

    devLog(`[OAUTH-CALLBACK] Detected - target account: ${newAccountId || 'MISSING'}`);

    // Clean up URL immediately to prevent re-triggering
    window.history.replaceState({}, document.title, window.location.pathname);

    if (!newAccountId) {
      console.error('[OAUTH-CALLBACK] CRITICAL: account_id parameter missing from callback URL');
      setError(t('auth.oauth_account_missing'));
      return;
    }

    // Retry logic: Poll for account to appear (handles Supabase replication delay)
    const MAX_RETRIES = 5;
    const INITIAL_DELAY = 1000; // Start with 1s
    let retryCount = 0;

    const attemptActivation = async () => {
      retryCount++;
      const delay = INITIAL_DELAY * Math.pow(1.5, retryCount - 1); // Exponential backoff

      devLog(`[OAUTH-CALLBACK] Attempt ${retryCount}/${MAX_RETRIES} - checking for account: ${newAccountId}`);

      try {
        // Reload accounts from backend
        const accountsData = await apiService.listAccounts();
        const loadedAccounts: AccountInfo[] = accountsData.accounts || [];

        devLog(`[OAUTH-CALLBACK] Found ${loadedAccounts.length} accounts:`, loadedAccounts.map(a => a.account_id));

        setAccounts(loadedAccounts);

        // CRITICAL: Only activate if EXACT match found (no fallback)
        const targetAccount = loadedAccounts.find(a => a.account_id === newAccountId);

        if (targetAccount) {
          devLog(`[OAUTH-CALLBACK] ✅ SUCCESS - Activating: ${newAccountId}`);
          setActiveEmail(newAccountId);
          localStorage.setItem('last_selected_account', newAccountId);
          setOfflineAccounts(prev => { const next = new Set(prev); next.delete(newAccountId); return next; });
          fetchEmails(newAccountId, { reason: 'oauth-callback' });
          return;
        }

        // Account not found yet - retry if attempts remaining
        if (retryCount < MAX_RETRIES) {
          devLog(`[OAUTH-CALLBACK] ⏳ Account not found yet - retrying in ${delay}ms...`);
          setTimeout(attemptActivation, delay);
        } else {
          // Max retries exceeded - show error
          console.error(`[OAUTH-CALLBACK] ❌ FAILED - Account ${newAccountId} not found after ${MAX_RETRIES} attempts`);
          setError(t('auth.oauth_activation_failed', { account: newAccountId }));
          // Leave user on account selection screen - don't auto-activate wrong account
        }
      } catch (error) {
        console.error(`[OAUTH-CALLBACK] Attempt ${retryCount} failed:`, error);
        if (retryCount < MAX_RETRIES) {
          setTimeout(attemptActivation, delay);
        } else {
          setError(t('auth.oauth_load_accounts_failed'));
        }
      }
    };

    // Start activation attempts
    attemptActivation();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-shot OAuth callback handler: URL param consumption, history cleanup, and retry activation flow must not retrigger due to callback identity changes
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

  const getKeyboardCardDomId = (item: EmailViewModel, index: number): string => {
    const raw = item.gmail_message_id || item.thread_id || item.subject || `index-${index}`;
    const safe = raw.replace(/[^a-zA-Z0-9_-]/g, '-');
    return `inbox-card-${safe}-${index}`;
  };

  const isShortcutBlockedTarget = (target: EventTarget | null): boolean => {
    if (!(target instanceof Element)) return false;
    return target.closest('input, textarea, select, button, a, [contenteditable="true"], [role="button"]') !== null;
  };

  const handleDisconnect = async (account_id: string) => {
    setConfirmDisconnect(null);
    devLog(`[DISCONNECT] Disconnecting account: ${account_id}`);
    const wasActiveAccount = activeEmail === account_id;

    try {
      if (wasActiveAccount) {
        websocketService.disconnect();
        activeEmailRef.current = null;
        syncingRef.current = false;
      }

      await apiService.disconnectAccount(account_id);
      devLog(`[DISCONNECT] Successfully disconnected: ${account_id}`);

      if (wasActiveAccount) {
        setActiveEmail(null);
        localStorage.removeItem('last_selected_account');
        setBriefings([]);
        setSentEmails([]);
        resetAccountScopedState();
        setLoading(false);
        setLoadingSent(false);
        setSyncing(false);
        setError(null);
        devLog(`[DISCONNECT] Cleared active account (was ${account_id})`);
      } else {
        // Non-active account removed — refresh account list only.
        // Cookie was NOT cleared by backend. Session remains valid.
        const updated = await apiService.listAccounts();
        const loadedAccounts: AccountInfo[] = updated.accounts || [];
        setAccounts(loadedAccounts);
        devLog(`[DISCONNECT] Reloaded ${loadedAccounts.length} accounts`);
      }
    } catch (err) {
      console.error('[DISCONNECT] Failed to disconnect account:', account_id, err);
      setError(t('auth.disconnect_account_failed', { account: account_id }));
    }
  };

  const handleDeleteAccountSuccess =
    async () => {
      setIsDeletingAccount(true);
      try {
        await apiService.deleteUserAccount();
        websocketService.disconnect();
        window.location.href = '/';
      } catch (err) {
        setDeleteAccountError(
          'Deletion failed. Please try again.'
        );
        setIsDeletingAccount(false);
      }
    };

  const connectedAccounts = accounts.filter(a => a.connected);
  const hasLegacyAccounts = connectedAccounts.some(a => a.account_id === 'default' || a.account_id === 'PRIMARY');

  // ── BL-01: Reply compose helpers ──────────────────────────────────────────
  const normalizeReplySubject = (subject: string): string => {
    const trimmed = subject.trim();
    if (!trimmed) return t('compose.reply_subject_no_subject');
    const withoutRe = trimmed.replace(/^(re:\s*)+/i, '');
    return `Re: ${withoutRe}`;
  };

  const buildAttribution = (date: string, sender: string): string => {
    if (date && sender) return t('compose.attribution_on_date_sender', { date, sender });
    if (sender) return t('compose.attribution_sender_only', { sender });
    if (date) return t('compose.attribution_date_only', { date });
    return t('compose.original_message');
  };

  // Conservative sanitizer for the original message body.
  // Removes quote prefixes, collapses blank lines, stops at prior-thread history markers.
  // maxChars=500 (default) caps the result for read-only preview/reference use.
  // maxChars=0 disables the cap — used by outbound send composition to preserve the full sanitized body.
  const sanitizeOriginalExcerpt = (body: string, maxChars = 500): string => {
    // 1. Normalize line endings
    const normalized = body.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const lines = normalized.split('\n');

    // 2. Stop before obvious prior-thread markers (conservatively)
    const historyMarkers = [
      /^On .+ wrote:\s*$/i,
      /^-{3,}\s*Original Message\s*-{3,}/i,
      /^From:\s/i,
    ];
    const stopIdx = lines.findIndex(l => historyMarkers.some(re => re.test(l.trim())));
    const relevant = stopIdx === -1 ? lines : lines.slice(0, stopIdx);

    // 3. Strip leading quote prefixes ("> ", ">>", etc.) from each line
    const stripped = relevant.map(l => l.replace(/^(\s*>+\s?)+/, '').trimEnd());

    // 4. Collapse 2+ consecutive blank lines into 1
    const collapsed: string[] = [];
    let blanks = 0;
    for (const l of stripped) {
      if (l === '') { if (++blanks <= 1) collapsed.push(l); }
      else { blanks = 0; collapsed.push(l); }
    }

    // 5. Join, trim edges, optionally cap
    const result = collapsed.join('\n').trim();
    if (maxChars > 0 && result.length > maxChars) {
      return result.slice(0, maxChars) + '…';
    }
    return result;
  };

  // Builds the outbound plain-text body: user reply + professional attribution + sanitized excerpt.
  // Disables the excerpt cap (maxChars=0) so the full sanitized body is preserved in outbound composition.
  // No ">" markers — clean for all recipients.
  const buildOutboundBody = (userText: string, date: string, sender: string, body: string): string => {
    const excerpt = sanitizeOriginalExcerpt(body, 0);
    return excerpt
      ? `${userText}\n\n${buildAttribution(date, sender)}\n${excerpt}`
      : userText;
  };
  // ──────────────────────────────────────────────────────────────────────────

  const handleSendReply = async () => {
    if (!selectedEmailDetail?.thread_id) {
      setPanelError(t('compose.cannot_send_missing_thread'));
      return;
    }

    const userText = replyBody.trim();
    if (!userText) {
      setPanelError(t('compose.empty_reply'));
      return;
    }

    if (replyAttachmentError) {
      setPanelError(replyAttachmentError);
      return;
    }

    if (replyAttachments.length > 0 && attachmentsDisabled) {
      setPanelError(t('compose.attachment_scope_required'));
      return;
    }

    setSending(true);
    setPanelError(null);

    const originalBody = selectedEmailDetail.body || '';
    const date = formatDisplayDate(selectedEmailDetail.date_iso, selectedEmailDetail.date || '');
    const sender = selectedEmailDetail.sender || '';
    const outboundBody = originalBody
      ? buildOutboundBody(userText, date, sender, originalBody)
      : userText;
    const ccValue = replyCC.trim() || undefined;

    try {
      const result = await apiService.sendThreadReply(
        selectedEmailDetail.thread_id,
        outboundBody,
        replySubject || undefined,
        ccValue,
        replyAttachments.length > 0 ? replyAttachments : undefined
      );

      if (result.success) {
        devLog('[SEND] Email sent successfully:', result.message_id);
        setSentToAddress(result.sent_to || '');
        setSentCCAddress(result.sent_cc || '');
        setSendSuccess(true);
        setReplyBody('');
        setReplySubject('');
        setReplyCC('');
        setReplyAttachments([]);
        setReplyAttachmentError(null);
        setActiveModal('detail');
        setPanelError(null);

        await fetchEmails(activeEmail, { reason: 'post-send' });
        setTimeout(() => { setSendSuccess(false); setSentToAddress(''); setSentCCAddress(''); }, 4000);
      } else {
        setPanelError(result.error || t('compose.send_failed'));
      }
    } catch (err: unknown) {
      console.error('[SEND] Unexpected error:', err);
      setPanelError(t('common.network_error_try_again'));
    } finally {
      setSending(false);
    }
  };

  // Reset all account-scoped UI state immediately on account switch.
  // CRITICAL: clears the feed to prevent old-account cards remaining visible under new account label.
  const resetSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
    setSearchError(null);
    setSearchLoading(false);
    setSearchHasAttachments(false);
  };

  const resetAccountScopedState = () => {
    devLog('[SWITCH] Resetting account-scoped UI state');
    // Feed — must be cleared immediately so old account cards are not visible under new account label
    setBriefings([]);
    setSummarizingIds(new Set());
    queuedSummarizeIdsRef.current.clear();
    // Cancel any pending summary-refresh timer — it belongs to the old account
    if (summaryRefreshTimerRef.current !== null) {
      clearTimeout(summaryRefreshTimerRef.current);
      summaryRefreshTimerRef.current = null;
    }
    // Detail panel + compose state
    setSelectedEmailDetail(null);
    setActiveModal('none');
    setReplyBody('');
    setReplySubject('');
    setReplyCC('');
    setSentToAddress('');
    setSentCCAddress('');
    setSending(false);
    setSendSuccess(false);
    setPanelError(null);
    setScrollToActions(false);
    setAiLanguageSavedAccountId(null);
    setFilterCategory('All');
    setCurrentPage(1);

    // P4 shared tone/template state
    setSelectedTone('professional');
    setTemplates([]);
    setTemplatesLoading(false);
    setTemplatesError(null);
    setTemplateSaving(false);
    setTemplateDeletingId(null);
    setAiLanguageResolvedAccountId(null);
    aiLanguageResolvedAccountRef.current = null;
    // P5.4 attachment compose state
    setReplyAttachments([]);
    setReplyAttachmentError(null);
    resetSearch();
  };

  // Close details panel. Compose state is handled by the selectedEmailDetail invariant effect.
  // sendSuccess is NOT cleared here — the app-level toast must survive panel close.
  const closeDetailPanel = () => {
    setSelectedEmailDetail(null);
    setDiagnosticClickCount(0);
  };

  // Open a specific email in the details panel, resetting any previous compose state
  const openEmailDetail = (item: EmailViewModel, scrollToAct = false, isSent = false) => {
    setActiveModal('detail');
    setReplyBody('');
    setReplySubject('');
    setReplyCC('');
    setSentToAddress('');
    setSendSuccess(false);
    setPanelError(null);
    setReplyAttachments([]);
    setReplyAttachmentError(null);
    setScrollToActions(scrollToAct);
    setPanelView('quick');
    setDetailIsSent(isSent);
    setIsDetailRead(!!item.is_read);
    setSelectedTone('professional');
    setTemplatesError(null);
    setTemplateSaving(false);
    setTemplateDeletingId(null);
    setSelectedEmailDetail(item);
    // Auto-mark read for unread inbox items when modify scope is available
    if (!isSent && !item.is_read && item.thread_id && activeEmail) {
      const acct = accounts.find(a => a.account_id === activeEmail);
      if (acct?.modify_scope) {
        const capturedAccountId = activeEmail;
        apiService.setThreadReadState(item.thread_id, true, capturedAccountId).then(res => {
          if (res.success === true && res.gmail_updated === true) {
            setIsDetailRead(true);
            setBriefings(prev => prev.map(b =>
              b.thread_id === item.thread_id ? { ...b, is_read: true } : b
            ));
            if (item.thread_id) _updateThreadItemReadState(item.thread_id, true);
            if (res.db_updated === false) {
              console.warn('[READ-STATE] DB mirror unconfirmed on auto-mark-read:', res.db_error);
              fetchEmails(capturedAccountId, { reason: 'read-state-db-reconcile' });
            }
          } else if (!res.success) {
            console.warn('[READ-STATE] Auto-mark-read failed:', res.error);
          }
        });
      }
    }
  };

  // Extracted: account-switch handler — called by AccountSwitcherMobile / AccountSwitcherDesktop
  const handleSwitchAccount = async (accountId: string) => {
    devLog(`[SWITCH] Requested account: ${accountId}`);
    resetAccountScopedState(); // immediately clears feed + summarize state
    setActiveEmail(accountId);
    setLoading(true);
    devLog(`[SWITCH] Target account handoff started: ${accountId}`);
    await runSync(accountId);
    // setLoading(false) handled by fetchEmails' finally (or pending switch path)
  };

  const handleAiLanguageChange = async (nextLanguage: AILanguage) => {
    if (!activeEmail || aiLanguageSaving) return;

    const accountId = activeEmail;
    const previousLanguage = aiLanguage;

    aiLanguageResolvedAccountRef.current = null;
    setAiLanguageResolvedAccountId(null);

    aiLanguageRef.current = nextLanguage;
    setAiLanguage(nextLanguage);
    setAiLanguageSaving(true);
    setAiLanguageError(null);
    setAiLanguageSavedAccountId(null);

    try {
      const response = await apiService.updatePreferences(accountId, nextLanguage as AILanguage);
      if (activeEmailRef.current !== accountId) return;

      const savedLanguage = response.ai_language ?? nextLanguage;
      aiLanguageRef.current = savedLanguage;
      setAiLanguage(savedLanguage as AILanguage);
      setAiLanguageSavedAccountId(accountId);

      aiLanguageResolvedAccountRef.current = accountId;
      setAiLanguageResolvedAccountId(accountId);

      // Re-fetch emails with new language preference so summaries reflect the saved language
      fetchEmails(accountId, { reason: 'language-change' });

      // Explicitly refresh templates for the new saved language.
      // A template refresh miss must not roll back a successfully saved language preference.
      try {
        await refreshTemplatesForContext(accountId, savedLanguage as AILanguage);
      } catch {
        // Best-effort reconciliation only. Keep the saved language authoritative.
      }
    } catch (error) {
      if (activeEmailRef.current !== accountId) return;

      aiLanguageRef.current = previousLanguage;
      setAiLanguage(previousLanguage);
      setAiLanguageSavedAccountId(null);
      setAiLanguageError(t('settings.ai_language_save_failed'));

      // Restore the previous account-language context as authoritative
      aiLanguageResolvedAccountRef.current = accountId;
      setAiLanguageResolvedAccountId(accountId);
    } finally {
      if (activeEmailRef.current === accountId) {
        setAiLanguageSaving(false);
      }
    }
  };

  const handleToneChange = (nextTone: DraftTone) => {
    setSelectedTone(nextTone);
  };

  const refreshTemplatesForContext = async (accountId: string, language: AILanguage) => {
    const rows = await apiService.listTemplates(accountId, language);
    if (activeEmailRef.current === accountId) {
      setTemplates(rows);
    }
    return rows;
  };

  const handleApplyTemplate = (template: EmailTemplate) => {
    setReplyBody(template.body || '');
    setSelectedTone(template.tone || 'professional');
    setPanelError(null);
    setTemplatesError(null);
  };

  const handleSaveTemplate = async (name: string): Promise<boolean> => {
    if (!activeEmail) return false;

    const trimmedName = name.trim();
    const trimmedBody = replyBody.trim();

    if (!trimmedName || !trimmedBody) return false;

    const accountId = activeEmail;
    const language = aiLanguage;

    setTemplateSaving(true);
    setTemplatesError(null);

    try {
      const createdTemplate = await apiService.createTemplate({
        account_id: accountId,
        name: trimmedName,
        tone: selectedTone,
        language,
        body: trimmedBody,
      });

      if (activeEmailRef.current === accountId) {
        setTemplates((prev) => {
          if (createdTemplate.id) {
            const withoutCreatedTemplate = prev.filter(
              (template) => template.id !== createdTemplate.id
            );
            return [createdTemplate, ...withoutCreatedTemplate];
          }

          return [createdTemplate, ...prev];
        });

        try {
          await refreshTemplatesForContext(accountId, language);
        } catch {
          // Best-effort reconciliation only. The template is already saved.
        }
      }

      return true;
    } catch (error) {
      if (activeEmailRef.current !== accountId) return false;

      setTemplatesError(t('compose.template_save_failed'));
      return false;
    } finally {
      if (activeEmailRef.current === accountId) {
        setTemplateSaving(false);
      }
    }
  };

  const handleDeleteTemplate = async (templateId: string) => {
    if (!activeEmail || !templateId) return;

    const accountId = activeEmail;
    const language = aiLanguage;

    setTemplateDeletingId(templateId);
    setTemplatesError(null);

    try {
      await apiService.deleteTemplate(templateId, accountId);

      if (activeEmailRef.current === accountId) {
        setTemplates((prev) => prev.filter((template) => template.id !== templateId));

        try {
          await refreshTemplatesForContext(accountId, language);
        } catch {
          // Best-effort reconciliation only. The template is already deleted.
        }
      }
    } catch (error) {
      if (activeEmailRef.current !== accountId) return;
      setTemplatesError(t('compose.template_delete_failed'));
    } finally {
      if (activeEmailRef.current === accountId) {
        setTemplateDeletingId(null);
      }
    }
  };

  // P5.4: attachment compose handlers — canonical state owner lives in App.tsx
  const handleAddAttachments = (files: File[]) => {
    if (attachmentsDisabled) {
      setReplyAttachmentError(t('compose.attachment_scope_required'));
      return;
    }

    // a. Normalize to ReplyAttachmentDraft
    const incoming: ReplyAttachmentDraft[] = files.map(file => ({
      file,
      filename: file.name,
      size: file.size,
      content_type: file.type || 'application/octet-stream',
      last_modified: file.lastModified,
    }));

    // b. Dedupe exact duplicates by (filename, size, last_modified) across full combined set
    //    Seeding `seen` from existing state also removes within-batch duplicates on the fly.
    const seen = new Set(
      replyAttachments.map(a => `${a.filename}|${a.size}|${a.last_modified}`)
    );
    const deduped = incoming.filter(inc => {
      const key = `${inc.filename}|${inc.size}|${inc.last_modified}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (deduped.length === 0) return;

    // c. Reject blocked extensions (case-insensitive)
    const hasBlocked = deduped.some(att => {
      const ext = att.filename.split('.').pop()?.toLowerCase() ?? '';
      return BLOCKED_ATTACHMENT_EXTENSIONS.has(ext);
    });
    if (hasBlocked) {
      setReplyAttachmentError(t('compose.attachment_blocked_type_error'));
      return;
    }

    // d–e. Sum total bytes; reject if > 25 MB
    const next = [...replyAttachments, ...deduped];
    const total = next.reduce((sum, a) => sum + a.size, 0);
    if (total > MAX_ATTACHMENT_BYTES) {
      setReplyAttachmentError(t('compose.attachment_size_error'));
      return;
    }

    // g. Commit and clear any prior error
    setReplyAttachments(next);
    setReplyAttachmentError(null);
  };

  const handleRemoveAttachment = (index: number) => {
    setReplyAttachments(prev => prev.filter((_, i) => i !== index));
    setReplyAttachmentError(null);
  };

  // Shared reply-compose entry path used by both keyboard shortcuts and modal UI
  const openReplyComposeForItem = (item: EmailViewModel) => {
    if (!item.thread_id) {
      openEmailDetail(item);
      setPanelError(t('compose.cannot_reply_missing_thread'));
      return;
    }
    openEmailDetail(item);
    setTemplatesError(null);
    setPanelError(null);
    setReplySubject(normalizeReplySubject(item.subject || ''));
    setReplyBody('');
    setReplyCC('');
    setSelectedTone('professional');
    setSendSuccess(false);
    setActiveModal('compose');
  };

  // Extracted: open compose in standalone modal; called by EmailDetailModal
  const handleOpenReply = () => {
    if (!selectedEmailDetail) {
      setPanelError(t('compose.cannot_reply_missing_thread'));
      return;
    }
    openReplyComposeForItem(selectedEmailDetail);
  };

  // Open AI assistant panel for the current email
  const handleOpenAssistant = () => {
    setActiveModal('assistant');
  };

  // Called by AssistantPanel when user clicks "Use this draft" — populates compose
  const handleUseDraft = (draft: string) => {
    if (!selectedEmailDetail?.thread_id) return;
    const subject = normalizeReplySubject(selectedEmailDetail.subject || '');
    setReplySubject(subject);
    setReplyBody(draft);
    setReplyCC('');
    setPanelError(null);
    setSendSuccess(false);
    setActiveModal('compose');
  };

  // Extracted: discard compose → return to detail view
  const handleDiscardCompose = () => {
    setActiveModal('detail');
    setReplyBody('');
    setReplySubject('');
    setReplyCC('');
    setPanelError(null);
    setReplyAttachments([]);
    setReplyAttachmentError(null);
  };

  // Extracted: mark thread read via Gmail API
  const handleMarkRead = async () => {
    if (!selectedEmailDetail?.thread_id || !activeEmail || readStatePending) return;
    setReadStatePending(true);
    setPanelError(null);
    try {
      const res = await apiService.setThreadReadState(selectedEmailDetail.thread_id, true, activeEmail);
      if (res.success === true && res.gmail_updated === true) {
        setIsDetailRead(true);
        setBriefings(prev => prev.map(b =>
          b.thread_id === selectedEmailDetail.thread_id ? { ...b, is_read: true } : b
        ));
        _updateThreadItemReadState(selectedEmailDetail.thread_id, true);
        if (res.db_updated === false) {
          console.warn('[READ-STATE] DB mirror unconfirmed on mark-read:', res.db_error);
          fetchEmails(activeEmail, { reason: 'read-state-db-reconcile' });
        }
      } else if (!res.success) {
        setPanelError(t('modal.mark_read_failed', { error: res.error || t('common.unknown_error') }));
      }
    } finally {
      setReadStatePending(false);
    }
  };

  // Extracted: mark thread unread via Gmail API
  const handleMarkUnread = async () => {
    if (!selectedEmailDetail?.thread_id || !activeEmail || readStatePending) return;
    setReadStatePending(true);
    setPanelError(null);
    try {
      const res = await apiService.setThreadReadState(selectedEmailDetail.thread_id, false, activeEmail);
      if (res.success === true && res.gmail_updated === true) {
        setIsDetailRead(false);
        setBriefings(prev => prev.map(b =>
          b.thread_id === selectedEmailDetail.thread_id ? { ...b, is_read: false } : b
        ));
        _updateThreadItemReadState(selectedEmailDetail.thread_id, false);
        if (res.db_updated === false) {
          console.warn('[READ-STATE] DB mirror unconfirmed on mark-unread:', res.db_error);
          fetchEmails(activeEmail, { reason: 'read-state-db-reconcile' });
        }
      } else if (!res.success) {
        setPanelError(t('modal.mark_unread_failed', { error: res.error || t('common.unknown_error') }));
      }
    } finally {
      setReadStatePending(false);
    }
  };

  // Extracted: queue AI summarization from modal; called by EmailDetailModal
  const handleSummarizeFromModal = async () => {
    if (!activeEmail || !selectedEmailDetail?.gmail_message_id) return;
    const id = selectedEmailDetail.gmail_message_id;
    setSummarizingIds(prev => new Set(prev).add(id));
    await apiService.summarizeEmail(id, activeEmail, aiLanguageRef.current);
    devLog('[MODAL] Summarization queued for', id);
    scheduleSummaryRefresh(activeEmail);
  };

  // Filter out self-generated security alerts (from app's own Gmail API access)
  const isSelfGeneratedAlert = (emailViewModel: EmailViewModel): boolean => {
    // Check if this is a security alert category
    if (emailViewModel.category !== 'Security') return false;

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
      emailViewModel.summary?.toLowerCase() || '',
      emailViewModel.subject?.toLowerCase() || '',
      emailViewModel.sender?.toLowerCase() || '',
      emailViewModel.action?.toLowerCase() || ''
    ].join(' ');

    // Check for Google security alert patterns related to our app
    const isGoogleSecurityAlert = (
      (emailViewModel.sender?.toLowerCase().includes('google') ||
        emailViewModel.sender?.toLowerCase().includes('no-reply@accounts.google.com')) &&
      emailViewModel.subject?.toLowerCase().includes('security alert')
    );

    // If it's a Google security alert, check if it mentions our app domains
    if (isGoogleSecurityAlert) {
      return appIdentifiers.some(id => textToCheck.includes(id));
    }

    // Otherwise, check if any of our identifiers appear in the content
    return appIdentifiers.some(id => textToCheck.includes(id));
  };

  // ── Gmail-style thread-collapsed inbox projection ───────────────────────
  // Groups raw emailViewModels by thread_id (fallback: gmail_message_id → subject).
  // emailViewModels is already sorted date DESC from fetchEmails, so the first
  // occurrence of each key IS the latest message — no secondary sort needed.
  // The original `emailViewModels` state is not mutated.
  const collapsedInbox: EmailViewModel[] = (() => {
    const seen = new Map<string, EmailViewModel>();
    const hasUnread = new Map<string, boolean>();
    for (const b of emailViewModels) {
      const key = b.thread_id || b.gmail_message_id || b.subject;
      if (!seen.has(key)) {
        seen.set(key, b);
        hasUnread.set(key, b.is_read === false);
      } else if (b.is_read === false) {
        // Propagate unread status even if a later (older) message is unread
        hasUnread.set(key, true);
      }
    }
    // Build representative rows with thread-level unread flag
    return Array.from(seen.entries()).map(([key, rep]) => ({
      ...rep,
      is_read: hasUnread.get(key) ? false : rep.is_read,
    }));
  })();
  // ─────────────────────────────────────────────────────────────────────────

  const visibleCollapsedInbox = collapsedInbox.filter((item) => !isSelfGeneratedAlert(item));

  const availableCategories: FilterCategory[] = [
    'All',
    ...CATEGORY_OPTIONS.filter(
      (category): category is Exclude<FilterCategory, 'All'> =>
        category !== 'All' && visibleCollapsedInbox.some((item) => item.category === category)
    ),
  ];

  const filteredBriefings = filterCategory === 'All'
    ? visibleCollapsedInbox
    : visibleCollapsedInbox.filter((item) => item.category === filterCategory);

  const totalPages = Math.ceil(filteredBriefings.length / ITEMS_PER_PAGE);
  const effectiveInboxPage = totalPages > 0 ? Math.min(currentPage, totalPages) : 1;
  const currentItems = filteredBriefings.slice((effectiveInboxPage - 1) * ITEMS_PER_PAGE, effectiveInboxPage * ITEMS_PER_PAGE);
  const hasFilteredBriefings = filteredBriefings.length > 0;

  // Search active when trimmed query is long enough to trigger FTS
  const isSearchActive = isSearchQueryActive(searchQuery) && !!activeEmail;
  // Unified display source: search results override normal paginated inbox when searching
  const displayItems = isSearchActive ? searchResults : currentItems;

  // Unread count: thread-level collapsed rows (not raw per-message count)
  const unreadCount = collapsedInbox.filter(b => b.is_read === false).length;

  // Convert a SentEmail to a minimal EmailViewModel for the shared detail panel
  const sentToEmailViewModel = (se: SentEmail): EmailViewModel => ({
    account: se.account_id,
    subject: se.subject || t('sent.no_subject'),
    sender: se.cc_addresses
      ? t('sent.you_to_recipient_with_cc', {
        recipient: se.to_address || t('sent.unknown_recipient'),
        ccLabel: t('sent.cc_label'),
        cc: se.cc_addresses,
      })
      : t('sent.you_to_recipient', { recipient: se.to_address || t('sent.unknown_recipient') }),
    date: formatDisplayDate(se.sent_at, se.sent_at),
    date_iso: se.sent_at ?? null,
    priority: 'Medium',
    category: 'General',
    should_alert: false,
    summary: se.body_preview || t('inbox.no_preview_available'),
    action: '',
    body: se.body_preview || '',
    sentMeta: {
      toAddress: se.to_address,
      ccAddresses: se.cc_addresses,
      sentAt: se.sent_at,
      bodyPreview: se.body_preview,
    },
    thread_id: se.thread_id || undefined,
    gmail_message_id: se.gmail_message_id || undefined,
    is_read: true,
  });

  // Show feed toolbar only when an account is active AND the feed has either
  // already loaded data or finished its initial load - prevents toolbar flashing
  // during the "Analyzing..." skeleton state on first account selection.
  const showFeedNavigation = Boolean(activeEmail) && (!loading || emailViewModels.length > 0);
  const showInboxEmptyState = activeTab === 'inbox' && !loading && !error && !hasFilteredBriefings && !isSearchActive;
  const showInboxPagination = activeTab === 'inbox' && !loading && !isSearchActive && hasFilteredBriefings && totalPages > 1;
  const showWakingOverlay = startupPhase === 'waking';
  const canShowSyncControl =
    startupPhase === 'ready' &&
    Boolean(activeEmail) &&
    connectedAccounts.length > 0;
  const useSearchHeaderLayout = Boolean(activeEmail);

  // Clamp inbox page when the filtered result set shrinks so the page indicator,
  // list slice, and empty state all stay aligned.
  useEffect(() => {
    const nextPage = totalPages === 0 ? 1 : Math.min(currentPage, totalPages);
    if (currentPage !== nextPage) {
      setCurrentPage(nextPage);
    }
  }, [currentPage, totalPages]);

  // Safety: close notification panel when no active account or no connected accounts
  useEffect(() => {
    if (!activeEmail || accounts.filter(a => a.connected).length === 0) {
      setIsNotificationCenterOpen(false);
    }
  }, [activeEmail, accounts]);

  // ── Keyboard navigation effects ────────────────────────────────────────────

  // H: Inbox keyboard navigation (j/k/ArrowDown/ArrowUp, o/Enter, r, /)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (shortcutsDisabledOnTouch) return;
      if (!activeEmail) return;
      if (activeTab !== 'inbox') return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isShortcutBlockedTarget(e.target)) return;

      switch (e.key) {
        case '/': {
          if (activeModal !== 'none') return;
          e.preventDefault();
          setKeyboardMode(true);
          setFocusedItemIndex(null);
          activeSearchInputRef()?.focus();
          break;
        }
        case 'j':
        case 'ArrowDown': {
          if (activeModal !== 'none') return;
          if (isSearchActive) return;
          if (displayItems.length === 0) return;
          e.preventDefault();
          setKeyboardMode(true);
          setFocusedItemIndex(prev =>
            prev === null ? 0 : Math.min(prev + 1, displayItems.length - 1)
          );
          break;
        }
        case 'k':
        case 'ArrowUp': {
          if (activeModal !== 'none') return;
          if (isSearchActive) return;
          if (displayItems.length === 0) return;
          e.preventDefault();
          setKeyboardMode(true);
          setFocusedItemIndex(prev => {
            if (prev === null) return null;
            if (prev === 0) return null;
            return prev - 1;
          });
          break;
        }
        case 'o':
        case 'Enter': {
          if (activeModal !== 'none') return;
          if (isSearchActive) return;
          if (!keyboardMode) return;
          if (focusedItemIndex === null) return;
          if (!displayItems[focusedItemIndex]) return;
          e.preventDefault();
          openEmailDetail(displayItems[focusedItemIndex]);
          break;
        }
        case 'r': {
          if (activeModal !== 'none') return;
          if (isSearchActive) return;
          if (!keyboardMode) return;
          if (focusedItemIndex === null) return;
          if (!displayItems[focusedItemIndex]) return;
          e.preventDefault();
          openReplyComposeForItem(displayItems[focusedItemIndex]);
          break;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortcutsDisabledOnTouch, activeEmail, activeTab, activeModal, isSearchActive, displayItems, focusedItemIndex]);

  // I: Scroll focused card into view (virtual selection — no DOM focus transfer)
  useEffect(() => {
    if (focusedItemIndex === null) return;
    if (shortcutsDisabledOnTouch) return;
    if (!displayItems[focusedItemIndex]) return;

    const domId = getKeyboardCardDomId(displayItems[focusedItemIndex], focusedItemIndex);
    const el = document.getElementById(domId);
    if (!el) return;

    requestAnimationFrame(() => {
      el.scrollIntoView({ block: 'nearest' });
    });
  }, [focusedItemIndex, shortcutsDisabledOnTouch, displayItems]);

  // J: Reset focusedItemIndex on modal open, account/tab/search/page/category changes
  useEffect(() => {
    if (activeModal !== 'none') setFocusedItemIndex(null);
  }, [activeModal]);

  useEffect(() => {
    setFocusedItemIndex(null);
  }, [activeEmail]);

  useEffect(() => {
    setFocusedItemIndex(null);
  }, [activeTab]);

  useEffect(() => {
    if (isSearchActive) setFocusedItemIndex(null);
  }, [isSearchActive]);

  useEffect(() => {
    setFocusedItemIndex(null);
  }, [currentPage]);

  useEffect(() => {
    setFocusedItemIndex(null);
  }, [filterCategory]);

  // K: Clamp focusedItemIndex when displayItems shrinks
  useEffect(() => {
    setFocusedItemIndex(prev => {
      if (prev === null) return null;
      if (displayItems.length === 0) return null;
      return Math.min(prev, displayItems.length - 1);
    });
  }, [displayItems.length]);

  // ─────────────────────────────────────────────────────────────────────────

  // ── Notification Center derived values ─────────────────────────────────────

  const notificationItems = getNotificationItemsFromEmailViewModels(emailViewModels).filter(item => {
    const id = getNotificationIdentity(item);
    return id !== null && !_notificationDismissedIds.has(id);
  });

  const visibleNotificationIds = new Set(
    notificationItems
      .map(item => getNotificationIdentity(item))
      .filter((id): id is string => id !== null)
  );

  const unseenNotificationCount = notificationItems.filter(item => {
    const id = getNotificationIdentity(item);
    return id !== null && _notificationUnseenIds.has(id);
  }).length;

  const notificationsSupported = typeof window !== 'undefined' && 'Notification' in window;

  // ── Urgency snapshot helpers ───────────────────────────────────────────────

  const buildNotificationUrgencySnapshot = (items: EmailViewModel[]): Record<string, 'low' | 'medium' | 'high'> => {
    const snapshot: Record<string, 'low' | 'medium' | 'high'> = {};
    items.forEach(item => {
      const id = getNotificationIdentity(item);
      if (id) snapshot[id] = getNotificationUrgency(item);
    });
    return snapshot;
  };

  const getNotificationDeltaIds = (
    items: EmailViewModel[],
    previousSnapshot: Record<string, 'low' | 'medium' | 'high'>
  ): Set<string> => {
    const delta = new Set<string>();
    items.forEach(item => {
      const id = getNotificationIdentity(item);
      if (!id) return;
      if (!(id in previousSnapshot)) return;
      const prevWeight = getNotificationUrgencyWeight(previousSnapshot[id]);
      const currWeight = getNotificationUrgencyWeight(getNotificationUrgency(item));
      if (currWeight > prevWeight) delta.add(id);
    });
    return delta;
  };

  const markNotificationIdsSeen = (ids: Set<string>) => {
    setNotificationSeenIds(prev => {
      const next = new Set(prev);
      ids.forEach(id => next.add(id));
      return next;
    });
    setNotificationUnseenIds(prev => {
      const next = new Set(prev);
      ids.forEach(id => next.delete(id));
      return next;
    });
  };

  const clearNotificationDeltaForId = (id: string) => {
    setNotificationUrgencyDeltaIds(prev => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const closeNotificationCenter = () => setIsNotificationCenterOpen(false);

  const toggleNotificationCenter = () => {
    if (isNotificationCenterOpen) {
      setIsNotificationCenterOpen(false);
      return;
    }
    // Compare against previous snapshot BEFORE updating it
    const deltaIds = getNotificationDeltaIds(notificationItems, urgencySnapshotRef.current);
    setNotificationUrgencyDeltaIds(deltaIds);
    // Replace snapshot AFTER computing delta
    urgencySnapshotRef.current = buildNotificationUrgencySnapshot(notificationItems);
    // Mark visible items as seen
    markNotificationIdsSeen(visibleNotificationIds);
    setIsNotificationCenterOpen(true);
  };

  // ── Notification item callbacks ────────────────────────────────────────────

  const isNotificationItemUnseen = (item: EmailViewModel): boolean => {
    const id = getNotificationIdentity(item);
    return id !== null && _notificationUnseenIds.has(id);
  };

  const hasNotificationItemUrgencyDelta = (item: EmailViewModel): boolean => {
    const id = getNotificationIdentity(item);
    return id !== null && notificationUrgencyDeltaIds.has(id);
  };

  const canMarkNotificationItemAsRead = (item: EmailViewModel): boolean => {
    if (item.is_read !== false) return false;
    if (!item.thread_id) return false;
    if (!activeEmail) return false;
    const acct = accounts.find(a => a.account_id === activeEmail);
    return Boolean(acct?.modify_scope);
  };

  const handleOpenNotificationItem = (item: EmailViewModel) => {
    const id = getNotificationIdentity(item);
    if (id) {
      clearNotificationDeltaForId(id);
      markNotificationIdsSeen(new Set([id]));
    }
    closeNotificationCenter();
    openEmailDetail(item);
  };

  const handleDismissNotificationItem = (item: EmailViewModel) => {
    const id = getNotificationIdentity(item);
    if (!id) return;
    setNotificationDismissedIds(prev => new Set(prev).add(id));
    markNotificationIdsSeen(new Set([id]));
    clearNotificationDeltaForId(id);
  };

  const handleToggleBrowserAlertsFromCenter = () => {
    if (notificationsEnabled) {
      setNotificationsEnabled(false);
    } else {
      requestNotificationPermission();
    }
  };

  const handleMarkNotificationItemAsRead = async (item: EmailViewModel) => {
    if (!canMarkNotificationItemAsRead(item)) return;
    if (!item.thread_id || !activeEmail) return;
    const capturedAccountId = activeEmail;
    try {
      const res = await apiService.setThreadReadState(item.thread_id, true, capturedAccountId);
      if (res.success === true && res.gmail_updated === true) {
        setBriefings(prev => prev.map(b =>
          b.thread_id === item.thread_id ? { ...b, is_read: true } : b
        ));
        _updateThreadItemReadState(item.thread_id, true);
        if (selectedEmailDetail?.thread_id === item.thread_id) {
          setIsDetailRead(true);
        }
        const id = getNotificationIdentity(item);
        if (id) markNotificationIdsSeen(new Set([id]));
        if (res.db_updated === false) {
          console.warn('[READ-STATE] DB mirror unconfirmed on notification mark-as-read:', res.db_error);
          fetchEmails(capturedAccountId, { reason: 'read-state-db-reconcile' });
        }
      }
    } catch {
      // Non-destructive failure — keep notification visible
    }
  };

  if (startupPhase !== 'ready') {
    return (
      <div className="min-h-screen bg-brand-bg">
        <AnimatePresence>
          {showWakingOverlay && <WakingUp />}
        </AnimatePresence>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-bg text-slate-300 font-sans selection:bg-primary-500/25 overflow-x-hidden">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary-500/[0.03] blur-[120px] rounded-full animate-pulse" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-primary-400/[0.03] blur-[120px] rounded-full animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-brand-bg/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4">
          {/* Primary row — left: brand | center: desktop search | right: desktop controls */}
          <div className={useSearchHeaderLayout ? "flex flex-wrap items-center gap-2 sm:gap-3" : "flex flex-wrap items-center justify-between gap-3"}>
            {/* LEFT: brand/status + mobile GlobeButton */}
            <div className={useSearchHeaderLayout ? "flex items-center gap-3 flex-shrink-0" : "flex items-center justify-between gap-3 w-full sm:w-auto"}>
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-10 h-10 bg-gradient-to-br from-primary-600 to-primary-500 rounded-xl flex items-center justify-center shadow-lg shadow-primary-600/20">
                  <Brain className="text-white" size={20} />
                </div>
                <div className="min-w-0">
                  <h1 className="text-white font-bold tracking-tight text-lg truncate">{brandName}</h1>
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${error ? 'bg-rose-500' : 'bg-emerald-500'}`} />
                    <p className={`text-[10px] uppercase tracking-[0.2em] font-bold ${error ? 'text-rose-500' : 'text-slate-500'}`}>
                      {error ? t('nav.sentinel_offline') : t('nav.sentinel_active')}
                    </p>
                  </div>
                </div>
              </div>
              <div className="sm:hidden flex items-center gap-2 flex-shrink-0">
                <GlobeButton />
                {connectedAccounts.length > 0 && !isDesktopViewport && (
                  <NotificationCenter
                    items={notificationItems}
                    isOpen={isNotificationCenterOpen}
                    unseenCount={unseenNotificationCount}
                    notificationsEnabled={notificationsEnabled}
                    notificationsSupported={notificationsSupported}
                    getItemId={(item) => getNotificationIdentity(item)!}
                    isItemUnseen={isNotificationItemUnseen}
                    hasUrgencyDelta={hasNotificationItemUrgencyDelta}
                    canMarkAsRead={canMarkNotificationItemAsRead}
                    onToggleOpen={toggleNotificationCenter}
                    onClose={closeNotificationCenter}
                    onOpenItem={handleOpenNotificationItem}
                    onDismissItem={handleDismissNotificationItem}
                    onMarkAsRead={handleMarkNotificationItemAsRead}
                    onToggleBrowserAlerts={handleToggleBrowserAlertsFromCenter}
                    buttonId="notification-center-button-mobile"
                    panelId="notification-center-panel-mobile"
                  />
                )}
              </div>
            </div>

            {/* CENTER: desktop search lane (visible only when an account is active) */}
            {activeEmail && (
              <div className="hidden sm:flex basis-full lg:basis-auto lg:flex-1 justify-center px-0 lg:px-2 order-3 lg:order-none">
                <div className="flex items-center gap-2 w-full max-w-xl lg:max-w-sm">
                  <div className="relative flex-1">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" aria-hidden="true" />
                    <input
                      ref={desktopSearchInputRef}
                      id="email-search-desktop"
                      name="email_search_desktop"
                      type="text"
                      value={searchQuery}
                      onChange={(e) => { setSearchQuery(e.target.value); if (shouldResetAttachmentFilterOnInput(e.target.value)) setSearchHasAttachments(false); }}
                      aria-label={t('search.aria_label')}
                      placeholder={t('search.placeholder')}
                      className="w-full h-9 pl-8 pr-8 rounded-xl bg-white/[0.04] border border-white/[0.08] text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-primary-500/50 focus:border-primary-500/30 transition-all"
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={resetSearch}
                        aria-label={t('search.clear')}
                        title={t('search.clear')}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                      >
                        <X size={13} />
                      </button>
                    )}
                  </div>
                  <AttachmentSearchToggle
                    isActive={searchHasAttachments}
                    label={t('search.filter_attachments')}
                    isRTL={isCategoryPillBarRTL}
                    disabled={shouldDisableAttachmentToggle(searchQuery)}
                    onToggle={() => setSearchHasAttachments(v => !v)}
                  />
                </div>
              </div>
            )}

            {/* RIGHT: desktop controls */}
            <div className={useSearchHeaderLayout ? "hidden sm:flex items-center justify-end gap-3 flex-shrink-0 flex-wrap min-w-0 ml-auto" : "hidden sm:flex items-center justify-end gap-3 flex-wrap min-w-0"}>
              <GlobeButton />

              {/* Desktop notification center — bell-based, replaces legacy Shield/toggle rail */}
              {connectedAccounts.length > 0 && isDesktopViewport && (
                <NotificationCenter
                  items={notificationItems}
                  isOpen={isNotificationCenterOpen}
                  unseenCount={unseenNotificationCount}
                  notificationsEnabled={notificationsEnabled}
                  notificationsSupported={notificationsSupported}
                  getItemId={(item) => getNotificationIdentity(item)!}
                  isItemUnseen={isNotificationItemUnseen}
                  hasUrgencyDelta={hasNotificationItemUrgencyDelta}
                  canMarkAsRead={canMarkNotificationItemAsRead}
                  onToggleOpen={toggleNotificationCenter}
                  onClose={closeNotificationCenter}
                  onOpenItem={handleOpenNotificationItem}
                  onDismissItem={handleDismissNotificationItem}
                  onMarkAsRead={handleMarkNotificationItemAsRead}
                  onToggleBrowserAlerts={handleToggleBrowserAlertsFromCenter}
                  buttonId="notification-center-button-desktop"
                  panelId="notification-center-panel-desktop"
                />
              )}

              {/* Desktop session/action rail — account context and immediate actions only */}
              <div className="flex items-center gap-3 min-w-0">
                <div className="relative">
                  {connectedAccounts.length === 0 ? (
                    <a
                      href={apiService.getGoogleAuthUrl()}
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary-600 hover:bg-primary-500 border border-primary-500/50 text-white text-sm font-bold transition-all shadow-lg shadow-primary-600/20 active:scale-95"
                    >
                      <Mail size={16} />
                      <span>{t('nav.connect_account')}</span>
                    </a>
                  ) : (
                    <AccountSwitcherDesktop
                      connectedAccounts={connectedAccounts}
                      activeEmail={activeEmail}
                      offlineAccounts={offlineAccounts}
                      maxAccounts={MAX_CONNECTED_ACCOUNTS}
                      authUrl={apiService.getGoogleAuthUrl()}
                      onSwitchAccount={handleSwitchAccount}
                      onRequestDisconnect={(id) => setConfirmDisconnect(id)}
                      aiLanguage={aiLanguage}
                      aiLanguageLoading={aiLanguageLoading}
                      aiLanguageSaving={aiLanguageSaving}
                      aiLanguageError={aiLanguageError}
                      aiLanguageSavedAccountId={aiLanguageSavedAccountId}
                      languageOptions={resolvedLanguageOptions}
                      onAiLanguageChange={handleAiLanguageChange}
                      languageAriaIdPrefix="desktop"
                    />
                  )}
                </div>

                {canShowSyncControl && (
                  <button
                    onClick={async () => {
                      if (!activeEmail || syncingRef.current) return;
                      devLog('[REFRESH] Manual refresh for account:', activeEmail);
                      setLoading(true);
                      await runSync(activeEmail);
                      // setLoading(false) handled by fetchEmails' finally
                    }}
                    disabled={loading || syncing}
                    className="group flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary-600 hover:bg-primary-500 disabled:opacity-50 text-white text-sm font-bold transition-all shadow-xl shadow-primary-600/20 active:scale-95"
                  >
                    <RefreshCw size={18} className={`${syncing ? 'animate-spin' : 'group-hover:rotate-180'} transition-transform duration-700`} />
                    {syncing ? t('common.syncing') : t('common.sync')}
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Mobile-only search row — below primary row, above session row */}
          {activeEmail && (
            <div className="sm:hidden mt-2">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" aria-hidden="true" />
                  <input
                    ref={mobileSearchInputRef}
                    id="email-search-mobile"
                    name="email_search_mobile"
                    type="text"
                    value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); if (shouldResetAttachmentFilterOnInput(e.target.value)) setSearchHasAttachments(false); }}
                    aria-label={t('search.aria_label')}
                    placeholder={t('search.placeholder')}
                    className="w-full h-10 pl-8 pr-8 rounded-xl bg-white/[0.04] border border-white/[0.08] text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-primary-500/50 focus:border-primary-500/30 transition-all"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={resetSearch}
                      aria-label={t('search.clear')}
                      title={t('search.clear')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>
                <AttachmentSearchToggle
                  isActive={searchHasAttachments}
                  label={t('search.filter_attachments')}
                  isRTL={isCategoryPillBarRTL}
                  disabled={shouldDisableAttachmentToggle(searchQuery)}
                  onToggle={() => setSearchHasAttachments(v => !v)}
                />
              </div>
            </div>
          )}

          {/* Mobile-only session/action row — connected accounts only */}
          {connectedAccounts.length > 0 && (
            <div className="sm:hidden flex items-center gap-2 mt-3 pt-2.5 border-t border-white/[0.05]">
              <AccountSwitcherMobile
                connectedAccounts={connectedAccounts}
                activeEmail={activeEmail}
                offlineAccounts={offlineAccounts}
                maxAccounts={MAX_CONNECTED_ACCOUNTS}
                authUrl={apiService.getGoogleAuthUrl()}
                onSwitchAccount={handleSwitchAccount}
                onRequestDisconnect={(id) => setConfirmDisconnect(id)}
                aiLanguage={aiLanguage}
                aiLanguageLoading={aiLanguageLoading}
                aiLanguageSaving={aiLanguageSaving}
                aiLanguageError={aiLanguageError}
                aiLanguageSavedAccountId={aiLanguageSavedAccountId}
                languageOptions={resolvedLanguageOptions}
                onAiLanguageChange={handleAiLanguageChange}
                languageAriaIdPrefix="mobile"
              />
              {canShowSyncControl && (
                <button
                  onClick={async () => {
                    if (!activeEmail || syncingRef.current) return;
                    setLoading(true);
                    await runSync(activeEmail);
                  }}
                  disabled={loading || syncing}
                  aria-label={syncing ? t('common.syncing') : t('common.sync')}
                  title={syncing ? t('common.syncing') : t('common.sync')}
                  className="flex-shrink-0 w-11 h-11 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl bg-primary-600 hover:bg-primary-500 disabled:opacity-50 text-white transition-all shadow-lg shadow-primary-600/20 active:scale-95"
                >
                  <RefreshCw size={16} className={`${syncing ? 'animate-spin' : ''} transition-transform duration-700`} />
                </button>
              )}
            </div>
          )}
        </div>
      </header>

      <AnimatePresence>
        {showSentinelToast && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-10 left-1/2 z-[100] px-6 py-3 rounded-2xl bg-primary-600 text-white font-black text-xs uppercase tracking-[0.2em] shadow-2xl shadow-primary-500/40 border border-white/10 flex items-center gap-3"
          >
            <Shield size={16} />
            {t('nav.urgency_alerts_enabled')}
          </motion.div>
        )}
      </AnimatePresence>

      {/* App-level send success toast — survives panel close, z-[300] above everything */}
      <AnimatePresence>
        {sendSuccess && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-10 left-1/2 z-[300] px-6 py-3 rounded-2xl bg-emerald-600 text-white font-black text-xs shadow-2xl shadow-emerald-500/40 border border-white/10 flex items-center gap-3"
          >
            <Mail size={16} />
            <span>
              {sentToAddress ? t('common.sent_to', { address: sentToAddress }) : t('common.email_sent_successfully')}
              {sentCCAddress && <span className="font-normal opacity-70"> - {t('common.cc_prefix')} {sentCCAddress}</span>}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Startup ready toast — only appears after waking flow succeeds */}
      <AnimatePresence>
        {showReadyToast && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-10 left-1/2 z-[320] px-6 py-3 rounded-2xl bg-primary-600 text-white font-black text-xs uppercase tracking-[0.2em] shadow-2xl shadow-primary-500/40 border border-white/10 flex items-center gap-3"
          >
            <Brain size={16} />
            {t('common.ready')}
          </motion.div>
        )}
      </AnimatePresence>

      <div className={connectedAccounts.length > 0 ? (activeEmail ? 'pt-[11.5rem] sm:pt-24' : 'pt-32 sm:pt-24') : 'pt-24'}>
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
                  <h4 className="text-white font-bold text-base mb-2">⚠️ {t('inbox.legacy_accounts_detected')}</h4>
                  <p className="text-amber-200 text-sm mb-4">
                    {t('inbox.legacy_accounts_helper')}
                  </p>
                  <div className="flex gap-3">
                    <a
                      href={apiService.getGoogleAuthUrl()}
                      className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-sm font-bold transition-all"
                    >
                      {t('inbox.reconnect_first_account')}
                    </a>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <main className={`relative max-w-7xl mx-auto px-6 pb-16 ${connectedAccounts.length === 0 ? 'pt-16' : 'pt-8 sm:pt-10'}`}>
          {connectedAccounts.length === 0 && (
            <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-8">
              <div className="text-center lg:text-left">
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary-500/10 border border-primary-500/20 text-primary-400 text-xs font-black uppercase tracking-[0.2em] mb-6"
                >
                  <Sparkles size={14} />
                  <span>{t('inbox.hardened_shell_version')}</span>
                </motion.div>
                <h2 className="text-5xl lg:text-6xl font-black text-white tracking-tighter mb-4">
                  {subtitle}<span className="text-primary-500">.</span>
                </h2>
                <p className="text-slate-400 text-lg max-w-xl font-medium leading-relaxed">
                  {t('inbox.hero_description')}
                </p>
              </div>

            </div>
          )}

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className={`mb-12 p-6 rounded-3xl flex items-center gap-4 shadow-2xl ${consecutiveFailures >= 5
                  ? 'bg-rose-500/10 border border-rose-500/20 text-rose-400 shadow-rose-900/10'
                  : 'bg-primary-500/10 border border-primary-500/20 text-primary-400 shadow-primary-900/10'
                  }`}
              >
                <AlertCircle size={22} className="flex-shrink-0" />
                <div className="flex-grow">
                  <h4 className="font-bold text-base">
                    {consecutiveFailures >= 5 ? t('inbox.transmission_alert') : t('inbox.connecting')}
                  </h4>
                  <p className="text-sm opacity-90">{error}</p>
                </div>
                {syncing && (
                  <RefreshCw size={18} className="animate-spin opacity-50" />
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Feed toolbar — tabs + category chips, only when an account is active */}
          {showFeedNavigation && (
            <div className="flex items-center justify-between gap-3 mb-6 max-w-[720px] mx-auto flex-wrap">
              {/* Left: Inbox / Sent tabs */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveTab('inbox')}
                  className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${activeTab === 'inbox' ? 'bg-primary-600 text-white shadow-lg shadow-primary-600/20' : 'text-slate-500 hover:text-slate-300 bg-white/[0.02] border border-white/5'}`}
                >
                  <Mail size={13} />
                  {t('nav.inbox_tab')}
                  {unreadCount > 0 && (
                    <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-rose-500 text-white text-[9px] font-black leading-none">
                      {unreadCount}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => { setActiveTab('sent'); resetSearch(); }}
                  className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${activeTab === 'sent' ? 'bg-primary-600 text-white shadow-lg shadow-primary-600/20' : 'text-slate-500 hover:text-slate-300 bg-white/[0.02] border border-white/5'}`}
                >
                  <Send size={13} />
                  {t('nav.sent_tab')}
                </button>
              </div>

              {/* Right: category pill bar — inbox only, hidden while search is active */}
              {activeTab === 'inbox' && !isSearchActive && (
                <div className="w-full sm:w-auto sm:max-w-[50%]">
                  <CategoryPillBar
                    categories={availableCategories}
                    activeCategoryCode={filterCategory}
                    onSelect={(code) => {
                      setFilterCategory(code as FilterCategory);
                      setCurrentPage(1);
                    }}
                    getLabel={getCategoryDisplayLabel}
                    isRTL={isCategoryPillBarRTL}
                    ariaLabel={t('inbox.category_filter_aria_label')}
                  />
                </div>
              )}
            </div>
          )}

          {/* Sent view */}
          {activeTab === 'sent' && (
            <div className="flex flex-col gap-4 mb-12 max-w-[720px] mx-auto">
              <SentList
                emails={currentSentItems}
                loading={loadingSent}
                onSelect={(se: SentEmail) => openEmailDetail(sentToEmailViewModel(se), false, true)}
              />
              {!loadingSent && sentTotalPages > 1 && (
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3 sm:gap-8 mt-4 w-full max-w-sm sm:max-w-none mx-auto">
                  <button
                    onClick={() => setSentCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={sentCurrentPage === 1}
                    className="w-full sm:w-auto px-4 sm:px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest text-center"
                  >
                    {t('common.previous')}
                  </button>
                  <div className="flex flex-col items-center min-w-0 sm:min-w-[120px]">
                    <span className="text-[10px] font-black text-primary-500 uppercase tracking-[0.2em] mb-1">{t('common.navigation')}</span>
                    <span className="text-white font-black text-sm">{getPageStatusLabel(sentCurrentPage, sentTotalPages)}</span>
                  </div>
                  <button
                    onClick={() => setSentCurrentPage(prev => Math.min(sentTotalPages, prev + 1))}
                    disabled={sentCurrentPage === sentTotalPages}
                    className="w-full sm:w-auto px-4 sm:px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest text-center"
                  >
                    {t('common.next')}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Inbox view */}
          {activeTab === 'inbox' && (
            <div
              className="flex flex-col gap-4 mb-12 max-w-[720px] mx-auto"
              role={!(isSearchActive && searchLoading) && !(loading && !isSearchActive) && displayItems.length > 0 ? 'list' : undefined}
              aria-label={!(isSearchActive && searchLoading) && !(loading && !isSearchActive) && displayItems.length > 0 ? t('nav.inbox_tab') : undefined}
            >
              <AnimatePresence mode="popLayout">
                {/* Search loading skeletons */}
                {isSearchActive && searchLoading && [...Array(3)].map((_, i) => (
                  <motion.div
                    key={`search-skeleton-${i}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.3, delay: i * 0.05 }}
                    className="skeleton-row rounded-2xl bg-white/[0.02] border border-white/5"
                  >
                    <div className="skeleton-bar h-4" style={{ width: '60%' }} />
                    <div className="skeleton-bar h-4" style={{ width: '85%' }} />
                    <div className="skeleton-bar h-3" style={{ width: '30%' }} />
                  </motion.div>
                ))}
                {/* Search error state */}
                {isSearchActive && !searchLoading && searchError && (
                  <motion.div
                    key="search-error"
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-6 rounded-3xl flex items-center gap-4 bg-rose-500/10 border border-rose-500/20 text-rose-400"
                  >
                    <AlertCircle size={22} className="flex-shrink-0" />
                    <div>
                      <h4 className="font-bold text-base text-white">{t('search.error_title')}</h4>
                      <p className="text-sm opacity-90">{t('search.error_body')}</p>
                    </div>
                  </motion.div>
                )}
                {/* Search no-results state */}
                {isSearchActive && !searchLoading && !searchError && searchResults.length === 0 && (
                  <motion.div
                    key="search-empty"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="w-full py-24 flex flex-col items-center gap-4 text-center"
                  >
                    <div className="w-16 h-16 rounded-full bg-white/[0.03] flex items-center justify-center border border-white/5">
                      <Search size={28} className="text-primary-500/20" />
                    </div>
                    <div>
                      <h3 className="text-xl font-black text-white mb-1">{t('search.no_results_title')}</h3>
                      <p className="text-slate-500 text-sm max-w-xs font-medium">{t(resolveSearchEmptyBodyKey(searchHasAttachments))}</p>
                    </div>
                  </motion.div>
                )}
                {/* Normal inbox loading skeletons (only when not in search mode) */}
                {!isSearchActive && loading && [...Array(6)].map((_, i) => (
                  <motion.div
                    key={`skeleton-${i}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.3, delay: i * 0.05 }}
                    className="skeleton-row rounded-2xl bg-white/[0.02] border border-white/5"
                  >
                    <div className="skeleton-bar h-4" style={{ width: '60%' }} />
                    <div className="skeleton-bar h-4" style={{ width: '85%' }} />
                    <div className="skeleton-bar h-3" style={{ width: '30%' }} />
                  </motion.div>
                ))}
                {/* Cards: search results OR normal inbox items */}
                {!(isSearchActive && searchLoading) && !(loading && !isSearchActive) && displayItems.length > 0 ? (
                  displayItems.map((item, index) => {
                    const cardId = `${item.gmail_message_id || item.subject}-${index}`;
                    const urgency = item.ai_summary_json?.urgency || 'medium';

                    const getPriorityBadgeStyle = () => {
                      switch (urgency) {
                        case 'high': return 'bg-[#FF3B5C] text-white border-[#FF3B5C] font-bold';
                        case 'low': return 'bg-[#3D4A5C] text-[#94A3B8] border-[#3D4A5C]';
                        default: return 'bg-[#FFB800] text-[#1a1a1a] border-[#FFB800] font-bold';
                      }
                    };

                    const domId = getKeyboardCardDomId(item, index);

                    return (
                      <motion.div
                        key={cardId}
                        id={domId}
                        role="listitem"
                        layout
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3, delay: index * 0.03 }}
                        className={`group relative flex flex-col p-6 rounded-2xl border hover:bg-white/[0.04] hover:border-white/10 transition-all duration-300 shadow-xl hover:shadow-primary-500/5 focus:outline-none ${focusedItemIndex === index && keyboardMode ? 'ring-2 ring-primary-500/50 ring-offset-1 ring-offset-slate-900' : ''} ${item.is_read === false ? 'bg-white/[0.035] border-primary-500/[0.15]' : 'bg-white/[0.02] border-white/5'}`}
                      >
                        {/* Header row: badges + AI indicator */}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getPriorityBadgeStyle()}`}>
                              {getUrgencyDisplayLabel(urgency)}
                            </span>
                            <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(item.category)}`}>
                              {getCategoryDisplayLabel(item.category)}
                            </span>
                            {item.thread_id && (item.thread_count ?? 1) > 1 && (
                              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border border-primary-500/30 bg-primary-500/10 text-primary-300">
                                {t('inbox.thread_message_count', { count: item.thread_count })}
                              </span>
                            )}
                          </div>
                          {item.ai_summary_text && (
                            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-primary-500/15 border border-primary-400/30">
                              <Sparkles size={10} className={`text-primary-300 ${summarizingIds.has(item.gmail_message_id || '') ? 'animate-pulse' : ''}`} />
                              <span className="text-[8px] font-black text-primary-300 uppercase tracking-wider">{t('common.ai_badge')}</span>
                            </div>
                          )}
                          {!item.ai_summary_text && item.gmail_message_id && summarizingIds.has(item.gmail_message_id) && (
                            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-primary-500/10 border border-primary-400/20">
                              <Sparkles size={10} className="text-primary-400 animate-pulse" />
                              <span className="text-[8px] font-black text-primary-400 uppercase tracking-wider">{t('common.queued_badge')}</span>
                            </div>
                          )}
                        </div>

                        {/* Executive Conversation Spine */}
                        {(() => {
                          const spine = deriveSpineSignals(
                            item, activeEmail ?? '');
                          return spine.hasAnySignal
                            ? <ThreadSpine result={spine} />
                            : null;
                        })()}

                        {/* Subject and sender */}
                        <div className="mb-3">
                          <div className="flex items-start gap-2 mb-1">
                            {item.is_read === false
                              ? <Mail size={14} className="mt-1 text-primary-400 flex-shrink-0" aria-label={t('common.unread')} />
                              : <MailOpen size={14} className="mt-1 text-slate-600 flex-shrink-0" aria-label={t('common.read')} />
                            }
                            <h3 className={`text-lg tracking-tight leading-tight group-hover:text-primary-400 transition-colors duration-300 ${item.is_read === false ? 'font-black text-white' : 'font-bold text-slate-200'}`}>
                              {item.subject}
                              {item.has_attachments && (
                                <span role="img" aria-label={t('inbox.has_attachments')} title={t('inbox.has_attachments')} className="inline-block">
                                  <Paperclip size={13} className="inline-block ml-1.5 text-slate-400 align-[-1px]" aria-hidden="true" />
                                </span>
                              )}
                            </h3>
                          </div>
                          <div className="flex items-center justify-between text-xs text-slate-500">
                            <span className={`truncate mr-2 ${item.is_read === false ? 'font-bold text-slate-300' : 'font-semibold'}`}>{item.sender.split('<')[0].trim()}</span>
                            <div className="flex items-center gap-1 shrink-0">
                              <Clock size={11} className="text-primary-400/60" />
                              <span className="text-[10px] font-medium">{formatDisplayDate(item.date_iso, item.date)}</span>
                            </div>
                          </div>
                        </div>

                        {/* Summary - 3-line clamp with fade, 14px body */}
                        <div className="mb-3 relative">
                          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                            <p className="text-sm leading-[1.6] text-slate-200 line-clamp-3">
                              {item.summary}
                            </p>
                            <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-brand-bg/80 to-transparent rounded-b-xl pointer-events-none" />
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
                                  onClick={e => { e.stopPropagation(); openEmailDetail(item, true); }}
                                  className="text-[10px] font-bold text-primary-400 hover:text-primary-300 mt-1.5 transition-colors"
                                >
                                  {t('inbox.view_more_actions', { count: item.ai_summary_json.action_items.length - 3 })} &rarr;
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
                              <span className="text-[9px] font-bold text-primary-400 uppercase flex items-center gap-1">
                                <Sparkles size={11} className="animate-pulse" />
                                {t('inbox.queued')}
                              </span>
                            )}
                            {/* Refresh AI Summary for cards that already have summaries */}
                            {item.ai_summary_text && item.gmail_message_id && (
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (!activeEmail) return;
                                  setSummarizingIds(prev => new Set(prev).add(item.gmail_message_id!));
                                  await apiService.summarizeEmail(item.gmail_message_id!, activeEmail, aiLanguageRef.current);
                                  // Use the same coalesced bounded refresh — no duplicate timers
                                  scheduleSummaryRefresh(activeEmail);
                                }}
                                disabled={summarizingIds.has(item.gmail_message_id!)}
                                aria-busy={summarizingIds.has(item.gmail_message_id!)}
                                title={summarizingIds.has(item.gmail_message_id!) ? t('common.summary_request_queued') : t('common.refresh_ai_summary')}
                                className="text-[9px] font-bold text-slate-500 hover:text-primary-400 uppercase flex items-center gap-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                {summarizingIds.has(item.gmail_message_id!) ? (
                                  <RefreshCw size={11} className="animate-spin" />
                                ) : (
                                  <Sparkles size={11} />
                                )}
                                {summarizingIds.has(item.gmail_message_id!) ? t('inbox.queued') : t('common.refresh_ai_summary')}
                              </button>
                            )}
                            <button
                              onClick={e => { e.stopPropagation(); openEmailDetail(item); }}
                              className="text-[9px] font-bold text-slate-500 hover:text-slate-300 uppercase flex items-center gap-1 transition-colors"
                            >
                              {t('inbox.details')} <ChevronRight size={11} />
                            </button>
                            {item.thread_id && (item.thread_count ?? 1) > 1 && (
                              <button
                                onClick={e => { e.stopPropagation(); _handleToggleThreadExpansion(item); }}
                                aria-expanded={expandedThreadIds.has(item.thread_id)}
                                aria-controls={`thread-messages-${item.thread_id}`}
                                aria-label={t('inbox.thread_message_count', { count: item.thread_count })}
                                className="text-[9px] font-bold text-primary-400 hover:text-primary-300 uppercase flex items-center gap-1 transition-colors min-h-[44px] py-2 px-2"
                              >
                                <ChevronRight size={11} className={`transition-transform duration-200 ${expandedThreadIds.has(item.thread_id) ? 'rotate-90' : ''}`} />
                                {t('inbox.thread_message_count', { count: item.thread_count })}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Expanded thread messages panel */}
                        {item.thread_id && expandedThreadIds.has(item.thread_id) && (
                          <div
                            id={`thread-messages-${item.thread_id}`}
                            className="mt-3 pt-3 border-t border-white/5 space-y-1.5"
                          >
                            {_threadLoadingIds.has(item.thread_id) && (
                              <div className="flex items-center gap-2 py-1.5 text-[11px] text-slate-500">
                                <RefreshCw size={11} className="animate-spin text-primary-400" />
                                <span>{t('common.syncing')}</span>
                              </div>
                            )}
                            {!_threadLoadingIds.has(item.thread_id) && _threadLoadErrors[item.thread_id] && (
                              <div className="flex items-center gap-2 py-1.5 text-[11px] text-slate-500">
                                <AlertCircle size={11} className="text-red-400/70" />
                                <span>{t('common.network_error_try_again')}</span>
                              </div>
                            )}
                            {!_threadLoadingIds.has(item.thread_id) && !_threadLoadErrors[item.thread_id] && threadItemsById[item.thread_id]?.map((msg, mi) => (
                              <button
                                key={msg.gmail_message_id || String(mi)}
                                onClick={e => { e.stopPropagation(); openEmailDetail(msg); }}
                                className="w-full text-left flex items-start gap-3 px-3 py-3 min-h-[44px] rounded-xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/5 hover:border-white/10 transition-all"
                              >
                                {msg.is_read === false
                                  ? <Mail size={12} className="mt-0.5 text-primary-400 flex-shrink-0" />
                                  : <MailOpen size={12} className="mt-0.5 text-slate-600 flex-shrink-0" />
                                }
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center justify-between gap-2 mb-0.5">
                                    <span className={`text-[11px] truncate ${msg.is_read === false ? 'font-bold text-slate-200' : 'font-medium text-slate-400'}`}>
                                      {msg.sender.split('<')[0].trim()}
                                    </span>
                                    <span className="text-[10px] text-slate-600 shrink-0">{formatDisplayDate(msg.date_iso, msg.date)}</span>
                                  </div>
                                  <p className="text-[11px] text-slate-500 leading-snug line-clamp-2">
                                    {msg.ai_summary_text || msg.body || msg.summary}
                                  </p>
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </motion.div>
                    );
                  })
                ) : null}

                {/* BATCH LIMIT INDICATOR: Inform users about auto-summary limits */}
                {!isSearchActive && currentItems.length > 30 && (
                  <div className="w-full mt-8 mb-4 p-6 rounded-2xl bg-gradient-to-r from-primary-500/10 to-primary-400/10 border border-primary-500/20">
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-600/20 flex items-center justify-center border border-primary-500/30">
                        <Sparkles size={20} className="text-primary-400" />
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-black text-primary-300 mb-1 uppercase tracking-wide">
                          {t('inbox.auto_summary_limit_title')}
                        </h4>
                        <p className="text-xs text-slate-400 leading-relaxed mb-3">
                          {t('inbox.auto_summary_limit_count', { count: currentItems.length })}
                          {' '}
                          {t('inbox.auto_summary_limit_body', { limit: 30 })}
                        </p>
                        <p className="text-xs text-slate-500">
                          <strong className="text-primary-400">💡 {t('inbox.auto_summary_limit_tip_label')}</strong>{' '}
                          {t('inbox.auto_summary_limit_tip', { start: 31 })}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {!isSearchActive && connectedAccounts.length === 0 && !error ? (
                  /* ONBOARDING GUIDE: Professional zero-account state with step-by-step instructions */
                  <div className="w-full py-10 flex flex-col items-center gap-6 text-center max-w-lg mx-auto">
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary-500/20 to-primary-400/20 flex items-center justify-center border border-primary-500/30 relative shadow-2xl">
                      <Mail size={36} className="text-primary-400" />
                      <div className="absolute inset-0 rounded-full border border-primary-500/20 animate-pulse" />
                    </div>

                    <div className="space-y-2">
                      <h3 className="text-2xl font-black text-white">{t('auth.welcome_to_brand', { brand: brandName })}</h3>
                      <p className="text-slate-400 text-sm font-medium">
                        {t('auth.connect_gmail_intro')}
                      </p>
                    </div>

                    <div className="w-full bg-white/[0.02] border border-white/5 rounded-2xl p-5 text-left space-y-4">
                      <div className="flex gap-3 items-start">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-600 flex items-center justify-center text-white font-black text-xs">1</div>
                        <div>
                          <p className="text-slate-200 text-sm font-semibold">{t('auth.connect_gmail_account')}</p>
                          <p className="text-slate-500 text-xs mt-0.5">{t('auth.authorize_access_help')}</p>
                        </div>
                      </div>
                      <div className="flex gap-3 items-start">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-600 flex items-center justify-center text-white font-black text-xs">2</div>
                        <div>
                          <p className="text-slate-200 text-sm font-semibold">{t('auth.select_your_account_step')}</p>
                          <p className="text-slate-500 text-xs mt-0.5">
                            {t('auth.select_your_account_step_help', { maxAccounts: MAX_CONNECTED_ACCOUNTS })}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-3 items-start">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-600 flex items-center justify-center text-white font-black text-xs">3</div>
                        <div>
                          <p className="text-slate-200 text-sm font-semibold">{t('auth.feed_syncs_automatically')}</p>
                          <p className="text-slate-500 text-xs mt-0.5">{t('auth.feed_syncs_automatically_help')}</p>
                        </div>
                      </div>
                    </div>

                    <a
                      href={apiService.getGoogleAuthUrl()}
                      className="inline-flex items-center gap-3 px-6 py-3 rounded-xl bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white text-sm font-bold transition-all shadow-2xl shadow-primary-600/30 active:scale-95 border border-primary-400/20"
                    >
                      <Mail size={16} />
                      <span>{t('auth.connect_your_first_account')}</span>
                      <ChevronRight size={14} />
                    </a>

                    <p className="text-slate-600 text-xs max-w-xs">
                      {t('auth.read_only_inbox_notice')}
                    </p>
                  </div>
                ) : !activeEmail && connectedAccounts.length > 0 ? (
                  /* CRITICAL: Show "Select Account" when accounts exist but none is active */
                  <div className="w-full py-16 flex flex-col items-center gap-6 text-center">
                    <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary-500/20 to-primary-400/20 flex items-center justify-center border border-primary-500/30 relative shadow-xl">
                      <Mail size={28} className="text-primary-400" />
                      <div className="absolute inset-0 rounded-full border border-primary-500/20 animate-pulse" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-black text-white mb-2">{t('auth.select_account_to_begin')}</h3>
                      <p className="text-slate-400 max-w-md font-medium mb-6">
                        {t(
                          connectedAccounts.length === 1
                            ? 'auth.connected_accounts_summary_one'
                            : 'auth.connected_accounts_summary_other',
                          { count: connectedAccounts.length }
                        )}
                      </p>
                      <div className="flex flex-wrap gap-3 justify-center">
                        {connectedAccounts.map((acc) => (
                          acc.auth_required ? (
                            <a
                              key={acc.account_id}
                              href={apiService.getGoogleAuthUrl()}
                              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20 hover:border-amber-400/50 transition-all group"
                              title={t('auth.authentication_expired_click_to_reconnect')}
                            >
                              <span className={`flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(acc.account_id)} text-[10px] font-black text-white shadow-md`}>
                                {getEmailInitials(acc.account_id)}
                              </span>
                              <div className="text-left">
                                <div className="text-xs font-bold text-amber-400 group-hover:text-amber-300 transition-colors">
                                  {acc.account_id.split('@')[0]}
                                </div>
                                <div className="text-[9px] font-black text-amber-500 uppercase tracking-wider">{t('settings.reconnect_required')}</div>
                              </div>
                            </a>
                          ) : (
                            <button
                              key={acc.account_id}
                              onClick={() => handleSwitchAccount(acc.account_id)}
                              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 hover:bg-primary-600/10 hover:border-primary-500/30 transition-all group"
                            >
                              <span className={`flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(acc.account_id)} text-[10px] font-black text-white shadow-md`}>
                                {getEmailInitials(acc.account_id)}
                              </span>
                              <span className="text-xs font-bold text-slate-300 group-hover:text-primary-300 transition-colors">
                                {acc.account_id.split('@')[0]}
                              </span>
                            </button>
                          )
                        ))}
                      </div>
                    </div>
                  </div>
                ) : showInboxEmptyState && (
                  <div className="w-full py-32 flex flex-col items-center gap-6 text-center">
                    <div className="w-24 h-24 rounded-full bg-white/[0.03] flex items-center justify-center text-slate-600 border border-white/5 relative shadow-inner">
                      <Mail size={40} className="text-primary-500/20" />
                      <div className="absolute inset-0 rounded-full border border-primary-500/10 animate-ping" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-black text-white mb-2">
                        {t('inbox.channel_clear', { category: getCategoryDisplayLabel(filterCategory) })}
                      </h3>
                      <p className="text-slate-500 max-w-xs font-medium">
                        {t('inbox.no_fresh_briefings_in_filter', { category: getCategoryDisplayLabel(filterCategory) })}
                      </p>
                    </div>
                  </div>
                )}
              </AnimatePresence>
            </div>
          )}

          {showInboxPagination && (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3 sm:gap-8 mt-4 w-full max-w-sm sm:max-w-none mx-auto">
              <button
                onClick={() => setCurrentPage(Math.max(1, effectiveInboxPage - 1))}
                disabled={effectiveInboxPage === 1}
                className="w-full sm:w-auto px-4 sm:px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest text-center"
              >
                {t('common.previous')}
              </button>
              <div className="flex flex-col items-center min-w-0 sm:min-w-[120px]">
                <span className="text-[10px] font-black text-primary-500 uppercase tracking-[0.2em] mb-1">{t('common.navigation')}</span>
                <span className="text-white font-black text-sm">{getPageStatusLabel(effectiveInboxPage, totalPages)}</span>
              </div>
              <button
                onClick={() => setCurrentPage(Math.min(totalPages, effectiveInboxPage + 1))}
                disabled={effectiveInboxPage === totalPages}
                className="w-full sm:w-auto px-4 sm:px-6 py-3 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/[0.05] disabled:opacity-30 disabled:pointer-events-none transition-all text-xs font-black uppercase tracking-widest text-center"
              >
                {t('common.next')}
              </button>
            </div>
          )}
        </main>
      </div>

      <footer className="max-w-7xl mx-auto px-6 pt-32 pb-16">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8 border-t border-white/5 pt-12">
          <div className="flex items-center gap-2 text-slate-600">
            <Shield size={18} className="text-primary-500/50" />
            <span className="text-[10px] font-black uppercase tracking-[0.3em]">{t('footer.hardware_aligned_intelligence')}</span>
          </div>
          <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest opacity-50">{t('footer.executive_brain_ecosystem_2026')}</p>
        </div>
        <div className="mt-8 pt-6 border-t border-white/5 flex justify-center">
          <button
            type="button"
            onClick={() => setShowDeleteModal(true)}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all"
          >
            Delete Account
          </button>
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
              className="bg-brand-surface border border-brand-border rounded-3xl p-8 max-w-sm w-full mx-4 shadow-2xl"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-2xl bg-rose-500/10 flex items-center justify-center">
                  <LogOut size={18} className="text-rose-400" />
                </div>
                <h3 className="text-white font-black text-lg">{t('auth.disconnect_account_heading')}</h3>
              </div>
              <p className="text-slate-400 text-sm mb-2">
                {t('auth.disconnect_account_prompt', { account: confirmDisconnect })}
              </p>
              <p className="text-slate-600 text-xs mb-8">
                {t('auth.disconnect_account_notice')}
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmDisconnect(null)}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-white/10 text-slate-400 hover:text-white text-sm font-bold transition-all"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={() => handleDisconnect(confirmDisconnect)}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-sm font-bold transition-all"
                >
                  {t('auth.disconnect_account_confirm')}
                </button>

              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Email Detail Modal — centered blocking dialog (read-only view) */}
      <AnimatePresence>
        {selectedEmailDetail && activeModal === 'detail' && (
          <EmailDetailModal
            email={selectedEmailDetail}
            panelView={panelView}
            detailIsSent={detailIsSent}
            modifyScope={!!accounts.find(a => a.account_id === activeEmail)?.modify_scope}
            isRead={isDetailRead}
            actionItemsRef={actionItemsRef}
            isSummarizing={!!selectedEmailDetail?.gmail_message_id && summarizingIds.has(selectedEmailDetail.gmail_message_id)}
            readStatePending={readStatePending}
            onClose={closeDetailPanel}
            onSwitchView={setPanelView}
            onOpenReply={handleOpenReply}
            onSummarize={handleSummarizeFromModal}
            onMarkRead={handleMarkRead}
            onMarkUnread={handleMarkUnread}
            onAskAssistant={handleOpenAssistant}
            getCategoryStyles={getCategoryStyles}
            preferredLanguage={aiLanguage}
            onGeneratePreferred={handleSummarizeFromModal}
          />
        )}
      </AnimatePresence>

      {/* Reply Compose Modal — standalone compose dialog */}
      <AnimatePresence>
        {selectedEmailDetail && activeModal === 'compose' && (
          <ReplyComposeModal
            email={selectedEmailDetail}
            accountEmail={activeEmail ?? undefined}
            replyBody={replyBody}
            replySubject={replySubject}
            replyCC={replyCC}
            sending={sending}
            panelError={panelError}
            replyTextareaRef={replyTextareaRef}
            onDiscard={handleDiscardCompose}
            onSend={handleSendReply}
            onReplyBodyChange={setReplyBody}
            onReplySubjectChange={setReplySubject}
            onReplyCCChange={setReplyCC}
            selectedTone={selectedTone}
            availableTones={availableTones}
            onToneChange={handleToneChange}
            templates={templates}
            templatesLoading={templatesLoading}
            templatesError={templatesError}
            templateSaving={templateSaving}
            templateDeletingId={templateDeletingId}
            onApplyTemplate={handleApplyTemplate}
            onSaveTemplate={handleSaveTemplate}
            onDeleteTemplate={handleDeleteTemplate}
            buildAttribution={buildAttribution}
            attachments={replyAttachments}
            attachmentError={replyAttachmentError}
            attachmentsTotalBytes={replyAttachmentsTotalBytes}
            attachmentsDisabled={attachmentsDisabled}
            onAddAttachments={handleAddAttachments}
            onRemoveAttachment={handleRemoveAttachment}
          />
        )}
      </AnimatePresence>

      {/* AI Assistant Panel — right-side drawer, Escape returns to detail */}
      {selectedEmailDetail && activeModal === 'assistant' && (
        <>
          <div
            className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm"
            aria-hidden="true"
            onClick={() => setActiveModal('detail')}
          />
          <div className="fixed inset-y-0 right-0 z-[200] w-full sm:w-[380px] flex flex-col">
            <AssistantPanel
              email={selectedEmailDetail}
              onUseDraft={handleUseDraft}
              onClose={() => setActiveModal('detail')}
              selectedTone={selectedTone}
              availableTones={availableTones}
              onToneChange={handleToneChange}
            />
          </div>
        </>
      )}

      <DeleteAccountModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setDeleteAccountError(null);
        }}
        onSuccess={handleDeleteAccountSuccess}
        isDeleting={isDeletingAccount}
        error={deleteAccountError}
      />

      {/* Scroll to Top FAB - Bottom Right — hidden while any modal is open */}
      <AnimatePresence>
        {showScrollTop && activeModal === 'none' && !selectedEmailDetail && (
          <motion.button
            initial={{ opacity: 0, y: 20, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.8 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            aria-label={t('common.scroll_to_top')}
            className="fixed bottom-20 right-4 sm:bottom-6 sm:right-6 z-50 w-10 h-10 sm:w-11 sm:h-11 flex items-center justify-center rounded-full bg-brand-surface border border-brand-border text-slate-400 hover:text-white hover:border-primary-500/40 hover:bg-primary-600/20 shadow-xl transition-all duration-200 hover:scale-105"
          >
            <svg
              className="w-4 h-4 sm:w-[18px] sm:h-[18px]"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
            </svg>
          </motion.button>
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

