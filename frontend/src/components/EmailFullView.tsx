import { RefObject, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, Sparkles } from 'lucide-react';
import { Briefing } from '@types';
import { normalizeBodyText } from '@utils/normalizeBodyText';
import { AttachmentStrip, AttachmentStripItem } from './AttachmentStrip';
import { ImageLightbox } from './ImageLightbox';

interface Props {
  email: Briefing;
  actionItemsRef: RefObject<HTMLDivElement>;
  onBackToSummary: () => void;
}

interface LinkedFileItem {
  title: string;
  url: string;
  provider: 'google_drive' | 'google_docs' | 'google_sheets' | 'google_slides' | string;
}

interface RenderedEmailPayload {
  gmail_message_id: string;
  body_html: string | null;
  body_text: string | null;
  attachments: AttachmentStripItem[];
  linked_files?: LinkedFileItem[];
}

function linkedFileCta(provider: string): string {
  if (provider === 'google_docs') return 'Open in Docs';
  if (provider === 'google_sheets') return 'Open in Sheets';
  if (provider === 'google_slides') return 'Open in Slides';
  return 'Open in Drive';
}

// ---------------------------------------------------------------------------
// HTML sanitization pipeline — three single-responsibility steps
// ---------------------------------------------------------------------------

/**
 * Step 1 — Security pass.
 * Strips dangerous tags, on* attributes, email-authored style attributes,
 * cid: references, and any unsafe src values.
 *
 * Allowed img src schemes after this pass:
 *   data:image/...   — attachment previews embedded as data URIs by backend
 *   /api/attachments/... — byte-serve route
 *   https://         — remote images, but ONLY when the element is <img>
 *
 * The https:// allowance is explicitly gated on tagName === 'img'.
 * Any non-img element with an https:// src is stripped here.
 */
function securitySanitize(htmlInput: string): Document {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlInput, 'text/html');

  doc.querySelectorAll('script, style, iframe, object, embed, link, meta, form').forEach((node) => {
    node.remove();
  });

  const allNodes = doc.body.querySelectorAll('*');

  allNodes.forEach((node) => {
    const element = node as HTMLElement;
    const tagName = element.tagName.toLowerCase();

    [...element.attributes].forEach((attribute) => {
      const attrName = attribute.name.toLowerCase();
      const attrValue = attribute.value.trim();

      if (attrName.startsWith('on') || attrName === 'style') {
        element.removeAttribute(attribute.name);
        return;
      }

      if ((attrName === 'src' || attrName === 'href') && attrValue) {
        if (attrValue.startsWith('cid:')) {
          element.removeAttribute(attribute.name);
          return;
        }

        if (attrName === 'src') {
          const isDataImage = /^data:image\//i.test(attrValue);
          const isApiAttachment = attrValue.startsWith('/api/attachments/');
          // https:// only permitted on <img> — not on video, source, script, or anything else.
          const isRemoteHttps = tagName === 'img' && attrValue.startsWith('https://');
          if (!isDataImage && !isApiAttachment && !isRemoteHttps) {
            element.removeAttribute(attribute.name);
          }
          return;
        }

        if (attrName === 'href') {
          const isSafeHref =
            attrValue.startsWith('http://') ||
            attrValue.startsWith('https://') ||
            attrValue.startsWith('mailto:') ||
            attrValue.startsWith('tel:') ||
            attrValue.startsWith('/');

          if (!isSafeHref) {
            element.removeAttribute(attribute.name);
            return;
          }

          element.setAttribute('target', '_blank');
          element.setAttribute('rel', 'noopener noreferrer');
        }
      }
    });

    if (tagName === 'img') {
      element.removeAttribute('width');
      element.removeAttribute('height');
      element.setAttribute('loading', 'lazy');
      element.className = [element.className, 'max-w-full max-h-[600px] object-contain mx-auto my-3'].filter(Boolean).join(' ');
    }
  });

  return doc;
}

/**
 * Step 2 — Content image resolution.
 * CID inline images are already stripped in securitySanitize; the backend
 * /rendered endpoint resolves them to data URIs before we receive the HTML.
 * data:image/... and /api/attachments/... pass through untouched.
 * This function is kept as a structural separation point for future needs.
 */
function resolveContentImages(_doc: Document): void {
  // No-op: CID → data URI resolution happens server-side at render time.
}

