import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { X } from 'lucide-react';
import { AttachmentStripItem } from './AttachmentStrip';

interface Props {
    attachment: AttachmentStripItem;
    onClose: () => void;
}

export function ImageLightbox({ attachment, onClose }: Props) {
    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                if (typeof event.stopImmediatePropagation === 'function') {
                    event.stopImmediatePropagation();
                }
                onClose();
            }
        };

        window.addEventListener('keydown', onKeyDown, true);
        return () => window.removeEventListener('keydown', onKeyDown, true);
    }, [onClose]);

    if (!attachment.preview_url) {
        return null;
    }

    return (
        <>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={onClose}
                className="fixed inset-0 z-[260] bg-black/85 backdrop-blur-sm"
                aria-hidden="true"
            />

            <div className="fixed inset-0 z-[270] flex items-center justify-center p-4">
                <motion.div
                    initial={{ opacity: 0, scale: 0.96, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.96, y: 10 }}
                    transition={{ duration: 0.18, ease: 'easeOut' }}
                    role="dialog"
                    aria-modal="true"
                    aria-label={attachment.filename}
                    className="relative flex items-center justify-center"
                >
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close image preview"
                        className="absolute right-3 top-3 z-10 inline-flex h-10 w-10 items-center justify-center rounded-full bg-black/70 text-white hover:bg-black/90 transition-colors"
                    >
                        <X size={18} />
                    </button>

                    <img
                        src={attachment.preview_url}
                        alt={attachment.filename}
                        className="max-w-[90vw] max-h-[90vh] object-contain"
                    />
                </motion.div>
            </div>
        </>
    );
}
