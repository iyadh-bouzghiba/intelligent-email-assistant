import { Download, File, FileSpreadsheet, FileText, Image as ImageIcon } from 'lucide-react';

export interface AttachmentStripItem {
    attachment_id?: string | null;
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

function formatBytes(size: number): string {
    if (!Number.isFinite(size) || size <= 0) {
        return '0 B';
    }

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

function getAttachmentIcon(mimeType: string) {
    if (mimeType.includes('pdf')) {
        return FileText;
    }

    if (
        mimeType.includes('sheet') ||
        mimeType.includes('excel') ||
        mimeType.includes('spreadsheet') ||
        mimeType.includes('csv')
    ) {
        return FileSpreadsheet;
    }

    if (mimeType.includes('word') || mimeType.includes('document') || mimeType.includes('officedocument')) {
        return FileText;
    }

    if (mimeType.startsWith('image/')) {
        return ImageIcon;
    }

    return File;
}

export function AttachmentStrip({ attachments, onOpenImage }: Props) {
    const displayAttachments = attachments.filter((attachment) => !attachment.is_inline);

    if (displayAttachments.length === 0) {
        return null;
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Attachments</h3>
                <span className="text-[11px] text-slate-500">{displayAttachments.length} item(s)</span>
            </div>

            <div className="flex flex-wrap gap-3">
                {displayAttachments.map((attachment) => {
                    const Icon = getAttachmentIcon(attachment.mime_type);
                    const itemKey = `${attachment.attachment_id ?? attachment.filename}-${attachment.size}`;

                    if (attachment.is_image) {
                        return (
                            <div
                                key={itemKey}
                                className="w-[80px] space-y-2"
                            >
                                {attachment.too_large || !attachment.preview_url ? (
                                    <div className="h-[80px] w-[80px] rounded-[6px] border border-dashed border-slate-600 bg-slate-900/60 p-2 flex items-center justify-center text-center">
                                        <span className="text-[10px] leading-tight text-slate-400">
                                            {attachment.placeholder_text || 'Preview unavailable'}
                                        </span>
                                    </div>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={() => onOpenImage(attachment)}
                                        className="block h-[80px] w-[80px] overflow-hidden rounded-[6px] border border-white/10 bg-slate-950/60 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                        aria-label={`Open image ${attachment.filename}`}
                                    >
                                        <img
                                            src={attachment.preview_url}
                                            alt={attachment.filename}
                                            className="h-[80px] w-[80px] rounded-[6px] object-cover"
                                        />
                                    </button>
                                )}

                                <div className="space-y-1">
                                    <p className="text-[11px] font-medium text-slate-300 break-words leading-tight">
                                        {attachment.filename}
                                    </p>
                                    <p className="text-[10px] text-slate-500">{formatBytes(attachment.size)}</p>
                                </div>
                            </div>
                        );
                    }

                    return (
                        <div
                            key={itemKey}
                            className="min-w-[220px] max-w-[280px] rounded-2xl border border-white/10 bg-white/[0.03] p-3"
                        >
                            <div className="flex items-start gap-3">
                                <div className="h-[44px] w-[44px] rounded-xl border border-white/10 bg-slate-900/80 flex items-center justify-center flex-shrink-0">
                                    <Icon size={18} className="text-slate-300" />
                                </div>

                                <div className="min-w-0 flex-1 space-y-1">
                                    <p className="text-sm font-medium text-slate-200 break-words leading-tight">
                                        {attachment.filename}
                                    </p>
                                    <p className="text-[11px] text-slate-500">
                                        {attachment.mime_type} • {formatBytes(attachment.size)}
                                    </p>

                                    {attachment.too_large ? (
                                        <p className="text-[11px] text-amber-400 leading-relaxed">
                                            {attachment.placeholder_text || 'File too large to preview'}
                                        </p>
                                    ) : attachment.download_url ? (
                                        <a
                                            href={attachment.download_url}
                                            className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-indigo-400 hover:text-indigo-300"
                                            download
                                        >
                                            <Download size={12} />
                                            Download
                                        </a>
                                    ) : (
                                        <p className="text-[11px] text-slate-500">Download unavailable</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