/**
 * Step 3 — Remote image policy.
 * Targets only img elements whose src begins with https://.
 *
 * Each remote image receives:
 *   - Browser-native privacy posture: lazy / no-referrer / async / low priority
 *   - data-remote-image="true" — query marker for DOM lifecycle useEffect
 *   - data-remote-image-state="loading" — state machine entry point
 *   - opacity:0 with transition — hidden until useEffect confirms load success
 *
 * No structural DOM mutation (no wrapper insertion).
 * http://, blob:, javascript:, and all other non-https schemes are not
 * reached here — securitySanitize already stripped them from <img> src.
 */
function applyRemoteImagePolicy(doc: Document): void {
  doc.body.querySelectorAll<HTMLImageElement>('img').forEach((img) => {
    const src = img.getAttribute('src') ?? '';
    if (!src.startsWith('https://')) return;

    img.setAttribute('referrerpolicy', 'no-referrer');
    img.setAttribute('decoding', 'async');
    img.setAttribute('fetchpriority', 'low');
    img.setAttribute('data-remote-image', 'true');
    img.setAttribute('data-remote-image-state', 'loading');
    // Hidden until load/error fires; transition gives a clean reveal.
    img.style.opacity = '0';
    img.style.transition = 'opacity 0.2s ease';
  });
}

/** Runs the full three-step pipeline and returns the safe HTML string. */
function buildSanitizedHtml(htmlInput: string): string {
  const doc = securitySanitize(htmlInput);
  resolveContentImages(doc);
  applyRemoteImagePolicy(doc);
  return doc.body.innerHTML;
}

// ---------------------------------------------------------------------------

/**
 * Full View — shows AI summary (if present) and the complete message body.
 *
 * Body rendering strategy:
 *   - If rendered HTML is available from the backend, run buildSanitizedHtml
 *     (security sanitize → resolve content images → remote image policy)
 *     and inject via dangerouslySetInnerHTML
 *   - Remote https:// images are allowed on <img> only, with no-referrer /
 *     lazy / async / low-priority policy; a DOM lifecycle effect manages
 *     reveal on load and silent collapse on error (no broken-image glyph)
 *   - Otherwise fall back to normalized plaintext paragraph rendering
 *   - AttachmentStrip renders non-inline attachments below the body
 *   - ImageLightbox renders full-size attachment previews on demand
 *
 * All action buttons live in EmailDetailModal's footer.
 */
