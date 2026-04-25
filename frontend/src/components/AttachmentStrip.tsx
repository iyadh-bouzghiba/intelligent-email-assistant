import { Download, Eye, File, FileSpreadsheet, FileText, Image as ImageIcon } from 'lucide-react';

export interface AttachmentStripItem {
    attachment_key?: string | null;
    filename: string;
    mime_type: string;
    size: number;
    is_inline: boolean;
    is_image: boolean;
    preview_url?: string | null;
    download_url?: string | null;
    too_large: boolean;
    placeholder_text?: string | null;
}

interface Props {
    attachments: AttachmentStripItem[];
    onOpenImage: (attachment: AttachmentStripItem) => void;
}

type FileCategory = 'image' | 'pdf' | 'text' | 'office' | 'other';

function formatBytes(size: number): string {
    if (!Number.isFinite(size) || size <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = size;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    const rounded = value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1);
    return `${rounded} ${units[unitIndex]}`;
}

function getFileCategory(mimeType: string): FileCategory {
    if (mimeType.startsWith('image/')) return 'image';
    if (mimeType === 'application/pdf') return 'pdf';
    if (
        mimeType === 'text/plain' ||
        mimeType === 'text/csv' ||
        mimeType === 'text/tab-separated-values' ||
        mimeType === 'application/json'
    ) return 'text';
    if (
        mimeType.includes('word') ||
        mimeType.includes('officedocument') ||
        mimeType.includes('spreadsheetml') ||
        mimeType.includes('excel') ||
        mimeType.includes('presentationml') ||
        mimeType.includes('powerpoint') ||
        mimeType.includes('opendocument') ||
        mimeType === 'application/vnd.ms-excel' ||
        mimeType === 'application/vnd.ms-powerpoint' ||
        mimeType === 'application/vnd.ms-word'
    ) return 'office';
    return 'other';
}

function getAttachmentIcon(mimeType: string, category: FileCategory) {
    if (category === 'image') return ImageIcon;
    if (category === 'pdf') return FileText;
    if (
        mimeType.includes('sheet') ||
        mimeType.includes('excel') ||
        mimeType.includes('spreadsheet') ||
        mimeType.includes('csv')
    ) return FileSpreadsheet;
    if (
        mimeType.includes('word') ||
        mimeType.includes('document') ||
        mimeType.includes('officedocument')
    ) return FileText;
    return File;
}

interface CardProps {
    attachment: AttachmentStripItem;
    onOpenImage: (attachment: AttachmentStripItem) => void;
}

function AttachmentCard({ attachment, onOpenImage }: CardProps) {
    const category = getFileCategory(attachment.mime_type);
    const Icon = getAttachmentIcon(attachment.mime_type, category);
    const hasPreview = category === 'image' && !attachment.too_large && !!attachment.preview_url;
    const canDownload = !attachment.too_large && !!attachment.download_url;

    return (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 flex flex-col gap-2 min-w-0">
            {/* Header: thumbnail/icon + filename + size */}
            <div className="flex items-start gap-2">
                <div className="h-10 w-10 rounded-lg border border-white/10 bg-slate-900/80 flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {hasPreview ? (
                        <img
                            src={attachment.preview_url!}
                            alt=""
                            className="h-10 w-10 object-cover"
                        />
                    ) : (
                        <Icon size={18} className="text-slate-400" />
                    )}
                </div>

                <div className="min-w-0 flex-1">
                    <p
                        className="text-xs font-medium text-slate-200 leading-tight break-all line-clamp-2"
                        title={attachment.filename}
                    >
                        {attachment.filename}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-0.5">{formatBytes(attachment.size)}</p>
                </div>
            </div>

            {/* Actions row */}
            <div className="flex items-center gap-2 flex-wrap">
                {attachment.too_large ? (
                    <span className="text-[10px] text-amber-400 leading-relaxed">
                        {attachment.placeholder_text || 'File too large'}
                    </span>
                ) : (
                    <>
                        {/* Image: View in lightbox */}
                        {category === 'image' && hasPreview && (
                            <button
                                type="button"
                                onClick={() => onOpenImage(attachment)}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                                <Eye size={11} />
                                View
                            </button>
                        )}

                        {/* Image: no preview available */}
                        {category === 'image' && !hasPreview && (
                            <span className="text-[10px] text-slate-500">Preview unavailable</span>
                        )}

                        {/* PDF: View in browser tab (served inline) */}
                        {category === 'pdf' && canDownload && (
                            <a
                                href={attachment.download_url!}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                                <Eye size={11} />
                                View
                            </a>
                        )}

                        {/* All downloadable non-image types */}
                        {category !== 'image' && canDownload && (
                            <a
                                href={attachment.download_url!}
                                download={category !== 'pdf'}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
                            >
                                <Download size={11} />
                                Download
                            </a>
                        )}

                        {/* Office files: honest note */}
                        {category === 'office' && (
                            <span className="text-[10px] text-slate-600">No in-app preview</span>
                        )}

                        {/* No download available */}
                        {category !== 'image' && !canDownload && (
                            <span className="text-[10px] text-slate-500">Download unavailable</span>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

export function AttachmentStrip({ attachments, onOpenImage }: Props) {
    const displayAttachments = attachments.filter((a) => !a.is_inline);

    if (displayAttachments.length === 0) return null;

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Attachments
                </h3>
                <span className="text-[11px] text-slate-600">
                    {displayAttachments.length} {displayAttachments.length === 1 ? 'file' : 'files'}
                </span>
            </div>

            <div className="grid grid-cols-2 gap-2 max-h-[360px] overflow-y-auto pr-0.5">
                {displayAttachments.map((attachment) => (
                    <AttachmentCard
                        key={`${attachment.attachment_key ?? attachment.filename}-${attachment.size}`}
                        attachment={attachment}
                        onOpenImage={onOpenImage}
                    />
                ))}
            </div>
        </div>
    );
}
