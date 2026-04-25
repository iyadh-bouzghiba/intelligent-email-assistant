import { RefObject, useEffect, useMemo, useState } from 'react';
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

function sanitizeResolvedHtml(htmlInput: string): string {
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
          if (!isDataImage && !attrValue.startsWith('/api/attachments/')) {
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

  return doc.body.innerHTML;
}

/**
 * Full View — shows AI summary (if present) and the complete message body.
 *
 * Body rendering strategy:
 *   - If rendered HTML is available from the backend, sanitize it in-browser
 *     and render it with resolved inline CID images
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
    () => (renderedEmail?.body_html ? sanitizeResolvedHtml(renderedEmail.body_html) : null),
    [renderedEmail?.body_html]
  );

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