export function EmailFullView({ email, actionItemsRef, onBackToSummary }: Props) {
  const [renderedEmail, setRenderedEmail] = useState<RenderedEmailPayload | null>(null);
  const [renderLoading, setRenderLoading] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [lightboxAttachment, setLightboxAttachment] = useState<AttachmentStripItem | null>(null);
  const bodyContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLightboxAttachment(null);
  }, [email.gmail_message_id]);

  useEffect(() => {
    if (!email.gmail_message_id) {
      setRenderedEmail(null);
      setRenderLoading(false);
      setRenderError(null);
      return;
    }

    const controller = new AbortController();

    async function loadRenderedEmail() {
      setRenderLoading(true);
      setRenderError(null);

      try {
        const response = await fetch(`/api/emails/${encodeURIComponent(email.gmail_message_id || '')}/rendered`, {
          credentials: 'include',
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Rendered email fetch failed with status ${response.status}`);
        }

        const payload = (await response.json()) as RenderedEmailPayload;
        setRenderedEmail(payload);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setRenderedEmail(null);
        setRenderError('Unable to load inline images and attachments for this email.');
      } finally {
        if (!controller.signal.aborted) {
          setRenderLoading(false);
        }
      }
    }

    loadRenderedEmail();

    return () => controller.abort();
  }, [email.gmail_message_id]);

  const rawText = renderedEmail?.body_text || email.body || email.summary || '';
  const bodyText = normalizeBodyText(rawText);
  const paragraphs = bodyText ? bodyText.split('\n\n').filter((p) => p.trim().length > 0) : [];

  const sanitizedHtml = useMemo(
    () => (renderedEmail?.body_html ? buildSanitizedHtml(renderedEmail.body_html) : null),
    [renderedEmail?.body_html]
  );

  // Attach native load/error listeners to remote images after sanitizedHtml renders.
  // Handles three cases:
  //   already loaded (cached)  → revealImage synchronously
  //   already errored          → collapseImage synchronously
  //   pending                  → attach load/error listeners, clean up on effect re-run
  useEffect(() => {
    const container = bodyContainerRef.current;
    if (!container || !sanitizedHtml) return;

    const remoteImages = Array.from(
      container.querySelectorAll<HTMLImageElement>('img[data-remote-image="true"]')
    );
    if (remoteImages.length === 0) return;

    const cleanups: (() => void)[] = [];

    for (const img of remoteImages) {
      const revealImage = () => {
        img.setAttribute('data-remote-image-state', 'loaded');
        img.style.opacity = '1';
      };

      const collapseImage = () => {
        img.setAttribute('data-remote-image-state', 'error');
        // display:none removes the img from flow — no raw broken-image glyph remains.
        img.style.display = 'none';
      };

      if (img.complete) {
        // Already settled before listeners could attach (cache hit or immediate error).
        if (img.naturalWidth > 0) {
          revealImage();
        } else {
          collapseImage();
        }
        continue;
      }

      img.addEventListener('load', revealImage);
      img.addEventListener('error', collapseImage);
      cleanups.push(() => {
        img.removeEventListener('load', revealImage);
        img.removeEventListener('error', collapseImage);
      });
    }

    return () => {
      cleanups.forEach((fn) => fn());
    };
  }, [sanitizedHtml]);

  return (
    <div className="space-y-6">
      {/* AI Analysis — mirrored from Quick View so context is preserved */}
      {email.ai_summary_text && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-indigo-400" />
            <h3 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">AI Analysis</h3>
            {email.ai_summary_model && (
              <span className="text-[9px] text-slate-600 font-bold">{email.ai_summary_model}</span>
            )}
          </div>

          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
            <p className="text-sm leading-relaxed text-slate-200">{email.ai_summary_text}</p>
          </div>

          {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
            <div ref={actionItemsRef} className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
              <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-3">Action Items</p>
              <ol className="space-y-2 list-decimal list-inside">
                {email.ai_summary_json.action_items.map((action: string, idx: number) => (
                  <li key={idx} className="text-sm leading-relaxed text-slate-300">{action}</li>
                ))}
              </ol>
            </div>
          )}

          {email.ai_summary_json?.urgency && (
            <p className="text-xs text-slate-500">
              Urgency{' '}
              <span className="font-bold text-slate-400 capitalize">{email.ai_summary_json.urgency}</span>
            </p>
          )}
        </div>
      )}

      {/* Full Message */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Full Message</h3>
          <button
            onClick={onBackToSummary}
            className="text-[10px] font-bold text-slate-600 hover:text-slate-400 transition-colors"
          >
            ← Summary
          </button>
        </div>

        <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
          {renderLoading ? (
            <p className="text-sm leading-relaxed text-slate-400">Loading inline images and attachments…</p>
          ) : sanitizedHtml ? (
            <div
              ref={bodyContainerRef}
              className="space-y-3 text-sm leading-relaxed text-slate-300 break-words overflow-x-auto"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />
          ) : paragraphs.length > 0 ? (
            <div className="space-y-3">
              {paragraphs.map((para, i) => (
                <p
                  key={i}
                  className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap break-words"
                >
                  {para}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-relaxed text-slate-500 italic">No message body available.</p>
          )}
        </div>

        {renderError && (
          <p className="text-xs leading-relaxed text-amber-400">
            {renderError}
          </p>
        )}

        <AttachmentStrip
          attachments={renderedEmail?.attachments || []}
          onOpenImage={setLightboxAttachment}
        />

        {(renderedEmail?.linked_files ?? []).length > 0 && (
          <div className="space-y-2 pt-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Linked files</p>
            <div className="flex flex-col gap-1">
              {(renderedEmail!.linked_files!).map((file, idx) => (
                <a
                  key={idx}
                  href={file.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm bg-white/[0.03] border border-white/5 hover:border-sky-500/30 transition-colors"
                >
                  <ExternalLink size={13} className="shrink-0 text-sky-400" />
                  <span className="flex-1 truncate text-sky-400 hover:text-sky-300">{file.title}</span>
                  <span className="shrink-0 text-xs font-semibold text-sky-500 hover:text-sky-300">{linkedFileCta(file.provider)}</span>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      {lightboxAttachment && (
        <ImageLightbox
          attachment={lightboxAttachment}
          onClose={() => setLightboxAttachment(null)}
        />
      )}
    </div>
  );
}
